import json
from dataclasses import dataclass, field, fields
from typing import Dict


@dataclass
class ImportConfig:
    """
    Padrão de importação de projetos (DXF/IFC) para água fria.

    Convenção DXF:
      - Tubulação: LINE/LWPOLYLINE/POLYLINE na layer `pipe_layer_prefix`;
        o diâmetro vem do sufixo (AF_TUBO_25 -> 25 mm; AF_TUBO -> `default_diameter_mm`).
      - Aparelhos: blocos (INSERT) na layer `fixture_layer`; o NOME DO BLOCO é a chave
        de `FIXTURE_DATABASE` (ex.: chuveiro_eletrico) ou um apelido em `fixture_aliases`.
      - Fonte de água (reservatório/ramal): qualquer bloco na layer `source_layer`.
      - Registros: blocos na layer `fitting_layer`, nome = registro_gaveta | registro_globo, sobre
        um ponto da rede (o registro conta no trecho que chega a esse ponto). Joelhos e tês
        são detectados automaticamente pela geometria.
      - Paredes: LINE/LWPOLYLINE na layer `wall_layer` (altura `wall_height_m`).
      - Cômodos: polilinha fechada na layer `AF_COMODO_<nome>` (ex.: AF_COMODO_Banheiro);
        os aparelhos dentro do contorno pertencem ao cômodo.
      - Cota (elevação): coordenada Z. Unidade: $INSUNITS do arquivo, ou `default_unit`.

    Convenção IFC: IfcPipeSegment = tubo; IfcSanitaryTerminal = aparelho (PredefinedType
    ou nome mapeado em `ifc_fixture_types`); fonte = qualquer elemento cujo Name/ObjectType
    contenha `ifc_source_keyword`.
    """
    pipe_layer_prefix: str = "AF_TUBO"
    fixture_layer: str = "AF_APARELHO"
    source_layer: str = "AF_FONTE"
    wall_layer: str = "AF_PAREDE"
    fitting_layer: str = "AF_CONEXAO"
    room_layer_prefix: str = "AF_COMODO"
    wall_height_m: float = 2.7
    default_unit: str = "m"            # usada se o DXF não declarar $INSUNITS
    default_diameter_mm: float = 20.0
    snap_tolerance_m: float = 0.05     # distância para unir pontas de tubos e aparelhos
    fixture_aliases: Dict[str, str] = field(default_factory=dict)
    ifc_source_keyword: str = "FONTE"
    ifc_fixture_types: Dict[str, str] = field(default_factory=lambda: {
        "SHOWER": "chuveiro_eletrico",
        "TOILETPAN": "bacia_sanitaria_cx_acoplada",
        "WCSEAT": "bacia_sanitaria_cx_acoplada",
        "WASHHANDBASIN": "lavatorio",
        "SINK": "pia_cozinha",
    })

    @classmethod
    def from_json(cls, path: str) -> "ImportConfig":
        """Carrega só os campos informados; o resto mantém o padrão."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Campos desconhecidos na configuração: {sorted(unknown)}")
        return cls(**data)
