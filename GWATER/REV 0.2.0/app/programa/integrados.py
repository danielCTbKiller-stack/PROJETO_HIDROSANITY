"""Programas integrados do HIDROSANITY: a gota no canto da faixa abre esta janela.

A lista fica em programas.json, na raiz do repositório (duas pastas acima de REV 0.2.0); o GPREDIAL lê o mesmo
arquivo (hydrosanitary_backend/gui/integrados.py). Sem a lista (GWATER sozinho), mostra só o GWATER.
"""
import json
import os
import subprocess

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QDialog, QLabel, QMessageBox, QSizePolicy, QToolButton, QVBoxLayout

from .tema import COR, icone

REV = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../GWATER/REV 0.2.0
RAIZ = os.path.dirname(os.path.dirname(REV))
ICONES = {"rede": "mapa", "predio": "estacao", "gota": "marca"}


def programas():
    try:
        with open(os.path.join(RAIZ, "programas.json"), encoding="utf-8") as f:
            return json.load(f)["programas"]
    except (OSError, ValueError, KeyError):
        return [{"id": "gwater", "nome": "GWATER", "descricao": "Redes de distribuição de água", "icone": "rede"}]


def abrir(prog):
    """Abre pelo primeiro comando que existir. Devolve o erro, ou None."""
    for cmd in prog.get("comandos", []):
        exe = os.path.join(RAIZ, *cmd[0].split("/"))
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe] + list(cmd[1:]), cwd=os.path.join(RAIZ, *prog.get("pasta", "").split("/")))
                return None
            except OSError as e:
                return str(e)
    return f"não encontrei o programa em {RAIZ}"


def escolher(janela, atual="gwater"):
    dlg = QDialog(janela)
    dlg.setWindowTitle("HIDROSANITY · programas integrados")
    dlg.setMinimumWidth(460)
    col = QVBoxLayout(dlg)
    col.setContentsMargins(18, 16, 18, 16)
    col.setSpacing(8)
    t = QLabel("PROGRAMAS INTEGRADOS")
    t.setStyleSheet(f"color:{COR['cyan']}; font-weight:700; letter-spacing:1px;")
    col.addWidget(t)
    s = QLabel("Escolha o programa que quer iniciar.")
    s.setStyleSheet(f"color:{COR['muted']};")
    col.addWidget(s)
    for prog in programas():
        aberto = prog["id"] == atual
        b = QToolButton()
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setIcon(icone(ICONES.get(prog.get("icone"), "marca")))
        b.setIconSize(QSize(34, 34))
        b.setText(f"{prog['nome']}{'   ● aberto' if aberto else ''}\n{prog.get('descricao', '')}")
        b.setMinimumHeight(70)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setEnabled(not aberto)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            f"QToolButton {{ background:{COR['panel2']}; color:{COR['text']}; border:1.5px solid "
            f"{COR['cyan'] if aberto else COR['line']}; border-radius:10px; padding:8px 14px; text-align:left;"
            f" font-size:10.5pt; }}"
            f"QToolButton:hover {{ background:{COR['btn_on']}; border-color:{COR['cyan']}; }}"
            f"QToolButton:disabled {{ color:{COR['muted']}; }}")

        def ir(_=False, prog=prog):
            erro = abrir(prog)
            if erro:
                QMessageBox.warning(dlg, prog["nome"], f"Não foi possível abrir o {prog['nome']}:\n{erro}")
                return
            dlg.accept()
            if janela is not None and hasattr(janela, "statusBar"):
                janela.statusBar().showMessage(f"Abrindo o {prog['nome']}…", 6000)
        b.clicked.connect(ir)
        col.addWidget(b)
    dlg.exec()
