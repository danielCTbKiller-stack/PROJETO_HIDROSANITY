"""Teste ponta a ponta: shapefile -> cadastro -> EPANET.

1. gera um shapefile de rede "real" (WGS84, campos abreviados, defeitos comuns);
2. importa com motor/importar_shp.py;
3. adiciona uma captação (o que o usuário faria no QGIS);
4. converte para .inp e simula.

Uso:  python teste_importacao.py
"""
import json
import os
import subprocess
import sys

import geopandas as gpd
from shapely.geometry import LineString, MultiLineString, Point

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "motor"))
PY = sys.executable
SHP = os.path.join(AQUI, "shp_teste")
os.makedirs(SHP, exist_ok=True)
UTM = "EPSG:31983"
E0, N0 = 335000.0, 7393000.0

# ---------------------------------------------------- 1) shapefile de teste
# grade de 4 x 3 quadras de 120 m
L, nx, ny = 120.0, 4, 3
P = lambda i, j: (E0 + i * L, N0 + j * L)
linhas, attrs = [], []
for j in range(ny + 1):
    for i in range(nx):
        linhas.append(LineString([P(i, j), P(i + 1, j)]))
        attrs.append(("DN100" if j else "DN150", "PVC"))
for i in range(nx + 1):
    for j in range(ny):
        linhas.append(LineString([P(i, j), P(i, j + 1)]))
        attrs.append(("DN100", "PVC" if i else "FOFO"))
# defeito 1: ponta com folga de 0,30 m (deve ser unida pela tolerância)
a, b = linhas[0].coords
linhas[0] = LineString([a, (b[0] - 0.30, b[1])])
# defeito 2: ramal que encosta no meio de um trecho sem dividir (T não segmentado)
meio = (E0 + 2.5 * L, N0 + L)
linhas.append(LineString([meio, (meio[0], meio[1] - 60)]))
attrs.append(("DN 75", "PEAD"))
# defeito 3: trecho multiparte
linhas.append(MultiLineString([[P(4, 3), (P(4, 3)[0] + 80, P(4, 3)[1])],
                               [(P(4, 3)[0] + 80, P(4, 3)[1]), (P(4, 3)[0] + 80, P(4, 3)[1] + 90)]]))
attrs.append(("DN100", "PVC"))

rede = gpd.GeoDataFrame({"COD": [f"TR{k:03d}" for k in range(len(linhas))],
                         "DN": [d for d, _ in attrs], "MAT": [m for _, m in attrs],
                         "ANO": [2008] * len(linhas)}, geometry=linhas, crs=UTM).to_crs("EPSG:4326")
rede.to_file(os.path.join(SHP, "rede_agua.shp"))

# pontos de cota em todos os vértices (terreno caindo para leste)
pts = {Point(c) for g in gpd.GeoSeries(linhas).explode() for c in g.coords}
cotas = gpd.GeoDataFrame({"COTA": [round(100 - (p.x - E0) * 0.02 - (p.y - N0) * 0.01, 2) for p in pts]},
                         geometry=list(pts), crs=UTM).to_crs("EPSG:4326")
cotas.to_file(os.path.join(SHP, "cotas.shp"))
print(f"shapefile de teste: {len(rede)} feições, {len(cotas)} pontos de cota")

# ---------------------------------------------------- 2) importar
cfg = {"trechos": os.path.join(SHP, "rede_agua.shp"), "pontos_cota": os.path.join(SHP, "cotas.shp"),
       "destino": "teste_importado",
       "campos": {"id": "COD", "diametro": "DN", "material": "MAT", "ano": "ANO", "cota": "COTA"},
       "materiais": {"PVC": "PVC PBA", "FOFO": "Ferro fundido dúctil", "PEAD": "PEAD"},
       "tolerancia_m": 0.5, "vazao_total_lps": 15.0, "padrao": "PAD_CONS"}
arq_cfg = os.path.join(SHP, "config_importacao.json")
with open(arq_cfg, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
print("\n--- importar_shp.py")
subprocess.run([PY, os.path.join(RAIZ, "motor", "importar_shp.py"), arq_cfg], check=True)

# ---------------------------------------------------- 3) captação ligada ao canto sudoeste
gpkg = os.path.join(RAIZ, "cadastro", "teste_importado.gpkg")
nos = gpd.read_file(gpkg, layer="no_juncao")
canto = nos.loc[nos.geometry.distance(Point(P(0, 0))).idxmin()]
pc = Point(canto.geometry.x - 50, canto.geometry.y)
cap = gpd.GeoDataFrame([{"id": "CAP", "nome": "Captação teste", "carga_hidraulica": 135.0,
                         "situacao": "EXISTENTE"}], geometry=[pc], crs=UTM)
cap.reindex(columns=gpd.read_file(gpkg, layer="captacao").columns).set_geometry("geometry") \
   .set_crs(UTM, allow_override=True).to_file(gpkg, layer="captacao", driver="GPKG")
tr = gpd.read_file(gpkg, layer="trecho")
novo = {c: None for c in tr.columns}
novo.update({"id": "T_ADUTORA", "no_inicial": "CAP", "no_final": canto["id"], "comprimento": 50.0,
             "diametro_nominal": 200.0, "material": "Ferro fundido dúctil", "rugosidade_hw": 130.0,
             "perda_localizada": 0.0, "status": "ABERTO", "situacao": "EXISTENTE",
             "geometry": LineString([pc, canto.geometry])})
gpd.GeoDataFrame([*tr.to_dict("records"), novo], geometry="geometry", crs=UTM) \
   .to_file(gpkg, layer="trecho", driver="GPKG")

# ---------------------------------------------------- 4) converter e simular
print("\n--- cadastro_para_inp.py")
from cadastro_para_inp import converter  # noqa: E402
from simular import rodar  # noqa: E402

inp, rel = converter(gpkg)
print(rel.texto())
assert rel.ok, "conversão falhou"
res, dt = rodar(inp)
p = res.node["pressure"].drop(columns=["CAP"])
v = res.link["velocity"]
print(f"\nSimulação OK em {dt * 1000:.0f} ms · {p.shape[1]} nós · {v.shape[1]} trechos")
print(f"pressão: mín {p.min().min():.1f} mca (nó {p.min().idxmin()}) · máx {p.max().max():.1f} mca")
print(f"velocidade máx {v.max().max():.2f} m/s (trecho {v.max().idxmax()})")

# ---------------------------------------------------- 5) shapefile 3D (PolylineZ, vindo do CAD)
print("\n--- shapefile com Z")
from importar_shp import importar  # noqa: E402

z_shp = os.path.join(SHP, "rede_z.shp")
gpd.GeoDataFrame({"DN": ["100", "75"]}, crs=UTM, geometry=[
    LineString([(E0, N0, 700), (E0 + 10, N0, 701), (E0 + 20, N0 + 5, 702), (E0 + 40, N0 + 10, 704)]),
    LineString([(E0 + 40, N0 + 10, 704), (E0 + 40, N0 + 50, 710)])]).to_file(z_shp)
tz, nz, _ = importar({"trechos": z_shp, "campos": {"diametro": "DN"}})
assert not tz.geometry.has_z.any(), "a rede importada deve ficar em 2D"
assert len(tz) == 2 and sorted(nz["cota"]) == [700, 704, 710], f"cota do Z das pontas: {list(nz['cota'])}"
print(f"OK: {len(tz)} trechos 3D importados em 2D, cotas {sorted(nz['cota'])} tiradas do Z")
