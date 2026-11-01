import unittest

from core.entities import Pipe
from engine.hydraulic_calculator import HydraulicCalculator
from engine.validator import HydraulicValidator
from services.budget_calculator import BudgetCalculator
from services.project_manager import ProjectManager


class TestHydraulicEngine(unittest.TestCase):

    def test_probable_flow_calculation(self):
        flow = HydraulicCalculator.calculate_probable_flow(4.0)
        self.assertAlmostEqual(flow, 0.6)

    def test_velocity_calculation(self):
        velocity = HydraulicCalculator.calculate_velocity(0.2, 20.0)
        self.assertAlmostEqual(velocity, 0.6366, places=3)

    def test_head_loss_fair_whipple_hsiao(self):
        pipe = Pipe("P1", "N1", "N2", length_m=10.0, diameter_mm=25.0)
        hf = HydraulicCalculator.calculate_head_loss(pipe, 0.3)
        # J ≈ 0.0242 m/m para Q=0.3 L/s e D=25 mm
        self.assertAlmostEqual(hf, 0.242, places=3)

    def test_validator_high_velocity(self):
        result = HydraulicValidator.validate_pipe_limits("P1", velocity=3.5, max_allowable_velocity=3.0)
        self.assertEqual(result["level"], "ALERTA")

    def test_validator_ok(self):
        result = HydraulicValidator.validate_pipe_limits("P1", velocity=1.0)
        self.assertEqual(result["code"], "APPROVED")


class TestServices(unittest.TestCase):

    def test_project_summary(self):
        pm = ProjectManager()
        pm.add_pipe(Pipe("P1", "N1", "N2", 5.0, 20.0))
        self.assertEqual(pm.get_project_summary(), {"total_nodes": 0, "total_pipes": 1, "total_rooms": 0})

    def test_budget_uses_price_table_for_float_diameters(self):
        pipes = [Pipe("P1", "A", "B", 3.0, 20.0), Pipe("P2", "B", "C", 2.0, 20.0)]
        items = BudgetCalculator.calculate_materials_cost(pipes)
        self.assertEqual(items[0]["material"], "Tubo PVC Soldável 20mm")
        self.assertEqual(items[0]["total_price"], 60.0)



class TestNetworkAnalyzer(unittest.TestCase):

    def _project(self):
        from core.entities import Fixture, Node
        pm = ProjectManager()
        pm.add_node(Node("R", 10.0))
        pm.add_node(Node("T", 9.0))
        pm.add_node(Node("A", 8.0, [Fixture("chuveiro", 0.4, 1.0)]))
        pm.add_node(Node("B", 8.0, [Fixture("pia", 0.7, 0.5)]))
        pm.add_pipe(Pipe("P1", "R", "T", 5.0, 32.0))
        pm.add_pipe(Pipe("P2", "A", "T", 3.0, 20.0))  # sentido invertido de propósito
        pm.add_pipe(Pipe("P3", "T", "B", 3.0, 20.0))
        return pm

    def test_flow_accumulates_downstream(self):
        from services.network_analyzer import NetworkAnalyzer
        res = NetworkAnalyzer(self._project()).analyze("R", 5.0)
        self.assertAlmostEqual(res["pipes"]["P1"]["flow_lps"], 0.3 * (1.1 ** 0.5))
        self.assertAlmostEqual(res["pipes"]["P2"]["flow_lps"], 0.3 * (0.4 ** 0.5))

    def test_pressure_and_low_pressure_alert(self):
        from services.network_analyzer import NetworkAnalyzer
        res = NetworkAnalyzer(self._project()).analyze("R", -1.5)
        self.assertFalse(res["nodes"]["A"]["ok"])
        self.assertTrue(any(a["code"] == "LOW_PRESSURE" for a in res["alerts"]))
        self.assertTrue(NetworkAnalyzer(self._project()).analyze("R", 10.0)["nodes"]["A"]["ok"])

    def test_auto_size_picks_commercial_diameter(self):
        from services.network_analyzer import NetworkAnalyzer
        pm = self._project()
        res = NetworkAnalyzer(pm).analyze("R", 10.0, auto_size=True)
        for r in res["pipes"].values():
            self.assertLessEqual(r["velocity_ms"], 3.0)
            self.assertIn(r["diameter_mm"], [15, 20, 25, 32, 40, 50, 60, 75, 85, 110])

    def test_disconnected_and_loop_rejected(self):
        from core.entities import Node
        from services.network_analyzer import NetworkAnalyzer
        pm = self._project()
        pm.add_node(Node("X", 0.0))
        with self.assertRaises(ValueError):
            NetworkAnalyzer(pm).analyze("R", 5.0)
        pm.add_pipe(Pipe("P4", "X", "A", 1.0, 20.0))
        pm.add_pipe(Pipe("P5", "X", "B", 1.0, 20.0))
        with self.assertRaises(ValueError):
            NetworkAnalyzer(pm).analyze("R", 5.0)


class TestSizing(unittest.TestCase):

    def test_select_diameter(self):
        from engine.sizing import select_diameter
        self.assertEqual(select_diameter(0.1), 15.0)
        self.assertIsNone(select_diameter(1000.0))


if __name__ == "__main__":
    unittest.main()
