"""Janela principal do GWATER.exe.

  faixa de menus (ribbon) ........ programa/faixa.py, catálogo em programa/catalogo.py
  centro .......................... abas: Início (sem cadastro aberto) ou Mapa, e as telas do Centro de
                                    Operações abertas dentro do programa
  painéis ......................... Simbologia dos elementos (esquerda), Propriedades e Consultas
                                    (direita), Cálculo (embaixo: notificações e linha do tempo)
  barra de status ................. coordenadas, escala, sistema, seleção, edição e hora do resultado
"""
import os
import zipfile

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsLayerTreeModel, QgsProject, QgsRectangle, QgsVectorLayer,
)
from qgis.gui import (
    QgsAdvancedDigitizingDockWidget, QgsLayerTreeMapCanvasBridge, QgsLayerTreeView, QgsMapCanvas,
    QgsMapCanvasSnappingUtils, QgsMapToolPan, QgsMapToolZoom, QgsMessageBar,
)
from qgis.PyQt.QtCore import QSettings, QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QKeySequence
from qgis.PyQt.QtWidgets import (
    QApplication, QComboBox, QDockWidget, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSlider, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

try:
    from qgis.PyQt.QtGui import QAction, QShortcut
except ImportError:
    from qgis.PyQt.QtWidgets import QAction, QShortcut

from . import ferramentas_mapa as fm
from .faixa import Faixa
from .nucleo import Iface, Nucleo
from .tema import icone

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # REV 0.2.0
CHAVE = "GWATER"
CONFIG = QSettings("GWATER", "GWATER")
# ferramentas de mapa da janela (não são ações do núcleo, mas respondem ao clique na faixa)
FERRAMENTAS_MAPA = {"selecionar", "pan", "zoom_mais", "zoom_menos", "mover", "sel_poligono", "medir_comprimento",
                    "medir_area"}


class Janela(QMainWindow):
    resultados = pyqtSignal()     # rodou ou limpou um cálculo
    selecao = pyqtSignal()        # a seleção mudou em alguma camada do cadastro
    projeto = pyqtSignal()        # abriu ou fechou um cadastro

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GWATER")
        self.setWindowIcon(icone("gwater"))
        self.resize(1500, 900)
        self.setDockOptions(QMainWindow.DockOption.AllowTabbedDocks | QMainWindow.DockOption.AnimatedDocks)
        self.iface = Iface(self)
        self.prototipos_tipo = {}
        self.ferramenta_atual = None
        self._pilha_desfazer, self._pilha_refazer = [], []
        self._conectadas = set()
        self.web = {}

        # ---- mapa
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QColor("#f4f7fb"))
        self.canvas.enableAntiAliasing(True)
        from . import desempenho
        desempenho.aplicar(self)  # núcleos, cache de memória e desenho do mapa em paralelo (Configurações)
        prj = QgsProject.instance()
        self.ponte = QgsLayerTreeMapCanvasBridge(prj.layerTreeRoot(), self.canvas)
        self.encaixe = QgsMapCanvasSnappingUtils(self.canvas)
        self.canvas.setSnappingUtils(self.encaixe)
        prj.snappingConfigChanged.connect(self.encaixe.setConfig)
        # tipos de campo dos formulários (texto, lista de valores, data...): o QGIS registra ao abrir; aqui é preciso
        # registrar, senão o formulário mostra "Failed to create widget"
        from qgis.gui import QgsGui
        if not QgsGui.editorWidgetRegistry().factories():
            QgsGui.editorWidgetRegistry().initEditors(self.canvas)
        self.cad = QgsAdvancedDigitizingDockWidget(self.canvas)
        self.cad.hide()

        # ---- núcleo (código do plugin) e faixa de menus
        self.nucleo = Nucleo(self)
        from .nucleo import instalar_acoes
        instalar_acoes()
        self.faixa = Faixa(self, tem_acao=lambda k: k in FERRAMENTAS_MAPA or self.nucleo.tem(k))
        self.faixa.acionado.connect(self.acionar)
        self.setMenuWidget(self.faixa)

        # ---- centro
        self.centro = QTabWidget()
        self.centro.setObjectName("centro")
        self.centro.setTabsClosable(True)
        self.centro.tabCloseRequested.connect(self._fechar_aba)
        self.setCentralWidget(self.centro)
        self.pagina_mapa = self._montar_mapa()
        self.pagina_inicio = self._montar_inicio()
        self.centro.addTab(self.pagina_inicio, icone("gwater"), "Início")
        self.centro.tabBar().setTabButton(0, self.centro.tabBar().ButtonPosition.RightSide, None)

        # ---- painéis
        self.arvore = self._montar_arvore()
        self.nucleo.iniciar()
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.nucleo.dock)
        from .propriedades import PainelPropriedades
        self.dock_prop = PainelPropriedades(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_prop)
        from .consultas import PainelConsultas
        self.dock_consultas = PainelConsultas(self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_consultas)
        self.tabifyDockWidget(self.dock_prop, self.dock_consultas)
        self.dock_prop.raise_()
        QTimer.singleShot(0, self._tamanhos)
        self.nucleo.dock.slider.valueChanged.connect(self._hora_mudou)

        # ---- ferramentas de mapa
        camadas = self.nucleo.camadas_rede
        self.ferramentas = {
            "selecionar": fm.FerramentaSelecao(self.canvas, camadas),
            "pan": QgsMapToolPan(self.canvas),
            "zoom_mais": QgsMapToolZoom(self.canvas, False),
            "zoom_menos": QgsMapToolZoom(self.canvas, True),
            "mover": fm.FerramentaMover(self.canvas, camadas, self.nucleo.aviso),
            "sel_poligono": fm.FerramentaPoligono(self.canvas, True),
            "medir_comprimento": fm.FerramentaMedir(self.canvas, False, self._medida),
            "medir_area": fm.FerramentaMedir(self.canvas, True, self._medida),
        }
        self.ferramentas["selecionar"].selecionou.connect(self._selecao_mudou)
        self.ferramentas["sel_poligono"].concluido.connect(
            lambda g: (fm.selecionar_por_geometria(self.canvas, camadas(), g), self._selecao_mudou()))

        self._montar_status()
        self._atalhos()
        prj.readProject.connect(lambda *_: QTimer.singleShot(0, self._projeto_lido))
        prj.cleared.connect(self._projeto_limpo)
        self.canvas.xyCoordinates.connect(self._coordenadas)
        self.canvas.scaleChanged.connect(lambda s: self.st_escala.setText(f"1:{s:,.0f}".replace(",", ".")))
        self.atualizar_recentes()
        self.usar("selecionar")

    def _tamanhos(self):
        self.resizeDocks([self.dock_arvore, self.dock_prop], [250, 340], Qt.Orientation.Horizontal)
        self.resizeDocks([self.nucleo.dock], [190], Qt.Orientation.Vertical)

    # ================================================================ montagem
    def _montar_mapa(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        barra = QFrame()
        barra.setObjectName("faixa")
        barra.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(barra)
        h.setContentsMargins(6, 3, 6, 3)
        h.setSpacing(4)
        h.addWidget(QLabel("Cenário:"))
        self.cmb_cenario = QComboBox()
        self.cmb_cenario.setMinimumWidth(220)
        self.cmb_cenario.setToolTip("Cenário ativo: o que o Calcular e as análises usam (Rede atual = o cadastro "
                                    "como está). Os cenários são criados em Cenários.")
        self.cmb_cenario.activated.connect(self._cenario_escolhido)
        h.addWidget(self.cmb_cenario)
        b = QToolButton()
        b.setIcon(icone("cenarios"))
        b.setToolTip("Gerenciar cenários")
        b.clicked.connect(lambda: self.acionar("cenarios"))
        h.addWidget(b)
        h.addSpacing(10)
        h.addWidget(QLabel("Fundo:"))
        from .vistas import FUNDOS
        self.cmb_fundo = QComboBox()
        self.cmb_fundo.addItem("(do projeto)", None)
        for nome in FUNDOS:
            self.cmb_fundo.addItem(icone("fundos"), nome, nome)
        self.cmb_fundo.addItem("Sem mapa de fundo", "")
        self.cmb_fundo.setToolTip("Mapa de fundo: claro, escuro, terreno, satélite… (precisa de internet)")
        self.cmb_fundo.activated.connect(self._fundo_escolhido)
        h.addWidget(self.cmb_fundo)
        h.addSpacing(10)
        b = QToolButton()
        b.setIcon(icone("opcoes"))
        b.setToolTip("Configurações (tema claro ou escuro)")
        b.clicked.connect(self._configurar)
        h.addWidget(b)
        h.addSpacing(10)
        for chave, ic, dica in (("selecionar", "selecionar", "Selecionar (Esc)"), ("pan", "pan", "Mover o mapa"),
                                ("zoom_mais", "zoom_mais", "Aproximar"), ("zoom_menos", "zoom_menos", "Afastar"),
                                ("zoom_total", "zoom_total", "Zoom total (Ctrl+Shift+F)"),
                                ("zoom_anterior", "zoom_anterior", "Vista anterior"),
                                ("zoom_proximo", "zoom_proximo", "Vista seguinte"),
                                ("zoom_selecao", "zoom_selecao", "Zoom na seleção")):
            b = QToolButton()
            b.setObjectName("rapido")
            b.setIcon(icone(ic))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(dica)
            b.clicked.connect(lambda _=False, k=chave: self.acionar(k))
            h.addWidget(b)
        h.addSpacing(10)
        self.lb_hora = QLabel("Sem resultados")
        self.lb_hora.setMinimumWidth(130)
        h.addWidget(self.lb_hora)
        self.sl_hora = QSlider(Qt.Orientation.Horizontal)
        self.sl_hora.setMaximumWidth(320)
        self.sl_hora.setEnabled(False)
        self.sl_hora.setToolTip("Hora do resultado mostrado no mapa (a mesma da linha do tempo em Tempos)")
        self.sl_hora.valueChanged.connect(lambda k: self.nucleo.dock.slider.setValue(k))
        h.addWidget(self.sl_hora, 1)
        v.addWidget(barra)
        caixa = QWidget()
        g = QGridLayout(caixa)
        g.setContentsMargins(0, 0, 0, 0)
        g.addWidget(self.canvas, 0, 0)
        self.barra_msg = QgsMessageBar(caixa)
        self.barra_msg.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        g.addWidget(self.barra_msg, 0, 0, Qt.AlignmentFlag.AlignTop)
        v.addWidget(caixa, 1)
        return w

    def _montar_inicio(self):
        w = QWidget()
        w.setObjectName("inicio")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(60, 40, 60, 40)
        topo = QHBoxLayout()
        marca = QLabel()
        marca.setPixmap(icone("marca").pixmap(QSize(64, 64)))
        topo.addWidget(marca)
        t = QLabel("<span style='font-size:26pt;font-weight:700'>GWATER</span><br>"
                   "<span style='color:#86a3c9;font-size:11pt'>Cadastro, modelagem hidráulica e operação de redes de "
                   "água · EPANET 2.2</span>")
        topo.addWidget(t, 1)
        lay.addLayout(topo)
        lay.addSpacing(24)
        corpo = QHBoxLayout()
        botoes = QVBoxLayout()
        for chave, ic, texto, desc in (
                ("novo", "novo", "Novo cadastro", "Rede vazia para desenhar do zero, em qualquer pasta e sistema UTM"),
                ("abrir", "abrir", "Abrir cadastro", "Um projeto GWATER (.qgz) ou um GeoPackage do cadastro"),
                ("importar", "importar", "Novo de shapefile", "Cria o cadastro a partir de um shapefile de rede"),
                ("exemplo", "gwater", "Abrir o exemplo", "Sistema de exemplo: captação, recalque, reservatório e VRPs")):
            b = QPushButton(icone(ic), f"  {texto}")
            b.setIconSize(QSize(26, 26))
            b.setMinimumHeight(52)
            b.setToolTip(desc)
            b.setStyleSheet("text-align:left; font-size:11pt; padding-left:14px")
            b.clicked.connect(lambda _=False, k=chave: self.acionar(k))
            botoes.addWidget(b)
            d = QLabel(desc)
            d.setStyleSheet("color:#86a3c9; margin:0 0 10px 6px")
            botoes.addWidget(d)
        botoes.addStretch(1)
        corpo.addLayout(botoes, 1)
        corpo.addSpacing(40)
        rec = QVBoxLayout()
        rec.addWidget(QLabel("<b>Abertos recentemente</b>"))
        self.lista_recentes = QListWidget()
        self.lista_recentes.itemActivated.connect(lambda it: self._abrir_recente(it.data(Qt.ItemDataRole.UserRole)))
        self.lista_recentes.itemDoubleClicked.connect(lambda it: self._abrir_recente(it.data(Qt.ItemDataRole.UserRole)))
        rec.addWidget(self.lista_recentes, 1)
        corpo.addLayout(rec, 2)
        lay.addLayout(corpo, 1)
        return w

    def _montar_arvore(self):
        modelo = QgsLayerTreeModel(QgsProject.instance().layerTreeRoot(), self)
        F = QgsLayerTreeModel.Flag
        modelo.setFlag(F.AllowNodeReorder)
        modelo.setFlag(F.AllowNodeRename)
        modelo.setFlag(F.AllowNodeChangeVisibility)
        modelo.setFlag(F.ShowLegendAsTree)
        modelo.setFlag(F.AllowLegendChangeState)
        arvore = QgsLayerTreeView()
        arvore.setModel(modelo)
        arvore.doubleClicked.connect(lambda _i: self.acionar("simbologia"))
        arvore.currentLayerChanged.connect(lambda l: self.iface.setActiveLayer(l))
        from .vistas import MenuArvore
        arvore.setMenuProvider(MenuArvore(arvore, self))
        from .simbologia import PainelSimbologia
        self.dock_arvore = PainelSimbologia(self, arvore)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_arvore)
        return arvore

    def _montar_status(self):
        sb = self.statusBar()
        self.st_msg = QLabel("")
        sb.addWidget(self.st_msg, 1)
        self.st_sel = QLabel("Nada selecionado")
        self.st_ed = QLabel("")
        self.st_xy = QLabel("X —  Y —")
        self.st_escala = QLabel("1:—")
        self.st_crs = QLabel("—")
        for w in (self.st_sel, self.st_ed, self.st_xy, self.st_escala, self.st_crs):
            sb.addPermanentWidget(w)

    def _atalhos(self):
        for seq, chave in ((QKeySequence.StandardKey.Save, "salvar"), (QKeySequence.StandardKey.Undo, "desfazer"),
                           (QKeySequence.StandardKey.Redo, "refazer"), ("F5", "simular"), ("F6", "validar"),
                           ("Ctrl+Shift+F", "zoom_total"), ("Ctrl+F", "localizar"), ("Ctrl+T", "tabelas"),
                           ("Ctrl+G", "graficos"), ("Ctrl+O", "abrir"), ("Ctrl+N", "novo"), ("F1", "guia")):
            a = QShortcut(QKeySequence(seq), self)
            a.activated.connect(lambda k=chave: self.acionar(k))
        QShortcut(QKeySequence("Esc"), self).activated.connect(self._esc)
        QShortcut(QKeySequence("Del"), self).activated.connect(lambda: self.acionar("excluir"))

    # ================================================================ ações
    def acionar(self, chave):
        if chave in self.ferramentas:
            if chave != "selecionar" and not self.nucleo.cadastro() and chave not in ("pan", "zoom_mais", "zoom_menos"):
                return self.nucleo.aviso("Abra um cadastro primeiro.")
            return self.usar(chave)
        if chave == "exemplo":
            arq = os.path.join(RAIZ, "cadastro", "GWATER_cadastro.qgz")
            if self.fechar_projeto(True):
                self.abrir_projeto(arq)
            return
        self.nucleo.executar(chave)

    def usar(self, nome):
        """Ativa uma ferramenta de mapa pelo nome (selecionar, pan, zoom, mover, medir...)."""
        f = self.ferramentas[nome]
        self.canvas.setMapTool(f)
        self.ferramenta_atual = nome
        self.faixa.marcar(nome)
        self.centro.setCurrentWidget(self.pagina_mapa) if self.centro.indexOf(self.pagina_mapa) >= 0 else None

    def usar_ferramenta(self, ferramenta, chave):
        """Ferramenta montada na hora (desenho, clique para gráfico, perfil, anotação)."""
        self._temporaria = ferramenta
        self.canvas.setMapTool(ferramenta)
        self.ferramenta_atual = chave
        self.faixa.marcar(chave)

    def desenhar(self, lyr, chave="tubulacao"):
        if lyr is None:
            return
        f = fm.FerramentaDesenho(self.canvas, self.cad, lyr, self, depois=lambda ok: self._editado())
        self.usar_ferramenta(f, chave)
        self.mostrar_mapa()

    def _esc(self):
        if self.ferramenta_atual != "selecionar":
            self.usar("selecionar")
            self.nucleo.dock.status.setText("Pronto.")
        else:
            for l in self.nucleo.camadas_rede():
                l.removeSelection()
            self._selecao_mudou()

    def _medida(self, texto, final):
        self.st_msg.setText(texto)
        if final:
            self.nucleo.informar(texto)

    def mostrar_mapa(self):
        if self.centro.indexOf(self.pagina_mapa) >= 0:
            self.centro.setCurrentWidget(self.pagina_mapa)

    def mostrar_painel(self, nome):
        d = {"propriedades": self.dock_prop, "consultas": self.dock_consultas, "simbologia": self.dock_arvore,
             "calculo": self.nucleo.dock}[nome]
        d.show()
        d.raise_()

    def alternar_painel(self, nome):
        d = {"propriedades": self.dock_prop, "consultas": self.dock_consultas, "simbologia": self.dock_arvore,
             "calculo": self.nucleo.dock}[nome]
        d.setVisible(not d.isVisible())
        if d.isVisible():
            d.raise_()

    def ocupado(self, texto=""):
        self.st_msg.setText(texto)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()

    def livre(self, texto=""):
        QApplication.restoreOverrideCursor()
        self.st_msg.setText(texto)

    # ================================================================ projeto
    def pasta_padrao(self):
        gpkg = self.nucleo.cadastro()
        return os.path.dirname(gpkg) if gpkg else os.path.join(RAIZ, "cadastro")

    def projeto_do_gpkg(self, gpkg):
        """Projeto GWATER_<nome>.qgz ao lado do GeoPackage; se não houver, cria um a partir do modelo."""
        base = os.path.splitext(os.path.basename(gpkg))[0]
        qgz = os.path.join(os.path.dirname(gpkg), f"GWATER_{base}.qgz")
        if os.path.exists(qgz):
            return qgz
        modelo = os.path.join(RAIZ, "cadastro", "GWATER_cadastro.qgz")
        r = QMessageBox.question(self, "GWATER", f"{os.path.basename(gpkg)} não tem projeto GWATER ao lado.\n\n"
                                 f"Criar {os.path.basename(qgz)} (estilos, formulários e encaixe do GWATER)?")
        if r != QMessageBox.StandardButton.Yes:
            return None
        with zipfile.ZipFile(modelo) as zin, zipfile.ZipFile(qgz, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                dados = zin.read(item.filename)
                if item.filename.endswith(".qgs"):
                    dados = dados.replace(b"./gwater_cadastro.gpkg", f"./{os.path.basename(gpkg)}".encode()) \
                        .replace(b"gwater_cadastro.gpkg", os.path.basename(gpkg).encode())
                zout.writestr(item, dados)
        return qgz

    def fechar_projeto(self, perguntar=True):
        """Fecha o cadastro aberto (perguntando sobre edições não salvas). True = pode seguir."""
        prj = QgsProject.instance()
        pendentes = [l for l in prj.mapLayers().values()
                     if isinstance(l, QgsVectorLayer) and l.isEditable() and l.isModified()]
        if perguntar and pendentes:
            r = QMessageBox.question(self, "GWATER", "Há edições não salvas em: " +
                                     ", ".join(l.name() for l in pendentes) + ".\n\nSalvar antes de fechar?",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                     QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return False
            for l in pendentes:
                if r == QMessageBox.StandardButton.Save:
                    l.commitChanges()
                else:
                    l.rollBack()
        if prj.fileName() and prj.isDirty():
            prj.write()
        self.nucleo.acao_limpar() if self.nucleo.res else None
        for i in reversed(range(self.centro.count())):
            if self.centro.widget(i) not in (self.pagina_mapa, self.pagina_inicio):
                self._fechar_aba(i)
        prj.clear()
        return True

    def abrir_projeto(self, arq):
        self.ocupado("Abrindo o cadastro…")
        try:
            ok = QgsProject.instance().read(arq)
        finally:
            self.livre()
        if not ok:
            self.nucleo.aviso(f"Não consegui abrir {arq}.")
            return False
        return True

    def _projeto_lido(self):
        prj = QgsProject.instance()
        self.nucleo._projeto_aberto()
        if self.nucleo.cadastro():
            self.nucleo.dock.status.setText(
                f"Cadastro: <b>{os.path.basename(self.nucleo.cadastro())}</b>. Desenhe na aba Desenho, ou Calcular (F5).")
        if not self.nucleo.cadastro():
            self.nucleo.aviso("O projeto aberto não tem um cadastro GWATER (camada trecho de um GeoPackage).")
        self.canvas.setDestinationCrs(prj.crs())
        self.st_crs.setText(prj.crs().authid())
        self.encaixe.setConfig(prj.snappingConfig())
        if self.centro.indexOf(self.pagina_mapa) < 0:
            i = self.centro.indexOf(self.pagina_inicio)
            self.centro.removeTab(i)
            self.centro.insertTab(0, self.pagina_mapa, icone("mapa"), "Mapa")
            self.centro.tabBar().setTabButton(0, self.centro.tabBar().ButtonPosition.RightSide, None)
        nome = os.path.basename(self.nucleo.cadastro() or prj.fileName())
        self.centro.setTabText(self.centro.indexOf(self.pagina_mapa), f"Mapa · {nome}")
        self.centro.setCurrentWidget(self.pagina_mapa)
        self.faixa.titulo.setText(f"{nome} — {os.path.dirname(self.nucleo.cadastro() or prj.fileName())}")
        self.setWindowTitle(f"GWATER · {nome}")
        self._conectar_camadas()
        self.acionar("zoom_total")
        self.guardar_recente(prj.fileName())
        self.prototipos_tipo = self._ler_json("prototipos_tipo", {})
        self.dock_arvore.projeto_aberto()
        from . import desempenho
        desempenho.camadas(self.nucleo)
        self.iniciar_auto_salvar()
        from .vistas import FUNDOS
        fundo = prj.readEntry(CHAVE, "fundo", "")[0]
        self.cmb_fundo.setCurrentIndex(max(0, self.cmb_fundo.findData(fundo)) if fundo else 0)
        if fundo in FUNDOS:
            self.canvas.setCanvasColor(QColor(FUNDOS[fundo][1]))
        from . import revisao
        revisao.conectar(self.nucleo)
        from .cenarios_ui import atualizar_combo
        atualizar_combo(self)
        self.projeto.emit()

    def _projeto_limpo(self):
        self._conectadas.clear()
        self.dock_arvore.projeto_fechado()
        self._pilha_desfazer.clear()
        self._pilha_refazer.clear()
        self.nucleo.cenario = None
        if self.centro.indexOf(self.pagina_inicio) < 0:
            self.centro.removeTab(self.centro.indexOf(self.pagina_mapa))
            self.centro.insertTab(0, self.pagina_inicio, icone("gwater"), "Início")
            self.centro.tabBar().setTabButton(0, self.centro.tabBar().ButtonPosition.RightSide, None)
        self.faixa.titulo.setText("GWATER")
        self.setWindowTitle("GWATER")
        self.atualizar_recentes()
        self.projeto.emit()

    def _conectar_camadas(self):
        for lyr in self.nucleo.camadas_rede():
            if lyr.id() in self._conectadas:
                continue
            self._conectadas.add(lyr.id())
            lyr.selectionChanged.connect(lambda *_: self._selecao_mudou())
            lyr.editingStarted.connect(self._estado_edicao)
            lyr.editingStopped.connect(self._estado_edicao)
            lyr.layerModified.connect(self._estado_edicao)
            lyr.undoStack().indexChanged.connect(lambda _i, l=lyr: self._comando(l))

    def _ler_json(self, chave, padrao):
        import json
        try:
            return json.loads(QgsProject.instance().readEntry(CHAVE, chave, "")[0] or "null") or padrao
        except ValueError:
            return padrao

    def gravar_json(self, chave, valor):
        import json
        QgsProject.instance().writeEntry(CHAVE, chave, json.dumps(valor, ensure_ascii=False))

    # ---- recentes
    def guardar_recente(self, arq):
        if not arq:
            return
        lista = [a for a in (CONFIG.value("recentes", []) or []) if a != arq and os.path.exists(a)]
        CONFIG.setValue("recentes", [arq] + lista[:9])
        self.atualizar_recentes()

    def atualizar_recentes(self):
        lista = [a for a in (CONFIG.value("recentes", []) or []) if os.path.exists(a)]
        self.lista_recentes.clear()
        menu = self.faixa.menu_recentes
        menu.clear()
        for a in lista:
            it = QListWidgetItem(icone("abrir"), f"{os.path.basename(a)}\n{os.path.dirname(a)}")
            it.setData(Qt.ItemDataRole.UserRole, a)
            self.lista_recentes.addItem(it)
            menu.addAction(os.path.basename(a)).triggered.connect(lambda _=False, x=a: self._abrir_recente(x))
        if not lista:
            menu.addAction("(nenhum)").setEnabled(False)

    def _abrir_recente(self, arq):
        if arq and self.fechar_projeto(True):
            self.abrir_projeto(arq)

    # ================================================================ seleção, edição, desfazer
    def _selecao_mudou(self):
        partes = []
        for lyr in self.nucleo.camadas_rede():
            n = lyr.selectedFeatureCount()
            if n:
                partes.append(f"{n} {lyr.name().lower()}")
        self.st_sel.setText("Selecionado: " + ", ".join(partes) if partes else "Nada selecionado")
        self.selecao.emit()

    def selecionados(self):
        """[(camada, [fids])] das camadas do cadastro com seleção."""
        return [(l, list(l.selectedFeatureIds())) for l in self.nucleo.camadas_rede() if l.selectedFeatureCount()]

    def _estado_edicao(self):
        import time
        self._ultima_edicao = time.monotonic()
        if not hasattr(self, "_timer_edicao"):
            from qgis.PyQt.QtCore import QTimer
            self._timer_edicao = QTimer(self)
            self._timer_edicao.setSingleShot(True)
            self._timer_edicao.setInterval(150)
            self._timer_edicao.timeout.connect(self._contar_edicoes)
        self._timer_edicao.start()

    def _contar_edicoes(self):
        n = sum(1 for l in self.nucleo.camadas_rede() if l.isEditable() and l.isModified())
        self.st_ed.setText(f"<span style='color:#ffb547'>● {n} camada(s) com edições não salvas</span>" if n else
                           "Sem edições pendentes")

    # ------------------------------------------------ salvamento automático (Configurações > Salvamento)
    def iniciar_auto_salvar(self):
        from qgis.PyQt.QtCore import QTimer
        if getattr(self, "_timer_auto", None) is None:
            import time
            self._ultimo_salvar = time.monotonic()
            self._timer_auto = QTimer(self)
            self._timer_auto.setInterval(10_000)  # confere a cada 10 s; só salva no intervalo escolhido
            self._timer_auto.timeout.connect(self._talvez_salvar)
        self._timer_auto.start()

    def _camadas_do_cadastro(self):
        gpkg = self.nucleo.cadastro()
        return [lyr for caminho, _, lyr in self.nucleo._camadas_gpkg() if caminho == gpkg]

    def _talvez_salvar(self):
        """Salva sozinho as camadas do cadastro com edições, no intervalo das Configurações, quando o usuário
        está parado (não salva no meio de um desenho, de um arraste ou com uma janela aberta)."""
        import time
        from qgis.PyQt.QtWidgets import QApplication
        from . import desempenho
        minutos = desempenho.ler()["auto_min"]
        if not minutos or not self.nucleo.cadastro():
            return
        agora = time.monotonic()
        if agora - getattr(self, "_ultimo_salvar", 0) < minutos * 60:
            return
        if agora - getattr(self, "_ultima_edicao", 0) < 8:  # editou agora há pouco: espera parar
            return
        if QApplication.activeModalWidget() is not None or QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            return
        if getattr(self.nucleo.topologia, "ocupado", False) or getattr(self.nucleo.topologia, "fila", None):
            return
        self.salvar_camadas(automatico=True)

    def salvar_camadas(self, automatico=False):
        """Grava as camadas do cadastro com edições (continuam em edição). Devolve (salvas, erros)."""
        import time
        from datetime import datetime
        pendentes = [l for l in self._camadas_do_cadastro() if l.isEditable() and l.isModified()]
        self._ultimo_salvar = time.monotonic()
        if not pendentes:
            return [], []
        salvas, erros = [], []
        for lyr in pendentes:
            if lyr.commitChanges(False):
                salvas.append(lyr.name())
            else:
                erros.append(f"{lyr.name()}: {'; '.join(lyr.commitErrors()[:2])}")
        if erros:
            self.nucleo.aviso("Salvamento automático: não consegui gravar " + " | ".join(erros))
        elif automatico:
            self.statusBar().showMessage(f"Salvo automaticamente às {datetime.now():%H:%M} ({', '.join(salvas)}).",
                                         8000)
        self._contar_edicoes()
        return salvas, erros

    def _editado(self):
        self._estado_edicao()
        self.selecao.emit()

    def _comando(self, lyr):
        pilha = lyr.undoStack()
        if getattr(self, "_mexendo", False):
            return
        if pilha.index() > 0 and (not self._pilha_desfazer or self._pilha_desfazer[-1] != lyr.id()
                                  or True):
            self._pilha_desfazer.append(lyr.id())
            self._pilha_refazer.clear()

    def desfazer(self):
        prj = QgsProject.instance()
        while self._pilha_desfazer:
            lyr = prj.mapLayer(self._pilha_desfazer.pop())
            if lyr is not None and lyr.isEditable() and lyr.undoStack().canUndo():
                self._mexendo = True
                lyr.undoStack().undo()
                self._mexendo = False
                self._pilha_refazer.append(lyr.id())
                self.canvas.refresh()
                return
        self.nucleo.informar("Nada para desfazer.")

    def refazer(self):
        prj = QgsProject.instance()
        while self._pilha_refazer:
            lyr = prj.mapLayer(self._pilha_refazer.pop())
            if lyr is not None and lyr.isEditable() and lyr.undoStack().canRedo():
                self._mexendo = True
                lyr.undoStack().redo()
                self._mexendo = False
                self._pilha_desfazer.append(lyr.id())
                self.canvas.refresh()
                return
        self.nucleo.informar("Nada para refazer.")

    # ================================================================ resultados e hora
    def resultados_mudaram(self):
        res = self.nucleo.res
        self.sl_hora.blockSignals(True)
        if res:
            self.sl_hora.setEnabled(True)
            self.sl_hora.setRange(0, len(res.horas) - 1)
            self.sl_hora.setValue(self.nucleo.dock.slider.value())
        else:
            self.sl_hora.setEnabled(False)
            self.lb_hora.setText("Sem resultados")
        self.sl_hora.blockSignals(False)
        self._hora_mudou(self.nucleo.dock.slider.value())
        QTimer.singleShot(0, lambda: self.resizeDocks([self.nucleo.dock], [210], Qt.Orientation.Vertical))
        self.resultados.emit()

    def passo(self):
        return self.nucleo.dock.slider.value() if self.nucleo.res else 0

    def _hora_mudou(self, k):
        res = self.nucleo.res
        if not res:
            return
        from gwater.resultados import _hora
        self.lb_hora.setText(f"Resultado: <b>{_hora(res.horas[k])}</b>")
        self.sl_hora.blockSignals(True)
        self.sl_hora.setValue(k)
        self.sl_hora.blockSignals(False)
        self.dock_prop.atualizar()

    def _configurar(self):
        from . import tema
        if tema.configurar(self):
            self.statusBar().showMessage(f"Tema {tema.tema_atual()} aplicado.", 6000)

    def _fundo_escolhido(self, i):
        from . import vistas
        nome = self.cmb_fundo.itemData(i)
        if nome:
            vistas.trocar_fundo(self.nucleo, nome)
        elif nome == "":
            vistas._tirar_fundos(self.nucleo)

    # ================================================================ cenários
    def _cenario_escolhido(self, i):
        from .cenarios_ui import ativar
        ativar(self.nucleo, self.cmb_cenario.itemData(i))

    # ================================================================ telas web dentro do programa
    def abrir_web(self, url, titulo):
        try:
            from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
            from qgis.PyQt.QtCore import QUrl
        except ImportError:
            return False
        v = self.web.get(titulo)
        if v is None or self.centro.indexOf(v) < 0:
            v = QWebEngineView()
            v.tentativas = 0

            def carregou(ok, v=v):  # servidor recém-ligado: tenta de novo algumas vezes
                if not ok and v.tentativas < 5:
                    v.tentativas += 1
                    QTimer.singleShot(800, v.reload)
            v.loadFinished.connect(carregou)
            self.web[titulo] = v
            self.centro.addTab(v, icone("painel"), titulo)
        v.tentativas = 0
        v.setUrl(QUrl(url))
        self.centro.setCurrentWidget(v)
        return True

    def _fechar_aba(self, i):
        w = self.centro.widget(i)
        if w in (self.pagina_mapa, self.pagina_inicio):
            return
        self.centro.removeTab(i)
        for k, v in list(self.web.items()):
            if v is w:
                del self.web[k]
        w.deleteLater()

    def abrir_aba(self, widget, titulo, ic="tabelas"):
        i = self.centro.addTab(widget, icone(ic), titulo)
        self.centro.setCurrentIndex(i)
        return widget

    # ================================================================ barra de status
    def _coordenadas(self, p):
        self.st_xy.setText(f"X {p.x():,.2f}  Y {p.y():,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    def zoom_total(self):
        ext = QgsRectangle()
        for lyr in self.nucleo.camadas_rede():
            if lyr.featureCount() > 0:
                lyr.updateExtents()
                e = self.canvas.mapSettings().layerExtentToOutputExtent(lyr, lyr.extent())
                ext.combineExtentWith(e)
        if ext.isEmpty() or ext.width() == 0:
            ext = self.canvas.fullExtent()
        if not ext.isEmpty():
            ext.grow(max(ext.width(), ext.height()) * 0.05 + 10)
            self.canvas.setExtent(ext)
        self.canvas.refresh()

    # ================================================================ fechar
    def closeEvent(self, ev):
        if not self.fechar_projeto(True):
            ev.ignore()
            return
        if self.nucleo.servidor:
            self.nucleo.servidor.terminate()
        ev.accept()
