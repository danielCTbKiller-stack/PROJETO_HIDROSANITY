"""Ferramentas de análise do GWATER, como as do WaterGEMS, calculadas no EPANET 2.2 (WNTR).

Cada função recebe o cadastro (.gpkg) e devolve um dicionário pronto para virar JSON:

  incendio        Fire Flow: vazão disponível em cada hidrante/nó mantendo a pressão residual
  descarga        Flushing: velocidade que cada descarga (abertura de hidrante) provoca nos tubos
  criticidade     Criticality: o que deixa de ser entregue quando cada tubulação sai de operação
  zonas_pressao   Pressure Zone: zonas separadas por bombas, válvulas reguladoras e tubos fechados
  energia         Energy Cost: energia e custo das bombas com tarifa por hora
  renovacao       Pipe Renewal Planner: nota de prioridade de troca de cada tubulação
  dimensionar     Darwin Designer: menores diâmetros que atendem pressão mínima e velocidade máxima
  qualidade       Water Quality: idade da água ou decaimento de cloro
  comparar        Scenario Comparison: duas propostas (ou a rede atual) lado a lado
  esqueletizar    Skelebrator: cadastro simplificado (ramais curtos cortados, tubos em série unidos)

As análises "instantâneas" (incêndio, descarga, criticidade, dimensionamento) usam a rede num instante
(por padrão o de maior consumo): demandas, níveis e estado das bombas daquele instante da simulação de
24 h, e o EPANET resolvido direto pela biblioteca (milissegundos por cálculo).
"""
import math
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date

import networkx as nx
import numpy as np
import pandas as pd
import wntr
from wntr.epanet import toolkit
from wntr.epanet.util import EN
from wntr.network import LinkStatus

from cadastro_para_inp import converter, ler_cadastro

VALVULAS_ZONA = ("PRV", "PSV", "PBV", "FCV")  # separam zonas de pressão (a TCV e a GPV só perdem carga)
VIDA_UTIL = {"PVC PBA": 50, "PVC DEFoFo": 50, "PEAD": 60, "Ferro fundido dúctil": 80, "Ferro fundido cinzento": 70,
             "Aço": 50, "Cimento-amianto": 40}
RISCO_MATERIAL = {"Cimento-amianto": 1.0, "Ferro fundido cinzento": 0.9, "Aço": 0.7, "PVC PBA": 0.4,
                  "PVC DEFoFo": 0.35, "Ferro fundido dúctil": 0.3, "PEAD": 0.2}
# custo de implantação (R$/m, tubo + assentamento, referência) por DN
CUSTO_DN = {50: 180, 75: 220, 100: 280, 150: 390, 200: 520, 250: 680, 300: 850, 350: 1050, 400: 1250,
            500: 1700, 600: 2200}
TARIFA_PADRAO = [0.55] * 18 + [2.10] * 3 + [0.55] * 3  # R$/kWh: ponta das 18 h às 21 h


class ErroModelo(Exception):
    """O cadastro não converte (erros de validação). `itens` vai para a aba Problemas."""

    def __init__(self, itens):
        super().__init__(f"{sum(1 for i in itens if i['nivel'] == 'ERRO')} erro(s) no cadastro: valide a rede antes")
        self.itens = itens


# ================================================================ modelo e simulação
class Modelo:
    """Cadastro convertido para o EPANET, com a simulação de 24 h sob demanda."""

    def __init__(self, gpkg, com_projetados=False, alteracoes=None):
        self.gpkg = gpkg
        self.c = ler_cadastro(gpkg)
        self.inp, rel = converter(gpkg, com_projetados, alteracoes, camadas=self.c)
        if not rel.ok:
            raise ErroModelo(rel.itens())
        self.pasta = tempfile.mkdtemp(prefix="gwater_analise_")
        self.arq = os.path.join(self.pasta, "rede.inp")
        with open(self.arq, "w", encoding="utf-8") as f:
            f.write(self.inp)
        self.wn = wntr.network.WaterNetworkModel(self.arq)
        self._res = None
        # nós de consumo do cadastro (não os nós internos de bombas e válvulas)
        self.consumo = [n for n in self.wn.junction_name_list if "__" not in n]

    def pontos_consumo(self):
        """Nós onde a pressão é avaliada (NBR 12218): tipo CONSUMO, HIDRANTE ou PONTA, ou com demanda.
        Fica de fora a entrada de reservatório, o recalque etc. Sem nenhum marcado: todos os nós."""
        nj = self.c["no_juncao"]
        marca = {r["id"] for _, r in nj.iterrows()
                 if r["tipo"] in ("CONSUMO", "HIDRANTE", "PONTA") or (r["demanda_base"] or 0) > 0}
        return [n for n in self.consumo if n in marca] or list(self.consumo)

    def novo_wn(self):
        return wntr.network.WaterNetworkModel(self.arq)

    def simular(self, wn=None, prefixo="eps"):
        wn = wn or self.wn
        sim = wntr.sim.EpanetSimulator(wn)
        return sim.run_sim(file_prefix=os.path.join(self.pasta, prefixo))

    @property
    def res(self):
        if self._res is None:
            self._res = self.simular()
        return self._res

    def esperada(self):
        """Demanda pedida (base × padrão) por nó e instante, em m³/s."""
        return wntr.metrics.expected_demand(self.wn)

    def hora_pico(self):
        """Instante (s) de maior consumo total da rede."""
        d = self.esperada()
        tempos = self.res.node["pressure"].index
        tot = d.reindex(tempos, method="ffill").sum(axis=1)
        return int(tot.idxmax())

    def instante(self, t=None, dda=True):
        """.inp da rede congelada no instante t (s): demandas, níveis, bombas e válvulas daquele momento."""
        res = self.res
        tempos = res.node["pressure"].index
        t = int(t if t is not None else self.hora_pico())
        t = int(tempos[np.abs(np.asarray(tempos) - t).argmin()])
        wn = self.novo_wn()
        esp = self.esperada().reindex(tempos, method="ffill")
        for nome, j in wn.junctions():
            d = float(esp.at[t, nome]) if nome in esp.columns else 0.0
            j.demand_timeseries_list.clear()
            j.add_demand(d, None)
        for nome, tq in wn.tanks():
            nivel = float(res.node["head"].at[t, nome]) - tq.elevation
            tq.init_level = min(max(nivel, tq.min_level), tq.max_level)
        for nome, r in wn.reservoirs():
            if r.head_pattern_name:
                r.base_head = float(res.node["head"].at[t, nome])
                r.head_pattern_name = None
        for nome in list(wn.control_name_list):
            wn.remove_control(nome)
        for nome, b in wn.pumps():
            b.initial_status = LinkStatus.Open if res.link["status"].at[t, nome] > 0 else LinkStatus.Closed
        for nome, v in wn.valves():
            st = res.link["status"].at[t, nome]
            if st == 0:
                v.initial_status = LinkStatus.Closed
        wn.options.time.duration = 0
        wn.options.hydraulic.demand_model = "DD" if dda else "PDD"
        arq = os.path.join(self.pasta, f"instante_{t}_{'dda' if dda else 'pda'}.inp")
        wntr.network.write_inpfile(wn, arq, units="LPS")
        return arq, t

    def fechar(self):
        shutil.rmtree(self.pasta, ignore_errors=True)


class Rapido:
    """EPANET pela biblioteca, para milhares de cálculos de um instante (unidades do .inp: L/s, m)."""

    def __init__(self, arq_inp):
        self.en = toolkit.ENepanet()
        base = os.path.splitext(arq_inp)[0]
        self.en.ENopen(arq_inp, base + ".rpt", "")
        self.en.ENopenH()
        self.n_nos = self.en.ENgetcount(EN.NODECOUNT)
        self.n_links = self.en.ENgetcount(EN.LINKCOUNT)
        wn = wntr.network.WaterNetworkModel(arq_inp)
        self.no = {n: self.en.ENgetnodeindex(n) for n in wn.node_name_list}
        self.link = {n: self.en.ENgetlinkindex(n) for n in wn.link_name_list}

    def resolver(self):
        try:
            self.en.ENinitH(0)
            self.en.ENrunH()
            return True
        except Exception:
            return False

    def no_valor(self, nid, par):
        return self.en.ENgetnodevalue(self.no[nid], par)

    def link_valor(self, lid, par):
        return self.en.ENgetlinkvalue(self.link[lid], par)

    def mudar_no(self, nid, par, valor):
        self.en.ENsetnodevalue(self.no[nid], par, valor)

    def mudar_link(self, lid, par, valor):
        self.en.ENsetlinkvalue(self.link[lid], par, valor)

    def fechar(self):
        try:
            self.en.ENcloseH()
            self.en.ENclose()
        except Exception:
            pass


def _r(x, d=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), d)


def _hora_txt(t):
    return f"{int(t // 3600) % 24:02d}:{int(t % 3600 // 60):02d}"


def _candidatos_hidrante(m, nos):
    if nos:
        return [n for n in nos if n in m.wn.junction_name_list]
    tipos = dict(zip(m.c["no_juncao"]["id"], m.c["no_juncao"]["tipo"]))
    hid = [n for n in m.consumo if tipos.get(n) == "HIDRANTE"]
    return hid or m.pontos_consumo()


# ================================================================ incêndio (Fire Flow)
def incendio(gpkg, com_projetados=False, alteracoes=None, nos=None, vazao=10.0, p_residual=10.0,
             p_min_zona=None, hora=None, vazao_max=500.0):
    """Para cada nó: a vazão de incêndio disponível mantendo `p_residual` (mca) no próprio nó e, se
    `p_min_zona` for dado, essa pressão em todos os outros nós de consumo. Atende = disponível ≥ `vazao`."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=True)
        R = Rapido(arq)
        outros = m.consumo
        try:
            base = {n: R.no_valor(n, EN.BASEDEMAND) for n in outros}

            def testar(n, q):
                R.mudar_no(n, EN.BASEDEMAND, base[n] + q)
                ok = R.resolver()
                p = R.no_valor(n, EN.PRESSURE) if ok else -1e9
                pz, onde = math.inf, None
                if ok and p_min_zona is not None:
                    for o in outros:
                        if o != n:
                            v = R.no_valor(o, EN.PRESSURE)
                            if v < pz:
                                pz, onde = v, o
                R.mudar_no(n, EN.BASEDEMAND, base[n])
                atende = ok and p >= p_residual and (p_min_zona is None or pz >= p_min_zona)
                return atende, p, (pz if pz < math.inf else None), onde

            linhas = []
            for n in _candidatos_hidrante(m, nos):
                atende_q, p_q, pz_q, onde_q = testar(n, vazao)
                lo, hi = 0.0, float(vazao_max)
                if testar(n, 0.0)[0]:
                    if testar(n, hi)[0]:
                        lo = hi
                    else:
                        for _ in range(16):
                            meio = (lo + hi) / 2
                            if testar(n, meio)[0]:
                                lo = meio
                            else:
                                hi = meio
                            if hi - lo < 0.05:
                                break
                linhas.append({"id": n, "q_necessaria": vazao, "q_disponivel": _r(lo, 1), "atende": bool(atende_q),
                               "p_residual": _r(p_q, 1), "p_min_zona": _r(pz_q, 1), "no_p_min_zona": onde_q,
                               "limitado_por": "pressão no próprio nó" if p_q < p_residual else
                               ("pressão na zona" if not atende_q else "")})
        finally:
            R.fechar()
        linhas.sort(key=lambda r: (r["atende"], r["q_disponivel"] or 0))
        return {"ok": True, "hora": _hora_txt(t), "linhas": linhas,
                "atendem": sum(r["atende"] for r in linhas), "total": len(linhas),
                "parametros": {"vazao": vazao, "p_residual": p_residual, "p_min_zona": p_min_zona}}
    finally:
        m.fechar()


# ================================================================ descarga (Flushing)
def descarga(gpkg, com_projetados=False, alteracoes=None, nos=None, vazao=20.0, v_alvo=0.76, hora=None):
    """Cada nó aberto sozinho com `vazao` (L/s): tubos que passam de `v_alvo` (m/s, limpeza) e pressão no nó."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=True)
        R = Rapido(arq)
        tubos = list(m.wn.pipe_name_list)
        try:
            R.resolver()
            v0 = {p: abs(R.link_valor(p, EN.VELOCITY)) for p in tubos}
            eventos = []
            for n in _candidatos_hidrante(m, nos):
                base = R.no_valor(n, EN.BASEDEMAND)
                R.mudar_no(n, EN.BASEDEMAND, base + vazao)
                ok = R.resolver()
                limpos = []
                if ok:
                    for p in tubos:
                        v = abs(R.link_valor(p, EN.VELOCITY))
                        if v >= v_alvo:
                            limpos.append({"id": p, "v": _r(v, 2), "v_antes": _r(v0[p], 2)})
                p_no = R.no_valor(n, EN.PRESSURE) if ok else None
                R.mudar_no(n, EN.BASEDEMAND, base)
                limpos.sort(key=lambda x: -x["v"])
                eventos.append({"id": n, "vazao": vazao, "p_no": _r(p_no, 1), "n_tubos": len(limpos),
                                "comprimento_m": _r(sum(m.wn.get_link(x["id"]).length for x in limpos), 0),
                                "tubos": limpos[:200], "convergiu": ok})
        finally:
            R.fechar()
        eventos.sort(key=lambda e: -e["comprimento_m"])
        return {"ok": True, "hora": _hora_txt(t), "eventos": eventos, "v_alvo": v_alvo}
    finally:
        m.fechar()


# ================================================================ criticidade (Criticality)
def criticidade(gpkg, com_projetados=False, alteracoes=None, trechos=None, hora=None, p_min=10.0):
    """Cada tubulação fechada sozinha (com demanda dependente da pressão): água que deixa de ser entregue
    e nós que ficam abaixo de `p_min`."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=False)
        R = Rapido(arq)
        nos = m.consumo
        try:
            R.resolver()
            pedido = sum(R.no_valor(n, EN.BASEDEMAND) for n in nos)
            entregue0 = sum(R.no_valor(n, EN.DEMAND) for n in nos)
            baixos0 = {n for n in nos if R.no_valor(n, EN.PRESSURE) < p_min}
            linhas = []
            for p in (trechos or m.wn.pipe_name_list):
                if p not in R.link:
                    continue
                st = R.link_valor(p, EN.INITSTATUS)
                try:
                    R.mudar_link(p, EN.INITSTATUS, 0)
                    fechar = lambda: R.mudar_link(p, EN.INITSTATUS, st)
                except Exception:  # tubo com retenção (CV): a biblioteca não muda o estado; diâmetro mínimo corta o fluxo
                    d = R.link_valor(p, EN.DIAMETER)
                    R.mudar_link(p, EN.DIAMETER, 0.01)
                    fechar = lambda: R.mudar_link(p, EN.DIAMETER, d)
                ok = R.resolver()
                if ok:
                    entregue = sum(R.no_valor(n, EN.DEMAND) for n in nos)
                    baixos = [n for n in nos if R.no_valor(n, EN.PRESSURE) < p_min and n not in baixos0]
                    sem_agua = [n for n in nos if R.no_valor(n, EN.BASEDEMAND) > 1e-9
                                and R.no_valor(n, EN.DEMAND) < 0.01 * R.no_valor(n, EN.BASEDEMAND)]
                else:
                    entregue, baixos, sem_agua = 0.0, [], []
                fechar()
                falta = max(0.0, entregue0 - entregue)
                linhas.append({"id": p, "falta_lps": _r(falta, 2),
                               "falta_pct": _r(100 * falta / pedido, 1) if pedido > 0 else 0.0,
                               "nos_baixa_pressao": len(baixos), "nos_sem_agua": len(sem_agua),
                               "exemplos": (sem_agua or baixos)[:8], "convergiu": ok})
        finally:
            R.fechar()
        linhas.sort(key=lambda r: (-(r["falta_pct"] or 0), -r["nos_baixa_pressao"]))
        return {"ok": True, "hora": _hora_txt(t), "pedido_lps": _r(pedido, 2), "linhas": linhas, "p_min": p_min}
    finally:
        m.fechar()


# ================================================================ zonas de pressão (Pressure Zone)
def zonas_pressao(gpkg, com_projetados=False, alteracoes=None):
    """Zonas de pressão: partes da rede ligadas só por tubos abertos (bombas, PRV/PSV/PBV/FCV e tubos ou
    válvulas fechados fazem a divisa). Cada nó do cadastro ganha o número da zona."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        wn = m.wn
        g = nx.Graph()
        g.add_nodes_from(wn.node_name_list)
        divisas = []
        for nome, l in wn.links():
            fechado = l.initial_status == LinkStatus.Closed
            if l.link_type == "Pump" or (l.link_type == "Valve" and l.valve_type in VALVULAS_ZONA) or fechado:
                divisas.append(nome)
                continue
            g.add_edge(l.start_node_name, l.end_node_name, link=nome)
        comp = sorted(nx.connected_components(g), key=len, reverse=True)
        zona_de = {}
        for i, nos in enumerate(comp, start=1):
            for n in nos:
                zona_de[n] = i
        res = m.res
        p = res.node["pressure"]
        zonas = []
        for i, nos in enumerate(comp, start=1):
            juncs = [n for n in nos if n in wn.junction_name_list]
            cadastro = sorted({n.split("__")[0] for n in nos})
            dem = sum(wn.get_node(n).demand_timeseries_list[0].base_value * 1000 for n in juncs
                      if wn.get_node(n).demand_timeseries_list)
            cotas = [wn.get_node(n).elevation for n in juncs] or [0]
            pz = p[[n for n in juncs if "__" not in n]] if any("__" not in n for n in juncs) else None
            fontes = [n for n in nos if n in wn.tank_name_list or n in wn.reservoir_name_list]
            entra = [d for d in divisas if zona_de.get(wn.get_link(d).end_node_name) == i]
            sai = [d for d in divisas if zona_de.get(wn.get_link(d).start_node_name) == i]
            zonas.append({"zona": i, "n_nos": len([n for n in juncs if "__" not in n]), "demanda_lps": _r(dem, 2),
                          "cota_min": _r(min(cotas), 1), "cota_max": _r(max(cotas), 1),
                          "p_min": _r(pz.min().min(), 1) if pz is not None and pz.size else None,
                          "p_max": _r(pz.max().max(), 1) if pz is not None and pz.size else None,
                          "fontes": fontes, "entradas": entra, "saidas": sai, "elementos": cadastro[:5000]})
        elementos = {}
        for n, z in zona_de.items():
            if "__" in n:
                base, lado = n.split("__")
                if lado == "J":  # bomba/válvula: o elemento fica na zona de jusante (a que ele abastece)
                    elementos[base] = z
                else:
                    elementos.setdefault(base, z)
            else:
                elementos[n] = z
        links = {}
        for nome, l in wn.links():
            if nome not in divisas:
                links[nome] = zona_de.get(l.start_node_name)
        return {"ok": True, "zonas": zonas, "nos": elementos, "trechos": links, "divisas": divisas}
    finally:
        m.fechar()


# ================================================================ energia (Energy Cost)
def energia(gpkg, com_projetados=False, alteracoes=None, eficiencia=0.70, tarifa=None, dias_mes=30):
    """Energia e custo de cada bomba na simulação de 24 h. `eficiencia`: número (todas) ou {bomba: η};
    `tarifa`: 24 valores em R$/kWh (um por hora do dia)."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        tarifa = list(tarifa or TARIFA_PADRAO)
        res = m.res
        tempos = np.asarray(res.link["flowrate"].index, dtype=float)
        dt = np.diff(np.append(tempos, tempos[-1] + (tempos[-1] - tempos[-2] if len(tempos) > 1 else 3600))) / 3600
        bombas = []
        for nome, b in m.wn.pumps():
            eta = float(eficiencia.get(nome, 0.7) if isinstance(eficiencia, dict) else eficiencia)
            q = res.link["flowrate"][nome].to_numpy()  # m³/s
            h = (res.node["head"][b.end_node_name] - res.node["head"][b.start_node_name]).to_numpy()
            ligada = (res.link["status"][nome].to_numpy() > 0) & (q > 1e-6)
            pot = np.where(ligada, 9.81 * q * np.maximum(h, 0) / max(eta, 0.05), 0.0)  # kW
            kwh = pot * dt
            preco = np.array([tarifa[int(t // 3600) % 24] for t in tempos])
            custo = kwh * preco
            vol = float((q * dt * 3600)[ligada].sum())
            bombas.append({"id": nome, "eficiencia": eta, "kwh_dia": _r(kwh.sum(), 1), "custo_dia": _r(custo.sum(), 2),
                           "custo_mes": _r(custo.sum() * dias_mes, 2), "horas_ligada": _r(float(dt[ligada].sum()), 2),
                           "potencia_max_kw": _r(pot.max(), 1), "q_media_lps": _r(q[ligada].mean() * 1000, 1) if ligada.any() else 0,
                           "h_media_m": _r(h[ligada].mean(), 1) if ligada.any() else 0, "volume_m3": _r(vol, 0),
                           "kwh_por_m3": _r(kwh.sum() / vol, 3) if vol > 0 else None,
                           "custo_ponta_pct": _r(100 * custo[(tempos // 3600 % 24 >= 18) & (tempos // 3600 % 24 < 21)].sum()
                                                 / custo.sum(), 1) if custo.sum() > 0 else 0,
                           "serie_kw": [_r(x, 2) for x in pot]})
        return {"ok": True, "horas": [_r(t / 3600, 3) for t in tempos], "bombas": bombas, "tarifa": tarifa,
                "total_kwh_dia": _r(sum(b["kwh_dia"] for b in bombas), 1),
                "total_custo_mes": _r(sum(b["custo_mes"] for b in bombas), 2)}
    finally:
        m.fechar()


# ================================================================ renovação (Pipe Renewal Planner)
def renovacao(gpkg, com_projetados=False, alteracoes=None, pesos=None, ano=None, com_criticidade=False,
              custo_m=None, vida=None):
    """Nota de 0 a 100 por tubulação: idade (vida útil do material), material, desempenho hidráulico
    (perda de carga e velocidade no pior momento) e, opcional, criticidade. Mais alto = trocar antes."""
    pesos = {"idade": 0.35, "material": 0.25, "hidraulica": 0.25, "criticidade": 0.15, **(pesos or {})}
    if not com_criticidade:
        pesos["criticidade"] = 0.0
    soma = sum(pesos.values()) or 1
    pesos = {k: v / soma for k, v in pesos.items()}
    ano = ano or date.today().year
    custo_m = {int(k): float(v) for k, v in (custo_m or CUSTO_DN).items()}
    vida = {**VIDA_UTIL, **(vida or {})}
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        res = m.res
        hl = res.link["headloss"].abs() * 1000  # m/km
        v = res.link["velocity"].abs()
        crit = {}
        if com_criticidade:
            for lin in criticidade(gpkg, com_projetados, alteracoes)["linhas"]:
                crit[lin["id"]] = min(1.0, (lin["falta_pct"] or 0) / 20 + lin["nos_baixa_pressao"] / 50)
        tr = m.c["trecho"].set_index("id")
        linhas = []
        for p in m.wn.pipe_name_list:
            if p not in tr.index:
                continue
            r = tr.loc[p]
            mat = r["material"] or ""
            idade = (ano - int(r["ano_instalacao"])) if r.get("ano_instalacao") not in (None, "") and \
                not pd.isna(r.get("ano_instalacao")) else None
            s_idade = min(1.0, idade / vida.get(mat, 50)) if idade is not None else 0.5
            s_mat = RISCO_MATERIAL.get(mat, 0.5)
            hmax, vmax = float(hl[p].max()), float(v[p].max())
            s_hid = min(1.0, max(hmax / 20, (vmax - 1.5) / 1.5 if vmax > 1.5 else 0))
            s_crit = crit.get(p, 0.0)
            nota = 100 * (pesos["idade"] * s_idade + pesos["material"] * s_mat + pesos["hidraulica"] * s_hid
                          + pesos["criticidade"] * s_crit)
            dn = r["diametro_nominal"] or 100
            dn_ref = min(custo_m, key=lambda d: abs(d - dn))
            L = float(r["comprimento"] or m.wn.get_link(p).length)
            linhas.append({"id": p, "nota": _r(nota, 1), "idade": idade, "material": mat, "dn": dn,
                           "perda_max_m_km": _r(hmax, 1), "v_max": _r(vmax, 2), "criticidade": _r(s_crit, 2),
                           "comprimento": _r(L, 1), "custo": _r(L * custo_m[dn_ref], 0),
                           "prioridade": "ALTA" if nota >= 60 else "MÉDIA" if nota >= 40 else "BAIXA"})
        linhas.sort(key=lambda x: -x["nota"])
        acum = 0
        for x in linhas:
            acum += x["custo"]
            x["custo_acumulado"] = _r(acum, 0)
        return {"ok": True, "linhas": linhas, "pesos": pesos, "ano": ano}
    finally:
        m.fechar()


# ================================================================ dimensionamento (Darwin Designer)
def dimensionar(gpkg, com_projetados=False, alteracoes=None, trechos=None, dns=None, custo_m=None, p_min=10.0,
                v_max=3.0, hora=None):
    """Menor custo para as tubulações candidatas atenderem `p_min` (mca) nos nós de consumo e `v_max` (m/s)
    no instante de maior consumo. Começa todas no menor DN e aumenta, a cada passo, a que dá mais ganho de
    pressão por real gasto (método guloso, como uma primeira rodada do Darwin Designer)."""
    custo_m = {int(k): float(v) for k, v in (custo_m or CUSTO_DN).items()}
    dns = sorted(int(d) for d in (dns or custo_m))
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        cand = [p for p in (trechos or []) if p in m.wn.pipe_name_list]
        if not cand:
            raise ValueError("escolha as tubulações candidatas (selecione no mapa)")
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=True)
        R = Rapido(arq)
        try:
            avaliar_em = m.pontos_consumo()
            L = {p: m.wn.get_link(p).length for p in cand}
            dn0 = {p: m.wn.get_link(p).diameter * 1000 for p in cand}
            custo = lambda dn, p: L[p] * custo_m.get(dn, custo_m[min(custo_m, key=lambda d: abs(d - dn))])

            def avaliar(atual):
                for p, d in atual.items():
                    R.mudar_link(p, EN.DIAMETER, d)
                if not R.resolver():
                    return -1e9, 1e9
                pm = min(R.no_valor(n, EN.PRESSURE) for n in avaliar_em) if avaliar_em else 0
                vm = max(abs(R.link_valor(p, EN.VELOCITY)) for p in cand)
                return pm, vm

            p_antes, v_antes = avaliar(dn0)
            atual = {p: dns[0] for p in cand}
            pm, vm = avaliar(atual)
            passos = 0
            while (pm < p_min or vm > v_max) and passos < len(cand) * len(dns):
                passos += 1
                melhor, ganho_melhor = None, -math.inf
                for p in cand:
                    i = dns.index(atual[p])
                    if i + 1 >= len(dns):
                        continue
                    teste = {**atual, p: dns[i + 1]}
                    pm2, vm2 = avaliar(teste)
                    dc = custo(dns[i + 1], p) - custo(atual[p], p) or 1
                    ganho = ((min(pm2, p_min) - min(pm, p_min)) + max(0, min(vm, 10) - max(vm2, v_max))) / dc
                    if ganho > ganho_melhor:
                        melhor, ganho_melhor = (p, dns[i + 1], pm2, vm2), ganho
                if melhor is None or ganho_melhor <= 0:
                    break  # nenhum aumento de diâmetro ajuda: o limite está em outra parte da rede
                atual[melhor[0]] = melhor[1]
                pm, vm = melhor[2], melhor[3]
            avaliar(atual)
            linhas = [{"id": p, "dn_atual": _r(dn0[p], 0), "dn_proposto": atual[p], "comprimento": _r(L[p], 1),
                       "custo": _r(custo(atual[p], p), 0)} for p in cand]
            return {"ok": True, "hora": _hora_txt(t), "atende": bool(pm >= p_min and vm <= v_max),
                    "p_min_antes": _r(p_antes, 1), "v_max_antes": _r(v_antes, 2), "p_min_depois": _r(pm, 1),
                    "v_max_depois": _r(vm, 2), "custo_total": _r(sum(x["custo"] for x in linhas), 0), "linhas": linhas,
                    "alteracoes": [{"camada": "trecho", "id": p, "campo": "diametro_nominal", "valor": atual[p]}
                                   for p in cand]}
        finally:
            R.fechar()
    finally:
        m.fechar()


# ================================================================ qualidade da água (Water Quality)
def qualidade(gpkg, com_projetados=False, alteracoes=None, parametro="AGE", duracao_h=72, conc_fonte=1.0,
              kb_dia=-0.5, kw=0.0):
    """Idade da água (h) ou cloro residual (mg/L, decaimento de 1ª ordem `kb_dia` em 1/dia, cloro
    `conc_fonte` nas captações e reservatórios-fonte). Devolve as últimas 24 h de cada nó."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        wn = m.wn
        wn.options.time.duration = int(duracao_h * 3600)
        wn.options.time.quality_timestep = 300
        parametro = parametro.upper()
        if parametro == "AGE":
            wn.options.quality.parameter = "AGE"
        else:
            wn.options.quality.parameter = "CHEMICAL"
            wn.options.quality.chemical_name = "Cloro"
            wn.options.reaction.bulk_coeff = kb_dia / 86400
            wn.options.reaction.wall_coeff = kw / 86400
            wn.add_pattern("_q1", [1.0])
            for r in wn.reservoir_name_list:
                wn.add_source(f"C_{r}", r, "CONCEN", conc_fonte, "_q1")
        res = m.simular(wn, "qualidade")
        q = res.node["quality"]
        ult = q[q.index >= q.index[-1] - 24 * 3600]
        if parametro == "AGE":
            ult = ult / 3600  # s -> h
        nos = {}
        for n in ult.columns:
            if "__" in n and not n.endswith("__J"):
                continue
            nome = n.split("__")[0]
            s = ult[n]
            nos[nome] = {"max": _r(s.max(), 2), "media": _r(s.mean(), 2), "min": _r(s.min(), 2),
                         "serie": [_r(x, 3) for x in s]}
        return {"ok": True, "parametro": "idade (h)" if parametro == "AGE" else "cloro (mg/L)",
                "horas": [_r((t - ult.index[0]) / 3600, 3) for t in ult.index], "nos": nos}
    finally:
        m.fechar()


# ================================================================ comparação de cenários
def _indicadores(m):
    res = m.res
    p = res.node["pressure"][m.consumo] if m.consumo else pd.DataFrame()
    v = res.link["velocity"].abs()
    tubos = [x for x in m.wn.pipe_name_list]
    hl = res.link["headloss"].abs()[tubos] * 1000
    dem = res.node["demand"][m.consumo].clip(lower=0) if m.consumo else pd.DataFrame()
    dt = 3600 * 24 / max(len(res.node["pressure"].index), 1)
    esperado = m.esperada().reindex(res.node["pressure"].index, method="ffill")
    esp = esperado[[n for n in m.consumo if n in esperado.columns]].sum().sum() * dt
    entregue = dem.sum().sum() * dt
    out = {"p_min": _r(p.min().min(), 1) if p.size else None, "p_media": _r(p.mean().mean(), 1) if p.size else None,
           "p_max": _r(p.max().max(), 1) if p.size else None,
           "nos_abaixo_10": int((p.min() < 10).sum()) if p.size else 0,
           "nos_acima_50": int((p.max() > 50).sum()) if p.size else 0,
           "v_max": _r(v[tubos].max().max(), 2) if tubos else None, "perda_max_m_km": _r(hl.max().max(), 1) if tubos else None,
           "tubos_v_alta": int((v[tubos].max() > 2.5).sum()) if tubos else 0,
           "atendimento_pct": _r(100 * entregue / esp, 1) if esp > 0 else 100.0,
           "volume_entregue_m3": _r(entregue, 0)}
    return out


def comparar(gpkg, com_projetados=False, cenario_a=None, cenario_b=None):
    """cenario_a / cenario_b: listas de alterações (None = rede atual). Indicadores e diferenças por elemento."""
    ma = Modelo(gpkg, com_projetados, cenario_a)
    mb = Modelo(gpkg, com_projetados, cenario_b)
    try:
        ia, ib = _indicadores(ma), _indicadores(mb)
        pa, pb = ma.res.node["pressure"], mb.res.node["pressure"]
        nos = []
        for n in sorted(set(ma.consumo) & set(mb.consumo)):
            a, b = float(pa[n].min()), float(pb[n].min())
            nos.append({"id": n, "p_min_a": _r(a, 1), "p_min_b": _r(b, 1), "dif": _r(b - a, 1)})
        va, vb = ma.res.link["velocity"].abs(), mb.res.link["velocity"].abs()
        tubos = []
        for t in sorted(set(ma.wn.pipe_name_list) & set(mb.wn.pipe_name_list)):
            a, b = float(va[t].max()), float(vb[t].max())
            tubos.append({"id": t, "v_max_a": _r(a, 2), "v_max_b": _r(b, 2), "dif": _r(b - a, 2)})
        nos.sort(key=lambda x: -abs(x["dif"] or 0))
        tubos.sort(key=lambda x: -abs(x["dif"] or 0))
        return {"ok": True, "a": ia, "b": ib, "nos": nos, "tubos": tubos}
    finally:
        ma.fechar()
        mb.fechar()


# ================================================================ esqueletização (Skelebrator)
def esqueletizar(gpkg, destino, dn_max=100.0, cortar_ramais=True, unir_serie=True, comprimento_max=None):
    """Grava em `destino` uma cópia do cadastro simplificada:
    - ramais: tubulação de ponta (nó com 1 só ligação) com DN ≤ `dn_max` sai, e a demanda do nó da ponta
      passa para o nó de onde o ramal sai (repete até não sobrar ramal);
    - série: nó de passagem (2 ligações, sem ser bomba/válvula/fonte) entre tubos de mesmo DN e material
      some, os dois tubos viram um só e a demanda do nó é dividida entre as pontas.
    Bombas, válvulas, reservatórios e captações nunca são removidos."""
    import geopandas as gpd
    from shapely.geometry import LineString
    if os.path.abspath(destino) == os.path.abspath(gpkg):
        raise ValueError("o destino precisa ser outro arquivo (o cadastro original não é alterado)")
    tr = gpd.read_file(gpkg, layer="trecho")
    nos = gpd.read_file(gpkg, layer="no_juncao")
    fixos = set()
    for camada in ("captacao", "reservatorio", "bomba", "valvula"):
        try:
            fixos |= set(gpd.read_file(gpkg, layer=camada)["id"].astype(str))
        except Exception:
            pass
    tr = tr[tr["situacao"].fillna("EXISTENTE") != "DESATIVADO"].copy()
    nos = nos.copy()
    nos["demanda_base"] = nos["demanda_base"].fillna(0.0).astype(float)
    dem = dict(zip(nos["id"], nos["demanda_base"]))
    removidos_t, removidos_n, unidos = 0, 0, 0

    def grau():
        g = defaultdict(list)
        for i, r in tr.iterrows():
            g[r["no_inicial"]].append(i)
            g[r["no_final"]].append(i)
        return g

    if cortar_ramais:
        mudou = True
        while mudou:
            mudou = False
            g = grau()
            for n, ts in list(g.items()):
                if len(ts) != 1 or n in fixos or n not in dem:
                    continue
                i = ts[0]
                r = tr.loc[i]
                if (r["diametro_nominal"] or 0) > dn_max:
                    continue
                if comprimento_max is not None and (r["comprimento"] or 0) > comprimento_max:
                    continue
                outro = r["no_final"] if r["no_inicial"] == n else r["no_inicial"]
                if outro in dem:
                    dem[outro] = dem.get(outro, 0) + dem.get(n, 0)
                elif dem.get(n, 0) > 0:
                    continue  # ramal ligado direto numa bomba/válvula/fonte: não perde a demanda
                dem.pop(n, None)
                tr = tr.drop(index=i)
                removidos_t += 1
                removidos_n += 1
                mudou = True
    if unir_serie:
        mudou = True
        while mudou:
            mudou = False
            g = grau()
            for n, ts in list(g.items()):
                if len(ts) != 2 or n in fixos or n not in dem:
                    continue
                a, b = tr.loc[ts[0]], tr.loc[ts[1]]
                if a["diametro_nominal"] != b["diametro_nominal"] or (a["material"] or "") != (b["material"] or ""):
                    continue
                # orienta: a termina em n, b começa em n
                ga = list(a.geometry.coords) if a["no_final"] == n else list(a.geometry.coords)[::-1]
                gb = list(b.geometry.coords) if b["no_inicial"] == n else list(b.geometry.coords)[::-1]
                ini = a["no_inicial"] if a["no_final"] == n else a["no_final"]
                fim = b["no_final"] if b["no_inicial"] == n else b["no_inicial"]
                if ini == fim:
                    continue
                d = dem.pop(n, 0)
                for ponta in (ini, fim):
                    if ponta in dem:
                        dem[ponta] += d / 2
                novo = a.copy()
                novo["geometry"] = LineString(ga + gb[1:])
                novo["no_inicial"], novo["no_final"] = ini, fim
                novo["comprimento"] = round((a["comprimento"] or 0) + (b["comprimento"] or 0), 2)
                novo["observacao"] = f"unido de {a['id']} + {b['id']} (esqueletização)"
                tr.loc[ts[0]] = novo
                tr = tr.drop(index=ts[1])
                removidos_n += 1
                unidos += 1
                mudou = True
                break
    nos = nos[nos["id"].isin(dem.keys())].copy()
    nos["demanda_base"] = nos["id"].map(dem).round(4)
    shutil.copyfile(gpkg, destino)
    tr.to_file(destino, layer="trecho", driver="GPKG")
    nos.to_file(destino, layer="no_juncao", driver="GPKG")
    qgz = os.path.join(os.path.dirname(destino), "GWATER_" + os.path.splitext(os.path.basename(destino))[0] + ".qgz")
    origem_qgz = os.path.join(os.path.dirname(gpkg), "GWATER_" + os.path.splitext(os.path.basename(gpkg))[0] + ".qgz")
    if os.path.exists(origem_qgz):
        import zipfile
        with zipfile.ZipFile(origem_qgz) as zin, zipfile.ZipFile(qgz, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                dados = zin.read(item.filename)
                if item.filename.endswith(".qgs"):
                    dados = dados.replace(os.path.basename(gpkg).encode(), os.path.basename(destino).encode())
                zout.writestr(item, dados)
    else:
        qgz = None
    return {"ok": True, "gpkg": destino, "qgz": qgz, "tubos_removidos": removidos_t, "nos_removidos": removidos_n,
            "tubos_unidos": unidos, "tubos_final": int(len(tr)), "nos_final": int(len(nos)),
            "demanda_total": _r(sum(dem.values()), 3)}


FUNCOES = {"incendio": incendio, "descarga": descarga, "criticidade": criticidade, "zonas_pressao": zonas_pressao,
           "energia": energia, "renovacao": renovacao, "dimensionar": dimensionar, "qualidade": qualidade,
           "comparar": comparar, "esqueletizar": esqueletizar}


def rodar(nome, gpkg, parametros):
    """Ponte do gwater_cli: erros de cadastro voltam como itens da aba Problemas."""
    try:
        return FUNCOES[nome](gpkg, **parametros)
    except ErroModelo as e:
        return {"ok": False, "itens": e.itens, "erro": str(e)}
