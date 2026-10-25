"""Desempenho do GWATER.exe numa rede grande: importar, salvar, TRex, abrir, tabelas e calcular.

Mede o tempo de cada operação (e o perfil das mais lentas, com GWATER_PERFIL=1) e falha se alguma passar do limite.

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_desempenho.py   (GWATER_N=100 → 20 mil tubos)
"""
import cProfile
import io
import os
import pstats
import shutil
import sys
import tempfile
import time

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "app"))
from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateTransformContext, QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

app = QgsApplication([b"teste"], True)
app.initQgis()
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
from programa.janela import Janela  # noqa: E402
from gwater import motor  # noqa: E402
from gwater.cotas import Fonte  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gwater_teste_desemp_")
N = int(os.environ.get("GWATER_N", "100"))
PERFIL = bool(os.environ.get("GWATER_PERFIL"))
falhas = []


def medir(nome, limite, func):
    pr = cProfile.Profile() if PERFIL else None
    t0 = time.perf_counter()
    if pr:
        pr.enable()
    r = func()
    for _ in range(3):
        app.processEvents()
    if pr:
        pr.disable()
    dt = time.perf_counter() - t0
    ok = dt <= limite
    print(f"  {'OK   ' if ok else 'LENTO'} {nome}: {dt:.2f} s (limite {limite} s)", flush=True)
    if not ok:
        falhas.append(nome)
    if pr:
        s = io.StringIO()
        pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(40)
        print("\n".join(s.getvalue().splitlines()[6:52]))
    return r


P = lambda x, y: QgsPointXY(333000.0 + x, 7390000.0 + y)  # noqa: E731
L = 50.0
mem = QgsVectorLayer("LineString?crs=EPSG:31983&field=DN:integer", "rede_tubos", "memory")
fs = []
for r in range(N + 1):
    for c in range(N):
        for a, b in (((c, r), (c + 1, r)), ((r, c), (r, c + 1))):
            f = QgsFeature(mem.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([P(a[0] * L, a[1] * L), P(b[0] * L, b[1] * L)]))
            f.setAttributes([100])
            fs.append(f)
mem.dataProvider().addFeatures(fs)
arq = os.path.join(TMP, "rede_tubos.shp")
opt = QgsVectorFileWriter.SaveVectorOptions()
opt.driverName = "ESRI Shapefile"
QgsVectorFileWriter.writeAsVectorFormatV3(mem, arq, QgsCoordinateTransformContext(), opt)
curvas = QgsVectorLayer("LineString?crs=EPSG:31983&field=COTA:double", "curvas", "memory")
cs = []
for k in range(-4, N + 6):
    f = QgsFeature(curvas.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([P(-300 + 7 * i, k * L + 10 * ((i % 9) - 4)) for i in range(int((N * L + 600) / 7))]))
    f.setAttributes([900.0 - k])
    cs.append(f)
curvas.dataProvider().addFeatures(cs)
print(f"rede de teste: {len(fs)} tubulações, {len(cs)} curvas de nível", flush=True)

r = motor.rodar("novo", os.path.join(TMP, "rede.gpkg"), False, ["--crs=EPSG:31983"])
j = Janela()
j.abrir_projeto(r["qgz"])
app.processEvents()
n = j.nucleo

from programa.modelbuilder_ui import ModelBuilderApp  # noqa: E402
dlg = ModelBuilderApp(j, n)
dlg._por(QgsVectorLayer(arq, "rede_tubos", "ogr"), "rede_tubos")
for k in (1, 2, 3):
    dlg._ir(k)
medir("importar (ModelBuilder)", 30, dlg._executar)
medir("salvar edições", 20, n.acao_salvar)

from gwater import ferramentas  # noqa: E402
fonte = Fonte("curvas", curvas, n.camada("trecho").crs(), "COTA")
feitos = medir("TRex (curvas de nível, todos os nós)", 30, lambda: ferramentas.preencher_cotas(n, fonte, True))
print("     cotas:", feitos[0], "sem cota:", len(feitos[1]))
medir("salvar as cotas", 20, n.acao_salvar)
medir("desfazer e refazer", 15, lambda: (j.desfazer(), j.refazer()))

medir("fechar o projeto", 15, lambda: j.fechar_projeto(False))
medir("abrir o projeto", 20, lambda: j.abrir_projeto(r["qgz"]))
n = j.nucleo
medir("tabela de tubulações", 15, lambda: j.acionar("tabela_trecho"))
i_cota, i_dem = n.camada("no_juncao").fields().indexOf("cota"), n.camada("no_juncao").fields().indexOf("demanda_base")
nos = n.camada("no_juncao")
nos.startEditing()
nos.beginEditCommand("demanda")
for f in nos.getFeatures():
    nos.changeAttributeValue(f.id(), i_dem, 0.02)
nos.endEditCommand()
nos.commitChanges()
medir("calcular (24 h)", 90, lambda: j.acionar("simular"))
medir("zoom total + redesenho", 15, lambda: (j.acionar("zoom_total"), j.canvas.refresh()))

j.fechar_projeto(False)
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"lentos: {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
