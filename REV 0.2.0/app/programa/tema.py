"""Tema do GWATER.exe: a identidade do Centro de Operações (gwater/estilo.py) aplicada ao programa todo.

Paleta escura no Qt (Fusion) para que os componentes do QGIS (formulários, tabelas, construtor de
expressões) fiquem iguais ao resto, e uma folha de estilo para a faixa de menus, painéis e botões.
O mapa continua claro, como no WaterGEMS: fica mais fácil ler a rede e o mapa de fundo.
"""
import os

from qgis.PyQt.QtGui import QColor, QFont, QIcon, QPalette

from gwater.estilo import COR, CORPO, DISPLAY, MONO, VISTO

ICONES = os.path.join(os.path.dirname(__file__), "icones")
ICONES_NUCLEO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gwater", "icones")


# ---------------------------------------------------------------- temas (Exibir > Tema)
TEMAS = {
    "Original": dict(COR),
    "Abissal Neon": {
        "bg": "#040a18", "panel": "#0a1530", "panel2": "#101f44", "line": "#1d3566", "grid": "#152a52",
        "text": "#eef5ff", "muted": "#8aa2c8", "cyan": "#00e5ff", "water": "#2196f3",
        "ok": "#00e6a0", "warn": "#ffc247", "crit": "#ff5470", "violet": "#b18cff",
        "btn": "#0f2149", "btn_on": "#0058b8", "chip": "#071029"},
    "Grafite Ciano": {
        "bg": "#111316", "panel": "#1a1d22", "panel2": "#22262c", "line": "#30353d", "grid": "#262a31",
        "text": "#eceff3", "muted": "#9099a6", "cyan": "#14c8d8", "water": "#2d8cf0",
        "ok": "#3ccf8e", "warn": "#f5b544", "crit": "#f0566a", "violet": "#9d8cff",
        "btn": "#252a31", "btn_on": "#0f6c78", "chip": "#15181c"},
    "Meia-noite Violeta": {
        "bg": "#0d0b1a", "panel": "#161229", "panel2": "#1e1838", "line": "#33295c", "grid": "#251e45",
        "text": "#f1edff", "muted": "#a39cc8", "cyan": "#8f7bff", "water": "#5b8cff",
        "ok": "#3ee0a4", "warn": "#ffb84d", "crit": "#ff5c8a", "violet": "#d38bff",
        "btn": "#211a3d", "btn_on": "#4b36b8", "chip": "#110e22"},
    "Esmeralda Noturno": {
        "bg": "#06120e", "panel": "#0c1d17", "panel2": "#112820", "line": "#1d4436", "grid": "#163429",
        "text": "#e9fbf3", "muted": "#88b3a2", "cyan": "#22e3a3", "water": "#1fa2d6",
        "ok": "#5ef08a", "warn": "#ffcb4d", "crit": "#ff6470", "violet": "#9f95ff",
        "btn": "#123026", "btn_on": "#0f7a58", "chip": "#08170f"},
    "Âmbar Industrial": {
        "bg": "#0f0f10", "panel": "#18181a", "panel2": "#212124", "line": "#36363b", "grid": "#29292d",
        "text": "#f4f1ea", "muted": "#a19d94", "cyan": "#ffae1a", "water": "#3a9bdc",
        "ok": "#4cd68a", "warn": "#ffd04d", "crit": "#ff5a4f", "violet": "#b49cff",
        "btn": "#26262a", "btn_on": "#8a5a00", "chip": "#141415"},
    "Claro": {
        "bg": "#eef1f5", "panel": "#ffffff", "panel2": "#f5f7fa", "line": "#d3d9e1", "grid": "#e4e8ee",
        "text": "#1a2230", "muted": "#5f6b7a", "cyan": "#0b8fa0", "water": "#1c6fd1",
        "ok": "#16935c", "warn": "#b9770e", "crit": "#d23048", "violet": "#6a4fd8",
        "btn": "#e8edf3", "btn_on": "#cdeef2", "chip": "#f1f4f8"},
}


def tema_atual():
    from qgis.PyQt.QtCore import QSettings
    nome = QSettings("GWATER", "GWATER").value("tema", "Grafite Ciano")
    return nome if nome in TEMAS else "Original"


def aplicar_tema(nome=None, app=None):
    """Troca as cores (COR é compartilhado por todo o programa) e reaplica paleta e folha de estilo."""
    from qgis.PyQt.QtCore import QSettings
    nome = nome or tema_atual()
    COR.update(TEMAS.get(nome, TEMAS["Original"]))
    if nome:
        QSettings("GWATER", "GWATER").setValue("tema", nome)
    if app is not None:
        app.setPalette(paleta())
        app.setStyleSheet(qss())
    return nome


def icone(nome):
    for pasta in (ICONES, ICONES_NUCLEO):
        arq = os.path.join(pasta, nome + ".svg")
        if os.path.exists(arq):
            return QIcon(arq)
    return QIcon(os.path.join(ICONES_NUCLEO, "gwater.svg"))


def paleta():
    p = QPalette()
    c = lambda k: QColor(COR[k])
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    p.setColor(R.Window, c("bg"))
    p.setColor(R.WindowText, c("text"))
    p.setColor(R.Base, c("panel"))
    p.setColor(R.AlternateBase, c("panel2"))
    p.setColor(R.ToolTipBase, c("panel2"))
    p.setColor(R.ToolTipText, c("text"))
    p.setColor(R.Text, c("text"))
    p.setColor(R.Button, c("btn"))
    p.setColor(R.ButtonText, c("text"))
    p.setColor(R.BrightText, c("warn"))
    p.setColor(R.Highlight, c("btn_on"))
    p.setColor(R.HighlightedText, c("text"))
    p.setColor(R.Link, c("cyan"))
    p.setColor(R.PlaceholderText, c("muted"))
    p.setColor(R.Mid, c("line"))
    p.setColor(R.Dark, c("bg"))
    p.setColor(R.Light, c("panel2"))
    for papel in (R.Text, R.WindowText, R.ButtonText):
        p.setColor(G.Disabled, papel, QColor(COR["muted"]).darker(140) if QColor(COR["bg"]).lightness() < 128
                   else QColor(COR["muted"]).lighter(140))
    return p


def fonte_app():
    f = QFont(CORPO)
    f.setPointSizeF(9)
    return f


def qss():
    c = COR
    return f"""
    QMainWindow, QDialog {{ background:{c['bg']}; }}
    QWidget {{ color:{c['text']}; }}
    QToolTip {{ background:{c['panel2']}; color:{c['text']}; border:1px solid {c['cyan']}; padding:6px; }}

    /* ---------------- faixa de menus (ribbon) ---------------- */
    QWidget#faixa {{ background:{c['panel']}; border-bottom:1px solid {c['line']}; }}
    QTabWidget#abasFaixa::pane {{ border:none; border-top:1px solid {c['line']}; background:{c['panel']}; top:-1px; }}
    QTabWidget#abasFaixa > QTabBar::tab {{ background:transparent; color:{c['muted']}; border:none;
        border-bottom:2px solid transparent; padding:7px 16px 6px 16px; margin:0 2px;
        font-family:'{CORPO}'; font-size:9.5pt; font-weight:600; }}
    QTabWidget#abasFaixa > QTabBar::tab:selected {{ color:{c['cyan']}; border-bottom:2px solid {c['cyan']};
        background:{c['panel2']}; border-top-left-radius:6px; border-top-right-radius:6px; }}
    QTabWidget#abasFaixa > QTabBar::tab:hover {{ color:{c['text']}; }}
    QFrame#grupoFaixa {{ background:transparent; border:none; border-right:1px solid {c['line']}; }}
    QLabel#tituloGrupo {{ color:{c['muted']}; font-size:8pt; padding-top:1px; }}
    QToolButton#botaoFaixa {{ background:transparent; border:1px solid transparent; border-radius:6px;
        color:{c['text']}; padding:2px 3px; font-size:8.5pt; }}
    QToolButton#botaoFaixa:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QToolButton#botaoFaixa:pressed, QToolButton#botaoFaixa:checked {{ background:{c['btn_on']};
        border-color:{c['cyan']}; }}
    QToolButton#botaoFaixa::menu-indicator {{ subcontrol-position:bottom center; subcontrol-origin:padding;
        width:7px; height:5px; bottom:1px; }}
    QToolButton#arquivo {{ background:{c['water']}; color:white; border:none; border-radius:5px; padding:5px 16px;
        font-weight:700; font-size:9.5pt; }}
    QToolButton#arquivo:hover {{ background:#2aa2ec; }}
    QToolButton#rapido {{ background:transparent; border:1px solid transparent; border-radius:5px; padding:3px; }}
    QToolButton#rapido:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QLabel#titulo {{ color:{c['text']}; font-family:'{DISPLAY}'; font-size:11pt; font-weight:600; }}
    QLabel#marcaTitulo {{ color:{c['cyan']}; font-family:'{DISPLAY}'; font-size:12pt; font-weight:700; }}

    /* ---------------- menus ---------------- */
    QMenuBar {{ background:{c['panel']}; color:{c['text']}; }}
    QMenu {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; padding:4px; }}
    QMenu::item {{ padding:6px 24px 6px 10px; border-radius:5px; }}
    QMenu::item:selected {{ background:{c['btn_on']}; }}
    QMenu::item:disabled {{ color:#55708f; }}
    QMenu::separator {{ height:1px; background:{c['line']}; margin:4px 6px; }}
    QMenu::icon {{ padding-left:6px; }}

    /* ---------------- painéis ---------------- */
    QDockWidget {{ color:{c['text']}; font-weight:600; titlebar-close-icon:none; }}
    QDockWidget::title {{ background:{c['panel2']}; border-bottom:1px solid {c['line']}; padding:6px 8px;
        text-align:left; }}
    QDockWidget::close-button, QDockWidget::float-button {{ background:transparent; border:none; padding:1px; }}
    QDockWidget::close-button:hover, QDockWidget::float-button:hover {{ background:{c['btn']}; }}
    QMainWindow::separator {{ background:{c['line']}; width:3px; height:3px; }}
    QMainWindow::separator:hover {{ background:{c['cyan']}; }}

    QTabWidget#centro::pane {{ border:1px solid {c['line']}; border-top:none; background:{c['bg']}; }}
    QTabWidget#centro > QTabBar::tab {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']};
        border-bottom:none; border-top-left-radius:7px; border-top-right-radius:7px; padding:6px 14px; margin-right:3px; }}
    QTabWidget#centro > QTabBar::tab:selected {{ background:{c['panel2']}; color:{c['cyan']}; border-color:{c['cyan']}; }}

    QTabWidget::pane {{ border:1px solid {c['line']}; border-radius:6px; top:-1px; }}
    QTabBar::tab {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']}; padding:5px 12px;
        border-top-left-radius:6px; border-top-right-radius:6px; margin-right:2px; }}
    QTabBar::tab:selected {{ color:{c['cyan']}; border-color:{c['cyan']}; background:{c['panel2']}; }}

    QGroupBox {{ border:1px solid {c['line']}; border-radius:8px; margin-top:14px; padding:10px 8px 8px 8px; }}
    QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; color:{c['cyan']}; font-weight:600; }}

    QPushButton {{ background:{c['btn']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:7px;
        padding:6px 14px; font-weight:600; }}
    QPushButton:hover {{ border-color:{c['cyan']}; }}
    QPushButton:pressed {{ background:{c['btn_on']}; }}
    QPushButton:default {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}
    QPushButton:disabled {{ color:#55708f; border-color:{c['grid']}; }}
    QToolButton {{ color:{c['text']}; }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QPlainTextEdit, QTextEdit {{
        background:{c['btn']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:6px; padding:3px 6px;
        selection-background-color:{c['btn_on']}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {{
        border-color:{c['cyan']}; }}
    QComboBox QAbstractItemView {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']};
        selection-background-color:{c['btn_on']}; }}
    QCheckBox, QRadioButton {{ spacing:7px; background:transparent; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width:14px; height:14px; border:1px solid {c['line']};
        background:{c['btn']}; border-radius:4px; }}
    QRadioButton::indicator {{ border-radius:8px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background:{c['cyan']}; border-color:{c['cyan']}; }}
    QCheckBox::indicator:checked {{ image:url({VISTO}); }}

    QTreeView, QListView, QTableView, QTreeWidget, QTableWidget, QListWidget {{ background:{c['panel']};
        alternate-background-color:{c['panel2']}; color:{c['text']}; border:1px solid {c['line']};
        gridline-color:{c['grid']}; selection-background-color:{c['btn_on']}; selection-color:{c['text']};
        outline:none; }}
    QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background:{c['btn']}; }}
    QHeaderView::section {{ background:{c['panel2']}; color:{c['muted']}; border:none;
        border-right:1px solid {c['grid']}; border-bottom:1px solid {c['line']}; padding:5px 7px;
        font-family:'{MONO}'; font-weight:600; }}
    QTableCornerButton::section {{ background:{c['panel2']}; border:none; }}

    QScrollBar:vertical {{ background:{c['bg']}; width:11px; margin:0; }}
    QScrollBar::handle:vertical {{ background:{c['line']}; border-radius:5px; min-height:30px; }}
    QScrollBar::handle:vertical:hover {{ background:{c['cyan']}; }}
    QScrollBar:horizontal {{ background:{c['bg']}; height:11px; margin:0; }}
    QScrollBar::handle:horizontal {{ background:{c['line']}; border-radius:5px; min-width:40px; }}
    QScrollBar::handle:horizontal:hover {{ background:{c['cyan']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; background:none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}

    QSlider::groove:horizontal {{ height:4px; background:{c['line']}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{c['cyan']}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:{c['cyan']}; width:14px; height:14px; margin:-5px 0; border-radius:7px; }}
    QProgressBar {{ background:{c['chip']}; border:1px solid {c['line']}; border-radius:6px; text-align:center;
        color:{c['text']}; height:14px; }}
    QProgressBar::chunk {{ background:{c['cyan']}; border-radius:5px; }}

    QStatusBar {{ background:{c['panel']}; color:{c['muted']}; border-top:1px solid {c['line']}; }}
    QStatusBar QLabel {{ color:{c['muted']}; padding:0 8px; }}
    QStatusBar::item {{ border:none; }}
    QTextBrowser {{ background:{c['panel']}; border:1px solid {c['line']}; border-radius:8px; padding:6px; }}
    QSplitter::handle {{ background:{c['line']}; }}
    """


def configurar(janela):
    """Configurações do programa: tema (claro ou escuro, com as cores de cada um)."""
    from qgis.PyQt.QtWidgets import QApplication, QComboBox, QFormLayout
    from .util import Dialogo
    d = Dialogo(janela, "Configurações", "Aparência do GWATER. O mapa não muda; alguns painéis só mudam ao reabri-los.",
                largura=420)
    f = QFormLayout()
    cmb = QComboBox()
    for n, c in TEMAS.items():
        cmb.addItem(("Escuro · " if QColor(c["bg"]).lightness() < 128 else "Claro · ") + n, n)
    cmb.setCurrentIndex(max(0, cmb.findData(tema_atual())))
    f.addRow("Tema:", cmb)
    d.lay.addLayout(f)
    d.botoes("Aplicar")
    if d.exec():
        aplicar_tema(cmb.currentData(), QApplication.instance())
        return True
    return False
