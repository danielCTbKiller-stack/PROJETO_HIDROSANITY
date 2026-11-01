"""Teste de ponta a ponta do GWATER.exe (programa à parte), sem tela.

Abre uma cópia do cadastro de exemplo e:
  - clica em TODOS os botões da faixa de menus (as janelas são aceitas com os valores padrão);
  - desenha uma tubulação (a Topologia cria o nó da ponta) e desfaz;
  - calcula a rede, roda as análises do motor e confere os números;
  - abre tabelas, gráficos, perfis, consultas, relatórios (PDF e HTML), cenários e comparação;
  - grava uma edição e confere o histórico de alterações; arquivo compactado; excluir com as tubulações ligadas.

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_programa.py
"""
import os
import shutil
import sys
import tempfile
import traceback

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "app"))
try:
    from qgis.PyQt import QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass
from qgis.PyQt.QtCore import Qt  # noqa: E402
from qgis.PyQt.QtWidgets import (  # noqa: E402
    QApplication, QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox,
)

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsPointXY, QgsProject  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
TMP = tempfile.mkdtemp(prefix="gwater_teste_programa_")
for a in ("gwater_cadastro.gpkg", "GWATER_cadastro.qgz"):
    shutil.copyfile(os.path.join(RAIZ, "cadastro", a), os.path.join(TMP, a))
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# ---------------------------------------------------------------- janelas respondem sozinhas
QDialog.exec = lambda self: 1
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.about = staticmethod(lambda *a, **k: None)
QInputDialog.getText = staticmethod(lambda *a, **k: (k.get("text") or "Teste GWATER", True))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (a[3] if len(a) > 3 else 1.0, True))
QInputDialog.getItem = staticmethod(lambda *a, **k: ((a[3][0] if len(a) > 3 and a[3] else ""), True))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("\n".join(["1"] * 24), True))
SALVOS = []


def _salvar(pai, titulo, padrao="", filtro=""):
    ext = os.path.splitext(padrao)[1] or ".txt"
    arq = os.path.join(TMP, f"saida_{len(SALVOS)}{ext}")
    SALVOS.append(arq)
    return arq, filtro


QFileDialog.getSaveFileName = staticmethod(_salvar)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QMenu.exec = lambda self, *a, **k: None
os.startfile = lambda *a, **k: None

from programa import catalogo, tema  # noqa: E402
from programa.janela import Janela  # noqa: E402

app.setStyle("Fusion")
app.setPalette(tema.paleta())
app.setStyleSheet(tema.qss())
j = Janela()
j.resize(1600, 950)
j.show()
n = j.nucleo


def esperar(k=20):
    for _ in range(k):
        app.processEvents()


print("== abrir o exemplo")
j.abrir_projeto(os.path.join(TMP, "GWATER_cadastro.qgz"))
esperar()
checar(n.cadastro() and n.cadastro().endswith("gwater_cadastro.gpkg"), f"cadastro aberto: {n.cadastro()}")
checar(len(n.camadas_rede()) == 7, f"7 camadas da rede (com os consumidores): {[l.name() for l in n.camadas_rede()]}")
checar(j.centro.tabText(0).startswith("Mapa"), "aba do mapa no lugar da tela Início")

print("\n== calcular")
j.acionar("simular")
esperar()
checar(n.res is not None and len(n.res.horas) > 90, f"simulação de 24 h: {len(n.res.horas) if n.res else 0} passos")
checar(j.sl_hora.isEnabled(), "linha do tempo do mapa ligada")

print("\n== desenhar uma tubulação (com nó novo na ponta)")
from programa.ferramentas_mapa import FerramentaDesenho  # noqa: E402
tr, nos = n.camada("trecho"), n.camada("no_juncao")
n0_tr, n0_nos = tr.featureCount(), nos.featureCount()
s2 = next(nos.getFeatures("\"id\" = 'S2'"))
p = s2.geometry().asPoint()
n.executar("tubulacao")
ferr = j.canvas.mapTool()
checar(isinstance(ferr, FerramentaDesenho), "Tubulação ativa a ferramenta de desenho")
n.dock.formulario.setChecked(False)
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(p), QgsPointXY(p.x() + 80, p.y() - 60)]))
ferr._concluido(f)
esperar(40)
checar(tr.featureCount() == n0_tr + 1, f"tubulação nova no cadastro ({n0_tr} → {tr.featureCount()})")
checar(nos.featureCount() == n0_nos + 1, f"nó novo na ponta solta ({n0_nos} → {nos.featureCount()})")
novo = [x for x in tr.getFeatures() if x.id() < 0]
checar(novo and str(novo[0]["no_inicial"]) == "S2", f"a tubulação liga no S2: {novo[0]['no_inicial'] if novo else '?'}")
for _ in range(10):
    j.desfazer()
esperar()
checar(tr.featureCount() == n0_tr, f"desfazer tira a tubulação ({tr.featureCount()})")

print("\n== consumidor (casa ligada ao nó, sem tubulação)")
cons = n.camada("consumidor")
n.executar("ponto_consumo")
ferr = j.canvas.mapTool()
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(p.x() + 15, p.y() + 10)))
ferr._concluido(f)
esperar(40)
c = list(cons.getFeatures())
checar(len(c) == 1, f"consumidor desenhado ({len(c)})")
checar(c and str(c[0]["ligado_a"]) == "S2" and c[0]["tipo_ligacao"] == "NO",
       f"ligou sozinho no nó mais perto: {c[0]['ligado_a'] if c else '?'} / {c[0]['tipo_ligacao'] if c else '?'}")
checar(tr.featureCount() == n0_tr, "nenhuma tubulação criada para o consumidor")
if os.environ.get("GWATER_FOTO"):
    from qgis.core import QgsRectangle  # noqa: E402
    j.canvas.setExtent(QgsRectangle(p.x() - 120, p.y() - 80, p.x() + 120, p.y() + 80))
    j.canvas.refreshAllLayers()
    esperar(60)
    import time as _t  # noqa: E402
    _t.sleep(2)
    esperar(60)
    j.canvas.grab().save(os.environ["GWATER_FOTO"])
cons.changeAttributeValue(c[0].id(), cons.fields().indexOf("demanda_base"), 3.0)
j.salvar_camadas()
esperar()
c = list(cons.getFeatures())
checar(len(c) == 1 and str(c[0]["ligado_a"]) == "S2" and c[0]["demanda_base"] == 3.0, "consumidor gravado")
q0 = n.res.d["nos"]["S2"]["d"][0]
j.acionar("simular")
esperar()
q1 = n.res.d["nos"]["S2"]["d"][0]
checar(q1 > q0 + 1.0, f"a demanda do consumidor entra no nó S2 no cálculo ({q0:g} → {q1:g} L/s)")

print("\n== todos os botões da faixa")
PULAR = {"sair", "novo", "abrir", "importar", "abrir_qgis", "abrir_epanet", "externas", "salvar_como", "recentes",
         "mapa", "calibracao", "aovivo", "dados", "sinotico", "esqueletizar", "loadbuilder", "rastreio_ligar"}
erros = []
for chave in catalogo.todos():
    if chave in PULAR:
        continue
    if os.environ.get("GWATER_VERBOSO"):
        print("    →", chave, flush=True)
    try:
        j.acionar(chave)
        esperar(3)
        if chave not in ("selecionar", "pan", "zoom_mais", "zoom_menos") and j.ferramenta_atual != "selecionar":
            j.usar("selecionar")
    except Exception:
        erros.append((chave, traceback.format_exc().splitlines()[-1]))
for k, e in erros:
    print("     ", k, "→", e)
checar(not erros, f"{len(catalogo.todos()) - len(PULAR)} botões clicados sem erro ({len(erros)} com erro)")
# os botões aceitos às cegas gravaram mudanças (renumeração, padrões...): volta para uma cópia limpa
j.fechar_projeto(False)
for a in ("gwater_cadastro.gpkg", "GWATER_cadastro.qgz"):
    shutil.copyfile(os.path.join(RAIZ, "cadastro", a), os.path.join(TMP, "limpo_" + a))
with open(os.path.join(TMP, "limpo_GWATER_cadastro.qgz"), "rb") as fh:
    pass
import zipfile as _z  # noqa: E402
with _z.ZipFile(os.path.join(TMP, "limpo_GWATER_cadastro.qgz")) as zin,         _z.ZipFile(os.path.join(TMP, "GWATER_limpo_gwater_cadastro.qgz"), "w") as zout:
    for item in zin.infolist():
        dados = zin.read(item.filename)
        if item.filename.endswith(".qgs"):
            dados = dados.replace(b"gwater_cadastro.gpkg", b"limpo_gwater_cadastro.gpkg")
        zout.writestr(item, dados)
j.abrir_projeto(os.path.join(TMP, "GWATER_limpo_gwater_cadastro.qgz"))
esperar()
tr, nos = n.camada("trecho"), n.camada("no_juncao")
j.acionar("simular")
esperar()
checar(n.res is not None, "cópia limpa reaberta e calculada")

print("\n== análises do motor (cenário da rede atual)")
from programa import analise_ui  # noqa: E402
r = analise_ui.rodar(n, "incendio", "Incêndio", vazao=10.0, p_residual=10.0)
checar(r and r["total"] > 0, f"incêndio: {r['atendem']}/{r['total']} atendem" if r else "incêndio falhou")
r = analise_ui.rodar(n, "criticidade", "Criticidade")
checar(r and r["linhas"][0]["falta_pct"] > 0, f"criticidade: mais crítica {r['linhas'][0]['id']} ({r['linhas'][0]['falta_pct']}%)"
       if r else "criticidade falhou")
r = analise_ui.rodar(n, "energia", "Energia")
checar(r and r["total_kwh_dia"] > 0, f"energia: {r['total_kwh_dia']} kWh/dia" if r else "energia falhou")
for chave in ("incendio", "criticidade", "energia", "zonas_pressao", "renovacao", "idade_agua", "descarga"):
    j.acionar(chave)
    esperar()
tr.selectByExpression("\"id\" IN ('T_S1_B', 'T_S1_C')")
j.acionar("dimensionar")
esperar()
abas = [j.centro.tabText(i) for i in range(j.centro.count())]
checar(all(any(x in a for a in abas) for x in ("Incêndio", "Criticidade", "Custo de energia", "Zonas de pressão",
                                                 "Renovação", "Qualidade", "Descarga", "Dimensionamento")),
       f"abas de resultado abertas: {abas[1:]}")
analises = [l.name() for l in QgsProject.instance().mapLayers().values() if "·" in l.name()]
checar(len(analises) >= 6, f"camadas coloridas das análises: {analises}")

print("\n== cenário, cálculo do cenário e comparação")
from programa import cenarios_ui  # noqa: E402
gpkg = n.cadastro()
cenarios_ui.gravar(gpkg, [{"id": "DEMANDA_MAIS_50", "nome": "Demanda +50%", "descricao": "", "com_projetados": False,
                           "fator_demanda": 1.5, "alteracoes": [{"camada": "trecho", "id": "T_S1_B",
                                                                 "campo": "diametro_nominal", "valor": "200"}]}])
cenarios_ui.ativar(n, "DEMANDA_MAIS_50")
checar(n.cenario and n.cenario["fator_demanda"] == 1.5, "cenário ativo com fator 1,5")
p_base = min(n.res.d["nos"]["S1"]["p"])
j.acionar("simular")
esperar()
p_cen = min(n.res.d["nos"]["S1"]["p"])
checar(n.res and p_cen != p_base, f"o cálculo usa o cenário (pressão mín S1: {p_base:.2f} → {p_cen:.2f} mca)")
r = analise_ui.rodar(n, "comparar", "Comparar", cenario_a=None,
                     cenario_b=cenarios_ui.alteracoes_completas(n.cenario))
checar(r and r["b"]["volume_entregue_m3"] > r["a"]["volume_entregue_m3"], "comparação: cenário B entrega mais água")
cenarios_ui.ativar(n, None)
j.acionar("simular")
esperar()

print("\n== tabelas, consultas e relatórios")
from programa.tabelas import abrir_tabela  # noqa: E402
t = abrir_tabela(n, camada="trecho")
checar(t.t.rowCount() == tr.featureCount() and t.t.columnCount() > len(tr.fields()) - 1,
       f"tabela das tubulações: {t.t.rowCount()} linhas, {t.t.columnCount()} colunas (com resultados)")
from programa import consultas  # noqa: E402
ruins = []
for grupo, itens in consultas.CONSULTAS:
    for nome, func in itens:
        try:
            func(n)
        except Exception:
            ruins.append((nome, traceback.format_exc().splitlines()[-1]))
for k, e in ruins:
    print("     ", k, "→", e)
checar(not ruins, f"{sum(len(i) for _, i in consultas.CONSULTAS)} consultas rodam sem erro")
for lyr in n.camadas_rede():
    lyr.removeSelection()
n.camada("trecho").selectByExpression("\"id\" = 'T_S1_B'")
iso = consultas.isolar(n)
checar(iso is not None and any("FECHAR" in x[1] for x in iso), f"isolar T_S1_B: {[x for x in iso if 'FECHAR' in x[1]][:3]}")
from programa import relatorios  # noqa: E402
SALVOS.clear()
w = relatorios.Relatorio(n, relatorios.ESTILO + relatorios.secao_inventario(n) + relatorios.secao_tubos(n), {})
w.pdf()
w.salvar_html()
checar(len(SALVOS) == 2 and all(os.path.getsize(a) > 500 for a in SALVOS), f"relatório em PDF e HTML ({SALVOS})")

print("\n== histórico de alterações e arquivo compactado")
nos.startEditing()
f1 = next(nos.getFeatures("\"id\" = 'S1'"))
nos.changeAttributeValue(f1.id(), nos.fields().indexOf("demanda_base"), 9.99)
nos.commitChanges()
import sqlite3  # noqa: E402
arq_hist = os.path.splitext(gpkg)[0] + "_historico.sqlite"
linhas = sqlite3.connect(arq_hist).execute("SELECT elemento, campo, depois FROM historico").fetchall() \
    if os.path.exists(arq_hist) else []
checar(("S1", "demanda_base", "9.99") in linhas, f"histórico registrou S1.demanda_base = 9,99: {linhas[-1:] }")
SALVOS.clear()
j.acionar("arquivar")
import zipfile  # noqa: E402
checar(SALVOS and zipfile.is_zipfile(SALVOS[0]) and any(x.endswith(".gpkg") for x in zipfile.ZipFile(SALVOS[0]).namelist()),
       "arquivo compactado com o cadastro")

print("\n== excluir um nó leva as tubulações ligadas")
n0 = tr.featureCount()
for lyr in n.camadas_rede():
    lyr.removeSelection()
nos.selectByExpression("\"id\" = 'S2'")
j.acionar("excluir")
esperar()
checar(tr.featureCount() < n0, f"tubulações ligadas ao S2 saíram ({n0} → {tr.featureCount()})")
for lyr in n.camadas_rede():
    if lyr.isEditable():
        lyr.rollBack()

j.fechar_projeto(False)
esperar()
checar(j.centro.tabText(0) == "Início", "fechar o cadastro volta para a tela Início")
QgsProject.instance().clear()
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
