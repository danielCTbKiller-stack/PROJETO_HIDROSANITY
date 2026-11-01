import os
import tempfile
import unittest

from core.entities import Fixture, Node, Pipe
from engine.hydraulic_calculator import HydraulicCalculator
from examples.make_sample_house import build
from importers import import_project
from services.fittings import equivalent_length
from services.network_analyzer import NetworkAnalyzer
from services.project_manager import ProjectManager


def project(nodes, pipes):
    pm = ProjectManager()
    for n in nodes:
        pm.add_node(n)
    for p in pipes:
        pm.add_pipe(p)
    return pm


FX = [Fixture("chuveiro", 0.4, 1.0)]


class TestEquivalentLength(unittest.TestCase):

    def test_table_and_interpolation(self):
        self.assertEqual(equivalent_length("joelho_90", 25), 1.2)
        self.assertEqual(equivalent_length("joelho_90", 15), 1.1)     # abaixo da faixa
        self.assertEqual(equivalent_length("joelho_90", 200), 4.9)    # acima da faixa
        self.assertAlmostEqual(equivalent_length("joelho_90", 28.5), (1.2 + 2.0) / 2)


class TestAutoFittings(unittest.TestCase):

    def analyze(self, pm, source="R", **kw):
        return NetworkAnalyzer(pm).analyze(source, 10.0, auto_fittings=True, **kw)

    def test_elbow_90_on_riser(self):
        pm = project([Node("R", 3.0), Node("A", 3.0, x_m=5.0), Node("B", 1.0, FX, x_m=5.0)],
                     [Pipe("P1", "R", "A", 5.0, 25.0), Pipe("P2", "A", "B", 2.0, 25.0)])
        res = self.analyze(pm)
        self.assertEqual(res["pipes"]["P1"]["fittings"], [])
        self.assertEqual(res["pipes"]["P2"]["fittings"], [("joelho_90", 1.2)])
        flow = res["pipes"]["P2"]["flow_lps"]
        expected = HydraulicCalculator.calculate_head_loss(Pipe("x", "a", "b", 2.0, 25.0, equivalent_length_m=1.2), flow)
        self.assertAlmostEqual(res["pipes"]["P2"]["head_loss_mca"], expected)
        self.assertEqual(pm.pipes["P2"].equivalent_length_m, 0.0)  # não altera o projeto

    def test_straight_has_no_fitting_and_45_elbow(self):
        pm = project([Node("R", 0.0), Node("A", 0.0, x_m=2.0), Node("B", 0.0, x_m=4.0),
                      Node("C", 0.0, FX, x_m=6.0, y_m=2.0)],
                     [Pipe("P1", "R", "A", 2.0, 25.0), Pipe("P2", "A", "B", 2.0, 25.0),
                      Pipe("P3", "B", "C", 2.83, 25.0)])
        res = self.analyze(pm)
        self.assertEqual(res["pipes"]["P2"]["fittings"], [])
        self.assertEqual(res["pipes"]["P3"]["fittings"], [("joelho_45", 0.5)])

    def test_tee_through_and_lateral(self):
        pm = project([Node("R", 0.0), Node("T", 0.0, x_m=2.0), Node("A", 0.0, FX, x_m=4.0),
                      Node("B", 0.0, FX, x_m=2.0, y_m=2.0)],
                     [Pipe("P1", "R", "T", 2.0, 25.0), Pipe("P2", "T", "A", 2.0, 25.0),
                      Pipe("P3", "T", "B", 2.0, 25.0)])
        res = self.analyze(pm)
        self.assertEqual(res["pipes"]["P2"]["fittings"], [("te_passagem_direta", 0.8)])
        self.assertEqual(res["pipes"]["P3"]["fittings"], [("te_saida_lateral", 2.4)])

    def test_tee_fed_from_branch_is_bilateral(self):
        pm = project([Node("R", 0.0, x_m=0.0, y_m=2.0), Node("T", 0.0), Node("A", 0.0, FX, x_m=2.0),
                      Node("B", 0.0, FX, x_m=-2.0)],
                     [Pipe("P1", "R", "T", 2.0, 25.0), Pipe("P2", "T", "A", 2.0, 25.0),
                      Pipe("P3", "T", "B", 2.0, 25.0)])
        res = self.analyze(pm)
        self.assertEqual(res["pipes"]["P2"]["fittings"], [("te_saida_bilateral", 2.4)])
        self.assertEqual(res["pipes"]["P3"]["fittings"], [("te_saida_bilateral", 2.4)])

    def test_manual_fitting_and_off_by_default(self):
        a = Node("A", 0.0, x_m=2.0, fittings=["registro_globo"])
        pm = project([Node("R", 0.0), a, Node("B", 0.0, FX, x_m=4.0)],
                     [Pipe("P1", "R", "A", 2.0, 25.0), Pipe("P2", "A", "B", 2.0, 25.0)])
        res = self.analyze(pm)
        self.assertEqual(res["pipes"]["P1"]["fittings"], [("registro_globo", 15.0)])
        off = NetworkAnalyzer(pm).analyze("R", 10.0)
        self.assertEqual(off["pipes"]["P1"]["equivalent_length_m"], 0.0)
        self.assertLess(off["pipes"]["P1"]["head_loss_mca"], res["pipes"]["P1"]["head_loss_mca"])


class TestHouseFittings(unittest.TestCase):

    def test_house(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.dxf")
            build(path)
            imp = import_project(path)
        self.assertEqual(imp.warnings, [])
        self.assertEqual(sorted(f for n in imp.project.nodes.values() for f in n.fittings), ["registro_gaveta"] * 2)
        res = NetworkAnalyzer(imp.project).analyze(imp.source_id, 3.0, auto_size=True, auto_fittings=True)
        names = sorted(n for r in res["pipes"].values() for n, _ in r["fittings"])
        self.assertIn("te_saida_lateral", names)
        self.assertIn("joelho_90", names)
        self.assertEqual(names.count("registro_gaveta"), 2)
        self.assertEqual(res["alerts"], [])
        no_fit = NetworkAnalyzer(imp.project).analyze(imp.source_id, 3.0, auto_size=True)
        shower = next(n.id for n in imp.project.nodes.values() if n.fixtures and n.fixtures[0].name == "chuveiro_eletrico")
        self.assertLess(res["nodes"][shower]["pressure_mca"], no_fit["nodes"][shower]["pressure_mca"])


if __name__ == "__main__":
    unittest.main()
