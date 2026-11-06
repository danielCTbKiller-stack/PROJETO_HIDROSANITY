"""Área de desenho do modelo: planta ou isométrica 2.5D, com ferramentas de CAD.

Desenha-se sempre no plano do pavimento ativo (na isométrica o clique é projetado de volta
nesse plano). Paredes são prismas com espessura e altura do pavimento; tubos, aparelhos e
peças ficam por cima. Botão do meio arrasta a vista, roda = zoom, Shift/F8 = ortogonal.
"""
import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QInputDialog, QLabel

from core.entities import Fixture, Node, Pipe, Room, Wall
from core.standards import FIXTURE_DATABASE, FIXTURE_INFO, FITTING_LABELS, MAX_STATIC_PRESSURE_MCA
from gui.symbols import draw_fitting, draw_fixture, draw_source
from gui.theme import COR, MONO
from services.project_manager import ProjectManager

SCALE = 60.0  # pixels por metro (zoom 1)
COS30, SIN30 = math.cos(math.radians(30)), math.sin(math.radians(30))
SNAP_PX = 12
ROOM_TINTS = ["#35d0ff", "#ffb547", "#3ddc97", "#a78bfa", "#ff6b7a", "#74c0fc"]
WALL_COLORS = {"externa": "#c9d3df", "interna": "#8fa5bd"}
VEL_COLORS = {"IDLE": "#3b5b85", "LOW": "#74c0fc", "OK": "#3ddc97", "HIGH": "#ff6b7a", "NONE": "#1d8fd6"}

TOOLS = {
    "select": "Selecionar: clique num elemento para ver/editar; arraste nós para mover. Del apaga.",
    "pipe": "Tubo: clique os pontos (encaixa em nós e tubos); botão direito ou Esc termina.",
    "riser": "Prumada: clique num ponto e informe a cota final do tubo vertical.",
    "fixture": "Aparelho: clique num nó, num tubo ou num ponto livre.",
    "fitting": "Peça: clique num nó ou sobre um tubo (o tubo é dividido no ponto).",
    "source": "Reservatório: clique no ponto que alimenta a rede.",
    "wall": "Parede: clique os vértices; botão direito ou Esc termina. Shift = ortogonal.",
    "rect": "Retângulo de paredes: clique dois cantos opostos.",
    "room": "Cômodo: clique os vértices; botão direito fecha o contorno.",
}


class Symbol(QGraphicsItem):
    """Símbolo com tamanho fixo na tela, desenhado por uma função (peças, aparelhos, rótulos)."""

    def __init__(self, painter_fn, size, extent=None):
        super().__init__()
        self.fn, self.s, self.e = painter_fn, size, extent or size
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)

    def boundingRect(self):
        return QRectF(-self.e, -self.e, 2 * self.e, 2 * self.e)

    def paint(self, p, *_):
        p.setRenderHint(QPainter.Antialiasing)
        self.fn(p, self.s)


class ModelCanvas(QGraphicsView):
    beforeChange = Signal()
    changed = Signal()
    selectionChanged = Signal(object)
    cursorMoved = Signal(float, float, float)
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.scene().setSceneRect(-1e5, -1e5, 2e5, 2e5)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor(COR["bg"]))
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.project: Optional[ProjectManager] = None
        self.source_id: Optional[str] = None
        self.result: Optional[dict] = None
        self.max_velocity = 3.0
        self.mode = "iso"
        self.rotation = 0
        self.active_floor = 0
        self.cut_above = True       # isométrica: esconde os pavimentos acima do ativo
        self.wall_alpha = 0.9
        self.ortho = False
        self.snap_grid = True
        self.tool = "select"
        self.opts = {"dn": 25.0, "material": "PVC Soldável", "pipe_h": 2.2, "fixture": "chuveiro_eletrico",
                     "fitting": "registro_gaveta", "wall_kind": "externa", "thk_externa": 0.20,
                     "thk_interna": 0.12, "grid": 0.10, "elev_off": 0.0}
        self.xray = False           # True: tubulação sempre por cima das paredes
        self._elev = None           # vista 2D da parede de trabalho (dados da parede)
        self._prev_mode = "iso"
        self.banner = QLabel()      # faixa da vista da parede (a janela coloca acima do desenho)
        self.banner.setObjectName("chip")
        self.banner.hide()
        self.selection = None       # ("node"|"pipe"|"wall"|"room", chave): o elemento em edição
        self.multi = []             # seleção por janela / Ctrl+clique (vários elementos)
        self.hover = None           # elemento sob o cursor (destaque na ferramenta Selecionar)
        self._band = None           # janela de seleção em andamento (ponto inicial, na tela)
        self._wall_polys = []       # (índice da parede, polígono na cena), do fundo para a frente
        self._c = (0.0, 0.0)
        self._chain = []            # pontos/nós da ferramenta em uso
        self._temp = []
        self._pan = None
        self._drag = None
        self.ask_double = lambda title, label, value: QInputDialog.getDouble(self, title, label, value, -1000, 1000, 2)
        self.ask_text = lambda title, label, value: QInputDialog.getText(self, title, label, text=value)

    # ================================================================ estado
    def set_project(self, project: ProjectManager, source_id: Optional[str], fit=True):
        self.project, self.source_id, self.result = project, source_id, None
        project.ensure_floors()
        self.active_floor = min(self.active_floor, len(project.floors) - 1)
        self.selection, self._chain, self.multi, self.hover = None, [], [], None
        if self.mode == "elev":  # a parede da vista 2D pode não existir no projeto novo
            self.mode, self._elev = self._prev_mode, None
            self.banner.hide()
        self._c = self._center()
        self.redraw()
        if fit:
            self.fit()

    def show_project(self, project, source_id, result=None):  # compatibilidade com a vista antiga
        if project is not self.project:
            self.set_project(project, source_id)
        self.source_id = source_id
        self.set_result(result)

    def set_result(self, result: Optional[dict], max_velocity: Optional[float] = None):
        self.result = result
        if max_velocity:
            self.max_velocity = max_velocity
        self.redraw()

    def set_mode(self, mode):
        if self.mode == "elev":
            self._elev = None
            self.banner.hide()
        self.mode = mode
        self.redraw()
        self.fit()

    def rotate_view(self):
        if self.mode == "elev":  # na vista da parede, "girar" mostra o outro lado
            self.flip_wall_view()
            return
        self.rotation = (self.rotation + 1) % 4
        self.redraw()
        self.fit()

    def set_active_floor(self, i):
        if self.project and 0 <= i < len(self.project.floors):
            if self.mode == "elev" and i != self.active_floor:
                self.set_mode(self._prev_mode)
            self.active_floor = i
            self._chain = []
            self.redraw()

    def set_tool(self, tool):
        if self.mode == "elev" and tool in ("wall", "rect", "room"):
            self.exit_wall_view()  # paredes e cômodos se desenham na planta/isométrica
        self.tool = tool
        self._chain = []
        self._clear_temp()
        self.setCursor(Qt.ArrowCursor if tool == "select" else Qt.CrossCursor)
        self.message.emit(TOOLS.get(tool, ""))
        if self.project is not None:
            self.redraw()  # a grade acompanha a altura de desenho da ferramenta

    # ================================================================ vista da parede (2D)
    def enter_wall_view(self, idx, flip=None):
        """Mostra a parede de pé, em 2D (comprimento × altura), para desenhar a tubulação nela."""
        w = self.project.walls[idx]
        L = math.hypot(w.x1_m - w.x0_m, w.y1_m - w.y0_m)
        if L < 1e-6:
            return
        if self.mode != "elev":
            self._prev_mode = self.mode
        if flip is None:  # por padrão, olha a parede de fora para dentro do prédio (a face voltada ao centro)
            ux, uy = (w.x1_m - w.x0_m) / L, (w.y1_m - w.y0_m) / L
            cx, cy = self._center()
            mx, my = (w.x0_m + w.x1_m) / 2, (w.y0_m + w.y1_m) / 2
            flip = ((cx - mx) * -uy + (cy - my) * ux) > 0
        self._elev = {"idx": idx, "ax": w.x0_m, "ay": w.y0_m, "ux": (w.x1_m - w.x0_m) / L, "uy": (w.y1_m - w.y0_m) / L,
                      "L": L, "flip": flip, "thk": w.thickness_m, "z0": w.z_base_m, "h": w.height_m}
        self.active_floor = self.project.floor_index(w.z_base_m + 0.01)
        self.mode = "elev"
        self.selection, self.multi, self.hover, self._chain = None, [], None, []
        if self.tool in ("wall", "rect", "room", "riser"):
            self.set_tool("pipe")
        self._update_banner()
        self.redraw()
        self.fit()
        self.selectionChanged.emit(None)
        self.message.emit("Vista da parede: desenhe tubos, aparelhos e peças direto na parede (clique = ponto; "
                          "a altura vem da posição vertical). Esc volta ao 3D.")

    def flip_wall_view(self):
        if self._elev:
            self.enter_wall_view(self._elev["idx"], not self._elev["flip"])

    def exit_wall_view(self):
        if self.mode != "elev":
            return
        self.mode = self._prev_mode
        sel = ("wall", self._elev["idx"])
        self._elev = None
        self.banner.hide()
        self.redraw()
        self.fit()
        self.select(sel if sel[1] < len(self.project.walls) else None)

    def _update_banner(self):
        e = self._elev
        if not e:
            self.banner.hide()
            return
        w = self.project.walls[e["idx"]]
        self.banner.setText(f"VISTA DA PAREDE {e['idx'] + 1} · {w.kind.upper()} · {e['L']:.2f} × {e['h']:.2f} m · "
                            f"{self.floor().name}  ·  afastamento {self.opts['elev_off']:.2f} m  ·  Esc volta")
        self.banner.adjustSize()
        self.banner.show()

    def _draw_elev(self):
        e = self._elev
        sc = self.scene()
        z0, h, L = e["z0"], e["h"], e["L"]
        P = lambda u, z: QPointF(u * SCALE, -z * SCALE)
        fine, major = QPen(QColor(COR["grid"]), 0), QPen(QColor(COR["line"]), 0)
        # grade: 10 cm dentro da parede, linhas fortes a cada metro
        g = 0.1
        nu = int(math.ceil((L + 2) / g))
        for k in range(nu + 1):
            u = -1 + k * g
            m = abs(u - round(u)) < 1e-6
            a, b = P(u, z0 - 0.5), P(u, z0 + h + 0.5)
            sc.addLine(a.x(), a.y(), b.x(), b.y(), major if m else fine).setZValue(-10)
        nv = int(math.ceil((h + 1) / g))
        for k in range(nv + 1):
            z = z0 - 0.5 + k * g
            m = abs((z - z0) - round(z - z0)) < 1e-6
            a, b = P(-1, z), P(L + 1, z)
            sc.addLine(a.x(), a.y(), b.x(), b.y(), major if m else fine).setZValue(-10)
        w = self.project.walls[e["idx"]]
        base = QColor(WALL_COLORS.get(w.kind, WALL_COLORS["interna"]))
        base.setAlpha(60)
        sc.addRect(QRectF(P(0, z0 + h), P(L, z0)), QPen(QColor(COR["cyan"]), 2), QBrush(base)).setZValue(-5)
        # encontros com outras paredes do pavimento (faixas hachuradas)
        for k, o in enumerate(self.project.walls):
            if k == e["idx"] or abs(o.z_base_m - z0) > 0.05:
                continue
            for x, y in ((o.x0_m, o.y0_m), (o.x1_m, o.y1_m)):
                d = abs((x - e["ax"]) * -e["uy"] + (y - e["ay"]) * e["ux"])
                u = self._elev_u(x, y)
                if d <= e["thk"] / 2 + o.thickness_m and -0.05 <= u <= L + 0.05:
                    r = QRectF(P(u - o.thickness_m / 2, z0 + h), P(u + o.thickness_m / 2, z0))
                    sc.addRect(r, QPen(QColor(COR["line"]), 0), QBrush(QColor(COR["muted"]), Qt.BDiagPattern)).setZValue(-4)
        # piso, teto e alturas típicas dos pontos de utilização
        for z, text in ((z0, "PISO"), (z0 + h, "TETO")):
            a, b = P(-1, z), P(L + 1, z)
            pen = QPen(QColor(COR["text"]), 2)
            pen.setCosmetic(True)
            sc.addLine(a.x(), a.y(), b.x(), b.y(), pen).setZValue(-3)
            self._label(P(L + 1, z), f"{text} {z:.2f}", COR["text"], 5, dx=6, dy=0, size=8)
        heights = {}
        for key, (label, _s, hh) in FIXTURE_INFO.items():
            heights.setdefault(round(hh, 2), []).append(label.split(" ")[0])
        heights[round(self.opts["pipe_h"], 2)] = ["Ramal"]
        for hh, names in sorted(heights.items()):
            if hh >= h:
                continue
            a, b = P(0, z0 + hh), P(L, z0 + hh)
            pen = QPen(QColor(COR["violet"]), 1, Qt.DashLine)
            pen.setCosmetic(True)
            sc.addLine(a.x(), a.y(), b.x(), b.y(), pen).setZValue(-2)
            self._label(P(0, z0 + hh), f"{hh:.2f}  {' / '.join(sorted(set(names)))[:28]}", COR["violet"], 5, dx=-6, dy=0,
                        size=7.5, right=True)
        # régua de comprimento
        for k in range(int(L) + 1):
            self._label(P(k, z0 - 0.5), f"{k} m", COR["muted"], 5, dy=12, center=True, size=7.5)

    def floor(self, i=None):
        return self.project.floors[self.active_floor if i is None else i]

    def fit(self):
        if self.project is None:
            return
        if self.mode == "elev":
            e = self._elev
            r = QRectF(QPointF(-1.6 * SCALE, -(e["z0"] + e["h"] + 0.7) * SCALE),
                       QPointF((e["L"] + 2.2) * SCALE, -(e["z0"] - 0.8) * SCALE))
            self.fitInView(r, Qt.KeepAspectRatio)
            self.redraw()
            return
        pts = [self._proj(n.x_m, n.y_m, n.elevation_m) for n in self.project.nodes.values()
               if self._visible_floor(self._node_floor(n))]
        for w in self.project.walls:
            if self._visible_floor(self.project.floor_index(w.z_base_m + 0.01)):
                pts += [self._proj(w.x0_m, w.y0_m, w.z_base_m), self._proj(w.x1_m, w.y1_m, w.z_base_m + w.height_m)]
        if not pts:
            pts = [self._proj(-5, -5, 0), self._proj(5, 5, 0)]
        xs, ys = [p.x() for p in pts], [p.y() for p in pts]
        self.fitInView(QRectF(min(xs) - 60, min(ys) - 60, max(xs) - min(xs) + 120, max(ys) - min(ys) + 120),
                       Qt.KeepAspectRatio)
        self.redraw()

    # ================================================================ projeção
    def _center(self):
        p = self.project
        xs = [n.x_m for n in p.nodes.values()] + [c for w in p.walls for c in (w.x0_m, w.x1_m)]
        ys = [n.y_m for n in p.nodes.values()] + [c for w in p.walls for c in (w.y0_m, w.y1_m)]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2) if xs else (0.0, 0.0)

    def _rot(self, dx, dy):
        for _ in range(self.rotation):
            dx, dy = -dy, dx
        return dx, dy

    def _elev_u(self, x, y):
        """Vista da parede: posição ao longo da parede (m, 0 = início visto da esquerda)."""
        e = self._elev
        u = (x - e["ax"]) * e["ux"] + (y - e["ay"]) * e["uy"]
        return e["L"] - u if e["flip"] else u

    def _elev_xy(self, u):
        e = self._elev
        if e["flip"]:
            u = e["L"] - u
        off = self.opts["elev_off"] * (-1 if e["flip"] else 1)
        return e["ax"] + u * e["ux"] - e["uy"] * off, e["ay"] + u * e["uy"] + e["ux"] * off

    def _proj(self, x, y, z):
        if self.mode == "elev":
            return QPointF(self._elev_u(x, y) * SCALE, -z * SCALE)
        dx, dy = self._rot(x - self._c[0], y - self._c[1])
        if self.mode == "plan":
            return QPointF(dx * SCALE, -dy * SCALE)
        return QPointF((dx - dy) * COS30 * SCALE, (dx + dy) * SIN30 * SCALE - z * SCALE)

    def _unproj(self, sp: QPointF, z):
        """Ponto da cena -> (x, y) no plano horizontal de cota z."""
        if self.mode == "elev":
            return self._elev_xy(sp.x() / SCALE)
        if self.mode == "plan":
            dx, dy = sp.x() / SCALE, -sp.y() / SCALE
        else:
            a = sp.x() / (COS30 * SCALE)
            b = (sp.y() + z * SCALE) / (SIN30 * SCALE)
            dx, dy = (a + b) / 2, (b - a) / 2
        for _ in range(self.rotation):
            dx, dy = dy, -dx
        return dx + self._c[0], dy + self._c[1]

    def _depth(self, x, y):
        dx, dy = self._rot(x - self._c[0], y - self._c[1])
        return dx + dy  # maior = mais perto do observador

    def _dz(self, fi, depth):
        """zValue pela profundidade (algoritmo do pintor): paredes, tubos e nós do mesmo pavimento
        competem no mesmo intervalo, então o que está na frente cobre o que está atrás em qualquer rotação."""
        return self._zbase(fi) + 100 + max(0.0, min(780.0, (depth + 400) * 0.9))

    def _in_elev(self, x, y, z):
        e = self._elev
        d = abs((x - e["ax"]) * -e["uy"] + (y - e["ay"]) * e["ux"])
        u = self._elev_u(x, y)
        return (d <= e["thk"] / 2 + 0.6 and -0.3 <= u <= e["L"] + 0.3
                and e["z0"] - 0.05 <= z <= e["z0"] + e["h"] + 0.05)

    def _visible_floor(self, fi):
        if self.mode in ("plan", "elev"):
            return fi == self.active_floor
        return not self.cut_above or fi <= self.active_floor

    def _node_floor(self, n: Node):
        return self.project.floor_index(n.elevation_m)

    def _pipe_floor(self, p: Pipe):
        return min(self._node_floor(self.project.nodes[p.start_node_id]),
                   self._node_floor(self.project.nodes[p.end_node_id]))

    def _pipe_visible(self, p: Pipe):
        if self.mode == "elev":
            a, b = self.project.nodes[p.start_node_id], self.project.nodes[p.end_node_id]
            return self._in_elev(a.x_m, a.y_m, a.elevation_m) and self._in_elev(b.x_m, b.y_m, b.elevation_m)
        if self.mode == "plan":
            a, b = (self._node_floor(self.project.nodes[k]) for k in (p.start_node_id, p.end_node_id))
            return min(a, b) <= self.active_floor <= max(a, b)
        return self._visible_floor(self._pipe_floor(p))

    def _node_visible(self, n: Node):
        if self.mode == "elev":
            return self._in_elev(n.x_m, n.y_m, n.elevation_m)
        if self.mode == "plan" and self._node_floor(n) != self.active_floor:
            return any(self._pipe_visible(p) for p in self.project.pipes.values()
                       if n.id in (p.start_node_id, p.end_node_id))
        return self._visible_floor(self._node_floor(n))

    # ================================================================ desenho
    def is_selected(self, kind, key):
        return self.selection == (kind, key) or (kind, key) in self.multi

    def redraw(self):
        sc = self.scene()
        sc.clear()
        self._temp = []
        self._placed = []  # retângulos (na tela) dos rótulos opcionais já colocados
        if self.project is None:
            return
        if self.mode == "elev":
            self._draw_elev()
            self._draw_pipes()
            self._draw_nodes()
            return
        self._draw_grid()
        self._draw_rooms()
        self._draw_walls()
        self._draw_pipes()
        self._draw_nodes()

    def _zbase(self, fi):
        return fi * 1000.0

    def _draw_grid(self):
        p, f = self.project, self.floor()
        xs = [n.x_m for n in p.nodes.values()] + [c for w in p.walls for c in (w.x0_m, w.x1_m)] or [0]
        ys = [n.y_m for n in p.nodes.values()] + [c for w in p.walls for c in (w.y0_m, w.y1_m)] or [0]
        x0, x1 = math.floor(min(xs)) - 4, math.ceil(max(xs)) + 4
        y0, y1 = math.floor(min(ys)) - 4, math.ceil(max(ys)) + 4
        # na isométrica a grade sobe para a altura em que a ferramenta desenha: o ponto clicado na grade
        # é exatamente onde o tubo/aparelho fica (com a grade no piso, um tubo a 2,20 m parecia deslocado)
        z = self._plane_z() if self.mode == "iso" else f.elevation_m
        fine, major = QPen(QColor(COR["grid"]), 0), QPen(QColor(COR["line"]), 0)
        zv = self._zbase(self.active_floor) - 1
        if abs(z - f.elevation_m) > 1e-6:
            zv = self._zbase(self.active_floor) + 95  # acima das lajes, abaixo das paredes
            fine = QPen(QColor(53, 208, 255, 45), 0)
            major = QPen(QColor(53, 208, 255, 110), 0)
            # rótulo no canto da grade que fica mais acima na tela (visível em qualquer rotação)
            top = min((self._proj(cx, cy, z) for cx in (x0, x1) for cy in (y0, y1)), key=lambda q: q.y())
            self._label(top, f"PLANO DE DESENHO  +{z - f.elevation_m:.2f} m do piso", COR["cyan"], zv + 1,
                        dy=-10, center=True, size=8)
        for x in range(x0, x1 + 1):
            a, b = self._proj(x, y0, z), self._proj(x, y1, z)
            self.scene().addLine(a.x(), a.y(), b.x(), b.y(), major if x % 5 == 0 else fine).setZValue(zv)
        for y in range(y0, y1 + 1):
            a, b = self._proj(x0, y, z), self._proj(x1, y, z)
            self.scene().addLine(a.x(), a.y(), b.x(), b.y(), major if y % 5 == 0 else fine).setZValue(zv)
        o = self._proj(0, 0, z)  # origem
        pen = QPen(QColor(COR["crit"]), 0)
        e = self._proj(1, 0, z); self.scene().addLine(o.x(), o.y(), e.x(), e.y(), pen).setZValue(zv)
        pen = QPen(QColor(COR["ok"]), 0)
        e = self._proj(0, 1, z); self.scene().addLine(o.x(), o.y(), e.x(), e.y(), pen).setZValue(zv)

    def _draw_rooms(self):
        for i, room in enumerate(self.project.rooms.values()):
            fi = self.project.floor_index(room.z_floor_m + 0.01)
            if not self._visible_floor(fi):
                continue
            tint = QColor(ROOM_TINTS[i % len(ROOM_TINTS)])
            tint.setAlpha(55 if fi == self.active_floor else 30)
            sel = self.is_selected("room", room.name)
            pen = QPen(QColor(COR["cyan"] if sel else COR["line"]), 2.5 if sel else 1)
            pen.setCosmetic(True)
            poly = QPolygonF([self._proj(x, y, room.z_floor_m) for x, y in room.polygon])
            self.scene().addPolygon(poly, pen, QBrush(tint)).setZValue(self._zbase(fi))
            if fi == self.active_floor:
                cx = sum(q[0] for q in room.polygon) / len(room.polygon)
                cy = sum(q[1] for q in room.polygon) / len(room.polygon)
                name = room.name.split(" – ")[0]
                self._label(self._proj(cx, cy, room.z_floor_m), name, COR["muted"], self._zbase(fi) + 1, center=True)

    def _wall_faces(self, w: Wall, s0=0.0, s1=1.0):
        """Faces visíveis do prisma da parede entre as frações s0 e s1 do comprimento:
        ([(polígono, tom)], [arestas]). As faces de topo só existem nas pontas verdadeiras da parede."""
        dx, dy = w.x1_m - w.x0_m, w.y1_m - w.y0_m
        L = math.hypot(dx, dy) or 1e-9
        ux, uy = dx / L, dy / L
        nx, ny = -uy * w.thickness_m / 2, ux * w.thickness_m / 2
        z0, z1 = w.z_base_m, w.z_base_m + w.height_m
        sx, sy = w.x0_m + dx * s0, w.y0_m + dy * s0
        ex, ey = w.x0_m + dx * s1, w.y0_m + dy * s1
        a1, a2 = (sx + nx, sy + ny), (sx - nx, sy - ny)
        b1, b2 = (ex + nx, ey + ny), (ex - nx, ey - ny)
        P = self._proj
        faces, edges = [], []
        sides = [((a1, b1), (-uy, ux), True), ((b2, a2), (uy, -ux), True)]
        if s1 >= 1.0:
            sides.append(((b1, b2), (ux, uy), False))
        if s0 <= 0.0:
            sides.append(((a2, a1), (-ux, -uy), False))
        # faces laterais: normal (no referencial girado) apontando para o observador (+1, +1)
        for (p, q), (mx, my), long_side in sides:
            rx, ry = self._rot(mx, my)
            if rx + ry > 1e-6:
                tone = 100 + int(28 * (1 - (rx + 1) / 2) + 10 * (ry < 0))
                faces.append((QPolygonF([P(p[0], p[1], z0), P(q[0], q[1], z0), P(q[0], q[1], z1), P(p[0], p[1], z1)]),
                              tone))
                edges.append((P(p[0], p[1], z0), P(q[0], q[1], z0)))
                if not long_side:
                    edges += [(P(p[0], p[1], z0), P(p[0], p[1], z1)), (P(q[0], q[1], z0), P(q[0], q[1], z1))]
        faces.append((QPolygonF([P(a1[0], a1[1], z1), P(b1[0], b1[1], z1), P(b2[0], b2[1], z1), P(a2[0], a2[1], z1)]), 0))
        edges += [(P(a1[0], a1[1], z1), P(b1[0], b1[1], z1)), (P(a2[0], a2[1], z1), P(b2[0], b2[1], z1))]
        if s0 <= 0.0:
            edges.append((P(a1[0], a1[1], z1), P(a2[0], a2[1], z1)))
        if s1 >= 1.0:
            edges.append((P(b1[0], b1[1], z1), P(b2[0], b2[1], z1)))
        return faces, edges

    def _draw_walls(self):
        walls = [(i, w) for i, w in enumerate(self.project.walls)]
        walls.sort(key=lambda iw: (iw[1].z_base_m, self._depth((iw[1].x0_m + iw[1].x1_m) / 2, (iw[1].y0_m + iw[1].y1_m) / 2)))
        self._wall_polys = []
        for rank, (i, w) in enumerate(walls):
            fi = self.project.floor_index(w.z_base_m + 0.01)
            if not self._visible_floor(fi):
                continue
            sel = self.is_selected("wall", i)
            hov = self.hover == ("wall", i) and not sel
            base = QColor(WALL_COLORS.get(w.kind, WALL_COLORS["interna"]))
            if sel:
                base = QColor(COR["cyan"])
            elif hov:
                base = base.lighter(122)
            alpha = int(255 * (self.wall_alpha if fi == self.active_floor or self.mode == "plan" else min(1.0, self.wall_alpha + 0.05)))
            if sel:
                alpha = max(alpha, 210)
            edge = QPen(QColor(COR["text"]) if sel else (QColor(COR["cyan"]) if hov else QColor(COR["bg"])),
                        2.2 if sel else (1.6 if hov else 0.8))
            edge.setCosmetic(True)
            zv = self._zbase(fi) + 100 + rank * 0.01
            if self.mode == "plan":
                dx, dy = w.x1_m - w.x0_m, w.y1_m - w.y0_m
                L = math.hypot(dx, dy) or 1e-9
                nx, ny = -dy / L * w.thickness_m / 2, dx / L * w.thickness_m / 2
                poly = QPolygonF([self._proj(w.x0_m + nx, w.y0_m + ny, 0), self._proj(w.x1_m + nx, w.y1_m + ny, 0),
                                  self._proj(w.x1_m - nx, w.y1_m - ny, 0), self._proj(w.x0_m - nx, w.y0_m - ny, 0)])
                brush = QBrush(base, Qt.SolidPattern if w.kind == "externa" else Qt.Dense4Pattern)
                self.scene().addPolygon(poly, edge, brush).setZValue(zv)
                self._wall_polys.append((zv, i, poly))
                continue
            # a parede é desenhada em pedaços curtos, cada um na sua profundidade: paredes compridas
            # e tubos atrás/na frente delas ficam na ordem certa em qualquer rotação
            L = math.hypot(w.x1_m - w.x0_m, w.y1_m - w.y0_m)
            n = max(1, math.ceil(L / 0.5))
            for k in range(n):
                s0, s1 = k / n, (k + 1) / n
                mx = w.x0_m + (w.x1_m - w.x0_m) * (s0 + s1) / 2
                my = w.y0_m + (w.y1_m - w.y0_m) * (s0 + s1) / 2
                zc = self._dz(fi, self._depth(mx, my))
                faces, edges = self._wall_faces(w, s0, s1)
                for poly, tone in faces:
                    c = base.lighter(115) if tone == 0 else base.darker(tone)
                    c.setAlpha(alpha)
                    seam = QPen(c, 0.8)  # contorno da cor da face: esconde as emendas entre os pedaços
                    seam.setCosmetic(True)
                    self.scene().addPolygon(poly, seam, QBrush(c)).setZValue(zc)
                    self._wall_polys.append((zc, i, poly))
                for a, b in edges:
                    self.scene().addLine(a.x(), a.y(), b.x(), b.y(), edge).setZValue(zc + 0.001)

    def _pipe_level(self, pid):
        if not self.result or pid not in self.result["pipes"]:
            return "NONE", None
        r = self.result["pipes"][pid]
        v = r["velocity_ms"]
        if r["flow_lps"] <= 0:
            return "IDLE", r
        return ("HIGH" if v > self.max_velocity else ("LOW" if v < 0.3 else "OK")), r

    def _draw_pipes(self):
        for pipe in self.project.pipes.values():
            if not self._pipe_visible(pipe):
                continue
            n0, n1 = self.project.nodes[pipe.start_node_id], self.project.nodes[pipe.end_node_id]
            a, b = self._proj(n0.x_m, n0.y_m, n0.elevation_m), self._proj(n1.x_m, n1.y_m, n1.elevation_m)
            level, r = self._pipe_level(pipe.id)
            fi = self._pipe_floor(pipe)
            width = 2.0 + pipe.diameter_mm / 14.0
            tip = f"{pipe.id}: {pipe.length_m:.2f} m · DN {pipe.diameter_mm:g} · {pipe.material}"
            if r:
                tip += f"\nQ = {r['flow_lps']:.3f} L/s · v = {r['velocity_ms']:.2f} m/s · hf = {r['head_loss_mca']:.3f} mca"
            pen = QPen(QColor(VEL_COLORS[level]), width)
            pen.setCosmetic(True)
            pen.setCapStyle(Qt.RoundCap)
            halo = QPen(QColor(53, 208, 255, 110), width + 8)
            halo.setCosmetic(True)
            halo.setCapStyle(Qt.RoundCap)
            # em pedaços, cada um na sua profundidade (some atrás das paredes, aparece na frente delas)
            depth_sorted = self.mode == "iso" and not self.xray
            n = max(1, math.ceil(math.hypot(n1.x_m - n0.x_m, n1.y_m - n0.y_m) / 0.5)) if depth_sorted else 1
            for k in range(n):
                t0, t1 = k / n, (k + 1) / n
                pa, pb = a + (b - a) * t0, a + (b - a) * t1
                if depth_sorted:
                    tm = (t0 + t1) / 2
                    zv = self._dz(fi, self._depth(n0.x_m + (n1.x_m - n0.x_m) * tm, n0.y_m + (n1.y_m - n0.y_m) * tm)) + 0.01
                else:
                    zv = self._zbase(fi) + 900
                if self.is_selected("pipe", pipe.id):
                    self.scene().addLine(pa.x(), pa.y(), pb.x(), pb.y(), halo).setZValue(zv - 0.005)
                line = self.scene().addLine(pa.x(), pa.y(), pb.x(), pb.y(), pen)
                line.setZValue(zv)
                line.setToolTip(tip)
            horizontal = abs(n0.elevation_m - n1.elevation_m) < 0.05
            if fi == self.active_floor and (horizontal or self.mode == "elev") and pipe.length_m >= 0.8:
                mid = (a + b) / 2
                if self._room_for(mid, 40, 0):
                    self._label(mid, f"Ø{pipe.diameter_mm:g}", COR["flow"], self._zbase(fi) + 990, center=True, size=8)

    def _draw_nodes(self):
        res_nodes = self.result["nodes"] if self.result else {}
        for nid, n in self.project.nodes.items():
            if not self._node_visible(n):
                continue
            fi = self._node_floor(n)
            zv = (self._dz(fi, self._depth(n.x_m, n.y_m)) + 0.02 if self.mode == "iso" and not self.xray
                  else self._zbase(fi) + 950)
            pos = self._proj(n.x_m, n.y_m, n.elevation_m)
            r = res_nodes.get(nid)
            sel = self.is_selected("node", nid)
            if sel:
                halo = self.scene().addEllipse(-16, -16, 32, 32, QPen(QColor(COR["cyan"]), 2), QBrush(QColor(53, 208, 255, 60)))
                halo.setFlag(QGraphicsItem.ItemIgnoresTransformations); halo.setPos(pos); halo.setZValue(zv - 1)
            tip = [f"{nid} · cota {n.elevation_m:.2f} m" + (f" · {n.room}" if n.room else "")]
            if nid == self.source_id:
                self._symbol(pos, lambda p, s: draw_source(p, s * 2), 15, zv + 3)
                self._label(pos + QPointF(0, 0), "RESERVATÓRIO", COR["cyan"], zv + 4, dy=-26, center=True, size=8)
            elif n.fixtures:
                bad = r is not None and r["required_mca"] > 0 and not r["ok"]
                high = r is not None and r["required_mca"] > 0 and r["pressure_mca"] > MAX_STATIC_PRESSURE_MCA
                color = COR["crit"] if bad else (COR["warn"] if high else COR["cyan"])
                key = n.fixtures[0].name
                self._symbol(pos, lambda p, s, k=key, c=color: draw_fixture(p, k, s * 2, c), 12, zv + 3)
                if len(n.fixtures) > 1:
                    self._label(pos, f"+{len(n.fixtures) - 1}", COR["muted"], zv + 4, dx=12, dy=-16, size=8)
                tip += [FIXTURE_INFO.get(f.name, (f.name,))[0] for f in n.fixtures]
                if r and fi == self.active_floor and self._room_for(pos, 74, 18):
                    self._label(pos, f"{r['pressure_mca']:.2f} mca", color, zv + 4, dy=18, center=True, size=8)
            else:
                dot = self.scene().addEllipse(-3.5, -3.5, 7, 7, QPen(QColor(COR["bg"]), 1), QBrush(QColor(COR["flow"])))
                dot.setFlag(QGraphicsItem.ItemIgnoresTransformations); dot.setPos(pos); dot.setZValue(zv + 1)
            for k, fit in enumerate(n.fittings):
                off = QPointF(16 + 18 * k, -14) if (n.fixtures or nid == self.source_id) else QPointF(18 * k, -14)
                self._symbol(pos, lambda p, s, f=fit, o=off: (p.translate(o), draw_fitting(p, f, s * 2)), 9, zv + 5,
                             extent=abs(off.x()) + 24)
                tip.append(FITTING_LABELS.get(fit, fit))
            if n.prv_setpoint_mca > 0:
                self._label(pos, f"VRP {n.prv_setpoint_mca:g} mca", COR["warn"], zv + 5, dy=-34, center=True, size=8)
            if r:
                tip.append(f"Pressão {r['pressure_mca']:.2f} mca (mín. {r['required_mca']:.2f})")
                if r.get("prv_reduction_mca"):
                    tip.append(f"VRP reduziu {r['prv_reduction_mca']:.2f} mca")
            hit = self.scene().addEllipse(-9, -9, 18, 18, QPen(Qt.NoPen), QBrush(Qt.transparent))
            hit.setFlag(QGraphicsItem.ItemIgnoresTransformations); hit.setPos(pos); hit.setZValue(zv + 6)
            hit.setToolTip("\n".join(tip))

    def _room_for(self, pos, w, dy, h=16):
        """Reserva espaço na tela para um rótulo opcional; False se já houver outro ali."""
        v = self.mapFromScene(pos)
        r = QRectF(v.x() - w / 2, v.y() + dy - h / 2, w, h)
        if any(r.intersects(o) for o in self._placed):
            return False
        self._placed.append(r)
        return True

    def _symbol(self, pos, fn, size, z, extent=None):
        it = Symbol(fn, size, extent)
        it.setPos(pos)
        it.setZValue(z)
        self.scene().addItem(it)
        return it

    def _label(self, pos, text, color, z, dx=0, dy=0, center=False, size=8.5, temp=False, right=False):
        def fn(p, s):
            f = QFont(MONO)
            f.setPointSizeF(size)
            f.setBold(True)
            p.setFont(f)
            w = p.fontMetrics().horizontalAdvance(text)
            x = dx - (w / 2 if center else (w if right else 0))
            path = QPainterPath()
            path.addText(x, dy + 4, f, text)
            p.setPen(QPen(QColor(COR["bg"]), 3))
            p.drawPath(path)
            p.fillPath(path, QColor(color))
        it = self._symbol(pos, fn, 80, z, extent=160)
        if temp:
            self._temp.append(it)
        return it

    # ================================================================ snap e seleção
    def _view_pt(self, x, y, z):
        return self.mapFromScene(self._proj(x, y, z))

    def _plane_z(self):
        f = self.floor()
        if self.tool in ("pipe", "riser", "source"):
            return f.elevation_m + self.opts["pipe_h"]
        if self.tool == "fixture":  # o aparelho fica onde foi clicado, já na altura típica dele
            return f.elevation_m + FIXTURE_INFO[self.opts["fixture"]][2]
        return f.elevation_m

    def _nearest_node(self, vpos, max_px=SNAP_PX):
        best, bd = None, max_px
        for nid, n in self.project.nodes.items():
            if not self._node_visible(n):
                continue
            q = self._view_pt(n.x_m, n.y_m, n.elevation_m)
            d = math.hypot(q.x() - vpos.x(), q.y() - vpos.y())
            if d < bd:
                best, bd = nid, d
        return best

    @staticmethod
    def _seg_dist(p, a, b):
        ax, ay, bx, by = a.x(), a.y(), b.x(), b.y()
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p.x() - ax) * vx + (p.y() - ay) * vy) / L2))
        return math.hypot(p.x() - ax - t * vx, p.y() - ay - t * vy), t

    def _nearest_pipe(self, vpos, max_px=8):
        best, bd, bt = None, max_px, 0
        for pipe in self.project.pipes.values():
            if not self._pipe_visible(pipe):
                continue
            n0, n1 = self.project.nodes[pipe.start_node_id], self.project.nodes[pipe.end_node_id]
            d, t = self._seg_dist(vpos, self._view_pt(n0.x_m, n0.y_m, n0.elevation_m),
                                  self._view_pt(n1.x_m, n1.y_m, n1.elevation_m))
            if d < bd and 0.02 < t < 0.98:
                best, bd, bt = pipe.id, d, t
        return best, bt

    def _nearest_wall(self, vpos, max_px=9):
        best, bd = None, max_px
        for i, w in enumerate(self.project.walls):
            if not self._visible_floor(self.project.floor_index(w.z_base_m + 0.01)):
                continue
            zs = (w.z_base_m,) if self.mode == "plan" else (w.z_base_m, w.z_base_m + w.height_m / 2, w.z_base_m + w.height_m)
            for z in zs:
                d, _ = self._seg_dist(vpos, self._view_pt(w.x0_m, w.y0_m, z), self._view_pt(w.x1_m, w.y1_m, z))
                if d < bd:
                    best, bd = i, d
        return best

    def _wall_vertex(self, vpos):
        z = self.floor().elevation_m
        best, bd = None, SNAP_PX
        for w in self.project.walls:
            if abs(w.z_base_m - z) > 0.05:
                continue
            for x, y in ((w.x0_m, w.y0_m), (w.x1_m, w.y1_m)):
                q = self._view_pt(x, y, z)
                d = math.hypot(q.x() - vpos.x(), q.y() - vpos.y())
                if d < bd:
                    best, bd = (x, y), d
        return best

    def _snap(self, vpos, modifiers=Qt.NoModifier):
        """O que está sob o cursor para a ferramenta atual: nó, tubo, vértice de parede ou ponto da grade."""
        z = self._plane_z()
        net_tool = self.tool in ("pipe", "riser", "fixture", "fitting", "source", "select")
        if net_tool:
            nid = self._nearest_node(vpos)
            if nid:
                n = self.project.nodes[nid]
                return {"kind": "node", "id": nid, "x": n.x_m, "y": n.y_m, "z": n.elevation_m}
            pid, t = self._nearest_pipe(vpos)
            if pid and self.tool != "select":
                p = self.project.pipes[pid]
                a, b = self.project.nodes[p.start_node_id], self.project.nodes[p.end_node_id]
                return {"kind": "pipe", "id": pid, "t": t, "x": a.x_m + t * (b.x_m - a.x_m),
                        "y": a.y_m + t * (b.y_m - a.y_m), "z": a.elevation_m + t * (b.elevation_m - a.elevation_m)}
        else:
            v = self._wall_vertex(vpos)
            if v:
                return {"kind": "vertex", "x": v[0], "y": v[1], "z": z}
        if self.mode == "elev":
            return self._snap_elev(vpos, modifiers)
        x, y = self._unproj(self.mapToScene(vpos), z)
        anchor = self._anchor_xy()
        if anchor and (self.ortho or modifiers & Qt.ShiftModifier):
            if abs(x - anchor[0]) >= abs(y - anchor[1]):
                y = anchor[1]
            else:
                x = anchor[0]
        if self.snap_grid:
            g = self.opts["grid"]
            if not (anchor and (self.ortho or modifiers & Qt.ShiftModifier)):
                x, y = round(x / g) * g, round(y / g) * g
            elif x == anchor[0]:
                y = anchor[1] + round((y - anchor[1]) / g) * g
            else:
                x = anchor[0] + round((x - anchor[0]) / g) * g
        return {"kind": "free", "x": round(x, 4), "y": round(y, 4), "z": z}

    def _snap_elev(self, vpos, modifiers):
        """Ponto livre na vista da parede: posição ao longo da parede e altura, na grade (u, z)."""
        sp = self.mapToScene(vpos)
        u, z = sp.x() / SCALE, -sp.y() / SCALE
        g = self.opts["grid"] if self.snap_grid else 0
        anchor = None
        if self._chain and isinstance(self._chain[-1], str):
            n = self.project.nodes[self._chain[-1]]
            anchor = (self._elev_u(n.x_m, n.y_m), n.elevation_m)
        if g:
            u = round(u / g) * g
            z = self._elev["z0"] + round((z - self._elev["z0"]) / g) * g
        if anchor and (self.ortho or modifiers & Qt.ShiftModifier):
            if abs(u - anchor[0]) >= abs(z - anchor[1]):
                z = anchor[1]
            else:
                u = anchor[0]
        x, y = self._elev_xy(u)
        return {"kind": "free", "x": round(x, 4), "y": round(y, 4), "z": round(z, 4)}

    def _anchor_xy(self):
        if not self._chain:
            return None
        last = self._chain[-1]
        if isinstance(last, str):
            n = self.project.nodes[last]
            return (n.x_m, n.y_m)
        return last

    def pick(self, vpos):
        nid = self._nearest_node(vpos)
        if nid:
            return ("node", nid)
        pid, _ = self._nearest_pipe(vpos, 7)
        if pid:
            return ("pipe", pid)
        wi = self._wall_at(vpos)
        if wi is not None:
            return ("wall", wi)
        z = self.floor().elevation_m
        x, y = self._unproj(self.mapToScene(vpos), z)
        for room in self.project.rooms.values():
            if abs(room.z_floor_m - z) < 0.05 and _inside(x, y, room.polygon):
                return ("room", room.name)
        return None

    def _wall_at(self, vpos):
        """Parede cuja face está sob o cursor (a da frente, se houver várias); senão a mais próxima da linha."""
        if self.mode == "elev":
            return None
        sp = self.mapToScene(vpos)
        for _, i, poly in sorted(self._wall_polys, key=lambda t: t[0], reverse=True):
            if poly.containsPoint(sp, Qt.OddEvenFill):
                return i
        return self._nearest_wall(vpos)

    def select(self, sel, multi=None):
        self.selection = sel
        self.multi = list(multi or [])
        self.redraw()
        self.selectionChanged.emit(sel)

    def selected_items(self):
        items = list(self.multi)
        if self.selection and self.selection not in items:
            items.insert(0, self.selection)
        return items

    def _band_select(self, a, b):
        """Janela de seleção. Da esquerda para a direita: só o que está inteiro dentro (janela);
        da direita para a esquerda: tudo o que a janela toca (cruzamento), como no CAD."""
        rect = QRectF(QPointF(a), QPointF(b)).normalized()
        crossing = b.x() < a.x()

        def V(x, y, z):
            return QPointF(self._view_pt(x, y, z))

        def take(points):
            inside = [rect.contains(q) for q in points]
            return any(inside) if crossing else all(inside)
        found = []
        for nid, n in self.project.nodes.items():
            if self._node_visible(n) and rect.contains(V(n.x_m, n.y_m, n.elevation_m)):
                found.append(("node", nid))
        for pid, p in self.project.pipes.items():
            if not self._pipe_visible(p):
                continue
            n0, n1 = self.project.nodes[p.start_node_id], self.project.nodes[p.end_node_id]
            pts = [V(n0.x_m + t * (n1.x_m - n0.x_m), n0.y_m + t * (n1.y_m - n0.y_m),
                     n0.elevation_m + t * (n1.elevation_m - n0.elevation_m)) for t in (0, .25, .5, .75, 1)]
            if take(pts):
                found.append(("pipe", pid))
        if self.mode == "elev":  # na vista da parede só a rede é selecionável
            return found
        for i, w in enumerate(self.project.walls):
            if not self._visible_floor(self.project.floor_index(w.z_base_m + 0.01)):
                continue
            zs = (w.z_base_m,) if self.mode == "plan" else (w.z_base_m, w.z_base_m + w.height_m)
            pts = [V(w.x0_m + t * (w.x1_m - w.x0_m), w.y0_m + t * (w.y1_m - w.y0_m), z) for z in zs for t in (0, .5, 1)]
            if take(pts):
                found.append(("wall", i))
        z = self.floor().elevation_m
        for name, r in self.project.rooms.items():
            if abs(r.z_floor_m - z) < 0.05 and take([V(x, y, z) for x, y in r.polygon]):
                found.append(("room", name))
        return found

    def selected_object(self):
        if not self.selection or not self.project:
            return None
        kind, key = self.selection
        try:
            return {"node": self.project.nodes, "pipe": self.project.pipes, "wall": self.project.walls,
                    "room": self.project.rooms}[kind][key]
        except (KeyError, IndexError):
            return None

    # ================================================================ edição
    def _begin(self):
        self.beforeChange.emit()

    def _done(self):
        self.redraw()
        self.changed.emit()

    def _new_node(self, x, y, z, **kw):
        nid = self.project.new_id("N", self.project.nodes)
        self.project.add_node(Node(nid, round(z, 3), x_m=round(x, 4), y_m=round(y, 4), **kw))
        return nid

    def _add_pipe(self, a, b):
        n0, n1 = self.project.nodes[a], self.project.nodes[b]
        L = math.dist((n0.x_m, n0.y_m, n0.elevation_m), (n1.x_m, n1.y_m, n1.elevation_m))
        pid = self.project.new_id("T", self.project.pipes)
        self.project.add_pipe(Pipe(pid, a, b, round(L, 3), self.opts["dn"], self.opts["material"]))
        return pid

    def split_pipe(self, pid, t):
        """Divide o trecho no ponto t (0..1) e devolve o nó criado (vira um tê na rede)."""
        p = self.project.pipes[pid]
        a, b = self.project.nodes[p.start_node_id], self.project.nodes[p.end_node_id]
        nid = self._new_node(a.x_m + t * (b.x_m - a.x_m), a.y_m + t * (b.y_m - a.y_m),
                             a.elevation_m + t * (b.elevation_m - a.elevation_m))
        new = self.project.new_id("T", self.project.pipes)
        self.project.add_pipe(Pipe(new, nid, p.end_node_id, round(p.length_m * (1 - t), 3), p.diameter_mm,
                                   p.material, p.equivalent_length_m / 2))
        p.end_node_id, p.length_m = nid, round(p.length_m * t, 3)
        p.equivalent_length_m /= 2
        return nid

    def _node_from(self, s, z_default=None):
        """Nó para o ponto do snap: o existente, um novo no meio do tubo ou um novo ponto livre."""
        if s["kind"] == "node":
            return s["id"]
        if s["kind"] == "pipe":
            return self.split_pipe(s["id"], s["t"])
        return self._new_node(s["x"], s["y"], s["z"] if z_default is None else z_default)

    def delete_selection(self):
        items = self.selected_items()
        if not items:
            return
        self._begin()
        for kind, key in items:
            if kind == "node" and key in self.project.nodes:
                self.project.remove_node(key)
                if key == self.source_id:
                    self.source_id = None
            elif kind == "pipe":
                self.project.pipes.pop(key, None)
            elif kind == "room":
                self.project.rooms.pop(key, None)
        # paredes do maior índice para o menor, para os índices das outras não mudarem
        for i in sorted((k for kind, k in items if kind == "wall"), reverse=True):
            if i < len(self.project.walls):
                del self.project.walls[i]
        if any(kind == "pipe" for kind, _ in items):
            self.project.remove_orphan_nodes(keep=self.source_id)
        self.message.emit(f"{len(items)} elemento(s) excluído(s). Ctrl+Z desfaz.")
        self.selection, self.multi = None, []
        self.selectionChanged.emit(None)
        self._done()

    def _click(self, vpos, modifiers):
        s = self._snap(vpos, modifiers)
        t = self.tool
        f = self.floor()
        if t == "select":
            sel = self.pick(vpos)
            if modifiers & (Qt.ControlModifier | Qt.ShiftModifier):  # soma ou retira da seleção
                items = self.selected_items()
                if sel in items:
                    items.remove(sel)
                elif sel:
                    items.append(sel)
                self.select(items[0] if len(items) == 1 else None, items if len(items) > 1 else [])
                return
            if sel is None:
                self._band = vpos  # clicou no vazio: começa a janela de seleção
                return
            self.select(sel)
            if sel[0] == "node":
                self._drag = {"id": sel[1], "started": False}
            return
        if t == "pipe":
            self._begin()
            nid = self._node_from(s)
            if self._chain and isinstance(self._chain[-1], str) and self._chain[-1] != nid:
                self._add_pipe(self._chain[-1], nid)
            self._chain = [nid]
            self._done()
        elif t == "riser":
            nxt = self.project.floors[self.active_floor + 1] if self.active_floor + 1 < len(self.project.floors) else None
            default = (nxt.elevation_m if nxt else f.elevation_m + f.height_m) + self.opts["pipe_h"]
            z, ok = self.ask_double("Prumada", f"Cota final do tubo vertical (m)\n(início em {s['z']:.2f} m)", default)
            if not ok or abs(z - s["z"]) < 0.01:
                return
            self._begin()
            a = self._node_from(s)
            na = self.project.nodes[a]
            b = next((k for k, n in self.project.nodes.items()
                      if abs(n.x_m - na.x_m) < 1e-3 and abs(n.y_m - na.y_m) < 1e-3 and abs(n.elevation_m - z) < 1e-3), None)
            b = b or self._new_node(na.x_m, na.y_m, z)
            self._add_pipe(a, b)
            self._done()
        elif t == "fixture":
            key = self.opts["fixture"]
            d = FIXTURE_DATABASE[key]
            self._begin()
            # na vista da parede vale a altura clicada; na planta/isométrica, a altura típica do aparelho
            typical = None if s["kind"] != "free" or self.mode == "elev" else f.elevation_m + FIXTURE_INFO[key][2]
            nid = self._node_from(s, typical)
            node = self.project.nodes[nid]
            node.fixtures.append(Fixture(key, d["weight"], d["min_pressure"]))
            if not node.room:
                node.room = self._room_at(node.x_m, node.y_m)
            self._done()
            self.select(("node", nid))
        elif t == "fitting":
            if s["kind"] == "free":
                self.message.emit("Peças vão sobre um nó ou um tubo: clique em cima da rede.")
                return
            key = self.opts["fitting"]
            setpoint = 0.0
            if key == "valvula_redutora_pressao":
                setpoint, ok = self.ask_double("Válvula redutora de pressão", "Pressão regulada a jusante (mca)", 15.0)
                if not ok:
                    return
            self._begin()
            nid = self._node_from(s)
            self.project.nodes[nid].fittings.append(key)
            if setpoint:
                self.project.nodes[nid].prv_setpoint_mca = setpoint
            self._done()
            self.select(("node", nid))
        elif t == "source":
            self._begin()
            self.source_id = self._node_from(s)
            self._done()
        elif t == "wall":
            pt = (s["x"], s["y"])
            if self._chain and math.dist(self._chain[-1], pt) > 1e-3:
                self._begin()
                self._add_wall(self._chain[-1], pt)
                self._done()
            self._chain = [pt]
        elif t == "rect":
            pt = (s["x"], s["y"])
            if not self._chain:
                self._chain = [pt]
                return
            (x0, y0), (x1, y1) = self._chain[0], pt
            self._chain = []
            if abs(x1 - x0) < 1e-3 or abs(y1 - y0) < 1e-3:
                return
            self._begin()
            for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
                self._add_wall(a, b)
            self._done()
        elif t == "room":
            pt = (s["x"], s["y"])
            if len(self._chain) >= 3 and math.dist(self._chain[0], pt) < 1e-3:
                self._finish_chain()
            else:
                self._chain.append(pt)

    def _add_wall(self, a, b):
        f = self.floor()
        kind = self.opts["wall_kind"]
        self.project.add_wall(Wall(a[0], a[1], b[0], b[1], f.elevation_m, f.height_m, self.opts[f"thk_{kind}"], kind))

    def _room_at(self, x, y):
        z = self.floor().elevation_m
        for room in self.project.rooms.values():
            if abs(room.z_floor_m - z) < 0.05 and _inside(x, y, room.polygon):
                return room.name
        return ""

    def _finish_chain(self):
        if self.tool == "room" and len(self._chain) >= 3:
            name, ok = self.ask_text("Cômodo", "Nome do cômodo", f"Cômodo {len(self.project.rooms) + 1}")
            if ok and name:
                f = self.floor()
                if name in self.project.rooms:
                    name = f"{name} – {f.name}"
                self._begin()
                self.project.add_room(Room(name, list(self._chain), f.elevation_m))
                for n in self.project.nodes.values():
                    if not n.room and self._node_floor(n) == self.active_floor and _inside(n.x_m, n.y_m, self._chain):
                        n.room = name
                self._done()
        self._chain = []
        self._clear_temp()

    # ================================================================ pré-visualização
    def _clear_temp(self):
        for it in self._temp:
            if it.scene():
                self.scene().removeItem(it)
        self._temp = []

    def _preview(self, s):
        self._clear_temp()
        sc = self.scene()
        cur = self._proj(s["x"], s["y"], s["z"])
        marker = {"node": "□", "pipe": "◇", "vertex": "□"}.get(s["kind"])
        size = 7
        pen = QPen(QColor(COR["cyan"]), 1.5)
        if marker:
            it = sc.addRect(-size, -size, 2 * size, 2 * size, pen) if marker == "□" else \
                sc.addPolygon(QPolygonF([QPointF(0, -size), QPointF(size, 0), QPointF(0, size), QPointF(-size, 0)]), pen)
        else:
            it = sc.addEllipse(-3, -3, 6, 6, QPen(QColor(COR["text"]), 1))
        it.setFlag(QGraphicsItem.ItemIgnoresTransformations); it.setPos(cur); it.setZValue(1e6)
        self._temp.append(it)
        floor_z = self.floor().elevation_m
        if self.mode == "iso" and s["z"] - floor_z > 0.01:
            # prumo do cursor até o piso: mostra onde o ponto está em planta e a que altura
            foot = self._proj(s["x"], s["y"], floor_z)
            guide = QPen(QColor(COR["violet"]), 1, Qt.DashLine)
            guide.setCosmetic(True)
            self._temp.append(sc.addLine(foot.x(), foot.y(), cur.x(), cur.y(), guide))
            cross = sc.addEllipse(-3, -3, 6, 6, QPen(QColor(COR["violet"]), 1.2))
            cross.setFlag(QGraphicsItem.ItemIgnoresTransformations); cross.setPos(foot)
            self._temp.append(cross)
            for t in self._temp[-2:]:
                t.setZValue(1e6)
            self._label(foot, f"h {s['z'] - floor_z:.2f} m", COR["violet"], 1e6, dx=8, dy=10, size=8, temp=True)
        anchor = None
        if self._chain:
            last = self._chain[-1]
            if isinstance(last, str):
                n = self.project.nodes[last]
                anchor = (n.x_m, n.y_m, n.elevation_m)
            else:
                anchor = (last[0], last[1], self.floor().elevation_m)
        if anchor is None:
            return
        a = self._proj(*anchor)
        dash = QPen(QColor(COR["cyan"]), 2, Qt.DashLine)
        dash.setCosmetic(True)
        if self.tool == "rect":
            (x0, y0), (x1, y1), z = anchor[:2], (s["x"], s["y"]), anchor[2]
            poly = QPolygonF([self._proj(x0, y0, z), self._proj(x1, y0, z), self._proj(x1, y1, z), self._proj(x0, y1, z)])
            self._temp.append(sc.addPolygon(poly, dash, QBrush(QColor(53, 208, 255, 30))))
            text = f"{abs(x1 - x0):.2f} × {abs(y1 - y0):.2f} m"
        else:
            if self.tool == "room":
                pts = [self._proj(x, y, anchor[2]) for x, y in self._chain] + [cur]
                self._temp.append(sc.addPolygon(QPolygonF(pts), dash, QBrush(QColor(53, 208, 255, 30))))
            else:
                self._temp.append(sc.addLine(a.x(), a.y(), cur.x(), cur.y(), dash))
            text = f"{math.dist(anchor, (s['x'], s['y'], s['z'] if self.tool == 'pipe' else anchor[2])):.2f} m"
        for it in self._temp[-1:]:
            it.setZValue(1e6)
        self._label(cur, text, COR["cyan"], 1e6, dx=12, dy=-12, size=9, temp=True)

    def _draw_band(self, a, b):
        self._clear_temp()
        crossing = b.x() < a.x()
        rect = QRectF(self.mapToScene(a), self.mapToScene(b)).normalized()
        pen = QPen(QColor(COR["ok"] if crossing else COR["cyan"]), 1.2, Qt.DashLine if crossing else Qt.SolidLine)
        pen.setCosmetic(True)
        fill = QColor(61, 220, 151, 35) if crossing else QColor(53, 208, 255, 35)
        it = self.scene().addRect(rect, pen, QBrush(fill))
        it.setZValue(1e6)
        self._temp.append(it)

    # ================================================================ eventos
    def wheelEvent(self, event):
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        pos = event.position().toPoint()
        before = self.mapToScene(pos)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.scale(factor, factor)
        # mantém sob o cursor o mesmo ponto do desenho
        after = self.mapToScene(pos)
        self.centerOn(self.mapToScene(self.viewport().rect().center()) + (before - after))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.redraw()  # os rótulos que cabem mudam com o zoom

    def mousePressEvent(self, e):
        if self.project is None:
            return
        if e.button() == Qt.MiddleButton:
            self._pan = e.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.RightButton:
            if self._chain:
                self._finish_chain()
            else:
                self.set_tool("select")
            return
        if e.button() == Qt.LeftButton:
            self.setFocus()
            self._click(e.position().toPoint(), e.modifiers())

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self.project is None:
            return
        vpos = e.position().toPoint()
        if self._drag and e.buttons() & Qt.LeftButton:
            n = self.project.nodes.get(self._drag["id"])
            if n is None:
                return
            if not self._drag["started"]:
                self._begin()
                self._drag["started"] = True
            if self.mode == "elev":  # na parede o nó anda ao longo dela e muda de altura
                s = self._snap_elev(vpos, e.modifiers())
                n.x_m, n.y_m, n.elevation_m = s["x"], s["y"], s["z"]
            else:
                x, y = self._unproj(self.mapToScene(vpos), n.elevation_m)
                g = self.opts["grid"] if self.snap_grid else 0
                n.x_m, n.y_m = (round(x / g) * g, round(y / g) * g) if g else (x, y)
            for p in self.project.pipes.values():
                if n.id in (p.start_node_id, p.end_node_id):
                    a, b = self.project.nodes[p.start_node_id], self.project.nodes[p.end_node_id]
                    p.length_m = round(math.dist((a.x_m, a.y_m, a.elevation_m), (b.x_m, b.y_m, b.elevation_m)), 3)
            self.redraw()
            return
        if self._band is not None and e.buttons() & Qt.LeftButton:
            self._draw_band(self._band, vpos)
            return
        s = self._snap(vpos, e.modifiers())
        self.cursorMoved.emit(s["x"], s["y"], s["z"])
        if self.tool != "select":
            self._preview(s)
        else:
            hov = self.pick(vpos)
            if hov != self.hover:
                self.hover = hov
                self.redraw()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self._pan = None
            self.setCursor(Qt.ArrowCursor if self.tool == "select" else Qt.CrossCursor)
            return
        if self._band is not None and e.button() == Qt.LeftButton:
            a, b = self._band, e.position().toPoint()
            self._band = None
            self._clear_temp()
            if (a - b).manhattanLength() > 4:
                items = self._band_select(a, b)
                self.select(items[0] if len(items) == 1 else None, items if len(items) > 1 else [])
                self.message.emit(f"{len(items)} elemento(s) selecionado(s). Del exclui; Ctrl+clique soma ou retira.")
            else:
                self.select(None)
            return
        if self._drag:
            if self._drag["started"]:
                self.changed.emit()
                self.selectionChanged.emit(self.selection)
            self._drag = None

    def mouseDoubleClickEvent(self, e):
        if self.tool in ("wall", "pipe", "room"):
            self._finish_chain()
        elif self.tool == "select" and self.mode != "elev":
            hit = self.pick(e.position().toPoint())
            if hit and hit[0] == "wall":  # duplo clique na parede: abre a vista 2D dela
                self.enter_wall_view(hit[1])

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            if self._chain:
                self._finish_chain() if self.tool == "room" else None
                self._chain = []
                self._clear_temp()
            elif self.mode == "elev" and self.tool == "select" and not self.selected_items():
                self.exit_wall_view()
            else:
                self.set_tool("select")
                self.select(None)
        elif k == Qt.Key_Delete:
            self.delete_selection()
        elif k in (Qt.Key_Return, Qt.Key_Enter):
            self._finish_chain()
        elif k == Qt.Key_F8:
            self.ortho = not self.ortho
            self.message.emit("Ortogonal " + ("ligado" if self.ortho else "desligado"))
        else:
            super().keyPressEvent(e)


def _inside(x, y, polygon):
    inside, j = False, len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


NetworkCanvas = ModelCanvas  # nome antigo
