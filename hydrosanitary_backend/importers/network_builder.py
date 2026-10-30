import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.entities import Fixture, Node, Pipe, Room, Wall
from core.standards import EQUIVALENT_LENGTH_TABLE, FIXTURE_DATABASE
from importers.config import ImportConfig
from services.project_manager import ProjectManager

Point = Tuple[float, float, float]  # metros


@dataclass
class ImportResult:
    project: ProjectManager
    source_id: Optional[str]
    warnings: List[str] = field(default_factory=list)


def _inside(x: float, y: float, polygon) -> bool:
    """Ponto em polígono (ray casting)."""
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


class NetworkBuilder:
    """Converte geometria (segmentos, aparelhos, fonte), em metros, em nós e trechos do projeto."""

    def __init__(self, config: ImportConfig):
        self.config = config
        self.project = ProjectManager()
        self.warnings: List[str] = []
        self._points: List[Point] = []
        self._ids: List[str] = []
        self._pipe_count = 0
        self._source_id: Optional[str] = None

    def _node_for(self, p: Point, create: bool = True) -> Optional[str]:
        best, best_d = None, self.config.snap_tolerance_m
        for i, q in enumerate(self._points):
            d = math.dist(p, q)
            if d <= best_d:
                best, best_d = i, d
        if best is not None:
            return self._ids[best]
        if not create:
            return None
        nid = f"N{len(self._points) + 1}"
        self._points.append(p)
        self._ids.append(nid)
        self.project.add_node(Node(nid, elevation_m=p[2], x_m=p[0], y_m=p[1]))
        return nid

    def add_segment(self, p0: Point, p1: Point, diameter_mm: float) -> None:
        length = math.dist(p0, p1)
        if length <= 1e-9:
            return
        a, b = self._node_for(p0), self._node_for(p1)
        if a == b:
            self.warnings.append(f"Segmento menor que a tolerância de união ignorado em {p0}.")
            return
        self._pipe_count += 1
        self.project.add_pipe(Pipe(f"P{self._pipe_count}", a, b, length, diameter_mm))

    def add_fixture(self, p: Point, key: str) -> None:
        key = self.config.fixture_aliases.get(key, key).lower()
        data = FIXTURE_DATABASE.get(key)
        if data is None:
            self.warnings.append(f"Aparelho '{key}' desconhecido; ignorado.")
            return
        nid = self._node_for(p, create=False)
        if nid is None:
            self.warnings.append(f"Aparelho '{key}' em {p} não encontra ponta de tubo; ignorado.")
            return
        self.project.nodes[nid].fixtures.append(Fixture(key, data["weight"], data["min_pressure"]))

    def add_fitting(self, p: Point, key: str) -> None:
        key = key.lower()
        if key not in EQUIVALENT_LENGTH_TABLE:
            self.warnings.append(f"Conexão '{key}' desconhecida; ignorada.")
            return
        nid = self._node_for(p, create=False)
        if nid is None:
            self.warnings.append(f"Conexão '{key}' em {p} não encontra ponto da rede; ignorada.")
        else:
            self.project.nodes[nid].fittings.append(key)

    def add_wall(self, p0: Point, p1: Point) -> None:
        if math.dist(p0[:2], p1[:2]) > 1e-9:
            self.project.add_wall(Wall(p0[0], p0[1], p1[0], p1[1], min(p0[2], p1[2]), self.config.wall_height_m))

    def add_room(self, name: str, polygon, z_floor: float = 0.0) -> None:
        if len(polygon) >= 3:
            self.project.add_room(Room(name, list(polygon), z_floor))

    def add_source(self, p: Point) -> None:
        nid = self._node_for(p, create=False)
        if nid is None:
            self.warnings.append(f"Fonte em {p} não encontra ponta de tubo; ignorada.")
        elif self._source_id is None:
            self._source_id = nid
        else:
            self.warnings.append("Mais de uma fonte encontrada; usando a primeira.")

    def build(self) -> ImportResult:
        for node in self.project.nodes.values():
            if node.fixtures:
                for room in self.project.rooms.values():
                    if _inside(node.x_m, node.y_m, room.polygon):
                        node.room = room.name
                        break
        if self._source_id is None:
            self.warnings.append("Nenhuma fonte de água identificada.")
        return ImportResult(self.project, self._source_id, self.warnings)
