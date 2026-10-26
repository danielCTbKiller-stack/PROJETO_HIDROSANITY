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
def _zona_de(wn):
    """Zona de pressão de cada nó (bombas, PRV/PSV/PBV/FCV e trechos fechados fazem a divisa)."""
    g = nx.Graph()
    g.add_nodes_from(wn.node_name_list)
    for nome, l in wn.links():
        if l.link_type == "Pump" or (l.link_type == "Valve" and l.valve_type in VALVULAS_ZONA) or \
                l.initial_status == LinkStatus.Closed:
            continue
        g.add_edge(l.start_node_name, l.end_node_name)
    out = {}
    for i, comp in enumerate(nx.connected_components(g)):
        for n in comp:
            out[n] = i
    return out


def incendio(gpkg, com_projetados=False, alteracoes=None, nos=None, vazao=10.0, p_residual=10.0,
             p_min_zona=None, p_min_sistema=None, v_max=None, modo="somar", hora=None, vazao_max=500.0):
    """Fire Flow do WaterGEMS: para cada nó, a maior vazão de incêndio que mantém
      - `p_residual` (mca) no próprio nó;
      - `p_min_zona` em todos os nós da mesma zona de pressão (opcional);
      - `p_min_sistema` em todos os nós da rede (opcional);
      - velocidade até `v_max` (m/s) em todas as tubulações (opcional).
    modo "somar": a vazão de incêndio soma à demanda do nó; "substituir": ocupa o lugar dela.
    Atende = disponível ≥ `vazao`."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=True)
        R = Rapido(arq)
        outros = m.consumo
        avaliados = set(m.pontos_consumo())  # pressões da zona e do sistema: só nos pontos de consumo (NBR 12218)
        zona = _zona_de(m.wn)
        tubos = list(m.wn.pipe_name_list)
        try:
            base = {n: R.no_valor(n, EN.BASEDEMAND) for n in outros}

            def testar(n, q):
                R.mudar_no(n, EN.BASEDEMAND, (base[n] if modo == "somar" else 0.0) + q)
                ok = R.resolver()
                r = {"ok": ok, "p": R.no_valor(n, EN.PRESSURE) if ok else -1e9, "pz": None, "no_pz": None,
                     "ps": None, "no_ps": None, "v": None, "tubo_v": None}
                if ok:
                    for o in avaliados:
                        if o == n:
                            continue
                        v = R.no_valor(o, EN.PRESSURE)
                        if zona.get(o) == zona.get(n) and (r["pz"] is None or v < r["pz"]):
                            r["pz"], r["no_pz"] = v, o
                        if r["ps"] is None or v < r["ps"]:
                            r["ps"], r["no_ps"] = v, o
                    if v_max is not None:
                        for tb in tubos:
                            v = abs(R.link_valor(tb, EN.VELOCITY))
                            if r["v"] is None or v > r["v"]:
                                r["v"], r["tubo_v"] = v, tb
                R.mudar_no(n, EN.BASEDEMAND, base[n])
                falhas = []
                if not ok:
                    falhas.append("o cálculo não convergiu")
                else:
                    if r["p"] < p_residual:
                        falhas.append("pressão residual no nó")
                    if p_min_zona is not None and r["pz"] is not None and r["pz"] < p_min_zona:
                        falhas.append(f"pressão na zona ({r['no_pz']})")
                    if p_min_sistema is not None and r["ps"] is not None and r["ps"] < p_min_sistema:
                        falhas.append(f"pressão no sistema ({r['no_ps']})")
                    if v_max is not None and r["v"] is not None and r["v"] > v_max:
                        falhas.append(f"velocidade ({r['tubo_v']})")
                r["falhas"] = falhas
                return not falhas, r

            linhas = []
            for n in _candidatos_hidrante(m, nos):
                atende_q, rq = testar(n, vazao)
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
                _, rl = testar(n, lo)
                _, rlim = testar(n, min(hi, lo + 0.1))  # o que limita logo acima da disponível
                linhas.append({"id": n, "q_necessaria": vazao, "q_disponivel": _r(lo, 1), "atende": bool(atende_q),
                               "q_total": _r((base[n] if modo == "somar" else 0) + lo, 1),
                               "p_residual": _r(rq["p"], 1), "p_min_zona": _r(rq["pz"], 1), "no_p_min_zona": rq["no_pz"],
                               "p_min_sistema": _r(rq["ps"], 1), "no_p_min_sistema": rq["no_ps"],
                               "v_max": _r(rq["v"], 2), "tubo_v_max": rq["tubo_v"],
                               "limitado_por": ", ".join(rlim["falhas"]) if lo < vazao_max else ""})
        finally:
            R.fechar()
        linhas.sort(key=lambda r: (r["atende"], r["q_disponivel"] or 0))
        return {"ok": True, "hora": _hora_txt(t), "linhas": linhas,
                "atendem": sum(r["atende"] for r in linhas), "total": len(linhas),
                "parametros": {"vazao": vazao, "p_residual": p_residual, "p_min_zona": p_min_zona,
                               "p_min_sistema": p_min_sistema, "v_max": v_max, "modo": modo}}
    finally:
        m.fechar()


# ================================================================ descarga (Flushing)
def descarga(gpkg, com_projetados=False, alteracoes=None, nos=None, vazao=20.0, v_alvo=0.76, hora=None,
             modo="vazao", p_hidrante=10.0, vazao_max=200.0, p_min=None):
    """Flushing do WaterGEMS: cada nó aberto sozinho; as tubulações que passam de `v_alvo` (m/s) ficam limpas.
    modo "vazao": a descarga tira `vazao` (L/s). modo "pressao": tira o máximo que mantém `p_hidrante` (mca)
    no próprio hidrante (até `vazao_max`). `p_min` (opcional): aponta quando outro nó fica abaixo dela."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        arq, t = m.instante(hora * 3600 if hora is not None else None, dda=True)
        R = Rapido(arq)
        tubos = list(m.wn.pipe_name_list)
        outros = m.pontos_consumo()
        try:
            R.resolver()
            v0 = {p: abs(R.link_valor(p, EN.VELOCITY)) for p in tubos}
            eventos = []
            for n in _candidatos_hidrante(m, nos):
                base = R.no_valor(n, EN.BASEDEMAND)
                q = vazao
                if modo == "pressao":  # maior vazão com a pressão residual no hidrante
                    lo, hi = 0.0, float(vazao_max)
                    for _ in range(18):
                        meio = (lo + hi) / 2
                        R.mudar_no(n, EN.BASEDEMAND, base + meio)
                        if R.resolver() and R.no_valor(n, EN.PRESSURE) >= p_hidrante:
                            lo = meio
                        else:
                            hi = meio
                        if hi - lo < 0.05:
                            break
                    q = lo
                R.mudar_no(n, EN.BASEDEMAND, base + q)
                ok = R.resolver()
                limpos = []
                pm, onde = None, None
                if ok:
                    for p in tubos:
                        v = abs(R.link_valor(p, EN.VELOCITY))
                        if v >= v_alvo:
                            limpos.append({"id": p, "v": _r(v, 2), "v_antes": _r(v0[p], 2)})
                    for o in outros:
                        if o != n:
                            v = R.no_valor(o, EN.PRESSURE)
                            if pm is None or v < pm:
                                pm, onde = v, o
                p_no = R.no_valor(n, EN.PRESSURE) if ok else None
                R.mudar_no(n, EN.BASEDEMAND, base)
                limpos.sort(key=lambda x: -x["v"])
                eventos.append({"id": n, "vazao": _r(q, 1), "p_no": _r(p_no, 1), "n_tubos": len(limpos),
                                "comprimento_m": _r(sum(m.wn.get_link(x["id"]).length for x in limpos), 0),
                                "v_max": limpos[0]["v"] if limpos else None,
                                "p_min_rede": _r(pm, 1), "no_p_min": onde,
                                "abaixo_p_min": bool(p_min is not None and pm is not None and pm < p_min),
                                "tubos": limpos[:200], "convergiu": ok})
        finally:
            R.fechar()
        eventos.sort(key=lambda e: -e["comprimento_m"])
        return {"ok": True, "hora": _hora_txt(t), "eventos": eventos, "v_alvo": v_alvo, "modo": modo}
    finally:
        m.fechar()


# ================================================================ criticidade (Criticality)
def segmentos(m):
    """Segmentos da rede (Segmentation do WaterGEMS): trechos que ficam ligados sem passar por um registro.
    Fechar um segmento = fechar os registros em volta dele. Devolve [{"id", "tubos", "nos", "registros"}]."""
    tipos = dict(zip(m.c["valvula"]["id"], m.c["valvula"]["tipo"])) if len(m.c["valvula"]) else {}
    registros = {v for v, tp in tipos.items() if str(tp).upper() in ("REGISTRO", "TCV")}
    g = nx.MultiGraph()
    reg_nos = defaultdict(set)  # registro → nós em que ele encosta
    for nome, l in m.wn.links():
        a, b = l.start_node_name, l.end_node_name
        if nome in registros:
            reg_nos[nome] |= {a, b}
            continue
        if l.link_type == "Pipe":
            g.add_edge(a, b, key=nome)
        else:  # bombas e outras válvulas não isolam: ligam os dois lados
            g.add_edge(a, b, key=nome)
    out = []
    for comp in nx.connected_components(g):
        tubos = sorted({k for a, b, k in g.subgraph(comp).edges(keys=True) if k in m.wn.pipe_name_list})
        if not tubos:
            continue
        regs = sorted(r for r, ns in reg_nos.items() if ns & comp)
        out.append({"tubos": tubos, "nos": sorted(n for n in comp if "__" not in n), "registros": regs})
    out.sort(key=lambda s_: -len(s_["tubos"]))
    for i, s_ in enumerate(out, start=1):
        s_["id"] = f"SEG{i:03d}"
    return out


def criticidade(gpkg, com_projetados=False, alteracoes=None, trechos=None, hora=None, p_min=10.0, modo="trecho"):
    """Criticality do WaterGEMS, com demanda dependente da pressão: água que deixa de ser entregue e nós abaixo
    de `p_min` quando sai de operação
      modo "trecho": cada tubulação, sozinha;
      modo "segmento": cada segmento entre registros (fecham-se os registros em volta e todo o trecho fica sem
      água, como numa manobra real)."""
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

            def fechar_link(p):
                st = R.link_valor(p, EN.INITSTATUS)
                try:
                    R.mudar_link(p, EN.INITSTATUS, 0)
                    return lambda: R.mudar_link(p, EN.INITSTATUS, st)
                except Exception:  # tubo com retenção (CV): diâmetro mínimo corta o fluxo
                    d = R.link_valor(p, EN.DIAMETER)
                    R.mudar_link(p, EN.DIAMETER, 0.01)
                    return lambda: R.mudar_link(p, EN.DIAMETER, d)

            if modo == "segmento":
                alvos = [(s_["id"], s_["tubos"], s_) for s_ in segmentos(m)
                         if not trechos or set(s_["tubos"]) & set(trechos)]
            else:
                alvos = [(p, [p], None) for p in (trechos or m.wn.pipe_name_list) if p in R.link]
            linhas = []
            for ident, tubos, seg in alvos:
                desfazer = [fechar_link(p) for p in tubos if p in R.link]
                ok = R.resolver()
                if ok:
                    entregue = sum(R.no_valor(n, EN.DEMAND) for n in nos)
                    baixos = [n for n in nos if R.no_valor(n, EN.PRESSURE) < p_min and n not in baixos0]
                    sem_agua = [n for n in nos if R.no_valor(n, EN.BASEDEMAND) > 1e-9
                                and R.no_valor(n, EN.DEMAND) < 0.01 * R.no_valor(n, EN.BASEDEMAND)]
                else:
                    entregue, baixos, sem_agua = 0.0, [], []
                for f in reversed(desfazer):
                    f()
                falta = max(0.0, entregue0 - entregue)
                lin = {"id": ident, "falta_lps": _r(falta, 2),
                       "falta_pct": _r(100 * falta / pedido, 1) if pedido > 0 else 0.0,
                       "nos_baixa_pressao": len(baixos), "nos_sem_agua": len(sem_agua),
                       "exemplos": (sem_agua or baixos)[:8], "convergiu": ok}
                if seg is not None:
                    lin.update({"tubos": tubos, "n_tubos": len(tubos), "registros": seg["registros"],
                                "comprimento_m": _r(sum(m.wn.get_link(p).length for p in tubos), 0)})
                linhas.append(lin)
        finally:
            R.fechar()
        linhas.sort(key=lambda r: (-(r["falta_pct"] or 0), -r["nos_baixa_pressao"]))
        return {"ok": True, "hora": _hora_txt(t), "pedido_lps": _r(pedido, 2), "linhas": linhas, "p_min": p_min,
                "modo": modo}
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
            dem = sum(d.base_value * 1000 for n in juncs for d in wn.get_node(n).demand_timeseries_list)
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
            curva_ef = getattr(b, "efficiency", None)
            if curva_ef is not None and getattr(curva_ef, "points", None):  # curva de rendimento da definição
                xs = np.array([x for x, _ in curva_ef.points]) * 1000 if max(x for x, _ in curva_ef.points) < 10                     else np.array([x for x, _ in curva_ef.points])
                ys = np.array([y for _, y in curva_ef.points]) / 100
                etas = np.interp(q * 1000, xs, ys)
                eta = float(np.mean(etas[ligada])) if ligada.any() else float(ys.mean())
            else:
                etas = np.full_like(q, eta)
            if b.pump_type == "POWER":  # potência constante: a da definição é a entregue à água
                pot = np.where(ligada, float(b.power) / 1000 / np.maximum(etas, 0.05), 0.0)
            else:
                pot = np.where(ligada, 9.81 * q * np.maximum(h, 0) / np.maximum(etas, 0.05), 0.0)  # kW
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
                v_max=3.0, hora=None, metodo="guloso", max_avaliacoes=3000):
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
            if metodo == "genetico":  # Darwin Designer: busca global do menor custo que atende (DN por índice)
                from scipy.optimize import differential_evolution
                caro = sum(custo(dns[-1], p) for p in cand) or 1.0

                def custo_total(x):
                    teste = {p: dns[int(round(i))] for p, i in zip(cand, x)}
                    pm2, vm2 = avaliar(teste)
                    falta = max(0.0, p_min - pm2) + max(0.0, vm2 - v_max) * 5
                    return sum(custo(d, p) for p, d in teste.items()) + (caro * (1 + falta) if falta > 0 else 0)
                pop = 15
                ger = max(5, int(max_avaliacoes) // (pop * len(cand)) - 1)
                x0 = [dns.index(min(dns, key=lambda d: abs(d - dn0[p]))) for p in cand]
                sol = differential_evolution(custo_total, [(0, len(dns) - 1)] * len(cand), integrality=[True] * len(cand),
                                             popsize=pop, maxiter=ger, seed=1, polish=False, x0=x0, tol=1e-8)
                atual = {p: dns[int(round(i))] for p, i in zip(cand, sol.x)}
                pm, vm = avaliar(atual)
                passos = len(cand) * len(dns)  # pula o guloso
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
            return {"ok": True, "hora": _hora_txt(t), "atende": bool(pm >= p_min and vm <= v_max), "metodo": metodo,
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
              kb_dia=-0.5, kw=0.0, fonte=None):
    """Idade da água (h), cloro residual (mg/L, decaimento de 1ª ordem `kb_dia` em 1/dia, cloro `conc_fonte`
    nas captações e reservatórios-fonte) ou rastreamento (TRACE: % da água de cada nó que veio de `fonte`).
    Devolve as últimas 24 h de cada nó."""
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        wn = m.wn
        wn.options.time.duration = int(duracao_h * 3600)
        wn.options.time.quality_timestep = 300
        parametro = parametro.upper()
        if parametro == "AGE":
            wn.options.quality.parameter = "AGE"
        elif parametro == "TRACE":
            if not fonte or fonte not in wn.node_name_list:
                raise ValueError(f"escolha a fonte a rastrear (captação, reservatório ou nó): '{fonte}'")
            wn.options.quality.parameter = "TRACE"
            wn.options.quality.trace_node = fonte
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
        return {"ok": True, "parametro": {"AGE": "idade (h)", "TRACE": f"água de {fonte} (%)"}.get(
                    parametro, "cloro (mg/L)"),
                "horas": [_r((t - ult.index[0]) / 3600, 3) for t in ult.index], "nos": nos}
    finally:
        m.fechar()


# ================================================================ comparação de cenários
def _indicadores(m, lim=None):
    lim = {"limite_pressao_min": 10.0, "limite_pressao_max": 50.0, "limite_velocidade": 2.5, **(lim or {})}
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
           "nos_abaixo_10": int((p.min() < lim["limite_pressao_min"]).sum()) if p.size else 0,
           "nos_acima_50": int((p.max() > lim["limite_pressao_max"]).sum()) if p.size else 0,
           "v_max": _r(v[tubos].max().max(), 2) if tubos else None, "perda_max_m_km": _r(hl.max().max(), 1) if tubos else None,
           "tubos_v_alta": int((v[tubos].max() > lim["limite_velocidade"]).sum()) if tubos else 0,
           "atendimento_pct": _r(100 * entregue / esp, 1) if esp > 0 else 100.0,
           "volume_entregue_m3": _r(entregue, 0)}
    return out


def comparar(gpkg, com_projetados=False, cenario_a=None, cenario_b=None, limites=None, hora=None):
    """cenario_a / cenario_b: listas de alterações (None = rede atual). Indicadores e diferenças por elemento:
    pressão (mínima do dia, ou na `hora`), velocidade e vazão (máximas do dia, ou na `hora`)."""
    ma = Modelo(gpkg, com_projetados, cenario_a)
    mb = Modelo(gpkg, com_projetados, cenario_b)
    try:
        ia, ib = _indicadores(ma, limites), _indicadores(mb, limites)
        pa, pb = ma.res.node["pressure"], mb.res.node["pressure"]

        def na_hora(df, col, agreg):
            s_ = df[col]
            if hora is None:
                return float(agreg(s_))
            t = s_.index[np.abs(np.asarray(s_.index) - hora * 3600).argmin()]
            return float(s_.at[t])
        nos = []
        for n in sorted(set(ma.consumo) & set(mb.consumo)):
            a, b = na_hora(pa, n, np.min), na_hora(pb, n, np.min)
            nos.append({"id": n, "p_min_a": _r(a, 1), "p_min_b": _r(b, 1), "dif": _r(b - a, 1)})
        va, vb = ma.res.link["velocity"].abs(), mb.res.link["velocity"].abs()
        qa, qb = ma.res.link["flowrate"].abs() * 1000, mb.res.link["flowrate"].abs() * 1000
        tubos = []
        for t in sorted(set(ma.wn.pipe_name_list) & set(mb.wn.pipe_name_list)):
            a, b = na_hora(va, t, np.max), na_hora(vb, t, np.max)
            q1, q2 = na_hora(qa, t, np.max), na_hora(qb, t, np.max)
            tubos.append({"id": t, "v_max_a": _r(a, 2), "v_max_b": _r(b, 2), "dif": _r(b - a, 2),
                          "q_a": _r(q1, 2), "q_b": _r(q2, 2), "dif_q": _r(q2 - q1, 2)})
        nos.sort(key=lambda x: -abs(x["dif"] or 0))
        tubos.sort(key=lambda x: -abs(x["dif"] or 0))
        return {"ok": True, "a": ia, "b": ib, "nos": nos, "tubos": tubos}
    finally:
        ma.fechar()
        mb.fechar()


# ================================================================ esqueletização (Skelebrator)
def esqueletizar(gpkg, destino, dn_max=100.0, cortar_ramais=True, unir_serie=True, comprimento_max=None,
                 unir_paralelos=True, tol_dn_pct=0.0, dn_max_serie=None, protegidos=()):
    """Grava em `destino` uma cópia do cadastro simplificada (Skelebrator do WaterGEMS):
    - ramais (Branch Trimming): tubulação de ponta (nó com 1 só ligação) com DN ≤ `dn_max` (e até
      `comprimento_max` m) sai, e a demanda do nó da ponta passa para o nó de onde o ramal sai;
    - série (Series Pipe Merging): nó de passagem (2 ligações, sem ser bomba/válvula/fonte) entre tubos de DN
      parecido (diferença até `tol_dn_pct` %) some; os dois viram um tubo equivalente (DN do mais longo e C que
      dá a mesma perda de carga de Hazen-Williams) e a demanda do nó vai metade para cada ponta;
    - paralelos (Parallel Pipe Merging): tubos entre os mesmos dois nós viram um só, com o DN do maior e o C
      que conduz a mesma vazão.
    Bombas, válvulas, reservatórios, captações e os nós `protegidos` (ex.: pontos de medição) nunca saem."""
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
    fixos |= {str(p) for p in protegidos}
    tr = tr[tr["situacao"].fillna("EXISTENTE") != "DESATIVADO"].copy()
    tr["rugosidade_hw"] = tr["rugosidade_hw"].fillna(130.0).astype(float)
    paralelos = 0
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
                da, db = float(a["diametro_nominal"] or 0), float(b["diametro_nominal"] or 0)
                if not da or not db or abs(da - db) > tol_dn_pct / 100 * max(da, db) + 1e-9:
                    continue
                if dn_max_serie is not None and max(da, db) > dn_max_serie:
                    continue
                if tol_dn_pct <= 0 and (a["material"] or "") != (b["material"] or ""):
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
                la, lb = float(a["comprimento"] or 0) or 1e-3, float(b["comprimento"] or 0) or 1e-3
                deq = da if la >= lb else db  # Hazen-Williams: mesma perda de carga com o DN do mais longo
                soma = la / (a["rugosidade_hw"] ** 1.852 * da ** 4.87) + lb / (b["rugosidade_hw"] ** 1.852 * db ** 4.87)
                novo["diametro_nominal"] = deq
                novo["rugosidade_hw"] = round(((la + lb) / (deq ** 4.87 * soma)) ** (1 / 1.852), 1)
                novo["observacao"] = f"unido de {a['id']} + {b['id']} (esqueletização)"
                tr.loc[ts[0]] = novo
                tr = tr.drop(index=ts[1])
                removidos_n += 1
                unidos += 1
                mudou = True
                break
    if unir_paralelos:
        grupos = defaultdict(list)
        for i, r in tr.iterrows():
            grupos[frozenset((r["no_inicial"], r["no_final"]))].append(i)
        for chave, idx in grupos.items():
            if len(idx) < 2 or len(chave) < 2:
                continue
            rs = [tr.loc[i] for i in idx]
            base = max(rs, key=lambda r: float(r["diametro_nominal"] or 0))
            D, L = float(base["diametro_nominal"]), float(base["comprimento"] or 1)
            # mesma vazão com a mesma perda: Σ C·D^2,63 / L^0,54 do conjunto = C_eq·D^2,63 / L^0,54
            soma = sum(float(r["rugosidade_hw"]) * float(r["diametro_nominal"] or 0) ** 2.63
                       / (float(r["comprimento"] or 1) ** 0.54) for r in rs)
            novo = base.copy()
            novo["rugosidade_hw"] = round(soma * L ** 0.54 / D ** 2.63, 1)
            novo["observacao"] = "paralelos " + " + ".join(str(r["id"]) for r in rs) + " (esqueletização)"
            tr.loc[base.name] = novo
            tr = tr.drop(index=[i for i in idx if i != base.name])
            paralelos += len(idx) - 1
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
            "tubos_unidos": unidos, "paralelos_unidos": paralelos, "tubos_final": int(len(tr)),
            "nos_final": int(len(nos)),
            "demanda_total": _r(sum(dem.values()), 3)}


FUNCOES = {"incendio": incendio, "descarga": descarga, "criticidade": criticidade, "zonas_pressao": zonas_pressao,
           "energia": energia, "renovacao": renovacao, "dimensionar": dimensionar, "qualidade": qualidade,
           "comparar": comparar, "esqueletizar": esqueletizar,
           "calibrar_darwin": lambda gpkg, **k: __import__("darwin").calibrar(gpkg, **k)}


def rodar(nome, gpkg, parametros):
    """Ponte do gwater_cli: erros de cadastro voltam como itens da aba Problemas."""
    try:
        return FUNCOES[nome](gpkg, **parametros)
    except ErroModelo as e:
        return {"ok": False, "itens": e.itens, "erro": str(e)}
    except ValueError as e:  # dados da análise incompletos: mensagem para o usuário
        return {"ok": False, "erro": str(e), "itens": [{"nivel": "ERRO", "msg": str(e), "camada": None, "id": None}]}
