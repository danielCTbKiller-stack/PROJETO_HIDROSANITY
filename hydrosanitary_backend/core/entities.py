from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Fixture:
    """Representa um aparelho sanitário (ex: Chuveiro, Bacia, Lavatório)."""
    name: str
    weight: float           # Peso relativo (Método de Hunter)
    min_pressure_mca: float  # Pressão mínima exigida em mca


@dataclass
class Node:
    """Nó hidráulico (conexão, bifurcação ou ponto de consumo)."""
    id: str
    elevation_m: float      # Cota geométrica em relação à referência
    fixtures: List[Fixture] = field(default_factory=list)
    x_m: float = 0.0       # posição em planta (para exibição)
    y_m: float = 0.0
    room: str = ""         # cômodo onde o ponto está (vazio se desconhecido)
    fittings: List[str] = field(default_factory=list)  # conexões informadas no ponto (ex.: registro_gaveta)
    prv_setpoint_mca: float = 0.0  # > 0: válvula redutora de pressão no ponto, regulada para este valor a jusante


@dataclass
class Pipe:
    """Trecho de tubulação."""
    id: str
    start_node_id: str
    end_node_id: str
    length_m: float
    diameter_mm: float
    material: str = "PVC Soldável"
    equivalent_length_m: float = 0.0  # Comprimento equivalente de conexões


@dataclass
class Wall:
    """Parede (segmento em planta com altura), usada na visualização."""
    x0_m: float
    y0_m: float
    x1_m: float
    y1_m: float
    z_base_m: float = 0.0
    height_m: float = 2.7
    thickness_m: float = 0.15
    kind: str = "interna"  # "externa" | "interna"


@dataclass
class Room:
    """Cômodo: contorno em planta e cota do piso."""
    name: str
    polygon: List[Tuple[float, float]]
    z_floor_m: float = 0.0


@dataclass
class Floor:
    """Pavimento: cota do piso acabado e pé-direito (piso a piso)."""
    name: str
    elevation_m: float
    height_m: float = 2.88
