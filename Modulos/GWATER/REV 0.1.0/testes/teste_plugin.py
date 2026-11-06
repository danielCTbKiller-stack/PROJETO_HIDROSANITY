"""Teste do plugin GWATER sem abrir a janela do QGIS (interface simulada).

1. menu, barras e Central: todo botão existe, tem ícone e explicação;
2. cadastros de exemplo: validar, simular, linha do tempo, edição pendente;
3. rede desenhada do zero, como um usuário faria: novo cadastro, captação, tubulações com
   nós automáticos, tubulação que encosta no meio de outra, válvula sobre tubulação,
   reservatório sobre nó, nó arrastado, cotas de um MDT, demanda distribuída, salvar,
   validar, simular e exportar o .inp;
4. importação de shapefile pelo botão.

Uso:  "C:\\Program Files\\QGIS 3.44.14\\bin\\python-qgis-ltr.bat" teste_plugin.py
"""
import os
import shutil
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from qgis.core import (  # noqa: E402
    Qgis, QgsApplication, QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer, QgsVectorLayerUtils,
)
from qgis.gui import QgsMapCanvas  # noqa: E402
from qgis.PyQt.QtWidgets import QFileDialog, QMainWindow, QMessageBox  # noqa: E402

# GWATER_RAIZ: roda sobre outra cópia (ex.: o cadastro de exemplo tirado do git, se o seu foi redesenhado)
RAIZ = os.environ.get("GWATER_RAIZ") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSAO = f"QGIS{Qgis.QGIS_VERSION_INT // 10000}"  # QGIS3 ou QGIS4: cada um tem a própria pasta de plugins
print("Testando no", Qgis.QGIS_VERSION)
PLUGINS = os.path.join(os.environ["APPDATA"], "QGIS", VERSAO, "profiles", "default", "python", "plugins")
sys.path.insert(0, PLUGINS)

app = QgsApplication([], True)
app.initQgis()


class Barra:
    def pushMessage(self, titulo, texto, level=None, duration=None):
        print(f"    [barra] {texto}")


class Ferramenta:
    def __init__(self, nome):
        self.nome = nome

    def trigger(self):
        print(f"    [qgis] ferramenta ativada: {self.nome}")


class IfaceFalsa:
    def __init__(self):
        self.janela, self.canvas = QMainWindow(), QgsMapCanvas()
        self.ajuda = self.janela.menuBar().addMenu("Ajuda")

    def mainWindow(self): return self.janela
    def mapCanvas(self): return self.canvas
    def messageBar(self): return Barra()
    def helpMenu(self): return self.ajuda
    def addToolBar(self, nome): return self.janela.addToolBar(nome)
    def addDockWidget(self, area, w): self.janela.addDockWidget(area, w)
    def removeDockWidget(self, w): self.janela.removeDockWidget(w)
    def setActiveLayer(self, l): self.ativa = l
    def actionAddFeature(self): return Ferramenta("adicionar feição")
    def actionVertexTool(self): return Ferramenta("vértices")
    def actionIdentify(self): return Ferramenta("identificar")

    def newProject(self, perguntar=False):
        QgsProject.instance().clear()
        return True

    def addProject(self, arq):
        return QgsProject.instance().read(arq)


import gwater  # noqa: E402
from gwater import acoes, ferramentas  # noqa: E402

iface = IfaceFalsa()
plugin = gwater.classFactory(iface)
plugin.initGui()
falhas = []
TMP = tempfile.mkdtemp(prefix="gwater_teste_plugin_")


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# ================================================================ 1) interface
print("\n== menu, barras e Central")
menu = [m for m in iface.janela.menuBar().actions() if m.text() == "&GWATER"]
checar(len(menu) == 1, "menu GWATER na barra de menus")
nomes_menu = [a.text() for a in menu[0].menu().actions() if a.text()]
checar(all(t in nomes_menu for _, t, _, _ in acoes.GRUPOS[:-1]) and "Central GWATER" in nomes_menu,
       f"submenus: {nomes_menu}")
barras = [b.windowTitle() for b in plugin.barras]
checar(barras == ["GWATER · Desenho", "GWATER · Modelo"], f"barras de ferramentas: {barras}")
todas = acoes.todas()
sem_explicacao = [k for k, a in plugin.qacoes.items() if len(a.statusTip()) < 40 or a.icon().isNull()]
checar(not sem_explicacao, f"{len(todas)} botões, todos com ícone e explicação {sem_explicacao or ''}")
checar(set(plugin.dock.botoes) == set(todas) - {"central"}, f"Central tem os {len(plugin.dock.botoes)} botões")
guia = ferramentas.html_guia()
checar(all(t in guia for t, *_ in todas.values() if t != "Central GWATER"), "guia explica todos os botões")

# ================================================================ 2) cadastros de exemplo
for projeto in ("GWATER_cadastro.qgz", "GWATER_teste_importado.qgz"):
    print(f"\n== {projeto}")
    QgsProject.instance().read(os.path.join(RAIZ, "cadastro", projeto))
    checar(plugin.cadastro() is not None, f"cadastro detectado: {os.path.basename(plugin.cadastro() or '')}")
    checar(len(plugin.topologia.camadas) == 6, "desenho automático ligado às 6 camadas da rede")

    plugin.executar("validar")
    checar("Rede válida" in plugin.dock.status.text(), "validar: " + plugin.dock.status.text())

    plugin.executar("simular")
    checar(plugin.res is not None, "simular: " + plugin.dock.status.text()[:90])
    r = plugin.res
    checar(r.nos.featureCount() > 0 and r.tr.featureCount() > 0,
           f"camadas de resultado: {r.nos.featureCount()} nós, {r.tr.featureCount()} trechos")
    k = plugin.dock.slider.value()
    checar(k == r.pior_momento(), f"abre no pior momento (passo {k})")
    f = next(r.nos.getFeatures())
    rid = dict(r.fid_nos)[f.id()]
    checar(abs(f["p"] - r.d["nos"][rid]["p"][k]) < 1e-6, f"pressão no mapa = motor ({f['id']}: {f['p']:.2f} mca)")
    plugin.dock.slider.setValue(0)
    f = r.nos.getFeature(f.id())
    checar(abs(f["p"] - r.d["nos"][rid]["p"][0]) < 1e-6, f"linha do tempo atualiza o mapa (00:00 -> {f['p']:.2f} mca)")
    plugin.executar("limpar")
    checar(QgsProject.instance().layerTreeRoot().findGroup("Resultados GWATER") is None, "Limpar resultados")

# --- cores dos resultados: variável dos tubos e faixas escolhidas pelo usuário
print("\n== faixas e cores dos resultados")
from gwater import resultados as rs  # noqa: E402
from gwater.faixas import JanelaFaixas  # noqa: E402

QgsProject.instance().read(os.path.join(RAIZ, "cadastro", "GWATER_cadastro.qgz"))
plugin.executar("simular")
r = plugin.res
checar(r.tr.renderer().classAttribute() == "v" and "Velocidade" in r.tr.name(), f"padrão: tubos por velocidade ({r.tr.name()})")
plugin.dock.cor_tubos.setCurrentIndex(1)  # perda de carga
checar(r.tr.renderer().classAttribute() == "perda_m_km" and r.tr.name() == "Perda de carga nos trechos (m/km)",
       f"tubos por perda de carga: {r.tr.name()}")
plugin.dock.slider.setValue(40)
hl = [f["perda_m_km"] for f in r.tr.getFeatures()]
checar(min(hl) >= 0 and max(hl) > 0, f"perda de carga no mapa (10h): até {max(hl):.2f} m/km, sem sinal")
rs.salvar_faixas("hl", [[None, 0.5, "#111111", ""], [0.5, 3, "#22aa22", "boa"], [3, None, "#ff0000", ""]])
r.estilizar()
fx = r.tr.renderer().ranges()
checar(len(fx) == 3 and fx[1].symbol().color().name() == "#22aa22" and fx[1].label() == "boa"
       and fx[0].label() == "< 0,5 m/km" and fx[2].label() == "> 3 m/km",
       f"faixas do usuário: {[x.label() for x in fx]}")
rs.salvar_faixas("p", [[None, 15, "#ff0000", ""], [15, 45, "#00ff00", ""], [45, None, "#0000ff", ""]])
r.estilizar()
regras = [x.filterExpression() for x in r.nos.renderer().rootRule().children()]
checar(any('"p" >= 15' in x and '"p" < 45' in x for x in regras), "pressão nos nós com as faixas do usuário (15 a 45 mca)")
plugin.dock.cor_tubos.setCurrentIndex(2)
checar(r.tr.renderer().classAttribute() == "q_abs" and all(f["q_abs"] >= 0 for f in r.tr.getFeatures()),
       "tubos por vazão (valor absoluto)")
jf = JanelaFaixas(None, "v")
from qgis.PyQt.QtGui import QColor  # noqa: E402
jf.tab.cellWidget(1, 2).setColor(QColor("#123456"))
jf.tab.cellWidget(1, 1).setText("0,8")
jf._aplicar()
checar(rs.faixas("v")[1][2] == "#123456" and rs.faixas("v")[1][1] == 0.8, f"janela salva cor e limite: {rs.faixas('v')[1]}")
jf.tab.cellWidget(0, 1).setText("5")
jf.tab.cellWidget(0, 0).setText("9")
jf._aplicar()
checar("maior que o" in jf.msg.text(), "janela recusa faixa com 'Até' menor que 'De'")
jf = None
plugin.executar("limpar")

# --- edição pendente: o plugin pergunta e salva antes de simular
print("\n== edição pendente")
QgsProject.instance().read(os.path.join(RAIZ, "cadastro", "GWATER_teste_importado.qgz"))
tr = plugin.camada("trecho")
tr.startEditing()
f0 = next(tr.getFeatures())
fid, dn_original = f0.id(), f0["diametro_nominal"]
plugin.topologia.ativo = False  # edição de atributo pura
tr.changeAttributeValue(fid, tr.fields().indexOf("diametro_nominal"), None)  # apaga o diâmetro
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)  # "Sim, salvar"
plugin.validar()
txt = plugin.dock.status.text()
checar("erro" in txt and not tr.isModified(), "salvou a edição e a validação acusou o diâmetro vazio")
item = plugin.dock.tabela.item(0, 0)
checar(item is not None and item.data(256)[0] == "trecho", f"problema aponta a feição {item.data(256)}")
plugin.dock._ir_ate(0, 0)
checar(tr.selectedFeatureCount() == 1, "clique duplo seleciona o trecho com problema")
tr.changeAttributeValue(fid, tr.fields().indexOf("diametro_nominal"), dn_original)  # desfaz
tr.commitChanges()
plugin.topologia.ativo = True

# ================================================================ 3) rede desenhada do zero
print("\n== novo cadastro e desenho estilo WaterGEMS")
gpkg_novo = os.path.join(TMP, "bairro_teste.gpkg")
ferramentas.janela_novo = lambda pai: {"gpkg": gpkg_novo, "crs": "EPSG:31983"}
plugin.executar("novo")
checar(plugin.cadastro() and os.path.samefile(plugin.cadastro(), gpkg_novo), "Novo cadastro criado e aberto")
checar(plugin.camada("trecho").featureCount() == 0 and plugin.camada("padrao_consumo").featureCount() == 96,
       "cadastro vazio, com as tabelas do modelo")
checar(len(plugin.topologia.camadas) == 6, "desenho automático ligado ao cadastro novo")

E0, N0 = 333000.0, 7395000.0
P = lambda x, y: QgsPointXY(E0 + x, N0 + y)


def desenhar(nome, geom, **attrs):
    """O que a ferramenta 'adicionar feição' do QGIS faz: valores padrão do formulário + addFeature."""
    lyr = plugin.camada(nome)
    f = QgsVectorLayerUtils.createFeature(lyr, geom, {}, lyr.createExpressionContext())
    for k, v in attrs.items():
        f[k] = v
    lyr.addFeature(f)
    app.processEvents()  # o GWATER trata depois que a ferramenta termina
    return f


def feicao(nome, cod):
    return next((f for f in plugin.camada(nome).getFeatures() if f["id"] == cod), None)


def ids(nome):
    return sorted(str(f["id"]) for f in plugin.camada(nome).getFeatures())


# MDT sintético: terreno caindo 1 m a cada 20 m para o norte, cota 120 na origem
from osgeo import gdal, osr  # noqa: E402

mdt_arq = os.path.join(TMP, "mdt.tif")
ds = gdal.GetDriverByName("GTiff").Create(mdt_arq, 120, 120, 1, gdal.GDT_Float32)
ds.SetGeoTransform([E0 - 100, 10, 0, N0 + 1100, 0, -10])
srs = osr.SpatialReference()
srs.ImportFromEPSG(31983)
ds.SetProjection(srs.ExportToWkt())
import numpy as np  # noqa: E402
yy = np.arange(120)[:, None] * -10 + 1100 - 5
ds.GetRasterBand(1).WriteArray(np.repeat(120 - yy / 20.0, 120, axis=1).astype("float32"))
ds = None
mdt = QgsRasterLayer(mdt_arq, "MDT")
QgsProject.instance().addMapLayer(mdt)

plugin.executar("captacao")
checar(plugin.camada("captacao").isEditable() and plugin.camada("no_juncao").isEditable(),
       "botão de desenho liga a edição da rede e o encaixe")
cfg = QgsProject.instance().snappingConfig()
checar(cfg.enabled() and QgsProject.instance().topologicalEditing(), "encaixe e edição topológica ligados")

desenhar("captacao", QgsGeometry.fromPointXY(P(0, 0)), carga_hidraulica=150.0)
checar(ids("captacao") == ["C-0001"], f"captação: {ids('captacao')}")

# tubulação 1: sai da captação e termina solta -> nó novo na ponta
plugin.executar("tubulacao")
desenhar("trecho", QgsGeometry.fromPolylineXY([P(0, 0), P(500, 0)]))
t1 = feicao("trecho", "T-0001")
checar(t1 and t1["no_inicial"] == "C-0001" and t1["no_final"] == "N-0001",
       f"tubulação T-0001 liga C-0001 -> {t1['no_final'] if t1 else '?'} (nó criado sozinho)")
checar(t1 and abs(t1["comprimento"] - 500) < 0.01 and t1["diametro_nominal"] == 100 and t1["material"] == "PVC PBA"
       and t1["rugosidade_hw"] == 140, "comprimento, DN e material do protótipo, rugosidade pelo material")

# tubulação 2 com uma curva: sai de N-0001 e termina solta
desenhar("trecho", QgsGeometry.fromPolylineXY([P(500, 0), P(500, 400), P(520, 600)]))
t2 = feicao("trecho", "T-0002")
checar(t2 and t2["no_inicial"] == "N-0001" and t2["no_final"] == "N-0002", "T-0002: N-0001 -> N-0002")

# tubulação 3 termina no meio da T-0001 -> T-0001 é dividida e ligada num nó novo
desenhar("trecho", QgsGeometry.fromPolylineXY([P(250, 300), P(250, 0)]))
n_meio = feicao("no_juncao", "N-0004")
checar(n_meio is not None and n_meio.geometry().asPoint().distance(P(250, 0)) < 1e-6,
       "nó N-0004 criado onde a tubulação encostou na T-0001")
t1 = feicao("trecho", "T-0001")
partes = [f for f in plugin.camada("trecho").getFeatures() if f["no_inicial"] == "N-0004" and f["no_final"] == "N-0001"]
checar(t1["no_final"] == "N-0004" and abs(t1["comprimento"] - 250) < 0.01 and len(partes) == 1
       and abs(partes[0]["comprimento"] - 250) < 0.01,
       f"T-0001 dividida: C-0001 -> N-0004 (250 m) e {partes[0]['id'] if partes else '?'}: N-0004 -> N-0001 (250 m)")
t3 = next(f for f in plugin.camada("trecho").getFeatures() if f["no_final"] == "N-0004" and f["id"] != "T-0001")
checar(t3["no_inicial"] == "N-0003", f"{t3['id']}: N-0003 -> N-0004")

# válvula sobre a T-0002 (em cima do vértice da curva) -> tubo dividido, válvula no meio
plugin.executar("valvula")
desenhar("valvula", QgsGeometry.fromPointXY(P(500, 200)), tipo="PRV", ajuste=25.0, diametro=100.0)
t2 = feicao("trecho", "T-0002")
jus = [f for f in plugin.camada("trecho").getFeatures() if f["no_inicial"] == "V-0001"]
checar(t2["no_final"] == "V-0001" and abs(t2["comprimento"] - 200) < 0.01 and len(jus) == 1
       and jus[0]["no_final"] == "N-0002",
       f"válvula V-0001 dividiu a T-0002: montante T-0002 (200 m), jusante {jus[0]['id'] if jus else '?'}")

# reservatório sobre o nó N-0002 -> o nó vira reservatório
plugin.executar("reservatorio")
desenhar("reservatorio", QgsGeometry.fromPointXY(P(520, 600)), cota_fundo=95.0, nivel_ini=2.0, nivel_min=0.5,
         nivel_max=4.0, diametro=12.0)
checar("N-0002" not in ids("no_juncao") and jus[0].id() and
       plugin.camada("trecho").getFeature(jus[0].id())["no_final"] == "R-0001",
       "reservatório R-0001 substituiu o nó N-0002 e a tubulação passou a ligar nele")

# nó arrastado (ferramenta Mover feição): a tubulação acompanha
plugin.executar("mover")
nos = plugin.camada("no_juncao")
n4 = feicao("no_juncao", "N-0003")
nos.changeGeometry(n4.id(), QgsGeometry.fromPointXY(P(250, 400)))
app.processEvents()
t3 = plugin.camada("trecho").getFeature(t3.id())
checar(abs(t3["comprimento"] - 400) < 0.01 and t3.geometry().asPolyline()[0].distance(P(250, 400)) < 1e-6,
       f"N-0003 movido 100 m: {t3['id']} acompanhou (300 -> {t3['comprimento']:.0f} m)")

# cotas do MDT para tudo e cota automática para os próximos nós
feitos, fora = ferramentas.preencher_cotas(plugin, mdt, todas=False)
plugin.topologia.mdt = mdt
c1 = feicao("no_juncao", "N-0001")["cota"]
checar(feitos == 6 and not fora and abs(c1 - 120) < 0.6, f"cotas do MDT em tudo (nós, válvula, reservatório, captação): {feitos} preenchidas (N-0001 = {c1} m)")
desenhar("trecho", QgsGeometry.fromPolylineXY([P(250, 400), P(250, 700)]))
n5 = feicao("no_juncao", "N-0005")
checar(n5 is not None and abs(n5["cota"] - 85) < 0.6, f"nó novo já nasce com a cota do MDT ({n5['cota'] if n5 else '?'} m)")
desenhar("no_juncao", QgsGeometry.fromPointXY(P(250, 550)))
n6 = feicao("no_juncao", "N-0006")
partes = [f for f in plugin.camada("trecho").getFeatures() if "N-0006" in (f["no_inicial"], f["no_final"])]
checar(n6 is not None and len(partes) == 2 and abs(sum(f["comprimento"] for f in partes) - 300) < 0.01,
       "nó inserido sobre a tubulação divide em duas (150 m + 150 m)")

# demanda: 6 L/s pela rede, proporcional ao comprimento
n, q = ferramentas.distribuir_demanda(plugin, 6.0, "todos", None, "comprimento", "PAD_CONS")
soma = sum(f["demanda_base"] or 0 for f in nos.getFeatures())
checar(abs(soma - 6.0) < 0.001, f"demanda distribuída entre {n} nós: soma {soma:.3f} L/s")

todos_ids = ids("captacao") + ids("reservatorio") + ids("valvula") + ids("no_juncao")
checar(len(todos_ids) == len(set(todos_ids)) and len(ids("trecho")) == len(set(ids("trecho"))),
       f"códigos únicos: {len(todos_ids)} elementos, {len(ids('trecho'))} tubulações")

plugin.executar("salvar")
checar(not any(l.isModified() for l in plugin.topologia.camadas.values()), "Salvar edições gravou todas as camadas")
plugin.executar("validar")
checar("Rede válida" in plugin.dock.status.text(), "rede desenhada é válida: " + plugin.dock.status.text()[:80])
plugin.executar("simular")
checar(plugin.res is not None, "rede desenhada simula no EPANET: " + plugin.dock.status.text()[:70])
if plugin.res:
    pv = plugin.res.d["nos"].get("V-0001__J", {}).get("p", [None])[0]
    print(f"    pressão a jusante da VRP V-0001: {pv} mca")

inp = os.path.join(TMP, "exportado.inp")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (inp, ""))
plugin.executar("exportar")
checar(os.path.exists(inp) and "[VALVES]" in open(inp, encoding="utf-8").read(), "Exportar .inp")

# ================================================================ 3b) curvas de bomba
print("\n== curvas de bomba")
from gwater import curvas  # noqa: E402

checar(curvas.problemas([(10, 30)]) == [] and curvas.problemas([(0, 60), (10, 45), (15, 30)]) == [],
       "curvas de 1 e 3 pontos válidas")
checar(curvas.problemas([(5, 40), (10, 30)]) and curvas.problemas([(0, 60), (10, 65), (15, 30)]),
       "curva de 2 pontos e altura subindo são recusadas")
j = curvas.JanelaCurvas(None, plugin)
j._nova()
j.nome.setText("BOMBA_TESTE")
j._renomear()
j._escrever([(0.0, 60.0), (8.0, 45.0), (12.0, 30.0)])
j.salvar()
lidas = curvas.ler(plugin.camada("curva"))
checar(lidas.get("BOMBA_TESTE") == [(0.0, 60.0), (8.0, 45.0), (12.0, 30.0)], f"curva salva na tabela: {sorted(lidas)}")
cfg = plugin.camada("bomba").editorWidgetSetup(plugin.camada("bomba").fields().indexOf("curva"))
checar(cfg.type() == "ValueMap" and any("BOMBA_TESTE" in d for d in cfg.config()["map"]),
       "campo curva da bomba virou lista com as curvas")
plugin.executar("bomba")
desenhar("bomba", QgsGeometry.fromPointXY(P(250, 100)), curva="BOMBA_TESTE")
b1 = feicao("bomba", "B-0001")
checar(b1 is not None and b1["cota"] is not None and len([f for f in plugin.camada("trecho").getFeatures()
                                                          if "B-0001" in (f["no_inicial"], f["no_final"])]) == 2,
       "bomba sobre a tubulação: dividida, com cota do MDT e a curva da lista")
plugin.executar("salvar")
plugin.executar("validar")
checar("Rede válida" in plugin.dock.status.text(), "rede com a bomba e a curva nova é válida")

# ================================================================ 3c) dividir tubulações com tolerância
print("\n== dividir tubulações (tolerância)")
plugin.topologia.ativo = False  # simula dados soltos (vindos de um arquivo, sem ligação automática)
plugin.camada("trecho").startEditing()
solta = desenhar("trecho", QgsGeometry.fromPolylineXY([P(250.3, 700.2), P(400, 700)]))       # a 0,36 m do N-0005
em_t = desenhar("trecho", QgsGeometry.fromPolylineXY([P(400, 625), P(250.2, 625)]))          # a 0,2 m do meio da T-0007
plugin.topologia.ativo = True
r = plugin.topologia.dividir_rede(0.5, fids=[solta.id(), em_t.id()])
checar(r["encaixadas"] >= 1 and r["divididas"] >= 1 and r["nos_criados"] >= 1,
       f"tolerância 0,5 m: {r}")
f_solta = plugin.camada("trecho").getFeature(solta.id())
checar(f_solta["no_inicial"] == "N-0005", f"ponta a 0,36 m encaixou no N-0005 ({f_solta['no_inicial']})")
r0 = plugin.topologia.dividir_rede(0.1, fids=None)
checar(r0 == {"encaixadas": 0, "divididas": 0, "nos_criados": 0}, f"rodar de novo não muda nada: {r0}")
plugin.executar("salvar")

# ================================================================ 3d) ModelBuilder
print("\n== ModelBuilder (importar elementos com de-para)")
from gwater.modelbuilder import ModelBuilder  # noqa: E402

shp = os.path.join(RAIZ, "testes", "shp_teste", "rede_agua.shp")
if os.path.exists(shp):
    n_tr0, n_no0 = plugin.camada("trecho").featureCount(), plugin.camada("no_juncao").featureCount()
    antes = {f.id() for f in plugin.camada("trecho").getFeatures()}
    mb = ModelBuilder(None, plugin)
    mb.tipo.setCurrentIndex(0)  # tubulações
    mb._abrir_arquivo(shp)
    checar(mb.origem() is not None, f"origem: {mb.info.text()[:80]}")
    mb._ir(1)
    m = mb.mapa()
    checar(m.get("id") == "COD" and m.get("diametro_nominal") == "DN" and m.get("material") == "MAT"
           and m.get("ano_instalacao") == "ANO", f"de-para automático: {m}")
    mb._ir(2)
    trad = mb.traducoes()
    checar(trad.get("material", {}).get("FOFO") == "Ferro fundido dúctil" and trad["material"].get("PVC") == "PVC PBA",
           f"valores traduzidos: {trad.get('material')}")
    mb._ir(3)
    mb.tol.setValue(0.5)
    mb._executar()
    r = mb.resultado
    tr = plugin.camada("trecho")
    importadas = [f for f in tr.getFeatures() if f.id() not in antes]
    print(f"    resultado: {r}")
    checar(r and r["importados"] > 0 and r["nos_criados"] > 0, "tubulações importadas e nós criados nas pontas")
    sem_no = [f["id"] for f in importadas if not f["no_inicial"] or not f["no_final"]]
    checar(not sem_no, f"toda tubulação tem nó inicial e final ({len(sem_no)} sem)")
    soltas = [f["id"] for f in importadas
              if not plugin.topologia.elemento_em(f.geometry().asPolyline()[0])
              or not plugin.topologia.elemento_em(f.geometry().asPolyline()[-1])]
    checar(not soltas, f"toda ponta está sobre um elemento ({len(soltas)} soltas)")
    checar(tr.featureCount() - n_tr0 == 35 and plugin.camada("no_juncao").featureCount() - n_no0 == 24,
           f"mesma rede que o importador do motor: {tr.featureCount() - n_tr0} tubulações e "
           f"{plugin.camada('no_juncao').featureCount() - n_no0} nós (motor: 35 e 24)")
    mats = {f["material"] for f in tr.getFeatures() if f["observacao"] != "x"}
    checar("Ferro fundido dúctil" in mats and all(f["rugosidade_hw"] for f in tr.getFeatures()),
           "material traduzido e rugosidade pelo material")

    # válvula de um arquivo de pontos, caindo no meio de uma tubulação importada
    from qgis.core import QgsFeature, QgsField, QgsVectorLayer  # noqa: E402
    alvo = next(f for f in tr.getFeatures() if f.geometry().length() > 20 and f["id"] not in ("T-0001",))
    meio = alvo.geometry().interpolate(alvo.geometry().length() / 2).asPoint()
    pts = QgsVectorLayer(f"Point?crs={tr.crs().authid()}", "valvulas_campo", "memory")
    from qgis.PyQt.QtCore import QVariant  # noqa: E402
    pts.dataProvider().addAttributes([QgsField("TIPO", QVariant.String), QgsField("SET", QVariant.Double),
                                      QgsField("DN", QVariant.String)])
    pts.updateFields()
    fv = QgsFeature(pts.fields())
    fv.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(meio.x() + 0.2, meio.y())))  # 0,2 m fora do eixo
    fv.setAttributes(["VRP", 20.0, "DN100"])
    pts.dataProvider().addFeatures([fv])
    mb = ModelBuilder(None, plugin)
    mb.tipo.setCurrentIndex(2)  # válvulas
    mb.arquivo = pts
    mb._mudou_origem()
    mb._ir(1)
    checar(mb.mapa().get("tipo") == "TIPO" and mb.mapa().get("ajuste") == "SET" and mb.mapa().get("diametro") == "DN",
           f"de-para da válvula: {mb.mapa()}")
    mb._ir(2)
    checar(mb.traducoes().get("tipo", {}).get("VRP") == "PRV", "VRP traduzida para PRV")
    mb._ir(3)
    mb._executar()
    v = [f for f in plugin.camada("valvula").getFeatures() if f["tipo"] == "PRV" and f["ajuste"] == 20]
    lig = [f for f in tr.getFeatures() if v and v[0]["id"] in (f["no_inicial"], f["no_final"])]
    checar(len(v) == 1 and len(lig) == 2 and v[0]["diametro"] == 100,
           f"válvula importada dividiu a tubulação {alvo['id']} ({mb.resultado})")
    plugin.executar("salvar")
    checar(not any(l.isModified() for l in plugin.topologia.camadas.values()), "importação salva no cadastro")
else:
    print("  (pulado: rode teste_importacao.py antes para gerar o shapefile de teste)")

# ================================================================ 3e) cotas como o TRex: curvas de nível e pontos
print("\n== cotas por curvas de nível e pontos cotados (TRex)")
from gwater import cotas  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature as QF, QgsField as QFd,
    QgsVectorFileWriter, QgsVectorLayer as QVL,
)
from qgis.PyQt.QtCore import QVariant as QV  # noqa: E402

crs_cad = plugin.camada("trecho").crs()
graus = QgsCoordinateReferenceSystem("EPSG:4674")  # SIRGAS 2000 geográfico, como os arquivos estaduais
para_graus = QgsCoordinateTransform(crs_cad, graus, QgsProject.instance())
curvas_mem = QVL("LineString?crs=EPSG:4674", "curvas_sp", "memory")
curvas_mem.dataProvider().addAttributes([QFd("COTA", QV.Double), QFd("TIPO", QV.String)])
curvas_mem.updateFields()
feats = []
for kk in range(0, 12):  # curva a cada 5 m: mesmo terreno do MDT de teste (cai 1 m a cada 20 m)
    g = QgsGeometry.fromPolylineXY([P(x, kk * 100) for x in range(-100, 1301, 50)])
    g.transform(para_graus)
    fc = QF(curvas_mem.fields())
    fc.setGeometry(g)
    fc.setAttributes([120.0 - 5 * kk, "mestra" if kk % 2 == 0 else "intermediaria"])
    feats.append(fc)
curvas_mem.dataProvider().addFeatures(feats)
arq_curvas = os.path.join(TMP, "curvas_estado.gpkg")
for nome_lyr, lyr_mem in (("curvas_sp", curvas_mem), ("limites", QVL("Polygon?crs=EPSG:4674", "limites", "memory"))):
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName, opt.layerName = "GPKG", nome_lyr
    opt.actionOnExistingFile = (QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer if os.path.exists(arq_curvas)
                                else QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile)
    QgsVectorFileWriter.writeAsVectorFormatV3(lyr_mem, arq_curvas, QgsProject.instance().transformContext(), opt)
checar(sorted(cotas.subcamadas(arq_curvas)) == ["curvas_sp", "limites"], f"camadas do gpkg: {cotas.subcamadas(arq_curvas)}")
lyr_curvas = cotas.abrir_arquivo(arq_curvas, "curvas_sp")
checar(lyr_curvas is not None and cotas.campo_cota(lyr_curvas) == "COTA", "abre a camada do arquivo e acha o campo COTA")
fonte_c = cotas.Fonte("curvas", lyr_curvas, crs_cad, "COTA")
checar(abs(fonte_c.cota(P(250, 250)) - 107.5) < 0.05 and abs(fonte_c.cota(P(600, 300)) - 105.0) < 0.05,
       f"entre curvas 110 e 105: {fonte_c.cota(P(250, 250))} m (esperado 107,5); sobre a curva 105: "
       f"{fonte_c.cota(P(600, 300))} m")
longe = cotas.Fonte("curvas", lyr_curvas, crs_cad, "COTA").cota(P(600, 3100))  # 2 km além da última curva
checar(longe is not None and 65 <= longe <= 70, f"sem raio de busca: 2 km longe das curvas ainda tem cota ({longe} m)")
dif = max(abs(fonte_c.cota(_ponto_q) - ferramentas_mdt) for _ponto_q, ferramentas_mdt in
          [(f.geometry().asPoint(), mdt.dataProvider().sample(f.geometry().asPoint(), 1)[0])
           for f in plugin.camada("no_juncao").getFeatures() if mdt.dataProvider().sample(f.geometry().asPoint(), 1)[1]])
checar(dif < 0.3, f"curvas de nível × MDT nos nós desenhados: diferença máx {dif:.2f} m (célula do MDT de 10 m)")
pts_mem = QVL("Point?crs=EPSG:4674", "pontos_cotados", "memory")
pts_mem.dataProvider().addAttributes([QFd("ELEV", QV.Double)])
pts_mem.updateFields()
feats = []
for xx in range(-100, 1301, 50):
    for yy in range(-100, 1101, 50):
        g = QgsGeometry.fromPointXY(P(xx, yy))
        g.transform(para_graus)
        fp = QF(pts_mem.fields())
        fp.setGeometry(g)
        fp.setAttributes([120.0 - yy / 20.0])
        feats.append(fp)
pts_mem.dataProvider().addFeatures(feats)
fonte_p = cotas.Fonte("pontos", pts_mem, crs_cad, cotas.campo_cota(pts_mem))
checar(abs(fonte_p.cota(P(275, 425)) - (120 - 425 / 20)) < 0.3, f"pontos cotados (inverso da distância): "
                                                                f"{fonte_p.cota(P(275, 425))} m (esperado {120 - 425 / 20})")
feitos, fora = cotas.preencher(plugin, fonte_c, todas=True, camadas=["valvula"])
n_val = len([f for f in plugin.camada("valvula").getFeatures() if fonte_c.cota(f.geometry().asPoint()) is not None])
checar(feitos == n_val, f"Aplicar em só Válvulas: {feitos} cota(s) (válvulas na região das curvas: {n_val})")
feitos, fora = cotas.preencher(plugin, fonte_c, todas=True)
checar(feitos >= 8 and not fora, f"Aplicar em tudo: {feitos} cota(s), {len(fora)} sem cota (sem raio: nenhum deve ficar sem)")
r1, c1 = feicao("reservatorio", "R-0001"), feicao("captacao", "C-0001")
checar(abs(r1["cota"] - 90.0) < 0.05 and abs(c1["cota"] - 120.0) < 0.05 and r1["cota_fundo"] == 95.0,
       f"cota do terreno também no reservatório ({r1['cota']} m, cota de fundo continua {r1['cota_fundo']}) "
       f"e na captação ({c1['cota']} m)")
antiga = QVL("Point?crs=EPSG:31983&field=id:string", "reservatorio_antigo", "memory")
checar(cotas.garantir_campo(antiga) and antiga.fields().indexOf("cota") >= 0, "cadastro antigo ganha o campo cota")
antiga.rollBack()
antiga = None
plugin.topologia.mdt = fonte_c
plugin.topologia.ativo = True
app.processEvents()  # no QGIS sempre há eventos entre salvar e desenhar (fim do modo "salvando")
plugin.camada("trecho").startEditing()
desenhar("trecho", QgsGeometry.fromPolylineXY([P(1000, 0), P(1000, 650)]))
novo = [f for f in plugin.camada("no_juncao").getFeatures() if f.geometry().asPoint().distance(P(1000, 650)) < 0.01]
checar(novo and abs(novo[0]["cota"] - 87.5) < 0.05, f"nó novo ganha cota pelas curvas: {novo[0]['cota'] if novo else '?'} m")
plugin.camada("trecho").rollBack()
for lyr in plugin.topologia.camadas.values():
    lyr.rollBack()
fonte_c = fonte_p = lyr_curvas = curvas_mem = pts_mem = None
plugin.topologia.mdt = None

# ================================================================ 4) importar shapefile pelo botão
print("\n== importar shapefile")
shp = os.path.join(RAIZ, "testes", "shp_teste", "rede_agua.shp")
if os.path.exists(shp):
    ferramentas.janela_importar = lambda pai: {
        "trechos": shp, "destino": os.path.join(TMP, "importado.gpkg"), "crs": "EPSG:31983",
        "campos": {"id": "COD", "diametro": "DN", "material": "MAT"}, "materiais": {"PVC": "PVC PBA"},
        "tolerancia_m": 0.5, "padrao": "PAD_CONS", "vazao_total_lps": 10.0}
    plugin.executar("importar")
    n_tr = plugin.camada("trecho").featureCount() if plugin.cadastro() else 0
    checar(plugin.cadastro() and "importado" in plugin.cadastro() and n_tr > 0,
           f"shapefile importado e aberto ({n_tr} tubulações)")
else:
    print("  (pulado: rode teste_importacao.py antes para gerar o shapefile de teste)")

# camadas e janelas criadas fora do projeto: liberar antes de fechar o QGIS (senão o QGIS 3 cai ao sair)
import gc  # noqa: E402
j = mb = pts = fv = alvo = None
gc.collect()
app.processEvents()
plugin.unload()
QgsProject.instance().clear()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
app.exitQgis()
sys.exit(1 if falhas else 0)
