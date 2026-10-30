import math
import os
import tempfile
import unittest

from examples.make_sample_house import build
from importers import import_project
from services.network_analyzer import NetworkAnalyzer

TOTAL_WEIGHT = 0.4 + 0.3 + 0.1 + 0.7 + 1.0 + 0.7


class TestHouseScenario(unittest.TestCase):

    def setUp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "casa.dxf")
            build(path)
            self.res = import_project(path)
        self.p = self.res.project

    def test_import_structure(self):
        self.assertEqual(self.res.warnings, [])
        self.assertEqual(len(self.p.walls), 7)
        self.assertEqual(sorted(self.p.rooms), ["Area de servico", "Banheiro", "Cozinha", "Quarto"])
        rooms = sorted(n.room for n in self.p.nodes.values() if n.fixtures)
        self.assertEqual(rooms, ["Area de servico"] * 2 + ["Banheiro"] * 3 + ["Cozinha"])

    def test_all_rooms_consuming_simultaneously(self):
        res = NetworkAnalyzer(self.p).analyze(self.res.source_id, 3.0, auto_size=True)
        self.assertEqual(res["alerts"], [])
        # vazão nos dois ramos principais que saem da fonte somam pesos, não vazões
        src_pipes = [p for p in self.p.pipes.values() if self.res.source_id in (p.start_node_id, p.end_node_id)]
        weights = {}
        for pipe in src_pipes:
            weights[pipe.id] = res["pipes"][pipe.id]["flow_lps"]
        # esquerda: banheiro 0.8 + pia 0.7; direita: máquina 1.0 + tanque 0.7
        self.assertAlmostEqual(min(weights.values()), 0.3 * math.sqrt(1.5), places=6)
        self.assertAlmostEqual(max(weights.values()), 0.3 * math.sqrt(1.7), places=6)
        self.assertLess(sum(weights.values()), 0.3 * math.sqrt(TOTAL_WEIGHT) * 2)
        self.assertTrue(all(n["ok"] for n in res["nodes"].values()))

    def test_active_rooms_subset(self):
        analyzer = NetworkAnalyzer(self.p)
        res = analyzer.analyze(self.res.source_id, 3.0, active_rooms=["Banheiro"])
        flows = [r["flow_lps"] for r in res["pipes"].values()]
        self.assertEqual(flows.count(0.0), 5)  # só o caminho do banheiro (8 trechos) tem vazão
        self.assertEqual(res["alerts"], [])
        shower = next(n for n in self.p.nodes.values() if any(f.name == "chuveiro_eletrico" for f in n.fixtures))
        self.assertGreaterEqual(res["nodes"][shower.id]["pressure_mca"], 1.0)

    def test_low_pressure_at_shower_only_when_source_weak(self):
        res = NetworkAnalyzer(self.p).analyze(self.res.source_id, -1.0)
        bad = [nid for nid, n in res["nodes"].items() if not n["ok"]]
        shower = next(n.id for n in self.p.nodes.values() if any(f.name == "chuveiro_eletrico" for f in n.fixtures))
        self.assertIn(shower, bad)


if __name__ == "__main__":
    unittest.main()


class TestMemorial(unittest.TestCase):

    def test_memorial_contents(self):
        from services.report_generator import generate_memorial
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "casa.dxf")
            build(path)
            res = import_project(path)
        out = NetworkAnalyzer(res.project).analyze(res.source_id, 3.0, auto_size=True)
        html = generate_memorial(res.project, out, source_id=res.source_id, source_pressure_mca=3.0,
                                 auto_size=True, project_name="Casa <exemplo>")
        out2 = NetworkAnalyzer(res.project).analyze(res.source_id, 3.0, auto_size=True, auto_fittings=True)
        html2 = generate_memorial(res.project, out2, source_id=res.source_id, source_pressure_mca=3.0)
        self.assertIn("1× joelho 90° (1.10 m cada)", html2)
        self.assertNotIn("Node(", html2)
        for text in ("Memorial de cálculo", "Casa &lt;exemplo&gt;", "chuveiro eletrico", "Banheiro",
                     "Fair-Whipple-Hsiao", "Nenhum alerta", "Total"):
            self.assertIn(text, html)
