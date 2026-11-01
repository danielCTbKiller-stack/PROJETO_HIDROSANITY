import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow
from examples.make_sample_house import build
from tests.test_importers import make_dxf


class TestMainWindow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_load_and_calculate(self):
        w = MainWindow()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.dxf")
            make_dxf(path)
            w.load_file(path)
        self.assertEqual(w.source_label.text(), "N1")
        self.assertEqual(w.pipe_table.rowCount(), 0)
        w.auto_size.setChecked(True)
        w.run_analysis()
        self.assertEqual(w.pipe_table.rowCount(), 4)
        self.assertEqual(w.node_table.rowCount(), 5)
        self.assertEqual(w.budget_table.item(w.budget_table.rowCount() - 1, 0).text(), "TOTAL")

    def test_low_pressure_shown(self):
        w = MainWindow()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.dxf")
            make_dxf(path)
            w.load_file(path)
        w.pressure.setValue(-10.0)
        w.run_analysis()
        texts = [w.alerts.item(i).text() for i in range(w.alerts.count())]
        self.assertTrue(any("LOW_PRESSURE" in t or "pressão" in t for t in texts))

    def test_room_selection_changes_flows(self):
        from PySide6.QtCore import Qt
        w = MainWindow()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "casa.dxf")
            build(path)
            w.load_file(path)
        w.pressure.setValue(3.0)
        w.run_analysis()
        self.assertEqual(w.rooms_list.count(), 3)
        all_flows = [w.pipe_table.item(r, 1).text() for r in range(w.pipe_table.rowCount())]
        self.assertNotIn("0.000", all_flows)
        for i in range(w.rooms_list.count()):
            if w.rooms_list.item(i).text() != "Banheiro":
                w.rooms_list.item(i).setCheckState(Qt.Unchecked)  # recalcula sozinho
        some_flows = [w.pipe_table.item(r, 1).text() for r in range(w.pipe_table.rowCount())]
        self.assertEqual(some_flows.count("0.000"), 5)
        w.canvas.set_mode("plan"); w.canvas.rotate_view()  # não deve falhar

    def test_export_pdf_and_html(self):
        w = MainWindow()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "casa.dxf")
            build(path)
            w.load_file(path)
            w.pressure.setValue(3.0)
            w.run_analysis()
            pdf, html = os.path.join(tmp, "m.pdf"), os.path.join(tmp, "m.html")
            w.export_report(pdf)
            w.export_report(html)
            with open(pdf, "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")
            with open(html, encoding="utf-8") as f:
                self.assertIn("data:image/png;base64", f.read())


if __name__ == "__main__":
    unittest.main()
