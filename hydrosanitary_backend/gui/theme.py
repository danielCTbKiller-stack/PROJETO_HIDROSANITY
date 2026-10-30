"""Identidade visual: a mesma do GWATER (Centro de Operações): fundo azul-noite, painéis em degradê,
destaque ciano, fontes Bahnschrift (títulos), Segoe UI (corpo) e Consolas (números)."""
from PySide6.QtGui import QColor, QFont, QPalette

COR = {
    "bg": "#050f24", "panel": "#0a1d3e", "panel2": "#0d2650", "line": "#16427a", "grid": "#17345f",
    "text": "#e8f2ff", "muted": "#86a3c9", "cyan": "#35d0ff", "water": "#1d8fd6", "flow": "#9cecff",
    "ok": "#3ddc97", "warn": "#ffb547", "crit": "#ff6b7a", "violet": "#a78bfa",
    "btn": "#0b2a58", "btn_on": "#0e4a8c", "chip": "#081833",
}
DISPLAY = "Bahnschrift"
CORPO = "Segoe UI"
MONO = "Consolas"


def fonte(tipo="corpo", tamanho=9.0, negrito=False):
    f = QFont({"display": DISPLAY, "mono": MONO}.get(tipo, CORPO))
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
    return f"""
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
    QFrame#faixa {{ background:{c['panel']}; border:1px solid {c['line']}; border-radius:10px; }}
    QFrame#grupo {{ background:transparent; border:none; border-right:1px solid {c['grid']}; }}
    QLabel#grupoTitulo {{ color:{c['muted']}; font-family:'{MONO}'; font-size:7.5pt; letter-spacing:1px; }}
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
                       padding:5px 12px; font-family:'{MONO}'; font-weight:600; letter-spacing:1px; }}
    QToolButton#aba:checked {{ color:{c['cyan']}; border-bottom-color:{c['cyan']}; }}
    QToolButton#aba:hover {{ color:{c['text']}; }}
    QToolButton#acao {{ background:transparent; color:{c['text']}; border:1px solid transparent; border-radius:8px;
                        padding:3px 4px; font-size:8pt; }}
    QToolButton#acao:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QToolButton#acao:checked {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}
    QToolButton#acao:pressed {{ background:{c['btn_on']}; }}

    QPushButton {{ background:{c['btn']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:8px;
                   padding:6px 12px; font-weight:600; }}
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

    QDockWidget {{ color:{c['cyan']}; font-family:'{MONO}'; font-weight:600; }}
    QDockWidget::title {{ background:{c['panel2']}; padding:6px 10px; border-bottom:1px solid {c['line']}; }}
    QTabWidget::pane {{ border:none; background:transparent; top:-1px; }}
    QTabBar::tab {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']}; border-radius:7px;
        padding:5px 11px; margin:3px 5px 3px 0; font-family:'{MONO}'; font-weight:600; }}
    QTabBar::tab:selected {{ color:{c['cyan']}; border-color:{c['cyan']}; }}
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
    QSlider::handle:horizontal {{ background:{c['cyan']}; width:12px; height:12px; margin:-4px 0; border-radius:6px; }}
    QStatusBar {{ background:{c['panel']}; color:{c['muted']}; border-top:1px solid {c['line']}; font-family:'{MONO}'; }}
    QStatusBar QLabel {{ color:{c['muted']}; padding:0 8px; }}
    QSplitter::handle {{ background:{c['bg']}; }}
    QMenu {{ background:{c['panel']}; border:1px solid {c['line']}; }}
    QMenu::item:selected {{ background:{c['btn_on']}; }}
    QScrollArea {{ border:none; }}
    """
