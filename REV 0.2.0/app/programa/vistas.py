"""Exibir: zoom, vistas com nome, vista aérea, simbologia, mapa de fundo, rótulos e o menu das camadas."""
from qgis.core import QgsProject, QgsRasterLayer, QgsRectangle, QgsStyle, QgsVectorLayer
from qgis.gui import QgsLayerTreeViewMenuProvider, QgsMapOverviewCanvas, QgsRendererPropertiesDialog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QDockWidget, QFileDialog, QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem,
    QMenu, QPushButton, QVBoxLayout,
)

from .tema import icone
from .util import Dialogo

ESRI = "type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}&zmax={}&zmin=0"
FUNDOS = {  # nome -> (endereço das imagens, cor do fundo do mapa que combina)
    # a CARTO passou a pedir chave de acesso: claro e escuro são os mapas cinza da Esri (livres)
    "Claro (Esri Light Gray)": (ESRI.format("Canvas/World_Light_Gray_Base", 16), "#f4f7fb"),
    "Escuro (Esri Dark Gray)": (ESRI.format("Canvas/World_Dark_Gray_Base", 16), "#0e1626"),
    "Terreno (relevo sombreado)": (ESRI.format("World_Topo_Map", 19), "#f4f7fb"),
    "Relevo puro (Esri Hillshade)": (ESRI.format("Elevation/World_Hillshade", 16), "#f4f7fb"),
    "Satélite (Esri World Imagery)": (ESRI.format("World_Imagery", 19), "#1b1b1b"),
    "OpenStreetMap": ("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0", "#f4f7fb"),
}


def zoom_total(nucleo):
    nucleo.janela.zoom_total()


def zoom_anterior(nucleo):
    nucleo.janela.canvas.zoomToPreviousExtent()


def zoom_proximo(nucleo):
    nucleo.janela.canvas.zoomToNextExtent()


def zoom_selecao(nucleo):
    janela = nucleo.janela
    ext = QgsRectangle()
    for lyr, _ in janela.selecionados():
        ext.combineExtentWith(janela.canvas.mapSettings().layerExtentToOutputExtent(lyr, lyr.boundingBoxOfSelected()))
    if ext.isEmpty() and ext.width() == 0 and ext.height() == 0 and not janela.selecionados():
        return nucleo.informar("Nada selecionado.")
    ext.grow(max(ext.width(), ext.height()) * 0.1 + 30)
    janela.canvas.setExtent(ext)
    janela.canvas.refresh()


def atualizar(nucleo):
    janela = nucleo.janela
    for lyr in QgsProject.instance().mapLayers().values():
        lyr.triggerRepaint()
    janela.canvas.refreshAllLayers()
    if nucleo.res:
        nucleo.res.estilizar()
    janela.dock_prop.atualizar()


# ---------------------------------------------------------------- vistas com nome
def vistas_nomeadas(nucleo):
    janela = nucleo.janela
    if not nucleo.cadastro():
        return
    vistas = janela._ler_json("vistas", {})
    d = Dialogo(janela, "Vistas com nome", "Guarde o enquadramento atual do mapa com um nome. Clique duplo volta para ele.")
    lista = QListWidget()
    lista.setMinimumHeight(220)
    d.lay.addWidget(lista)

    def recarregar():
        lista.clear()
        for nome in sorted(vistas):
            it = QListWidgetItem(icone("vistas"), nome)
            lista.addItem(it)

    def guardar():
        nome, ok = QInputDialog.getText(janela, "Nova vista", "Nome da vista:")
        if ok and nome.strip():
            e = janela.canvas.extent()
            vistas[nome.strip()] = [e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum()]
            janela.gravar_json("vistas", vistas)
            recarregar()

    def ir(it=None):
        it = it or lista.currentItem()
        if it:
            janela.canvas.setExtent(QgsRectangle(*vistas[it.text()]))
            janela.canvas.refresh()

    def apagar():
        it = lista.currentItem()
        if it:
            vistas.pop(it.text(), None)
            janela.gravar_json("vistas", vistas)
            recarregar()

    h = QHBoxLayout()
    for texto, f in (("Guardar a vista atual", guardar), ("Ir para", ir), ("Apagar", apagar)):
        b = QPushButton(texto)
        b.clicked.connect(f)
        h.addWidget(b)
    d.lay.addLayout(h)
    lista.itemDoubleClicked.connect(ir)
    recarregar()
    d.botoes(None, "Fechar")
    d.exec()


def vista_aerea(nucleo):
    janela = nucleo.janela
    dock = getattr(janela, "dock_aerea", None)
    if dock is None:
        dock = QDockWidget("Vista aérea", janela)
        dock.setObjectName("GwaterVistaAerea")
        ov = QgsMapOverviewCanvas(dock, janela.canvas)
        ov.setBackgroundColor(QColor("#f4f7fb"))
        ov.setMinimumSize(220, 180)
        dock.setWidget(ov)
        janela.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        janela.dock_aerea = dock
        janela.vista_aerea = ov

        def camadas():
            ov.setLayers([l for l in nucleo.camadas_rede()])
            ov.refresh()
        camadas()
        janela.projeto.connect(camadas)
        janela.canvas.extentsChanged.connect(ov.drawExtentRect)
    else:
        dock.setVisible(not dock.isVisible())


# ---------------------------------------------------------------- simbologia e fundo
def simbologia(nucleo, lyr=None):
    janela = nucleo.janela
    lyr = lyr or janela.arvore.currentLayer() or janela.iface.activeLayer()
    if not isinstance(lyr, QgsVectorLayer):
        return nucleo.informar("Escolha uma camada de elementos no painel Simbologia dos elementos.")
    if lyr in nucleo.camadas_rede():  # camada do cadastro: o editor do GWATER, por tipo de elemento
        from .simbologia import TIPOS, editar_tipo
        tipos = [t for t in TIPOS if nucleo.camada(t[2]) == lyr]
        m = QMenu(janela)
        for t in tipos:
            m.addAction(icone(t[5]), t[1]).triggered.connect(
                lambda _=False, tt=t: editar_tipo(janela, tt, lyr) and janela.dock_arvore.projeto_aberto())
        return m.exec(janela.cursor().pos())
    dlg = QDialog(janela)
    dlg.setWindowTitle(f"GWATER · Simbologia · {lyr.name()}")
    dlg.resize(760, 620)
    v = QVBoxLayout(dlg)
    w = QgsRendererPropertiesDialog(lyr, QgsStyle.defaultStyle(), False, dlg)
    w.setMapCanvas(janela.canvas)
    v.addWidget(w)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply |
                          QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Apply).setText("Aplicar")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
    v.addWidget(bb)

    def aplicar():
        w.apply()
        lyr.triggerRepaint()
        janela.arvore.refreshLayerSymbology(lyr.id())
    bb.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(aplicar)
    bb.accepted.connect(lambda: (aplicar(), dlg.accept()))
    bb.rejected.connect(dlg.reject)
    dlg.exec()


def fundos(nucleo):
    janela = nucleo.janela
    m = QMenu(janela)
    for nome in FUNDOS:
        m.addAction(icone("fundos"), nome).triggered.connect(lambda _=False, n=nome: trocar_fundo(nucleo, n))
    m.addSeparator()
    m.addAction(icone("abrir"), "Arquivo (raster, shapefile, GeoPackage)…").triggered.connect(lambda: _fundo_arquivo(nucleo))
    m.addAction(icone("excluir"), "Sem mapa de fundo").triggered.connect(lambda: _tirar_fundos(nucleo))
    m.exec(janela.cursor().pos())


def _grupo_fundo():
    raiz = QgsProject.instance().layerTreeRoot()
    g = raiz.findGroup("Mapa de fundo")
    return g or raiz.addGroup("Mapa de fundo")


def trocar_fundo(nucleo, nome):
    """Troca o mapa de fundo (um só por vez, sempre embaixo da rede) e guarda a escolha no projeto."""
    uri, cor = FUNDOS[nome]
    lyr = QgsRasterLayer(uri, nome, "wms")
    if not lyr.isValid():
        return nucleo.aviso(f"Não consegui carregar {nome} (precisa de internet).")
    _tirar_fundos(nucleo)
    QgsProject.instance().addMapLayer(lyr, False)
    raiz = QgsProject.instance().layerTreeRoot()
    g = raiz.addGroup("Mapa de fundo")  # addGroup põe no fim da árvore: desenhado por baixo de tudo
    g.addLayer(lyr)
    nucleo.janela.canvas.setCanvasColor(QColor(cor))
    QgsProject.instance().writeEntry("GWATER", "fundo", nome)
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"Mapa de fundo: {nome}.")


def _fundo_arquivo(nucleo):
    arq, _ = QFileDialog.getOpenFileName(nucleo.janela, "Mapa de fundo", nucleo.janela.pasta_padrao(),
                                         "Mapas (*.tif *.tiff *.ecw *.jp2 *.png *.jpg *.shp *.gpkg *.geojson *.kml *.dxf);;"
                                         "Todos (*.*)")
    if not arq:
        return
    nome = arq.replace("\\", "/").split("/")[-1]
    lyr = QgsRasterLayer(arq, nome)
    if not lyr.isValid():
        lyr = QgsVectorLayer(arq, nome, "ogr")
    if not lyr.isValid():
        return nucleo.aviso(f"Não consegui abrir {nome}.")
    QgsProject.instance().addMapLayer(lyr, False)
    _grupo_fundo().addLayer(lyr)
    nucleo.janela.canvas.refresh()


def _tirar_fundos(nucleo):
    prj = QgsProject.instance()
    g = prj.layerTreeRoot().findGroup("Mapa de fundo")
    if g:
        prj.removeMapLayers([n.layerId() for n in g.findLayers()])
        g.parent().removeChildNode(g)
    # o mapa de fundo que vem no projeto do cadastro (OpenStreetMap, fora do grupo)
    prj.removeMapLayers([l.id() for l in prj.mapLayers().values()
                         if isinstance(l, QgsRasterLayer) and l.providerType() == "wms" and "type=xyz" in l.source()])
    nucleo.janela.canvas.setCanvasColor(QColor("#f4f7fb"))
    nucleo.janela.canvas.refresh()


def rotulos(nucleo):
    camadas = nucleo.camadas_rede()
    if not camadas:
        return
    ligar = not any(l.labelsEnabled() for l in camadas)
    for l in camadas:
        if l.labeling() is None and ligar:
            from qgis.core import QgsPalLayerSettings, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
            s = QgsPalLayerSettings()
            s.fieldName = "id"
            fmt = QgsTextFormat()
            fmt.setSize(7.5)
            buf = QgsTextBufferSettings()
            buf.setEnabled(True)
            fmt.setBuffer(buf)
            s.setFormat(fmt)
            l.setLabeling(QgsVectorLayerSimpleLabeling(s))
        l.setLabelsEnabled(ligar)
        l.triggerRepaint()
    nucleo.informar("Rótulos " + ("ligados." if ligar else "desligados."))


ROTULOS_NOS = [("", "Nenhum"), ("p", "Pressão (mca)")]
ROTULOS_TUBOS = [("", "Nenhum"), ("q", "Vazão (L/s)"), ("v", "Velocidade (m/s)"), ("perda_m_km", "Perda de carga (m/km)"),
                 ("dn", "Diâmetro (mm)")]


def rotulos_resultados(nucleo, no=None, tubo=None, casas=None):
    """Valores do cálculo escritos no mapa, na hora da linha do tempo (Annotation do WaterGEMS)."""
    res = nucleo.res
    if not res:
        return nucleo.aviso("Calcule a rede primeiro (F5).")
    if no is None:
        from qgis.PyQt.QtWidgets import QComboBox, QSpinBox
        from .util import Dialogo
        d = Dialogo(nucleo.janela, "Rótulos de resultados",
                    "Escreve no mapa o valor calculado de cada elemento na hora escolhida na linha do tempo, como as "
                    "anotações do WaterGEMS. Os rótulos acompanham a hora quando ela muda.")
        cn, ct = QComboBox(), QComboBox()
        for k, t in ROTULOS_NOS:
            cn.addItem(t, k)
        for k, t in ROTULOS_TUBOS:
            ct.addItem(t, k)
        cn.setCurrentIndex(1)
        cd = QSpinBox()
        cd.setRange(0, 4)
        cd.setValue(1)
        d.linha("Nós:", cn)
        d.linha("Tubulações:", ct)
        d.linha("Casas decimais:", cd)
        d.botoes("Aplicar")
        if not d.exec():
            return
        no, tubo, casas = cn.currentData(), ct.currentData(), cd.value()
    from gwater.resultados import _rotulo
    casas = 1 if casas is None else casas
    for lyr, campo in ((res.nos, no), (res.tr, tubo)):
        if campo:
            un = {"p": "", "q": "", "v": "", "perda_m_km": "", "dn": ""}[campo]
            _rotulo(lyr, f'format_number({"abs(" if campo == "q" else ""}"{campo}"{")" if campo == "q" else ""}, '
                         f'{casas}){un}')
        else:
            lyr.setLabelsEnabled(False)
        lyr.triggerRepaint()
    nucleo.informar("Rótulos de resultados aplicados.")


# ---------------------------------------------------------------- menu do painel de camadas
class MenuArvore(QgsLayerTreeViewMenuProvider):
    def __init__(self, arvore, janela):
        super().__init__()
        self.arvore, self.janela = arvore, janela

    def createContextMenu(self):
        lyr = self.arvore.currentLayer()
        m = QMenu()
        if lyr is None:
            return m
        j = self.janela
        m.addAction(icone("zoom_total"), "Zoom na camada").triggered.connect(lambda: _zoom_camada(j, lyr))
        if isinstance(lyr, QgsVectorLayer):
            m.addAction(icone("tabelas"), "Abrir tabela").triggered.connect(lambda: _tabela(j, lyr))
            m.addAction(icone("simbologia"), "Simbologia…").triggered.connect(lambda: simbologia(j.nucleo, lyr))
            m.addAction(icone("rotulos"), "Mostrar / esconder rótulos").triggered.connect(
                lambda: (lyr.setLabelsEnabled(not lyr.labelsEnabled()), lyr.triggerRepaint()))
        if lyr not in j.nucleo.camadas_rede():
            m.addSeparator()
            m.addAction(icone("excluir"), "Tirar do mapa").triggered.connect(
                lambda: QgsProject.instance().removeMapLayer(lyr.id()))
        return m


def _zoom_camada(janela, lyr):
    e = janela.canvas.mapSettings().layerExtentToOutputExtent(lyr, lyr.extent())
    e.grow(max(e.width(), e.height()) * 0.05 + 10)
    janela.canvas.setExtent(e)
    janela.canvas.refresh()


def _tabela(janela, lyr):
    from .tabelas import abrir_tabela
    abrir_tabela(janela.nucleo, lyr)


ACOES = {"rotulos_resultados": rotulos_resultados, "zoom_total": zoom_total, "zoom_anterior": zoom_anterior, "zoom_proximo": zoom_proximo,
         "zoom_selecao": zoom_selecao, "atualizar": atualizar, "vistas_nomeadas": vistas_nomeadas,
         "vista_aerea": vista_aerea, "simbologia": simbologia, "fundos": fundos, "rotulos": rotulos,
         "painel_simbologia": lambda n: n.janela.alternar_painel("simbologia"),
         "painel_propriedades": lambda n: n.janela.alternar_painel("propriedades"),
         "painel_consultas": lambda n: n.janela.alternar_painel("consultas"),
         "painel_calculo": lambda n: n.janela.alternar_painel("calculo"),
         "propriedades": lambda n: n.janela.mostrar_painel("propriedades"),
         "disposicao": lambda n: n.janela.faixa.ir_para("desenho")}
