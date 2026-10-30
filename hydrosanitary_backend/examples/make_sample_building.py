"""Edifício de exemplo, desenhado direto no modelo (sem DXF): 8 pavimentos-tipo com um apartamento
cada, prumada única saindo do reservatório superior e VRP nos ramais dos pavimentos mais baixos.

    python examples/make_sample_building.py edificio.hsp
"""
import sys

from core.entities import Fixture, Floor, Node, Pipe, Room, Wall
from core.standards import FIXTURE_DATABASE
from services.project_manager import ProjectManager

FLOOR_HEIGHT = 2.88
N_FLOORS = 8
RAMAL_Z = 2.20          # altura do ramal (forro) acima do piso
RISER = (0.5, 8.5)
PRV_FLOORS = 4          # pavimentos com VRP no ramal (os mais baixos)
PRV_SETPOINT = 15.0

ROOMS = {  # nome: (x0, y0, x1, y1)
    "Sala": (0, 0, 7, 5), "Quarto": (7, 0, 12, 5), "Banheiro": (0, 5, 3, 9),
    "Cozinha": (3, 5, 8, 9), "Área de serviço": (8, 5, 12, 9),
}
INTERNAL_WALLS = [((7, 0), (7, 5)), ((0, 5), (12, 5)), ((3, 5), (3, 9)), ((8, 5), (8, 9))]
FIXTURES = [  # aparelho, x do ponto, altura, conexão no ponto
    ("chuveiro_eletrico", 1.2, 2.10, "registro_pressao"),
    ("bacia_sanitaria_cx_acoplada", 1.9, 0.30, "registro_gaveta"),
    ("lavatorio", 2.6, 0.60, None),
    ("pia_cozinha", 5.5, 1.00, None),
    ("maquina_lavar", 9.5, 0.75, None),
    ("tanque", 11.0, 0.90, None),
]


def _fixture(key):
    d = FIXTURE_DATABASE[key]
    return Fixture(key, d["weight"], d["min_pressure"])


def _rect_walls(project, x0, y0, x1, y1, z, h, kind, t):
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        project.add_wall(Wall(a[0], a[1], b[0], b[1], z, h, t, kind))


def build_building(n_floors: int = N_FLOORS):
    p = ProjectManager()
    names = ["Térreo"] + [f"{i}º pavimento" for i in range(1, n_floors)]
    for i, name in enumerate(names):
        p.floors.append(Floor(name, round(i * FLOOR_HEIGHT, 2), FLOOR_HEIGHT))
    roof = round(n_floors * FLOOR_HEIGHT, 2)
    p.floors.append(Floor("Cobertura", roof, 3.0))

    # arquitetura
    for f in p.floors[:-1]:
        _rect_walls(p, 0, 0, 12, 9, f.elevation_m, f.height_m, "externa", 0.20)
        for (a, b) in INTERNAL_WALLS:
            p.add_wall(Wall(a[0], a[1], b[0], b[1], f.elevation_m, f.height_m, 0.12, "interna"))
        for name, (x0, y0, x1, y1) in ROOMS.items():
            room = f"{name} – {f.name}"
            p.add_room(Room(room, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], f.elevation_m))
    _rect_walls(p, 0, 0, 12, 9, roof, 1.1, "externa", 0.20)        # platibanda
    _rect_walls(p, 0, 6.5, 3, 9, roof, 2.8, "externa", 0.15)        # casa da caixa d'água

    # reservatório e prumada
    src = "RES"
    p.add_node(Node(src, roof + 5.0, x_m=RISER[0], y_m=RISER[1], fittings=["registro_gaveta"]))
    above = src
    for i in reversed(range(n_floors)):
        f = p.floors[i]
        z = f.elevation_m + RAMAL_Z
        rid = f"AF1-{i}"
        p.add_node(Node(rid, z, x_m=RISER[0], y_m=RISER[1]))
        p.add_pipe(Pipe(f"T-AF1-{i}", above, rid, abs(p.nodes[above].elevation_m - z), 40.0 if i < 4 else 32.0))
        above = rid

        # ramal do apartamento
        room_of = lambda x: f"{'Banheiro' if x < 3 else ('Cozinha' if x < 8 else 'Área de serviço')} – {f.name}"
        inlet = f"P{i}-RG"
        p.add_node(Node(inlet, z, x_m=1.0, y_m=RISER[1], fittings=["registro_gaveta"],
                        prv_setpoint_mca=PRV_SETPOINT if i < PRV_FLOORS else 0.0))
        if i < PRV_FLOORS:
            p.nodes[inlet].fittings.append("valvula_redutora_pressao")
        p.add_pipe(Pipe(f"T{i}-0", rid, inlet, 0.5, 25.0))
        prev = inlet
        for k, (key, x, h, fit) in enumerate(FIXTURES):
            tee = f"P{i}-{k}"
            p.add_node(Node(tee, z, x_m=x, y_m=RISER[1]))
            p.add_pipe(Pipe(f"T{i}-{k + 1}", prev, tee, abs(x - p.nodes[prev].x_m), 25.0))
            pt = f"P{i}-{k}A"
            p.add_node(Node(pt, f.elevation_m + h, x_m=x, y_m=RISER[1] + 0.3, fixtures=[_fixture(key)],
                            room=room_of(x), fittings=[fit] if fit else []))
            p.add_pipe(Pipe(f"T{i}-{k + 1}A", tee, pt, abs(z - f.elevation_m - h) + 0.3, 20.0))
            prev = tee
    return p, src


if __name__ == "__main__":
    from services import project_io
    project, source = build_building()
    project_io.save(sys.argv[1] if len(sys.argv) > 1 else "edificio.hsp", project, source,
                    {"source_pressure_mca": 0.0})
