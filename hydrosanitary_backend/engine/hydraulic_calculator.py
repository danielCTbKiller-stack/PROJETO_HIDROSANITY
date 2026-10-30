import math

from core.entities import Pipe


class HydraulicCalculator:
    """Motor de cálculo de engenharia para instalações prediais."""

    @staticmethod
    def calculate_probable_flow(total_fixture_weight: float) -> float:
        """
        Calcula a vazão provável (Q em L/s) pelo método dos pesos (NBR 5626).
        Q = 0.3 * sqrt(sum_weights)
        """
        if total_fixture_weight <= 0:
            return 0.0
        return 0.3 * math.sqrt(total_fixture_weight)

    @staticmethod
    def calculate_velocity(flow_lps: float, diameter_mm: float) -> float:
        """Calcula a velocidade de escoamento (m/s) em um tubo circular."""
        if diameter_mm <= 0:
            return 0.0
        flow_m3s = flow_lps / 1000.0
        radius_m = (diameter_mm / 1000.0) / 2.0
        area_m2 = math.pi * (radius_m ** 2)
        return flow_m3s / area_m2

    @staticmethod
    def calculate_head_loss(pipe: Pipe, flow_lps: float) -> float:
        """
        Calcula a perda de carga total (hf) em metros de coluna d'água (mca).
        Fórmula de Fair-Whipple-Hsiao para tubos lisos (PVC), água fria:
            J = 0.0008695 * Q^1.75 / D^4.75   (Q em m³/s, D em m, J em m/m)
        Considera comprimento real + comprimento equivalente de conexões.
        """
        if pipe.diameter_mm <= 0 or flow_lps <= 0:
            return 0.0

        flow_m3s = flow_lps / 1000.0
        diameter_m = pipe.diameter_mm / 1000.0
        total_length = pipe.length_m + pipe.equivalent_length_m
        j_unit = 0.0008695 * (flow_m3s ** 1.75) / (diameter_m ** 4.75)
        return j_unit * total_length
