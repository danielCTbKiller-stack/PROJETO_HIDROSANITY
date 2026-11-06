"""Identidade visual: os temas do GeoLogic Water, os mesmos do hub e do GWATER (GeoLogic Water/temas.json).

Cada tema tem cores (nomes do Centro de Operações: cyan = destaque, sobre = texto em cima do destaque), fontes e o
arredondamento dos cantos. O escolhido em Configurações fica gravado (QSettings, o mesmo do hub) e vale ao abrir
de novo.
"""
import json
import re
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QPalette

COR = {
    "bg": "#050f24", "panel": "#0a1d3e", "panel2": "#0d2650", "line": "#16427a", "grid": "#17345f",
    "text": "#e8f2ff", "muted": "#86a3c9", "cyan": "#35d0ff", "water": "#1d8fd6", "flow": "#9cecff",
    "ok": "#3ddc97", "warn": "#ffb547", "crit": "#ff6b7a", "violet": "#a78bfa",
    "btn": "#0b2a58", "btn_on": "#0e4a8c", "chip": "#081833", "sobre": "#ffffff",
}
DISPLAY = "Bahnschrift"
CORPO = "Segoe UI"
MONO = "Consolas"
_ORIGINAL = dict(COR)
_ESTILO_ORIGINAL = {"corpo": CORPO, "display": DISPLAY, "mono": MONO, "abas": MONO, "raio": 8}
ESTILO = dict(_ESTILO_ORIGINAL)


def _ler_temas():
    try:
        arq = next(d / "GeoLogic Water" / "temas.json" for d in Path(__file__).resolve().parents
                   if (d / "GeoLogic Water" / "temas.json").is_file())
        d = json.loads(arq.read_text(encoding="utf-8"))
        return d["temas"], d.get("padrao")
    except (OSError, ValueError, KeyError, StopIteration):
        return {}, None


TEMAS, PADRAO = _ler_temas()
PADRAO = PADRAO if PADRAO in TEMAS else None


def configuracoes():
    return QSettings("GeoLogic Water", "GeoLogic Water")  # o hub lê o mesmo tema


def tema_atual():
    nome = configuracoes().value("tema", PADRAO)
    return nome if nome in TEMAS else PADRAO


def aplicar_tema(nome=None, app=None):
    """Cores, fontes e cantos do tema (o escolhido fica gravado); com `app`, reaplica paleta e folha de estilo."""
    nome = nome if nome in TEMAS else tema_atual()
    COR.clear()
    COR.update(_ORIGINAL)
    ESTILO.clear()
    ESTILO.update(_ESTILO_ORIGINAL)
    if nome:
        t = TEMAS[nome]
        COR.update(t["cores"])
        ESTILO.update(t.get("fontes", {}))
        ESTILO["raio"] = t.get("raio", 8)
        configuracoes().setValue("tema", nome)
    if app is not None:
        app.setPalette(paleta())
        app.setFont(fonte("corpo", 9))
        app.setStyleSheet(qss())
    return nome


def escuro():
    return QColor(COR["bg"]).lightness() < 128


def fonte(tipo="corpo", tamanho=9.0, negrito=False):
    f = QFont(ESTILO.get(tipo, ESTILO["corpo"]))
    f.setPointSizeF(tamanho)
    f.setBold(negrito)
    return f


def paleta():
    c = COR
    p = QPalette()
    for role, cor in ((QPalette.Window, c["bg"]), (QPalette.WindowText, c["text"]), (QPalette.Base, c["panel"]),
                      (QPalette.AlternateBase, c["panel2"]), (QPalette.Text, c["text"]), (QPalette.Button, c["btn"]),
                      (QPalette.ButtonText, c["text"]), (QPalette.Highlight, c["btn_on"]),
                      (QPalette.HighlightedText, c["text"]), (QPalette.ToolTipBase, c["panel2"]),
                      (QPalette.ToolTipText, c["text"]), (QPalette.PlaceholderText, c["muted"])):
        p.setColor(role, QColor(cor))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(c["muted"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["muted"]))
    return p


def qss():
    c = COR
    CORPO, DISPLAY, MONO, ABAS = ESTILO["corpo"], ESTILO["display"], ESTILO["mono"], ESTILO["abas"]  # noqa: N806
    return _cantos(f"""
    QMainWindow, QWidget {{ background:{c['bg']}; color:{c['text']}; font-family:'{CORPO}'; font-size:9pt; }}
    QToolTip {{ background:{c['panel2']}; color:{c['text']}; border:1px solid {c['cyan']}; padding:5px; }}
    QLabel {{ background:transparent; }}
    QLabel#sub, QLabel#rotulo {{ color:{c['muted']}; }}
    QLabel#h1 {{ font-family:'{DISPLAY}'; font-size:15pt; font-weight:700; }}
    QLabel#h3 {{ color:{c['cyan']}; font-family:'{MONO}'; font-weight:600; letter-spacing:1px; }}
    QLabel#chip {{ background:{c['chip']}; border:1px solid {c['line']}; border-radius:10px; padding:3px 9px;
                   color:{c['muted']}; font-family:'{MONO}'; font-size:8pt; font-weight:600; }}
    QLabel#chip[estado="ok"] {{ color:{c['ok']}; border-color:#1f7a5a; }}
    QLabel#chip[estado="warn"] {{ color:{c['warn']}; border-color:#8a5d17; }}
    QLabel#chip[estado="crit"] {{ color:{c['crit']}; border-color:#8a2a38; }}

    QFrame#cabecalho, QFrame#card {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['panel2']}, stop:1 {c['panel']});
                   border:1px solid {c['line']}; border-radius:10px; }}
    QFrame#faixa {{ background:{c['panel']}; border:none; border-bottom:1px solid {c['line']}; border-radius:0; }}
    QStackedWidget#corpoFaixa, QStackedWidget#corpoFaixa > QWidget {{ background:{c['panel']}; }}
    QStackedWidget#corpoFaixa {{ border-top:1px solid {c['line']}; }}
    QFrame#grupo {{ background:transparent; border:none; border-right:1px solid {c['line']}; }}
    QLabel#grupoTitulo {{ color:{c['muted']}; font-size:8pt; padding-top:1px; }}
    QFrame#kpi {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['panel2']}, stop:1 {c['panel']});
                  border:1px solid {c['line']}; border-radius:10px; }}
    QLabel#kpiK {{ color:{c['muted']}; font-family:'{MONO}'; font-size:7.5pt; font-weight:600; letter-spacing:1px; }}
    QLabel#kpiV {{ font-family:'{DISPLAY}'; font-size:19pt; font-weight:600; }}
    QLabel#kpiV[estado="ok"] {{ color:{c['ok']}; }} QLabel#kpiV[estado="warn"] {{ color:{c['warn']}; }}
    QLabel#kpiV[estado="crit"] {{ color:{c['crit']}; }}

    QToolButton#nav {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']}; border-radius:8px;
                       padding:7px 14px; font-family:'{MONO}'; font-weight:600; letter-spacing:1px; }}
    QToolButton#nav:checked {{ color:{c['cyan']}; border-color:{c['cyan']}; }}
    QToolButton#nav:hover {{ color:{c['text']}; }}
    QToolButton#aba {{ background:transparent; color:{c['muted']}; border:none; border-bottom:2px solid transparent;
                       padding:7px 16px 6px 16px; margin:0 2px; font-family:'{ABAS}'; font-size:9.5pt; font-weight:600; }}
    QToolButton#aba:checked {{ color:{c['cyan']}; border-bottom-color:{c['cyan']}; background:{c['panel2']};
                       border-top-left-radius:6px; border-top-right-radius:6px; }}
    QToolButton#aba:hover {{ color:{c['text']}; }}
    QToolButton#acao {{ background:transparent; color:{c['text']}; border:1px solid transparent; border-radius:6px;
                        padding:2px 3px; font-size:8.5pt; }}
    QToolButton#acao:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QToolButton#acao:checked {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}
    QToolButton#acao:pressed {{ background:{c['btn_on']}; }}
    QToolButton#arquivo {{ background:{c['cyan']}; color:{c['sobre']}; border:none; border-radius:5px; padding:5px 16px;
                           font-weight:700; font-size:9.5pt; }}
    QToolButton#arquivo:hover {{ background:{c['water']}; }}
    QToolButton#arquivo::menu-indicator {{ subcontrol-position:right bottom; }}
    QToolButton#rapido {{ background:transparent; border:1px solid transparent; border-radius:5px; padding:3px; }}
    QToolButton#rapido:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QLabel#marcaTitulo {{ color:{c['cyan']}; font-family:'{DISPLAY}'; font-size:12pt; font-weight:700; }}

    QPushButton {{ background:{c['btn']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:7px;
                   padding:6px 14px; font-weight:600; }}
    QPushButton:disabled {{ color:{c['muted']}; border-color:{c['grid']}; }}
    QPushButton:hover {{ border-color:{c['cyan']}; }}
    QPushButton:pressed, QPushButton#pri {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}
    QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {{ background:{c['btn']}; color:{c['text']};
        border:1px solid {c['line']}; border-radius:7px; padding:3px 7px; selection-background-color:{c['btn_on']}; }}
    QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color:{c['cyan']}; }}
    QComboBox::drop-down {{ border:none; width:16px; }}
    QComboBox QAbstractItemView {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']};
        selection-background-color:{c['btn_on']}; }}
    QCheckBox {{ color:{c['text']}; background:transparent; spacing:7px; }}
    QCheckBox::indicator {{ width:13px; height:13px; border:1px solid {c['line']}; background:{c['btn']}; border-radius:4px; }}
    QCheckBox::indicator:checked {{ background:{c['cyan']}; border-color:{c['cyan']}; }}

    QDockWidget {{ color:{c['text']}; font-weight:600; }}
    QDockWidget::title {{ background:{c['panel2']}; border-bottom:1px solid {c['line']}; padding:6px 8px; text-align:left; }}
    QDockWidget::close-button, QDockWidget::float-button {{ background:transparent; border:none; padding:1px; }}
    QDockWidget::close-button:hover, QDockWidget::float-button:hover {{ background:{c['btn']}; }}
    QMainWindow::separator {{ background:{c['line']}; width:3px; height:3px; }}
    QMainWindow::separator:hover {{ background:{c['cyan']}; }}
    QGroupBox {{ border:1px solid {c['line']}; border-radius:8px; margin-top:14px; padding:10px 8px 8px 8px; }}
    QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; color:{c['cyan']}; font-weight:600; }}
    QTabWidget::pane {{ border:none; background:transparent; top:-1px; }}
    QTabBar::tab {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']}; padding:5px 12px;
        border-top-left-radius:6px; border-top-right-radius:6px; margin-right:2px; }}
    QTabBar::tab:selected {{ color:{c['cyan']}; border-color:{c['cyan']}; background:{c['panel2']}; }}
    QListWidget, QTableWidget, QTextBrowser {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']};
        border-radius:9px; gridline-color:{c['grid']}; selection-background-color:{c['btn_on']}; outline:none; }}
    QListWidget::item {{ padding:5px 7px; border-radius:6px; }}
    QListWidget::item:selected {{ background:{c['btn_on']}; border:1px solid {c['cyan']}; }}
    QHeaderView::section {{ background:{c['panel2']}; color:{c['muted']}; border:none; border-bottom:1px solid {c['line']};
        padding:5px 7px; font-family:'{MONO}'; font-weight:600; }}
    QTableCornerButton::section {{ background:{c['panel2']}; border:none; }}
    QScrollBar:vertical {{ background:{c['bg']}; width:10px; margin:0; }}
    QScrollBar::handle:vertical {{ background:{c['line']}; border-radius:5px; min-height:30px; }}
    QScrollBar:horizontal {{ background:{c['bg']}; height:10px; margin:0; }}
    QScrollBar::handle:horizontal {{ background:{c['line']}; border-radius:5px; min-width:40px; }}
    QScrollBar::handle:hover {{ background:{c['cyan']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; background:none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}
    QSlider::groove:horizontal {{ height:4px; background:{c['line']}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{c['cyan']}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:{c['cyan']}; width:12px; height:12px; margin:-4px 0; border-radius: 6px; }}
    QStatusBar {{ background:{c['panel']}; color:{c['muted']}; border-top:1px solid {c['line']}; }}
    QStatusBar::item {{ border:none; }}
    QStatusBar QLabel {{ color:{c['muted']}; padding:0 8px; }}
    QSplitter::handle {{ background:{c['line']}; }}
    QMenu {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; padding:4px; }}
    QMenu::item {{ padding:6px 24px 6px 10px; border-radius:5px; }}
    QMenu::item:selected {{ background:{c['btn_on']}; }}
    QMenu::item:disabled {{ color:{c['muted']}; }}
    QMenu::separator {{ height:1px; background:{c['line']}; margin:4px 6px; }}
    QMenu::icon {{ padding-left:6px; }}
    QScrollArea {{ border:none; }}
    """)


def _cantos(texto):
    """Cantos (border-radius:Npx) na proporção do raio do tema; 8 px é o original. Com espaço depois dos
    dois-pontos ficam como estão (bolinhas do controle deslizante)."""
    k = ESTILO["raio"] / 8
    return re.sub(r"border-radius:(\d+)px", lambda m: f"border-radius:{round(int(m.group(1)) * k)}px", texto)
