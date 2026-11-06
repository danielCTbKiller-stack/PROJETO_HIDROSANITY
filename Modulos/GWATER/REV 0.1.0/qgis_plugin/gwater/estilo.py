"""Identidade visual do GWATER no QGIS: a mesma do Centro de Operações web (painel/mapa.html).

As cores são as variáveis CSS do painel (--bg, --panel, --line, --cyan...). As fontes do painel
(Rajdhani, IBM Plex) vêm da internet; aqui usamos as equivalentes que o Windows já tem.
"""
import os

from qgis.PyQt.QtGui import QFont

VISTO = os.path.join(os.path.dirname(__file__), "icones", "visto.svg").replace("\\", "/")

COR = {
    "bg": "#050f24", "panel": "#0a1d3e", "panel2": "#0d2650", "line": "#16427a", "grid": "#17345f",
    "text": "#e8f2ff", "muted": "#86a3c9", "cyan": "#35d0ff", "water": "#1d8fd6",
    "ok": "#3ddc97", "warn": "#ffb547", "crit": "#ff6b7a", "violet": "#a78bfa",
    "btn": "#0b2a58", "btn_on": "#0e4a8c", "chip": "#081833",
}
DISPLAY = "Bahnschrift"     # no painel: Rajdhani
CORPO = "Segoe UI"          # no painel: IBM Plex Sans
MONO = "Consolas"           # no painel: IBM Plex Mono


def fonte(tipo, tamanho, negrito=False, espaco=0.0):
    """espaco: espaçamento entre letras em % (o QSS do Qt não tem letter-spacing)."""
    f = QFont({"display": DISPLAY, "mono": MONO}.get(tipo, CORPO))
    f.setPointSizeF(tamanho)
    f.setBold(negrito)
    if espaco:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + espaco)
    return f


def qss():
    c = COR
    return f"""
    QWidget#gwater {{ background:{c['bg']}; color:{c['text']}; font-family:'{CORPO}'; font-size:9pt; }}
    QWidget#gwater QLabel {{ background:transparent; color:{c['text']}; }}
    QWidget#gwater QLabel#sub, QWidget#gwater QLabel#rotulo {{ color:{c['muted']}; }}
    QWidget#gwater QLabel#h3 {{ color:{c['cyan']}; }}

    QFrame#card {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['panel2']}, stop:1 {c['panel']});
                   border:1px solid {c['line']}; border-radius:10px; }}
    QFrame#ajuda {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {c['panel2']}, stop:1 {c['panel']});
                    border:1px solid {c['line']}; border-left:3px solid {c['cyan']}; border-radius:10px; }}
    QLabel#status {{ background:{c['chip']}; border:1px solid {c['line']}; border-radius:8px; padding:6px 9px;
                     color:{c['text']}; }}
    QLabel#chip {{ background:{c['chip']}; border:1px solid {c['line']}; border-radius:9px; padding:2px 8px;
                   color:{c['muted']}; }}

    QToolButton#acao {{ background:{c['btn']}; border:1px solid {c['line']}; border-radius:8px; padding:4px;
                        color:{c['text']}; }}
    QToolButton#acao:hover {{ border-color:{c['cyan']}; }}
    QToolButton#acao:pressed {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}
    QPushButton {{ background:{c['btn']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:8px;
                   padding:6px 12px; font-weight:600; }}
    QPushButton:hover {{ border-color:{c['cyan']}; }}
    QPushButton:pressed, QPushButton:default {{ background:{c['btn_on']}; border-color:{c['cyan']}; }}

    QComboBox, QLineEdit, QDoubleSpinBox, QSpinBox {{ background:{c['btn']}; color:{c['text']};
        border:1px solid {c['line']}; border-radius:8px; padding:4px 8px; selection-background-color:{c['btn_on']}; }}
    QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover {{ border-color:{c['cyan']}; }}
    QComboBox::drop-down {{ border:none; width:18px; }}
    QComboBox QAbstractItemView {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']};
        selection-background-color:{c['btn_on']}; }}
    QCheckBox, QRadioButton {{ color:{c['text']}; background:transparent; spacing:7px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width:14px; height:14px; border:1px solid {c['line']};
        background:{c['btn']}; border-radius:4px; }}
    QRadioButton::indicator {{ border-radius:8px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background:{c['cyan']}; border-color:{c['cyan']}; }}
    QCheckBox::indicator:checked {{ image:url({VISTO}); }}

    QTabWidget::pane {{ border:none; background:transparent; top:-1px; }}
    QTabBar::tab {{ background:{c['chip']}; color:{c['muted']}; border:1px solid {c['line']}; border-radius:8px;
        padding:6px 12px; margin-right:6px; }}
    QTabBar::tab:selected {{ color:{c['cyan']}; border-color:{c['cyan']}; }}
    QTabBar::tab:hover {{ color:{c['text']}; }}

    QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:none; }}
    QScrollBar:vertical {{ background:{c['bg']}; width:10px; margin:0; }}
    QScrollBar::handle:vertical {{ background:{c['line']}; border-radius:5px; min-height:30px; }}
    QScrollBar::handle:vertical:hover {{ background:{c['cyan']}; }}
    QScrollBar:horizontal {{ background:{c['bg']}; height:10px; margin:0; }}
    QScrollBar::handle:horizontal {{ background:{c['line']}; border-radius:5px; min-width:40px; }}
    QScrollBar::handle:horizontal:hover {{ background:{c['cyan']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; background:none; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}

    QListWidget {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:10px;
        padding:4px; outline:none; }}
    QListWidget::item {{ padding:6px 8px; border-radius:6px; }}
    QListWidget::item:selected {{ background:{c['btn_on']}; color:{c['text']}; border:1px solid {c['cyan']}; }}
    QListWidget::item:hover {{ background:{c['btn']}; }}
    QTableWidget {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:10px;
        gridline-color:{c['grid']}; selection-background-color:{c['btn_on']}; }}
    QHeaderView::section {{ background:{c['panel2']}; color:{c['muted']}; border:none;
        border-bottom:1px solid {c['line']}; padding:6px 8px; font-family:'{MONO}'; font-weight:600; }}
    QSlider::groove:horizontal {{ height:4px; background:{c['line']}; border-radius:2px; }}
    QSlider::sub-page:horizontal {{ background:{c['cyan']}; border-radius:2px; }}
    QSlider::handle:horizontal {{ background:{c['cyan']}; width:14px; height:14px; margin:-5px 0; border-radius:7px; }}
    QTextBrowser {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; border-radius:10px;
        padding:8px; }}
    QDialogButtonBox QPushButton {{ min-width:90px; }}
    """


def css_html():
    """Estilo do Guia (QTextBrowser com HTML)."""
    c = COR
    return (f"<style>body{{color:{c['text']};font-family:'{CORPO}'}} h2{{color:{c['text']};font-family:'{DISPLAY}'}}"
            f" h3{{color:{c['cyan']};font-family:'{MONO}';text-transform:uppercase}} i{{color:{c['muted']}}}"
            f" td{{border-bottom:1px solid {c['grid']}}} b{{color:{c['text']}}}</style>")
