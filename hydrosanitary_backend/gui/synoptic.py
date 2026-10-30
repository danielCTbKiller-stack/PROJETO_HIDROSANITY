"""Sinótico do prédio, no estilo do sinótico do GWATER: corte esquemático com o reservatório,
as prumadas (colunas de água fria) e, em cada pavimento, o ramal com VRP, registros e os
aparelhos agrupados por tipo, com a pressão no pior ponto. O escoamento é animado.

O diagrama é montado a partir do próprio modelo: os pavimentos vêm de `project.floors`, as
colunas são os tubos verticais (agrupados pela posição em planta) e cada aparelho é ligado à
coluna que o alimenta seguindo a rede até o reservatório.
"""
import math
from collections import defaultdict, deque

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
                               QToolTip, QVBoxLayout, QWidget)

from core.standards import FIXTURE_INFO, MAX_STATIC_PRESSURE_MCA
from gui.symbols import draw_fitting, draw_fixture, draw_source
from gui.theme import COR, DISPLAY, MONO

VERTICAL_MIN_M = 0.9  # tubo com desnível maior que isto e quase sem deslocamento em planta = prumada


def _font(family, px, bold=True):
    f = QFont(family)
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


class SynopticModel:
    """Topologia resumida do prédio para o diagrama."""

    def __init__(self, project, source_id, result):
        self.project, self.source_id, self.result = project, source_id, result
        self.floors = list(project.floors)
        nodes, pipes = project.nodes, project.pipes
        adj = defaultdict(list)
        for p in pipes.values():
            adj[p.start_node_id].append(p)
            adj[p.end_node_id].append(p)
        self.parent = {}
        if source_id in nodes:
            seen, q = {source_id}, deque([source_id])
            while q:
                cur = q.popleft()
                for p in adj[cur]:
                    o = p.end_node_id if p.start_node_id == cur else p.start_node_id
                    if o not in seen:
                        seen.add(o)
                        self.parent[o] = (cur, p)
                        q.append(o)

        def vertical(p):
            a, b = nodes[p.start_node_id], nodes[p.end_node_id]
            return abs(a.elevation_m - b.elevation_m) >= VERTICAL_MIN_M and math.hypot(a.x_m - b.x_m, a.y_m - b.y_m) < 0.3

        self.risers = defaultdict(list)  # coluna -> trechos verticais
        for p in pipes.values():
            if vertical(p):
                a = nodes[p.start_node_id]
                self.risers[(round(a.x_m, 1), round(a.y_m, 1))].append(p)
        self.columns = sorted(self.risers, key=lambda k: (k[0], k[1]))[:6]

        # aparelhos por (pavimento, coluna), agrupados pelo tipo
        self.branches = defaultdict(lambda: {"groups": defaultdict(list), "prv": None, "valves": [], "entry": None})
        for nid, n in nodes.items():
            if not n.fixtures:
                continue
            fi = project.floor_index(n.elevation_m)
            col, prv, valves, entry, cur = None, None, [], None, nid
            while cur in self.parent:
                up, pipe = self.parent[cur]
                if vertical(pipe):
                    a = nodes[pipe.start_node_id]
                    key = (round(a.x_m, 1), round(a.y_m, 1))
                    col = key if key in self.columns else None
                    break
                entry = pipe.id
                node = nodes[cur]
                if node.prv_setpoint_mca > 0 and prv is None:
                    prv = (cur, node.prv_setpoint_mca)
                valves += [f for f in node.fittings if f.startswith("registro") or f in ("valvula_retencao", "hidrometro")]
                cur = up
            b = self.branches[(fi, col)]
            for f in n.fixtures:
                b["groups"][f.name].append(nid)
            b["prv"] = b["prv"] or prv
            b["entry"] = b["entry"] or entry
            for v in valves:
                if v not in b["valves"]:
                    b["valves"].append(v)

    def node_result(self, nid):
        return (self.result or {}).get("nodes", {}).get(nid)

    def pipe_result(self, pid):
        return (self.result or {}).get("pipes", {}).get(pid)


class SynopticView(QWidget):
    floorClicked = Signal(int)
    hovered = Signal(str)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setMinimumSize(640, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.model = None
        self.phase = 0.0
        self._hits = []  # (QRectF, tipo, dados)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

    def set_data(self, project, source_id, result):
        self.model = SynopticModel(project, source_id, result) if project else None
        self.update()

    def _tick(self):
        if self.isVisible() and self.model and self.model.result:
            self.phase = (self.phase + 1) % 10000
            self.update()

    # ---------------------------------------------------------------- desenho
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(COR["bg"]))
        self._hits = []
        m = self.model
        if not m or not m.floors:
            p.setPen(QColor(COR["muted"]))
            p.setFont(_font(DISPLAY, 18))
            p.drawText(self.rect(), Qt.AlignCenter, "Abra ou desenhe um projeto para ver o sinótico do prédio")
            return
        W, H = self.width(), self.height()
        floors = m.floors
        n = len(floors)
        top_h = 120
        left, right = 132, W - 20
        band = max(30.0, min(110.0, (H - top_h - 46) / n))
        ground = top_h + band * n
        bld = QRectF(left, top_h, right - left, band * n)

        # terreno
        p.fillRect(QRectF(0, ground, W, H - ground), QColor("#071631"))
        p.setPen(QPen(QColor(COR["line"]), 2))
        p.drawLine(QPointF(0, ground), QPointF(W, ground))

        # fachada
        g = QLinearGradient(bld.topLeft(), bld.bottomLeft())
        g.setColorAt(0, QColor(COR["panel2"]))
        g.setColorAt(1, QColor(COR["panel"]))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(COR["line"]), 1.5))
        p.drawRoundedRect(bld, 6, 6)

        cols = m.columns or [None]
        col_x = {c: left + 34 + i * 30 for i, c in enumerate(cols)}
        branch_x0 = left + 34 + len(cols) * 30 + 12
        chip_w = 176 if W > 900 else 138
        fix_x0, fix_x1 = branch_x0 + 120, right - chip_w - 30

        floor_y = {}
        for i, f in enumerate(floors):
            y1 = ground - i * band
            y0 = y1 - band
            r = QRectF(left, y0, right - left, band)
            floor_y[i] = (y0, y1)
            self._hits.append((QRectF(0, y0, W, band), "floor", i))
            p.setPen(QPen(QColor(COR["grid"]), 1))
            p.drawLine(QPointF(left, y1), QPointF(right, y1))  # laje
            p.setPen(QColor(COR["text"]))
            p.setFont(_font(DISPLAY, min(15, band * 0.36)))
            p.drawText(QRectF(8, y0, left - 16, band * 0.6), Qt.AlignRight | Qt.AlignBottom, f.name.upper())
            p.setPen(QColor(COR["muted"]))
            p.setFont(_font(MONO, min(11, band * 0.26), False))
            p.drawText(QRectF(8, y0 + band * 0.6, left - 16, band * 0.4), Qt.AlignRight | Qt.AlignTop,
                       f"+{f.elevation_m:.2f} m")

        # reservatório
        src = m.project.nodes.get(m.source_id)
        res_y = top_h - 62
        if src is not None:
            res_r = QRectF(left + 6, res_y - 34, 110, 64)
            p.save()
            p.translate(res_r.center())
            draw_source(p, 110)
            p.restore()
            p.setPen(QColor(COR["cyan"]))
            p.setFont(_font(MONO, 10))
            p.drawText(QRectF(res_r.right() + 8, res_r.top(), 260, 18), Qt.AlignLeft, "RESERVATÓRIO SUPERIOR")
            p.setPen(QColor(COR["muted"]))
            p.setFont(_font(MONO, 10, False))
            p.drawText(QRectF(res_r.right() + 8, res_r.top() + 18, 300, 18), Qt.AlignLeft,
                       f"{m.source_id} · cota {src.elevation_m:.2f} m · NA")
            self._hits.append((res_r, "source", m.source_id))
            res_bottom = QPointF(res_r.center().x(), res_r.bottom() - 6)
        else:
            res_bottom = None

        # colunas (prumadas)
        branch_y = {}
        for (fi, col), b in m.branches.items():
            y0, y1 = floor_y.get(fi, (ground - band, ground))
            branch_y[(fi, col)] = y0 + band * 0.42
        lowest = defaultdict(lambda: None)
        for (fi, col) in branch_y:
            lowest[col] = max(lowest[col] or 0, branch_y[(fi, col)])
        barrilete_y = top_h - 14
        if res_bottom is not None:
            xs = [col_x[c] for c in cols]
            self._flow_line(p, [res_bottom, QPointF(res_bottom.x(), barrilete_y), QPointF(max(xs), barrilete_y)],
                            self._source_flow(m), 7)
        for c in cols:
            x = col_x[c]
            bottom = lowest[c] or ground - band * 0.5
            flow = self._riser_flow(m, c)
            self._flow_line(p, [QPointF(x, barrilete_y), QPointF(x, bottom)], flow, 7, down=True)
            p.setPen(QColor(COR["cyan"]))
            p.setFont(_font(MONO, 9))
            p.drawText(QRectF(x - 20, barrilete_y + 4, 40, 14), Qt.AlignCenter, f"AF-{cols.index(c) + 1}")

        # ramais
        for (fi, col), b in sorted(m.branches.items(), key=lambda kv: kv[0][0]):
            y = branch_y[(fi, col)]
            y0, y1 = floor_y.get(fi, (y - band / 2, y + band / 2))
            x = col_x.get(col, col_x[cols[0]])
            entry_r = m.pipe_result(b["entry"]) if b["entry"] else None
            q = entry_r["flow_lps"] if entry_r else 0.0
            self._flow_line(p, [QPointF(x, y), QPointF(fix_x1 + 14, y)], q if m.result else None, 5)
            p.setBrush(QColor(COR["flow"]))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(x, y), 4, 4)
            sx = x + 28
            s = min(26.0, band * 0.5)
            if b["prv"]:
                p.save(); p.translate(sx, y); draw_fitting(p, "valvula_redutora_pressao", s, COR["warn"]); p.restore()
                p.setPen(QColor(COR["warn"]))
                p.setFont(_font(MONO, 9))
                p.drawText(QRectF(sx - 30, y + s * 0.38, 60, 14), Qt.AlignCenter, f"VRP {b['prv'][1]:g}")
                self._hits.append((QRectF(sx - s / 2, y - s / 2, s, s), "prv", b["prv"][0]))
                sx += 34
            for v in b["valves"][:2]:
                p.save(); p.translate(sx, y); draw_fitting(p, v, s * 0.8); p.restore()
                sx += 26
            groups = sorted(b["groups"].items(), key=lambda kv: list(FIXTURE_INFO).index(kv[0]) if kv[0] in FIXTURE_INFO else 99)
            k = len(groups)
            fx0 = max(fix_x0, sx + 20)
            step = (fix_x1 - fx0) / max(1, k)
            worst_all, high_all, pmin, pmax = False, False, None, None
            for j, (key, nids) in enumerate(groups):
                gx = fx0 + step * (j + 0.3)
                gy = y + min(band * 0.26, 20)
                res = [m.node_result(nid) for nid in nids]
                res = [r for r in res if r]
                pw = min((r["pressure_mca"] for r in res), default=None)
                bad = any(not r["ok"] for r in res)
                high = any(r["pressure_mca"] > MAX_STATIC_PRESSURE_MCA for r in res if r["required_mca"] > 0)
                worst_all |= bad
                high_all |= high
                if pw is not None:
                    pmin = pw if pmin is None else min(pmin, pw)
                    pmax = max([pmax or pw] + [r["pressure_mca"] for r in res])
                color = COR["crit"] if bad else (COR["warn"] if high else COR["cyan"])
                p.setPen(QPen(QColor(COR["line"]), 2))
                p.drawLine(QPointF(gx, y), QPointF(gx, gy))
                p.save(); p.translate(gx, gy); draw_fixture(p, key, s * 1.1, color); p.restore()
                p.setFont(_font(MONO, max(8, min(11, band * 0.22))))
                if pw is not None:
                    p.setPen(QColor(color if bad or high else COR["ok"]))
                    p.drawText(QRectF(gx + s * 0.6, gy - 8, 80, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{pw:.1f}")
                if len(nids) > 1:
                    p.setPen(QColor(COR["muted"]))
                    p.drawText(QRectF(gx + s * 0.6, gy - 22, 40, 14), Qt.AlignLeft, f"×{len(nids)}")
                self._hits.append((QRectF(gx - s * 0.6, gy - s * 0.6, s * 1.2, s * 1.2), "fixture", (key, nids)))
            # cartão do pavimento
            chip = QRectF(right - chip_w - 10, y0 + band * 0.16, chip_w, min(44.0, band * 0.68))
            state = "crit" if worst_all else ("warn" if high_all else ("ok" if m.result else None))
            border = {"crit": "#8a2a38", "warn": "#8a5d17", "ok": "#1f7a5a"}.get(state, COR["line"])
            p.setBrush(QColor(COR["chip"]))
            p.setPen(QPen(QColor(border), 1))
            p.drawRoundedRect(chip, 8, 8)
            p.setFont(_font(MONO, max(8, min(10.5, band * 0.2))))
            p.setPen(QColor(COR[state] if state else COR["muted"]))
            if m.result:
                txt = f"Q {q:.2f} L/s"
                txt2 = f"P {pmin:.1f}–{pmax:.1f} mca" if pmin is not None else "sem consumo"
            else:
                txt, txt2 = f"{sum(len(v) for v in b['groups'].values())} aparelhos", "calcule (F5)"
            p.drawText(chip.adjusted(10, 2, -8, -chip.height() / 2), Qt.AlignLeft | Qt.AlignVCenter, txt)
            p.setPen(QColor(COR["text"] if m.result else COR["muted"]))
            p.drawText(chip.adjusted(10, chip.height() / 2 - 2, -8, -2), Qt.AlignLeft | Qt.AlignVCenter, txt2)

        if not m.branches:
            p.setPen(QColor(COR["muted"]))
            p.setFont(_font(DISPLAY, 15))
            p.drawText(bld, Qt.AlignCenter, "Nenhum aparelho no modelo ainda")

    def _source_flow(self, m):
        if not m.result:
            return None
        for nid, (up, pipe) in m.parent.items():
            if up == m.source_id:
                r = m.pipe_result(pipe.id)
                return r["flow_lps"] if r else 0.0
        return 0.0

    def _riser_flow(self, m, col):
        if not m.result or col is None:
            return None if not m.result else self._source_flow(m)
        return max((m.pipe_result(pp.id) or {"flow_lps": 0})["flow_lps"] for pp in m.risers[col])

    def _flow_line(self, p: QPainter, pts, flow, width, down=False):
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        base = QPen(QColor(COR["line"]), width + 3)
        base.setCapStyle(Qt.RoundCap)
        base.setJoinStyle(Qt.RoundJoin)
        p.setPen(base)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if flow is None or flow <= 0:
            pen = QPen(QColor("#3b5b85"), 2, Qt.CustomDashLine)
            pen.setDashPattern([1, 4])
        else:
            pen = QPen(QColor(COR["flow"]), 2.6, Qt.CustomDashLine)
            pen.setDashPattern([3.5, 3.5])
            pen.setDashOffset(-self.phase * min(1.2, 0.25 + flow) / 2.6 * 2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)

    # ---------------------------------------------------------------- interação
    def _hit(self, pos):
        best = None
        for rect, kind, data in self._hits:
            if rect.contains(pos):
                if kind != "floor":
                    return kind, data
                best = (kind, data)
        return best

    def mouseMoveEvent(self, e):
        hit = self._hit(e.position())
        text = self._describe(hit) if hit else ""
        if text:
            QToolTip.showText(e.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()
        self.hovered.emit(text)
        self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)

    def mousePressEvent(self, e):
        hit = self._hit(e.position())
        if hit and hit[0] == "floor":
            self.floorClicked.emit(hit[1])

    def _describe(self, hit):
        m = self.model
        kind, data = hit
        if kind == "floor":
            f = m.floors[data]
            fixtures = sum(len(n.fixtures) for n in m.project.nodes.values() if m.project.floor_index(n.elevation_m) == data)
            return f"{f.name}\nPiso +{f.elevation_m:.2f} m · pé-direito {f.height_m:.2f} m\n{fixtures} aparelho(s)\nClique para editar este pavimento"
        if kind == "source":
            return f"Reservatório ({data})"
        if kind == "prv":
            n = m.project.nodes[data]
            r = m.node_result(data)
            extra = f"\nreduziu {r['prv_reduction_mca']:.2f} mca" if r and r.get("prv_reduction_mca") else ""
            return f"VRP no nó {data}\nregulada para {n.prv_setpoint_mca:g} mca{extra}"
        if kind == "fixture":
            key, nids = data
            lines = [f"{FIXTURE_INFO.get(key, (key,))[0]} × {len(nids)}"]
            for nid in nids[:8]:
                r = m.node_result(nid)
                lines.append(f"  {nid}: " + (f"{r['pressure_mca']:.2f} mca (mín. {r['required_mca']:.2f})" if r else "—"))
            return "\n".join(lines)
        return ""


class Kpi(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("kpi")
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 8, 12, 8)
        col.setSpacing(0)
        k = QLabel(title.upper())
        k.setObjectName("kpiK")
        self.v = QLabel("—")
        self.v.setObjectName("kpiV")
        self.d = QLabel("")
        self.d.setObjectName("sub")
        for w in (k, self.v, self.d):
            col.addWidget(w)

    def set(self, value, detail="", state=""):
        self.v.setText(value)
        self.d.setText(detail)
        self.v.setProperty("estado", state)
        self.v.style().unpolish(self.v)
        self.v.style().polish(self.v)


class SynopticPage(QWidget):
    """Tela do sinótico: indicadores, diagrama do prédio e coluna lateral (detalhe, alertas, legenda)."""
    floorClicked = Signal(int)

    def __init__(self):
        super().__init__()
        col = QVBoxLayout(self)
        col.setContentsMargins(10, 10, 10, 10)
        col.setSpacing(10)
        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self.k_flow, self.k_pmin, self.k_pmax, self.k_alerts, self.k_floors = (
            Kpi("Vazão na saída do reservatório"), Kpi("Pressão mínima"), Kpi("Pressão máxima"), Kpi("Alertas"),
            Kpi("Pavimentos"))
        for k in (self.k_flow, self.k_pmin, self.k_pmax, self.k_alerts, self.k_floors):
            kpis.addWidget(k)
        col.addLayout(kpis)
        main = QHBoxLayout()
        main.setSpacing(10)
        frame = QFrame()
        frame.setObjectName("card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(6, 6, 6, 6)
        self.view = SynopticView()
        self.view.floorClicked.connect(self.floorClicked)
        fl.addWidget(self.view)
        main.addWidget(frame, 1)

        side = QVBoxLayout()
        side.setSpacing(10)
        det = QFrame(); det.setObjectName("card")
        dl = QVBoxLayout(det)
        t = QLabel("DETALHE"); t.setObjectName("h3"); dl.addWidget(t)
        self.detail = QLabel("Passe o mouse sobre o diagrama.")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("sub")
        self.detail.setMinimumHeight(90)
        self.detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        dl.addWidget(self.detail)
        self.view.hovered.connect(lambda t: self.detail.setText(t) if t else None)
        side.addWidget(det)
        al = QFrame(); al.setObjectName("card")
        all_ = QVBoxLayout(al)
        t = QLabel("ALERTAS"); t.setObjectName("h3"); all_.addWidget(t)
        self.alerts = QListWidget()
        all_.addWidget(self.alerts)
        side.addWidget(al, 1)
        lg = QFrame(); lg.setObjectName("card")
        grid = QGridLayout(lg)
        t = QLabel("LEGENDA"); t.setObjectName("h3"); grid.addWidget(t, 0, 0, 1, 2)
        for i, (c, text) in enumerate(((COR["flow"], "escoamento (animado)"), ("#3b5b85", "sem consumo / não calculado"),
                                       (COR["ok"], "pressão adequada"), (COR["warn"], f"acima de {MAX_STATIC_PRESSURE_MCA:g} mca: use VRP"),
                                       (COR["crit"], "abaixo da mínima do aparelho"))):
            sw = QLabel(); sw.setFixedSize(18, 4); sw.setStyleSheet(f"background:{c};border-radius:2px;")
            grid.addWidget(sw, i + 1, 0)
            lb = QLabel(text); lb.setObjectName("sub"); grid.addWidget(lb, i + 1, 1)
        side.addWidget(lg)
        holder = QWidget()
        holder.setLayout(side)
        holder.setFixedWidth(330)
        main.addWidget(holder)
        col.addLayout(main, 1)

    def set_data(self, project, source_id, result, warnings=()):
        self.view.set_data(project, source_id, result)
        self.alerts.clear()
        floors = len(project.floors) if project else 0
        self.k_floors.set(str(floors), f"{len(project.nodes) if project else 0} nós · {len(project.pipes) if project else 0} trechos")
        if not result:
            for k in (self.k_flow, self.k_pmin, self.k_pmax):
                k.set("—", "calcule (F5)")
            self.k_alerts.set("—")
            for w in warnings:
                self.alerts.addItem(QListWidgetItem(w))
            return
        m = self.view.model
        q = self.view._source_flow(m) or 0.0
        self.k_flow.set(f"{q:.2f} L/s", "vazão provável (NBR 5626)", "ok")
        fx = [(nid, r) for nid, r in result["nodes"].items() if r["required_mca"] > 0]
        if fx:
            nmin, rmin = min(fx, key=lambda t: t[1]["pressure_mca"])
            nmax, rmax = max(fx, key=lambda t: t[1]["pressure_mca"])
            self.k_pmin.set(f"{rmin['pressure_mca']:.1f} mca", f"no ponto {nmin}", "ok" if rmin["ok"] else "crit")
            high = rmax["pressure_mca"] > MAX_STATIC_PRESSURE_MCA
            self.k_pmax.set(f"{rmax['pressure_mca']:.1f} mca", f"no ponto {nmax}", "warn" if high else "ok")
        n = len(result["alerts"])
        self.k_alerts.set(str(n), "verificações da rede", "crit" if n else "ok")
        for w in warnings:
            self.alerts.addItem(QListWidgetItem(w))
        for a in result["alerts"]:
            self.alerts.addItem(QListWidgetItem(f"[{a['level']}] {a['message']}"))
        for nid, r in fx:
            if r["pressure_mca"] > MAX_STATIC_PRESSURE_MCA:
                self.alerts.addItem(QListWidgetItem(f"[ATENÇÃO] {nid}: {r['pressure_mca']:.1f} mca acima de "
                                                    f"{MAX_STATIC_PRESSURE_MCA:g} mca (NBR 5626) – instale VRP"))
        if not self.alerts.count():
            self.alerts.addItem(QListWidgetItem("Nenhum alerta. Rede atende às verificações."))
