import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.entities import Fixture, Node, Pipe
from examples.make_sample_building import build_building
from gui.main_window import MainWindow
from services import project_io
from services.network_analyzer import NetworkAnalyzer
from services.project_manager import ProjectManager


class TestPrv(unittest.TestCase):

    def test_prv_limits_downstream_pressure(self):
        p = ProjectManager()
        p.add_node(Node("S", 30.0))
        p.add_node(Node("V", 0.0, prv_setpoint_mca=15.0))
        p.add_node(Node("A", 0.0, fixtures=[Fixture("lavatorio", 0.1, 0.5)]))
        p.add_pipe(Pipe("T1", "S", "V", 30.0, 32.0))
        p.add_pipe(Pipe("T2", "V", "A", 2.0, 20.0))
        r = NetworkAnalyzer(p).analyze("S", 0.0)
        self.assertAlmostEqual(r["nodes"]["V"]["pressure_mca"], 15.0)
        self.assertGreater(r["nodes"]["V"]["prv_reduction_mca"], 14.0)
        self.assertLess(r["nodes"]["A"]["pressure_mca"], 15.0)

    def test_informed_elbow_replaces_detected(self):
        p = ProjectManager()
        p.add_node(Node("S", 0.0, x_m=0, y_m=0))
        p.add_node(Node("B", 0.0, x_m=2, y_m=0, fittings=["curva_90"]))
        p.add_node(Node("A", 0.0, x_m=2, y_m=2, fixtures=[Fixture("lavatorio", 0.1, 0.5)]))
        p.add_pipe(Pipe("T1", "S", "B", 2.0, 20.0))
        p.add_pipe(Pipe("T2", "B", "A", 2.0, 20.0))
        r = NetworkAnalyzer(p).analyze("S", 10.0, auto_fittings=True)
        names = [n for n, _ in r["pipes"]["T2"]["fittings"]] + [n for n, _ in r["pipes"]["T1"]["fittings"]]
        self.assertIn("curva_90", names)
        self.assertNotIn("joelho_90", names)


class TestProjectIO(unittest.TestCase):

    def test_roundtrip(self):
        project, source = build_building(3)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "e.hsp")
            project_io.save(path, project, source, {"source_pressure_mca": 1.5})
            loaded, src, params = project_io.load(path)
        self.assertEqual(src, source)
        self.assertEqual(params["source_pressure_mca"], 1.5)
        self.assertEqual(len(loaded.nodes), len(project.nodes))
        self.assertEqual(len(loaded.walls), len(project.walls))
        self.assertEqual([f.name for f in loaded.floors], [f.name for f in project.floors])
        self.assertEqual(loaded.nodes["P0-RG"].prv_setpoint_mca, 15.0)


class TestEditor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.resize(1400, 900)
        self.w.show()
        self.c = self.w.canvas
        self.c.ask_double = lambda *_: (8.0, True)
        self.c.ask_text = lambda *_: ("Banheiro", True)
        self.c.set_mode("plan")
        self.app.processEvents()

    def click(self, x, y, z=None, mods=Qt.NoModifier):
        z = self.c._plane_z() if z is None else z
        self.c._click(self.c._view_pt(x, y, z), mods)

    def test_draw_network_and_calculate(self):
        c, w = self.c, self.w
        w.set_tool("source")
        self.click(0, 0)
        self.assertIsNotNone(c.source_id)
        w.set_tool("pipe")
        self.click(0, 0)
        self.click(4, 0)
        self.click(4, 3)
        c._finish_chain()
        self.assertEqual(len(c.project.pipes), 2)
        w.set_tool("fixture", "fixture", "chuveiro_eletrico")
        self.click(4, 3)
        w.set_tool("fitting", "fitting", "registro_gaveta")
        self.click(2, 0)  # no meio do tubo: divide em dois
        self.assertEqual(len(c.project.pipes), 3)
        self.assertTrue(any("registro_gaveta" in n.fittings for n in c.project.nodes.values()))
        c.source_id and c.project.nodes[c.source_id].__setattr__("elevation_m", 12.0)
        w.run_analysis()
        self.assertIsNotNone(w.last_result)
        self.assertEqual(w.pipe_table.rowCount(), 3)

    def test_walls_rect_undo_redo(self):
        w = self.w
        w.set_tool("rect", "wall_kind", "externa")
        self.click(0, 0)
        self.click(5, 4)
        self.assertEqual(len(self.c.project.walls), 4)
        self.assertTrue(all(x.kind == "externa" and abs(x.thickness_m - 0.20) < 1e-9 for x in self.c.project.walls))
        w.set_tool("wall", "wall_kind", "interna")
        self.click(2.5, 0)
        self.click(2.5, 4)
        self.c._finish_chain()
        self.assertEqual(len(self.c.project.walls), 5)
        w.undo()
        self.assertEqual(len(self.c.project.walls), 4)
        w.redo()
        self.assertEqual(len(self.c.project.walls), 5)

    def test_stack_and_replicate_floor(self):
        w = self.w
        w.set_tool("rect", "wall_kind", "externa")
        self.click(0, 0)
        self.click(5, 4)
        w.copy_floor_up(network=False, copies=2)
        self.assertEqual(len(self.c.project.floors), 3)
        zs = sorted({round(x.z_base_m, 2) for x in self.c.project.walls})
        self.assertEqual(zs, [0.0, 2.88, 5.76])

    def test_riser_between_floors(self):
        w = self.w
        w.add_floor()
        w._fill_floors(0)
        w.set_tool("riser")
        self.click(1, 1)
        verticals = [p for p in self.c.project.pipes.values()
                     if abs(self.c.project.nodes[p.start_node_id].elevation_m - self.c.project.nodes[p.end_node_id].elevation_m) > 1]
        self.assertEqual(len(verticals), 1)

    def test_properties_edit_pipe(self):
        w = self.w
        w.load_sample_building()
        w.show_page(0)
        self.c.select(("pipe", "T0-1"))
        before = len(w._undo)
        self.w.properties._apply(lambda: setattr(self.c.project.pipes["T0-1"], "diameter_mm", 32.0))
        self.assertEqual(self.c.project.pipes["T0-1"].diameter_mm, 32.0)
        self.assertEqual(len(w._undo), before + 1)
        w.undo()
        self.assertEqual(self.c.project.pipes["T0-1"].diameter_mm, 25.0)

    def test_sample_building_synoptic(self):
        w = self.w
        w.load_sample_building()
        m = w.synoptic.view.model
        self.assertEqual(len(m.columns), 1)
        self.assertEqual(len(m.branches), 8)
        self.assertTrue(m.branches[(0, m.columns[0])]["prv"])
        w.synoptic.view.grab()  # desenha sem erro


if __name__ == "__main__":
    unittest.main()


class TestSelectionAndZoom(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.resize(1400, 900)
        self.w.show()
        self.w.load_sample_building()
        self.w.show_page(0)
        self.c = self.w.canvas
        self.app.processEvents()

    def test_click_on_wall_face_selects_wall(self):
        c = self.c
        i = next(k for k, w in enumerate(c.project.walls) if w.kind == "externa" and w.z_base_m == 0 and w.y0_m == 9)
        w = c.project.walls[i]
        c._click(c._view_pt((w.x0_m + w.x1_m) / 2 + 2, w.y0_m, w.z_base_m + 1.0), Qt.NoModifier)
        self.assertEqual(c.selection[0], "wall")
        self.assertTrue(c.is_selected("wall", c.selection[1]))

    def test_band_select_and_delete_many(self):
        c = self.c
        vp = c.viewport().rect()
        items = c._band_select(vp.topLeft(), vp.bottomRight())
        walls = [k for kind, k in items if kind == "wall"]
        self.assertGreater(len(walls), 3)
        c.select(None, [("wall", k) for k in walls])
        n0 = len(c.project.walls)
        c.delete_selection()
        self.assertEqual(len(c.project.walls), n0 - len(walls))
        self.w.undo()
        self.assertEqual(len(c.project.walls), n0)

    def test_zoom_keeps_point_under_mouse(self):
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QWheelEvent
        c = self.c
        pos = QPoint(200, 150)
        before = c.mapToScene(pos)
        ev = QWheelEvent(QPointF(pos), QPointF(c.mapToGlobal(pos)), QPoint(0, 0), QPoint(0, 120),
                         Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        c.wheelEvent(ev)
        after = c.mapToScene(pos)
        self.assertLess((before - after).manhattanLength(), 3.0)


class TestExtendedPeriod(unittest.TestCase):

    def test_supply_cut_drains_reservoir(self):
        from services.extended_period import default_config, simulate
        p, s = build_building(4)
        cfg = default_config(p)
        full = simulate(p, s, cfg)
        self.assertEqual(full["summary"]["hours_empty"], 0)
        cfg.cut_start_h, cfg.cut_end_h = 6, 23
        cut = simulate(p, s, cfg)
        self.assertLess(cut["summary"]["min_level"], full["summary"]["min_level"])
        self.assertAlmostEqual(sum(cfg.pattern) / 24, 1.0, delta=0.05)

    def test_page_runs_and_applies_instant(self):
        app = QApplication.instance() or QApplication([])
        w = MainWindow()
        w.load_sample_building()
        w.show_page(3)
        w.extended.simulate()
        self.assertIsNotNone(w.extended.run)
        w.extended.set_cursor(10)
        w.extended._apply()
        self.assertIs(w.last_result, w.extended.run["steps"][10]["result"])


class TestWallViewAndRotation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = MainWindow()
        self.w.resize(1400, 900)
        self.w.show()
        self.w.load_sample_building()
        self.w.show_page(0)
        self.c = self.w.canvas
        self.idx = next(i for i, x in enumerate(self.c.project.walls)
                        if x.kind == "externa" and x.z_base_m == 0 and x.y0_m == 9 and x.y1_m == 9)

    def at(self, u, z):
        from PySide6.QtCore import QPointF
        from gui.canvas import SCALE
        return self.c.mapFromScene(QPointF(u * SCALE, -z * SCALE))

    def test_draw_pipe_on_wall(self):
        c, w = self.c, self.w
        c.select(("wall", self.idx))
        w.open_wall_view()
        self.assertEqual(c.mode, "elev")
        w.set_tool("pipe")
        n0 = len(c.project.pipes)
        c._click(self.at(4.5, 1.2), Qt.NoModifier)
        c._click(self.at(4.5, 0.4), Qt.NoModifier)
        c._finish_chain()
        self.assertEqual(len(c.project.pipes), n0 + 1)
        node = c.project.nodes[list(c.project.nodes)[-1]]
        self.assertAlmostEqual(node.y_m, 9.0, places=3)        # no plano da parede
        self.assertAlmostEqual(node.elevation_m, 0.4, places=3)  # altura clicada
        c.exit_wall_view()
        self.assertEqual(c.mode, "iso")
        self.assertEqual(c.selection, ("wall", self.idx))

    def test_flip_keeps_points_on_wall(self):
        c = self.c
        c.enter_wall_view(self.idx, flip=False)
        u_a = c._elev_u(2.0, 9.0)
        c.flip_wall_view()
        self.assertAlmostEqual(c._elev_u(2.0, 9.0), c._elev["L"] - u_a)

    def test_rotation_depth_order(self):
        """Em qualquer rotação, o pedaço de parede mais perto do observador fica por cima."""
        c = self.c
        for r in range(4):
            c.rotation = r
            c.redraw()
            near = max(((zv, i) for zv, i, _ in c._wall_polys), key=lambda t: t[0])
            w = c.project.walls[near[1]]
            # a parede da frente tem a maior profundidade média
            d = max(c._depth(x, y) for x, y in ((w.x0_m, w.y0_m), (w.x1_m, w.y1_m)))
            best = max(max(c._depth(x.x0_m, x.y0_m), c._depth(x.x1_m, x.y1_m))
                       for x in c.project.walls if x.z_base_m == 0)
            self.assertAlmostEqual(d, best, delta=0.6)


class TestIsoDrawingAllRotations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_point_lands_where_clicked(self):
        """Na isométrica, em qualquer rotação, o nó fica no ponto da grade (do plano de desenho) clicado."""
        w = MainWindow()
        w.resize(1400, 900)
        w.show()
        c = w.canvas
        c.set_mode("iso")
        for r in range(4):
            c.rotation = r
            c.redraw()
            for tool, opt, value in (("pipe", None, None), ("fixture", "fixture", "lavatorio")):
                w.set_tool(tool, opt, value)
                z = c._plane_z()
                x, y = 1.0 + r, 2.0
                s = c._snap(c._view_pt(x, y, z))
                self.assertAlmostEqual(s["x"], x, places=2)
                self.assertAlmostEqual(s["y"], y, places=2)
                self.assertAlmostEqual(s["z"], z, places=3)
        w.set_tool("fixture", "fixture", "lavatorio")
        c._click(c._view_pt(3.0, 1.0, c._plane_z()), Qt.NoModifier)
        n = c.project.nodes[c.selection[1]]
        self.assertEqual((round(n.x_m, 2), round(n.y_m, 2), round(n.elevation_m, 2)), (3.0, 1.0, 0.6))
