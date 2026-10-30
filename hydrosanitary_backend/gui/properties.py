"""Painel de propriedades: edita os atributos do elemento selecionado no modelo."""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPushButton, QVBoxLayout, QWidget)

from core.entities import Fixture
from core.standards import (COMMERCIAL_DIAMETERS, EQUIVALENT_LENGTH_TABLE, FITTING_LABELS, FIXTURE_DATABASE,
                            FIXTURE_INFO, MATERIALS)


def _spin(value, lo=-1000.0, hi=1000.0, step=0.1, dec=2, suffix=""):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)  # só aplica ao confirmar (Enter, setas ou sair do campo)
    return s


class PropertiesPanel(QWidget):
    before = Signal()
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.canvas = None
        self.col = QVBoxLayout(self)
        self.col.setContentsMargins(10, 10, 10, 10)
        self.title = QLabel("NADA SELECIONADO")
        self.title.setObjectName("h3")
        self.col.addWidget(self.title)
        self.body = QWidget()
        self.col.addWidget(self.body)
        self.col.addStretch(1)
        self.form = None

    def _reset(self, title):
        self.title.setText(title)
        self.col.removeWidget(self.body)
        self.body.hide()
        self.body.deleteLater()
        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(0, 6, 0, 0)
        self.form.setVerticalSpacing(6)
        self.col.insertWidget(1, self.body)

    def _apply(self, fn):
        self.before.emit()
        fn()
        self.changed.emit()

    def _row(self, label, widget):
        lb = QLabel(label)
        lb.setObjectName("rotulo")
        self.form.addRow(lb, widget)
        return widget

    def _info(self, text):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setObjectName("sub")
        self.form.addRow(lb)

    def show_selection(self, canvas):
        self.canvas = canvas
        items = canvas.selected_items()
        if len(items) > 1:
            self._multi(items)
            return
        sel = canvas.selection
        obj = canvas.selected_object()
        if obj is None:
            self._reset("NADA SELECIONADO")
            self._info("Use a ferramenta Selecionar e clique num tubo, nó, aparelho, parede ou cômodo para editar "
                       "os atributos. Del apaga o elemento; Ctrl+Z desfaz.")
            return
        getattr(self, "_" + sel[0])(obj, sel[1])

    # ---------------------------------------------------------------- vários elementos
    def _multi(self, items):
        p = self.canvas.project
        self._reset(f"{len(items)} ELEMENTOS")
        names = {"node": "nó(s)/aparelho(s)", "pipe": "trecho(s)", "wall": "parede(s)", "room": "cômodo(s)"}
        counts = {}
        for kind, _ in items:
            counts[kind] = counts.get(kind, 0) + 1
        self._info(" · ".join(f"{n} {names[k]}" for k, n in counts.items()))
        walls = [p.walls[k] for kind, k in items if kind == "wall" and k < len(p.walls)]
        pipes = [p.pipes[k] for kind, k in items if kind == "pipe" and k in p.pipes]
        if walls:  # edição em lote: vale para todas as paredes selecionadas
            kind = QComboBox()
            kind.addItems(["(manter)", "externa", "interna"])
            kind.currentTextChanged.connect(lambda t: t != "(manter)" and self._apply(
                lambda: [setattr(w, "kind", t) for w in walls]))
            self._row("Tipo das paredes", kind)
            for label, attr, lo, hi in (("Espessura", "thickness_m", 0.03, 2), ("Altura", "height_m", 0.1, 50)):
                s = _spin(walls[0].thickness_m if attr == "thickness_m" else walls[0].height_m, lo, hi, 0.01, 2, " m")
                s.valueChanged.connect(lambda v, a=attr: self._apply(lambda: [setattr(w, a, v) for w in walls]))
                self._row(label, s)
        if pipes:
            dn = QComboBox()
            dn.addItems(["(manter)"] + [f"{v:g}" for v in COMMERCIAL_DIAMETERS])
            dn.currentTextChanged.connect(lambda t: t != "(manter)" and self._apply(
                lambda: [setattr(x, "diameter_mm", float(t)) for x in pipes]))
            self._row("Diâmetro dos trechos", dn)
            mat = QComboBox()
            mat.addItems(["(manter)"] + MATERIALS)
            mat.currentTextChanged.connect(lambda t: t != "(manter)" and self._apply(
                lambda: [setattr(x, "material", t) for x in pipes]))
            self._row("Material", mat)
        delete = QPushButton(f"Excluir os {len(items)} elementos")
        delete.setStyleSheet("QPushButton{border-color:#8a2a38;color:#ff6b7a;}")
        delete.clicked.connect(self.canvas.delete_selection)
        self.form.addRow(delete)
        self._info("Del também exclui. Ctrl+clique soma ou retira um elemento da seleção.")

    # ---------------------------------------------------------------- trecho
    def _pipe(self, p, pid):
        self._reset(f"TRECHO {pid}")
        dn = QComboBox()
        values = sorted(set(COMMERCIAL_DIAMETERS) | {p.diameter_mm})
        dn.addItems([f"{v:g}" for v in values])
        dn.setCurrentText(f"{p.diameter_mm:g}")
        dn.currentTextChanged.connect(lambda t: self._apply(lambda: setattr(p, "diameter_mm", float(t))))
        self._row("Diâmetro (mm)", dn)
        mat = QComboBox()
        mat.addItems(sorted(set(MATERIALS) | {p.material}, key=lambda m: MATERIALS.index(m) if m in MATERIALS else 99))
        mat.setCurrentText(p.material)
        mat.currentTextChanged.connect(lambda t: self._apply(lambda: setattr(p, "material", t)))
        self._row("Material", mat)
        L = _spin(p.length_m, 0.01, 10000, 0.1, 2, " m")
        L.valueChanged.connect(lambda v: self._apply(lambda: setattr(p, "length_m", v)))
        self._row("Comprimento", L)
        leq = _spin(p.equivalent_length_m, 0, 1000, 0.1, 2, " m")
        leq.valueChanged.connect(lambda v: self._apply(lambda: setattr(p, "equivalent_length_m", v)))
        self._row("Leq adicional", leq)
        geo = QPushButton("Comprimento pela geometria")
        nodes = self.canvas.project.nodes

        def from_geometry():
            a, b = nodes[p.start_node_id], nodes[p.end_node_id]
            p.length_m = round(math.dist((a.x_m, a.y_m, a.elevation_m), (b.x_m, b.y_m, b.elevation_m)), 3)
        geo.clicked.connect(lambda: (self._apply(from_geometry), self.show_selection(self.canvas)))
        self.form.addRow(geo)
        self._info(f"De {p.start_node_id} até {p.end_node_id}")
        r = (self.canvas.result or {}).get("pipes", {}).get(pid)
        if r:
            self._info(f"Q = {r['flow_lps']:.3f} L/s · v = {r['velocity_ms']:.2f} m/s\n"
                       f"hf = {r['head_loss_mca']:.3f} mca · Leq total = {r['equivalent_length_m']:.2f} m")

    # ---------------------------------------------------------------- nó / aparelho / peça
    def _node(self, n, nid):
        kind = "RESERVATÓRIO" if nid == self.canvas.source_id else ("APARELHO" if n.fixtures else "NÓ")
        self._reset(f"{kind} {nid}")
        z = _spin(n.elevation_m, -100, 1000, 0.05, 3, " m")
        z.valueChanged.connect(lambda v: self._apply(lambda: setattr(n, "elevation_m", v)))
        self._row("Cota", z)
        x = _spin(n.x_m, -1e5, 1e5, 0.1, 3, " m")
        x.valueChanged.connect(lambda v: self._apply(lambda: setattr(n, "x_m", v)))
        self._row("X", x)
        y = _spin(n.y_m, -1e5, 1e5, 0.1, 3, " m")
        y.valueChanged.connect(lambda v: self._apply(lambda: setattr(n, "y_m", v)))
        self._row("Y", y)
        room = QComboBox()
        room.addItems([""] + list(self.canvas.project.rooms))
        room.setCurrentText(n.room)
        room.currentTextChanged.connect(lambda t: self._apply(lambda: setattr(n, "room", t)))
        self._row("Cômodo", room)

        self._list_editor("Aparelhos", [f.name for f in n.fixtures],
                          {k: v[0] for k, v in FIXTURE_INFO.items() if k in FIXTURE_DATABASE},
                          add=lambda k: n.fixtures.append(Fixture(k, FIXTURE_DATABASE[k]["weight"],
                                                                  FIXTURE_DATABASE[k]["min_pressure"])),
                          remove=lambda i: n.fixtures.pop(i))
        self._list_editor("Peças", list(n.fittings), {k: FITTING_LABELS.get(k, k) for k in EQUIVALENT_LENGTH_TABLE},
                          add=lambda k: n.fittings.append(k), remove=lambda i: n.fittings.pop(i))
        vrp = _spin(n.prv_setpoint_mca, 0, 200, 1, 1, " mca")
        vrp.setSpecialValueText("sem VRP")

        def set_vrp(v):
            n.prv_setpoint_mca = v
            if v > 0 and "valvula_redutora_pressao" not in n.fittings:
                n.fittings.append("valvula_redutora_pressao")
            if v == 0 and "valvula_redutora_pressao" in n.fittings:
                n.fittings.remove("valvula_redutora_pressao")
        vrp.valueChanged.connect(lambda v: (self._apply(lambda: set_vrp(v)), self.show_selection(self.canvas)))
        self._row("VRP regulada", vrp)
        if nid != self.canvas.source_id:
            src = QPushButton("Usar como reservatório")
            src.clicked.connect(lambda: (self._apply(lambda: setattr(self.canvas, "source_id", nid)),
                                         self.show_selection(self.canvas)))
            self.form.addRow(src)
        r = (self.canvas.result or {}).get("nodes", {}).get(nid)
        if r:
            txt = f"Pressão = {r['pressure_mca']:.2f} mca (mínima {r['required_mca']:.2f})"
            if r.get("prv_reduction_mca"):
                txt += f"\nVRP reduziu {r['prv_reduction_mca']:.2f} mca"
            self._info(txt)

    def _list_editor(self, title, keys, options, add, remove):
        lst = QListWidget()
        lst.setMaximumHeight(86)
        for k in keys:
            lst.addItem(options.get(k, k))
        self._row(title, lst)
        combo = QComboBox()
        for k, label in options.items():
            combo.addItem(label, k)
        plus, minus = QPushButton("+"), QPushButton("–")
        for b in (plus, minus):
            b.setFixedWidth(30)
        row = QHBoxLayout()
        row.addWidget(combo, 1)
        row.addWidget(plus)
        row.addWidget(minus)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.form.addRow("", holder)
        plus.clicked.connect(lambda: (self._apply(lambda: add(combo.currentData())), self.show_selection(self.canvas)))
        minus.clicked.connect(lambda: lst.currentRow() >= 0 and (
            self._apply(lambda: remove(lst.currentRow())), self.show_selection(self.canvas)))

    # ---------------------------------------------------------------- arquitetura
    def _wall(self, w, idx):
        self._reset(f"PAREDE {idx + 1}")
        kind = QComboBox()
        kind.addItems(["externa", "interna"])
        kind.setCurrentText(w.kind)
        kind.currentTextChanged.connect(lambda t: self._apply(lambda: setattr(w, "kind", t)))
        self._row("Tipo", kind)
        for label, attr, lo, hi, suf in (("Espessura", "thickness_m", 0.03, 2, " m"), ("Altura", "height_m", 0.1, 50, " m"),
                                         ("Cota da base", "z_base_m", -100, 1000, " m")):
            s = _spin(getattr(w, attr), lo, hi, 0.01 if attr == "thickness_m" else 0.1, 2, suf)
            s.valueChanged.connect(lambda v, a=attr: self._apply(lambda: setattr(w, a, v)))
            self._row(label, s)
        self._info(f"Comprimento: {math.hypot(w.x1_m - w.x0_m, w.y1_m - w.y0_m):.2f} m")
        open_2d = QPushButton("Desenhar tubulação nesta parede (2D)")
        open_2d.setObjectName("pri")
        open_2d.clicked.connect(lambda: self.canvas.enter_wall_view(idx))
        self.form.addRow(open_2d)
        self._info("Dica: duplo clique na parede também abre a vista 2D.")

    def _room(self, room, name):
        self._reset("CÔMODO")
        edit = QLineEdit(room.name)
        project = self.canvas.project

        def rename():
            new = edit.text().strip()
            if not new or new == room.name or new in project.rooms:
                return
            old = room.name
            room.name = new
            project.rooms = {(new if k == old else k): v for k, v in project.rooms.items()}
            for n in project.nodes.values():
                if n.room == old:
                    n.room = new
            self.canvas.selection = ("room", new)
        edit.editingFinished.connect(lambda: self._apply(rename))
        self._row("Nome", edit)
        z = _spin(room.z_floor_m, -100, 1000, 0.05, 2, " m")
        z.valueChanged.connect(lambda v: self._apply(lambda: setattr(room, "z_floor_m", v)))
        self._row("Cota do piso", z)
        pts = room.polygon
        area = abs(sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))) / 2
        n_fix = sum(len(n.fixtures) for n in project.nodes.values() if n.room == room.name)
        self._info(f"Área: {area:.2f} m² · {n_fix} aparelho(s)")
