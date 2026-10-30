from typing import List, Optional

from core.entities import Floor, Node, Pipe, Room, Wall


class ProjectManager:
    """Gerencia o estado atual do projeto hidrossanitário em memória."""

    def __init__(self):
        self.nodes: dict[str, Node] = {}
        self.pipes: dict[str, Pipe] = {}
        self.walls: List[Wall] = []
        self.rooms: dict[str, Room] = {}
        self.floors: List[Floor] = []

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def add_pipe(self, pipe: Pipe):
        self.pipes[pipe.id] = pipe

    def add_wall(self, wall: Wall):
        self.walls.append(wall)

    def add_room(self, room: Room):
        self.rooms[room.name] = room

    def get_project_summary(self) -> dict:
        return {
            "total_nodes": len(self.nodes),
            "total_pipes": len(self.pipes),
            "total_rooms": len(self.rooms),
        }

    # ---- edição ----------------------------------------------------
    def new_id(self, prefix: str, existing) -> str:
        i = len(existing) + 1
        while f"{prefix}{i}" in existing:
            i += 1
        return f"{prefix}{i}"

    def remove_node(self, nid: str):
        """Remove o nó e os trechos ligados a ele."""
        for pid in [p.id for p in self.pipes.values() if nid in (p.start_node_id, p.end_node_id)]:
            del self.pipes[pid]
        self.nodes.pop(nid, None)

    def remove_orphan_nodes(self, keep: Optional[str] = None):
        """Remove nós sem trecho, sem aparelho e sem conexão (sobras de edição)."""
        used = {n for p in self.pipes.values() for n in (p.start_node_id, p.end_node_id)}
        for nid in [n.id for n in self.nodes.values()
                    if n.id not in used and n.id != keep and not n.fixtures and not n.fittings]:
            del self.nodes[nid]

    # ---- pavimentos ------------------------------------------------
    def ensure_floors(self):
        """Projetos importados não trazem pavimentos: cria um por cota de piso dos cômodos."""
        if self.floors:
            return
        levels = sorted({round(r.z_floor_m, 2) for r in self.rooms.values()} | {0.0})
        for i, z in enumerate(levels):
            nxt = levels[i + 1] if i + 1 < len(levels) else z + 2.88
            self.floors.append(Floor("Térreo" if i == 0 else f"{i}º pavimento", z, max(2.4, nxt - z)))

    def floor_index(self, z: float) -> int:
        """Pavimento que contém a cota z (o último cuja cota de piso é <= z)."""
        if not self.floors:
            return 0
        idx = 0
        for i, f in enumerate(sorted(self.floors, key=lambda f: f.elevation_m)):
            if z >= f.elevation_m - 0.05:
                idx = i
        return idx

    def sort_floors(self):
        self.floors.sort(key=lambda f: f.elevation_m)
