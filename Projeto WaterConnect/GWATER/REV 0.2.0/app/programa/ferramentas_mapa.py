"""Ferramentas de mapa do GWATER.exe: selecionar, desenhar, mover, medir, clicar num elemento, anotar.

No QGIS essas ferramentas vêm do próprio aplicativo; fora dele, o GWATER tem as suas, montadas com as
peças públicas do QGIS (QgsMapTool, QgsRubberBand, QgsMapToolDigitizeFeature, QgsSnapIndicator).
"""
from qgis.core import (
    Qgis, QgsDistanceArea, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle, QgsUnitTypes,
    QgsVectorLayer, QgsVectorLayerUtils, QgsWkbTypes,
)
from qgis.gui import (
    QgsAttributeDialog, QgsAttributeEditorContext, QgsMapTool, QgsMapToolCapture, QgsMapToolDigitizeFeature,
    QgsRubberBand, QgsSnapIndicator,
)
from qgis.PyQt.QtCore import QPoint, QRect, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor
from qgis.PyQt.QtWidgets import QApplication

TOL_PX = 7  # tolerância de clique, em pixels
COR_SEL = QColor(255, 181, 71, 220)


def _geom_tipo(lyr):
    return QgsWkbTypes.geometryType(lyr.wkbType())


def eh_ponto(lyr):
    return _geom_tipo(lyr) == QgsWkbTypes.GeometryType.PointGeometry


def elemento_em(canvas, camadas, ponto_tela, tol_px=TOL_PX):
    """(camada, feição) mais próxima do clique; pontos têm preferência sobre linhas, como no WaterGEMS."""
    mp = canvas.getCoordinateTransform().toMapCoordinates(ponto_tela)
    tol = tol_px * canvas.mapSettings().mapUnitsPerPixel()
    melhor = (None, None, 1e99, 9)
    for lyr in camadas:
        if lyr is None or not lyr.isSpatial():
            continue
        try:
            p_lyr = canvas.mapSettings().mapToLayerCoordinates(lyr, mp)
            r = canvas.mapSettings().mapToLayerCoordinates(lyr, QgsRectangle(mp.x() - tol, mp.y() - tol,
                                                                             mp.x() + tol, mp.y() + tol))
        except Exception:
            continue
        gp = QgsGeometry.fromPointXY(QgsPointXY(p_lyr))
        prioridade = 0 if eh_ponto(lyr) else 1
        for f in lyr.getFeatures(QgsFeatureRequest().setFilterRect(r).setNoAttributes()):
            if not f.hasGeometry():
                continue
            d = f.geometry().distance(gp)
            if d <= tol * 1.5 and (prioridade, d) < (melhor[3], melhor[2]):
                melhor = (lyr, f.id(), d, prioridade)
    return (melhor[0], melhor[1]) if melhor[0] else (None, None)


# ================================================================ seleção
class FerramentaSelecao(QgsMapTool):
    """Clique seleciona um elemento; arrastar faz uma janela. Shift soma, Ctrl tira. Clique no vazio limpa."""
    selecionou = pyqtSignal()

    def __init__(self, canvas, camadas):
        super().__init__(canvas)
        self.camadas = camadas  # função que devolve as camadas selecionáveis
        self.inicio = None
        self.banda = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.banda.setColor(QColor(53, 208, 255, 50))
        self.banda.setStrokeColor(QColor(53, 208, 255, 220))
        self.banda.setWidth(1)
        self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.inicio = e.pos()

    def canvasMoveEvent(self, e):
        if self.inicio is None or (e.pos() - self.inicio).manhattanLength() < 4:
            return
        r = QRect(self.inicio, e.pos()).normalized()
        t = self.canvas().getCoordinateTransform()
        a, b = t.toMapCoordinates(r.topLeft()), t.toMapCoordinates(r.bottomRight())
        self.banda.setToGeometry(QgsGeometry.fromRect(QgsRectangle(a, b)), None)

    def canvasReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.inicio is None:
            return
        mod = e.modifiers()
        modo = (Qgis.SelectBehavior.AddToSelection if mod & Qt.KeyboardModifier.ShiftModifier else
                Qgis.SelectBehavior.RemoveFromSelection if mod & Qt.KeyboardModifier.ControlModifier else
                Qgis.SelectBehavior.SetSelection)
        if (e.pos() - self.inicio).manhattanLength() >= 4:
            r = QRect(self.inicio, e.pos()).normalized()
            t = self.canvas().getCoordinateTransform()
            geom = QgsGeometry.fromRect(QgsRectangle(t.toMapCoordinates(r.topLeft()),
                                                     t.toMapCoordinates(r.bottomRight())))
            selecionar_por_geometria(self.canvas(), self.camadas(), geom, modo)
        else:
            lyr, fid = elemento_em(self.canvas(), self.camadas(), e.pos())
            if modo == Qgis.SelectBehavior.SetSelection:
                for l in self.camadas():
                    if l is not lyr:
                        l.removeSelection()
            if lyr is not None:
                lyr.selectByIds([fid], modo)
            elif modo == Qgis.SelectBehavior.SetSelection:
                for l in self.camadas():
                    l.removeSelection()
        self.inicio = None
        self.banda.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        self.selecionou.emit()

    def deactivate(self):
        self.banda.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
        super().deactivate()


def selecionar_por_geometria(canvas, camadas, geom, modo=None):
    """Seleciona o que intercepta a geometria (no sistema do mapa) em todas as camadas."""
    modo = modo or Qgis.SelectBehavior.SetSelection
    for lyr in camadas:
        g = QgsGeometry(geom)
        if lyr.crs() != canvas.mapSettings().destinationCrs():
            from qgis.core import QgsCoordinateTransform
            g.transform(QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), lyr.crs(), QgsProject.instance()))
        ids = [f.id() for f in lyr.getFeatures(QgsFeatureRequest().setFilterRect(g.boundingBox()).setNoAttributes())
               if f.hasGeometry() and f.geometry().intersects(g)]
        lyr.selectByIds(ids, modo)


class FerramentaPoligono(QgsMapTool):
    """Clique os vértices; clique direito (ou duplo) fecha e chama `concluido(geometria)`."""
    concluido = pyqtSignal(QgsGeometry)

    def __init__(self, canvas, area=True, cor=QColor(53, 208, 255)):
        super().__init__(canvas)
        self.area = area
        tipo = QgsWkbTypes.GeometryType.PolygonGeometry if area else QgsWkbTypes.GeometryType.LineGeometry
        self.tipo = tipo
        self.banda = QgsRubberBand(canvas, tipo)
        c = QColor(cor)
        c.setAlpha(45)
        self.banda.setColor(c if area else cor)
        self.banda.setStrokeColor(cor)
        self.banda.setWidth(2)
        self.pontos = []
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def _mapa(self, e):
        return self.toMapCoordinates(e.pos())

    def canvasMoveEvent(self, e):
        if self.pontos:
            self.banda.setToGeometry(self._geom(self.pontos + [self._mapa(e)]), None)
            self.movendo(self.pontos + [self._mapa(e)])

    def movendo(self, pts):
        pass

    def _geom(self, pts):
        if self.area and len(pts) >= 3:
            return QgsGeometry.fromPolygonXY([[QgsPointXY(p) for p in pts]])
        return QgsGeometry.fromPolylineXY([QgsPointXY(p) for p in pts])

    def canvasReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.pontos.append(self._mapa(e))
        elif e.button() == Qt.MouseButton.RightButton:
            self.terminar()

    def canvasDoubleClickEvent(self, e):
        self.terminar()

    def terminar(self):
        minimo = 3 if self.area else 2
        if len(self.pontos) >= minimo:
            self.concluido.emit(self._geom(self.pontos))
        self.pontos = []
        self.banda.reset(self.tipo)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.pontos = []
            self.banda.reset(self.tipo)
        elif e.key() == Qt.Key.Key_Backspace and self.pontos:
            self.pontos.pop()

    def deactivate(self):
        self.pontos = []
        self.banda.reset(self.tipo)
        super().deactivate()


class FerramentaMedir(FerramentaPoligono):
    """Mede comprimento (linha) ou área (polígono) e mostra pela função `mostrar(texto)`."""

    def __init__(self, canvas, area, mostrar):
        super().__init__(canvas, area, QColor(255, 181, 71))
        self.mostrar = mostrar
        self.da = QgsDistanceArea()
        self.da.setSourceCrs(canvas.mapSettings().destinationCrs(), QgsProject.instance().transformContext())
        self.da.setEllipsoid(QgsProject.instance().ellipsoid() or "EPSG:7019")
        self.concluido.connect(lambda g: self.mostrar(self._texto(g), True))

    def _texto(self, g):
        if self.area:
            a = self.da.measureArea(g)
            a = self.da.convertAreaMeasurement(a, Qgis.AreaUnit.SquareMeters)
            return f"Área: {a:,.1f} m² ({a / 10000:,.3f} ha)".replace(",", "X").replace(".", ",").replace("X", ".")
        L = self.da.measureLength(g)
        L = self.da.convertLengthMeasurement(L, Qgis.DistanceUnit.Meters)
        return f"Comprimento: {L:,.2f} m".replace(",", "X").replace(".", ",").replace("X", ".")

    def movendo(self, pts):
        self.mostrar(self._texto(self._geom(pts)), False)


# ================================================================ clique num elemento
class FerramentaClique(QgsMapTool):
    """Clique num elemento: chama `ao_clicar(camada, fid, ponto_mapa)` (camada None = clique no vazio)."""

    def __init__(self, canvas, camadas, ao_clicar, cursor=Qt.CursorShape.PointingHandCursor):
        super().__init__(canvas)
        self.camadas, self.ao_clicar = camadas, ao_clicar
        self.setCursor(QCursor(cursor))

    def canvasReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            lyr, fid = elemento_em(self.canvas(), self.camadas(), e.pos())
            self.ao_clicar(lyr, fid, self.toMapCoordinates(e.pos()))


# ================================================================ mover elemento ou vértice
class FerramentaMover(QgsMapTool):
    """Arraste um elemento pontual (as tubulações ligadas acompanham, pela Topologia) ou um vértice de
    tubulação. Encaixa nos outros elementos (snapping)."""

    def __init__(self, canvas, camadas, aviso):
        super().__init__(canvas)
        self.camadas, self.aviso = camadas, aviso
        self.alvo = None  # (camada, fid, índice do vértice ou None)
        self.banda = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self.banda.setColor(QColor(255, 181, 71))
        self.banda.setWidth(2)
        self.indicador = QgsSnapIndicator(canvas)
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))

    def _ponto(self, e):
        m = self.canvas().snappingUtils().snapToMap(e.pos())
        self.indicador.setMatch(m)
        return QgsPointXY(m.point()) if m.isValid() else self.toMapCoordinates(e.pos())

    def canvasPressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        lyr, fid = elemento_em(self.canvas(), self.camadas(), e.pos())
        if lyr is None:
            return
        if not lyr.isEditable():
            lyr.startEditing()
        if eh_ponto(lyr):
            self.alvo = (lyr, fid, None)
        else:
            g = lyr.getFeature(fid).geometry()
            mp = self.canvas().mapSettings().mapToLayerCoordinates(lyr, self.toMapCoordinates(e.pos()))
            _, idx, _, _, d2 = g.closestVertex(QgsPointXY(mp))
            tol = TOL_PX * 1.5 * self.canvas().mapSettings().mapUnitsPerPixel()
            if idx < 0 or d2 > tol * tol:
                self.aviso("Clique num vértice da tubulação para movê-lo (as pontas acompanham os nós).")
                return
            self.alvo = (lyr, fid, idx)

    def canvasMoveEvent(self, e):
        p = self._ponto(e)
        if self.alvo:
            lyr, fid, idx = self.alvo
            g = lyr.getFeature(fid).geometry()
            if idx is None:
                o = self.canvas().mapSettings().layerToMapCoordinates(lyr, g.asPoint())
                self.banda.setToGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(o), p]), None)
            else:
                pts = [self.canvas().mapSettings().layerToMapCoordinates(lyr, QgsPointXY(v)) for v in g.vertices()]
                pts[idx] = p
                self.banda.setToGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x) for x in pts]), None)

    def canvasReleaseEvent(self, e):
        if not self.alvo or e.button() != Qt.MouseButton.LeftButton:
            return
        lyr, fid, idx = self.alvo
        self.alvo = None
        self.banda.reset(QgsWkbTypes.GeometryType.LineGeometry)
        p = self.canvas().mapSettings().mapToLayerCoordinates(lyr, self._ponto(e))
        lyr.beginEditCommand("Mover")
        if idx is None:
            lyr.changeGeometry(fid, QgsGeometry.fromPointXY(QgsPointXY(p)))
        else:
            lyr.moveVertex(p.x(), p.y(), fid, idx)
        lyr.endEditCommand()
        self.canvas().refresh()

    def deactivate(self):
        self.banda.reset(QgsWkbTypes.GeometryType.LineGeometry)
        self.indicador.setMatch(type(self.canvas().snappingUtils().snapToMap(QPoint(0, 0)))())
        super().deactivate()


# ================================================================ desenho
def _formulario_suprimido(lyr):
    s = lyr.editFormConfig().suppress()
    return getattr(s, "name", str(s)).endswith("On") or str(s).endswith("SuppressOn")


class FerramentaDesenho(QgsMapToolDigitizeFeature):
    """Desenha na camada (ponto ou linha) com encaixe; abre o formulário, a não ser que o protótipo o
    dispense. A Topologia do GWATER faz o resto (nós nas pontas, divisões) ao receber a feição."""

    def __init__(self, canvas, cad, camada, pai=None, depois=None):
        modo = QgsMapToolCapture.CaptureMode.CapturePoint if eh_ponto(camada) else \
            QgsMapToolCapture.CaptureMode.CaptureLine
        super().__init__(canvas, cad, modo)
        self.camada, self.pai, self.depois = camada, pai, depois
        self.setLayer(camada)
        self.digitizingCompleted.connect(self._concluido)

    def _concluido(self, f):
        lyr = self.camada
        if not lyr.isEditable():
            lyr.startEditing()
        nova = QgsVectorLayerUtils.createFeature(lyr, f.geometry(), {}, lyr.createExpressionContext())
        if _formulario_suprimido(lyr):
            lyr.beginEditCommand("Desenhar")
            ok = lyr.addFeature(nova)
            lyr.endEditCommand()
        else:
            dlg = QgsAttributeDialog(lyr, nova, False, self.pai, True)
            dlg.setMode(QgsAttributeEditorContext.Mode.AddFeatureMode)
            dlg.setWindowTitle(f"Novo elemento · {lyr.name()}")
            ok = bool(dlg.exec())
        self.canvas().refresh()
        if self.depois:
            self.depois(ok)


# ================================================================ anotações (texto, linha, borda)
def anotar(tipo, geom, texto=None):
    """Item na camada de anotações do projeto (fica salva no .qgz)."""
    from qgis.core import (
        QgsAnnotationLineItem, QgsAnnotationPointTextItem, QgsAnnotationPolygonItem, QgsCurvePolygon, QgsLineString,
        QgsPoint, QgsTextFormat,
    )
    camada = QgsProject.instance().mainAnnotationLayer()
    if tipo == "texto":
        p = geom.asPoint()
        item = QgsAnnotationPointTextItem(texto or "", QgsPointXY(p))
        fmt = QgsTextFormat()
        fmt.setSize(11)
        fmt.setColor(QColor("#0d2650"))
        item.setFormat(fmt)
    elif tipo == "linha":
        item = QgsAnnotationLineItem(QgsLineString([QgsPoint(v.x(), v.y()) for v in geom.vertices()]))
    else:
        anel = QgsLineString([QgsPoint(v.x(), v.y()) for v in geom.vertices()])
        pol = QgsCurvePolygon()
        pol.setExteriorRing(anel)
        item = QgsAnnotationPolygonItem(pol)
    camada.addItem(item)
    camada.triggerRepaint()
    return item


class FerramentaRetangulo(QgsMapTool):
    """Arraste um retângulo: `concluido(geometria)`."""
    concluido = pyqtSignal(QgsGeometry)

    def __init__(self, canvas):
        super().__init__(canvas)
        self.inicio = None
        self.banda = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self.banda.setColor(QColor(13, 38, 80, 40))
        self.banda.setStrokeColor(QColor(13, 38, 80))
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def canvasPressEvent(self, e):
        self.inicio = self.toMapCoordinates(e.pos())

    def canvasMoveEvent(self, e):
        if self.inicio:
            self.banda.setToGeometry(QgsGeometry.fromRect(QgsRectangle(self.inicio, self.toMapCoordinates(e.pos()))), None)

    def canvasReleaseEvent(self, e):
        if self.inicio:
            r = QgsRectangle(self.inicio, self.toMapCoordinates(e.pos()))
            self.inicio = None
            self.banda.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            if r.width() > 0 and r.height() > 0:
                self.concluido.emit(QgsGeometry.fromRect(r))
