"""Edição da rede como no WaterGEMS:

  Inverter sentido      Reverse: a tubulação passa a ir do nó final para o inicial (geometria e nós)
  Converter em…         Morph: troca o tipo do elemento (nó → hidrante, nó → PRV, válvula → bomba…) no mesmo lugar,
                        com as tubulações ligadas no elemento novo
  Unir nós próximos     Merge Nodes in Close Proximity: nós a menos da tolerância viram um só (demandas somadas)
"""
from qgis.core import QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle
from qgis.PyQt.QtWidgets import QComboBox, QDoubleSpinBox

from .nucleo import DESENHO_TIPO
from .util import Dialogo, ids_selecionados, num

NOMES_TIPO = {"no": "Nó (junção)", "ponto_consumo": "Nó de consumo", "hidrante": "Hidrante",
              "reservatorio": "Reservatório", "captacao": "Captação", "bomba": "Bomba", "valvula_prv": "PRV",
              "valvula_psv": "PSV", "valvula_pbv": "PBV", "valvula_fcv": "FCV", "valvula_vre": "VRE", "valvula_vse": "VSE", "valvula_tcv": "TCV",
              "retencao": "Retenção", "turbina": "Turbina", "orificio": "Orifício entre tubos",
              "area_linear": "Válvula de área linear", "tomada": "Tomada", "ventosa": "Ventosa",
              "valvula_alivio": "Válvula de alívio", "disco_ruptura": "Disco de ruptura",
              "descarga_atmosfera": "Descarga para a atmosfera", "tanque_hidropneumatico": "Tanque hidropneumático",
              "chamine_equilibrio": "Chaminé de equilíbrio", "carga_periodica": "Carga-vazão periódica",
              "valvula_gpv": "GPV", "registro": "Registro"}
COMUNS = ("nome", "cota", "setor", "situacao", "observacao", "diametro")
# camada e valores de cada destino (os que se desenham com tipo; os outros têm camada própria)
DESTINOS = {**DESENHO_TIPO, "no": ("no_juncao", {"tipo": "JUNCAO"}), "ponto_consumo": ("no_juncao", {"tipo": "CONSUMO"}), "reservatorio": ("reservatorio", {}),
            "captacao": ("captacao", {}), "bomba": ("bomba", {"status_inicial": "ABERTA", "rotacao_relativa": 1.0})}


def _topo(nucleo):
    t = nucleo.topologia
    if not t.camadas:
        t.conectar()
    return t


class _Ocupado:
    """Nossas edições não disparam a ligação automática (ela trataria cada mudança como um desenho novo)."""

    def __init__(self, topo):
        self.t = topo

    def __enter__(self):
        self.antes, self.t.ocupado = self.t.ocupado, True

    def __exit__(self, *_):
        self.t.ocupado = self.antes


# ================================================================ inverter sentido
def inverter_sentido(nucleo, ids=None):
    tr = nucleo.camada("trecho")
    fids = list(tr.selectedFeatureIds()) if ids is None else \
        [f.id() for f in tr.getFeatures() if str(f["id"]) in set(ids)]
    if not fids:
        return nucleo.informar("Selecione as tubulações a inverter.")
    topo = _topo(nucleo)
    if not tr.isEditable():
        tr.startEditing()
    i_a, i_b = tr.fields().indexOf("no_inicial"), tr.fields().indexOf("no_final")
    with _Ocupado(topo):
        tr.beginEditCommand("Inverter sentido")
        for f in tr.getFeatures(QgsFeatureRequest().setFilterFids(fids)):
            pts = [QgsPointXY(v) for v in f.geometry().vertices()]
            tr.changeGeometry(f.id(), QgsGeometry.fromPolylineXY(pts[::-1]), True)
            tr.changeAttributeValue(f.id(), i_a, f["no_final"], None, True)
            tr.changeAttributeValue(f.id(), i_b, f["no_inicial"], None, True)
        tr.endEditCommand()
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{len(fids)} tubulação(ões) com o sentido invertido (Ctrl+Z desfaz).")
    return len(fids)


# ================================================================ converter em outro tipo (Morph)
def converter(nucleo, alvo=None, ids=None):
    pontos = [(lyr, fids) for lyr, fids in nucleo.janela.selecionados() if nome_de(nucleo, lyr) != "trecho"]
    if ids is not None:
        pontos = []
        for c in ("no_juncao", "reservatorio", "captacao", "bomba", "valvula"):
            lyr = nucleo.camada(c)
            fs = [f.id() for f in lyr.getFeatures() if str(f["id"]) in set(ids)]
            if fs:
                pontos.append((lyr, fs))
    if not pontos:
        return nucleo.informar("Selecione no mapa os nós, válvulas, bombas ou reservatórios a converter.")
    n = sum(len(f) for _, f in pontos)
    if alvo is None:
        d = Dialogo(nucleo.janela, "Converter em…",
                    f"Troca o tipo dos {n} elemento(s) selecionado(s), no mesmo lugar, como o Morph do WaterGEMS: as "
                    "tubulações passam a ligar no elemento novo e o código, a cota, a zona e o nome são mantidos.")
        cb = QComboBox()
        for k, t in NOMES_TIPO.items():
            cb.addItem(t, k)
        d.linha("Converter em:", cb)
        d.botoes("Converter")
        if not d.exec():
            return
        alvo = cb.currentData()
    if alvo not in DESTINOS:
        return nucleo.aviso(f"Tipo desconhecido: {alvo}.")
    camada_alvo, fixos = DESTINOS[alvo]
    topo = _topo(nucleo)
    dest = nucleo.camada(camada_alvo)
    tr = nucleo.camada("trecho")
    feitos, avisos = 0, []
    with _Ocupado(topo):
        for lyr in {dest, tr} | {l for l, _ in pontos}:
            if not lyr.isEditable():
                lyr.startEditing()
            lyr.beginEditCommand(f"Converter em {NOMES_TIPO.get(alvo, alvo)}")
        try:
            usados = {str(f["id"]) for f in dest.getFeatures()}
            for lyr, fids in pontos:
                for f in lyr.getFeatures(QgsFeatureRequest().setFilterFids(fids)):
                    cod = str(f["id"])
                    if lyr.id() == dest.id():  # mesma camada: só o tipo (nó → hidrante, PRV → FCV…)
                        for campo, v in fixos.items():
                            if dest.fields().indexOf(campo) >= 0:
                                dest.changeAttributeValue(f.id(), dest.fields().indexOf(campo), v)
                        feitos += 1
                        continue
                    if camada_alvo in ("valvula", "bomba"):
                        ligadas = _grau(tr, cod)
                        if ligadas != 2:
                            avisos.append(f"{cod}: tem {ligadas} tubulação(ões) ligadas (válvula e bomba ficam entre "
                                          "exatamente 2)")
                            continue
                    novo = QgsFeature(dest.fields())
                    novo.setGeometry(QgsGeometry(f.geometry()))
                    for campo in COMUNS:
                        if dest.fields().indexOf(campo) >= 0 and f.fields().indexOf(campo) >= 0:
                            novo[campo] = f[campo]
                    if dest.fields().indexOf("cota") >= 0 and f.fields().indexOf("cota_fundo") >= 0:
                        novo["cota"] = f["cota_fundo"]
                    if dest.fields().indexOf("cota_fundo") >= 0 and f.fields().indexOf("cota") >= 0:
                        novo["cota_fundo"] = f["cota"]
                    for campo, v in fixos.items():
                        if dest.fields().indexOf(campo) >= 0:
                            novo[campo] = v
                    novo_cod = cod if cod not in usados else topo.proximo_id(camada_alvo)
                    novo["id"] = novo_cod
                    usados.add(novo_cod)
                    if dest.fields().indexOf("fid") >= 0:
                        novo["fid"] = None
                    dest.addFeature(novo)
                    if novo_cod != cod:
                        topo.religar(cod, novo_cod)
                    lyr.deleteFeature(f.id())
                    feitos += 1
        finally:
            for lyr in {dest, tr} | {l for l, _ in pontos}:
                lyr.endEditCommand()
    nucleo.janela.canvas.refresh()
    nucleo.janela.dock_arvore.recontar()
    msg = f"{feitos} elemento(s) convertido(s) em {NOMES_TIPO.get(alvo, alvo)}."
    if avisos:
        msg += " Não convertidos: " + "; ".join(avisos[:5]) + "."
    nucleo.informar(msg + " Confira os dados no painel Propriedades e Salvar edições.")
    return feitos


def _grau(tr, cod):
    from qgis.core import QgsExpression
    filtro = f'"no_inicial" = {QgsExpression.quotedValue(cod)} OR "no_final" = {QgsExpression.quotedValue(cod)}'
    return sum(1 for _ in tr.getFeatures(QgsFeatureRequest().setFilterExpression(filtro)))


def nome_de(nucleo, lyr):
    for c in ("trecho", "no_juncao", "reservatorio", "captacao", "bomba", "valvula"):
        try:
            if nucleo.camada(c).id() == lyr.id():
                return c
        except LookupError:
            pass
    return None


# ================================================================ unir nós próximos
def unir_nos(nucleo, tol=None):
    nos = nucleo.camada("no_juncao")
    if tol is None:
        d = Dialogo(nucleo.janela, "Unir nós próximos",
                    "Nós (junções) a menos da tolerância um do outro viram um só, como o Merge Nodes in Close "
                    "Proximity do WaterGEMS: fica o nó com mais tubulações, as demandas são somadas e as tubulações "
                    "passam a ligar nele. Só os selecionados, se houver seleção.")
        t = QDoubleSpinBox()
        t.setRange(0.001, 100)
        t.setDecimals(3)
        t.setValue(0.5)
        t.setSuffix(" m")
        d.linha("Tolerância:", t)
        d.botoes("Unir")
        if not d.exec():
            return
        tol = t.value()
    topo = _topo(nucleo)
    tr = nucleo.camada("trecho")
    so = set(nos.selectedFeatureIds())
    feats = [f for f in nos.getFeatures() if f.hasGeometry() and (not so or f.id() in so)]
    grau = {}
    for t_ in tr.getFeatures():
        for c in ("no_inicial", "no_final"):
            grau[str(t_[c])] = grau.get(str(t_[c]), 0) + 1
    from qgis.core import QgsSpatialIndex
    idx = QgsSpatialIndex(nos.getFeatures(QgsFeatureRequest().setFilterFids([f.id() for f in feats])),
                          flags=QgsSpatialIndex.Flag.FlagStoreFeatureGeometries)
    por_fid = {f.id(): f for f in feats}
    pai = {f.id(): f.id() for f in feats}

    def raiz(x):
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x
    for f in feats:
        p = f.geometry().asPoint()
        for o in idx.intersects(QgsRectangle(p.x() - tol, p.y() - tol, p.x() + tol, p.y() + tol)):
            if o != f.id() and por_fid[o].geometry().asPoint().distance(p) <= tol:
                pai[raiz(o)] = raiz(f.id())
    grupos = {}
    for f in feats:
        grupos.setdefault(raiz(f.id()), []).append(f)
    grupos = [g for g in grupos.values() if len(g) > 1]
    if not grupos:
        nucleo.informar(f"Nenhum par de nós a menos de {num(tol, 3)} m.")
        return 0
    i_d = nos.fields().indexOf("demanda_base")
    removidos = 0
    with _Ocupado(topo):
        for lyr in (nos, tr):
            if not lyr.isEditable():
                lyr.startEditing()
            lyr.beginEditCommand("Unir nós próximos")
        try:
            for g in grupos:
                fica = max(g, key=lambda f: (grau.get(str(f["id"]), 0), -f.id()))
                p = fica.geometry().asPoint()
                dem = sum(float(f["demanda_base"] or 0) for f in g if str(f["demanda_base"]) != "NULL")
                nos.changeAttributeValue(fica.id(), i_d, round(dem, 6))
                for f in g:
                    if f.id() == fica.id():
                        continue
                    cod = str(f["id"])
                    filtro = f'"no_inicial" = \'{cod}\' OR "no_final" = \'{cod}\''
                    for t_ in tr.getFeatures(QgsFeatureRequest().setFilterExpression(filtro)):
                        pts = [QgsPointXY(v) for v in t_.geometry().vertices()]
                        if str(t_["no_inicial"]) == cod:
                            pts[0] = p
                            tr.changeAttributeValue(t_.id(), tr.fields().indexOf("no_inicial"), str(fica["id"]))
                        if str(t_["no_final"]) == cod:
                            pts[-1] = p
                            tr.changeAttributeValue(t_.id(), tr.fields().indexOf("no_final"), str(fica["id"]))
                        tr.changeGeometry(t_.id(), QgsGeometry.fromPolylineXY(pts), True)
                    nos.deleteFeature(f.id())
                    removidos += 1
            # tubulação que ficou com as duas pontas no mesmo nó não leva água a lugar nenhum
            curtas = [t_.id() for t_ in tr.getFeatures() if str(t_["no_inicial"]) == str(t_["no_final"])
                      and t_.geometry().length() <= 2 * tol]
            tr.deleteFeatures(curtas)
        finally:
            nos.endEditCommand()
            tr.endEditCommand()
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{removidos} nó(s) unido(s) em {len(grupos)} grupo(s); {len(curtas)} tubulação(ões) sem "
                    "comprimento removida(s). Ctrl+Z desfaz.")
    return removidos


ACOES = {"inverter_sentido": inverter_sentido, "converter": converter, "unir_nos": unir_nos}
