"""Consumidores, como o Customer Meter do WaterGEMS.

O consumidor é um ponto com o símbolo de casa e a sua demanda, sem tubulação própria: fica ligado a um nó ou a uma
tubulação (campo `ligado_a`, `tipo_ligacao` NO ou TRECHO), e uma linha tracejada no mapa vai da casa ao nó ou ao
meio da tubulação. No cálculo a demanda vai para o nó, ou metade para cada ponta da tubulação
(motor/cadastro_para_inp.consumidores).

Ao desenhar, o consumidor liga sozinho no nó ou no meio de tubulação mais perto. Cadastros criados antes ganham a
camada ao abrir.
"""
import math

from qgis.core import (
    Qgis, QgsCoordinateTransformContext, QgsDefaultValue, QgsFeatureRequest, QgsField, QgsFields,
    QgsMarkerSymbol, QgsProject, QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer, QgsVectorFileWriter, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType, QTimer

from .tema import ICONES

NOME = "Consumidores"
CAMPOS = [("id", QMetaType.Type.QString), ("nome", QMetaType.Type.QString), ("demanda_base", QMetaType.Type.Double),
          ("padrao", QMetaType.Type.QString), ("ligado_a", QMetaType.Type.QString),
          ("tipo_ligacao", QMetaType.Type.QString), ("categoria", QMetaType.Type.QString),
          ("situacao", QMetaType.Type.QString), ("setor", QMetaType.Type.QString),
          ("observacao", QMetaType.Type.QString)]
ID_PADRAO = ("'CL-' || lpad(to_string(coalesce(maximum(to_int(regexp_substr(\"id\", '^CL-(\\\\d+)$'))), 0) + 1), "
             "4, '0')")


def _criar_tabela(gpkg, crs):
    flds = QgsFields()
    for nome, tipo in CAMPOS:
        flds.append(QgsField(nome, tipo))
    mem = QgsVectorLayer(f"Point?crs={crs.authid()}", "consumidor", "memory")
    mem.dataProvider().addAttributes(flds.toList())
    mem.updateFields()
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = "GPKG"
    opt.layerName = "consumidor"
    opt.fileEncoding = "UTF-8"
    opt.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsCoordinateTransformContext(), opt)
    if err[0] != QgsVectorFileWriter.WriterError.NoError:
        raise RuntimeError(f"não consegui criar a camada de consumidores: {err[1]}")


def garantir(nucleo):
    """Põe a camada de consumidores no projeto (criando a tabela no GeoPackage se o cadastro é antigo)."""
    gpkg = nucleo.cadastro()
    if not gpkg:
        return None
    try:
        lyr = nucleo.camada("consumidor")
    except LookupError:
        lyr = QgsVectorLayer(f"{gpkg}|layername=consumidor", NOME, "ogr")
        if not lyr.isValid():
            _criar_tabela(gpkg, nucleo.camada("no_juncao").crs())
            lyr = QgsVectorLayer(f"{gpkg}|layername=consumidor", NOME, "ogr")
        prj = QgsProject.instance()
        prj.addMapLayer(lyr, False)
        no = prj.layerTreeRoot().findLayer(nucleo.camada("no_juncao").id())
        grupo = no.parent() if no is not None else prj.layerTreeRoot()
        grupo.insertLayer(grupo.children().index(no) if no is not None else 0, lyr)
        nucleo._invalidar_camadas()
    preparar(nucleo, lyr)
    return lyr


def preparar(nucleo, lyr):
    idx = lyr.fields().indexOf
    for campo, expr in (("id", ID_PADRAO), ("situacao", "'EXISTENTE'"), ("demanda_base", "0")):
        if idx(campo) >= 0:
            lyr.setDefaultValueDefinition(idx(campo), QgsDefaultValue(expr))
    estilo(nucleo, lyr)
    formulario(nucleo, lyr)
    if not getattr(lyr, "_gwater_ligado", False):
        lyr.featureAdded.connect(lambda fid: QTimer.singleShot(0, lambda: _ao_adicionar(nucleo, lyr, fid)))
        lyr._gwater_ligado = True


def formulario(nucleo, lyr=None):
    """O formulário do consumidor novo abre ou não como o das outras camadas (caixa do painel de cálculo)."""
    try:
        lyr = lyr or nucleo.camada("consumidor")
        cfg = lyr.editFormConfig()
        cfg.setSuppress(nucleo.camada("no_juncao").editFormConfig().suppress())
        lyr.setEditFormConfig(cfg)
    except LookupError:
        pass


def estilo(nucleo, lyr):
    """Casa no ponto. A linha tracejada até o nó (ou o meio da tubulação) é desenhada à parte (`Ligacoes`): um
    símbolo que lê as outras camadas (get_feature) roda na linha de desenho do mapa e travava o QGIS quando os nós
    eram editados ao mesmo tempo."""
    s = QgsMarkerSymbol()
    s.deleteSymbolLayer(0)
    s.appendSymbolLayer(QgsSvgMarkerSymbolLayer(f"{ICONES}/elem_consumidor.svg".replace("\\", "/"), 5.0))
    lyr.setRenderer(QgsSingleSymbolRenderer(s))
    lyr.triggerRepaint()
    lig = getattr(nucleo, "_ligacoes_consumidores", None)
    if lig is None:
        lig = nucleo._ligacoes_consumidores = Ligacoes(nucleo)
    lig.conectar(lyr)


class Ligacoes:
    """Linhas tracejadas casa → nó / meio da tubulação, numa camada de desenho do mapa (não vai para o projeto).
    Refeitas pouco depois de qualquer mudança em consumidores, nós ou tubulações."""

    def __init__(self, nucleo):
        from qgis.gui import QgsRubberBand
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtGui import QColor
        self.nucleo = nucleo
        self.banda = QgsRubberBand(nucleo.janela.canvas, Qgis.GeometryType.Line)
        self.banda.setColor(QColor("#e8590c"))
        self.banda.setWidth(1)
        self.banda.setLineStyle(Qt.PenStyle.DashLine)
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refazer)
        self.ligadas = set()
        QgsProject.instance().cleared.connect(self._limpar)

    def _limpar(self):
        self.timer.stop()
        self.ligadas.clear()
        self.banda.reset(Qgis.GeometryType.Line)

    def conectar(self, cons):
        for nome in ("consumidor", "no_juncao", "trecho"):
            try:
                lyr = cons if nome == "consumidor" else self.nucleo.camada(nome)
            except LookupError:
                continue
            if lyr.id() in self.ligadas:
                continue
            self.ligadas.add(lyr.id())
            for sinal in (lyr.featureAdded, lyr.featuresDeleted, lyr.attributeValueChanged, lyr.geometryChanged,
                          lyr.afterRollBack, lyr.afterCommitChanges):
                sinal.connect(lambda *_: self.timer.start())
            if nome == "consumidor":
                QgsProject.instance().layerTreeRoot().findLayer(lyr.id()).visibilityChanged.connect(
                    lambda *_: self.timer.start())
        self.timer.start()

    def refazer(self):
        from qgis.core import QgsGeometry, QgsPointXY
        try:
            cons = self.nucleo.camada("consumidor")
            nos, tr = self.nucleo.camada("no_juncao"), self.nucleo.camada("trecho")
            no_arvore = QgsProject.instance().layerTreeRoot().findLayer(cons.id())
        except (LookupError, RuntimeError):
            self.banda.reset(Qgis.GeometryType.Line)
            return
        self.banda.reset(Qgis.GeometryType.Line)
        if no_arvore is not None and not no_arvore.isVisible():
            return
        alvos = {}
        for f in cons.getFeatures():
            if f.hasGeometry() and f["ligado_a"] not in (None, "") and str(f["ligado_a"]) != "NULL":
                alvos.setdefault((str(f["tipo_ligacao"]) == "TRECHO", str(f["ligado_a"])), []).append(f.geometry())
        if not alvos:
            return
        pos = {}
        for f in nos.getFeatures():
            if f.hasGeometry() and (False, str(f["id"])) in alvos:
                pos[(False, str(f["id"]))] = f.geometry().centroid().asPoint()
        for f in tr.getFeatures():
            if f.hasGeometry() and (True, str(f["id"])) in alvos:
                g = f.geometry()
                pos[(True, str(f["id"]))] = g.interpolate(g.length() / 2).asPoint()
        crs = cons.crs()
        linhas = [[QgsPointXY(g.centroid().asPoint()), QgsPointXY(pos[k])]
                  for k, gs in alvos.items() if k in pos for g in gs]
        if linhas:
            self.banda.setToGeometry(QgsGeometry.fromMultiPolylineXY(linhas), crs)


def mais_perto(nucleo, ponto):
    """(id, 'NO' | 'TRECHO') do nó de junção ou do meio de tubulação mais perto do ponto (QgsPointXY)."""
    melhor = (math.inf, None, None)
    caixa = None
    for raio in (50, 250, 1000, 5000, None):  # procura perto primeiro: cadastros grandes têm milhares de elementos
        req = QgsFeatureRequest()
        if raio is not None:
            from qgis.core import QgsRectangle
            caixa = QgsRectangle(ponto.x() - raio, ponto.y() - raio, ponto.x() + raio, ponto.y() + raio)
            req.setFilterRect(caixa)
        for f in nucleo.camada("no_juncao").getFeatures(req):
            if f.hasGeometry() and f["id"]:
                d = f.geometry().asPoint().distance(ponto) if not f.geometry().isMultipart() else \
                    f.geometry().distance(f.geometry().fromPointXY(ponto))
                melhor = min(melhor, (d, str(f["id"]), "NO"))
        for f in nucleo.camada("trecho").getFeatures(req):
            if f.hasGeometry() and f["id"]:
                g = f.geometry()
                m = g.interpolate(g.length() / 2)
                if not m.isNull():
                    melhor = min(melhor, (m.asPoint().distance(ponto), str(f["id"]), "TRECHO"))
        if melhor[1] is not None and (raio is None or melhor[0] <= raio):
            break
    return melhor[1], melhor[2]


def ligar(nucleo, lyr, fids=None, so_vazios=True):
    """Liga consumidores ao elemento mais perto. Devolve quantos mudaram."""
    if not lyr.isEditable():
        lyr.startEditing()
    i_l, i_t = lyr.fields().indexOf("ligado_a"), lyr.fields().indexOf("tipo_ligacao")
    req = QgsFeatureRequest().setFilterFids(list(fids)) if fids is not None else QgsFeatureRequest()
    n = 0
    for f in list(lyr.getFeatures(req)):
        if not f.hasGeometry() or (so_vazios and f["ligado_a"] not in (None, "") and str(f["ligado_a"]) != "NULL"):
            continue
        g = f.geometry()
        alvo, tipo = mais_perto(nucleo, g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0])
        if alvo:
            lyr.changeAttributeValue(f.id(), i_l, alvo)
            lyr.changeAttributeValue(f.id(), i_t, tipo)
            n += 1
    lyr.triggerRepaint()
    return n


def _ao_adicionar(nucleo, lyr, fid):
    try:
        if lyr.getFeature(fid).isValid():
            ligar(nucleo, lyr, [fid])
    except (RuntimeError, LookupError):
        pass


def acao_ligar_consumidores(nucleo):
    """Religa ao mais perto os consumidores selecionados (ou todos, sem seleção)."""
    lyr = garantir(nucleo)
    if lyr is None:
        nucleo.aviso("Abra um cadastro primeiro.")
        return
    sel = list(lyr.selectedFeatureIds())
    n = ligar(nucleo, lyr, sel or None, so_vazios=False)
    nucleo.informar(f"{n} consumidor(es) ligado(s) ao nó ou à tubulação mais perto. Salve as edições para gravar.")


ACOES = {"ligar_consumidores": acao_ligar_consumidores}
