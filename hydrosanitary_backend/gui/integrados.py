"""Programas integrados do HIDROSANITY (lista em programas.json, na raiz do repositório).

A gota no canto da faixa abre `escolher()`: uma janela com um cartão por programa; clicar abre o programa. O
GWATER tem o mesmo seletor (GWATER/REV 0.2.0/app/programa/integrados.py), lendo o mesmo arquivo.
"""
import json
import subprocess
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QVBoxLayout, QWidget

from gui import theme
from gui.theme import COR

RAIZ = Path(__file__).resolve().parents[2]


def programas():
    try:
        return json.loads((RAIZ / "programas.json").read_text(encoding="utf-8"))["programas"]
    except (OSError, ValueError, KeyError):
        return []


def abrir(prog):
    """Abre o programa pelo primeiro comando que existir. Devolve o erro, ou None."""
    for cmd in prog.get("comandos", []):
        exe = RAIZ / cmd[0]
        if exe.exists():
            try:
                subprocess.Popen([str(exe)] + list(cmd[1:]), cwd=str(RAIZ / prog.get("pasta", "")))
                return None
            except OSError as e:
                return str(e)
    return f"não encontrei {prog['comandos'][0][0]} em {RAIZ}"


def desenhar_icone(p, c, r, nome, cor):
    """Ícones dos cartões: gota, rede (malha com nós) ou prédio."""
    p.setPen(QPen(QColor(cor), 2))
    p.setBrush(Qt.NoBrush)
    if nome == "rede":
        pts = [QPointF(c.x() + dx * r, c.y() + dy * r) for dx, dy in ((-.8, -.5), (0, -.7), (.8, -.3), (-.6, .5), (.3, .6))]
        for i, j in ((0, 1), (1, 2), (0, 3), (1, 4), (3, 4), (2, 4)):
            p.drawLine(pts[i], pts[j])
        p.setBrush(QColor(cor))
        for q in pts:
            p.drawEllipse(q, 3.5, 3.5)
    elif nome == "predio":
        p.drawRect(QRectF(c.x() - r * .55, c.y() - r * .85, r * 1.1, r * 1.7))
        for k in range(4):
            y = c.y() - r * .6 + k * r * .38
            p.drawLine(QPointF(c.x() - r * .35, y), QPointF(c.x() + r * .35, y))
    else:
        from gui.inicio import desenhar_gota
        p.setBrush(QColor(cor))
        desenhar_gota(p, c, r, None)


class Cartao(QWidget):
    clicked = Signal()

    def __init__(self, prog, atual):
        super().__init__()
        self.prog, self.atual, self.hover = prog, atual, False
        self.setMinimumSize(420, 74)
        self.setCursor(Qt.ArrowCursor if atual else Qt.PointingHandCursor)
        self.setToolTip("Você está neste programa" if atual else f"Abrir o {prog['nome']}")

    def enterEvent(self, _):
        self.hover = True
        self.update()

    def leaveEvent(self, _):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if not self.atual and e.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        on = self.hover and not self.atual
        p.setBrush(QColor(COR["btn_on"] if on else COR["panel2"]))
        p.setPen(QPen(QColor(COR["cyan"] if on or self.atual else COR["line"]), 1.5))
        p.drawRoundedRect(r, 10, 10)
        desenhar_icone(p, QPointF(r.left() + 38, r.center().y()), 20, self.prog.get("icone"), COR["cyan"])
        p.setPen(QColor(COR["text"]))
        p.setFont(theme.fonte("display", 14, True))
        p.drawText(QRectF(r.left() + 76, r.top() + 10, r.width() - 190, 28), Qt.AlignLeft | Qt.AlignVCenter,
                   self.prog["nome"])
        p.setPen(QColor(COR["muted"]))
        p.setFont(theme.fonte("corpo", 9))
        p.drawText(QRectF(r.left() + 76, r.top() + 38, r.width() - 90, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   self.prog.get("descricao", ""))
        p.setPen(QColor(COR["ok"] if self.atual else COR["cyan"]))
        p.setFont(theme.fonte("corpo", 8.5, True))
        p.drawText(QRectF(r.right() - 120, r.top() + 10, 108, 28), Qt.AlignRight | Qt.AlignVCenter,
                   "● ABERTO" if self.atual else "ABRIR  ›")


def escolher(parent, atual):
    """Janela com os programas integrados; `atual` é o id do programa que chamou."""
    progs = programas()
    dlg = QDialog(parent)
    dlg.setWindowTitle("HIDROSANITY · programas integrados")
    col = QVBoxLayout(dlg)
    col.setContentsMargins(18, 16, 18, 16)
    col.setSpacing(8)
    t = QLabel("PROGRAMAS INTEGRADOS")
    t.setObjectName("h3")
    col.addWidget(t)
    s = QLabel("Escolha o programa que quer iniciar.")
    s.setObjectName("sub")
    col.addWidget(s)
    if not progs:
        col.addWidget(QLabel(f"Lista não encontrada: {RAIZ / 'programas.json'}"))
    for prog in progs:
        c = Cartao(prog, prog["id"] == atual)

        def go(prog=prog):
            erro = abrir(prog)
            if erro:
                QMessageBox.warning(dlg, prog["nome"], f"Não foi possível abrir o {prog['nome']}:\n{erro}")
            else:
                dlg.accept()
                if parent is not None and hasattr(parent, "statusBar"):
                    parent.statusBar().showMessage(f"Abrindo o {prog['nome']}…", 6000)
        c.clicked.connect(go)
        col.addWidget(c)
    dlg.exec()
