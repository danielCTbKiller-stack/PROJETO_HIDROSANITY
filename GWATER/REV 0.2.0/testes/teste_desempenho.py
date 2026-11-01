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
# o uso do dia a dia: poucas edições num cadastro grande (o salvar não pode reler a rede inteira)
_tr, _nos = n.camada("trecho"), n.camada("no_juncao")
for lyr_, campo_, val_ in ((_tr, "material", "PEAD"), (_nos, "demanda_base", 0.05)):
    lyr_.startEditing()
    i_ = lyr_.fields().indexOf(campo_)
    for f_ in list(lyr_.getFeatures())[:30]:
        lyr_.changeAttributeValue(f_.id(), i_, val_)
medir("salvar poucas edições (30 tubos e 30 nós)", 3, n.acao_salvar)
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
trl = n.camada("trecho")
trl.startEditing()
i_rug = trl.fields().indexOf("rugosidade_hw")
trl.beginEditCommand("rugosidade")
for f in trl.getFeatures():
    trl.changeAttributeValue(f.id(), i_rug, 130.0)
trl.endEditCommand()
trl.commitChanges()
from programa import desenho_extra  # noqa: E402
canto = min(nos.getFeatures(), key=lambda f: f.geometry().asPoint().distance(P(0, 0)))  # vira a fonte da rede
desenho_extra.converter(n, "captacao", [str(canto["id"])])
cap = n.camada("captacao")
cap.startEditing()
for f in cap.getFeatures():
    cap.changeAttributeValue(f.id(), cap.fields().indexOf("carga_hidraulica"), 960.0)
for lyr in n.camadas_rede():
    if lyr.isEditable() and not lyr.commitChanges():
        print("     não salvou", lyr.name(), lyr.commitErrors()[:3], flush=True)
print("     captações:", cap.featureCount(), flush=True)
medir("calcular (24 h)", 90, lambda: j.acionar("simular"))
# animação hora a hora: cada quadro termina de desenhar antes do próximo (nada de mapa pela metade)
from qgis.PyQt.QtCore import QEventLoop, QTimer  # noqa: E402
d_ = n.dock
j.resize(1600, 1000)
j.show()
j.canvas.resize(1200, 800)
quadros = {"inicio": 0, "fim": 0, "cortados": 0}
j.canvas.renderStarting.connect(lambda: quadros.__setitem__("inicio", quadros["inicio"] + 1))
j.canvas.mapCanvasRefreshed.connect(lambda: quadros.__setitem__("fim", quadros["fim"] + 1))
n.res.aplicar(9)  # a primeira vez monta as séries; o que importa é o passo a passo
t_ap = time.perf_counter()
n.res.aplicar(10)
t_ap = time.perf_counter() - t_ap
k0 = d_.slider.value()
d_.vel.setCurrentIndex(3)  # 4×: pede quadros mais rápido do que o mapa desenha
j._animar()
laco = QEventLoop()
QTimer.singleShot(8000, laco.quit)
laco.exec()
passos = (d_.slider.value() - k0) % (d_.slider.maximum() + 1)
durante = dict(quadros)  # contado com a animação rodando (ao pausar, os rótulos voltam e o mapa redesenha)
j._animar()
for _ in range(20):
    app.processEvents()
print(f"     animação: {passos} horas em 8 s; desenhos começados {durante['inicio']}, terminados {durante['fim']}; "
      f"atualizar a hora no mapa: {t_ap * 1000:.0f} ms", flush=True)
ok_anim = passos >= 3 and durante["fim"] >= durante["inicio"] - 1 and j.bt_play.text() == "▶"
print(f"  {'OK   ' if ok_anim else 'LENTO'} animação fluida (todo quadro terminado antes do próximo)", flush=True)
if not ok_anim:
    falhas.append("animação")
# fluxo da água: setas animadas. Mede o quadro só da camada do fluxo (é só ela que redesenha a cada quadro) e
# confere que as setas andam de um quadro para o outro; depois, o fluxo junto com a hora andando
from qgis.core import QgsMapRendererSequentialJob  # noqa: E402
j.bt_fluxo.setChecked(True)
j._fluxo(True, gravar=False)
fl_ = n.res.fl
ms = j.canvas.mapSettings()
ms.setLayers([fl_])
ms.setFrameRate(15)
imgs, tempos_q = [], []
c_ = n.res.tr.extent().center()  # no meio da rede
from qgis.core import QgsRectangle  # noqa: E402
for frame in (0, 4):  # quadro na rede toda (tempo) e, com zoom num bairro, se as setas andaram
    ms.setCurrentFrame(frame)
    job = QgsMapRendererSequentialJob(ms)
    t0 = time.perf_counter()
    job.start()
    job.waitForFinished()
    tempos_q.append(time.perf_counter() - t0)
ms.setExtent(QgsRectangle(c_.x() - 300, c_.y() - 200, c_.x() + 300, c_.y() + 200))
for frame in (0, 4):
    ms.setCurrentFrame(frame)
    job = QgsMapRendererSequentialJob(ms)
    job.start()
    job.waitForFinished()
    imgs.append(job.renderedImage())
anda = imgs[0] != imgs[1]
if os.environ.get("GWATER_FOTO"):
    imgs[0].save(os.environ["GWATER_FOTO"] + "_f0.png")
    imgs[1].save(os.environ["GWATER_FOTO"] + "_f4.png")
from qgis.PyQt.QtGui import QColor  # noqa: E402
fundo = imgs[0].pixel(0, 0)
tem_seta = any(imgs[0].pixel(x, y) != fundo for x in range(0, imgs[0].width(), 3)
               for y in range(0, imgs[0].height(), 3))
zoom = j.canvas.extent()
ms2 = j.canvas.mapSettings()
centro = zoom.center()
from qgis.core import QgsRectangle  # noqa: E402
ms2.setExtent(QgsRectangle(centro.x() - 300, centro.y() - 200, centro.x() + 300, centro.y() + 200))
ms2.setLayers([fl_])
ms2.setFrameRate(15)
job = QgsMapRendererSequentialJob(ms2)
t0 = time.perf_counter()
job.start()
job.waitForFinished()
t_zoom = time.perf_counter() - t0
quadros.update(inicio=0, fim=0)
j._animar()
laco = QEventLoop()
QTimer.singleShot(5000, laco.quit)
laco.exec()
junto = dict(quadros)
j._animar()
print(f"     fluxo: quadro das setas {min(tempos_q) * 1000:.0f} ms na rede toda, {t_zoom * 1000:.0f} ms com zoom num "
      f"bairro; setas aparecem: {tem_seta}, andam entre quadros: {anda}; hora andando junto: {junto['fim'] / 5:.1f} horas/s "
      f"({junto['inicio']}/{junto['fim']})", flush=True)
ok_fl = anda and tem_seta and min(tempos_q) < 0.2 and junto["fim"] >= junto["inicio"] - 1 and junto["fim"] >= 5
print(f"  {'OK   ' if ok_fl else 'LENTO'} fluxo da água animado", flush=True)
if not ok_fl:
    falhas.append("fluxo")
j._fluxo(False, gravar=False)
# análises com milhares de cálculos independentes: 1 núcleo × todos os núcleos
alvo_nos = [str(f["id"]) for f in n.camada("no_juncao").getFeatures()][:int(os.environ.get("GWATER_N_INCENDIO", "400"))]
tempos = {}
for nn in ("1", ""):
    os.environ["GWATER_NUCLEOS"] = nn
    t0 = time.perf_counter()
    r = motor.analise("incendio", n.cadastro(), False, nos=alvo_nos, vazao=10)
    tempos[nn or "todos"] = time.perf_counter() - t0
    print(f"     incêndio em {len(alvo_nos)} nós com {nn or os.cpu_count()} núcleo(s): {tempos[nn or 'todos']:.1f} s "
          f"(ok={r.get('ok')} {r.get('erro') or ''} {[i['msg'] for i in r.get('itens', [])][:3]})", flush=True)
os.environ.pop("GWATER_NUCLEOS", None)
ganho = tempos["1"] / max(tempos["todos"], 1e-9)
print(f"  {'OK   ' if ganho > 1.5 or (os.cpu_count() or 1) < 4 else 'LENTO'} paralelo: {ganho:.1f}× mais rápido", flush=True)
if (os.cpu_count() or 1) >= 4 and ganho <= 1.5:
    falhas.append("paralelo")
medir("zoom total + redesenho", 15, lambda: (j.acionar("zoom_total"), j.canvas.refresh()))

j.fechar_projeto(False)
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"lentos: {', '.join(falhas)}")
sys.exit(1 if falhas else 0)
