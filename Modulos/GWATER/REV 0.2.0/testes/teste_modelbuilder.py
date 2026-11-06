"""Teste do ModelBuilder do GWATER.exe com uma rede grande (importação rápida em lote).

Gera, com o próprio QGIS, os shapefiles de uma rede em grade:
  rede_tubos.shp   linhas de quadra contínuas (viram "T" em cada cruzamento) e segmentos com folga de até 15 cm
  vrp.shp          PRVs no meio das tubulações (dividem a tubulação e ficam entre os pedaços)
  registros.shp    registros no meio das tubulações
  hidrantes.shp    hidrantes nos cruzamentos (substituem o nó)
  captacao.shp     a fonte
Monta o ModelBuilder com os cinco arquivos (o tipo sugerido pelo nome de cada um), importa e confere:
tempo, quantidades, nenhuma ponta sem nó, válvula com 1 tubulação chegando e 1 saindo, desfazer e a rede
válida no motor depois de Salvar edições.

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_modelbuilder.py   (GWATER_N=100 para 20 mil tubos)
"""
import os
import random
import shutil
import sys
import tempfile
import time
from collections import defaultdict

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "app"))
from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateTransformContext, QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

app = QgsApplication([b"teste"], True)
app.initQgis()
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
from programa.janela import Janela  # noqa: E402
from gwater import motor  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gwater_teste_mb_")
N = int(os.environ.get("GWATER_N", "60"))
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg, flush=True)
    if not cond:
        falhas.append(msg)


def shp(nome, geo, campos, feicoes):
    mem = QgsVectorLayer(f"{geo}?crs=EPSG:31983", nome, "memory")
    mem.dataProvider().addAttributes([QgsField(c, t) for c, t in campos])
    mem.updateFields()
    fs = []
    for g, vals in feicoes:
        f = QgsFeature(mem.fields())
        f.setGeometry(g)
        f.setAttributes(vals)
        fs.append(f)
    mem.dataProvider().addFeatures(fs)
    arq = os.path.join(TMP, nome + ".shp")
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = "ESRI Shapefile"
    QgsVectorFileWriter.writeAsVectorFormatV3(mem, arq, QgsCoordinateTransformContext(), opt)
    return arq


random.seed(1)
E0, N0, L = 333000.0, 7390000.0, 50.0
j = lambda: random.uniform(-0.15, 0.15)  # noqa: E731
P = lambda x, y: QgsPointXY(E0 + x, N0 + y)  # noqa: E731
tubos = [(QgsGeometry.fromPolylineXY([P(0, r * L), P(N * L, r * L)]), ["PVC", 150, f"R{r}"]) for r in range(N + 1)]
tubos += [(QgsGeometry.fromPolylineXY([P(c * L + j(), r * L + j()), P(c * L + j(), (r + 1) * L + j())]),
           ["FOFO" if c % 7 == 0 else "PVC", 75, f"V{c}_{r}"]) for c in range(N + 1) for r in range(N)]
arq_tubos = shp("rede_tubos", "LineString", [("MAT", QVariant.String), ("DN", QVariant.Int), ("COD", QVariant.String)], tubos)
prv = [(QgsGeometry.fromPointXY(P(c * L, 5 * L + L / 2)), [25.0, 75]) for c in range(0, N, 2)]
arq_vrp = shp("vrp", "Point", [("AJUSTE", QVariant.Double), ("DN", QVariant.Int)], prv)
reg = [(QgsGeometry.fromPointXY(P(c * L + L / 2, 20 * L)), ["ABERTO"]) for c in range(0, N - 10, 3)]
arq_reg = shp("registros", "Point", [("ESTADO", QVariant.String)], reg)
hid = [(QgsGeometry.fromPointXY(P(c * L, r * L)), [800.0]) for c in range(5, N, 10) for r in range(5, N, 10)]
arq_hid = shp("hidrantes", "Point", [("COTA", QVariant.Double)], hid)
arq_cap = shp("captacao", "Point", [("CARGA", QVariant.Double)], [(QgsGeometry.fromPointXY(P(0, 0)), [900.0])])
print(f"rede de teste: {len(tubos)} linhas, {len(prv)} PRV, {len(reg)} registros, {len(hid)} hidrantes", flush=True)

r = motor.rodar("novo", os.path.join(TMP, "rede.gpkg"), False, ["--crs=EPSG:31983"])
j_ = Janela()
j_.abrir_projeto(r["qgz"])
for _ in range(10):
    app.processEvents()
n = j_.nucleo
checar(n.cadastro() is not None, "cadastro vazio aberto")

print("\n== janela do ModelBuilder", flush=True)
from programa.modelbuilder_ui import ModelBuilderApp  # noqa: E402
dlg = ModelBuilderApp(j_, n)
for arq in (arq_tubos, arq_vrp, arq_reg, arq_hid, arq_cap):
    dlg._por(QgsVectorLayer(arq, os.path.basename(arq), "ogr"), os.path.basename(arq))
tipos = [f["combo"].currentData() for f in dlg.fontes]
checar(tipos == ["tubulacao", "valvula_prv", "registro", "hidrante", "captacao"], f"tipo sugerido pelo nome: {tipos}")
checar(not dlg.fontes[0]["combo"].isEnabled() and dlg.fontes[1]["combo"].isEnabled(),
       "linhas só podem ser tubulação; pontos têm a lista de tipos")
checar(dlg.fontes[1]["combo"].count() >= 15, f"tipos de ponto: {dlg.fontes[1]['combo'].count()}")
for k in (1, 2, 3):
    dlg._ir(k)
mapa_vrp = dlg.mapa(dlg.fontes[1])
checar(mapa_vrp.get("ajuste") == "AJUSTE" and mapa_vrp.get("diametro") == "DN" and "tipo" not in mapa_vrp,
       f"de-para da PRV (o tipo vem da escolha): {mapa_vrp}")
dlg.fontes[4]["estado"]["combos"]["carga_hidraulica"].setCurrentIndex(
    dlg.fontes[4]["estado"]["combos"]["carga_hidraulica"].findData("CARGA"))
# cota automática ligada (como quem usou o TRex com curvas de nível): a importação não pode travar nela
from gwater.cotas import Fonte  # noqa: E402
curvas = QgsVectorLayer("LineString?crs=EPSG:31983&field=COTA:double", "curvas", "memory")
fs = []
for k in range(0, N + 2, 2):
    f = QgsFeature(curvas.fields())
    f.setGeometry(QgsGeometry.fromPolylineXY([P(-200, k * L), P(N * L + 200, k * L)]))
    f.setAttributes([900.0 - k])
    fs.append(f)
curvas.dataProvider().addFeatures(fs)
n.topologia.mdt = Fonte("curvas", curvas, n.camada("trecho").crs(), "COTA")
t0 = time.perf_counter()
dlg._executar()
dt = time.perf_counter() - t0
res = dlg.resultado
checar(res is not None, f"importou: {res and {k: v for k, v in res.items() if k != 'avisos'}}")
print("     avisos:", res["avisos"] if res else None, flush=True)
checar(dt < 60, f"tempo da importação: {dt:.1f} s para {len(tubos)} linhas")

tr, nos, val = n.camada("trecho"), n.camada("no_juncao"), n.camada("valvula")
esperado = (N + 1) * N + N * (N + 1) + len(prv) + len(reg)
checar(abs(tr.featureCount() - esperado) <= 2, f"tubulações: {tr.featureCount()} (esperado ~{esperado}: linhas de quadra "
       "divididas em cada cruzamento + divisões nas válvulas)")
vazias = sum(1 for f in tr.getFeatures() if f["no_inicial"] in (None, "") or f["no_final"] in (None, ""))
checar(vazias == 0, f"nenhuma tubulação com ponta sem nó ({vazias})")
checar(val.featureCount() == len(prv) + len(reg), f"válvulas: {val.featureCount()}")
tipos_v = defaultdict(int)
for f in val.getFeatures():
    tipos_v[f["tipo"]] += 1
checar(tipos_v == {"PRV": len(prv), "REGISTRO": len(reg)}, f"cada válvula com o seu tipo: {dict(tipos_v)}")
inc = defaultdict(lambda: [0, 0])
for f in tr.getFeatures():
    inc[f["no_final"]][0] += 1
    inc[f["no_inicial"]][1] += 1
ruins = [str(f["id"]) for f in val.getFeatures() if inc[str(f["id"])] != [1, 1]]
checar(not ruins, f"toda válvula com 1 tubulação chegando e 1 saindo ({len(ruins)} fora: {ruins[:5]})")
hidr = sum(1 for f in nos.getFeatures() if f["tipo"] == "HIDRANTE")
checar(hidr == len(hid), f"hidrantes: {hidr} (substituíram os nós dos cruzamentos)")
sem_cota = sum(1 for f in nos.getFeatures() if f["cota"] is None or str(f["cota"]) == "NULL")
checar(sem_cota == 0, f"todos os nós com cota das curvas de nível ({sem_cota} sem)")
n.topologia.mdt = None
nos_total = nos.featureCount()
checar(abs(nos_total - (N + 1) ** 2) <= 2, f"nós: {nos_total} (um por cruzamento: as folgas de 15 cm foram unidas)")
n.janela.dock_arvore.recontar()  # na janela isso roda sozinho, logo depois das edições
contagem = n.janela.dock_arvore.itens["valvula_prv"].text(0)
checar(f"({len(prv)})" in contagem, f"painel Simbologia conta os tipos: '{contagem}'")

print("\n== desfazer e validar no motor", flush=True)
for _ in range(8):
    n.janela.desfazer()
checar(tr.featureCount() == 0 and val.featureCount() == 0, f"Ctrl+Z desfaz a importação ({tr.featureCount()} tubos)")
for _ in range(8):
    n.janela.refazer()
checar(tr.featureCount() > 0, f"Ctrl+Y refaz ({tr.featureCount()} tubos)")
i_cota, i_dem = nos.fields().indexOf("cota"), nos.fields().indexOf("demanda_base")
nos.beginEditCommand("cotas e demandas")
for f in nos.getFeatures():  # como uma rede de verdade: terreno e um consumo pequeno em cada nó
    nos.changeAttributeValue(f.id(), i_cota, 800.0)
    nos.changeAttributeValue(f.id(), i_dem, 0.02)
nos.endEditCommand()
i_cv = val.fields().indexOf("cota")
for f in val.getFeatures():
    val.changeAttributeValue(f.id(), i_cv, 800.0)
for lyr in n.camadas_rede():
    if lyr.isEditable():
        checar(lyr.commitChanges(), f"salvou {lyr.name()}")
t0 = time.perf_counter()
dados = motor.rodar("validar", n.cadastro())
erros = [i["msg"] for i in dados.get("itens", []) if i["nivel"] == "ERRO"]
checar(dados.get("ok") and not erros, f"rede importada válida para o EPANET ({time.perf_counter() - t0:.1f} s): {erros[:4]}")
dados = motor.rodar("simular", n.cadastro())
checar(dados.get("ok"), f"e simula: {len(dados.get('nos', {}))} nós no resultado "
       f"{[i['msg'] for i in dados.get('itens', []) if i['nivel'] == 'ERRO'][:3]}")

j_.fechar_projeto(False)
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
