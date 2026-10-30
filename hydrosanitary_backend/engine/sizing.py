from typing import Optional, Sequence

from core.standards import COMMERCIAL_DIAMETERS
from engine.hydraulic_calculator import HydraulicCalculator


def select_diameter(
    flow_lps: float,
    max_velocity: float = 3.0,
    diameters: Sequence[float] = COMMERCIAL_DIAMETERS,
) -> Optional[float]:
    """Menor diâmetro comercial cuja velocidade respeita o limite; None se nenhum atender."""
    for d in sorted(diameters):
        if HydraulicCalculator.calculate_velocity(flow_lps, d) <= max_velocity:
            return float(d)
    return None
