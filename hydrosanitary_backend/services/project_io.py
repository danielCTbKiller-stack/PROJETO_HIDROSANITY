"""Arquivo de projeto do Hidrossanitário (.hsp): JSON com rede, arquitetura e pavimentos."""
import json
from dataclasses import asdict
from typing import Optional, Tuple

from core.entities import Fixture, Floor, Node, Pipe, Room, Wall
from services.project_manager import ProjectManager

FORMAT_VERSION = 1


def to_dict(project: ProjectManager, source_id: Optional[str] = None, params: Optional[dict] = None) -> dict:
    return {
        "format": "hidrossanitario", "version": FORMAT_VERSION, "source_id": source_id, "params": params or {},
        "floors": [asdict(f) for f in project.floors],
        "nodes": [asdict(n) for n in project.nodes.values()],
        "pipes": [asdict(p) for p in project.pipes.values()],
        "walls": [asdict(w) for w in project.walls],
        "rooms": [asdict(r) for r in project.rooms.values()],
    }


def from_dict(data: dict) -> Tuple[ProjectManager, Optional[str], dict]:
    project = ProjectManager()
    for f in data.get("floors", []):
        project.floors.append(Floor(**f))
    for n in data.get("nodes", []):
        n = dict(n)
        n["fixtures"] = [Fixture(**f) for f in n.get("fixtures", [])]
        project.add_node(Node(**n))
    for p in data.get("pipes", []):
        project.add_pipe(Pipe(**p))
    for w in data.get("walls", []):
        project.add_wall(Wall(**w))
    for r in data.get("rooms", []):
        r = dict(r)
        r["polygon"] = [tuple(p) for p in r["polygon"]]
        project.add_room(Room(**r))
    project.sort_floors()
    return project, data.get("source_id"), data.get("params", {})


def save(path: str, project: ProjectManager, source_id: Optional[str] = None, params: Optional[dict] = None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(project, source_id, params), f, ensure_ascii=False, indent=1)


def load(path: str) -> Tuple[ProjectManager, Optional[str], dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != "hidrossanitario":
        raise ValueError("Arquivo não é um projeto do Hidrossanitário (.hsp).")
    return from_dict(data)
