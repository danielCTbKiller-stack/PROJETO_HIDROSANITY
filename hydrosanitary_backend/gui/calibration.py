"""Tela de calibração (Darwin Calibrator do WaterGEMS, como no GWATER): momentos de medição com as leituras
de campo, grupos de rugosidade e de demanda, aptidão e método; mostra as melhores soluções, a comparação
observado × simulado e grava a solução escolhida no projeto."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QScrollArea, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from gui.synoptic import Kpi
from gui.theme import COR, MONO
from services.calibration import (Calibrador, Estudo, Grupo, Leitura, Momento, grupos_por_material,
                                  grupos_por_pavimento)
from services.network_analyzer import NetworkAnalyzer

GR_LABEL = {"pressao": "Pressão (mca)", "vazao": "Vazão (L/s)"}
OBJ_LABEL = {"quadrados": "Soma dos quadrados", "absoluto": "Soma dos absolutos", "maximo": "Maior diferença"}


def _font(px, bold=False):
    f = QFont(MONO)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _table(headers, editable=True):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    if not editable:
        t.setEditTriggers(QTableWidget.NoEditTriggers)
    return t


def _num(t, r, c, default=0.0):
    it = t.item(r, c)
    try:
        return float(it.text().replace(",", ".")) if it and it.text().strip() else default
    except ValueError:
        return default


def _txt(t, r, c):
    it = t.item(r, c)
    return it.text().strip() if it else ""


def _set(t, r, c, v, edit=True):
    it = QTableWidgetItem(f"{v:.3f}" if isinstance(v, float) else str(v))
    if not edit:
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    t.setItem(r, c, it)


class Scatter(QWidget):
    """Observado × simulado: pontos na diagonal = modelo calibrado."""

    def __init__(self):
        super().__init__()
        self.before, self.after = [], []
        self.setMinimumHeight(220)

    def set_data(self, before, after):
        self.before, self.after = before, after
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(COR["cyan"]))
        p.setFont(_font(11, True))
        p.drawText(QRectF(10, 4, 400, 18), Qt.AlignLeft, "OBSERVADO × SIMULADO (PRESSÃO)")
        side = min(self.width() - 70, self.height() - 50)
        r = QRectF(52, 28, side, side)
        pts = self.before + self.after
        if not pts:
            p.setPen(QColor(COR["muted"]))
            p.drawText(r, Qt.AlignCenter, "Rode a calibração")
            return
        vals = [v for xy in pts for v in xy]
        lo, hi = min(vals + [0.0]), max(vals) * 1.08 + 1e-6
        X = lambda v: r.left() + r.width() * (v - lo) / (hi - lo)
        Y = lambda v: r.bottom() - r.height() * (v - lo) / (hi - lo)
        p.setFont(_font(9))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            p.setPen(QPen(QColor(COR["grid"]), 1))
            p.drawLine(QPointF(r.left(), Y(v)), QPointF(r.right(), Y(v)))
            p.drawLine(QPointF(X(v), r.top()), QPointF(X(v), r.bottom()))
            p.setPen(QColor(COR["muted"]))
            p.drawText(QRectF(0, Y(v) - 7, r.left() - 6, 14), Qt.AlignRight | Qt.AlignVCenter, f"{v:.0f}")
            p.drawText(QRectF(X(v) - 20, r.bottom() + 3, 40, 14), Qt.AlignCenter, f"{v:.0f}")
        p.setPen(QPen(QColor(COR["line"]), 1.2, Qt.DashLine))
        p.drawLine(QPointF(X(lo), Y(lo)), QPointF(X(hi), Y(hi)))
        for data, color in ((self.before, COR["warn"]), (self.after, COR["ok"])):
            p.setBrush(QColor(color))
            p.setPen(QPen(QColor(COR["bg"]), 1))
            for o, s in data:
                p.drawEllipse(QPointF(X(o), Y(s)), 4.5, 4.5)
        p.setFont(_font(10))
        for i, (label, color) in enumerate((("antes", COR["warn"]), ("calibrado", COR["ok"]))):
            x = r.right() + 8
            p.fillRect(QRectF(x, r.top() + 4 + i * 18, 10, 10), QColor(color))
            p.setPen(QColor(COR["text"]))
            p.drawText(QRectF(x + 14, r.top() + i * 18, 80, 18), Qt.AlignLeft | Qt.AlignVCenter, label)


class CalibrationPage(QWidget):
    """`context()` devolve (projeto, id do reservatório, pressão na fonte, considerar conexões, itens selecionados)."""
    before = Signal()
    applied = Signal(str)

    def __init__(self, context):
        super().__init__()
        self.context = context
        self.cal = None
        self.run = None
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 10, 10, 10)
        row.setSpacing(10)

        # ---- estudo
        card = QFrame(); card.setObjectName("card")
        cl = QVBoxLayout(card)
        t = QLabel("MOMENTOS DE MEDIÇÃO"); t.setObjectName("h3"); cl.addWidget(t)
        self.moments = _table(["Momento", "Fator demanda", "P. fonte (mca)"])
        self.moments.setMaximumHeight(130)
        cl.addWidget(self.moments)
        cl.addLayout(self._buttons((("+ Momento", lambda: self.add_moment()), ("Remover", lambda: self._remove(self.moments)))))

        t = QLabel("LEITURAS DE CAMPO"); t.setObjectName("h3"); cl.addWidget(t)
        self.readings = _table(["Momento", "Elemento", "Grandeza", "Observado", "Peso"])
        self.readings.setMinimumHeight(170)
        cl.addWidget(self.readings)
        cl.addLayout(self._buttons((("+ Da seleção", self.add_from_selection), ("+ Linha", lambda: self.add_reading()),
                                    ("Remover", lambda: self._remove(self.readings)))))
        self.synth = QPushButton("Leituras de exemplo (do modelo × rugosidade)")
        self.synth.setToolTip("Preenche as leituras com o modelo calculado com a perda de carga multiplicada, "
                              "para conferir se o calibrador encontra o valor")
        self.synth_k = QDoubleSpinBox(); self.synth_k.setRange(0.3, 5); self.synth_k.setValue(1.6); self.synth_k.setSingleStep(0.1)
        self.synth_k.setPrefix("× ")
        sr = QHBoxLayout(); sr.addWidget(self.synth, 1); sr.addWidget(self.synth_k)
        cl.addLayout(sr)

        t = QLabel("GRUPOS"); t.setObjectName("h3"); cl.addWidget(t)
        self.groups = _table(["Grupo", "Itens", "Mín.", "Máx."])
        self.groups.setMinimumHeight(150)
        cl.addWidget(self.groups)
        cl.addLayout(self._buttons((("Rugosidade por material", lambda: self.set_groups("material")),
                                    ("por pavimento", lambda: self.set_groups("pav")))))
        cl.addLayout(self._buttons((("+ Demanda por pavimento", lambda: self.set_groups("dem")),
                                    ("Remover", lambda: self._remove(self.groups)))))

        t = QLabel("APTIDÃO E MÉTODO"); t.setObjectName("h3"); cl.addWidget(t)
        form = QFormLayout(); form.setVerticalSpacing(5)
        self.obj = QComboBox()
        for k, v in OBJ_LABEL.items():
            self.obj.addItem(v, k)
        self.method = QComboBox(); self.method.addItem("Genético (evolução diferencial)", "genetico")
        self.method.addItem("Gradiente (mínimos quadrados)", "gradiente")
        self.mca_pt = QDoubleSpinBox(); self.mca_pt.setRange(0.01, 100); self.mca_pt.setValue(1.0); self.mca_pt.setSuffix(" mca")
        self.lps_pt = QDoubleSpinBox(); self.lps_pt.setRange(0.001, 100); self.lps_pt.setDecimals(3); self.lps_pt.setValue(0.1); self.lps_pt.setSuffix(" L/s")
        self.gens = QSpinBox(); self.gens.setRange(5, 2000); self.gens.setValue(60)
        self.pop = QSpinBox(); self.pop.setRange(5, 200); self.pop.setValue(15)
        self.nsol = QSpinBox(); self.nsol.setRange(1, 20); self.nsol.setValue(5)
        for label, w in (("Aptidão", self.obj), ("Método", self.method), ("mca por ponto", self.mca_pt),
                         ("L/s por ponto", self.lps_pt), ("Gerações máx.", self.gens), ("População", self.pop),
                         ("Soluções", self.nsol)):
            lb = QLabel(label); lb.setObjectName("rotulo")
            form.addRow(lb, w)
        cl.addLayout(form)
        self.info = QLabel(); self.info.setObjectName("sub"); self.info.setWordWrap(True)
        cl.addWidget(self.info)
        self.btn_run = QPushButton("Calibrar"); self.btn_run.setObjectName("pri")
        cl.addWidget(self.btn_run)
        cl.addStretch(1)
        scroll = QScrollArea(); scroll.setWidget(card); scroll.setWidgetResizable(True); scroll.setFixedWidth(450)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        row.addWidget(scroll)

        # ---- resultados
        right = QVBoxLayout(); right.setSpacing(10)
        kpis = QHBoxLayout(); kpis.setSpacing(10)
        self.k_before, self.k_after, self.k_err, self.k_eval = (
            Kpi("Aptidão inicial"), Kpi("Melhor aptidão"), Kpi("Maior diferença"), Kpi("Avaliações"))
        for k in (self.k_before, self.k_after, self.k_err, self.k_eval):
            kpis.addWidget(k)
        right.addLayout(kpis)
        mid = QHBoxLayout(); mid.setSpacing(10)
        sc = QFrame(); sc.setObjectName("card")
        sl = QVBoxLayout(sc)
        t = QLabel("MELHORES SOLUÇÕES"); t.setObjectName("h3"); sl.addWidget(t)
        self.solutions = _table(["#", "Aptidão"], editable=False)
        self.solutions.setSelectionMode(QAbstractItemView.SingleSelection)
        sl.addWidget(self.solutions, 1)
        self.btn_apply = QPushButton("Gravar solução no projeto"); self.btn_apply.setObjectName("pri")
        self.btn_apply.setEnabled(False)
        sl.addWidget(self.btn_apply)
        mid.addWidget(sc, 3)
        pc = QFrame(); pc.setObjectName("card")
        self.scatter = Scatter()
        QVBoxLayout(pc).addWidget(self.scatter)
        mid.addWidget(pc, 2)
        right.addLayout(mid, 1)
        cc = QFrame(); cc.setObjectName("card")
        ccl = QVBoxLayout(cc)
        t = QLabel("OBSERVADO × SIMULADO (SOLUÇÃO SELECIONADA)"); t.setObjectName("h3"); ccl.addWidget(t)
        self.compare = _table(["Momento", "Elemento", "Grandeza", "Observado", "Antes", "Calibrado", "Diferença"],
                              editable=False)
        ccl.addWidget(self.compare)
        right.addWidget(cc, 1)
        holder = QWidget(); holder.setLayout(right)
        row.addWidget(holder, 1)

        self.btn_run.clicked.connect(self.calibrate)
        self.btn_apply.clicked.connect(self.apply)
        self.synth.clicked.connect(self.synthetic)
        self.solutions.currentCellChanged.connect(lambda r, *_: self.show_solution(r))
        self.add_moment(5.0)  # a janela ainda está sendo montada: sem context() aqui

    @staticmethod
    def _buttons(items):
        h = QHBoxLayout()
        for text, slot in items:
            b = QPushButton(text)
            b.clicked.connect(slot)
            h.addWidget(b)
        return h

    @staticmethod
    def _remove(t):
        for r in sorted({i.row() for i in t.selectedIndexes()}, reverse=True):
            t.removeRow(r)

    def _moment_names(self):
        return [_txt(self.moments, r, 0) for r in range(self.moments.rowCount())]

    # ------------------------------------------------------------------ edição do estudo
    def add_moment(self, pressure=None):
        r = self.moments.rowCount()
        self.moments.insertRow(r)
        pressure = self.context()[2] if pressure is None else pressure
        for c, v in enumerate((f"M{r + 1}" if r else "Pico", 1.0, pressure)):
            _set(self.moments, r, c, v)

    def add_reading(self, elem="", grandeza="pressao", valor=0.0):
        r = self.readings.rowCount()
        self.readings.insertRow(r)
        names = self._moment_names() or ["Pico"]
        mo = QComboBox(); mo.addItems(names)
        gr = QComboBox()
        for k, v in GR_LABEL.items():
            gr.addItem(v, k)
        gr.setCurrentIndex(list(GR_LABEL).index(grandeza))
        self.readings.setCellWidget(r, 0, mo)
        _set(self.readings, r, 1, elem)
        self.readings.setCellWidget(r, 2, gr)
        _set(self.readings, r, 3, float(valor))
        _set(self.readings, r, 4, 1.0)

    def add_from_selection(self):
        sel = self.context()[4]
        added = 0
        for kind, ident in sel:
            if kind in ("node", "pipe"):
                self.add_reading(ident, "pressao" if kind == "node" else "vazao")
                added += 1
        self.info.setText(f"{added} leitura(s) adicionada(s) da seleção. Digite os valores medidos."
                          if added else "Selecione nós (pressão) ou trechos (vazão) no MODELO e volte aqui.")

    def set_groups(self, how):
        project = self.context()[0]
        if project is None:
            return
        if how == "material":
            new = grupos_por_material(project)
        elif how == "pav":
            new = grupos_por_pavimento(project)
        else:
            new = grupos_por_pavimento(project, demanda=True)
        keep = [self._group(r) for r in range(self.groups.rowCount())]
        tipo = "Demanda" if how == "dem" else "Rugosidade"
        keep = [g for g in keep if not g[0].nome.startswith(tipo)]  # troca os grupos do mesmo tipo
        self.groups.setRowCount(0)
        for g, ids in keep + [(g, g.ids) for g in new]:
            r = self.groups.rowCount()
            self.groups.insertRow(r)
            _set(self.groups, r, 0, g.nome, edit=False)
            _set(self.groups, r, 1, len(ids), edit=False)
            self.groups.item(r, 0).setData(Qt.UserRole, list(ids))
            _set(self.groups, r, 2, float(g.min))
            _set(self.groups, r, 3, float(g.max))

    def _group(self, r):
        ids = self.groups.item(r, 0).data(Qt.UserRole) or []
        return Grupo(_txt(self.groups, r, 0), list(ids), _num(self.groups, r, 2, 0.5), _num(self.groups, r, 3, 3.0)), ids

    def synthetic(self):
        """Leituras de exemplo: pressões dos pontos de consumo com a perda de carga × k."""
        project, source, p0, fittings, _ = self.context()
        if project is None or source is None:
            return
        k = self.synth_k.value()
        old = {pid: p.roughness_factor for pid, p in project.pipes.items()}
        try:
            for p in project.pipes.values():
                p.roughness_factor *= k
            res = NetworkAnalyzer(project).analyze(source, p0, auto_fittings=fittings)
        finally:
            for pid, p in project.pipes.items():
                p.roughness_factor = old[pid]
        pts = [n for n in project.nodes if project.nodes[n].fixtures]
        pts = pts[::max(1, len(pts) // 8)][:8]
        self.readings.setRowCount(0)
        for n in pts:
            self.add_reading(n, "pressao", round(res["nodes"][n]["pressure_mca"], 2))
        if not self.groups.rowCount():
            self.set_groups("material")
        self.info.setText(f"{len(pts)} leituras de exemplo com a perda de carga × {k:g}. "
                          "O calibrador deve encontrar esse multiplicador.")

    def study(self) -> Estudo:
        moments = {}
        for r in range(self.moments.rowCount()):
            name = _txt(self.moments, r, 0) or f"M{r + 1}"
            moments[name] = Momento(name, _num(self.moments, r, 1, 1.0), _num(self.moments, r, 2, self.context()[2]))
        first = next(iter(moments.values()), None)
        for r in range(self.readings.rowCount()):
            elem = _txt(self.readings, r, 1)
            if not elem:
                continue
            mo = moments.get(self.readings.cellWidget(r, 0).currentText(), first)
            mo.leituras.append(Leitura(elem, self.readings.cellWidget(r, 2).currentData(),
                                       _num(self.readings, r, 3), _num(self.readings, r, 4, 1.0)))
        gc, gd = [], []
        for r in range(self.groups.rowCount()):
            g, _ = self._group(r)
            (gd if g.nome.startswith("Demanda") else gc).append(g)
        return Estudo(list(moments.values()), gc, gd, objetivo=self.obj.currentData(),
                      mca_por_ponto=self.mca_pt.value(), lps_por_ponto=self.lps_pt.value(),
                      metodo=self.method.currentData(), geracoes=self.gens.value(), populacao=self.pop.value(),
                      n_solucoes=self.nsol.value())

    # ------------------------------------------------------------------ cálculo
    def calibrate(self):
        project, source, p0, fittings, _ = self.context()
        if project is None or source is None or not project.pipes:
            self.info.setText("Defina a rede e o reservatório antes de calibrar.")
            return
        try:
            self.cal = Calibrador(project, source, p0, self.study(), auto_fittings=fittings)
        except ValueError as e:
            self.info.setText(f"Estudo incompleto: {e}")
            return
        self.btn_run.setEnabled(False)
        self.info.setText("Calibrando…")

        def progress(n, best):
            self.info.setText(f"Calibrando… {n} avaliações · melhor aptidão {best:.4g}")
            QApplication.processEvents()
            return False

        try:
            self.run = self.cal.rodar(progress)
        except ValueError as e:
            self.info.setText(str(e))
            return
        finally:
            self.btn_run.setEnabled(True)
        self._before_rows = self.cal.tabela(self.cal.inicial())
        sols = self.run["solucoes"]
        names = list(sols[0]["grupos"]) if sols else []
        self.solutions.setColumnCount(2 + len(names))
        self.solutions.setHorizontalHeaderLabels(["#", "Aptidão"] + [n.split(" · ", 1)[-1] for n in names])
        self.solutions.setRowCount(len(sols))
        for i, s in enumerate(sols):
            _set(self.solutions, i, 0, i + 1, edit=False)
            _set(self.solutions, i, 1, f"{s['aptidao']:.4g}", edit=False)
            for c, n in enumerate(names):
                _set(self.solutions, i, 2 + c, f"× {s['grupos'][n]:.3f}", edit=False)
        self.k_before.set(f"{self.run['inicial']:.4g}", OBJ_LABEL[self.cal.e.objetivo], "warn")
        if sols:
            self.k_after.set(f"{sols[0]['aptidao']:.4g}", "solução 1", "ok")
        self.k_eval.set(str(self.run["avaliacoes"]), self.method.currentText().split(" (")[0], "")
        self.btn_apply.setEnabled(bool(sols))
        self.info.setText(f"Pronto: {len(sols)} solução(ões). Escolha uma e grave no projeto.")
        self.solutions.selectRow(0)
        self.show_solution(0)

    def show_solution(self, i):
        if not self.run or not (0 <= i < len(self.run["solucoes"])):
            return
        rows = self.cal.tabela(self.run["solucoes"][i]["x"])
        self.compare.setRowCount(len(rows))
        worst = 0.0
        for r, (a, b) in enumerate(zip(self._before_rows, rows)):
            for c, v in enumerate((b["momento"], b["elemento"], b["unidade"], f"{b['observado']:.2f}",
                                   f"{a['simulado']:.2f}", f"{b['simulado']:.2f}", f"{b['diferenca']:+.2f}")):
                _set(self.compare, r, c, v, edit=False)
            worst = max(worst, abs(b["diferenca"]))
        self.k_err.set(f"{worst:.2f}", "maior |simulado − observado|", "ok" if worst < 1 else "warn")
        press = lambda rs: [(x["observado"], x["simulado"]) for x in rs if x["grandeza"] == "pressao"]
        self.scatter.set_data(press(self._before_rows), press(rows))

    def apply(self):
        if not self.run:
            return
        i = max(0, self.solutions.currentRow())
        self.before.emit()
        self.cal.aplicar(self.run["solucoes"][i]["x"])
        self.btn_apply.setEnabled(False)
        self.info.setText("Solução gravada: rugosidade nos trechos (Propriedades → fator de rugosidade) e pesos "
                          "dos aparelhos. Ctrl+Z desfaz.")
        self.applied.emit(f"Calibração: solução {i + 1} gravada no projeto")
