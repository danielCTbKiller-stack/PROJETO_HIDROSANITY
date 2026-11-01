"""Operação ao vivo: telemetria, gêmeo digital (digital twin) e alarmes.

Telemetria: leituras {elemento, grandeza, valor, ts} chegam por POST /api/telemetria
(SCADA, gateway OPC-UA/MQTT, Node-RED...) ou pelo simulador deste módulo.
  grandeza: pressao (mca; em válvula/bomba = jusante), vazao (L/s), nivel (m, reservatório)
  ts: segundos Unix ou data/hora ISO. O "agora" do gêmeo é o ts mais recente recebido.

Gêmeo digital: a cada 15 min (tempo da telemetria) roda o EPANET a partir do estado
medido (nível dos reservatórios, bomba ligada/desligada, hora do dia) e projeta as
próximas 24 h. Esse "esperado" é comparado com cada leitura que chega.

Alarmes:
  LIMITE        pressão de consumo < 10 / > 50 mca; reservatório < 25% (< 10% crítico) / > 95%
  VAZAMENTO     vazão de um setor persistentemente acima do gêmeo (> 15% por 15 min; > 30% crítico)
  DESVIO        vazão abaixo do gêmeo (registro fechado?) ou pressão a mais de 3 mca do gêmeo
  PREVISAO      reservatório previsto abaixo de 20% nas próximas 6 h
  COMUNICACAO   sensor sem leitura há mais de 10 min
"""
import os
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

import numpy as np
import wntr

from cadastro_para_inp import converter, ler_cadastro

UN = {"pressao": "mca", "vazao": "L/s", "nivel": "m"}
SYNC_S = 15 * 60          # re-sincronização do gêmeo
JANELA = 15 * 60          # persistência exigida para alarmes de desvio
SEM_COMUNICACAO = 10 * 60
GUARDA = 6 * 3600         # histórico em memória por sensor
HORIZONTE = 6 * 3600      # previsão usada nos alarmes
SEV = {"critico": 0, "alerta": 1, "info": 2}


def hora_do_dia(ts):
    d = datetime.fromtimestamp(ts)
    return d.hour * 3600 + d.minute * 60 + d.second


def txt_hora(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def _ts(v):
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(str(v)).timestamp()


class Gemeo:
    def __init__(self, gpkg):
        self.gpkg = gpkg
        self.lock = threading.RLock()
        c = ler_cadastro(gpkg)
        inp, rel = converter(camadas=c)
        if not rel.ok:
            raise ValueError("cadastro com erros: " + "; ".join(rel.erros[:3]))
        self.inp_path = os.path.join(tempfile.mkdtemp(prefix="gwater_gemeo_"), "base.inp")
        with open(self.inp_path, "w", encoding="utf-8") as f:
            f.write(inp)
        self.camada_de = {i: cam for cam in ("captacao", "reservatorio", "bomba", "valvula", "no_juncao", "trecho")
                          for i in c[cam]["id"]}
        self.setor_de = {i: s for cam in ("valvula", "no_juncao", "trecho", "bomba", "reservatorio")
                         for i, s in zip(c[cam]["id"], c[cam]["setor"]) if s}
        nj = c["no_juncao"]
        self.consumo = {i for i, t, d in zip(nj["id"], nj["tipo"], nj["demanda_base"])
                        if t in ("CONSUMO", "HIDRANTE", "PONTA") or (d or 0) > 0}
        rs = c["reservatorio"]
        self.nivel_max = {i: float(m) for i, m in zip(rs["id"], rs["nivel_max"]) if m}
        self.cadastro = c
        self.medido = defaultdict(deque)     # (el, gr) -> deque[(ts, valor)]
        self.esperado = defaultdict(deque)   # (el, gr) -> deque[(ts, esperado)]
        self.ultimo = {}
        self.agora = None
        self.recebido_em = None              # relógio real da última leitura (status de comunicação)
        self.prev = None                     # última projeção do gêmeo
        self.alarmes, self.historico, self.seq = {}, deque(maxlen=300), 0
        self.db = sqlite3.connect(gpkg[:-5] + "_telemetria.sqlite", check_same_thread=False)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS leitura (ts REAL, elemento TEXT, grandeza TEXT, valor REAL);
            CREATE INDEX IF NOT EXISTS ix_leitura ON leitura (elemento, grandeza, ts);
            CREATE TABLE IF NOT EXISTS alarme (id INTEGER, chave TEXT, tipo TEXT, severidade TEXT,
                elemento TEXT, setor TEXT, mensagem TEXT, inicio REAL, fim REAL, reconhecido REAL);""")

    # ------------------------------------------------------------ telemetria
    def receber(self, leituras):
        with self.lock:
            ok = []
            for l in leituras:
                gr = str(l["grandeza"]).lower()
                if gr not in UN:
                    raise ValueError(f"grandeza '{gr}' inválida (pressao, vazao ou nivel)")
                el, ts, v = str(l["elemento"]), _ts(l["ts"]), float(l["valor"])
                ok.append((ts, el, gr, v))
            if not ok:
                return 0
            ok.sort()
            self.db.executemany("INSERT INTO leitura VALUES (?,?,?,?)", ok)
            self.db.commit()
            for ts, el, gr, v in ok:
                self.medido[(el, gr)].append((ts, v))
                self.ultimo[(el, gr)] = (ts, v)
                self.agora = max(self.agora or ts, ts)
            self.recebido_em = time.time()
            # cada leitura é comparada com a projeção vigente quando foi medida;
            # só depois o gêmeo re-sincroniza (se já passaram 15 min)
            pendentes = []
            for ts, el, gr, v in ok:
                e = self.esperado_em(el, gr, ts)
                if e is None:
                    pendentes.append((ts, el, gr))
                else:
                    self.esperado[(el, gr)].append((ts, e))
            if self.prev is None or self.agora - self.prev["t0"] >= SYNC_S:
                self.sincronizar()
                for ts, el, gr in pendentes:
                    e = self.esperado_em(el, gr, ts)
                    if e is not None:
                        self.esperado[(el, gr)].append((ts, e))
            for d in (self.medido, self.esperado):
                for q in d.values():
                    while q and q[0][0] < self.agora - GUARDA:
                        q.popleft()
            self.avaliar()
            return len(ok)

    # ------------------------------------------------------------ gêmeo digital
    def sincronizar(self):
        """Roda o EPANET a partir do estado medido agora e projeta 24 h."""
        t0 = self.agora
        wn = wntr.network.WaterNetworkModel(self.inp_path)
        for tid, nmax in self.nivel_max.items():
            u = self.ultimo.get((tid, "nivel"))
            if u and t0 - u[0] < SEM_COMUNICACAO:
                tk = wn.get_node(tid)
                tk.init_level = min(max(u[1], tk.min_level), tk.max_level)
        for bid in wn.pump_name_list:
            u = self.ultimo.get((bid, "vazao"))
            if u and t0 - u[0] < SEM_COMUNICACAO:
                wn.get_link(bid).initial_status = (wntr.network.LinkStatus.Open if u[1] > 0.5
                                                   else wntr.network.LinkStatus.Closed)
        hd = int(hora_do_dia(t0) // 60 * 60)
        tm = wn.options.time
        tm.duration, tm.pattern_start, tm.start_clocktime = 24 * 3600, hd, hd
        with tempfile.TemporaryDirectory(prefix="gwater_sim_", ignore_cleanup_errors=True) as tmp:
            res = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=os.path.join(tmp, "g"))
        self.prev = {"t0": t0, "rel": res.node["pressure"].index.to_numpy(float), "res": res}

    def _serie_prev(self, el, gr):
        if not self.prev:
            return None
        n, l = self.prev["res"].node, self.prev["res"].link
        if gr == "vazao":
            return (l["flowrate"][el].abs() * 1000).to_numpy() if el in l["flowrate"] else None
        alvo = el + "__J" if self.camada_de.get(el) in ("valvula", "bomba") else el
        return n["pressure"][alvo].to_numpy() if alvo in n["pressure"] else None

    def esperado_em(self, el, gr, ts):
        s = self._serie_prev(el, gr)
        if s is None or ts < self.prev["t0"] - 60:
            return None
        return float(np.interp(ts - self.prev["t0"], self.prev["rel"], s))

    def previsao(self, el, gr, horizonte=HORIZONTE):
        s = self._serie_prev(el, gr)
        if s is None:
            return []
        t0, rel = self.prev["t0"], self.prev["rel"]
        m = rel <= (self.agora - t0) + horizonte
        return [(t0 + r, float(v)) for r, v in zip(rel[m], s[m]) if t0 + r >= self.agora]

    # ------------------------------------------------------------ alarmes
    def _ativar(self, chave, sev, tipo, el, msg, setor=None):
        a = self.alarmes.get(chave)
        if a is None:
            self.seq += 1
            a = {"id": self.seq, "chave": chave, "tipo": tipo, "severidade": sev, "elemento": el,
                 "setor": setor or self.setor_de.get(el), "mensagem": msg, "inicio": self.agora,
                 "fim": None, "reconhecido": None}
            self.alarmes[chave] = a
            self.historico.appendleft({**a, "evento": "ativado"})
            self.db.execute("INSERT INTO alarme VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (a["id"], chave, tipo, sev, el, a["setor"], msg, self.agora, None, None))
        else:
            if SEV[sev] < SEV[a["severidade"]]:  # agravou: volta a pedir reconhecimento
                a["reconhecido"] = None
                self.historico.appendleft({**a, "severidade": sev, "mensagem": msg, "evento": "agravado"})
            a["severidade"], a["mensagem"] = sev, msg
            self.db.execute("UPDATE alarme SET severidade=?, mensagem=? WHERE id=?", (sev, msg, a["id"]))
        return a

    def _limpar(self, chave):
        a = self.alarmes.pop(chave, None)
        if a:
            a["fim"] = self.agora
            self.historico.appendleft({**a, "evento": "normalizado"})
            self.db.execute("UPDATE alarme SET fim=? WHERE id=?", (self.agora, a["id"]))

    def reconhecer(self, aid):
        with self.lock:
            for a in self.alarmes.values():
                if a["id"] == aid:
                    a["reconhecido"] = self.agora
                    self.db.execute("UPDATE alarme SET reconhecido=? WHERE id=?", (self.agora, aid))
                    self.db.commit()
                    return True
            return False

    def _janela(self, chave):
        """Pares (medido, esperado) dos últimos JANELA s; None se a janela ainda não está coberta."""
        esp = [(t, e) for t, e in self.esperado[chave] if t >= self.agora - JANELA]
        if len(esp) < 3 or esp[0][0] > self.agora - 0.8 * JANELA:
            return None
        med = dict(self.medido[chave])
        par = [(med[t], e) for t, e in esp if t in med]
        return np.array(par) if len(par) >= 3 else None

    def avaliar(self):
        now = self.agora
        vivos = set()
        # comunicação e limites
        for (el, gr), (ts, v) in self.ultimo.items():
            ch = f"COMUNICACAO|{el}|{gr}"
            if now - ts > SEM_COMUNICACAO:
                self._ativar(ch, "alerta", "COMUNICACAO", el, f"{el} ({gr}) sem leitura há {(now - ts) / 60:.0f} min")
                vivos.add(ch)
                continue
            ch = f"LIMITE|{el}|{gr}"
            if gr == "pressao" and el in self.consumo:
                if v < 10:
                    self._ativar(ch, "critico", "LIMITE", el, f"Pressão em {el}: {v:.1f} mca, abaixo de 10 mca (NBR 12218)")
                    vivos.add(ch)
                elif v > 50:
                    self._ativar(ch, "alerta", "LIMITE", el, f"Pressão em {el}: {v:.1f} mca, acima de 50 mca (NBR 12218)")
                    vivos.add(ch)
            elif gr == "nivel" and el in self.nivel_max:
                p = v / self.nivel_max[el] * 100
                if p < 25 or p > 95:
                    sev = "critico" if p < 10 else "alerta"
                    self._ativar(ch, sev, "LIMITE", el, f"Reservatório {el} em {p:.0f}% ({v:.2f} m)" +
                                 (" — nível baixo" if p < 25 else " — risco de extravasamento"))
                    vivos.add(ch)
        # desvio em relação ao gêmeo: vazões agrupadas por setor (um alarme por setor)
        por_setor = defaultdict(list)
        for (el, gr) in list(self.ultimo):
            if (el, gr) in self.esperado and f"COMUNICACAO|{el}|{gr}" not in vivos:
                j = self._janela((el, gr))
                if j is None:
                    continue
                if gr == "vazao" and self.camada_de.get(el) == "trecho":
                    rel = (j[:, 0] - j[:, 1]) / np.maximum(j[:, 1], 0.5)
                    por_setor[self.setor_de.get(el, "(sem setor)")].append((el, float(rel.mean()), float(rel.min()),
                                                                           float(rel.max()), float(j[-1, 0] - j[-1, 1])))
                elif gr == "pressao":
                    d = j[:, 0] - j[:, 1]
                    if abs(d.mean()) > 3 and np.all(np.sign(d) == np.sign(d.mean())):
                        ch = f"DESVIO|{el}|pressao"
                        self._ativar(ch, "alerta", "DESVIO", el,
                                     f"Pressão em {el} {d.mean():+.1f} mca em relação ao gêmeo há 15 min "
                                     f"(registro, VRP ou cadastro?)")
                        vivos.add(ch)
        for setor, lst in por_setor.items():
            alto = [x for x in lst if x[1] > 0.15 and x[2] > 0.08]
            baixo = [x for x in lst if x[1] < -0.15 and x[3] < -0.08]
            if alto:
                pior = max(alto, key=lambda x: x[1])
                ctx = self._contexto_pressao(setor)
                ch = f"VAZAMENTO|{setor}"
                self._ativar(ch, "critico" if pior[1] > 0.30 else "alerta", "VAZAMENTO", pior[0],
                             f"Setor {setor}: vazão {pior[1]:+.0%} acima do gêmeo há 15 min em "
                             f"{', '.join(x[0] for x in alto)} (+{pior[4]:.1f} L/s){ctx} — possível vazamento "
                             f"ou consumo anormal", setor=setor)
                vivos.add(ch)
            if baixo:
                pior = min(baixo, key=lambda x: x[1])
                ch = f"DESVIO|{setor}|vazao"
                self._ativar(ch, "alerta", "DESVIO", pior[0],
                             f"Setor {setor}: vazão {pior[1]:+.0%} abaixo do gêmeo em {pior[0]} — "
                             f"registro fechado, macromedidor ou consumo menor?", setor=setor)
                vivos.add(ch)
        # previsão dos reservatórios
        for tid, nmax in self.nivel_max.items():
            prev = self.previsao(tid, "nivel")
            if prev:
                t, v = min(prev, key=lambda x: x[1])
                ch = f"PREVISAO|{tid}"
                if v / nmax * 100 < 20:
                    self._ativar(ch, "alerta", "PREVISAO", tid,
                                 f"Previsão do gêmeo: reservatório {tid} chega a {v / nmax * 100:.0f}% às {txt_hora(t)}")
                    vivos.add(ch)
        for ch in [c for c in self.alarmes if c not in vivos]:
            self._limpar(ch)
        self.db.commit()

    def _contexto_pressao(self, setor):
        partes = []
        for (el, gr) in self.ultimo:
            if gr == "pressao" and self.setor_de.get(el) == setor:
                j = self._janela((el, gr))
                if j is not None and (j[:, 0] - j[:, 1]).mean() < -0.3:
                    partes.append(f"pressão em {el} {(j[:, 0] - j[:, 1]).mean():+.1f} mca")
        return f"; {', '.join(partes)}" if partes else ""

    # ------------------------------------------------------------ estado para a tela
    def estado(self, janela_h=4):
        with self.lock:
            if self.agora is None:
                return {"agora": None, "sensores": [], "alarmes": [], "historico": []}
            ini = self.agora - janela_h * 3600
            sens = []
            for (el, gr), (ts, v) in sorted(self.ultimo.items(), key=lambda x: (x[0][1], x[0][0])):
                e = self.esperado_em(el, gr, ts)
                lim = [10, 50] if gr == "pressao" and el in self.consumo else \
                      [0.25 * self.nivel_max[el], 0.95 * self.nivel_max[el]] if gr == "nivel" and el in self.nivel_max else None
                ativos = [a for a in self.alarmes.values() if a["elemento"] == el or
                          (a["tipo"] == "VAZAMENTO" and a["setor"] == self.setor_de.get(el) and gr == "vazao")]
                sens.append({
                    "elemento": el, "grandeza": gr, "un": UN[gr], "setor": self.setor_de.get(el),
                    "camada": self.camada_de.get(el), "valor": v, "ts": ts, "esperado": e,
                    "desvio": None if e is None else v - e, "limites": lim, "nivel_max": self.nivel_max.get(el),
                    "status": min((a["severidade"] for a in ativos), key=SEV.get, default="ok"),
                    "medido": [(t, round(x, 3)) for t, x in self.medido[(el, gr)] if t >= ini],
                    "esperado_serie": [(t, round(x, 3)) for t, x in self.esperado[(el, gr)] if t >= ini],
                    "previsao": [(t, round(x, 3)) for t, x in self.previsao(el, gr)],
                })
            ordem = lambda a: (SEV[a["severidade"]], a["reconhecido"] is not None, -a["inicio"])
            return {
                "agora": self.agora, "agora_txt": datetime.fromtimestamp(self.agora).strftime("%d/%m %H:%M"),
                "sem_dados_ha": time.time() - self.recebido_em if self.recebido_em else None,
                "sincronizado": self.prev and self.prev["t0"], "sensores": sens,
                "alarmes": sorted(self.alarmes.values(), key=ordem), "historico": list(self.historico)[:40],
            }


class Simulador(threading.Thread):
    """Emula o SCADA: gera a "rede real" (cadastro + vazamento) e envia leituras com ruído.

    velocidade: minutos simulados por segundo real. vazamento: {"no", "hora", "lps"}.
    """

    def __init__(self, gemeo, velocidade=2.0, inicio_h=5.0, vazamento=None, sensores=None, semente=1):
        super().__init__(daemon=True)
        self.g, self.vel, self.vazamento = gemeo, float(velocidade), vazamento
        self.parar = threading.Event()
        self.rng = np.random.default_rng(semente)
        self.base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        self.t = float(inicio_h) * 3600
        self.sensores = sensores or self._sensores_padrao()
        self.falha = set()           # sensores "mudos" (teste de comunicação)
        wn = wntr.network.WaterNetworkModel(gemeo.inp_path)
        tm = wn.options.time
        tm.duration, tm.hydraulic_timestep, tm.report_timestep = 48 * 3600, 60, 60
        if vazamento:
            passo = tm.pattern_timestep
            n = int(48 * 3600 // passo)
            k0 = int(float(vazamento["hora"]) * 3600 // passo)
            wn.add_pattern("VAZAMENTO", [0.0] * k0 + [1.0] * (n - k0))
            wn.get_node(vazamento["no"]).add_demand(float(vazamento["lps"]) / 1000, "VAZAMENTO")
        with tempfile.TemporaryDirectory(prefix="gwater_sim_", ignore_cleanup_errors=True) as tmp:
            self.res = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=os.path.join(tmp, "real"))
        self.rel = self.res.node["pressure"].index.to_numpy(float)

    def _sensores_padrao(self):
        """Reservatórios (nível), bombas (vazão), válvulas (pressão de jusante e vazão do trecho que sai)
        e até 8 nós de consumo (pressão): o que costuma ter medição numa rede real."""
        c, s = self.g.cadastro, []
        s += [(i, "nivel") for i in self.g.nivel_max]
        s += [(i, "vazao") for i in c["bomba"]["id"]]
        for v in c["valvula"]["id"]:
            s.append((v, "pressao"))
            s += [(t, "vazao") for t, a in zip(c["trecho"]["id"], c["trecho"]["no_inicial"]) if a == v]
        s += [(i, "pressao") for i in sorted(self.g.consumo)[:8]]
        return s

    def leitura(self, el, gr, t):
        n, l = self.res.node, self.res.link
        if gr == "vazao":
            s = l["flowrate"][el].abs().to_numpy() * 1000
        else:
            alvo = el + "__J" if self.g.camada_de.get(el) in ("valvula", "bomba") else el
            s = n["pressure"][alvo].to_numpy()
        v = float(np.interp(t, self.rel, s))
        ruido = {"pressao": 0.12, "nivel": 0.01}.get(gr)
        return max(0.0, v * (1 + self.rng.normal(0, 0.015)) if gr == "vazao" else v + self.rng.normal(0, ruido))

    def avancar(self, minutos):
        """Gera e entrega as leituras de 'minutos' minutos simulados (uma por minuto por sensor)."""
        lote = []
        for _ in range(int(minutos)):
            self.t += 60
            if self.t >= 47 * 3600:
                return False
            lote += [{"elemento": el, "grandeza": gr, "valor": self.leitura(el, gr, self.t), "ts": self.base + self.t}
                     for el, gr in self.sensores if (el, gr) not in self.falha]
        if lote:
            self.g.receber(lote)
        return True

    def run(self):
        acumulado = 0.0
        while not self.parar.is_set():
            time.sleep(0.25)
            acumulado += self.vel * 0.25
            if acumulado >= 1:
                if not self.avancar(acumulado):
                    break
                acumulado -= int(acumulado)

    def status(self):
        return {"rodando": self.is_alive() and not self.parar.is_set(), "velocidade": self.vel,
                "vazamento": self.vazamento, "hora": txt_hora(self.base + self.t), "sensores": len(self.sensores)}
