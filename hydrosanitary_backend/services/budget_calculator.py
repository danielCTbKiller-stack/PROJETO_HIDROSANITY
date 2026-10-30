from typing import List

from core.entities import Pipe


class BudgetCalculator:
    """Calcula o orçamento de materiais com base nos tubos e diâmetros."""

    PRICE_TABLE = {
        "Tubo PVC Soldável 20mm": 12.00,
        "Tubo PVC Soldável 25mm": 18.50,
        "Tubo PVC Soldável 32mm": 25.00,
    }
    DEFAULT_UNIT_PRICE = 15.00

    @classmethod
    def calculate_materials_cost(cls, pipes: List[Pipe]) -> list:
        pipe_lengths = {}
        for pipe in pipes:
            # :g evita chaves como "20.0mm", que não casariam com a tabela de preços
            key = f"Tubo PVC Soldável {pipe.diameter_mm:g}mm"
            pipe_lengths[key] = pipe_lengths.get(key, 0.0) + pipe.length_m

        items = []
        for material, meters in pipe_lengths.items():
            unit_price = cls.PRICE_TABLE.get(material, cls.DEFAULT_UNIT_PRICE)
            items.append({
                "material": material,
                "quantity": round(meters, 2),
                "unit": "m",
                "unit_price": unit_price,
                "total_price": round(meters * unit_price, 2),
            })
        return items
