"""Exporta a rede do cadastro em GeoJSON (WGS84) para o mapa do painel web."""
import json

import geopandas as gpd
import pyogrio

# campos de cada camada que o painel mostra ao clicar no elemento
CAMPOS = {
    "captacao": ["id", "nome", "carga_hidraulica"],
    "reservatorio": ["id", "nome", "cota_fundo", "nivel_ini", "nivel_min", "nivel_max", "diametro", "volume_util"],
    "bomba": ["id", "nome", "elevatoria", "cota", "curva", "status_inicial", "rotacao_relativa"],
    "valvula": ["id", "nome", "tipo", "cota", "diametro", "ajuste", "status"],
    "no_juncao": ["id", "nome", "tipo", "cota", "demanda_base", "padrao"],
    "trecho": ["id", "no_inicial", "no_final", "comprimento", "diametro_nominal", "material",
               "rugosidade_hw", "perda_localizada", "status", "ano_instalacao"],
}
COMUNS = ["situacao", "setor"]


def rede(gpkg, com_projetados=True):
    """{'nos': FeatureCollection, 'trechos': FeatureCollection}; desativados ficam de fora."""
    nos, trechos = [], None
    situacoes = ["EXISTENTE", "PROJETADO"] if com_projetados else ["EXISTENTE"]
    for camada, campos in CAMPOS.items():
        g = gpd.read_file(gpkg, layer=camada)
        g = g[g["situacao"].isin(situacoes) | g["situacao"].isna()]
        g = g[[c for c in campos + COMUNS if c in g.columns] + ["geometry"]].to_crs(4326)
        g.insert(1, "camada", camada)
        if camada == "trecho":
            trechos = json.loads(g.to_json(na="null", drop_id=True))
        elif len(g):
            nos.append(g)
    nos = json.loads(gpd.pd.concat(nos).to_json(na="null", drop_id=True)) if nos else \
        {"type": "FeatureCollection", "features": []}
    return {"nos": nos, "trechos": trechos, "cadastro": pyogrio.read_info(gpkg, layer="trecho")["crs"]}


if __name__ == "__main__":
    import sys
    from cadastro_para_inp import GPKG_PADRAO
    r = rede(sys.argv[1] if len(sys.argv) > 1 else GPKG_PADRAO)
    print(len(r["nos"]["features"]), "nós ·", len(r["trechos"]["features"]), "trechos ·", r["cadastro"])
    print(r["trechos"]["features"][0]["properties"], r["trechos"]["features"][0]["geometry"]["coordinates"][:2])
