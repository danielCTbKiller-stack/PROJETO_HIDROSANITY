"""Consultas (Queries do WaterGEMS) e Navegador.

Revisão da rede: nós muito próximos, tubulações que se cruzam, nós órfãos, pontas, candidatos a divisão,
tubulações sem nós e duplicadas, elementos isolados. Rastreamento: conectados, adjacentes, desconectados,
caminho mais curto, a montante e a jusante (pelo sentido do fluxo calculado) e isolar um trecho (que
registros fechar). Dados de entrada e Resultados: filtros prontos. Personalizadas: condições do usuário.
O resultado vai para o Navegador: lista dos elementos, um a um, e seleção no mapa.
"""
import math
from collections import defaultdict

from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsSpatialIndex
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDockWidget, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QSplitter, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .tema import icone
from .util import NOMES, PONTOS, achar, selecionar_ids


# ================================================================ dados da rede
class Rede:
    """Rede do cadastro para as consultas: pontos {id: (camada, feição)} e tubulações."""

    def __init__(self, nucleo):
        self.nucleo = nucleo
        self.pontos, self.tubos = {}, {}
        for c in PONTOS:
            try:
                for f in nucleo.camada(c).getFeatures():
                    self.pontos[str(f["id"])] = (c, f)
            except LookupError:
                pass
        try:
            for f in nucleo.camada("trecho").getFeatures():
                self.tubos[str(f["id"])] = f
        except LookupError:
            pass

    def grafo(self, abertos=False):
        import networkx as nx
        g = nx.MultiGraph()
        for pid in self.pontos:
            g.add_node(pid)
        for tid, f in self.tubos.items():
            if abertos and str(f["status"]) == "FECHADO":
                continue
            if str(f["situacao"]) == "DESATIVADO":
                continue
            a, b = str(f["no_inicial"]), str(f["no_final"])
            if a in self.pontos and b in self.pontos:
                g.add_edge(a, b, key=tid)
        if abertos:  # válvula fechada corta a passagem
            for pid, (c, f) in self.pontos.items():
                if c == "valvula" and str(f["status"]) == "FECHADA":
                    g.remove_edges_from(list(g.edges(pid, keys=True)))
        return g

    def fontes(self):
        return [pid for pid, (c, _) in self.pontos.items() if c in ("captacao", "reservatorio")]


def _xy(f):
    g = f.geometry()
    return QgsPointXY(g.vertexAt(0)) if g.isMultipart() else g.asPoint()


# ================================================================ revisão da rede
def nos_proximos(nucleo, tol=None):
    if tol is None:
        tol, ok = QInputDialog.getDouble(nucleo.janela, "Nós muito próximos", "Distância máxima (m):", 0.5, 0.001, 100, 3)
        if not ok:
            return None
    r = Rede(nucleo)
    idx = QgsSpatialIndex()
    pts = {}
    for i, (pid, (_, f)) in enumerate(r.pontos.items()):
        p = _xy(f)
        pts[i] = (pid, p)
        idx.addFeature(i, QgsGeometry.fromPointXY(p).boundingBox())
    out, visto = [], set()
    for i, (pid, p) in pts.items():
        for j in idx.intersects(QgsGeometry.fromPointXY(p).buffer(tol, 4).boundingBox()):
            if j <= i:
                continue
            qid, q = pts[j]
            d = p.distance(q)
            if d <= tol and (pid, qid) not in visto:
                visto.add((pid, qid))
                out.append((pid, f"a {d:.3f} m de {qid}"))
                out.append((qid, f"a {d:.3f} m de {pid}"))
    return out


def tubos_cruzando(nucleo):
    r = Rede(nucleo)
    idx = QgsSpatialIndex()
    geoms = {}
    for i, (tid, f) in enumerate(r.tubos.items()):
        geoms[i] = (tid, f.geometry())
        idx.addFeature(i, f.geometry().boundingBox())
    out = []
    for i, (tid, g) in geoms.items():
        for j in idx.intersects(g.boundingBox()):
            if j <= i:
                continue
            uid, h = geoms[j]
            if g.crosses(h):
                inter = g.intersection(h)
                out.append((tid, f"cruza {uid} sem nó (pode ser travessia sem ligação, ou ligação faltando)"))
                out.append((uid, f"cruza {tid}"))
    return out


def nos_orfaos(nucleo):
    r = Rede(nucleo)
    ligados = set()
    for f in r.tubos.values():
        ligados |= {str(f["no_inicial"]), str(f["no_final"])}
    return [(pid, f"{NOMES[c]} sem nenhuma tubulação ligada") for pid, (c, _) in r.pontos.items() if pid not in ligados]


def pontas(nucleo, so_juncao=False):
    r = Rede(nucleo)
    grau = defaultdict(int)
    for f in r.tubos.values():
        grau[str(f["no_inicial"])] += 1
        grau[str(f["no_final"])] += 1
    out = []
    for pid, (c, f) in r.pontos.items():
        if grau.get(pid) == 1 and (not so_juncao or c == "no_juncao"):
            if so_juncao and float(f["demanda_base"] or 0) > 0:
                continue
            out.append((pid, f"ponta de rede ({NOMES[c].lower()})" + ("" if not so_juncao else ", sem demanda")))
    return out


def candidatos_divisao(nucleo, tol=None):
    if tol is None:
        tol, ok = QInputDialog.getDouble(nucleo.janela, "Candidatos a divisão",
                                         "Distância máxima de um nó ao meio da tubulação (m):", 0.5, 0.001, 50, 3)
        if not ok:
            return None
    r = Rede(nucleo)
    idx = QgsSpatialIndex()
    tubos = list(r.tubos.items())
    for i, (_, f) in enumerate(tubos):
        idx.addFeature(i, f.geometry().boundingBox())
    out = []
    for pid, (c, f) in r.pontos.items():
        p = _xy(f)
        gp = QgsGeometry.fromPointXY(p)
        for i in idx.intersects(gp.buffer(tol, 4).boundingBox()):
            tid, t = tubos[i]
            if pid in (str(t["no_inicial"]), str(t["no_final"])):
                continue
            g = t.geometry()
            if g.distance(gp) <= tol:
                d = g.lineLocatePoint(gp)
                if tol < d < g.length() - tol:
                    out.append((pid, f"está sobre a tubulação {tid} sem dividi-la (use Dividir tubulações)"))
    return out


def tubos_sem_nos(nucleo):
    r = Rede(nucleo)
    out = []
    for tid, f in r.tubos.items():
        g = f.geometry()
        for campo, ponta in (("no_inicial", 0), ("no_final", -1)):
            nid = str(f[campo])
            if nid in ("", "NULL", "None") or nid not in r.pontos:
                out.append((tid, f"{campo} vazio ou inexistente ({nid})"))
                break
            vs = list(g.vertices())
            pp = QgsPointXY(vs[ponta])
            if pp.distance(_xy(r.pontos[nid][1])) > 0.05:
                out.append((tid, f"a ponta não está sobre o nó {nid} ({pp.distance(_xy(r.pontos[nid][1])):.2f} m)"))
                break
    return out


def tubos_duplicados(nucleo):
    r = Rede(nucleo)
    por = defaultdict(list)
    for tid, f in r.tubos.items():
        por[frozenset((str(f["no_inicial"]), str(f["no_final"])))].append(tid)
    out = []
    for k, ts in por.items():
        if len(ts) > 1:
            for t in ts:
                out.append((t, "mesmas pontas que " + ", ".join(x for x in ts if x != t)))
    return out


def isolados(nucleo, abertos=True):
    import networkx as nx
    r = Rede(nucleo)
    g = r.grafo(abertos=abertos)
    fontes = set(r.fontes())
    out = []
    for comp in nx.connected_components(g):
        if not comp & fontes:
            for n in comp:
                out.append((n, "sem ligação com captação ou reservatório" + (" (com registros fechados)" if abertos else "")))
    for tid, f in r.tubos.items():
        if str(f["no_inicial"]) in {x for x, _ in out}:
            out.append((tid, "tubulação num trecho isolado"))
    return out


# ================================================================ rastreamento
def _selecao(nucleo):
    from .util import ids_selecionados
    return ids_selecionados(nucleo)


def conectados(nucleo):
    import networkx as nx
    sel = _selecao(nucleo)
    if not sel:
        nucleo.informar("Selecione um elemento: a consulta acha tudo o que está ligado a ele.")
        return None
    r = Rede(nucleo)
    g = r.grafo(abertos=True)
    inicio = set()
    for s in sel:
        if s in r.pontos:
            inicio.add(s)
        elif s in r.tubos:
            inicio |= {str(r.tubos[s]["no_inicial"]), str(r.tubos[s]["no_final"])}
    comp = set()
    for n in inicio:
        if n in g:
            comp |= nx.node_connected_component(g, n)
    tubos = [tid for tid, f in r.tubos.items() if str(f["no_inicial"]) in comp and str(f["no_final"]) in comp]
    return [(n, "conectado") for n in sorted(comp)] + [(t, "conectada") for t in tubos]


def adjacentes(nucleo):
    sel = _selecao(nucleo)
    if not sel:
        nucleo.informar("Selecione um ou mais elementos.")
        return None
    r = Rede(nucleo)
    out = []
    for s in sel:
        if s in r.pontos:
            for tid, f in r.tubos.items():
                if s in (str(f["no_inicial"]), str(f["no_final"])):
                    outro = str(f["no_final"]) if str(f["no_inicial"]) == s else str(f["no_inicial"])
                    out += [(tid, f"tubulação ligada a {s}"), (outro, f"nó vizinho de {s}")]
        elif s in r.tubos:
            f = r.tubos[s]
            out += [(str(f["no_inicial"]), f"início de {s}"), (str(f["no_final"]), f"fim de {s}")]
    return out


def desconectados(nucleo):
    return isolados(nucleo, abertos=False)


def caminho(nucleo):
    import networkx as nx
    sel = [s for s in _selecao(nucleo)]
    r = Rede(nucleo)
    pts = [s for s in sel if s in r.pontos]
    if len(pts) != 2:
        nucleo.informar("Selecione exatamente dois nós (Shift soma à seleção).")
        return None
    g = nx.Graph()
    for tid, f in r.tubos.items():
        g.add_edge(str(f["no_inicial"]), str(f["no_final"]), id=tid, L=float(f["comprimento"] or f.geometry().length()))
    try:
        c = nx.shortest_path(g, pts[0], pts[1], weight="L")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        nucleo.aviso("Não há caminho pela rede entre os dois nós.")
        return None
    L = 0
    out = []
    for a, b in zip(c, c[1:]):
        L += g[a][b]["L"]
        out.append((a, f"{L - g[a][b]['L']:.1f} m do início"))
        out.append((g[a][b]["id"], f"tubulação, {g[a][b]['L']:.1f} m"))
    out.append((c[-1], f"{L:.1f} m do início (fim)"))
    return out


def _direcionado(nucleo):
    """Grafo no sentido do fluxo na hora escolhida (precisa do cálculo)."""
    import networkx as nx
    res = nucleo.res
    if not res:
        nucleo.aviso("Calcule a rede (F5): o sentido do fluxo vem do resultado.")
        return None, None
    k = nucleo.janela.passo()
    r = Rede(nucleo)
    g = nx.DiGraph()
    for tid, f in r.tubos.items():
        l = res.d["links"].get(tid)
        a, b = str(f["no_inicial"]), str(f["no_final"])
        if not l or abs(l["q"][k]) < 1e-4:
            continue
        if l["q"][k] > 0:
            g.add_edge(a, b, id=tid)
        else:
            g.add_edge(b, a, id=tid)
    return g, r


def montante(nucleo, jusante=False):
    import networkx as nx
    sel = _selecao(nucleo)
    if not sel:
        nucleo.informar("Selecione um elemento.")
        return None
    g, r = _direcionado(nucleo)
    if g is None:
        return None
    inicio = set()
    for s in sel:
        if s in r.pontos:
            inicio.add(s)
        elif s in r.tubos:
            inicio.add(str(r.tubos[s]["no_inicial"]) if not jusante else str(r.tubos[s]["no_final"]))
    nos = set()
    for n in inicio:
        if n in g:
            nos |= (nx.descendants(g, n) if jusante else nx.ancestors(g, n)) | {n}
    tubos = [d["id"] for a, b, d in g.edges(data=True) if a in nos and b in nos]
    rot = "a jusante (a água vem dele)" if jusante else "a montante (a água passa por ele)"
    return [(n, rot) for n in sorted(nos)] + [(t, rot) for t in tubos]


def isolar(nucleo):
    """Registros a fechar para isolar a tubulação selecionada e o que fica sem água."""
    import networkx as nx
    sel = _selecao(nucleo)
    r = Rede(nucleo)
    tubos = [s for s in sel if s in r.tubos]
    if not tubos:
        nucleo.informar("Selecione a tubulação a isolar (vazamento, manutenção).")
        return None
    g = r.grafo(abertos=False)
    valvulas = {pid for pid, (c, _) in r.pontos.items() if c == "valvula"}
    fontes = set(r.fontes())
    segmento, fechar, fila = set(), set(), []
    for t in tubos:
        fila += [str(r.tubos[t]["no_inicial"]), str(r.tubos[t]["no_final"])]
    while fila:
        n = fila.pop()
        if n in segmento or n in fechar:
            continue
        if n in valvulas:
            fechar.add(n)
            continue
        if n in fontes:
            fechar.add(n)
            continue
        segmento.add(n)
        fila += [m for m in g.neighbors(n)]
    if not fechar - fontes:
        nucleo.aviso("Não há válvulas/registros para isolar este trecho: ele só se isola desligando a fonte.")
    g2 = g.copy()
    g2.remove_nodes_from(segmento | fechar)
    sem_agua = set()
    for comp in nx.connected_components(g2):
        if not comp & fontes:
            sem_agua |= comp
    out = [(v, "FECHAR este registro/válvula") for v in sorted(fechar - fontes)]
    out += [(n, "fica sem água (dentro do trecho isolado)") for n in sorted(segmento)]
    out += [(n, "fica sem água (perde a ligação com a fonte)") for n in sorted(sem_agua)]
    return out


# ================================================================ dados de entrada
def _filtro(nucleo, camada, expr, texto):
    try:
        lyr = nucleo.camada(camada)
    except LookupError:
        return []
    return [(str(f["id"]), texto) for f in lyr.getFeatures(QgsFeatureRequest().setFilterExpression(expr))]


def codigos_repetidos(nucleo):
    vistos = defaultdict(list)
    for lyr in nucleo.camadas_rede():
        for f in lyr.getFeatures():
            vistos[str(f["id"])].append(lyr.name())
    out = []
    for k, v in vistos.items():
        if len(v) > 1 or k in ("", "NULL", "None"):
            out.append((k, "código repetido em " + ", ".join(v) if len(v) > 1 else "sem código"))
    return out


def controlados(nucleo):
    try:
        ctl = nucleo.camada("controle")
    except LookupError:
        return []
    out = []
    for f in ctl.getFeatures():
        out.append((str(f["elemento"]), f"{f['acao']} se {f['condicao']} {f['no_ref'] or ''} {f['valor']}"))
        if f["no_ref"] and str(f["no_ref"]) != "NULL":
            out.append((str(f["no_ref"]), f"controla {f['elemento']}"))
    return out


def com_series(nucleo):
    import os
    gpkg = nucleo.cadastro()
    import json
    arq = os.path.splitext(gpkg)[0] + "_dados_recebidos.json"
    out = []
    try:
        dados = json.load(open(arq, encoding="utf-8")) if os.path.exists(arq) else {}
    except ValueError:
        dados = {}
    for el, info in dados.items():
        out.append((el, f"dados recebidos: {', '.join(info.get('series', {}))}"))
    return out


# ================================================================ resultados
def _res(nucleo):
    if not nucleo.res:
        nucleo.aviso("Calcule a rede (F5) para as consultas de resultado.")
        return None
    return nucleo.res


def res_nos(nucleo, cond, texto):
    res = _res(nucleo)
    if not res:
        return None
    out = []
    for nid in res.rid_consumo:
        p = res.d["nos"][nid]["p"]
        if cond(p):
            out.append((nid, texto.format(min=min(p), max=max(p))))
    return out


def res_tubos(nucleo, cond, texto, campo="v"):
    res = _res(nucleo)
    if not res:
        return None
    return [(t, texto.format(max=max(abs(x) for x in res.d["links"][t][campo])))
            for t in res.rid_tr if cond([abs(x) for x in res.d["links"][t][campo]])]


def res_reservatorios(nucleo, cheio):
    res = _res(nucleo)
    if not res:
        return None
    out = []
    try:
        for f in nucleo.camada("reservatorio").getFeatures():
            n = res.d["nos"].get(str(f["id"]))
            if not n:
                continue
            if cheio and f["nivel_max"] and max(n["p"]) >= float(f["nivel_max"]) - 0.05:
                out.append((str(f["id"]), f"chega ao nível máximo ({max(n['p']):.2f} m)"))
            if not cheio and min(n["p"]) <= float(f["nivel_min"] or 0) + 0.05:
                out.append((str(f["id"]), f"chega ao nível mínimo ({min(n['p']):.2f} m)"))
    except LookupError:
        pass
    return out


def res_links(nucleo, camada, cond, texto):
    res = _res(nucleo)
    if not res:
        return None
    out = []
    try:
        for f in nucleo.camada(camada).getFeatures():
            l = res.d["links"].get(str(f["id"]))
            if l and cond(l, f):
                out.append((str(f["id"]), texto))
    except LookupError:
        pass
    return out


def bombas_fora_curva(nucleo):
    res = _res(nucleo)
    if not res:
        return None
    try:
        curvas = defaultdict(list)
        for f in nucleo.camada("curva").getFeatures():
            curvas[str(f["id_curva"])].append((float(f["x"]), float(f["y"])))
    except LookupError:
        return []
    out = []
    for f in nucleo.camada("bomba").getFeatures():
        l = res.d["links"].get(str(f["id"]))
        pts = sorted(curvas.get(str(f["curva"]), []))
        if not l or not pts:
            continue
        qmax = pts[-1][0] if len(pts) > 1 else pts[0][0] * 2
        acima = [q for q, s in zip(l["q"], l["s"]) if s and q > qmax * 1.001]
        if acima:
            out.append((str(f["id"]), f"vazão até {max(acima):.1f} L/s, além do fim da curva ({qmax:g} L/s)"))
    return out


def valvulas_sem_regular(nucleo):
    res = _res(nucleo)
    if not res:
        return None
    out = []
    try:
        for f in nucleo.camada("valvula").getFeatures():
            l = res.d["links"].get(str(f["id"]))
            if l and f["tipo"] in ("PRV", "PSV", "FCV", "PBV") and str(f["status"]) in ("ATIVA", "NULL", "None"):
                horas = sum(1 for s in l["s"] if s != 2)
                if horas:
                    out.append((str(f["id"]), f"não regula em {horas} de {len(l['s'])} passos (fica aberta ou fechada)"))
    except LookupError:
        pass
    return out


# ================================================================ catálogo das consultas
CONSULTAS = [
    ("Revisão da rede", [
        ("Nós muito próximos…", nos_proximos), ("Tubulações que se cruzam", tubos_cruzando),
        ("Nós órfãos (sem tubulação)", nos_orfaos), ("Pontas de rede", lambda n: pontas(n)),
        ("Junções de ponta sem demanda", lambda n: pontas(n, True)), ("Candidatos a divisão…", candidatos_divisao),
        ("Tubulações sem nós", tubos_sem_nos), ("Tubulações duplicadas", tubos_duplicados),
        ("Elementos isolados (com registros fechados)", lambda n: isolados(n, True)),
    ]),
    ("Rastreamento", [
        ("Conectados à seleção", conectados), ("Adjacentes à seleção", adjacentes),
        ("Desconectados de qualquer fonte", desconectados), ("Caminho mais curto (2 nós)", caminho),
        ("A montante (pelo fluxo)", lambda n: montante(n, False)), ("A jusante (pelo fluxo)", lambda n: montante(n, True)),
        ("Isolar a tubulação (registros a fechar)…", isolar),
    ]),
    ("Dados de entrada", [
        ("Códigos repetidos ou vazios", codigos_repetidos),
        ("Elementos desativados", lambda n: sum((_filtro(n, c, "\"situacao\" = 'DESATIVADO'", "desativado")
                                                 for c in ("trecho",) + PONTOS), [])),
        ("Elementos projetados", lambda n: sum((_filtro(n, c, "\"situacao\" = 'PROJETADO'", "projetado")
                                                for c in ("trecho",) + PONTOS), [])),
        ("Tubulações com retenção (CV)", lambda n: _filtro(n, "trecho", "\"status\" = 'CV'", "válvula de retenção")),
        ("Tubulações fechadas", lambda n: _filtro(n, "trecho", "\"status\" = 'FECHADO'", "fechada no cadastro")),
        ("Válvulas fechadas", lambda n: _filtro(n, "valvula", "\"status\" = 'FECHADA'", "fechada no cadastro")),
        ("Bombas desligadas no início", lambda n: _filtro(n, "bomba", "\"status_inicial\" = 'FECHADA'", "começa desligada")),
        ("Elementos controlados", controlados),
        ("Hidrantes", lambda n: _filtro(n, "no_juncao", "\"tipo\" = 'HIDRANTE'", "hidrante")),
        ("Nós sem cota", lambda n: sum((_filtro(n, c, "\"cota\" IS NULL", "sem cota") for c in PONTOS), [])),
        ("Nós sem demanda", lambda n: _filtro(n, "no_juncao", "coalesce(\"demanda_base\", 0) = 0", "demanda zero")),
        ("Tubulações sem material ou rugosidade", lambda n: _filtro(
            n, "trecho", "\"material\" IS NULL OR \"material\" = '' OR \"rugosidade_hw\" IS NULL", "sem material/C")),
        ("Elementos sem zona (setor)", lambda n: sum((_filtro(n, c, "\"setor\" IS NULL OR \"setor\" = ''", "sem setor")
                                                      for c in ("trecho",) + PONTOS), [])),
        ("Elementos com dados recebidos", com_series),
    ]),
    ("Resultados", [
        ("Pressões negativas", lambda n: res_nos(n, lambda p: min(p) < 0, "mínima {min:.1f} mca")),
        ("Pressão abaixo de 10 mca", lambda n: res_nos(n, lambda p: min(p) < 10, "mínima {min:.1f} mca")),
        ("Pressão acima de 50 mca", lambda n: res_nos(n, lambda p: max(p) > 50, "máxima {max:.1f} mca")),
        ("Bombas fora da curva", bombas_fora_curva),
        ("Válvulas que não regulam", valvulas_sem_regular),
        ("Reservatórios vazios", lambda n: res_reservatorios(n, False)),
        ("Reservatórios cheios", lambda n: res_reservatorios(n, True)),
        ("Bombas desligadas o dia todo", lambda n: res_links(n, "bomba", lambda l, f: not any(l["s"]), "desligada")),
        ("Válvulas fechadas no cálculo", lambda n: res_links(n, "valvula", lambda l, f: any(s == 0 for s in l["s"]),
                                                             "fechada em algum momento")),
        ("Tubulações fechadas no cálculo", lambda n: res_links(n, "trecho", lambda l, f: any(s == 0 for s in l["s"]),
                                                               "fechada em algum momento")),
        ("Velocidade acima de 2,5 m/s", lambda n: res_tubos(n, lambda v: max(v) > 2.5, "máxima {max:.2f} m/s")),
        ("Perda de carga acima de 10 m/km", lambda n: res_tubos(n, lambda v: max(v) > 10, "máxima {max:.1f} m/km", "hl")),
        ("Sem autolimpeza (vel. máx < 0,6 m/s)", lambda n: res_tubos(n, lambda v: max(v) < 0.6, "máxima {max:.2f} m/s")),
        ("Água parada (vel. máx < 0,01 m/s)", lambda n: res_tubos(n, lambda v: max(v) < 0.01, "máxima {max:.3f} m/s")),
    ]),
]


# ================================================================ painel
class PainelConsultas(QDockWidget):
    def __init__(self, janela):
        super().__init__("Consultas", janela)
        self.setObjectName("GwaterConsultas")
        self.janela = janela
        sp = QSplitter(Qt.Orientation.Vertical)
        cima = QWidget()
        v = QVBoxLayout(cima)
        v.setContentsMargins(4, 4, 4, 4)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.funcoes = {}
        for grupo, itens in CONSULTAS:
            g = QTreeWidgetItem([grupo])
            g.setIcon(0, icone("consultas"))
            for nome, f in itens:
                it = QTreeWidgetItem([nome])
                self.funcoes[id(it)] = (nome, f)
                g.addChild(it)
            self.arvore.addTopLevelItem(g)
        self.pers = QTreeWidgetItem(["Personalizadas"])
        self.pers.setIcon(0, icone("consultas"))
        self.arvore.addTopLevelItem(self.pers)
        self.arvore.itemDoubleClicked.connect(self._rodar)
        v.addWidget(QLabel("Clique duplo roda a consulta:"))
        v.addWidget(self.arvore, 1)
        h = QHBoxLayout()
        b = QPushButton("Nova consulta…")
        b.setToolTip("Consulta personalizada: um tipo de elemento e uma condição (fica salva no projeto)")
        b.clicked.connect(self._nova)
        h.addWidget(b)
        b = QPushButton("Rodar")
        b.clicked.connect(lambda: self._rodar(self.arvore.currentItem()))
        h.addWidget(b)
        v.addLayout(h)
        sp.addWidget(cima)
        # ---- navegador
        baixo = QWidget()
        v2 = QVBoxLayout(baixo)
        v2.setContentsMargins(4, 4, 4, 4)
        self.titulo = QLabel("<b>Navegador</b>")
        v2.addWidget(self.titulo)
        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(lambda it, _p: it and self._ir(it))
        v2.addWidget(self.lista, 1)
        h2 = QHBoxLayout()
        for texto, f in (("◀", lambda: self._passo(-1)), ("▶", lambda: self._passo(1)),
                         ("Selecionar todos", self._todos)):
            b = QPushButton(texto)
            b.clicked.connect(f)
            h2.addWidget(b)
        v2.addLayout(h2)
        sp.addWidget(baixo)
        self.setWidget(sp)
        janela.projeto.connect(self._carregar_personalizadas)

    def _carregar_personalizadas(self):
        while self.pers.childCount():
            self.pers.removeChild(self.pers.child(0))
        for nome, (camada, expr) in self.janela._ler_json("consultas", {}).items():
            it = QTreeWidgetItem([nome])
            self.funcoes[id(it)] = (nome, lambda n, c=camada, e=expr: _filtro(n, c, e, e))
            self.pers.addChild(it)

    def _nova(self):
        from qgis.PyQt.QtWidgets import QComboBox, QLineEdit
        from .util import Dialogo
        nucleo = self.janela.nucleo
        if not nucleo.cadastro():
            return
        d = Dialogo(self.janela, "Nova consulta", "Ex.: tubulações com \"diametro_nominal\" <= 50 AND \"material\" = "
                    "'Cimento-amianto'. Fica na lista Personalizadas.")
        nome = d.linha("Nome:", QLineEdit())
        tipo = QComboBox()
        for c in ("trecho",) + PONTOS:
            tipo.addItem(NOMES[c], c)
        d.linha("Elemento:", tipo)
        expr = d.linha("Condição:", QLineEdit())
        d.botoes("Gravar")
        if d.exec() and nome.text().strip() and expr.text().strip():
            dados = self.janela._ler_json("consultas", {})
            dados[nome.text().strip()] = [tipo.currentData(), expr.text().strip()]
            self.janela.gravar_json("consultas", dados)
            self._carregar_personalizadas()

    def _rodar(self, it):
        if it is None or id(it) not in self.funcoes:
            return
        nucleo = self.janela.nucleo
        if not nucleo.cadastro():
            return nucleo.aviso("Abra um cadastro primeiro.")
        nome, f = self.funcoes[id(it)]
        self.janela.ocupado(f"Consulta: {nome}…")
        try:
            r = f(nucleo)
        finally:
            self.janela.livre()
        if r is None:
            return
        self.mostrar(nome, r)

    def mostrar(self, nome, itens):
        self.lista.blockSignals(True)
        self.lista.clear()
        for eid, texto in itens:
            it = QListWidgetItem(f"{eid}  —  {texto}")
            it.setData(Qt.ItemDataRole.UserRole, eid)
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        n = len({e for e, _ in itens})
        self.titulo.setText(f"<b>Navegador</b> · {nome}: {n} elemento(s)")
        self.show()
        self.raise_()
        if n:
            selecionar_ids(self.janela.nucleo, [e for e, _ in itens], zoom=False)
        else:
            self.janela.nucleo.informar(f"{nome}: nenhum elemento encontrado.")

    def _ir(self, it):
        selecionar_ids(self.janela.nucleo, [it.data(Qt.ItemDataRole.UserRole)])

    def _passo(self, d):
        if self.lista.count():
            self.lista.setCurrentRow((self.lista.currentRow() + d) % self.lista.count())

    def _todos(self):
        selecionar_ids(self.janela.nucleo, [self.lista.item(i).data(Qt.ItemDataRole.UserRole)
                                            for i in range(self.lista.count())])


def consultas(nucleo):
    nucleo.janela.mostrar_painel("consultas")


ACOES = {"consultas": consultas, "navegador": consultas}
