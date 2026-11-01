"""Importa uma rede de shapefile (linhas) para um cadastro GWATER novo.

Uso:
  python importar_shp.py config.json

O config.json diz onde estão os arquivos e como se chamam os campos do seu .shp:
{
  "trechos": "C:/dados/rede.shp",            # obrigatório: linhas da rede
  "pontos_cota": "C:/dados/cotas.shp",       # opcional: pontos com cota
  "destino": "importado",                     # gera cadastro/importado.gpkg + GWATER_importado.qgz
                                              # (ou um caminho completo: C:/obras/bairro.gpkg)
  "crs": "EPSG:31983",                        # opcional: sistema do cadastro novo (padrão = o do exemplo)
  "campos": {"id": "COD", "diametro": "DN", "material": "MAT", "ano": "ANO", "cota": "COTA"},
  "materiais": {"PVC": "PVC PBA", "FOFO": "Ferro fundido dúctil"},
  "tolerancia_m": 0.5,                        # pontas mais próximas que isso viram o mesmo nó
  "vazao_total_lps": 12.0,                    # opcional: distribui a demanda pelos nós
  "padrao": "PAD_CONS"
}

O que ele faz:
  1. reprojeta para o SIRGAS 2000 / UTM do cadastro e separa multipartes;
  2. cria os nós nas pontas dos trechos, unindo pontas a menos de tolerancia_m;
  3. lê a cota do ponto de cota mais próximo (se houver);
  4. distribui a vazão total pelos nós, proporcional a metade do comprimento
     dos trechos ligados a cada nó (método usual de alocação de demanda);
  5. avisa sobre pontas soltas que encostam no meio de outro trecho
     (ligação provavelmente não segmentada no .shp).
Captação, reservatórios, bombas e válvulas são adicionados depois, no QGIS.
"""
import json
import os
import shutil
import sys
import zipfile
from collections import defaultdict

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CADASTRO = os.path.join(RAIZ, "cadastro")
MODELO_GPKG = os.path.join(CADASTRO, "gwater_cadastro.gpkg")
MODELO_QGZ = os.path.join(CADASTRO, "GWATER_cadastro.qgz")
REDE = ["captacao", "reservatorio", "bomba", "valvula", "no_juncao", "trecho"]


def _campo(df, cfg, chave):
    nome = cfg["campos"].get(chave)
    if nome and nome not in df.columns:
        raise SystemExit(f"campo '{nome}' ({chave}) não existe no shapefile. Campos: {list(df.columns)}")
    return df[nome] if nome else pd.Series([None] * len(df), index=df.index)


def _num(s):
    """'DN100', '100 mm', '0,15' -> número."""
    return pd.to_numeric(s.astype(str).str.replace(",", ".").str.extract(r"([\d.]+)")[0], errors="coerce")


def dividir_em_T(lin, tol, avisos):
    """Divide o trecho onde a ponta de outro trecho encosta no meio dele (T não segmentado)."""
    from shapely.ops import substring
    linhas = list(lin.to_dict("records"))
    mudou = True
    while mudou:
        mudou = False
        arvore = STRtree([r["geometry"] for r in linhas])
        for r in linhas:
            for ponta in (Point(r["geometry"].coords[0]), Point(r["geometry"].coords[-1])):
                for j in arvore.query(ponta, predicate="dwithin", distance=tol):
                    host = linhas[int(j)]
                    g = host["geometry"]
                    if host is r:
                        continue
                    d = g.project(ponta)
                    if d <= tol or d >= g.length - tol:
                        continue  # encosta na ponta do outro: ligação normal
                    a, b = substring(g, 0, d), substring(g, d, g.length)
                    avisos.append(f"trecho {host.get(lin.columns[0], j)} dividido em T a {d:.1f} m do início")
                    linhas[int(j)] = {**host, "geometry": a}
                    linhas.append({**host, "geometry": b})
                    mudou = True
                    break
                if mudou:
                    break
            if mudou:
                break
    return gpd.GeoDataFrame(linhas, geometry="geometry", crs=lin.crs).reset_index(drop=True)


def importar(cfg):
    avisos = []
    tol = float(cfg.get("tolerancia_m", 0.5))
    crs = cfg.get("crs") or pyogrio.read_info(MODELO_GPKG, layer="trecho")["crs"]

    lin = gpd.read_file(cfg["trechos"])
    if lin.crs is None:
        raise SystemExit("o shapefile não tem sistema de coordenadas (.prj). Defina no QGIS e salve de novo.")
    lin = lin.to_crs(crs).explode(index_parts=False).reset_index(drop=True)
    lin = lin[lin.geometry.notna() & ~lin.geometry.is_empty & (lin.geometry.length > 0)]
    # linhas 3D (PolylineZ, comum em arquivo vindo do CAD): o Z das pontas vira cota dos nós sem ponto de cota,
    # e a rede segue em 2D (misturar vértices 2D e 3D na mesma linha quebra a geometria)
    z_pontas = []
    if lin.geometry.has_z.any():
        for g in lin.geometry:
            for c in (g.coords[0], g.coords[-1]):
                if len(c) > 2 and c[2] == c[2] and c[2] != 0:
                    z_pontas.append((Point(c[0], c[1]), float(c[2])))
        lin = lin.set_geometry(shapely.force_2d(lin.geometry.values))
    print(f"  {len(lin)} trechos lidos de {os.path.basename(cfg['trechos'])}")
    if cfg.get("dividir_em_T", True):
        lin = dividir_em_T(lin, tol, avisos)

    # ------------------------------------------------ nós nas pontas (com tolerância)
    pontas = []  # (indice_trecho, 0=inicio/1=fim, Point)
    for i, g in zip(lin.index, lin.geometry):
        pontas += [(i, 0, Point(g.coords[0])), (i, 1, Point(g.coords[-1]))]
    arvore = STRtree([p for _, _, p in pontas])
    pai = list(range(len(pontas)))

    def raiz(k):
        while pai[k] != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k

    for k, (_, _, p) in enumerate(pontas):
        for j in arvore.query(p, predicate="dwithin", distance=tol):
            pai[raiz(int(j))] = raiz(k)

    grupos = defaultdict(list)
    for k in range(len(pontas)):
        grupos[raiz(k)].append(k)
    no_de, nos_xy = {}, []
    for n, (r, membros) in enumerate(sorted(grupos.items(), key=lambda x: min(x[1])), start=1):
        nid = f"N-{n:04d}"
        p = pontas[membros[0]][2]
        nos_xy.append((nid, p))
        for k in membros:
            no_de[k] = (nid, p)
            if pontas[k][2].distance(p) > 1e-6:
                avisos.append(f"ponta do trecho {pontas[k][0]} movida {pontas[k][2].distance(p):.2f} m para o nó {nid}")

    # ------------------------------------------------ trechos
    ids = _campo(lin, cfg, "id")
    dn = _num(_campo(lin, cfg, "diametro"))
    mat_shp = _campo(lin, cfg, "material")
    mapa_mat = cfg.get("materiais", {})
    ano = _campo(lin, cfg, "ano")  # aceita 1998, 15/03/1998, 1998-03-15 ou campo de data
    if not pd.api.types.is_numeric_dtype(ano):
        datas = pd.to_datetime(ano, errors="coerce", dayfirst=True, format="mixed")
        ano = datas.dt.year.where(datas.notna(), pd.to_numeric(ano, errors="coerce"))
    ano = pd.to_numeric(ano, errors="coerce")
    dom = pyogrio.read_dataframe(MODELO_GPKG, layer="dominio_material")
    rug = dict(zip(dom["material"], dom["rugosidade_hw"]))

    registros, geoms, usados = [], [], set()
    for n, i in enumerate(lin.index):
        k0, k1 = 2 * n, 2 * n + 1
        (a, pa), (b, pb) = no_de[k0], no_de[k1]
        if a == b:
            avisos.append(f"trecho {i} descartado: as duas pontas caem no mesmo nó {a} (trecho muito curto?)")
            continue
        coords = list(lin.geometry[i].coords)
        coords[0], coords[-1] = (pa.x, pa.y), (pb.x, pb.y)
        g = LineString(coords)
        tid = str(ids[i]) if pd.notna(ids[i]) and str(ids[i]).strip() else f"T-{n + 1:04d}"
        if tid in usados:
            tid = f"{tid}_{n + 1}"
        usados.add(tid)
        m = mat_shp[i]
        mat = mapa_mat.get(str(m).strip(), str(m).strip()) if pd.notna(m) else None
        if mat and mat not in rug:
            avisos.append(f"trecho {tid}: material '{mat}' fora do domínio; ajuste em 'materiais' no config")
        if pd.isna(dn[i]):
            avisos.append(f"trecho {tid}: sem diâmetro")
        registros.append({"id": tid, "no_inicial": a, "no_final": b, "comprimento": round(g.length, 2),
                          "diametro_nominal": dn[i], "material": mat, "rugosidade_hw": rug.get(mat),
                          "perda_localizada": 0.0, "status": "ABERTO",
                          "ano_instalacao": int(ano[i]) if pd.notna(ano[i]) else None,
                          "situacao": "EXISTENTE", "setor": None, "observacao": "importado do shp"})
        geoms.append(g)
    trechos = gpd.GeoDataFrame(registros, geometry=geoms, crs=crs)

    # ------------------------------------------------ pontas soltas encostando no meio de outro trecho
    grau = defaultdict(int)
    for t in registros:
        grau[t["no_inicial"]] += 1
        grau[t["no_final"]] += 1
    arv_t = STRtree(list(trechos.geometry))
    xy = dict(nos_xy)
    for nid, g in grau.items():
        if g != 1:
            continue
        for j in arv_t.query(xy[nid], predicate="dwithin", distance=tol):
            t = registros[int(j)]
            if nid not in (t["no_inicial"], t["no_final"]):
                avisos.append(f"nó {nid} encosta no meio do trecho {t['id']}: ligação não segmentada? "
                              f"(divida o trecho no QGIS se forem conectados)")

    # ------------------------------------------------ cotas e demandas
    cota = {}
    if cfg.get("pontos_cota"):
        pc = gpd.read_file(cfg["pontos_cota"]).to_crs(crs)
        col = cfg["campos"].get("cota", "COTA")
        arv_c = STRtree(list(pc.geometry))
        for nid, p in nos_xy:
            j = arv_c.nearest(p)
            if pc.geometry.iloc[j].distance(p) <= max(tol, 5.0):
                cota[nid] = float(str(pc[col].iloc[j]).replace(",", "."))
    if z_pontas:
        arv_z = STRtree([p for p, _ in z_pontas])
        for nid, p in nos_xy:
            if nid not in cota:
                j = int(arv_z.nearest(p))
                if z_pontas[j][0].distance(p) <= max(tol, 0.01):
                    cota[nid] = round(z_pontas[j][1], 3)
        print(f"  shapefile com Z: cota de {sum(1 for n, _ in nos_xy if n in cota)} nó(s) tirada do Z das pontas")
    sem_cota = [n for n, _ in nos_xy if n not in cota]
    if sem_cota:
        avisos.append(f"{len(sem_cota)} nós sem cota (ex.: {', '.join(sem_cota[:5])}). "
                      f"Preencha no QGIS ou use 'Amostrar valores raster' sobre um MDT.")

    meio_L = defaultdict(float)
    for t in registros:
        meio_L[t["no_inicial"]] += t["comprimento"] / 2
        meio_L[t["no_final"]] += t["comprimento"] / 2
    q_total = cfg.get("vazao_total_lps")
    L_total = sum(meio_L.values())
    nos = gpd.GeoDataFrame([{
        "id": nid, "nome": None, "tipo": "CONSUMO" if q_total else "JUNCAO", "cota": cota.get(nid),
        "demanda_base": round(q_total * meio_L[nid] / L_total, 4) if q_total else 0.0,
        "padrao": cfg.get("padrao", "PAD_CONS") if q_total else None,
        "situacao": "EXISTENTE", "setor": None, "observacao": "criado na importação"} for nid, _ in nos_xy],
        geometry=[p for _, p in nos_xy], crs=crs)
    return trechos, nos, avisos


def _destino(destino):
    """'bairro' -> cadastro/bairro.gpkg + cadastro/GWATER_bairro.qgz; caminho completo -> na pasta dele."""
    if os.path.isabs(destino):
        pasta, nome = os.path.split(os.path.splitext(destino)[0])
    else:
        pasta, nome = CADASTRO, destino
    return os.path.join(pasta, nome + ".gpkg"), os.path.join(pasta, f"GWATER_{nome}.qgz")


def gravar(trechos, nos, destino, crs=None):
    """Copia o cadastro-modelo (tabelas, domínios, projeto) e troca a rede pela importada.

    crs: sistema das camadas do cadastro novo (padrão = o do exemplo).
    """
    gpkg, qgz = _destino(destino)
    if os.path.abspath(gpkg) == os.path.abspath(MODELO_GPKG):
        raise SystemExit("o destino não pode ser o próprio cadastro de exemplo")
    os.makedirs(os.path.dirname(gpkg), exist_ok=True)
    shutil.copyfile(MODELO_GPKG, gpkg)
    for camada in REDE + ["controle"]:  # controles do exemplo não valem para a rede nova
        modelo = gpd.read_file(gpkg, layer=camada)
        if camada == "trecho" and trechos is not None:
            novo = trechos
        elif camada == "no_juncao" and nos is not None:
            novo = nos
        else:
            novo = modelo.iloc[0:0]
        novo = novo.reindex(columns=modelo.columns)
        if "geometry" in modelo.columns and modelo.geometry.name == "geometry" and modelo.crs is not None:
            novo = gpd.GeoDataFrame(novo, geometry="geometry", crs=crs or modelo.crs)
            # tipo explícito: camada vazia gravada como "Unknown" não aceita o que se desenha no QGIS
            tipo = pyogrio.read_info(MODELO_GPKG, layer=camada)["geometry_type"]
            novo.to_file(gpkg, layer=camada, driver="GPKG", geometry_type=tipo)
        else:
            pyogrio.write_dataframe(pd.DataFrame(novo), gpkg, layer=camada, driver="GPKG")
    # propostas, medições e telemetria são do cadastro de origem, não da rede nova
    for camada in {n for n, _ in pyogrio.list_layers(gpkg)} & {"cenario", "cenario_alteracao", "medicao"}:
        modelo = pyogrio.read_dataframe(gpkg, layer=camada)
        pyogrio.write_dataframe(modelo.iloc[0:0], gpkg, layer=camada, driver="GPKG")

    # projeto QGIS: mesmo do exemplo, apontando para o novo GeoPackage (caminho relativo: mesma pasta)
    nome_gpkg = os.path.basename(gpkg)
    with zipfile.ZipFile(MODELO_QGZ) as zin, zipfile.ZipFile(qgz, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename.endswith(".qgs"):
                dados = dados.replace(b"gwater_cadastro.gpkg", nome_gpkg.encode())
            zout.writestr(item, dados)
    return gpkg, qgz


def novo_cadastro(destino, crs=None):
    """Cadastro vazio (só tabelas, padrões, curvas-modelo e projeto QGIS) para desenhar do zero."""
    return gravar(None, None, destino, crs)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)
    trechos, nos, avisos = importar(cfg)
    gpkg, qgz = gravar(trechos, nos, cfg.get("destino", "importado"), cfg.get("crs"))
    print(f"  {len(trechos)} trechos e {len(nos)} nós gravados")
    for a in avisos:
        print("  AVISO", a)
    print(f"\nCadastro: {gpkg}\nProjeto QGIS: {qgz}")
    print("Próximo passo: abra o projeto e adicione a captação/reservatório, bombas e válvulas.")
