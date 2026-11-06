"""Modelo de dados comum do GFLOOD: as seis entidades que descrevem um cenário de ponta a ponta.

Os motores (LISFLOOD-FP no macro, ANUGA no micro) só recebem dados por estas entidades, nunca direto das camadas do
QGIS. Tudo em SI, num único CRS projetado (SIRGAS 2000 / UTM), tempo em segundos desde o início do evento. Cada
entidade vira JSON (`Cenario.salvar` / `Cenario.abrir`), para o cenário ser reaberto e reprocessado sem refazer o
preparo.
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

Ponto = Tuple[float, float]


@dataclass
class Terreno:
    """MDT (GeoTIFF) e as resoluções de cada motor; edificações viram obstáculos (sobem no MDT do micro)."""
    mdt: str                                  # GeoTIFF
    resolucao_macro: float = 10.0             # m, grade do LISFLOOD-FP
    resolucao_micro: float = 2.0              # m, aresta máxima típica do ANUGA
    edificacoes: Optional[str] = None         # GeoPackage de polígonos (opcional)
    altura_edificacoes: float = 10.0          # m acrescentados ao MDT dentro das edificações


@dataclass
class Rugosidade:
    """Manning: um raster pronto, ou polígonos de uso do solo com n por classe, ou um valor único."""
    raster: Optional[str] = None
    poligonos: Optional[str] = None           # GeoPackage
    campo_classe: str = "classe"
    n_por_classe: dict = field(default_factory=dict)
    n_padrao: float = 0.035


@dataclass
class Hidrograma:
    """Entrada pontual de vazão: posição e a série (tempo s, vazão m³/s)."""
    nome: str
    ponto: Ponto
    serie: List[Tuple[float, float]]


@dataclass
class Forcante:
    """O que move a água: hidrogramas de entrada, chuva distribuída (série mm/h) e nível de jusante."""
    hidrogramas: List[Hidrograma] = field(default_factory=list)
    chuva: List[Tuple[float, float]] = field(default_factory=list)   # (tempo s, intensidade mm/h), uniforme na área
    nivel_jusante: Optional[float] = None     # m, cota fixa na borda de saída
    borda_jusante: str = "E"                  # N, S, E ou W (lado da grade do macro por onde a água sai)


@dataclass
class AreaInteresse:
    """Polígono do micro, faixa de transição e tamanho máximo de triângulo."""
    poligono: List[Ponto] = field(default_factory=list)
    faixa_transicao: float = 50.0             # m
    area_max_triangulo: float = 25.0          # m²


@dataclass
class Resultado:
    """Rasters gerados, por motor: instantes e máximos (profundidade, nível, velocidade, h×v, chegada)."""
    motor: str
    pasta: str
    instantes: List[Tuple[float, str]] = field(default_factory=list)   # (tempo s, GeoTIFF de profundidade)
    maximos: dict = field(default_factory=dict)                       # {"profundidade": tif, ...}
    log: str = ""


@dataclass
class Cenario:
    nome: str
    crs: str                                  # ex.: "EPSG:31983"
    terreno: Terreno
    rugosidade: Rugosidade = field(default_factory=Rugosidade)
    forcante: Forcante = field(default_factory=Forcante)
    area_interesse: Optional[AreaInteresse] = None
    tr_anos: Optional[float] = None
    duracao: float = 3600.0                   # s
    passo_saida: float = 600.0                # s
    motores: List[str] = field(default_factory=lambda: ["macro"])   # "macro", "micro" ou os dois (acoplado)
    gpu: bool = True                          # LISFLOOD-FP na placa de vídeo (CUDA), se houver
    pasta_trabalho: str = ""

    def salvar(self, arq):
        Path(arq).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def abrir(cls, arq):
        d = json.loads(Path(arq).read_text(encoding="utf-8"))
        f = d.get("forcante") or {}
        f["hidrogramas"] = [Hidrograma(h["nome"], tuple(h["ponto"]), [tuple(x) for x in h["serie"]])
                            for h in f.get("hidrogramas", [])]
        f["chuva"] = [tuple(x) for x in f.get("chuva", [])]
        a = d.get("area_interesse")
        return cls(**{**d, "terreno": Terreno(**d["terreno"]), "rugosidade": Rugosidade(**d.get("rugosidade", {})),
                      "forcante": Forcante(**f),
                      "area_interesse": AreaInteresse(**{**a, "poligono": [tuple(p) for p in a["poligono"]]})
                      if a else None})
