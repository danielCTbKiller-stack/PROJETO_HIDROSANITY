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


# ---------------------------------------------------------------- temas (Configurações)
# Os temas do GeoLogic Water ficam em temas.json, na pasta do hub (Projeto WaterConnect): o GPREDIAL lê o mesmo. Cada um tem
# cores, fontes e o arredondamento dos cantos. Sem o arquivo (GWATER sozinho), só o tema original.
def _ler_temas():
    import json
    rev = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    acima = [rev]
    for _ in range(6):
        acima.append(os.path.dirname(acima[-1]))
    for arq in [os.path.join(d, "temas.json") for d in acima]:
        try:
            with open(arq, encoding="utf-8") as fh:
                d = json.load(fh)
            return d["temas"], d.get("padrao")
        except (OSError, ValueError, KeyError):
            continue
    return {}, None


_ORIGINAL = dict(COR)
_LIDOS, PADRAO = _ler_temas()
TEMAS = {n: {**_ORIGINAL, **t["cores"]} for n, t in _LIDOS.items()} or {"Original": dict(_ORIGINAL)}
PADRAO = PADRAO if PADRAO in TEMAS else next(iter(TEMAS))
_ESTILO_ORIGINAL = {"corpo": CORPO, "display": DISPLAY, "mono": MONO, "abas": CORPO, "raio": 6}
ESTILO = dict(_ESTILO_ORIGINAL)  # fontes e cantos do tema em uso (o qss lê daqui)


def tema_atual():
    from .desempenho import configuracoes
    nome = configuracoes().value("tema", PADRAO)
    return nome if nome in TEMAS else PADRAO


def aplicar_tema(nome=None, app=None):
    """Troca as cores (COR é compartilhado por todo o programa), as fontes e os cantos, e reaplica paleta e folha
    de estilo. A escolha fica gravada nas configurações: vale ao abrir o GWATER de novo."""
    from .desempenho import configuracoes
    nome = nome if nome in TEMAS else tema_atual()
    COR.update(TEMAS[nome])
    t = _LIDOS.get(nome, {})
    ESTILO.clear()
    ESTILO.update(_ESTILO_ORIGINAL, **t.get("fontes", {}))
    ESTILO["raio"] = t.get("raio", 6)
    configuracoes().setValue("tema", nome)
    if app is not None:
        app.setPalette(paleta())
        app.setFont(fonte_app())
        app.setStyleSheet(qss())
    return nome


# cores com que os ícones de traço foram desenhados (icones/_gerar.py) -> chave do tema que entra no lugar
_TINTAS = {"#35d0ff": "cyan", "#e8f2ff": "text", "#86a3c9": "muted", "#0b2a58": "btn", "#1d8fd6": "water",
           "#3ddc97": "ok", "#ffb547": "warn", "#ff6b7a": "crit", "#a78bfa": "violet"}


def icone(nome):
    """Ícone com as cores do tema em uso: o SVG de traço ganha as cores do tema numa cópia (pasta temporária, uma
    por tema); os ilustrados não têm essas cores e ficam como são."""
    for pasta in (ICONES, ICONES_NUCLEO):
        arq = os.path.join(pasta, nome + ".svg")
        if os.path.exists(arq):
            return QIcon(_tingido(arq))
    return QIcon(os.path.join(ICONES_NUCLEO, "gwater.svg"))


def _tingido(arq):
    import hashlib
    import tempfile
    try:
        with open(arq, encoding="utf-8") as fh:
            svg = fh.read()
    except OSError:
        return arq
    if not any(c in svg for c in _TINTAS):
        return arq
    chave = hashlib.md5("".join(COR.get(k, "") for k in sorted(set(_TINTAS.values()))).encode()).hexdigest()[:10]
    pasta = os.path.join(tempfile.gettempdir(), "gwater_icones", chave)
    destino = os.path.join(pasta, os.path.basename(arq))
    if not os.path.exists(destino) or os.path.getmtime(destino) < os.path.getmtime(arq):
        for antiga, k in _TINTAS.items():
            svg = svg.replace(antiga, COR.get(k, antiga))
        try:
            os.makedirs(pasta, exist_ok=True)
            with open(destino, "w", encoding="utf-8") as fh:
                fh.write(svg)
        except OSError:
            return arq
    return destino


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
    f = QFont(ESTILO["corpo"])
    f.setPointSizeF(9)
    return f


def qss():
    c = COR
    CORPO, DISPLAY, MONO, ABAS = ESTILO["corpo"], ESTILO["display"], ESTILO["mono"], ESTILO["abas"]  # noqa: N806
    return _cantos(f"""
    QMainWindow, QDialog {{ background:{c['bg']}; }}
    QWidget {{ color:{c['text']}; }}
    QToolTip {{ background:{c['panel2']}; color:{c['text']}; border:1px solid {c['cyan']}; padding:6px; }}

    /* ---------------- faixa de menus (ribbon) ---------------- */
    QWidget#faixa {{ background:{c['panel']}; border-bottom:1px solid {c['line']}; }}
    QTabWidget#abasFaixa::pane {{ border:none; border-top:1px solid {c['line']}; background:{c['panel']}; top:-1px; }}
    QTabWidget#abasFaixa > QTabBar::tab {{ background:transparent; color:{c['muted']}; border:none;
        border-bottom:2px solid transparent; padding:7px 16px 6px 16px; margin:0 2px;
        font-family:'{ABAS}'; font-size:9.5pt; font-weight:600; }}
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
    QToolButton#arquivo {{ background:{c['cyan']}; color:{c['sobre']}; border:none; border-radius:5px; padding:5px 16px;
        font-weight:700; font-size:9.5pt; }}
    QToolButton#arquivo:hover {{ background:{c['water']}; }}
    QToolButton#rapido {{ background:transparent; border:1px solid transparent; border-radius:5px; padding:3px; }}
    QToolButton#rapido:hover {{ background:{c['btn']}; border-color:{c['line']}; }}
    QLabel#titulo {{ color:{c['text']}; font-family:'{DISPLAY}'; font-size:11pt; font-weight:600; }}
    QLabel#marcaTitulo {{ color:{c['cyan']}; font-family:'{DISPLAY}'; font-size:12pt; font-weight:700; }}

    /* ---------------- menus ---------------- */
    QMenuBar {{ background:{c['panel']}; color:{c['text']}; }}
    QMenu {{ background:{c['panel']}; color:{c['text']}; border:1px solid {c['line']}; padding:4px; }}
    QMenu::item {{ padding:6px 24px 6px 10px; border-radius:5px; }}
    QMenu::item:selected {{ background:{c['btn_on']}; }}
    QMenu::item:disabled {{ color:{c['muted']}; }}
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
    QPushButton:disabled {{ color:{c['muted']}; border-color:{c['grid']}; }}
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
    QRadioButton::indicator {{ border-radius: 8px; }}
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
    QSlider::handle:horizontal {{ background:{c['cyan']}; width:14px; height:14px; margin:-5px 0; border-radius: 7px; }}
    QProgressBar {{ background:{c['chip']}; border:1px solid {c['line']}; border-radius:6px; text-align:center;
        color:{c['text']}; height:14px; }}
    QProgressBar::chunk {{ background:{c['cyan']}; border-radius:5px; }}

    QStatusBar {{ background:{c['panel']}; color:{c['muted']}; border-top:1px solid {c['line']}; }}
    QStatusBar QLabel {{ color:{c['muted']}; padding:0 8px; }}
    QStatusBar::item {{ border:none; }}
    QTextBrowser {{ background:{c['panel']}; border:1px solid {c['line']}; border-radius:8px; padding:6px; }}
    QSplitter::handle {{ background:{c['line']}; }}
    """)


def _cantos(texto):
    """Os cantos (border-radius:Npx) na proporção do raio do tema; 6 px é o original. Os que têm espaço depois
    dos dois-pontos ficam como estão (bolinha do rádio e do controle deslizante)."""
    import re
    k = ESTILO["raio"] / 6
    return re.sub(r"border-radius:(\d+)px", lambda m: f"border-radius:{round(int(m.group(1)) * k)}px", texto)


def configurar(janela):
    """Configurações do programa: tema (claro ou escuro) e desempenho (núcleos do processador e memória RAM)."""
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QSpinBox
    from . import desempenho
    from .util import Dialogo
    d = Dialogo(janela, "Configurações", "Aparência e desempenho do GWATER. O tema escolhido fica gravado e vale "
                "também nas próximas vezes; é o mesmo do GPREDIAL. O mapa não muda de cor com o tema; alguns painéis só "
                "mudam ao reabri-los.", largura=520)
    f = QFormLayout()
    cmb = QComboBox()
    for n, c in TEMAS.items():
        cmb.addItem(n + ("  ·  padrão" if n == PADRAO else ""), n)
        cmb.setItemData(cmb.count() - 1, _LIDOS.get(n, {}).get("descricao", ""), Qt.ItemDataRole.ToolTipRole)
    cmb.setCurrentIndex(max(0, cmb.findData(tema_atual())))
    f.addRow("Tema:", cmb)
    d.lay.addLayout(f)
    cfg = desempenho.ler()
    total_n, total_mb = desempenho.nucleos_maquina(), desempenho.memoria_total_mb()
    caixa = QGroupBox("Desempenho")
    fd = QFormLayout(caixa)
    nuc = QSpinBox()
    nuc.setRange(1, total_n)
    nuc.setValue(cfg["nucleos"])
    nuc.setSuffix(f" de {total_n}")
    nuc.setToolTip("Threads do processador para o desenho do mapa e para as análises com muitos cálculos (incêndio, "
                   "descarga, criticidade, calibração). Todos = o máximo de velocidade.")
    mem = QSpinBox()
    mem.setRange(256, max(512, int(total_mb * 0.75)))
    mem.setSingleStep(256)
    mem.setValue(min(cfg["cache_mb"], mem.maximum()))
    mem.setSuffix(f" MB de {total_mb:,} MB".replace(",", "."))
    mem.setToolTip("Memória RAM para cache: leitura de rasters e do cadastro (GDAL e SQLite) e imagens dos mapas de "
                   "fundo. Mais memória = menos leitura de disco e de rede. Deixe sobrar RAM para o Windows e outros "
                   "programas.")
    par = QCheckBox("Desenhar as camadas do mapa em paralelo")
    par.setChecked(cfg["mapa_paralelo"])
    fps = QSpinBox()
    fps.setRange(5, 30)
    fps.setValue(cfg["fluxo_fps"])
    fps.setSuffix(" quadros/s")
    fps.setToolTip("Animação do fluxo da água: mais quadros = mais suave, e mais trabalho para o computador")
    fd.addRow("Núcleos (threads):", nuc)
    fd.addRow("Animação do fluxo:", fps)
    fd.addRow("Memória para cache:", mem)
    fd.addRow(par)
    dica = QLabel("A memória do cache do GDAL e do SQLite vale por completo ao reabrir o GWATER.")
    dica.setWordWrap(True)
    dica.setObjectName("sub")
    fd.addRow(dica)
    d.lay.addWidget(caixa)
    cx2 = QGroupBox("Salvamento")
    fs = QFormLayout(cx2)
    auto = QSpinBox()
    auto.setRange(0, 120)
    auto.setValue(cfg["auto_min"])
    auto.setSuffix(" min")
    auto.setSpecialValueText("desligado")
    auto.setToolTip("Grava sozinho as camadas do cadastro com edições, neste intervalo, quando você está parado "
                    "(não salva no meio de um desenho). Depois de salvar, o Ctrl+Z não volta antes do salvamento.")
    fs.addRow("Salvar automaticamente a cada:", auto)
    d.lay.addWidget(cx2)
    d.botoes("Aplicar")
    if d.exec():
        aplicar_tema(cmb.currentData(), QApplication.instance())
        desempenho.gravar(nuc.value(), mem.value(), par.isChecked(), auto.value(), fps.value())
        desempenho.aplicar(janela)
        if getattr(janela, "bt_fluxo", None) is not None and janela.bt_fluxo.isChecked():
            janela._fluxo(True, gravar=False)
        return True
    return False
