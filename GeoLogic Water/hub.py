"""GeoLogic Water: o hub dos programas (GWATER, GPREDIAL e os que vierem).

O hub não tem programa próprio: lê a lista em programas.json (nesta pasta) e abre o escolhido, cada um na sua pasta
dentro de Modulos/ (GWATER, GPREDIAL, GFLOOD…), ao lado desta. Para integrar outro programa basta acrescentar um item na lista. O tema vem de
temas.json, com a escolha gravada pelo GPREDIAL (Configurações); sem escolha, o padrão (Verde Saneamento).

Uso:  pythonw hub.py        (o "GeoLogic Water.exe" desta pasta faz isso, com o Python do GPREDIAL)
Precisa só do PySide6.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent  # a pasta com o hub e os programas lado a lado
sys.path.insert(0, str(AQUI))
import seletor  # noqa: E402  (o mesmo do GWATER e do GPREDIAL)

ORIGINAL = {"bg": "#050f24", "panel": "#0a1d3e", "panel2": "#0d2650", "line": "#16427a", "grid": "#17345f",
            "text": "#e8f2ff", "muted": "#86a3c9", "cyan": "#35d0ff", "water": "#1d8fd6", "ok": "#3ddc97",
            "warn": "#ffb547", "crit": "#ff6b7a", "violet": "#a78bfa", "btn": "#0b2a58", "btn_on": "#0e4a8c",
            "chip": "#081833", "sobre": "#ffffff"}


def _json(nome, padrao):
    try:
        return json.loads((AQUI / nome).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def programas():
    return _json("programas.json", {}).get("programas", [])


def tema():
    """(cores, fontes) do tema escolhido (o mesmo QSettings do GPREDIAL) ou do padrão."""
    d = _json("temas.json", {})
    temas = d.get("temas", {})
    nome = QSettings("GeoLogic Water", "GeoLogic Water").value("tema", d.get("padrao"))
    t = temas.get(nome) or temas.get(d.get("padrao")) or {}
    return {**ORIGINAL, **t.get("cores", {})}, {"corpo": "Segoe UI", "display": "Bahnschrift", **t.get("fontes", {})}


def _ambiente():
    """Ambiente sem as variáveis do Python do hub: cada programa usa o seu (o GWATER traz o do QGIS)."""
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("PYTHON", "QT_", "VIRTUAL_ENV"))}
    scripts = os.path.normcase(os.path.dirname(sys.executable))
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if p and os.path.normcase(p) != scripts)
    return env


def abrir(prog):
    """Abre pelo primeiro comando que existir (caminhos relativos à pasta de cima). Devolve o erro, ou None."""
    for cmd in prog.get("comandos", []):
        exe = RAIZ / cmd[0]
        if exe.exists():
            try:
                subprocess.Popen([str(exe)] + list(cmd[1:]), cwd=str(RAIZ / prog.get("pasta", "")), env=_ambiente())
                return None
            except OSError as e:
                return str(e)
    return f"não encontrei {prog['comandos'][0][0]} em {RAIZ}" if prog.get("comandos") else "programa sem comando"


def _icone(cor):
    pm = QPixmap(64, 64)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    seletor._gota(p, seletor.QPointF(32, 34), 28, cor)
    p.end()
    return QIcon(pm)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GeoLogic Water")
    app.setStyle("Fusion")
    cor, fontes = tema()
    pal = QPalette()
    for papel, k in ((QPalette.Window, "bg"), (QPalette.WindowText, "text"), (QPalette.Base, "panel"),
                     (QPalette.Text, "text"), (QPalette.Button, "btn"), (QPalette.ButtonText, "text"),
                     (QPalette.Highlight, "btn_on"), (QPalette.HighlightedText, "text")):
        pal.setColor(papel, QColor(cor[k]))
    app.setPalette(pal)
    app.setFont(QFont(fontes["corpo"], 9))
    app.setWindowIcon(_icone(cor["cyan"]))
    seletor.mostrar(None, None, programas(), abrir, cor, fontes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
