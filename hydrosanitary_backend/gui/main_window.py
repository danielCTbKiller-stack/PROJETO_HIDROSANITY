import copy
import os
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPainterPath
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                               QSlider, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from core.entities import Floor, Node, Pipe, Room, Wall
from core.standards import COMMERCIAL_DIAMETERS, FITTING_LABELS, FIXTURE_INFO, MATERIALS
from gui.canvas import ModelCanvas
from gui.properties import PropertiesPanel
from gui.ribbon import Ribbon
from gui.extended import ExtendedPage
from gui.synoptic import SynopticPage
from gui.theme import COR
from importers import import_project
from importers.config import ImportConfig
from services import project_io
from services.budget_calculator import BudgetCalculator
from services.network_analyzer import NetworkAnalyzer
from services.project_manager import ProjectManager
from services.report_generator import generate_memorial

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "import_config.json")
UNDO_LIMIT = 80
PIECES = ["valvula_redutora_pressao", "registro_gaveta", "registro_globo", "registro_pressao", "valvula_retencao",
          "hidrometro", "te_passagem_direta", "joelho_90", "joelho_45", "curva_90", "curva_45", "bucha_reducao", "luva"]
PIECE_TEXT = {"valvula_redutora_pressao": "VRP", "registro_gaveta": "Reg.\ngaveta", "registro_globo": "Reg.\nglobo",
              "registro_pressao": "Reg.\npressão", "valvula_retencao": "Retenção", "hidrometro": "Hidrômetro",
              "te_passagem_direta": "Tê", "joelho_90": "Joelho\n90°", "joelho_45": "Joelho\n45°",
              "curva_90": "Curva\n90°", "curva_45": "Curva\n45°", "bucha_reducao": "Bucha\nredução", "luva": "Luva"}


def logo_pixmap(size=42):
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(COR["cyan"]), 2))
    p.setBrush(QColor("#0a2a58"))
    p.drawEllipse(QPointF(size / 2, size / 2), size / 2 - 2, size / 2 - 2)
    s = size / 42
    path = QPainterPath(QPointF(21 * s, 9 * s))
    path.cubicTo(QPointF(26 * s, 16 * s), QPointF(29 * s, 20 * s), QPointF(29 * s, 24 * s))
    path.arcTo(13 * s, 16 * s, 16 * s, 16 * s, 0, -180)
    path.cubicTo(QPointF(13 * s, 20 * s), QPointF(16 * s, 16 * s), QPointF(21 * s, 9 * s))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COR["cyan"]))
    p.drawPath(path)
    p.end()
    return pm


class FloorDialog(QDialog):
    def __init__(self, parent, floor: Floor):
        super().__init__(parent)
        self.setWindowTitle("Pavimento")
        form = QFormLayout(self)
        self.name = QLineEdit(floor.name)
        self.elev = QDoubleSpinBox(); self.elev.setRange(-100, 1000); self.elev.setDecimals(2); self.elev.setValue(floor.elevation_m)
        self.height = QDoubleSpinBox(); self.height.setRange(1, 50); self.height.setDecimals(2); self.height.setValue(floor.height_m)
        form.addRow("Nome", self.name)
        form.addRow("Cota do piso (m)", self.elev)
        form.addRow("Pé-direito (piso a piso, m)", self.height)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hidrossanitário – Água fria predial")
        self.setWindowIcon(QIcon(logo_pixmap(64)))
        self.resize(1440, 880)
        self.project_name = "Projeto"
        self.file_path: Optional[str] = None
        self.warnings: list = []
        self.last_result: Optional[dict] = None
        self.import_result = None
        self._undo, self._redo = [], []

        self.canvas = ModelCanvas()
        self.properties = PropertiesPanel()
        self.synoptic = SynopticPage()
        self.extended = ExtendedPage(lambda: (self.canvas.project, self.canvas.source_id, self.max_velocity.value(),
                                              self.fittings_check.isChecked()))
        self.extended.applyStep.connect(self._apply_instant)
        self.pipe_table = self._table(["Trecho", "Q (L/s)", "DN (mm)", "v (m/s)", "hf (mca)", "Leq (m)"])
        self.node_table = self._table(["Nó", "Cota (m)", "Pressão (mca)", "Mínima (mca)", "Situação"])
        self.budget_table = self._table(["Material", "Qtd (m)", "Preço un.", "Total"])
        self.alerts = QListWidget()

        self._build_params()
        self._build_center()
        self._build_docks()
        self._build_top()
        self._build_status()
        self._connect()
        self.new_project(ask=False)

    # ================================================================ montagem
    @staticmethod
    def _table(headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.horizontalHeader().setStretchLastSection(True)
        t.verticalHeader().setVisible(False)
        return t

    def _build_params(self):
        self.pressure = QDoubleSpinBox(); self.pressure.setRange(-50, 200); self.pressure.setValue(5.0)
        self.pressure.setSuffix(" mca")
        self.max_velocity = QDoubleSpinBox(); self.max_velocity.setRange(0.5, 10); self.max_velocity.setValue(3.0)
        self.max_velocity.setSingleStep(0.1); self.max_velocity.setSuffix(" m/s")
        self.auto_size = QCheckBox("Dimensionar diâmetros")
        self.fittings_check = QCheckBox("Considerar conexões (Leq)")
        self.fittings_check.setChecked(True)
        self.fittings_check.stateChanged.connect(lambda _: self.run_analysis(quiet=True))
        self.source_label = QLabel("–")
        self.rooms_list = QListWidget()
        self.rooms_list.itemChanged.connect(lambda _: self.run_analysis(quiet=True))
        self.view_mode = QComboBox(); self.view_mode.addItems(["Isométrica", "Planta"])
        self.view_mode.currentIndexChanged.connect(lambda i: self.canvas.set_mode("iso" if i == 0 else "plan"))

    def _build_center(self):
        model_page = QFrame()
        model_page.setObjectName("card")
        lay = QVBoxLayout(model_page)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.canvas.banner)
        lay.addWidget(self.canvas)
        results = QTabWidget()
        for widget, title in ((self.pipe_table, "TRECHOS"), (self.node_table, "NÓS"),
                              (self.budget_table, "ORÇAMENTO"), (self.alerts, "ALERTAS")):
            results.addTab(widget, title)
        res_page = QWidget()
        rl = QVBoxLayout(res_page)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.addWidget(results)
        self.pages = QStackedWidget()
        for w in (model_page, self.synoptic, res_page, self.extended):
            self.pages.addWidget(w)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(8, 0, 8, 0)
        hl.addWidget(self.pages)
        self.setCentralWidget(holder)

    def _build_docks(self):
        floors = QWidget()
        fl = QVBoxLayout(floors)
        fl.setContentsMargins(8, 8, 8, 8)
        self.floor_list = QListWidget()
        self.floor_list.currentRowChanged.connect(self._floor_selected)
        self.floor_list.itemDoubleClicked.connect(lambda _: self.edit_floor())
        fl.addWidget(self.floor_list, 2)
        row = QHBoxLayout()
        for text, slot in (("+ Novo", self.add_floor), ("Editar", self.edit_floor), ("Remover", self.remove_floor)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        fl.addLayout(row)
        self.show_above = QCheckBox("Mostrar pavimentos acima do ativo")
        self.show_above.stateChanged.connect(lambda s: (setattr(self.canvas, "cut_above", not s), self.canvas.redraw()))
        fl.addWidget(self.show_above)
        t = QLabel("CÔMODOS CONSUMINDO"); t.setObjectName("h3")
        fl.addWidget(t)
        fl.addWidget(self.rooms_list, 3)
        src = QHBoxLayout()
        lb = QLabel("Reservatório:"); lb.setObjectName("rotulo")
        src.addWidget(lb); src.addWidget(self.source_label, 1)
        fl.addLayout(src)
        dock = QDockWidget("PAVIMENTOS", self)
        dock.setObjectName("dock_pavimentos")
        dock.setWidget(floors)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        dock.setMinimumWidth(240)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        dock = QDockWidget("PROPRIEDADES", self)
        dock.setObjectName("dock_propriedades")
        dock.setWidget(self.properties)
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        dock.setMinimumWidth(290)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.properties.show_selection(self.canvas)

    def _build_top(self):
        top = QWidget()
        col = QVBoxLayout(top)
        col.setContentsMargins(8, 8, 8, 6)
        col.setSpacing(6)
        head = QFrame()
        head.setObjectName("cabecalho")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 6, 12, 6)
        logo = QLabel(); logo.setPixmap(logo_pixmap(40))
        hl.addWidget(logo)
        titles = QVBoxLayout(); titles.setSpacing(0)
        h1 = QLabel("Hidrossanitário · Água fria predial"); h1.setObjectName("h1")
        self.subtitle = QLabel("Projeto"); self.subtitle.setObjectName("sub")
        titles.addWidget(h1); titles.addWidget(self.subtitle)
        hl.addLayout(titles)
        hl.addStretch(1)
        self.nav = QButtonGroup(self)
        for i, text in enumerate(("MODELO", "SINÓTICO", "RESULTADOS", "PERÍODO ESTENDIDO")):
            b = QToolButton(); b.setObjectName("nav"); b.setText(text); b.setCheckable(True)
            b.setChecked(i == 0)
            self.nav.addButton(b, i)
            hl.addWidget(b)
        self.nav.idClicked.connect(self.show_page)
        hl.addStretch(1)
        self.chip_norm = self._chip("NBR 5626")
        self.chip_calc = self._chip("NÃO CALCULADO")
        self.chip_alerts = self._chip("ALERTAS –")
        for c in (self.chip_norm, self.chip_calc, self.chip_alerts):
            hl.addWidget(c)
        col.addWidget(head)
        col.addWidget(self._build_ribbon())
        self.setMenuWidget(top)

    @staticmethod
    def _chip(text):
        c = QLabel(text)
        c.setObjectName("chip")
        return c

    @staticmethod
    def _set_chip(chip, text, state=""):
        chip.setText(text)
        chip.setProperty("estado", state)
        chip.style().unpolish(chip)
        chip.style().polish(chip)

    def _build_ribbon(self):
        rb = self.ribbon = Ribbon()
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_buttons = {}

        def tool(group, text, icon_name, tool_name, opt=None, value=None, tip=""):
            b = group.button(text, icon_name, None, tip, checkable=True, group=self.tool_group)
            b.clicked.connect(lambda: self.set_tool(tool_name, opt, value))
            self._tool_buttons[(tool_name, value)] = b
            return b

        pg = rb.page("Início")
        g = pg.group("Arquivo")
        g.button("Novo", "novo", lambda: self.new_project(), "Projeto em branco (Ctrl+N)")
        g.button("Abrir", "abrir", self.open_file, "Abrir .hsp, .dxf ou .ifc (Ctrl+O)")
        g.button("Salvar", "salvar", self.save_file, "Salvar projeto .hsp (Ctrl+S)")
        g.button("Memorial", "memorial", lambda: self.export_report(), "Exportar memorial de cálculo (Ctrl+E)")
        g = pg.group("Editar")
        g.button("Desfazer", "desfazer", self.undo, "Ctrl+Z")
        g.button("Refazer", "refazer", self.redo, "Ctrl+Y")
        g.button("Excluir", "excluir", self.canvas.delete_selection, "Apaga o elemento selecionado (Del)")
        g = pg.group("Exemplo")
        g.button("Edifício", "exemplo", self.load_sample_building, "Abre um edifício de 8 pavimentos já desenhado")

        pg = rb.page("Desenho")
        g = pg.group("Rede")
        tool(g, "Selecionar", "selecionar", "select", tip="Selecionar e editar (Esc)")
        tool(g, "Tubo", "tubo", "pipe", tip="Desenhar tubulação")
        tool(g, "Prumada", "prumada", "riser", tip="Tubo vertical entre pavimentos")
        tool(g, "Reservatório", "fonte", "source", tip="Ponto de alimentação da rede")
        g = pg.group("Parede de trabalho")
        g.button("Vista da\nparede", "parede_2d", self.open_wall_view,
                 "Abre a parede selecionada em 2D para desenhar a tubulação nela (ou dê duplo clique na parede)")
        g.button("Outro\nlado", "girar", self.canvas.flip_wall_view, "Olha a parede pelo outro lado")
        g.button("Voltar\nao 3D", "iso", self.canvas.exit_wall_view, "Sai da vista da parede (Esc)")
        self.elev_off = QDoubleSpinBox(); self.elev_off.setRange(-1, 1); self.elev_off.setSingleStep(0.01)
        self.elev_off.setDecimals(2); self.elev_off.setSuffix(" m")
        self.elev_off.setToolTip("0 = tubo embutido no eixo da parede; positivo = afastado para o lado de quem olha")
        self.elev_off.valueChanged.connect(lambda v: (self.canvas.opts.__setitem__("elev_off", v), self.canvas._update_banner()))
        g.widgets([("Afastamento", self.elev_off)])
        g = pg.group("Tubo")
        self.dn = QComboBox(); self.dn.addItems([f"{d:g}" for d in COMMERCIAL_DIAMETERS]); self.dn.setCurrentText("25")
        self.dn.currentTextChanged.connect(lambda t: self.canvas.opts.__setitem__("dn", float(t)))
        self.material = QComboBox(); self.material.addItems(MATERIALS)
        self.material.currentTextChanged.connect(lambda t: self.canvas.opts.__setitem__("material", t))
        self.pipe_h = QDoubleSpinBox(); self.pipe_h.setRange(-5, 20); self.pipe_h.setSingleStep(0.1); self.pipe_h.setValue(2.2)
        self.pipe_h.setSuffix(" m")
        self.pipe_h.valueChanged.connect(lambda v: (self.canvas.opts.__setitem__("pipe_h", v), self.canvas.redraw()))
        g.widgets([("DN (mm)", self.dn), ("Material", self.material), ("Altura do piso", self.pipe_h)])
        g = pg.group("Precisão")
        b = g.button("Grade", "grade", None, "Encaixar na grade", checkable=True)
        b.setChecked(True)
        b.toggled.connect(lambda on: setattr(self.canvas, "snap_grid", on))
        self.ortho_btn = g.button("Ortogonal", "orto", None, "Só horizontal/vertical (F8 ou segurar Shift)", checkable=True)
        self.ortho_btn.toggled.connect(lambda on: setattr(self.canvas, "ortho", on))
        self.grid_step = QDoubleSpinBox(); self.grid_step.setRange(0.01, 5); self.grid_step.setSingleStep(0.05)
        self.grid_step.setValue(0.10); self.grid_step.setSuffix(" m")
        self.grid_step.valueChanged.connect(lambda v: self.canvas.opts.__setitem__("grid", v))
        g.widgets([("Passo", self.grid_step)])

        pg = rb.page("Aparelhos")
        g = pg.group("Aparelhos sanitários")
        for key, (label, sigla, _h) in FIXTURE_INFO.items():
            short = label.replace("Bacia c/ caixa acoplada", "Bacia cx.\nacoplada").replace(
                "Bacia c/ válvula de descarga", "Válvula\ndescarga").replace("Máquina de lavar roupa", "Máq. lavar\nroupa").replace(
                "Máquina de lavar louça", "Máq. lavar\nlouça").replace("Torneira de jardim", "Torneira\njardim").replace(
                "Chuveiro elétrico", "Chuveiro").replace("Pia de cozinha", "Pia").replace("Ducha higiênica", "Ducha\nhigiênica")
            tool(g, short, key, "fixture", "fixture", key, label)

        pg = rb.page("Peças")
        g = pg.group("Válvulas e registros")
        for key in PIECES[:6]:
            tool(g, PIECE_TEXT[key], key, "fitting", "fitting", key, FITTING_LABELS[key])
        g = pg.group("Conexões")
        for key in PIECES[6:]:
            tool(g, PIECE_TEXT[key], key, "fitting", "fitting", key, FITTING_LABELS[key])

        pg = rb.page("Arquitetura")
        g = pg.group("Paredes")
        tool(g, "Externa", "parede_ext", "wall", "wall_kind", "externa", "Parede externa")
        tool(g, "Interna", "parede_int", "wall", "wall_kind", "interna", "Parede interna")
        tool(g, "Retângulo", "retangulo", "rect", "wall_kind", None, "Ambiente retangular (4 paredes)")
        tool(g, "Cômodo", "comodo", "room", tip="Contorno do cômodo (área de consumo)")
        g = pg.group("Espessura")
        self.thk_ext = QDoubleSpinBox(); self.thk_ext.setRange(0.05, 1); self.thk_ext.setSingleStep(0.01); self.thk_ext.setValue(0.20); self.thk_ext.setSuffix(" m")
        self.thk_int = QDoubleSpinBox(); self.thk_int.setRange(0.03, 1); self.thk_int.setSingleStep(0.01); self.thk_int.setValue(0.12); self.thk_int.setSuffix(" m")
        self.thk_ext.valueChanged.connect(lambda v: self.canvas.opts.__setitem__("thk_externa", v))
        self.thk_int.valueChanged.connect(lambda v: self.canvas.opts.__setitem__("thk_interna", v))
        g.widgets([("Externa", self.thk_ext), ("Interna", self.thk_int)])
        g = pg.group("Pavimentos")
        g.button("Novo\npavimento", "pavimento", self.add_floor, "Cria um pavimento acima do último")
        g.button("Paredes\np/ cima", "copiar_acima", lambda: self.copy_floor_up(network=False),
                 "Copia paredes e cômodos do pavimento ativo para o de cima (empilha)")
        g.button("Replicar\npavimento", "replicar", lambda: self.copy_floor_up(network=True, ask=True),
                 "Replica o pavimento tipo (arquitetura + rede) para os pavimentos acima")

        pg = rb.page("Análise")
        g = pg.group("Cálculo")
        b = g.button("Calcular", "calcular", lambda: self.run_analysis(), "Calcula vazões e pressões (F5)")
        g.widgets([("Pressão na fonte", self.pressure), ("Velocidade máx.", self.max_velocity)])
        g.widgets([("", self.auto_size), ("", self.fittings_check)])
        g = pg.group("Saída")
        g.button("Sinótico", "sinotico", lambda: self.show_page(1))
        g.button("Período\nestendido", "relogio", lambda: self.show_page(3),
                 "Simulação ao longo do dia: consumo, nível do reservatório e pressões")
        g.button("Memorial", "memorial", lambda: self.export_report())

        pg = rb.page("Exibir")
        g = pg.group("Vista")
        g.button("Isométrica", "iso", lambda: self._set_view(0))
        g.button("Planta", "planta", lambda: self._set_view(1))
        g.button("Vista da\nparede", "parede_2d", self.open_wall_view)
        g.button("Girar 90°", "girar", self.canvas.rotate_view)
        g.button("Ajustar", "ajustar", self.canvas.fit, "Enquadrar o modelo")
        g = pg.group("Paredes")
        self.alpha = QSlider(Qt.Horizontal); self.alpha.setRange(15, 100); self.alpha.setValue(90); self.alpha.setFixedWidth(130)
        self.alpha.valueChanged.connect(lambda v: (setattr(self.canvas, "wall_alpha", v / 100), self.canvas.redraw()))
        g.widgets([("Opacidade", self.alpha), ("Vista", self.view_mode)])
        self.xray = QCheckBox("Tubulação sempre visível (raio-X)")
        self.xray.toggled.connect(lambda on: (setattr(self.canvas, "xray", on), self.canvas.redraw()))
        g.widgets([("", self.xray)])
        self._tool_buttons[("select", None)].setChecked(True)
        return rb

    def _build_status(self):
        self.coord = QLabel("x –  y –  z –")
        self.statusBar().addPermanentWidget(self.coord)

    def _connect(self):
        c = self.canvas
        c.beforeChange.connect(self._snapshot)
        c.changed.connect(self._after_change)
        c.selectionChanged.connect(lambda _: self.properties.show_selection(c))
        c.cursorMoved.connect(lambda x, y, z: self.coord.setText(f"x {x:8.2f}  y {y:8.2f}  z {z:6.2f} m"))
        c.message.connect(lambda t: self.statusBar().showMessage(t))
        self.properties.before.connect(self._snapshot)
        self.properties.changed.connect(self._after_change)
        self.synoptic.floorClicked.connect(self._floor_from_synoptic)
        for seq, slot in ((QKeySequence.New, lambda: self.new_project()), (QKeySequence.Open, self.open_file),
                          (QKeySequence.Save, self.save_file), ("Ctrl+Shift+S", lambda: self.save_file(as_new=True)),
                          ("Ctrl+E", lambda: self.export_report()), ("F5", lambda: self.run_analysis()),
                          (QKeySequence.Undo, self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Q", self.close)):
            act = QAction(self, triggered=slot)
            act.setShortcut(QKeySequence(seq))
            self.addAction(act)

    # ================================================================ navegação / ferramentas
    def show_page(self, i):
        self.pages.setCurrentIndex(i)
        self.nav.button(i).setChecked(True)
        for dock in self.findChildren(QDockWidget):  # sinótico e resultados usam a tela toda, como no GWATER
            dock.setVisible(i == 0)
        if i == 3 and self.extended.run is None:
            self.extended.load_defaults()
        if i == 1:
            self._refresh_synoptic()

    def _set_view(self, i):
        if self.view_mode.currentIndex() == i:
            self.canvas.set_mode("iso" if i == 0 else "plan")  # também sai da vista da parede
        else:
            self.view_mode.setCurrentIndex(i)

    def open_wall_view(self):
        sel = self.canvas.selection
        if not sel or sel[0] != "wall":
            QMessageBox.information(self, "Vista da parede",
                                    "Selecione uma parede (ou dê duplo clique nela) para abrir a vista 2D.")
            return
        self.show_page(0)
        self.canvas.enter_wall_view(sel[1])

    def set_tool(self, tool, opt=None, value=None):
        if opt and value is not None:
            self.canvas.opts[opt] = value
        self.canvas.set_tool(tool)
        b = self._tool_buttons.get((tool, value)) or self._tool_buttons.get((tool, None))
        if b:
            b.setChecked(True)
        if self.pages.currentIndex() != 0:
            self.show_page(0)

    def _floor_selected(self, row):
        if row < 0 or not self.project:
            return
        idx = len(self.project.floors) - 1 - row  # a lista mostra o pavimento mais alto em cima
        self.canvas.set_active_floor(idx)
        f = self.project.floors[idx]
        self.statusBar().showMessage(f"Pavimento ativo: {f.name} (piso +{f.elevation_m:.2f} m)")

    def _floor_from_synoptic(self, idx):
        self._fill_floors(active=idx)
        self.show_page(0)
        self.canvas.fit()

    def _fill_floors(self, active=None):
        fl = self.project.floors
        active = self.canvas.active_floor if active is None else active
        self.floor_list.blockSignals(True)
        self.floor_list.clear()
        for f in reversed(fl):
            self.floor_list.addItem(QListWidgetItem(f"{f.name}\n+{f.elevation_m:.2f} m · pé-direito {f.height_m:.2f} m"))
        self.floor_list.setCurrentRow(len(fl) - 1 - active)
        self.floor_list.blockSignals(False)
        self.canvas.set_active_floor(active)

    # ================================================================ projeto
    @property
    def project(self) -> Optional[ProjectManager]:
        return self.canvas.project

    def _set_document(self, project, source_id, name, warnings=(), fit=True):
        project.ensure_floors()
        self.project_name = name
        self.warnings = list(warnings)
        self.last_result = None
        self._undo, self._redo = [], []
        self.canvas.active_floor = 0
        self.canvas.set_project(project, source_id, fit=fit)
        self._fill_floors(0)
        self.alerts.clear()
        for w in self.warnings:
            self.alerts.addItem(QListWidgetItem(f"Importação: {w}"))
        for t in (self.pipe_table, self.node_table):
            t.setRowCount(0)
        self._fill_rooms(reset=True)
        self._fill_budget()
        self._update_header()
        self.properties.show_selection(self.canvas)
        self._refresh_synoptic()

    def new_project(self, ask=True):
        p = ProjectManager()
        p.floors = [Floor("Térreo", 0.0, 2.88)]
        self.file_path = None
        self._set_document(p, None, "Novo projeto")
        self.canvas.resetTransform()
        self.canvas.scale(0.8, 0.8)
        self.canvas.centerOn(0, 0)
        self.set_tool("select")
        self.statusBar().showMessage("Projeto novo: desenhe paredes (Arquitetura) e a rede (Desenho, Aparelhos, Peças).")

    def load_sample_building(self):
        from examples.make_sample_building import build_building
        project, source = build_building()
        self.file_path = None
        self.pressure.setValue(0.0)
        self._set_document(project, source, "Edifício exemplo")
        self.run_analysis(quiet=True)
        self.show_page(1)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir projeto", "", "Projetos (*.hsp *.dxf *.ifc)")
        if path:
            self.load_file(path)

    def load_file(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            if path.lower().endswith(".hsp"):
                project, source, params = project_io.load(path)
                warnings = []
                self.import_result = None
                for key, widget in (("source_pressure_mca", self.pressure), ("max_velocity", self.max_velocity)):
                    if key in params:
                        widget.setValue(params[key])
                self.file_path = path
            else:
                self.import_result = import_project(path, ImportConfig.from_json(CONFIG_PATH))
                project, source, warnings = self.import_result.project, self.import_result.source_id, self.import_result.warnings
                self.file_path = None
        except Exception as exc:  # erro de arquivo/formato vai para o usuário, não derruba o app
            QMessageBox.critical(self, "Erro ao abrir", str(exc))
            return
        self._set_document(project, source, name, warnings)
        self.statusBar().showMessage(f"{os.path.basename(path)}: {len(project.nodes)} nós, {len(project.pipes)} trechos, "
                                     f"{len(project.walls)} paredes, {len(project.floors)} pavimento(s).")

    def save_file(self, as_new=False, path=None):
        path = path or (None if as_new else self.file_path)
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Salvar projeto", f"{self.project_name}.hsp", "Projeto (*.hsp)")
        if not path:
            return
        project_io.save(path, self.project, self.canvas.source_id,
                        {"source_pressure_mca": self.pressure.value(), "max_velocity": self.max_velocity.value()})
        self.file_path = path
        self.project_name = os.path.splitext(os.path.basename(path))[0]
        self._update_header()
        self.statusBar().showMessage(f"Projeto salvo: {path}")

    def _update_header(self):
        p = self.project
        self.source_label.setText(self.canvas.source_id or "não definido")
        self.subtitle.setText(f"{self.project_name} · {len(p.floors)} pavimento(s) · {len(p.pipes)} trechos · "
                              f"{sum(len(n.fixtures) for n in p.nodes.values())} aparelhos · {len(p.walls)} paredes")
        self.setWindowTitle(f"{self.project_name} – Hidrossanitário")

    # ================================================================ desfazer / refazer
    def _state(self):
        return (project_io.to_dict(self.project, self.canvas.source_id), self.canvas.selection)

    def _snapshot(self):
        self._undo.append(self._state())
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def _restore(self, state):
        data, sel = state
        project, source, _ = project_io.from_dict(data)
        c = self.canvas
        c.project, c.source_id, c._chain = project, source, []
        c.selection = sel
        if c.selected_object() is None:
            c.selection = None
        self._after_change()
        self._fill_floors()
        self.properties.show_selection(c)

    def undo(self):
        if self._undo:
            self._redo.append(self._state())
            self._restore(self._undo.pop())

    def redo(self):
        if self._redo:
            self._undo.append(self._state())
            self._restore(self._redo.pop())

    def _after_change(self):
        """Depois de qualquer edição: recalcula se já havia resultado e atualiza as vistas."""
        if self.last_result is not None:
            self.run_analysis(quiet=True)
        else:
            self.canvas.redraw()
            self._refresh_synoptic()
        self._fill_rooms()
        self._fill_budget()
        self._update_header()
        self.extended.invalidate()

    def _apply_instant(self, result, when):
        """Leva o resultado de um instante da simulação estendida ao modelo e ao sinótico."""
        if result is None:
            return
        self.last_result = result
        self._fill_results(result)
        self.canvas.set_result(result, self.max_velocity.value())
        self._refresh_synoptic()
        self._set_chip(self.chip_calc, f"INSTANTE {when.upper()}", "ok")
        self.show_page(1)
        self.statusBar().showMessage(f"Mostrando o instante {when} da simulação em período estendido. F5 volta ao pico.")

    # ================================================================ pavimentos
    def add_floor(self):
        fl = self.project.floors
        top = fl[-1] if fl else Floor("", -2.88, 2.88)
        self._snapshot()
        fl.append(Floor(f"{len(fl)}º pavimento" if fl else "Térreo", round(top.elevation_m + top.height_m, 2), top.height_m))
        self._fill_floors(len(fl) - 1)
        self._after_change()

    def edit_floor(self):
        i = self.canvas.active_floor
        f = self.project.floors[i]
        dlg = FloorDialog(self, f)
        if dlg.exec() != QDialog.Accepted:
            return
        self._snapshot()
        dz = dlg.elev.value() - f.elevation_m
        if abs(dz) > 1e-6:  # move tudo o que está no pavimento junto
            for n in self.project.nodes.values():
                if self.project.floor_index(n.elevation_m) == i:
                    n.elevation_m += dz
            for w in self.project.walls:
                if abs(w.z_base_m - f.elevation_m) < 0.05:
                    w.z_base_m += dz
            for r in self.project.rooms.values():
                if abs(r.z_floor_m - f.elevation_m) < 0.05:
                    r.z_floor_m += dz
        for w in self.project.walls:
            if abs(w.z_base_m - f.elevation_m - dz) < 0.05 and abs(w.height_m - f.height_m) < 0.01:
                w.height_m = dlg.height.value()
        f.name, f.elevation_m, f.height_m = dlg.name.text() or f.name, dlg.elev.value(), dlg.height.value()
        self.project.sort_floors()
        self._fill_floors(self.project.floors.index(f))
        self._after_change()

    def remove_floor(self):
        fl = self.project.floors
        if len(fl) <= 1:
            return
        f = fl[self.canvas.active_floor]
        if QMessageBox.question(self, "Remover pavimento",
                                f"Remover '{f.name}' com as paredes e cômodos dele? A rede não é apagada.") != QMessageBox.Yes:
            return
        self._snapshot()
        self.project.walls = [w for w in self.project.walls if abs(w.z_base_m - f.elevation_m) >= 0.05]
        self.project.rooms = {k: r for k, r in self.project.rooms.items() if abs(r.z_floor_m - f.elevation_m) >= 0.05}
        fl.remove(f)
        self._fill_floors(max(0, self.canvas.active_floor - 1))
        self._after_change()

    def copy_floor_up(self, network=False, copies=1, ask=False):
        """Empilha o pavimento ativo: copia paredes e cômodos (e, se `network`, a rede do pavimento)."""
        if ask:
            copies, ok = QInputDialog.getInt(self, "Replicar pavimento", "Quantos pavimentos acima?", 1, 1, 60)
            if not ok:
                return
        p = self.project
        i0 = self.canvas.active_floor
        src = p.floors[i0]
        self._snapshot()
        for k in range(1, copies + 1):
            ti = i0 + k
            if ti >= len(p.floors):
                last = p.floors[-1]
                p.floors.append(Floor(f"{len(p.floors)}º pavimento", round(last.elevation_m + last.height_m, 2), src.height_m))
            dst = p.floors[ti]
            dz = dst.elevation_m - src.elevation_m
            # limpa a arquitetura que já houver no destino, para não duplicar
            p.walls = [w for w in p.walls if abs(w.z_base_m - dst.elevation_m) >= 0.05]
            for w in [w for w in p.walls if abs(w.z_base_m - src.elevation_m) < 0.05]:
                nw = copy.copy(w)
                nw.z_base_m = round(w.z_base_m + dz, 3)
                p.walls.append(nw)
            for r in [r for r in p.rooms.values() if abs(r.z_floor_m - src.elevation_m) < 0.05]:
                name = f"{r.name.split(' – ')[0]} – {dst.name}"
                p.rooms[name] = Room(name, list(r.polygon), round(r.z_floor_m + dz, 3))
            if network:
                self._copy_network(i0, dz, dst.name)
        self._fill_floors(i0)
        self._after_change()
        self.statusBar().showMessage(f"{src.name} copiado para {copies} pavimento(s) acima.")

    def _copy_network(self, fi, dz, floor_name):
        p = self.project
        ids = {nid for nid, n in p.nodes.items() if p.floor_index(n.elevation_m) == fi and nid != self.canvas.source_id}
        new_id = {}
        for nid in sorted(ids):
            n = p.nodes[nid]
            nn = copy.deepcopy(n)
            nn.id = p.new_id("N", p.nodes)
            nn.elevation_m = round(n.elevation_m + dz, 3)
            if nn.room:
                nn.room = f"{nn.room.split(' – ')[0]} – {floor_name}"
            p.add_node(nn)
            new_id[nid] = nn.id
        for pipe in list(p.pipes.values()):
            if pipe.start_node_id in ids and pipe.end_node_id in ids:
                np_ = copy.copy(pipe)
                np_.id = p.new_id("T", p.pipes)
                np_.start_node_id, np_.end_node_id = new_id[pipe.start_node_id], new_id[pipe.end_node_id]
                p.add_pipe(np_)

    # ================================================================ cálculo
    def active_rooms(self):
        if self.rooms_list.count() == 0:
            return None
        return [self.rooms_list.item(i).text() for i in range(self.rooms_list.count())
                if self.rooms_list.item(i).checkState() == Qt.Checked]

    def _fill_rooms(self, reset=False):
        p = self.project
        states = {} if reset else {self.rooms_list.item(i).text(): self.rooms_list.item(i).checkState()
                                   for i in range(self.rooms_list.count())}
        names = [name for name in p.rooms if any(n.room == name and n.fixtures for n in p.nodes.values())]
        if [self.rooms_list.item(i).text() for i in range(self.rooms_list.count())] == names and not reset:
            return
        self.rooms_list.blockSignals(True)
        self.rooms_list.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(states.get(name, Qt.Checked))
            self.rooms_list.addItem(item)
        self.rooms_list.blockSignals(False)

    def run_analysis(self, quiet: bool = False):
        p = self.project
        source = self.canvas.source_id
        if p is None or not p.pipes:
            if not quiet:
                QMessageBox.information(self, "Calcular", "Desenhe ou abra uma rede primeiro.")
            return
        if source is None:
            if not quiet:
                QMessageBox.warning(self, "Calcular", "Nenhuma fonte de água: use Desenho → Reservatório.")
            return
        if self.auto_size.isChecked() and not quiet:
            self._snapshot()  # o dimensionamento altera os diâmetros: dá para desfazer
        # aparelhos sem cômodo continuam consumindo quando há filtro por cômodo
        active = self.active_rooms()
        if active is not None:
            active = active + [""]
        try:
            result = NetworkAnalyzer(p).analyze(
                source, self.pressure.value(), self.auto_size.isChecked(), self.max_velocity.value(),
                active_rooms=active, auto_fittings=self.fittings_check.isChecked())
        except ValueError as exc:
            self.last_result = None
            self.canvas.set_result(None)
            self._refresh_synoptic()
            self._set_chip(self.chip_calc, "REDE INCOMPLETA", "warn")
            if quiet:
                self.statusBar().showMessage(f"Cálculo pausado: {exc}")
            else:
                QMessageBox.warning(self, "Calcular", str(exc))
            return
        result["max_velocity"] = self.max_velocity.value()
        self.last_result = result
        self._fill_results(result)
        self.canvas.set_result(result, self.max_velocity.value())
        self._refresh_synoptic()
        n = len(result["alerts"])
        self._set_chip(self.chip_calc, "CALCULADO", "ok")
        self._set_chip(self.chip_alerts, f"ALERTAS {n}", "crit" if n else "ok")
        self.statusBar().showMessage("Cálculo concluído – " + (f"{n} alerta(s)." if n else "sem alertas."))

    def _refresh_synoptic(self):
        if self.project is not None:
            self.synoptic.set_data(self.project, self.canvas.source_id, self.last_result,
                                   [f"Importação: {w}" for w in self.warnings])

    def _fill_results(self, result):
        project = self.project
        self._fill(self.pipe_table, [
            (pid, f"{r['flow_lps']:.3f}", f"{r['diameter_mm']:g}", f"{r['velocity_ms']:.2f}", f"{r['head_loss_mca']:.3f}",
             f"{r['equivalent_length_m']:.2f}") for pid, r in result["pipes"].items()])
        self._fill(self.node_table, [
            (nid, f"{project.nodes[nid].elevation_m:.2f}", f"{r['pressure_mca']:.2f}",
             f"{r['required_mca']:.2f}", "OK" if r["ok"] else "PRESSÃO BAIXA")
            for nid, r in result["nodes"].items()])
        self.alerts.clear()
        for w in self.warnings:
            self.alerts.addItem(QListWidgetItem(f"Importação: {w}"))
        for a in result["alerts"]:
            self.alerts.addItem(QListWidgetItem(f"[{a['level']}] {a['message']}"))

    def _fill_budget(self):
        items = BudgetCalculator.calculate_materials_cost(list(self.project.pipes.values()))
        rows = [(i["material"], f"{i['quantity']:.2f}", f"R$ {i['unit_price']:.2f}", f"R$ {i['total_price']:.2f}")
                for i in items]
        total = sum(i["total_price"] for i in items)
        rows.append(("TOTAL", "", "", f"R$ {total:.2f}"))
        self._fill(self.budget_table, rows)

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(value))
        table.resizeColumnsToContents()

    # ================================================================ memorial
    def report_html(self) -> str:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        data = QByteArray()  # precisa continuar referenciado enquanto o QBuffer o usa
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        self.canvas.grab().save(buf, "PNG")
        buf.close()
        return generate_memorial(
            self.project, self.last_result, source_id=self.canvas.source_id, source_pressure_mca=self.pressure.value(),
            max_velocity=self.max_velocity.value(), auto_size=self.auto_size.isChecked(),
            active_rooms=self.active_rooms(), project_name=self.project_name, image_png=bytes(data.data()))

    def export_report(self, path: Optional[str] = None):
        if self.last_result is None:
            QMessageBox.information(self, "Exportar", "Calcule o projeto antes de exportar o memorial.")
            return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Exportar memorial", "memorial_de_calculo.pdf",
                                                  "PDF (*.pdf);;HTML (*.html)")
        if not path:
            return
        html = self.report_html()
        if path.lower().endswith(".html"):
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
        else:
            from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
            writer = QPdfWriter(path)
            writer.setPageSize(QPageSize(QPageSize.A4))
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print_(writer)
        self.statusBar().showMessage(f"Memorial exportado: {path}")
