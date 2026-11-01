"""Seletor dos programas do GeoLogic Water: a tela do hub e a janela que a gota abre no GWATER e no GPREDIAL.

Este arquivo é o mesmo nos três (GeoLogic Water/seletor.py, GPREDIAL/gui/seletor.py e
GWATER/REV 0.2.0/app/programa/seletor.py) e funciona com o PySide6 (hub e GPREDIAL) ou com o PyQt do QGIS (GWATER):
quem chama passa a lista, a função que abre, as cores e as fontes do tema.

Janela sem moldura, com um cartão grande por programa: o cartão sobe e acende com o mouse, uma luz acompanha o
cursor, a ilustração cresce e o botão Abrir se preenche; o clique afunda o cartão e mostra "Abrindo…". Teclado:
← → escolhem, Enter abre, Esc fecha.
"""
try:
    from PySide6.QtCore import (QByteArray, QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation,
                                Signal)
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QToolButton, QVBoxLayout, QWidget
except ImportError:  # GWATER: o PyQt do QGIS
    from qgis.PyQt.QtCore import (QByteArray, QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation,
                                  pyqtSignal as Signal)
    from qgis.PyQt.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
    from qgis.PyQt.QtSvg import QSvgRenderer
    from qgis.PyQt.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QToolButton, QVBoxLayout, QWidget

# ---------------------------------------------------------------- ilustrações dos cartões (SVG 160×96)
K = "#1d3447"
ARTE = {
    "rede": f"""
<path d="M8 82 Q40 70 80 76 T152 66" fill="none" stroke="#9fd6a8" stroke-width="10" stroke-linecap="round" opacity=".55"/>
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
 <path d="M38 40 H70 L96 24 H132 M70 40 L84 66 H128 L132 24 M84 66 L56 76 L38 40" stroke="{K}" stroke-width="6"/>
 <path d="M38 40 H70 L96 24 H132 M70 40 L84 66 H128 L132 24 M84 66 L56 76 L38 40" stroke="#2f9be0" stroke-width="3.6"/>
 <path d="M38 40 H70 L96 24 H132" stroke="#bfe6ff" stroke-width="1.2" stroke-dasharray="4 5"/>
</g>
<g stroke="{K}" stroke-width="1.6">
 <circle cx="70" cy="40" r="4.5" fill="#fff"/><circle cx="96" cy="24" r="4.5" fill="#fff"/><circle cx="132" cy="24" r="4.5" fill="#fff"/>
 <circle cx="84" cy="66" r="4.5" fill="#fff"/><circle cx="128" cy="66" r="4.5" fill="#fff"/><circle cx="56" cy="76" r="4.5" fill="#fff"/>
</g>
<path d="M114 60 l5 3.5 -5 3.5z M124 60 l-5 3.5 5 3.5z" fill="#2fae74" stroke="{K}" stroke-width="1.2"/>
<g transform="translate(14 8)">
 <path d="M8 30 L5 44 M24 30 L27 44 M16 30 V44" stroke="#7b8fa1" stroke-width="2.4"/>
 <path d="M2 6 Q16 1 30 6 V28 Q16 33 2 28 Z" fill="#fff" stroke="{K}" stroke-width="1.8"/>
 <path d="M2 15 Q16 18 30 15 V28 Q16 33 2 28 Z" fill="#2f9be0"/>
 <path d="M2 6 Q16 1 30 6 V28 Q16 33 2 28 Z" fill="none" stroke="{K}" stroke-width="1.8"/>
</g>
<g transform="translate(130 70)"><path d="M0 12 L9 4 L18 12" fill="none" stroke="#e0524f" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
 <path d="M3 10 V20 H15 V10" fill="#fff4e0" stroke="{K}" stroke-width="1.6"/></g>
""",
    "predio": f"""
<path d="M10 90 H150" stroke="#b9b19f" stroke-width="3" stroke-linecap="round"/>
<rect x="40" y="18" width="80" height="72" rx="2" fill="#eef3f7" stroke="{K}" stroke-width="2"/>
<path d="M40 36 H120 M40 54 H120 M40 72 H120" stroke="#b4c4d1" stroke-width="1.6"/>
<rect x="88" y="4" width="26" height="14" rx="2" fill="#fff" stroke="{K}" stroke-width="1.8"/>
<rect x="89" y="10" width="24" height="7" fill="#2f9be0"/>
<g fill="none" stroke-linecap="round" stroke-linejoin="round">
 <path d="M101 18 V84 M101 30 H62 V34 M101 48 H62 V52 M101 66 H62 V70 M101 84 H70" stroke="{K}" stroke-width="5"/>
 <path d="M101 18 V84 M101 30 H62 V34 M101 48 H62 V52 M101 66 H62 V70 M101 84 H70" stroke="#2f9be0" stroke-width="2.8"/>
</g>
<g fill="#fff" stroke="{K}" stroke-width="1.3">
 <path d="M54 33 h10 q0 5 -5 5 q-5 0 -5 -5z"/><path d="M54 51 h10 q0 5 -5 5 q-5 0 -5 -5z"/><path d="M54 69 h10 q0 5 -5 5 q-5 0 -5 -5z"/>
</g>
<g fill="#8fd3ff" stroke="{K}" stroke-width="1"><rect x="46" y="22" width="8" height="8"/><rect x="108" y="40" width="8" height="8"/><rect x="108" y="58" width="8" height="8"/></g>
<rect x="74" y="78" width="10" height="12" fill="#f2a33a" stroke="{K}" stroke-width="1.2"/>
<path d="M14 70 Q20 54 26 70 Z M134 72 Q141 56 148 72 Z" fill="#5fb76b" stroke="{K}" stroke-width="1.2"/>
""",
}


def _mistura(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def _alfa(cor, a):
    c = QColor(cor)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _gota(p, c, r, cor):
    path = QPainterPath(QPointF(c.x(), c.y() - r))
    path.cubicTo(QPointF(c.x() + r * .55, c.y() - r * .25), QPointF(c.x() + r * .75, c.y() + r * .15),
                 QPointF(c.x() + r * .75, c.y() + r * .35))
    path.arcTo(QRectF(c.x() - r * .75, c.y() - r * .4, r * 1.5, r * 1.5), 0, -180)
    path.cubicTo(QPointF(c.x() - r * .75, c.y() + r * .15), QPointF(c.x() - r * .55, c.y() - r * .25),
                 QPointF(c.x(), c.y() - r))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(cor))
    p.drawPath(path)


class Cartao(QWidget):
    clicado = Signal()

    def __init__(self, prog, atual, cor, fontes, atraso=0):
        super().__init__()
        self.prog, self.atual, self.cor, self.fontes = prog, atual, cor, fontes
        self.h = 0.0          # 0 → 1 com o mouse em cima
        self.press = 0.0      # 0 → 1 enquanto aperta
        self.entrada = 0.0    # 0 → 1 ao abrir a janela (sobe e aparece)
        self.mouse = None
        self.abrindo, self.giro = False, 0
        self.setFixedSize(318, 372)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.ArrowCursor if atual else Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Você está neste programa" if atual else f"Abrir o {prog['nome']}")
        self._an = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.Type.OutCubic)
        self._an.valueChanged.connect(lambda v: self._set("h", v))
        self._ap = QVariantAnimation(self, duration=110)
        self._ap.valueChanged.connect(lambda v: self._set("press", v))
        self._ae = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=480,
                                     easingCurve=QEasingCurve.Type.OutBack)
        self._ae.valueChanged.connect(lambda v: self._set("entrada", v))
        QTimer.singleShot(60 + atraso, self._ae.start)
        self._tg = QTimer(self, interval=30)
        self._tg.timeout.connect(self._girar)

    def _set(self, k, v):
        setattr(self, k, float(v))
        self.update()

    def _animar(self, an, para):
        an.stop()
        an.setStartValue(self.h if an is self._an else self.press)
        an.setEndValue(float(para))
        an.start()

    # ------------------------------------------------ mouse e teclado
    def enterEvent(self, _):
        self._animar(self._an, 1.0)

    def leaveEvent(self, _):
        self.mouse = None
        self._animar(self._an, 1.0 if self.hasFocus() else 0.0)
        self._animar(self._ap, 0.0)

    def focusInEvent(self, _):
        self._animar(self._an, 1.0)

    def focusOutEvent(self, _):
        if not self.underMouse():
            self._animar(self._an, 0.0)

    def mouseMoveEvent(self, e):
        self.mouse = e.position() if hasattr(e, "position") else QPointF(e.pos())
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.atual:
            self._animar(self._ap, 1.0)

    def mouseReleaseEvent(self, e):
        self._animar(self._ap, 0.0)
        if e.button() == Qt.MouseButton.LeftButton and not self.atual and self.rect().contains(
                e.position().toPoint() if hasattr(e, "position") else e.pos()):
            self.clicado.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) and not self.atual:
            self.clicado.emit()
        else:
            super().keyPressEvent(e)

    def mostrar_abrindo(self):
        self.abrindo = True
        self._tg.start()

    def _girar(self):
        self.giro = (self.giro + 12) % 360
        self.update()

    # ------------------------------------------------ desenho
    def _fonte(self, tipo, tam, negrito=False):
        f = QFont(self.fontes.get(tipo) or self.fontes.get("corpo") or "Segoe UI")
        f.setPointSizeF(tam)
        f.setBold(negrito)
        return f

    def paintEvent(self, _):
        c, h = self.cor, self.h if not self.atual else self.h * 0.35
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        e = max(0.0, min(1.0, self.entrada))
        p.setOpacity(e)
        sobe = -8 * h + 26 * (1 - self.entrada)
        r = QRectF(self.rect()).adjusted(14, 16, -14, -16).translated(0, sobe)
        esc = 1 - 0.025 * self.press
        p.translate(r.center())
        p.scale(esc, esc)
        p.translate(-r.center())
        raio = 18
        # sombra (camadas que se abrem com o mouse)
        for i in range(6):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alfa("#000000", (0.035 + 0.05 * h) * (1 - i / 6)))
            d = 2 + i * (2 + 2.2 * h)
            p.drawRoundedRect(r.adjusted(-d * .6, -d * .2 + 4 * h, d * .6, d + 6 * h), raio + d, raio + d)
        # cartão
        fundo = QLinearGradient(r.topLeft(), r.bottomLeft())
        fundo.setColorAt(0, QColor(c["panel"]))
        fundo.setColorAt(1, _mistura(c["panel"], c["panel2"], 0.9))
        borda = _mistura(c["line"], c["cyan"], h if not self.atual else 0.6)
        p.setBrush(fundo)
        p.setPen(QPen(borda, 1.3 + 0.9 * h))
        p.drawRoundedRect(r, raio, raio)
        # topo com a ilustração
        topo = QRectF(r.left() + 10, r.top() + 10, r.width() - 20, 150)
        caminho = QPainterPath()
        caminho.addRoundedRect(topo, raio - 6, raio - 6)
        p.save()
        p.setClipPath(caminho)
        g = QLinearGradient(topo.topLeft(), topo.bottomRight())
        g.setColorAt(0, _alfa(c["cyan"], 0.10 + 0.10 * h))
        g.setColorAt(1, _alfa(c["water"], 0.05 + 0.12 * h))
        p.fillRect(topo, QColor(c["panel2"]))
        p.fillRect(topo, g)
        if self.mouse is not None and h > 0.01:  # luz que acompanha o cursor
            m = QPointF(self.mouse.x(), self.mouse.y() - sobe)
            luz = QRadialGradient(m, 150)
            luz.setColorAt(0, _alfa("#ffffff", 0.28 * h))
            luz.setColorAt(1, _alfa("#ffffff", 0))
            p.fillRect(topo, luz)
        arte = ARTE.get(self.prog.get("icone"), ARTE["rede"])
        rend = QSvgRenderer(QByteArray(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 96">{arte}</svg>'.encode()))
        k = 1 + 0.07 * h
        w_, h_ = 212 * k, 127.2 * k
        dx = 0 if self.mouse is None else (self.mouse.x() - r.center().x()) / r.width() * 8 * h  # paralaxe
        rend.render(p, QRectF(topo.center().x() - w_ / 2 + dx, topo.center().y() - h_ / 2 + 4, w_, h_))
        p.restore()
        # nome, descrição e etiquetas
        x0 = r.left() + 22
        p.setPen(QColor(c["text"]))
        p.setFont(self._fonte("display", 19, True))
        p.drawText(QRectF(x0, topo.bottom() + 14, r.width() - 44, 32), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self.prog["nome"])
        partes = [x.strip() for x in self.prog.get("descricao", "").split("·")]
        p.setPen(QColor(c["muted"]))
        p.setFont(self._fonte("corpo", 9.5))
        p.drawText(QRectF(x0, topo.bottom() + 46, r.width() - 44, 40),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, partes[0])
        x, y = x0, topo.bottom() + 90
        p.setFont(self._fonte("corpo", 8))
        for tag in [t.strip() for parte in partes[1:] for t in parte.split(",") if t.strip()][:4]:
            w = p.fontMetrics().horizontalAdvance(tag) + 16
            if x + w > r.right() - 20:
                break
            p.setPen(QPen(_mistura(c["line"], c["cyan"], 0.35 * h), 1))
            p.setBrush(QColor(c["chip"]))
            p.drawRoundedRect(QRectF(x, y, w, 20), 10, 10)
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(x, y, w, 20), Qt.AlignmentFlag.AlignCenter, tag)
            x += w + 6
        # botão de baixo
        b = QRectF(x0, r.bottom() - 52, r.width() - 44, 36)
        p.setFont(self._fonte("corpo", 10, True))
        if self.atual:
            p.setPen(QPen(_alfa(c["ok"], 0.6), 1.2))
            p.setBrush(_alfa(c["ok"], 0.10))
            p.drawRoundedRect(b, 18, 18)
            p.setPen(QColor(c["ok"]))
            p.drawText(b, Qt.AlignmentFlag.AlignCenter, "●  Aberto agora")
        else:
            p.setPen(QPen(QColor(c["cyan"]), 1.4))
            p.setBrush(_alfa(c["cyan"], 0.08 + 0.92 * h))
            p.drawRoundedRect(b, 18, 18)
            p.setPen(_mistura(c["cyan"], c.get("sobre", "#ffffff"), h))
            if self.abrindo:
                p.drawText(b.adjusted(0, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, "Abrindo…")
                p.setPen(QPen(_mistura(c["cyan"], c.get("sobre", "#ffffff"), h), 2.2, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(b.right() - 32, b.center().y() - 8, 16, 16), -self.giro * 16, 270 * 16)
            else:
                texto = f"Abrir o {self.prog['nome']}"
                tw = p.fontMetrics().horizontalAdvance(texto)
                cx = b.center().x() - 10
                p.drawText(QRectF(cx - tw / 2, b.top(), tw, b.height()), Qt.AlignmentFlag.AlignCenter, texto)
                ax = cx + tw / 2 + 10 + 6 * h
                p.setPen(QPen(p.pen().color(), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                cy = b.center().y()
                p.drawLine(QPointF(ax, cy), QPointF(ax + 12, cy))
                p.drawLine(QPointF(ax + 7, cy - 5), QPointF(ax + 12, cy))
                p.drawLine(QPointF(ax + 7, cy + 5), QPointF(ax + 12, cy))
        if self.hasFocus() and not self.underMouse():  # foco pelo teclado
            p.setPen(QPen(_alfa(c["cyan"], 0.6), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-5, -5, 5, 5), raio + 5, raio + 5)
        p.end()


class Seletor(QDialog):
    def __init__(self, pai, atual, progs, abrir, cor, fontes):
        super().__init__(pai)
        self.cor, self.fontes, self.abrir_prog, self.pai = cor, fontes, abrir, pai
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("GeoLogic Water")
        self._arraste = None
        col = QVBoxLayout(self)
        col.setContentsMargins(34, 96, 34, 54)
        linha = QHBoxLayout()
        linha.setSpacing(6)
        self.cartoes = []
        for i, prog in enumerate(progs):
            c = Cartao(prog, prog["id"] == atual, cor, fontes, atraso=i * 90)
            c.clicado.connect(lambda c=c: self._abrir(c))
            linha.addWidget(c)
            self.cartoes.append(c)
        col.addLayout(linha)
        self.fechar = QToolButton(self)
        self.fechar.setText("✕")
        self.fechar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fechar.setToolTip("Fechar (Esc)")
        self.fechar.clicked.connect(self.reject)
        self.fechar.setStyleSheet(
            f"QToolButton{{border:none;border-radius:15px;color:{cor['muted']};font-size:13pt;background:transparent;}}"
            f"QToolButton:hover{{background:{cor['crit']};color:#ffffff;}}")
        self.fechar.setFixedSize(30, 30)
        self.adjustSize()
        self.setWindowOpacity(0.0)
        self._af = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=200)
        self._af.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        QTimer.singleShot(0, self._af.start)
        livres = [c for c in self.cartoes if not c.atual]
        if livres:
            QTimer.singleShot(0, livres[0].setFocus)

    def resizeEvent(self, e):
        self.fechar.move(self.width() - 30 - 26, 22)
        super().resizeEvent(e)

    def _abrir(self, cartao):
        cartao.mostrar_abrindo()
        QTimer.singleShot(350, lambda: self._executar(cartao))

    def _executar(self, cartao):
        prog = cartao.prog
        erro = self.abrir_prog(prog)
        if erro:
            cartao.abrindo = False
            cartao._tg.stop()
            cartao.update()
            QMessageBox.warning(self, prog["nome"], f"Não foi possível abrir o {prog['nome']}:\n{erro}")
            return
        if self.pai is not None and hasattr(self.pai, "statusBar"):
            self.pai.statusBar().showMessage(f"Abrindo o {prog['nome']}…", 6000)
        QTimer.singleShot(500, self.accept)

    # ------------------------------------------------ arrastar pelo cabeçalho, teclado
    def mousePressEvent(self, e):
        pos = e.position().toPoint() if hasattr(e, "position") else e.pos()
        if e.button() == Qt.MouseButton.LeftButton and pos.y() < 90:
            gp = e.globalPosition().toPoint() if hasattr(e, "globalPosition") else e.globalPos()
            self._arraste = gp - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._arraste is not None:
            gp = e.globalPosition().toPoint() if hasattr(e, "globalPosition") else e.globalPos()
            self.move(gp - self._arraste)

    def mouseReleaseEvent(self, _):
        self._arraste = None

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.cartoes:
            atual = next((i for i, c in enumerate(self.cartoes) if c.hasFocus()), -1)
            passo = 1 if e.key() == Qt.Key.Key_Right else -1
            self.cartoes[(atual + passo) % len(self.cartoes)].setFocus()
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        c = self.cor
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        for i in range(8):  # sombra da janela
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alfa("#000000", 0.05 * (1 - i / 8)))
            p.drawRoundedRect(r.adjusted(-i, -i + 3, i, i + 3), 24 + i, 24 + i)
        fundo = QLinearGradient(r.topLeft(), r.bottomRight())
        fundo.setColorAt(0, QColor(c["bg"]))
        fundo.setColorAt(1, _mistura(c["bg"], c["panel2"], 0.8))
        p.setBrush(fundo)
        p.setPen(QPen(QColor(c["line"]), 1.2))
        p.drawRoundedRect(r, 24, 24)
        # brilho do destaque no canto
        brilho = QRadialGradient(QPointF(r.left() + 60, r.top() + 30), 260)
        brilho.setColorAt(0, _alfa(c["cyan"], 0.14))
        brilho.setColorAt(1, _alfa(c["cyan"], 0.0))
        p.setBrush(brilho)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 24, 24)
        # cabeçalho
        _gota(p, QPointF(r.left() + 42, r.top() + 44), 15, c["cyan"])
        f = QFont(self.fontes.get("display") or "Segoe UI")
        f.setPointSizeF(16)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(c["text"]))
        p.drawText(QRectF(r.left() + 68, r.top() + 22, 400, 26), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "GeoLogic Water")
        f2 = QFont(self.fontes.get("corpo") or "Segoe UI")
        f2.setPointSizeF(9.5)
        p.setFont(f2)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(r.left() + 68, r.top() + 48, 500, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "Escolha o programa que quer abrir")
        p.drawText(QRectF(r.left(), r.bottom() - 40, r.width(), 26), Qt.AlignmentFlag.AlignCenter,
                   "Clique num cartão  ·  ← → escolhem  ·  Enter abre  ·  Esc fecha")
        p.end()


def mostrar(pai, atual, progs, abrir, cor, fontes):
    """Abre o seletor. progs: lista do programas.json; abrir(prog) devolve o erro ou None; cor: as cores do tema
    (bg, panel, panel2, line, text, muted, cyan, water, ok, crit, chip, sobre); fontes: {"corpo", "display"}."""
    if not progs:
        QMessageBox.information(pai, "GeoLogic Water", "Lista de programas integrados não encontrada (programas.json).")
        return
    Seletor(pai, atual, progs, abrir, dict(cor), dict(fontes)).exec()
