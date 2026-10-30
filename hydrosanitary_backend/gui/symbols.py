"""Símbolos desenhados com QPainter: peças (conexões, válvulas), aparelhos e os ícones da faixa.

Tudo é desenhado num quadrado de lado `s` centrado em (0, 0), para servir tanto ao modelo
(tamanho fixo na tela) quanto ao sinótico e aos botões.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

from core.standards import FITTING_SHORT, FIXTURE_INFO
from gui.theme import COR, MONO


def _pen(color, w):
    p = QPen(QColor(color), w)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def bowtie(p: QPainter, s, color, fill):
    """Corpo de válvula (dois triângulos opostos)."""
    h = s * 0.32
    p.setBrush(QBrush(QColor(fill)))
    p.drawPolygon(QPolygonF([QPointF(-s / 2, -h), QPointF(0, 0), QPointF(-s / 2, h)]))
    p.drawPolygon(QPolygonF([QPointF(s / 2, -h), QPointF(0, 0), QPointF(s / 2, h)]))


def draw_fitting(p: QPainter, key: str, s: float, color=None, fill=None):
    color = color or COR["cyan"]
    fill = fill or COR["panel2"]
    p.save()
    p.setPen(_pen(color, max(1.2, s / 14)))
    p.setBrush(Qt.NoBrush)
    if key in ("registro_gaveta", "registro_globo", "registro_pressao", "valvula_retencao"):
        bowtie(p, s, color, fill)
        if key == "registro_gaveta":
            p.drawLine(QPointF(0, 0), QPointF(0, -s * 0.45)); p.drawLine(QPointF(-s * .18, -s * .45), QPointF(s * .18, -s * .45))
        elif key == "registro_globo":
            p.setBrush(QColor(color)); p.drawEllipse(QPointF(0, 0), s * .1, s * .1)
        elif key == "registro_pressao":
            p.drawLine(QPointF(0, 0), QPointF(0, -s * 0.42)); p.drawEllipse(QPointF(0, -s * .45), s * .1, s * .1)
        else:  # retenção: seta indicando o sentido único
            p.drawLine(QPointF(-s * .1, -s * .45), QPointF(s * .25, -s * .45))
            p.drawLine(QPointF(s * .25, -s * .45), QPointF(s * .1, -s * .55))
    elif key == "valvula_redutora_pressao":
        bowtie(p, s, color, fill)
        p.drawLine(QPointF(0, 0), QPointF(0, -s * .3))
        p.setBrush(QBrush(QColor(fill)))
        dome = QPainterPath(QPointF(-s * .28, -s * .3))
        dome.arcTo(QRectF(-s * .28, -s * .58, s * .56, s * .56), 180, -180)
        dome.closeSubpath()
        p.drawPath(dome)
        p.setPen(_pen(COR["warn"], max(1.2, s / 14)))  # mola do diafragma
        p.drawLine(QPointF(-s * .12, -s * .36), QPointF(s * .12, -s * .48))
    elif key in ("joelho_90", "curva_90", "joelho_45", "curva_45"):
        p.setPen(_pen(color, max(2.0, s / 7)))
        if key == "joelho_90":
            p.drawPolyline(QPolygonF([QPointF(-s * .4, s * .3), QPointF(s * .3, s * .3), QPointF(s * .3, -s * .4)]))
        elif key == "curva_90":
            path = QPainterPath(QPointF(-s * .4, s * .3))
            path.arcTo(QRectF(-s * .4 - s * .7, s * .3 - s * 1.4, s * 1.4, s * 1.4), -90, 90)
            p.drawPath(path)
        elif key == "joelho_45":
            p.drawPolyline(QPolygonF([QPointF(-s * .45, s * .3), QPointF(0, s * .3), QPointF(s * .35, -s * .1)]))
        else:
            path = QPainterPath(QPointF(-s * .45, s * .3))
            path.quadTo(QPointF(s * .05, s * .3), QPointF(s * .35, -s * .1))
            p.drawPath(path)
    elif key.startswith("te_"):
        p.setPen(_pen(color, max(2.0, s / 7)))
        p.drawLine(QPointF(-s * .45, s * .1), QPointF(s * .45, s * .1))
        p.drawLine(QPointF(0, s * .1), QPointF(0, -s * .45))
    elif key == "hidrometro":
        p.setBrush(QBrush(QColor(fill)))
        p.drawEllipse(QPointF(0, 0), s * .38, s * .38)
        p.setFont(_font(s * .26)); p.drawText(QRectF(-s / 2, -s / 2, s, s), Qt.AlignCenter, "H")
    elif key in ("luva", "bucha_reducao"):
        p.setBrush(QBrush(QColor(fill)))
        if key == "luva":
            p.drawRect(QRectF(-s * .2, -s * .22, s * .4, s * .44))
        else:
            p.drawPolygon(QPolygonF([QPointF(-s * .3, -s * .3), QPointF(s * .3, -s * .15),
                                     QPointF(s * .3, s * .15), QPointF(-s * .3, s * .3)]))
    else:
        p.setFont(_font(s * .3)); p.drawText(QRectF(-s / 2, -s / 2, s, s), Qt.AlignCenter, FITTING_SHORT.get(key, "?"))
    p.restore()


def _font(px):
    f = QFont(MONO)
    f.setPixelSize(max(6, int(px)))
    f.setBold(True)
    return f


def draw_fixture(p: QPainter, key: str, s: float, color=None, fill=None, text_color=None):
    """Aparelho: disco com a sigla (CH, BS, LV…)."""
    color = color or COR["cyan"]
    p.save()
    p.setPen(_pen(color, max(1.2, s / 14)))
    p.setBrush(QBrush(QColor(fill or COR["panel2"])))
    p.drawEllipse(QPointF(0, 0), s * .45, s * .45)
    sigla = FIXTURE_INFO.get(key, ("", "?", 0))[1]
    p.setPen(QColor(text_color or COR["text"]))
    p.setFont(_font(s * (0.3 if len(sigla) <= 2 else 0.24)))
    p.drawText(QRectF(-s / 2, -s / 2, s, s), Qt.AlignCenter, sigla)
    p.restore()


def draw_source(p: QPainter, s: float, color=None):
    """Reservatório (caixa d'água) com nível."""
    color = color or COR["cyan"]
    p.save()
    p.setPen(_pen(color, max(1.2, s / 14)))
    p.setBrush(QBrush(QColor(COR["panel2"])))
    p.drawRoundedRect(QRectF(-s * .42, -s * .34, s * .84, s * .68), s * .08, s * .08)
    p.setBrush(QBrush(QColor(COR["water"])))
    p.setPen(Qt.NoPen)
    p.drawRect(QRectF(-s * .36, -s * .02, s * .72, s * .3))
    p.restore()


# ---------------------------------------------------------------- ícones da faixa
def _icon_glyph(p: QPainter, name: str, s: float):
    c, t = COR["cyan"], COR["text"]
    pen = _pen(t, s / 16)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if name in FIXTURE_INFO:
        draw_fixture(p, name, s * .9); return
    if name in FITTING_SHORT:
        draw_fitting(p, name, s * .9); return
    if name == "fonte":
        draw_source(p, s * .9); return
    if name == "selecionar":
        p.setBrush(QColor(t))
        p.drawPolygon(QPolygonF([QPointF(-s * .25, -s * .4), QPointF(s * .3, s * .1), QPointF(s * .02, s * .12),
                                 QPointF(s * .15, s * .4), QPointF(s * .05, s * .44), QPointF(-s * .08, s * .17),
                                 QPointF(-s * .25, s * .3)]))
    elif name == "tubo":
        p.setPen(_pen(COR["water"], s / 7)); p.drawLine(QPointF(-s * .4, s * .3), QPointF(s * .4, -s * .3))
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(COR["panel2"]))
        for q in (QPointF(-s * .4, s * .3), QPointF(s * .4, -s * .3)):
            p.drawEllipse(q, s * .09, s * .09)
    elif name == "prumada":
        p.setPen(_pen(COR["water"], s / 7)); p.drawLine(QPointF(0, -s * .42), QPointF(0, s * .42))
        p.setPen(_pen(c, s / 14))
        for y in (-s * .2, s * .2):
            p.drawLine(QPointF(0, y), QPointF(s * .35, y))
    elif name in ("parede_ext", "parede_int", "retangulo"):
        _iso_wall_icon(p, s, name)
    elif name == "comodo":
        p.setBrush(QColor(53, 208, 255, 60)); p.setPen(_pen(c, s / 16))
        p.drawPolygon(QPolygonF([QPointF(-s * .4, -s * .1), QPointF(0, -s * .38), QPointF(s * .4, -s * .1),
                                 QPointF(0, s * .18)]))
        p.setPen(_pen(t, s / 18)); p.drawLine(QPointF(-s * .4, -s * .1), QPointF(-s * .4, s * .25))
    elif name in ("pavimento", "copiar_acima", "replicar"):
        for i, y in enumerate((s * .22, -s * .02, -s * .26)):
            p.setBrush(QColor(COR["panel2"] if i else COR["btn_on"]))
            p.drawPolygon(QPolygonF([QPointF(-s * .4, y), QPointF(0, y - s * .14), QPointF(s * .4, y),
                                     QPointF(0, y + s * .14)]))
        if name != "pavimento":
            p.setPen(_pen(COR["ok"], s / 12))
            p.drawLine(QPointF(s * .32, s * .05), QPointF(s * .32, -s * .42))
            p.drawLine(QPointF(s * .2, -s * .3), QPointF(s * .32, -s * .42)); p.drawLine(QPointF(s * .44, -s * .3), QPointF(s * .32, -s * .42))
    elif name == "calcular":
        p.setBrush(QColor(COR["btn_on"])); p.setPen(_pen(c, s / 16))
        p.drawPolygon(QPolygonF([QPointF(-s * .25, -s * .38), QPointF(s * .38, 0), QPointF(-s * .25, s * .38)]))
    elif name in ("novo", "abrir", "salvar", "memorial"):
        p.setBrush(QColor(COR["panel2"]))
        p.drawPolygon(QPolygonF([QPointF(-s * .3, -s * .42), QPointF(s * .12, -s * .42), QPointF(s * .3, -s * .24),
                                 QPointF(s * .3, s * .42), QPointF(-s * .3, s * .42)]))
        p.setPen(_pen(c, s / 14))
        if name == "novo":
            p.drawLine(QPointF(0, -s * .05), QPointF(0, s * .27)); p.drawLine(QPointF(-s * .16, s * .11), QPointF(s * .16, s * .11))
        elif name == "abrir":
            p.drawLine(QPointF(0, s * .28), QPointF(0, -s * .1)); p.drawLine(QPointF(-s * .13, s * .03), QPointF(0, -s * .1)); p.drawLine(QPointF(s * .13, s * .03), QPointF(0, -s * .1))
        elif name == "salvar":
            p.drawLine(QPointF(0, -s * .12), QPointF(0, s * .26)); p.drawLine(QPointF(-s * .13, s * .13), QPointF(0, s * .26)); p.drawLine(QPointF(s * .13, s * .13), QPointF(0, s * .26))
        else:
            for y in (-s * .1, s * .05, s * .2):
                p.drawLine(QPointF(-s * .17, y), QPointF(s * .17, y))
    elif name in ("desfazer", "refazer"):
        k = -1 if name == "desfazer" else 1
        p.setPen(_pen(c, s / 12))
        path = QPainterPath(QPointF(-k * s * .3, s * .3))
        path.cubicTo(QPointF(-k * s * .3, -s * .2), QPointF(k * s * .2, -s * .25), QPointF(k * s * .32, -s * .05))
        p.drawPath(path)
        p.drawLine(QPointF(k * s * .32, -s * .05), QPointF(k * s * .32, -s * .3))
        p.drawLine(QPointF(k * s * .32, -s * .05), QPointF(k * s * .08, -s * .08))
    elif name == "excluir":
        p.setPen(_pen(COR["crit"], s / 10))
        p.drawLine(QPointF(-s * .28, -s * .28), QPointF(s * .28, s * .28)); p.drawLine(QPointF(s * .28, -s * .28), QPointF(-s * .28, s * .28))
    elif name in ("iso", "planta"):
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(COR["panel2"]))
        if name == "planta":
            p.drawRect(QRectF(-s * .35, -s * .35, s * .7, s * .7)); p.drawLine(QPointF(0, -s * .35), QPointF(0, s * .35))
        else:
            top = [QPointF(0, -s * .42), QPointF(s * .36, -s * .22), QPointF(0, -s * .02), QPointF(-s * .36, -s * .22)]
            p.drawPolygon(QPolygonF(top))
            p.drawPolygon(QPolygonF([top[3], top[2], QPointF(0, s * .42), QPointF(-s * .36, s * .2)]))
            p.drawPolygon(QPolygonF([top[2], top[1], QPointF(s * .36, s * .2), QPointF(0, s * .42)]))
    elif name == "girar":
        p.setPen(_pen(c, s / 12))
        p.drawArc(QRectF(-s * .32, -s * .32, s * .64, s * .64), 30 * 16, 280 * 16)
        p.drawLine(QPointF(s * .28, -s * .16), QPointF(s * .34, -s * .38))
        p.drawLine(QPointF(s * .28, -s * .16), QPointF(s * .06, -s * .2))
    elif name == "ajustar":
        p.setPen(_pen(c, s / 12))
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p.drawLine(QPointF(sx * s * .38, sy * s * .38), QPointF(sx * s * .14, sy * s * .38))
            p.drawLine(QPointF(sx * s * .38, sy * s * .38), QPointF(sx * s * .38, sy * s * .14))
    elif name == "sinotico":
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(COR["panel2"]))
        p.drawRect(QRectF(-s * .3, -s * .2, s * .6, s * .6))
        for y in (-s * .0, s * .2):
            p.drawLine(QPointF(-s * .3, y), QPointF(s * .3, y))
        draw_source(p, s * .4)
    elif name == "exemplo":
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(COR["panel2"]))
        p.drawRect(QRectF(-s * .25, -s * .42, s * .5, s * .84))
        for y in (-s * .25, -s * .05, s * .15):
            for x in (-s * .12, s * .06):
                p.fillRect(QRectF(x, y, s * .08, s * .1), QColor(COR["flow"]))
    elif name == "grade":
        p.setPen(_pen(COR["muted"], s / 22))
        for k in (-.3, -.1, .1, .3):
            p.drawLine(QPointF(k * s, -s * .4), QPointF(k * s, s * .4)); p.drawLine(QPointF(-s * .4, k * s), QPointF(s * .4, k * s))
    elif name == "parede_2d":
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(143, 165, 189, 90))
        p.drawRect(QRectF(-s * .4, -s * .32, s * .8, s * .64))
        p.setPen(_pen(COR["water"], s / 10))
        p.drawPolyline(QPolygonF([QPointF(-s * .3, -s * .18), QPointF(s * .1, -s * .18), QPointF(s * .1, s * .2)]))
        p.setPen(_pen(c, s / 16)); p.setBrush(QColor(COR["panel2"]))
        p.drawEllipse(QPointF(s * .1, s * .2), s * .07, s * .07)
    elif name == "relogio":
        p.setPen(_pen(c, s / 14)); p.setBrush(QColor(COR["panel2"]))
        p.drawEllipse(QPointF(0, 0), s * .38, s * .38)
        p.drawLine(QPointF(0, 0), QPointF(0, -s * .26)); p.drawLine(QPointF(0, 0), QPointF(s * .18, s * .1))
    elif name == "orto":
        p.setPen(_pen(c, s / 12))
        p.drawLine(QPointF(-s * .35, s * .35), QPointF(-s * .35, -s * .35)); p.drawLine(QPointF(-s * .35, s * .35), QPointF(s * .35, s * .35))
    else:
        p.setFont(_font(s * .4)); p.drawText(QRectF(-s / 2, -s / 2, s, s), Qt.AlignCenter, name[:2].upper())


def _iso_wall_icon(p, s, name):
    ext = name == "parede_ext"
    face = QColor("#c9d3df" if ext else "#8fa5bd")
    side = face.darker(135)
    top = face.lighter(118)
    p.setPen(_pen(COR["bg"], s / 30))
    if name == "retangulo":
        p.setBrush(QColor(53, 208, 255, 40)); p.setPen(_pen(COR["cyan"], s / 16))
        p.drawPolygon(QPolygonF([QPointF(-s * .42, 0), QPointF(0, -s * .24), QPointF(s * .42, 0), QPointF(0, s * .24)]))
        p.setPen(_pen(COR["text"], s / 16))
        for q in (QPointF(-s * .42, 0), QPointF(0, -s * .24), QPointF(s * .42, 0), QPointF(0, s * .24)):
            p.drawLine(q, q - QPointF(0, s * .2))
        return
    t = s * (.12 if ext else .07)
    a, b = QPointF(-s * .4, s * .1), QPointF(s * .2, -s * .22)
    h = QPointF(0, -s * .32)
    d = QPointF(t, t * .55)
    p.setBrush(face); p.drawPolygon(QPolygonF([a + d, b + d, b + d + h, a + d + h]))
    p.setBrush(side); p.drawPolygon(QPolygonF([b, b + d, b + d + h, b + h]))
    p.setBrush(top); p.drawPolygon(QPolygonF([a + h, b + h, b + d + h, a + d + h]))


def icon(name: str, size: int = 32) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.translate(size / 2, size / 2)
    _icon_glyph(p, name, size * 0.92)
    p.end()
    return QIcon(pm)
