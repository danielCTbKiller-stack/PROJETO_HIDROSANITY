import os
import tempfile
import unittest

import ezdxf
import ifcopenshell
import ifcopenshell.api

from importers import import_project
from importers.config import ImportConfig
from services.network_analyzer import NetworkAnalyzer


def make_dxf(path, insunits=4):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = insunits  # 4 = mm
    msp = doc.modelspace()
    for name in ("AF_TUBO_32", "AF_TUBO_20", "AF_TUBO"):
        doc.layers.add(name)
    # fonte em (0,0,3000) -> junção (5000,0,3000) -> desce até (5000,0,0) -> polilinha até o chuveiro
    msp.add_line((0, 0, 3000), (5000, 0, 3000), dxfattribs={"layer": "AF_TUBO_32"})
    msp.add_line((5000, 0, 3000), (5000, 0, 0), dxfattribs={"layer": "AF_TUBO_20"})
    msp.add_polyline3d([(5000, 0, 0), (5000, 2000, 0), (7000, 2000, 0)], dxfattribs={"layer": "AF_TUBO"})
    msp.add_blockref("FONTE", (0, 0, 3000), dxfattribs={"layer": "AF_FONTE"})
    msp.add_blockref("chuveiro_eletrico", (7000, 2000, 0), dxfattribs={"layer": "AF_APARELHO"})
    msp.add_blockref("bloco_estranho", (5000, 2000, 0), dxfattribs={"layer": "AF_APARELHO"})
    doc.saveas(path)


class TestDxfImport(unittest.TestCase):

    def test_import_and_analyze(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.dxf")
            make_dxf(path)
            res = import_project(path)
        p = res.project
        self.assertEqual(len(p.pipes), 4)
        self.assertEqual(len(p.nodes), 5)
        self.assertEqual(sorted(x.diameter_mm for x in p.pipes.values()), [20.0, 20.0, 20.0, 32.0])
        self.assertAlmostEqual(sum(x.length_m for x in p.pipes.values()), 5 + 3 + 2 + 2)
        self.assertEqual(sum(len(n.fixtures) for n in p.nodes.values()), 1)
        self.assertTrue(any("bloco_estranho" in w for w in res.warnings))
        out = NetworkAnalyzer(p).analyze(res.source_id, 5.0)
        self.assertTrue(all(n["ok"] for n in out["nodes"].values()))

    def test_unknown_extension(self):
        with self.assertRaises(NotImplementedError):
            import_project("x.dwg")
        with self.assertRaises(ValueError):
            import_project("x.rvt")

    def test_config_from_json(self):
        cfg = ImportConfig.from_json(os.path.join(os.path.dirname(__file__), "..", "config", "import_config.json"))
        self.assertEqual(cfg.fixture_aliases["VASO"], "bacia_sanitaria_cx_acoplada")


def make_ifc(path):
    f = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="t")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body",
                                target_view="MODEL_VIEW", parent=ctx)
    import numpy as np

    def pipe(name, start, end, diameter):
        el = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcPipeSegment", name=name)
        length = float(np.linalg.norm(np.array(end) - np.array(start)))
        rep = ifcopenshell.api.run("geometry.add_profile_representation", f, context=body,
                                   profile=f.createIfcCircleProfileDef("AREA", None, None, diameter / 2000.0), depth=length)
        ifcopenshell.api.run("geometry.assign_representation", f, product=el, representation=rep)
        direction = (np.array(end) - np.array(start)) / length
        z = np.array([0.0, 0.0, 1.0])
        x = np.cross(z, direction)
        x = x / np.linalg.norm(x) if np.linalg.norm(x) > 1e-9 else np.array([1.0, 0.0, 0.0])
        y = np.cross(direction, x)
        m = np.identity(4)
        m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = x, y, direction, start
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=el, matrix=m)
        pset = ifcopenshell.api.run("pset.add_pset", f, product=el, name="Pset_PipeSegmentTypeCommon")
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={"NominalDiameter": diameter / 1000.0})

    def point(cls, name, loc, **kw):
        el = ifcopenshell.api.run("root.create_entity", f, ifc_class=cls, name=name, **kw)
        m = np.identity(4)
        m[:3, 3] = loc
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=el, matrix=m)
        return el

    pipe("T1", (0, 0, 3), (5, 0, 3), 32)
    pipe("T2", (5, 0, 3), (5, 0, 0), 25)
    point("IfcTank", "FONTE", (0, 0, 3))
    point("IfcSanitaryTerminal", "chuveiro", (5, 0, 0), predefined_type="SHOWER")
    f.write(path)


class TestIfcImport(unittest.TestCase):

    def test_import_and_analyze(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.ifc")
            make_ifc(path)
            res = import_project(path)
        p = res.project
        self.assertEqual(len(p.pipes), 2, res.warnings)
        self.assertEqual(sorted(x.diameter_mm for x in p.pipes.values()), [25.0, 32.0])
        self.assertAlmostEqual(sum(x.length_m for x in p.pipes.values()), 8.0, places=2)
        self.assertEqual(sum(len(n.fixtures) for n in p.nodes.values()), 1, res.warnings)
        self.assertIsNotNone(res.source_id, res.warnings)
        out = NetworkAnalyzer(p).analyze(res.source_id, 5.0)
        self.assertTrue(all(n["ok"] for n in out["nodes"].values()))


if __name__ == "__main__":
    unittest.main()
