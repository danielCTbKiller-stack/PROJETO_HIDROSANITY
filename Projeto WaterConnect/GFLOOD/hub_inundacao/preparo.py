"""Preparo dos dados de entrada: rasters no CRS e na grade de cada motor, Manning e chuva de projeto.

Tudo com o GDAL. As saídas são GeoTIFF na pasta de trabalho do cenário; os formatos próprios de cada motor (grade
ASCII do LISFLOOD-FP, vértices da malha do ANUGA) são feitos pelos adaptadores a partir destes.
"""
from pathlib import Path

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()


def info(tif):
    """(transform, largura, altura, crs wkt) de um raster."""
    ds = gdal.Open(str(tif))
    return ds.GetGeoTransform(), ds.RasterXSize, ds.RasterYSize, ds.GetProjection()


def limites(tif):
    gt, w, h, _ = info(tif)
    return gt[0], gt[3] + h * gt[5], gt[0] + w * gt[1], gt[3]   # xmin, ymin, xmax, ymax


def grade(origem, saida, crs, resolucao, limites_=None, metodo="bilinear", nodata=-9999.0):
    """Reprojeta, recorta (limites xmin, ymin, xmax, ymax no CRS de destino) e reamostra para a resolução."""
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    gdal.Warp(str(saida), str(origem), dstSRS=crs, xRes=resolucao, yRes=resolucao, outputBounds=limites_,
              resampleAlg=metodo, dstNodata=nodata, targetAlignedPixels=limites_ is None, format="GTiff",
              creationOptions=["COMPRESS=DEFLATE"])
    return str(saida)


def _vazio_como(ref, saida, valor):
    gt, w, h, wkt = info(ref)
    ds = gdal.GetDriverByName("GTiff").Create(str(saida), w, h, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(wkt)
    b = ds.GetRasterBand(1)
    b.Fill(valor)
    b.SetNoDataValue(-9999.0)
    return ds


def manning(rug, ref, saida):
    """Raster de Manning na grade de `ref`: o raster informado reamostrado, ou os polígonos de uso do solo
    queimados com o n de cada classe (n_padrao onde não há polígono nem classe conhecida)."""
    gt, w, h, wkt = info(ref)
    xmin, ymin, xmax, ymax = limites(ref)
    if rug.raster:
        return grade(rug.raster, saida, wkt, gt[1], (xmin, ymin, xmax, ymax), metodo="near")
    ds = _vazio_como(ref, saida, rug.n_padrao)
    if rug.poligonos:
        src = ogr.Open(str(rug.poligonos))
        lyr = src.GetLayer(0)
        for classe, n in rug.n_por_classe.items():
            lyr.SetAttributeFilter(f"\"{rug.campo_classe}\" = '{str(classe).replace(chr(39), chr(39) * 2)}'")
            gdal.RasterizeLayer(ds, [1], lyr, burn_values=[float(n)])
        lyr.SetAttributeFilter(None)
    ds.FlushCache()
    ds = None
    return str(saida)


def edificacoes(mdt, poligonos, altura, saida):
    """MDT com as edificações levantadas `altura` metros (obstáculos para a água)."""
    src = gdal.Open(str(mdt))
    gdal.Translate(str(saida), src, format="GTiff", creationOptions=["COMPRESS=DEFLATE"])
    src = None
    ds = gdal.Open(str(saida), gdal.GA_Update)
    mascara = _vazio_como(saida, str(saida) + ".mask.tif", 0.0)
    camada = ogr.Open(str(poligonos)).GetLayer(0)
    gdal.RasterizeLayer(mascara, [1], camada, burn_values=[1.0])
    b = ds.GetRasterBand(1)
    z = b.ReadAsArray().astype("float64")
    m = mascara.GetRasterBand(1).ReadAsArray() > 0.5
    nd = b.GetNoDataValue()
    z[m & (z != nd if nd is not None else True)] += altura
    b.WriteArray(z)
    ds, mascara = None, None
    Path(str(saida) + ".mask.tif").unlink(missing_ok=True)
    return str(saida)


def ler(tif):
    """(matriz, transform, nodata)"""
    ds = gdal.Open(str(tif))
    b = ds.GetRasterBand(1)
    return b.ReadAsArray().astype("float64"), ds.GetGeoTransform(), b.GetNoDataValue()


def gravar(matriz, ref, saida, nodata=-9999.0):
    """GeoTIFF com a grade e o CRS de `ref`."""
    gt, _, _, wkt = info(ref)
    h, w = matriz.shape
    ds = gdal.GetDriverByName("GTiff").Create(str(saida), w, h, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(wkt)
    b = ds.GetRasterBand(1)
    b.WriteArray(np.where(np.isfinite(matriz), matriz, nodata))
    b.SetNoDataValue(nodata)
    ds = None
    return str(saida)


def criar_raster(matriz, x0, y0_topo, resolucao, crs, saida, nodata=-9999.0):
    """GeoTIFF a partir de uma matriz (linha 0 = norte). Usado nos casos sintéticos."""
    h, w = matriz.shape
    ds = gdal.GetDriverByName("GTiff").Create(str(saida), w, h, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((x0, resolucao, 0, y0_topo, 0, -resolucao))
    s = osr.SpatialReference()
    s.SetFromUserInput(crs)
    ds.SetProjection(s.ExportToWkt())
    b = ds.GetRasterBand(1)
    b.WriteArray(matriz)
    b.SetNoDataValue(nodata)
    ds = None
    return str(saida)


# ---------------------------------------------------------------- chuva de projeto
def idf(K, a, b, c, tr_anos, duracao_min):
    """Intensidade (mm/h) pela equação IDF i = K·TR^a / (t + b)^c, com t em minutos."""
    return K * tr_anos ** a / (duracao_min + b) ** c


def hietograma(K, a, b, c, tr_anos, duracao_min, passo_min=5):
    """Chuva de projeto pelos blocos alternados: [(tempo s, intensidade mm/h)] com o pico no meio do evento."""
    n = max(1, int(round(duracao_min / passo_min)))
    acum = [idf(K, a, b, c, tr_anos, passo_min * (k + 1)) * passo_min * (k + 1) / 60 for k in range(n)]  # mm
    blocos = [acum[0]] + [acum[k] - acum[k - 1] for k in range(1, n)]
    meio = (n - 1) // 2
    lugares = [meio]  # o maior bloco no meio; os seguintes alternando direita e esquerda
    for d in range(1, n):
        lugares += [x for x in (meio + d, meio - d) if 0 <= x < n]
    serie = [0.0] * n
    for lugar, bloco in zip(lugares, sorted(blocos, reverse=True)):
        serie[lugar] = bloco * 60 / passo_min   # mm no bloco -> mm/h
    return [(i * passo_min * 60.0, round(v, 3)) for i, v in enumerate(serie)]


def volume_chuva_mm(serie, passo_s=None):
    """Altura total (mm) de uma série (tempo s, mm/h) em degraus."""
    if not serie:
        return 0.0
    ts = [t for t, _ in serie] + [serie[-1][0] + (passo_s or (serie[1][0] - serie[0][0] if len(serie) > 1 else 0))]
    return sum(v * (ts[i + 1] - ts[i]) / 3600 for i, (_, v) in enumerate(serie))


def mm_h_para_m_s(v):
    return v / 1000.0 / 3600.0

