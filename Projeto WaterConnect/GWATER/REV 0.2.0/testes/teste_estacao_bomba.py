"""Teste do ModelBuilder: polígono como estação de bomba (pump station do WaterGEMS) e ano de instalação vindo
de data (dd/mm/aaaa, aaaa-mm-dd e campo Date do shapefile).

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_estacao_bomba.py
"""
import os
import sys
import tempfile

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "app"))
from qgis.core import (  # noqa: E402
    QgsApplication, QgsCoordinateTransformContext, QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QVariant  # noqa: E402

app = QgsApplication([b"teste"], True)
app.initQgis()
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
from programa.janela import Janela  # noqa: E402
from gwater import motor  # noqa: E402
from gwater.modelbuilder import ano  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gwater_teste_eb_")
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


print("== leitura do ano", flush=True)
for bruto, esperado in (("15/03/1998", 1998), ("1998", 1998), ("1998-03-15", 1998), ("03/2004", 2004),
                        ("15/03/98", 1998), ("01-02-05", 2005), (1987, 1987), (QDate(2010, 5, 2), 2010),
                        ("2001-07-09T00:00:00", 2001), (None, None), ("", None)):
    checar(ano(bruto) == esperado, f"ano({bruto!r}) = {ano(bruto)}")

E0, N0 = 333000.0, 7390000.0
P = lambda x, y: QgsPointXY(E0 + x, N0 + y)  # noqa: E731
tubos = [(QgsGeometry.fromPolylineXY([P(0, 0), P(100, 0)]), ["T1", "15/03/1998"]),
         (QgsGeometry.fromPolylineXY([P(100, 0), P(200, 0)]), ["T2", "2004-06-30"]),
         (QgsGeometry.fromPolylineXY([P(200, 0), P(300, 0)]), ["T3", "1979"])]
arq_tubos = shp("rede", "LineString", [("COD", QVariant.String), ("DATA_INST", QVariant.String)], tubos)
quad = lambda x, y, r: QgsGeometry.fromPolygonXY([[P(x - r, y - r), P(x + r, y - r), P(x + r, y + r),  # noqa: E731
                                                     P(x - r, y + r), P(x - r, y - r)]])
arq_eeat = shp("eeat", "Polygon", [("NOME", QVariant.String), ("INICIO", QVariant.Date)],
               [(quad(150, 3, 12), ["EEAT-01", QDate(2012, 8, 20)]),   # sobre o meio do tubo T2
                (quad(100, -2, 8), ["EEAT-02", QDate(2015, 1, 1)])])   # com o nó entre T1 e T2 dentro

r = motor.rodar("novo", os.path.join(TMP, "rede.gpkg"), False, ["--crs=EPSG:31983"])
j = Janela()
j.abrir_projeto(r["qgz"])
for _ in range(10):
    app.processEvents()
n = j.nucleo

print("\n== ModelBuilder", flush=True)
from programa.modelbuilder_ui import ModelBuilderApp  # noqa: E402
dlg = ModelBuilderApp(j, n)
for arq in (arq_tubos, arq_eeat):
    dlg._por(QgsVectorLayer(arq, os.path.basename(arq), "ogr"), os.path.basename(arq))
checar([f["geo"] for f in dlg.fontes] == ["linha", "poligono"], f"geometrias: {[f['geo'] for f in dlg.fontes]}")
checar(dlg.tab_arq.item(1, 1).text() == "polígonos", f"tabela mostra: {dlg.tab_arq.item(1, 1).text()}")
checar(dlg.fontes[1]["combo"].currentData() == "estacao_bomba", f"polígono sugerido: {dlg.fontes[1]['combo'].currentData()}")
for k in (1, 2, 3):
    dlg._ir(k)
mapa = dlg.mapa(dlg.fontes[0])
checar(mapa.get("ano_instalacao") == "DATA_INST", f"coluna de data ligada no ano: {mapa}")
dlg._executar()
res = dlg.resultado
checar(res is not None, f"importou: {res and {k: v for k, v in res.items() if k != 'avisos'}}")
print("     avisos:", res and res["avisos"], flush=True)

tr, bo = n.camada("trecho"), n.camada("bomba")
anos = sorted(f["ano_instalacao"] for f in tr.getFeatures() if f["ano_instalacao"] not in (None, ""))
checar({1998, 2004, 1979} <= set(anos), f"anos das tubulações: {anos}")
checar(bo.featureCount() == 2, f"bombas criadas das estações: {bo.featureCount()}")
for f in bo.getFeatures():
    p = f.geometry().asPoint()
    checar(abs(p.y() - N0) < 0.01, f"bomba {f['id']} na tubulação (x={p.x() - E0:.1f}, y={p.y() - N0:.2f})")
    ligados = [t for t in tr.getFeatures() if f["id"] in (t["no_inicial"], t["no_final"])]
    checar(len(ligados) == 2, f"bomba {f['id']} entre 2 tubulações ({len(ligados)})")

print("\n" + ("TUDO OK" if not falhas else f"{len(falhas)} FALHA(S): " + "; ".join(falhas)), flush=True)
os._exit(1 if falhas else 0)
