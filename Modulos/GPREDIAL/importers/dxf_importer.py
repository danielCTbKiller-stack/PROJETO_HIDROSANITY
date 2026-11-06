import ezdxf
from ezdxf import units

from importers.config import ImportConfig
from importers.network_builder import ImportResult, NetworkBuilder

# fator de ezdxf.units.* -> metros
_TO_METERS = {
    units.MM: 0.001, units.CM: 0.01, units.M: 1.0, units.KM: 1000.0,
    units.IN: 0.0254, units.FT: 0.3048,
}
_UNIT_NAMES = {"mm": units.MM, "cm": units.CM, "m": units.M}


def _diameter_from_layer(layer: str, config: ImportConfig) -> float:
    suffix = layer[len(config.pipe_layer_prefix):].lstrip("_- ")
    try:
        return float(suffix.replace(",", ".")) if suffix else config.default_diameter_mm
    except ValueError:
        return config.default_diameter_mm


def import_dxf(path: str, config: ImportConfig = None) -> ImportResult:
    config = config or ImportConfig()
    doc = ezdxf.readfile(path)
    code = doc.header.get("$INSUNITS", 0)
    if code not in _TO_METERS:
        code = _UNIT_NAMES[config.default_unit]
    k = _TO_METERS[code]

    builder = NetworkBuilder(config)
    prefix = config.pipe_layer_prefix.upper()

    def pt(x, y, z=0.0):
        return (x * k, y * k, z * k)

    def polyline_points(e):
        if e.dxftype() == "LWPOLYLINE":
            pts = [pt(x, y, e.dxf.elevation) for x, y, *_ in e.get_points("xy")]
            closed = e.closed
        else:
            pts = [pt(*v.dxf.location) for v in e.vertices]
            closed = e.is_closed
        return pts, closed

    fittings = []
    wall_layer = config.wall_layer.upper()
    room_prefix = config.room_layer_prefix.upper()
    for e in doc.modelspace():
        layer = e.dxf.layer
        kind = e.dxftype()
        if layer.upper() == wall_layer:
            if kind == "LINE":
                builder.add_wall(pt(*e.dxf.start), pt(*e.dxf.end))
            elif kind in ("LWPOLYLINE", "POLYLINE"):
                pts, closed = polyline_points(e)
                if closed:
                    pts.append(pts[0])
                for a, b in zip(pts, pts[1:]):
                    builder.add_wall(a, b)
        elif layer.upper().startswith(room_prefix) and kind in ("LWPOLYLINE", "POLYLINE"):
            pts, _ = polyline_points(e)
            name = layer[len(config.room_layer_prefix):].lstrip("_- ").replace("_", " ") or "Cômodo"
            builder.add_room(name, [(p[0], p[1]) for p in pts], pts[0][2] if pts else 0.0)
        elif layer.upper().startswith(prefix):
            d = _diameter_from_layer(layer, config)
            if kind == "LINE":
                builder.add_segment(pt(*e.dxf.start), pt(*e.dxf.end), d)
            elif kind == "LWPOLYLINE":
                pts = [pt(x, y, e.dxf.elevation) for x, y, *_ in e.get_points("xy")]
                if e.closed:
                    pts.append(pts[0])
                for a, b in zip(pts, pts[1:]):
                    builder.add_segment(a, b, d)
            elif kind == "POLYLINE":
                pts = [pt(*v.dxf.location) for v in e.vertices]
                if e.is_closed:
                    pts.append(pts[0])
                for a, b in zip(pts, pts[1:]):
                    builder.add_segment(a, b, d)
        elif kind == "INSERT" and layer.upper() == config.fixture_layer.upper():
            builder.add_fixture(pt(*e.dxf.insert), e.dxf.name)
        elif kind == "INSERT" and layer.upper() == config.fitting_layer.upper():
            fittings.append((pt(*e.dxf.insert), e.dxf.name))
        elif kind == "INSERT" and layer.upper() == config.source_layer.upper():
            builder.add_source(pt(*e.dxf.insert))

    for point, name in fittings:  # depois dos tubos, para encontrar os nós
        builder.add_fitting(point, name)
    return builder.build()
