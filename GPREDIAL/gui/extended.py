"""Tela de simulação em período estendido: parâmetros, curva de consumo editável, gráficos ao longo do
tempo (consumo × alimentação, nível do reservatório, pressões) e linha do tempo com reprodução.
Qualquer instante pode ser levado ao modelo e ao sinótico."""
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

from core.standards import MAX_STATIC_PRESSURE_MCA
from gui.synoptic import Kpi
from gui.theme import COR, MONO
from services.extended_period import PATTERNS, EPSConfig, default_config, simulate, supply_cut


def _font(px, bold=False):
    f = QFont(MONO)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def fmt_t(t_h):
    day = int(t_h // 24) + 1
    h = t_h % 24
    return f"Dia {day} · {int(h):02d}:{int(round((h % 1) * 60)) % 60:02d}"


class PatternEditor(QWidget):
    """Curva de consumo horária: 24 barras; arraste para mudar o fator de cada hora."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.values = list(PATTERNS["Residencial"])
        self.setMinimumHeight(96)
        self.setToolTip("Arraste as barras para ajustar o fator de consumo de cada hora")

    def set_values(self, v):
        self.values = list(v)
        self.update()

    def _rect(self):
        return QRectF(4, 6, self.width() - 8, self.height() - 22)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._rect()
        top = max(2.5, max(self.values) * 1.1)
        w = r.width() / 24
        p.setPen(QPen(QColor(COR["grid"]), 1, Qt.DashLine))
        y1 = r.bottom() - r.height() / top
        p.drawLine(QPointF(r.left(), y1), QPointF(r.right(), y1))  # fator 1 = média
        for h, v in enumerate(self.values):
            hgt = r.height() * v / top
            p.fillRect(QRectF(r.left() + h * w + 1, r.bottom() - hgt, w - 2, hgt), QColor(COR["water"]))
        p.setPen(QColor(COR["muted"]))
        p.setFont(_font(9))
        for h in (0, 6, 12, 18):
            p.drawText(QRectF(r.left() + h * w - 2, r.bottom() + 2, 30, 14), Qt.AlignLeft, f"{h}h")

    def _set_at(self, pos):
        r = self._rect()
        h = int((pos.x() - r.left()) / (r.width() / 24))
        if 0 <= h < 24:
            top = max(2.5, max(self.values) * 1.1)
            self.values[h] = round(max(0.0, min(3.0, (r.bottom() - pos.y()) / r.height() * top)), 2)
            self.update()
            self.changed.emit()

    def mousePressEvent(self, e):
        self._set_at(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._set_at(e.position())


class TimeChart(QWidget):
    """Gráfico ao longo do tempo com cursor (clique ou arraste para escolher o instante)."""
    picked = Signal(int)

    def __init__(self, title, unit):
        super().__init__()
        self.title, self.unit = title, unit
        self.t = []
        self.series = []   # {"label", "color", "values", "kind": line|area|bar}
        self.refs = []     # (valor, cor, rótulo)
        self.shade = []    # índices com faixa de destaque (ex.: falta d'água)
        self.cursor = 0
        self.ymin = None
        self.ymax = None
        self.setMinimumHeight(150)

    def set_data(self, t, series, refs=(), shade=(), ymin=None, ymax=None):
        self.t, self.series, self.refs, self.shade = t, series, list(refs), list(shade)
        self.ymin, self.ymax = ymin, ymax
        self.update()

    def _plot(self):
        return QRectF(52, 26, self.width() - 66, self.height() - 48)

    def _range(self):
        vals = [v for s in self.series for v in s["values"] if v is not None] + [r[0] for r in self.refs]
        lo = self.ymin if self.ymin is not None else min(vals + [0.0])
        hi = self.ymax if self.ymax is not None else max(vals + [1e-6])
        if hi - lo < 1e-9:
            hi = lo + 1
        return lo, hi + (0 if self.ymax is not None else (hi - lo) * 0.08)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(COR["cyan"]))
        p.setFont(_font(11, True))
        p.drawText(QRectF(10, 4, 400, 18), Qt.AlignLeft, self.title.upper())
        r = self._plot()
        if not self.t:
            p.setPen(QColor(COR["muted"]))
            p.drawText(r, Qt.AlignCenter, "Rode a simulação")
            return
        lo, hi = self._range()
        T = self.t[-1] or 1
        X = lambda t: r.left() + r.width() * t / T
        Y = lambda v: r.bottom() - r.height() * (v - lo) / (hi - lo)
        dt = (self.t[1] - self.t[0]) if len(self.t) > 1 else 1
        for i in self.shade:
            p.fillRect(QRectF(X(self.t[i]), r.top(), r.width() * dt / T, r.height()), QColor(255, 107, 122, 28))
        p.setFont(_font(9))
        for k in range(5):  # eixo y
            v = lo + (hi - lo) * k / 4
            y = Y(v)
            p.setPen(QPen(QColor(COR["grid"]), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(COR["muted"]))
            p.drawText(QRectF(0, y - 7, r.left() - 6, 14), Qt.AlignRight | Qt.AlignVCenter, f"{v:.1f}")
        step = 6 if T <= 48 else (12 if T <= 96 else 24)
        h = 0
        while h <= T + 1e-9:  # eixo x
            x = X(h)
            p.setPen(QPen(QColor(COR["line"] if h % 24 == 0 else COR["grid"]), 1))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.setPen(QColor(COR["muted"]))
            p.drawText(QRectF(x - 20, r.bottom() + 3, 40, 14), Qt.AlignCenter, f"{int(h % 24)}h" if h % 24 else f"D{int(h // 24) + 1}")
            h += step
        for ref_v, color, label in self.refs:
            y = Y(ref_v)
            p.setPen(QPen(QColor(color), 1.2, Qt.DashLine))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.drawText(QRectF(r.right() - 200, y - 15, 196, 14), Qt.AlignRight, label)
        for s in self.series:
            color = QColor(s["color"])
            pts = [(X(t), Y(v)) for t, v in zip(self.t, s["values"]) if v is not None]
            if not pts:
                continue
            if s.get("kind") == "bar":
                w = max(1.0, r.width() * dt / T - 1)
                c = QColor(color); c.setAlpha(170)
                for x, y in pts:
                    p.fillRect(QRectF(x, y, w, r.bottom() - y), c)
                continue
            path = QPainterPath(QPointF(*pts[0]))
            for x, y in pts[1:]:
                path.lineTo(x, y)
            if s.get("kind") == "area":
                area = QPainterPath(path)
                area.lineTo(pts[-1][0], r.bottom())
                area.lineTo(pts[0][0], r.bottom())
                c = QColor(color); c.setAlpha(55)
                p.fillPath(area, c)
            p.setPen(QPen(color, 2))
            p.drawPath(path)
        # legenda
        x = r.right()
        p.setFont(_font(10))
        for s in reversed(self.series):
            w = p.fontMetrics().horizontalAdvance(s["label"]) + 26
            x -= w
            p.fillRect(QRectF(x, 9, 14, 4), QColor(s["color"]))
            p.setPen(QColor(COR["text"]))
            p.drawText(QRectF(x + 18, 2, w, 16), Qt.AlignLeft | Qt.AlignVCenter, s["label"])
        # cursor
        i = min(self.cursor, len(self.t) - 1)
        cx = X(self.t[i])
        p.setPen(QPen(QColor(COR["cyan"]), 1.5))
        p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
        for s in self.series:
            v = s["values"][i]
            if v is not None:
                p.setBrush(QColor(s["color"]))
                p.setPen(QPen(QColor(COR["bg"]), 1.5))
                p.drawEllipse(QPointF(cx + (r.width() * dt / T / 2 if s.get("kind") == "bar" else 0), Y(v)), 4, 4)
        p.setPen(QColor(COR["text"]))
        p.setFont(_font(10, True))
        vals = "  ".join(f"{s['values'][i]:.2f}" for s in self.series if s["values"][i] is not None)
        p.drawText(QRectF(r.left() + 6, r.top() + 2, 300, 14), Qt.AlignLeft, f"{vals} {self.unit}")

    def _pick(self, pos):
        if not self.t:
            return
        r = self._plot()
        t = (pos.x() - r.left()) / r.width() * self.t[-1]
        i = min(range(len(self.t)), key=lambda k: abs(self.t[k] - t))
        self.picked.emit(i)

    def mousePressEvent(self, e):
        self._pick(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e.position())


def _dspin(value, lo, hi, step, dec, suffix):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    return s


class ExtendedPage(QWidget):
    """`context()` devolve (projeto, id do reservatório, velocidade máxima, considerar conexões)."""
    applyStep = Signal(object, str)

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.run = None
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(10)

        # ---- parâmetros
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        t = QLabel("PARÂMETROS"); t.setObjectName("h3"); cl.addWidget(t)
        form = QFormLayout()
        form.setVerticalSpacing(5)
        self.pop = QSpinBox(); self.pop.setRange(1, 100000); self.pop.setSuffix(" hab")
        self.qpc = _dspin(200, 10, 2000, 10, 0, " L/hab·dia")
        self.curve = QComboBox(); self.curve.addItems(list(PATTERNS) + ["Personalizada"])
        self.pattern = PatternEditor()
        self.duration = QSpinBox(); self.duration.setRange(6, 24 * 14); self.duration.setSingleStep(24); self.duration.setValue(48); self.duration.setSuffix(" h")
        self.step = QComboBox(); self.step.addItems(["15 min", "30 min", "60 min"]); self.step.setCurrentIndex(1)
        self.vol = _dspin(10, 0.1, 100000, 0.5, 1, " m³")
        self.height = _dspin(1.5, 0.1, 20, 0.1, 2, " m")
        self.level0 = QSpinBox(); self.level0.setRange(0, 100); self.level0.setValue(100); self.level0.setSuffix(" %")
        self.inflow = _dspin(0.5, 0, 10000, 0.05, 2, " m³/h")
        self.cut = QCheckBox("Falta d'água na alimentação")
        self.cut_a = QSpinBox(); self.cut_a.setRange(0, 23); self.cut_a.setValue(8); self.cut_a.setSuffix(" h")
        self.cut_b = QSpinBox(); self.cut_b.setRange(0, 23); self.cut_b.setValue(18); self.cut_b.setSuffix(" h")
        cut_row = QHBoxLayout(); cut_row.addWidget(QLabel("das")); cut_row.addWidget(self.cut_a)
        cut_row.addWidget(QLabel("às")); cut_row.addWidget(self.cut_b)
        cut_w = QWidget(); cut_w.setLayout(cut_row); cut_row.setContentsMargins(0, 0, 0, 0)
        for label, w in (("População", self.pop), ("Consumo per capita", self.qpc), ("Curva de consumo", self.curve)):
            form.addRow(self._lbl(label), w)
        form.addRow(self.pattern)
        for label, w in (("Duração", self.duration), ("Passo", self.step), ("Reservatório (útil)", self.vol),
                         ("Lâmina d'água cheio", self.height), ("Nível inicial", self.level0),
                         ("Alimentação máx.", self.inflow)):
            form.addRow(self._lbl(label), w)
        form.addRow(self.cut)
        form.addRow(cut_w)
        cl.addLayout(form)
        self.info = QLabel(); self.info.setObjectName("sub"); self.info.setWordWrap(True)
        cl.addWidget(self.info)
        self.btn_defaults = QPushButton("Valores sugeridos pelo modelo")
        self.btn_run = QPushButton("Simular"); self.btn_run.setObjectName("pri")
        cl.addWidget(self.btn_defaults)
        cl.addWidget(self.btn_run)
        cl.addStretch(1)
        scroll = QScrollArea(); scroll.setWidget(card); scroll.setWidgetResizable(True); scroll.setFixedWidth(330)
        row.addWidget(scroll)

        # ---- resultados
        right = QVBoxLayout()
        right.setSpacing(10)
        kpis = QHBoxLayout(); kpis.setSpacing(10)
        self.k_cons, self.k_level, self.k_press, self.k_empty, self.k_res = (
            Kpi("Consumo no período"), Kpi("Nível mínimo"), Kpi("Pior pressão"), Kpi("Sem água"), Kpi("Reservação"))
        for k in (self.k_cons, self.k_level, self.k_press, self.k_empty, self.k_res):
            kpis.addWidget(k)
        right.addLayout(kpis)
        charts = QFrame(); charts.setObjectName("card")
        chl = QVBoxLayout(charts)
        self.c_flow = TimeChart("Consumo × alimentação do reservatório", "m³/h")
        self.c_level = TimeChart("Nível do reservatório", "%")
        self.c_press = TimeChart("Pressão nos pontos de utilização", "mca")
        for c in (self.c_flow, self.c_level, self.c_press):
            c.picked.connect(self.set_cursor)
            chl.addWidget(c, 1)
        right.addWidget(charts, 1)
        bar = QFrame(); bar.setObjectName("card")
        bl = QHBoxLayout(bar)
        self.play = QPushButton("▶  Reproduzir"); self.play.setCheckable(True)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.set_cursor)
        self.when = QLabel("—"); self.when.setObjectName("h3"); self.when.setMinimumWidth(130)
        self.now = QLabel(""); self.now.setObjectName("sub"); self.now.setMinimumWidth(330)
        self.btn_apply = QPushButton("Ver este instante no sinótico")
        for w in (self.play, self.slider, self.when, self.now, self.btn_apply):
            bl.addWidget(w, 1 if w is self.slider else 0)
        right.addWidget(bar)
        holder = QWidget(); holder.setLayout(right)
        row.addWidget(holder, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.play.toggled.connect(self._toggle_play)
        self.btn_run.clicked.connect(self.simulate)
        self.btn_defaults.clicked.connect(self.load_defaults)
        self.btn_apply.clicked.connect(self._apply)
        self.curve.currentTextChanged.connect(self._curve_changed)
        self.pattern.changed.connect(lambda: self.curve.setCurrentText("Personalizada"))
        for w in (self.pop, self.qpc, self.vol, self.inflow):
            w.valueChanged.connect(self._update_info)
        self._update_info()

    @staticmethod
    def _lbl(text):
        lb = QLabel(text)
        lb.setObjectName("rotulo")
        return lb

    def _curve_changed(self, name):
        if name in PATTERNS:
            self.pattern.blockSignals(True)
            self.pattern.set_values(PATTERNS[name])
            self.pattern.blockSignals(False)

    def _update_info(self):
        daily = self.pop.value() * self.qpc.value() / 1000
        days = self.vol.value() / daily if daily else 0
        self.info.setText(f"Consumo diário: {daily:.2f} m³ · reservação de {days:.2f} dia(s) "
                          f"(NBR 5626: no mínimo 1 dia de consumo) · alimentação repõe o dia em "
                          f"{(daily / self.inflow.value()) if self.inflow.value() else float('inf'):.1f} h")

    def load_defaults(self):
        project = self.context()[0]
        if project is None:
            return
        cfg = default_config(project)
        self.pop.setValue(cfg.population)
        self.qpc.setValue(cfg.per_capita_lpd)
        self.vol.setValue(cfg.reservoir_m3)
        self.inflow.setValue(cfg.inflow_m3h)

    def config(self) -> EPSConfig:
        _, _, vmax, fittings = self.context()
        return EPSConfig(
            population=self.pop.value(), per_capita_lpd=self.qpc.value(), pattern=list(self.pattern.values),
            duration_h=self.duration.value(), step_min=int(self.step.currentText().split()[0]),
            reservoir_m3=self.vol.value(), reservoir_height_m=self.height.value(),
            initial_level=self.level0.value() / 100, inflow_m3h=self.inflow.value(),
            cut_start_h=self.cut_a.value() if self.cut.isChecked() else -1,
            cut_end_h=self.cut_b.value() if self.cut.isChecked() else -1,
            max_velocity=vmax, auto_fittings=fittings)

    def invalidate(self):
        if self.run:
            self.when.setText("MODELO ALTERADO")
            self.now.setText("Simule de novo para atualizar.")

    def simulate(self):
        project, source, _, _ = self.context()
        if project is None or source is None or not project.pipes:
            self.info.setText("Defina a rede e o reservatório antes de simular.")
            return
        cfg = self.config()
        self.cfg = cfg
        self.run = simulate(project, source, cfg)
        steps, sm = self.run["steps"], self.run["summary"]
        t = [s["t_h"] for s in steps]
        shade = [i for i, s in enumerate(steps) if supply_cut(cfg, s["t_h"]) or s["empty"]]
        self.c_flow.set_data(t, [
            {"label": "consumo", "color": COR["water"], "values": [s["demand_m3h"] for s in steps], "kind": "bar"},
            {"label": "alimentação", "color": COR["ok"], "values": [s["inflow_m3h"] for s in steps], "kind": "line"},
            {"label": "déficit", "color": COR["crit"], "values": [s["deficit_m3h"] or None for s in steps], "kind": "line"},
        ], shade=shade)
        self.c_level.set_data(t, [{"label": "nível", "color": COR["cyan"], "values": [s["level"] * 100 for s in steps],
                                   "kind": "area"}], refs=[(25, COR["warn"], "25 %")], shade=shade, ymin=0, ymax=100)
        self.c_press.set_data(t, [
            {"label": "máxima", "color": COR["violet"], "values": [s["p_max"] for s in steps], "kind": "line"},
            {"label": "mínima", "color": COR["ok"], "values": [s["p_min"] for s in steps], "kind": "line"},
        ], refs=[(MAX_STATIC_PRESSURE_MCA, COR["warn"], f"{MAX_STATIC_PRESSURE_MCA:g} mca (máx. NBR 5626)"),
                 (1.0, COR["crit"], "1 mca")], shade=shade)
        self.k_cons.set(f"{sm['consumed_m3']:.2f} m³", f"{sm['daily_m3']:.2f} m³/dia · pico {sm['peak_demand_m3h']:.2f} m³/h às {int(sm['peak_t'] % 24)}h", "ok")
        self.k_level.set(f"{sm['min_level'] * 100:.0f} %", fmt_t(sm["min_level_t"]),
                         "crit" if sm["min_level"] <= 0.01 else ("warn" if sm["min_level"] < 0.25 else "ok"))
        if sm["worst_p"] is not None:
            self.k_press.set(f"{sm['worst_p']:.2f} mca", f"{sm['worst_p_node']} · {fmt_t(sm['worst_p_t'])}",
                             "crit" if sm["worst_p"] < 1.0 else "ok")
        self.k_empty.set(f"{sm['hours_empty']:.1f} h", f"déficit {sm['deficit_m3']:.2f} m³",
                         "crit" if sm["hours_empty"] > 0 else "ok")
        self.k_res.set(f"{sm['reserve_days']:.2f} dia", "mín. 1 dia (NBR 5626)", "ok" if sm["reserve_days"] >= 1 else "warn")
        self.slider.blockSignals(True)
        self.slider.setRange(0, len(steps) - 1)
        self.slider.blockSignals(False)
        start = max(range(len(steps)), key=lambda i: steps[i]["demand_m3h"])  # começa na hora de pico
        self.set_cursor(start)

    def set_cursor(self, i):
        if not self.run:
            return
        steps = self.run["steps"]
        i = max(0, min(i, len(steps) - 1))
        for c in (self.c_flow, self.c_level, self.c_press):
            c.cursor = i
            c.update()
        if self.slider.value() != i:
            self.slider.blockSignals(True)
            self.slider.setValue(i)
            self.slider.blockSignals(False)
        s = steps[i]
        self.when.setText(fmt_t(s["t_h"]).upper())
        pmin = f"{s['p_min']:.2f}" if s["p_min"] is not None else "—"
        self.now.setText(("SEM ÁGUA · " if s["empty"] else "") +
                         f"consumo {s['demand_m3h']:.2f} m³/h · nível {s['level'] * 100:.0f} % · "
                         f"Q saída {s['q_source_lps']:.2f} L/s · Pmín {pmin} mca")
        self.index = i

    def _toggle_play(self, on):
        self.play.setText("❚❚  Pausar" if on else "▶  Reproduzir")
        if on and self.run:
            self.timer.start(120)
        else:
            self.timer.stop()

    def _advance(self):
        if not self.run:
            return
        n = len(self.run["steps"])
        self.set_cursor((self.index + 1) % n)

    def _apply(self):
        if self.run:
            s = self.run["steps"][self.index]
            self.applyStep.emit(s["result"], fmt_t(s["t_h"]))
