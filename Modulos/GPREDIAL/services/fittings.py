import math
from typing import Dict, List, Sequence, Tuple

from core.entities import Node, Pipe
from core.standards import EQUIVALENT_LENGTH_DIAMETERS, EQUIVALENT_LENGTH_TABLE

STRAIGHT_DEG = 10.0   # desvio até aqui = trecho reto (sem conexão)
ELBOW_45_MAX_DEG = 67.5  # entre 10° e 67,5° joelho 45°; acima, joelho 90°


def equivalent_length(fitting: str, diameter_mm: float) -> float:
    """Comprimento equivalente (m) da conexão para o diâmetro, interpolando a tabela."""
    values = EQUIVALENT_LENGTH_TABLE[fitting]
    dns = EQUIVALENT_LENGTH_DIAMETERS
    if diameter_mm <= dns[0]:
        return values[0]
    if diameter_mm >= dns[-1]:
        return values[-1]
    for i in range(1, len(dns)):
        if diameter_mm <= dns[i]:
            t = (diameter_mm - dns[i - 1]) / (dns[i] - dns[i - 1])
            return values[i - 1] + t * (values[i] - values[i - 1])
    return values[-1]


def _vector(a: Node, b: Node) -> Tuple[float, float, float]:
    return (b.x_m - a.x_m, b.y_m - a.y_m, b.elevation_m - a.elevation_m)


def _deflection_deg(u, v) -> float:
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu == 0 or nv == 0:
        return 0.0
    cos = max(-1.0, min(1.0, sum(a * b for a, b in zip(u, v)) / (nu * nv)))
    return math.degrees(math.acos(cos))


def detect_fittings(
    nodes: Dict[str, Node],
    children: Dict[str, List[str]],
    parent_pipe: Dict[str, Pipe],
    parent_id: str,
    child_id: str,
) -> List[str]:
    """
    Conexões que o escoamento atravessa ao sair de `parent_id` rumo a `child_id`,
    deduzidas da geometria do nó: 2 trechos -> joelho (se houver desvio); 3 ou mais -> tê.
    A conexão é contada no trecho que SAI do nó. Na fonte não há conexão.
    """
    up = parent_pipe.get(parent_id)
    if up is None:
        return []
    grand = up.start_node_id if up.end_node_id == parent_id else up.end_node_id
    flow_in = _vector(nodes[grand], nodes[parent_id])
    deflections = {c: _deflection_deg(flow_in, _vector(nodes[parent_id], nodes[c])) for c in children[parent_id]}
    theta = deflections[child_id]

    if len(deflections) == 1:
        if theta < STRAIGHT_DEG:
            return []
        return ["joelho_45" if theta <= ELBOW_45_MAX_DEG else "joelho_90"]
    if theta < STRAIGHT_DEG:
        return ["te_passagem_direta"]
    if any(d < STRAIGHT_DEG for d in deflections.values()):
        return ["te_saida_lateral"]
    return ["te_saida_bilateral"]  # o escoamento chega pela derivação do tê e se divide


def fittings_equivalent_length(fittings: Sequence[str], diameter_mm: float) -> Tuple[float, List[Tuple[str, float]]]:
    detail = [(f, equivalent_length(f, diameter_mm)) for f in fittings]
    return sum(leq for _, leq in detail), detail
