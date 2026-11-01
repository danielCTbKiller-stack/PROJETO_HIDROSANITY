"""Menu inicial do HIDROSANITY: escolhe o programa a abrir.

  GWATER     redes de distribuição de água (EPANET/WNTR + QGIS), com a calibração Darwin e o Calibrador WaterGEMS
  GPREDIAL   instalações prediais de água fria (NBR 5626): desenho 2.5D, sinótico, período estendido, calibração

O GPREDIAL roda neste mesmo processo (PySide6, .venv). O GWATER usa o Python e as bibliotecas do QGIS, então
abre pelo GWATER.exe dele, em outro processo.
"""
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from gui import theme
from gui.theme import COR

RAIZ = Path(__file__).resolve().parents[2]  # pasta do repositório (hydrosanitary_backend e GWATER ao lado)
VERSAO = "1.0"


def gwater_exe():
    """GWATER.exe que tem o ambiente (QGIS + Python): o do repositório ou a versão portátil."""
    for c in (RAIZ / "GWATER" / "REV 0.2.0" / "GWATER.exe",
              RAIZ / "GWATER" / "PORTATIL" / "GWATER" / "GWATER.exe",
              Path(r"C:\0 - PROJETO PILOTO GWATER\PORTATIL\GWATER\GWATER.exe")):
        if c.exists() and ((c.parent / "runtime" / "qgis").exists() or _qgis_instalado()):
            return c
    return None


def _qgis_instalado():
    return any(Path(r"C:\Program Files").glob("QGIS*/bin/python-qgis*.bat"))


def desenhar_gota(p, c, r, cor):
    path = QPainterPath(QPointF(c.x(), c.y() - r))
    path.cubicTo(QPointF(c.x() + r * .25, c.y() - r * .5), QPointF(c.x() + r * .8, c.y()), QPointF(c.x() + r * .8, c.y() + r * .3))
    path.arcTo(QRectF(c.x() - r * .8, c.y() - r * .5, r * 1.6, r * 1.6), 0, -180)
    path.cubicTo(QPointF(c.x() - r * .8, c.y()), QPointF(c.x() - r * .25, c.y() - r * .5), QPointF(c.x(), c.y() - r))
    p.drawPath(path)


class Cartao(QWidget):
    """Cartão grande e clicável de um programa, com a ilustração pintada."""
    clicked = Signal()

    def __init__(self, nome, linha, itens, desenho):
        super().__init__()
        self.nome, self.linha, self.itens, self.desenho = nome, linha, itens, desenho
        self.hover = False
        self.status = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(380, 430)
        self.setAttribute(Qt.WA_Hover)

    def enterEvent(self, _):
        self.hover = True
        self.update()

    def leaveEvent(self, _):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(COR["panel2"]))
        g.setColorAt(1, QColor(COR["panel"]))
        p.setBrush(g)
        p.setPen(QPen(QColor(COR["cyan"] if self.hover else COR["line"]), 2 if self.hover else 1))
        p.drawRoundedRect(r, 14, 14)
        art = QRectF(r.left() + 20, r.top() + 20, r.width() - 40, 170)
        p.save()
        p.setClipRect(art)
        self.desenho(p, art, self.hover)
        p.restore()
        y = art.bottom() + 18
        p.setPen(QColor(COR["text"]))
        p.setFont(theme.fonte("display", 22, True))
        p.drawText(QRectF(r.left() + 24, y, r.width() - 48, 36), Qt.AlignLeft | Qt.AlignVCenter, self.nome)
        p.setPen(QColor(COR["cyan"]))
        p.setFont(theme.fonte("corpo", 10.5))
        p.drawText(QRectF(r.left() + 24, y + 36, r.width() - 48, 22), Qt.AlignLeft | Qt.AlignVCenter, self.linha)
        p.setFont(theme.fonte("corpo", 9.5))
        yy = y + 70
        for item in self.itens:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(COR["cyan"]))
            p.drawEllipse(QPointF(r.left() + 30, yy + 9), 2.5, 2.5)
            p.setPen(QColor(COR["muted"]))
            p.drawText(QRectF(r.left() + 42, yy, r.width() - 66, 18), Qt.AlignLeft | Qt.AlignVCenter, item)
            yy += 21
        btn = QRectF(r.left() + 24, r.bottom() - 52, r.width() - 48, 34)
        p.setBrush(QColor(COR["btn_on"] if self.hover else COR["btn"]))
        p.setPen(QPen(QColor(COR["cyan"]), 1))
        p.drawRoundedRect(btn, 8, 8)
        p.setPen(QColor(COR["text"]))
        p.setFont(theme.fonte("corpo", 10, True))
        p.drawText(btn, Qt.AlignCenter, self.status or f"ABRIR {self.nome}")


def arte_gwater(p, a, hover):
    """Rede de distribuição: malha de tubos com nós, reservatório e uma gota."""
    p.fillRect(a, QColor(COR["bg"]))
    pts = [(.12, .3), (.32, .22), (.55, .3), (.8, .2), (.2, .62), (.42, .58), (.66, .66), (.88, .55), (.3, .88), (.6, .9)]
    P = [QPointF(a.left() + x * a.width(), a.top() + y * a.height()) for x, y in pts]
    ligs = [(0, 1), (1, 2), (2, 3), (0, 4), (1, 5), (2, 6), (3, 7), (4, 5), (5, 6), (6, 7), (4, 8), (5, 9), (8, 9), (6, 9)]
    p.setPen(QPen(QColor(COR["water"]), 3))
    for i, j in ligs:
        p.drawLine(P[i], P[j])
    p.setPen(QPen(QColor(COR["flow"] if hover else COR["cyan"]), 1.2, Qt.DashLine))
    for i, j in ligs[::3]:
        p.drawLine(P[i], P[j])
    p.setPen(QPen(QColor(COR["bg"]), 2))
    for k, q in enumerate(P):
        p.setBrush(QColor(COR["ok"] if k % 3 else COR["cyan"]))
        p.drawEllipse(q, 5, 5)
    p.setBrush(QColor(COR["cyan"]))
    p.setPen(Qt.NoPen)
    desenhar_gota(p, QPointF(a.right() - 34, a.top() + 40), 24, None)


def arte_gpredial(p, a, hover):
    """Prédio em corte com a coluna de água e ramais por pavimento."""
    p.fillRect(a, QColor(COR["bg"]))
    w, n = a.width() * .46, 6
    x0 = a.center().x() - w / 2
    hh = (a.height() - 30) / n
    base = a.bottom() - 8
    for k in range(n):
        y = base - (k + 1) * hh
        p.setPen(QPen(QColor(COR["line"]), 1.2))
        p.setBrush(QColor(COR["panel2"]))
        p.drawRect(QRectF(x0, y, w, hh))
        p.setBrush(QColor(COR["chip"]))
        for j in range(4):
            p.drawRect(QRectF(x0 + 10 + j * (w - 20) / 4, y + hh * .25, (w - 20) / 4 - 8, hh * .45))
        p.setPen(QPen(QColor(COR["water"]), 2.5))
        p.drawLine(QPointF(x0 - 14, y + hh * .8), QPointF(x0 + w * .7, y + hh * .8))
        p.setPen(QPen(QColor(COR["bg"]), 1.5))
        p.setBrush(QColor(COR["ok"]))
        p.drawEllipse(QPointF(x0 + w * .7, y + hh * .8), 3.5, 3.5)
    top = base - n * hh
    p.setPen(QPen(QColor(COR["cyan"] if hover else COR["water"]), 4))
    p.drawLine(QPointF(x0 - 14, top - 8), QPointF(x0 - 14, base - hh * .2))
    p.setPen(QPen(QColor(COR["cyan"]), 1.5))
    p.setBrush(QColor(COR["btn"]))
    p.drawRect(QRectF(x0 - 40, top - 22, 54, 18))  # reservatório superior
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(COR["cyan"]))
    desenhar_gota(p, QPointF(a.right() - 34, a.top() + 40), 24, None)


class MenuInicial(QWidget):
    def __init__(self):
        super().__init__()
        self.janela = None
        self.setWindowTitle("HIDROSANITY")
        self.setWindowIcon(QIcon(self._icone()))
        self.setMinimumSize(900, 660)
        col = QVBoxLayout(self)
        col.setContentsMargins(40, 32, 40, 24)
        col.setSpacing(6)
        t = QLabel("HIDROSANITY")
        t.setFont(theme.fonte("display", 30, True))
        t.setStyleSheet(f"color:{COR['text']}; font-family:Bahnschrift; font-size:34px; font-weight:700; letter-spacing:4px;")
        s = QLabel("Modelagem hidráulica · redes de distribuição e instalações prediais. Escolha o programa:")
        s.setStyleSheet(f"color:{COR['muted']};")
        s.setFont(theme.fonte("corpo", 11))
        col.addWidget(t)
        col.addWidget(s)
        col.addSpacing(18)
        row = QHBoxLayout()
        row.setSpacing(24)
        self.c_gwater = Cartao("GWATER", "Redes de distribuição de água", [
            "Cadastro e mapa (QGIS), EPANET 2.2",
            "Cenários, incêndio, descarga, criticidade",
            "Calibração Darwin e Calibrador WaterGEMS",
            "Centro de Operações: sinótico e ao vivo",
        ], arte_gwater)
        self.c_gpredial = Cartao("GPREDIAL", "Instalações prediais de água fria · NBR 5626", [
            "Desenho em planta, isométrica 2.5D e parede",
            "Aparelhos, peças, VRP e paredes por pavimento",
            "Sinótico do prédio e período estendido",
            "Calibração Darwin da rede predial",
        ], arte_gpredial)
        self.c_gwater.clicked.connect(self.abrir_gwater)
        self.c_gpredial.clicked.connect(self.abrir_gpredial)
        row.addWidget(self.c_gwater)
        row.addWidget(self.c_gpredial)
        col.addLayout(row, 1)
        rod = QLabel(f"HIDROSANITY {VERSAO} · {RAIZ}")
        rod.setStyleSheet(f"color:{COR['muted']};")
        rod.setFont(theme.fonte("mono", 8.5))
        col.addSpacing(8)
        col.addWidget(rod)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(COR["bg"]))
        self.setPalette(pal)

    @staticmethod
    def _icone():
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(COR["cyan"]))
        desenhar_gota(p, QPointF(32, 30), 26, None)
        p.end()
        return pm

    def abrir_gpredial(self, arquivo=None):
        from gui.main_window import MainWindow
        self.janela = MainWindow()
        self.janela.showMaximized()
        if arquivo:
            self.janela.load_file(arquivo)
        self.close()

    def abrir_gwater(self):
        exe = gwater_exe()
        if exe is None:
            QMessageBox.information(
                self, "GWATER",
                "O GWATER precisa do QGIS e do Python dele (versão portátil, ~2,5 GB, fora do Git).\n\n"
                "Instale o QGIS, ou gere a versão portátil com GWATER\\REV 0.2.0\\gerar_portatil.bat, ou ligue a "
                "pasta runtime de uma versão portátil em GWATER\\REV 0.2.0\\runtime.")
            return
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
        self.c_gwater.status = "ABRINDO O GWATER…"
        self.c_gwater.update()
        QTimer.singleShot(2500, self.close)


def main(argv=None):
    app = QApplication(argv or sys.argv)
    app.setStyle("Fusion")
    theme.aplicar_tema(None, app)  # o tema escolhido em Configurações (padrão: Verde Saneamento)
    menu = MenuInicial()
    args = app.arguments()[1:]
    if args:  # arquivo de projeto predial (.hsp/.dxf/.ifc): vai direto ao GPREDIAL
        menu.abrir_gpredial(args[0])
    else:
        menu.resize(1000, 700)
        menu.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
