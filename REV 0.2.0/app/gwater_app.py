"""GWATER · programa à parte (REV 0.2.0).

Usa as bibliotecas do QGIS (mapa, edição, formatos) sem abrir o QGIS: a janela, a faixa de menus e as
ferramentas são do GWATER. O cálculo é do motor (EPANET 2.2 pelo WNTR), no Python da pasta (.venv).

Uso:  GWATER.exe [cadastro.qgz | cadastro.gpkg]
      (ou, sem o .exe: <QGIS>\\bin\\python-qgis.bat gwater_app.py)
"""
import os
import sys
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

# o navegador embutido (telas do Centro de Operações) não sobe com o isolamento do Chromium dentro do Python do
# QGIS; ele só abre as telas locais do GWATER e os mapas de fundo
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
if "--no-sandbox" not in os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""):
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "") + " --no-sandbox").strip()

from qgis.PyQt.QtCore import Qt  # noqa: E402

try:  # o visualizador web precisa ser carregado antes de criar o aplicativo
    from qgis.PyQt import QtWebEngineWidgets  # noqa: F401,E402
except ImportError:
    pass
from qgis.PyQt.QtWidgets import QApplication, QMessageBox, QSplashScreen  # noqa: E402

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from qgis.core import QgsApplication  # noqa: E402


def registro(arq):
    """Erros não tratados vão para gwater_erros.log (e para uma mensagem), sem derrubar o programa."""
    def gancho(tipo, valor, tb):
        texto = "".join(traceback.format_exception(tipo, valor, tb))
        try:
            with open(arq, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S}\n{texto}")
        except OSError:
            pass
        sys.__stderr__ and sys.__stderr__.write(texto)
        app = QApplication.instance()
        if app is not None and not os.environ.get("GWATER_TESTE"):
            QMessageBox.warning(None, "GWATER", f"Ocorreu um erro inesperado:\n\n{valor}\n\nDetalhes em {arq}")
    sys.excepthook = gancho


def criar_aplicativo():
    """QgsApplication só com o nome do programa: os outros argumentos são do GWATER (arquivo a abrir).
    O navegador embutido (Chromium) precisa do nome; no QGIS 4 ele vai em bytes, no 3 em texto."""
    nome = sys.argv[0] if sys.argv and sys.argv[0] else "GWATER"
    try:
        return QgsApplication([nome.encode()], True)
    except TypeError:
        return QgsApplication([nome], True)


def abertura(app, duracao=2600):
    """Logo animado de abertura (uma das animações de programa/abertura.html, sorteada). Roda a animação
    inteira antes de montar a janela, que congela a tela enquanto carrega. None se não houver navegador."""
    if os.environ.get("GWATER_TESTE") or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return None
    try:
        from qgis.PyQt.QtCore import QEventLoop, QTimer, QUrl
        from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        return None
    import random
    v = QWebEngineView()
    v.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
    v.setFixedSize(560, 320)
    v.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    url = QUrl.fromLocalFile(os.path.join(AQUI, "programa", "abertura.html"))
    url.setFragment(str(random.randrange(4)))
    v.load(url)
    tela = app.primaryScreen().availableGeometry()
    v.move(tela.center().x() - 280, tela.center().y() - 160)
    laco = QEventLoop()
    v.loadFinished.connect(lambda _ok: (v.show(), QTimer.singleShot(duracao, laco.quit)))
    QTimer.singleShot(duracao + 4000, laco.quit)  # se a página não carregar, segue sem ela
    laco.exec()
    return v if v.isVisible() else (v.deleteLater() or None)


def main(argv):
    prefixo = os.environ.get("QGIS_PREFIX_PATH")
    if prefixo:
        QgsApplication.setPrefixPath(prefixo, True)
    app = criar_aplicativo()
    app.setApplicationName("GWATER")
    app.setOrganizationName("GWATER")
    app.initQgis()
    registro(os.path.join(os.path.dirname(AQUI), "gwater_erros.log"))

    from programa import tema
    app.setStyle("Fusion")
    tema.aplicar_tema()
    app.setPalette(tema.paleta())
    app.setFont(tema.fonte_app())
    app.setStyleSheet(tema.qss())
    app.setWindowIcon(tema.icone("gwater"))
    splash = abertura(app) or QSplashScreen(tema.icone("marca").pixmap(220, 220))
    if isinstance(splash, QSplashScreen):
        splash.showMessage("GWATER · carregando…", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                           Qt.GlobalColor.white)
        splash.show()
    app.processEvents()

    from programa.janela import Janela
    janela = Janela()
    janela.showMaximized()
    if isinstance(splash, QSplashScreen):
        splash.finish(janela)
    else:
        splash.close()
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args and os.environ.get("GWATER_ABRIR"):  # o GWATER.exe passa o arquivo por aqui
        args = [os.environ["GWATER_ABRIR"]]
    if args and os.path.exists(args[0]):
        arq = args[0]
        if arq.lower().endswith(".gpkg"):
            arq = janela.projeto_do_gpkg(arq)
        if arq:
            janela.abrir_projeto(arq)
    rc = app.exec()
    app.exitQgis()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
