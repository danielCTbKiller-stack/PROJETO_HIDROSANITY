"""Teste do plugin GWATER sem abrir a janela do QGIS (interface simulada).

Uso:  "C:\\Program Files\\QGIS 3.44.14\\bin\\python-qgis-ltr.bat" teste_plugin.py
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.gui import QgsMapCanvas  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow, QMessageBox  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGINS = os.path.join(os.environ["APPDATA"], "QGIS", "QGIS3", "profiles", "default", "python", "plugins")
sys.path.insert(0, PLUGINS)

app = QgsApplication([], True)
app.initQgis()


class Barra:
    def pushMessage(self, titulo, texto, level=None, duration=None):
        print(f"    [barra] {texto}")


class IfaceFalsa:
    def __init__(self):
        self.janela, self.canvas = QMainWindow(), QgsMapCanvas()

    def mainWindow(self): return self.janela
    def mapCanvas(self): return self.canvas
    def messageBar(self): return Barra()
    def addToolBar(self, nome): return self.janela.addToolBar(nome)
    def addPluginToMenu(self, *a): pass
    def removePluginMenu(self, *a): pass
    def addDockWidget(self, area, w): self.janela.addDockWidget(area, w)
    def removeDockWidget(self, w): self.janela.removeDockWidget(w)
    def setActiveLayer(self, l): pass


import gwater  # noqa: E402

plugin = gwater.classFactory(IfaceFalsa())
plugin.initGui()
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


for projeto in ("GWATER_cadastro.qgz", "GWATER_teste_importado.qgz"):
    print(f"\n== {projeto}")
    QgsProject.instance().read(os.path.join(RAIZ, "cadastro", projeto))
    checar(plugin.cadastro() is not None, f"cadastro detectado: {os.path.basename(plugin.cadastro() or '')}")

    plugin.validar()
    checar("Rede válida" in plugin.dock.status.text(), "validar: " + plugin.dock.status.text())

    plugin.simular()
    checar(plugin.res is not None, "simular: " + plugin.dock.status.text()[:90])
    r = plugin.res
    checar(r.nos.featureCount() > 0 and r.tr.featureCount() > 0,
           f"camadas de resultado: {r.nos.featureCount()} nós, {r.tr.featureCount()} trechos")
    k = plugin.dock.slider.value()
    checar(k == r.pior_momento(), f"abre no pior momento (passo {k})")
    # o valor no mapa bate com o motor?
    f = next(r.nos.getFeatures())
    rid = dict(r.fid_nos)[f.id()]
    checar(abs(f["p"] - r.d["nos"][rid]["p"][k]) < 1e-6, f"pressão no mapa = motor ({f['id']}: {f['p']:.2f} mca)")
    plugin.dock.slider.setValue(0)
    f = r.nos.getFeature(f.id())
    checar(abs(f["p"] - r.d["nos"][rid]["p"][0]) < 1e-6, f"linha do tempo atualiza o mapa (00:00 -> {f['p']:.2f} mca)")
    print("  resumo:", plugin.dock.resumo.text().replace("<br>", " | ")[:400])

# --- edição pendente: o plugin pergunta e salva antes de simular
print("\n== edição pendente")
QgsProject.instance().read(os.path.join(RAIZ, "cadastro", "GWATER_teste_importado.qgz"))
tr = plugin.camada("trecho")
tr.startEditing()
f0 = next(tr.getFeatures())
fid, dn_original = f0.id(), f0["diametro_nominal"]
tr.changeAttributeValue(fid, tr.fields().indexOf("diametro_nominal"), None)  # apaga o diâmetro
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)  # "Sim, salvar"
plugin.validar()
txt = plugin.dock.status.text()
checar("erro" in txt and not tr.isModified(), "salvou a edição e a validação acusou o diâmetro vazio")
item = plugin.dock.tabela.item(0, 0)
checar(item is not None and item.data(256)[0] == "trecho", f"problema aponta a feição {item.data(256)}")
plugin.dock._ir_ate(0, 0)
checar(tr.selectedFeatureCount() == 1, "clique duplo seleciona o trecho com problema")
tr.startEditing()  # desfaz o estrago no cadastro de teste
tr.changeAttributeValue(fid, tr.fields().indexOf("diametro_nominal"), dn_original)
tr.commitChanges()

plugin.unload()
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
app.exitQgis()
sys.exit(1 if falhas else 0)
