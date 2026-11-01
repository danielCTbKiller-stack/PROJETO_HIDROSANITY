import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np

from importers.config import ImportConfig
from importers.network_builder import ImportResult, NetworkBuilder


def _axis_endpoints(settings, element):
    """Extremidades do eixo de um tubo: eixo principal (PCA) da malha e centro das pontas."""
    verts = np.asarray(ifcopenshell.geom.create_shape(settings, element).geometry.verts).reshape(-1, 3)
    centroid = verts.mean(axis=0)
    axis = np.linalg.svd(verts - centroid, full_matrices=False)[2][0]
    t = (verts - centroid) @ axis
    band = max((t.max() - t.min()) * 0.02, 1e-6)
    p0 = verts[t <= t.min() + band].mean(axis=0)
    p1 = verts[t >= t.max() - band].mean(axis=0)
    radial = np.linalg.norm((verts - centroid) - np.outer(t, axis), axis=1)
    return p0, p1, 2.0 * float(radial.max())


def _nominal_diameter_mm(element, scale):
    for props in ifcopenshell.util.element.get_psets(element).values():
        for name in ("NominalDiameter", "OuterDiameter", "InnerDiameter"):
            if isinstance(props.get(name), (int, float)):
                return props[name] * scale * 1000.0
    return None


def import_ifc(path: str, config: ImportConfig = None) -> ImportResult:
    config = config or ImportConfig()
    model = ifcopenshell.open(path)
    scale = ifcopenshell.util.unit.calculate_unit_scale(model)  # unidade do arquivo -> metros
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)

    builder = NetworkBuilder(config)
    keyword = config.ifc_source_keyword.upper()

    for pipe in model.by_type("IfcPipeSegment"):
        p0, p1, geo_d = _axis_endpoints(settings, pipe)
        d = _nominal_diameter_mm(pipe, scale) or geo_d * 1000.0 or config.default_diameter_mm
        builder.add_segment(tuple(p0), tuple(p1), round(d, 1))  # create_shape já devolve metros

    for term in model.by_type("IfcSanitaryTerminal"):
        loc = tuple(ifcopenshell.util.placement.get_local_placement(term.ObjectPlacement)[:3, 3] * scale)
        key = config.ifc_fixture_types.get(str(term.PredefinedType or "").upper()) or term.ObjectType or term.Name
        if key:
            builder.add_fixture(loc, key)
        else:
            builder.warnings.append(f"Aparelho IFC {term.GlobalId} sem tipo reconhecível; ignorado.")

    for el in model.by_type("IfcProduct"):
        label = f"{el.Name or ''} {el.ObjectType or ''}".upper()
        if keyword in label and el.ObjectPlacement and not el.is_a("IfcPipeSegment"):
            builder.add_source(tuple(ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)[:3, 3] * scale))

    return builder.build()
