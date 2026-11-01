"""Teste das válvulas (TCV sem ajuste, PRV INATIVA), das notificações agrupadas e da tabela
(colar com Ctrl+V numa coluna inteira, selecionar coluna e edição global).

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_tabela_valvulas.py
"""
import os
import shutil
import sys
import tempfile

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "app"))
from qgis.core import QgsApplication, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer  # noqa: E402
from qgis.PyQt.QtCore import Qt  # noqa: E402

app = QgsApplication([b"teste"], True)
app.initQgis()
from qgis.PyQt.QtWidgets import QApplication, QDialog, QMessageBox  # noqa: E402
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
from programa.janela import Janela  # noqa: E402
from gwater import motor  # noqa: E402

TMP = tempfile.mkdtemp(prefix="gwater_teste_tv_")
for a in ("gwater_cadastro.gpkg", "GWATER_cadastro.qgz"):
    shutil.copyfile(os.path.join(RAIZ, "cadastro", a), os.path.join(TMP, a))
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg, flush=True)
    if not cond:
        falhas.append(msg)


j = Janela()
j.abrir_projeto(os.path.join(TMP, "GWATER_cadastro.qgz"))
app.processEvents()
n = j.nucleo
val, tr = n.camada("valvula"), n.camada("trecho")

print("== válvulas")
cfg = val.editorWidgetSetup(val.fields().indexOf("status")).config().get("map")
checar(any("INATIVA" in d.values() for d in cfg), "status INATIVA na lista do formulário da válvula")
i_tipo, i_aj, i_st = (val.fields().indexOf(c) for c in ("tipo", "ajuste", "status"))
prvs = [f for f in val.getFeatures() if f["tipo"] == "PRV"]
val.startEditing()
val.changeAttributeValue(prvs[0].id(), i_st, "INATIVA")
val.changeAttributeValue(prvs[0].id(), i_aj, None)  # inativa: o ajuste não importa
val.changeAttributeValue(prvs[1].id(), i_tipo, "TCV")
val.changeAttributeValue(prvs[1].id(), i_aj, None)  # TCV: sem ajuste
val.changeAttributeValue(prvs[1].id(), i_st, "ATIVA")
val.commitChanges()
dados = motor.rodar("validar", n.cadastro())
erros = [i["msg"] for i in dados.get("itens", []) if i["nivel"] == "ERRO"]
checar(dados.get("ok") and not erros, f"TCV sem ajuste e PRV INATIVA sem ajuste passam na validação: {erros[:3]}")
from importlib import util as _u  # noqa: E402
spec = _u.spec_from_file_location("conv", os.path.join(RAIZ, "motor", "cadastro_para_inp.py"))
conv = _u.module_from_spec(spec)
sys.path.insert(0, os.path.join(RAIZ, "motor"))
try:
    spec.loader.exec_module(conv)
    inp = conv.converter(n.cadastro())[0] if hasattr(conv, "converter") else None
except Exception as e:  # o conversor usa as bibliotecas do motor (.venv): sem elas, confere só a validação
    inp = None
    print("     (conversor não carregado no Python do QGIS:", type(e).__name__, ")")
if isinstance(inp, str):
    linhas = inp.splitlines()
    st = [l for l in linhas if l.split()[:1] == [str(prvs[0]["id"])] and "Open" in l]
    checar(bool(st), f"PRV INATIVA vai para o EPANET como Open (100% aberta): {st[:1]}")
dados = motor.rodar("simular", n.cadastro())
checar(dados.get("ok"), "simula com a TCV e a PRV inativa")

print("\n== notificações agrupadas por tipo")
itens = [{"nivel": "ERRO", "msg": f"no_juncao N{k}: sem ligação com nenhuma fonte (rede desconexa)",
          "camada": "no_juncao", "id": f"N{k}"} for k in range(5)]
itens += [{"nivel": "AVISO", "msg": f"válvula V{k} (PRV): ajuste de {k + 1} mca é muito baixo", "camada": "valvula",
           "id": f"V{k}"} for k in range(3)]
itens += [{"nivel": "AVISO", "msg": "padrão vazio", "camada": None, "id": None}]
n.dock.mostrar_problemas(itens)
arv = n.arvore_notif.arvore
grupos = {arv.topLevelItem(k).text(0): arv.topLevelItem(k).childCount() for k in range(arv.topLevelItemCount())}
print("    ", grupos)
checar(len(grupos) == 3, f"3 tipos de problema ({len(grupos)})")
checar(list(grupos.values())[0] == 5 and list(grupos)[0].startswith("ERRO"), "erros primeiro, com os 5 nós no grupo")
n.arvore_notif.nivel.setCurrentIndex(1)
checar(arv.topLevelItemCount() == 1, "filtro 'Só erros'")

print("\n== tabela: selecionar coluna, Ctrl+V e edição global")
from programa.tabelas import TabelaFlex  # noqa: E402


class _Area:  # a área de transferência do Windows não existe no modo offscreen
    txt = ""

    def text(self):
        return self.txt

    def setText(self, t):
        self.txt = t


_area = _Area()
QApplication.clipboard = staticmethod(lambda: _area)
t = TabelaFlex(n, "trecho")
c = t.campos.index("rugosidade_hw")
t.t.setCurrentCell(0, c)
t._selecionar_coluna()
checar(len({i.row() for i in t.t.selectedIndexes()}) == t.t.rowCount(), "coluna inteira selecionada")
QApplication.clipboard().setText("135")
t._colar()
vals = {f["rugosidade_hw"] for f in tr.getFeatures()}
checar(vals == {135}, f"Ctrl+V de um valor na coluna inteira: {vals}")
QDialog.exec = lambda self: 1  # janela da edição global com as escolhas padrão trocadas abaixo
orig = TabelaFlex._edicao_global


def global_mult(self):
    from qgis.PyQt.QtWidgets import QComboBox, QLineEdit
    real = QDialog.exec

    def exec_(d):
        cbs = d.findChildren(QComboBox)
        cbs[0].setCurrentText("rugosidade_hw")
        cbs[1].setCurrentText("Multiplicar")
        d.findChildren(QLineEdit)[0].setText("0,8")
        cbs[2].setCurrentIndex(0)
        return 1
    QDialog.exec = exec_
    try:
        orig(self)
    finally:
        QDialog.exec = real


t.t.clearSelection()
global_mult(t)
vals = {round(f["rugosidade_hw"], 3) for f in tr.getFeatures()}
checar(vals == {108.0}, f"edição global: multiplicar por 0,8 em todas as linhas: {vals}")
tr.undoStack().undo()
vals = {f["rugosidade_hw"] for f in tr.getFeatures()}
checar(vals == {135}, f"um Ctrl+Z desfaz a edição global inteira: {vals}")
QApplication.clipboard().setText("PVC\nFOFO")
t.carregar()
cm = t.campos.index("material")
t.t.setCurrentCell(0, cm)
t.t.clearSelection()
t.t.setCurrentCell(0, cm)
t._colar()
fids = [t.t.item(r, cm).data(Qt.ItemDataRole.UserRole) for r in (0, 1)]
mats = [tr.getFeature(fid)["material"] for fid in fids]
checar(mats == ["PVC", "FOFO"], f"colar duas linhas do Excel a partir da célula: {mats}")
tr.rollBack()

print("\n== central de demanda: várias demandas por nó")
from programa import componentes  # noqa: E402
nos = n.camada("no_juncao")
lyr_d = componentes.tabela_demandas(n)
checar(lyr_d is not None and lyr_d.isValid(), "tabela de demandas criada no cadastro")
alvo = next(f for f in nos.getFeatures() if float(f["demanda_base"] or 0) > 0)
nid = str(alvo["id"])
pads = sorted({str(f["id_padrao"]) for f in n.camada("padrao_consumo").getFeatures()})
componentes._substituir(n, lyr_d, [{"no_id": nid, "demanda": 1.0, "padrao": pads[0], "categoria": "residencial"},
                                   {"no_id": nid, "demanda": 3.0, "padrao": None, "categoria": "industrial"}],
                        ["no_id", "demanda", "padrao", "categoria"])
nos.startEditing()
nos.changeAttributeValue(alvo.id(), nos.fields().indexOf("demanda_base"), 8.0)  # total mudou por fora: partes × 2
nos.commitChanges()
checar(componentes.ler_colecao(n).get(nid) == [[1.0, pads[0], "residencial"], [3.0, "", "industrial"]],
       "coleção lida do cadastro")
arq = os.path.join(TMP, "m.inp")
r = motor.rodar("exportar", n.cadastro(), False, [f"--inp={arq}"])
txt = open(arq, encoding="utf-8").read() if r.get("ok") else ""
sec = txt.split("[DEMANDS]")[1].split("[")[0] if "[DEMANDS]" in txt else ""
linhas = [l.split() for l in sec.splitlines() if l.strip() and l.split()[0] == nid]
checar(len(linhas) == 2 and [float(l[1]) for l in linhas] == [2.0, 6.0],
       f"[DEMANDS] com as 2 demandas, escaladas ao total do nó: {linhas}")
checar(r.get("ok") and motor.rodar("simular", n.cadastro()).get("ok"), "simula com várias demandas por nó")
QDialog.exec = lambda self: 0
componentes.central_demanda(n)  # monta a janela com a coleção carregada
checar(True, "janela da Central de demanda abre com a coleção")

print("\n== curvas de bomba: tipos e rendimento")
from gwater import curvas as cv  # noqa: E402
jc = cv.JanelaCurvas(j, n)
nome = sorted(jc.curvas)[0]
jc._selecionar(nome)
jc.forma_ef.setCurrentIndex(jc.forma_ef.findData("b"))
jc._mudar_rendimento()
checar(len(jc.rend[nome]) == 1 and jc.rend[nome][0][0] > 0, f"rendimento pelo ponto de melhor rendimento: {jc.rend[nome]}")
jc._nova()
nova = jc.atual
jc.forma.setCurrentIndex(jc.forma.findData("p"))
jc._mudar_forma()
jc.pot.setValue(12.5)
checar(jc.potencia.get(nova) == 12.5, "definição de potência constante")
jc.forma_ef.setCurrentIndex(jc.forma_ef.findData("c"))
jc._mudar_rendimento()
if os.environ.get("GWATER_FOTO"):  # imagem da janela para conferir o layout
    jc._selecionar(nome)
    jc.grab().save(os.environ["GWATER_FOTO"])
jc.salvar()
c2, p2, r2 = cv.ler_tudo(n.camada("curva"))
checar(p2.get(nova) == 12.5 and nome in r2 and nova in r2 and nome in c2, "gravou curva, potência e rendimentos")
checar(nova in cv.nomes(n.camada("curva")), "a potência constante aparece na lista do campo curva da bomba")
b1 = next(n.camada("bomba").getFeatures())
bl = n.camada("bomba")
bl.startEditing()
bl.changeAttributeValue(b1.id(), bl.fields().indexOf("curva"), nova)
bl.commitChanges()
arq = os.path.join(TMP, "b.inp")
r = motor.rodar("exportar", n.cadastro(), False, [f"--inp={arq}"])
txt = open(arq, encoding="utf-8").read() if r.get("ok") else ""
checar("POWER 12.5" in txt and f"Efficiency {nova}__EF" in txt, "EPANET: bomba de potência constante com rendimento")
checar(motor.rodar("simular", n.cadastro()).get("ok"), "simula com a bomba de potência constante")

print("\n== controles lógicos")
from programa import regras as rg  # noqa: E402
regras = {"R1_ENCHE": {"prioridade": 3.0,
                       "SE": [{"conector": "SE", "elemento": "R1", "atributo": "NIVEL", "operador": "<", "valor": "2"},
                              {"conector": "OU", "elemento": "SISTEMA", "atributo": "HORA_RELOGIO", "operador": ">=",
                               "valor": "22"}],
                       "ENTAO": [{"conector": "E", "elemento": "B1", "atributo": "STATUS", "operador": "=",
                                  "valor": "ABERTA"}],
                       "SENAO": [{"conector": "E", "elemento": "B1", "atributo": "STATUS", "operador": "=",
                                  "valor": "FECHADA"}]},
          "VRP_NOITE": {"prioridade": 0.0,
                        "SE": [{"conector": "SE", "elemento": "SISTEMA", "atributo": "HORA_RELOGIO", "operador": ">=",
                                "valor": "23.5"}],
                        "ENTAO": [{"conector": "E", "elemento": "VRP2", "atributo": "AJUSTE", "operador": "=",
                                   "valor": "18"}], "SENAO": []}}
rg.gravar(n, regras)
lidas = rg.ler(n)
checar(list(lidas) == ["R1_ENCHE", "VRP_NOITE"] and lidas["R1_ENCHE"]["SE"][1]["conector"] == "OU"
       and lidas["R1_ENCHE"]["prioridade"] == 3, "regras gravadas e lidas do cadastro")
arq = os.path.join(TMP, "r.inp")
r = motor.rodar("exportar", n.cadastro(), False, [f"--inp={arq}"])
txt = open(arq, encoding="utf-8").read() if r.get("ok") else ""
sec = txt.split("[RULES]")[1].split("[")[0] if "[RULES]" in txt else ""
esperado = ["RULE R1_ENCHE", "IF NODE R1 LEVEL < 2", "OR SYSTEM CLOCKTIME >= 22:00", "THEN LINK B1 STATUS IS OPEN",
            "ELSE LINK B1 STATUS IS CLOSED", "PRIORITY 3", "IF SYSTEM CLOCKTIME >= 23:30",
            "THEN LINK VRP2 SETTING IS 18"]
checar(all(e in sec for e in esperado), f"[RULES] do EPANET: {[l for l in sec.splitlines() if l][:9]}")
checar(motor.rodar("simular", n.cadastro()).get("ok"), "simula com os controles lógicos")
QDialog.exec = lambda self: 0
if os.environ.get("GWATER_FOTO"):
    orig_exec = QDialog.exec

    def foto(self):
        self.grab().save(os.environ["GWATER_FOTO"].replace(".png", "_regras.png"))
        return 0
    QDialog.exec = foto
rg.controles_logicos(n)
checar(True, "janela dos controles lógicos abre com as regras")

print("\n== padrões: em degraus, contínuo e multiplicador inicial")
from programa.componentes import gravar_padroes, passos_padrao  # noqa: E402
checar(passos_padrao("DEGRAUS", [(0, 0.5), (6, 1.5), (18, 0.8)], 60)[5:7] == [0.5, 1.5], "degraus: muda na hora do ponto")
cont = passos_padrao("CONTINUO", [(0, 0.5), (12, 1.5)], 120)
checar(cont[0] < cont[5] and cont[-1] < cont[6] and len(cont) == 12, f"contínuo: sobe até 12 h e volta ao inicial: {cont}")
pads = {"PAD_CONS": {"formato": "CONTINUO", "pts": [(0.0, 0.4), (8.0, 1.6), (20.0, 1.2)]},
        "PAD_COM": {"formato": "DEGRAUS", "pts": [(0.0, 0.2), (8.0, 1.8), (18.0, 0.2)]}}
gravar_padroes(n, pads, 15)
arq = os.path.join(TMP, "p.inp")
r = motor.rodar("exportar", n.cadastro(), False, [f"--inp={arq}"])
txt = open(arq, encoding="utf-8").read() if r.get("ok") else ""
sec = txt.split("[PATTERNS]")[1].split("[")[0] if "[PATTERNS]" in txt else ""
vals = [float(x) for l in sec.splitlines() if l.split()[:1] == ["PAD_COM"] for x in l.split()[1:]]
checar(len(vals) == 96 and vals[31] == 0.2 and vals[32] == 1.8, f"EPANET: PAD_COM em 96 passos de 15 min ({len(vals)})")
checar(motor.rodar("simular", n.cadastro()).get("ok"), "simula com o padrão contínuo")
if os.environ.get("GWATER_FOTO"):
    def foto2(self):
        self.grab().save(os.environ["GWATER_FOTO"].replace(".png", "_padroes.png"))
        return 0
    QDialog.exec = foto2
from programa.componentes import padroes as janela_padroes  # noqa: E402
janela_padroes(n)
checar(True, "janela de padrões abre com a definição")

print("\n== análises: segmentos, incêndio, descarga, origem da água, dimensionamento genético")
r = motor.analise("criticidade", n.cadastro(), False, modo="segmento")
segs = r.get("linhas", [])
checar(r.get("ok") and len(segs) >= 2 and any(s_["registros"] for s_ in segs),
       f"criticidade por segmentos entre registros: {[(s_['id'], s_['n_tubos'], s_['registros']) for s_ in segs]}")
r = motor.analise("incendio", n.cadastro(), False, vazao=10, p_min_sistema=5, v_max=3, modo="substituir")
checar(r.get("ok") and all("p_min_sistema" in x and "v_max" in x for x in r["linhas"]),
       f"incêndio com pressão do sistema e velocidade: {[(x['id'], x['q_disponivel'], x['limitado_por']) for x in r.get('linhas', [])][:3]}")
r = motor.analise("descarga", n.cadastro(), False, modo="pressao", p_hidrante=10)
checar(r.get("ok") and all(e["vazao"] > 0 for e in r["eventos"]), "descarga pela pressão no hidrante")
cap = str(next(n.camada("captacao").getFeatures())["id"])
r = motor.analise("qualidade", n.cadastro(), False, parametro="TRACE", fonte=cap, duracao_h=48)
checar(r.get("ok") and "%" in r["parametro"], f"origem da água (trace) de {cap}")
r = motor.analise("dimensionar", n.cadastro(), False, trechos=[str(f["id"]) for f in tr.getFeatures()][:3], p_min=10,
                  metodo="genetico", max_avaliacoes=500)
checar(r.get("ok") and r.get("metodo") == "genetico", f"dimensionamento genético: custo {r.get('custo_total')}")

print("\n== componentes: curvas de válvula GPV, demandas unitárias, tarifas")
from programa import componentes_extra as cx  # noqa: E402
vl = n.camada("valvula")
v_gpv = next(f for f in vl.getFeatures() if f["tipo"] == "PRV")
vl.startEditing()
vl.changeAttributeValue(v_gpv.id(), vl.fields().indexOf("tipo"), "GPV")
vl.commitChanges()
r = motor.rodar("validar", n.cadastro())
checar(any("GPV" in i["msg"] and "curva" in i["msg"] for i in r.get("itens", [])), "GPV sem curva vira erro claro")
cx.gravar_curvas_valvula(n, {str(v_gpv["id"]): [(0.0, 0.0), (10.0, 2.0), (30.0, 12.0)]})
arq = os.path.join(TMP, "g.inp")
r = motor.rodar("exportar", n.cadastro(), False, [f"--inp={arq}"])
txt = open(arq, encoding="utf-8").read() if r.get("ok") else ""
checar(f"GPV  {v_gpv['id']}__GPV" in txt, "GPV vai ao EPANET com a curva perda × vazão")
checar(motor.rodar("simular", n.cadastro()).get("ok"), "simula com a GPV")
alvos = [str(f["id"]) for f in n.camada("no_juncao").getFeatures()][:2]
antes = {str(f["id"]): float(f["demanda_base"] or 0) for f in n.camada("no_juncao").getFeatures()}
cx.adicionar_unitaria(n, alvos, "Residencial", {"valor": 150.0, "unidade": "habitante", "padrao": ""}, 864)
depois = {str(f["id"]): float(f["demanda_base"] or 0) for f in n.camada("no_juncao").getFeatures()}
checar(all(abs(depois[a] - antes[a] - 1.5) < 1e-6 for a in alvos),
       "demanda unitária: 864 hab × 150 L/dia = +1,5 L/s em cada nó")
from programa.componentes import ler_colecao  # noqa: E402
checar(any("Residencial" in c for _, _, c in ler_colecao(n)[alvos[0]]), "entra na Central com a categoria")
n.camada("no_juncao").commitChanges()
j.gravar_json("tarifas", {"Verde": [0.4] * 17 + [1.9] * 3 + [0.4] * 4})
r = motor.analise("energia", n.cadastro(), False, tarifa=j._ler_json("tarifas", {})["Verde"])
checar(r.get("ok") and r["tarifa"][18] == 1.9, "custo de energia com a tarifa gravada")

print("\n== ferramentas: LoadBuilder, ModelBuilder (sincronizar), esqueletizador")
from qgis.core import QgsVectorLayer as _VL  # noqa: E402
from programa.ferramentas_modelo import distribuir_cargas  # noqa: E402
nos_l = n.camada("no_juncao")
crs = nos_l.crs().authid()
ext = nos_l.extent()
ext.grow(200)
pol = _VL(f"Polygon?crs={crs}&field=POP:double", "setores", "memory")
fp = QgsFeature(pol.fields())
fp.setGeometry(QgsGeometry.fromRect(ext))
fp.setAttributes([1000.0])
pol.dataProvider().addFeatures([fp])
for met in ("area", "igual", "comprimento"):
    dest, sem = distribuir_cargas(n, pol, "POP", 150 / 86400, False, met)
    checar(abs(sum(dest.values()) - 1000 * 150 / 86400) < 1e-6 and sem == 0,
           f"LoadBuilder polígono ({met}): 1000 hab × 150 L/dia = {sum(dest.values()):.4f} L/s em {len(dest)} nós")
pt = _VL(f"Point?crs={crs}&field=CONS:double", "hidrometros", "memory")
c0 = ext.center()
fq = QgsFeature(pt.fields())
fq.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(c0.x(), c0.y())))
fq.setAttributes([2.0])
pt.dataProvider().addFeatures([fq])
for met in ("no", "tubo", "tubo_igual"):
    dest, _ = distribuir_cargas(n, pt, "CONS", 1.0, True, met)
    checar(abs(sum(dest.values()) - 2.0) < 1e-9, f"LoadBuilder ponto ({met}): {dest}")
from programa.importador import sincronizar  # noqa: E402
alvo_no = next(nos_l.getFeatures())
mem = _VL(f"Point?crs={crs}&field=COD:string&field=DEM:double", "nos_sync", "memory")
fs_ = QgsFeature(mem.fields())
fs_.setGeometry(QgsGeometry(alvo_no.geometry()))
fs_.setAttributes([str(alvo_no["id"]), 7.25])
fn_ = QgsFeature(mem.fields())
fn_.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(c0.x() + 5, c0.y() + 5)))
fn_.setAttributes(["NOVO_X", 1.0])
mem.dataProvider().addFeatures([fs_, fn_])
job = {"nome": "nos_sync", "camada": "no_juncao", "fixos_tipo": {}, "origem": mem,
       "mapa": {"id": "COD", "demanda_base": "DEM"}, "fixos": {}, "traducoes": {}, "so_sel": False}
res_s = sincronizar(n, [job])
checar(res_s.get("no_juncao") == 1 and len(job["pular"]) == 1, f"sincronizar: 1 nó atualizado, o outro fica para criar ({res_s})")
checar(abs(nos_l.getFeature(alvo_no.id())["demanda_base"] - 7.25) < 1e-9, "dados do nó existente atualizados pelo código")
nos_l.rollBack()
r = motor.analise("esqueletizar", n.cadastro(), False, destino=os.path.join(TMP, "esq.gpkg"), dn_max=0,
                  cortar_ramais=False, unir_serie=True, tol_dn_pct=60, unir_paralelos=True)
checar(r.get("ok") and "paralelos_unidos" in r, f"esqueletizador com equivalência e paralelos: {r.get('tubos_unidos')} série, "
       f"{r.get('paralelos_unidos')} paralelos")

print("\n== desenho: inverter sentido, converter em, unir nós próximos")
from programa import desenho_extra as dx  # noqa: E402
trl = n.camada("trecho")
t0 = next(trl.getFeatures())
a0, b0 = str(t0["no_inicial"]), str(t0["no_final"])
p_ini = t0.geometry().vertexAt(0)
dx.inverter_sentido(n, [str(t0["id"])])
t1 = trl.getFeature(t0.id())
checar(str(t1["no_inicial"]) == b0 and str(t1["no_final"]) == a0 and t1.geometry().vertexAt(t1.geometry().constGet().nCoordinates() - 1) == p_ini,
       "inverter sentido: nós trocados e geometria invertida")
nosl = n.camada("no_juncao")
grau2 = None
for f in nosl.getFeatures():
    if dx._grau(trl, str(f["id"])) == 2:
        grau2 = f
        break
outro = next(f for f in nosl.getFeatures() if grau2 is None or f.id() != grau2.id())
dx.converter(n, "hidrante", [str(outro["id"])])
checar(str(nosl.getFeature(outro.id())["tipo"]) == "HIDRANTE", "converter nó em hidrante (mesma camada)")
if grau2 is not None:
    cod2 = str(grau2["id"])
    dx.converter(n, "valvula_fcv", [cod2])
    v_nova = [f for f in n.camada("valvula").getFeatures() if str(f["id"]) == cod2]
    checar(len(v_nova) == 1 and v_nova[0]["tipo"] == "FCV" and dx._grau(trl, cod2) == 2 and
           not any(str(f["id"]) == cod2 for f in nosl.getFeatures()),
           f"converter nó {cod2} em FCV: mesmo código, tubulações ligadas nela")
nosl.startEditing()
perto = QgsFeature(nosl.fields())
pp = outro.geometry().asPoint()
perto.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pp.x() + 0.2, pp.y())))
perto["id"], perto["tipo"], perto["demanda_base"] = "N_DUP", "JUNCAO", 1.0
nosl.addFeature(perto)
dem0 = float(nosl.getFeature(outro.id())["demanda_base"] or 0)
nosl.selectByIds([])
removidos = dx.unir_nos(n, 0.5)
checar(removidos == 1 and not any(str(f["id"]) == "N_DUP" for f in nosl.getFeatures()) and
       abs(float(nosl.getFeature(outro.id())["demanda_base"] or 0) - dem0 - 1.0) < 1e-9,
       "unir nós próximos: o nó a 0,2 m sumiu e a demanda foi somada")
for l in (nosl, trl, n.camada("valvula")):
    l.rollBack()

print("\n== calibração (Darwin)")
from programa import calibracao_ui as cal  # noqa: E402
from qgis.PyQt.QtWidgets import QPushButton  # noqa: E402
tr = n.camada("trecho")
i_c = tr.fields().indexOf("rugosidade_hw")
original = {f.id(): f["rugosidade_hw"] for f in tr.getFeatures()}
tr.startEditing()
for fid in original:  # rede "verdadeira": C 85 em tudo; as leituras de campo saem dela
    tr.changeAttributeValue(fid, i_c, 85.0)
tr.commitChanges()
sim = motor.rodar("simular", n.cadastro())
horas = sim["horas"]
nos_ids = [str(f["id"]) for f in n.camada("no_juncao").getFeatures()]
momentos = []
for hh in (7, 20):
    k = min(range(len(horas)), key=lambda i: abs(horas[i] - hh))
    momentos.append({"nome": f"{hh:02d}:00", "hora": hh, "fator_demanda": 1.0, "contorno": [],
                     "observacoes": [{"elemento": nid, "grandeza": "pressao", "valor": round(sim["nos"][nid]["p"][k], 2),
                                      "peso": 1} for nid in nos_ids if nid in sim["nos"]]})
tr.startEditing()
for fid, v in original.items():
    tr.changeAttributeValue(fid, i_c, v)
tr.commitChanges()
est = cal.estudo_padrao()
est["momentos"] = momentos
est["agrupar_c"] = "unico"
est["grupos_c"] = cal.gerar_grupos_c(n, "unico")
est["max_avaliacoes"] = 600
j.gravar_json("calibracao", est)
checar(len(est["grupos_c"]) == 1 and len(est["grupos_c"][0]["ids"]) == tr.featureCount(), "grupo único de rugosidade")
csv_txt = "elemento;grandeza;hora;valor\nS1;pressao;07:00;20,5\nS2;pressao;07:00;18\nT1;vazao;19:30;12"
lidos = cal.ler_csv(csv_txt)
checar(len(lidos) == 2 and lidos[0]["observacoes"][0]["valor"] == 20.5, "CSV de campo vira momentos por hora")


def exec_calibrar(self):
    for b in self.findChildren(QPushButton):
        if "Calibrar" in b.text():
            b.click()
            break
    if os.environ.get("GWATER_FOTO"):
        self.grab().save(os.environ["GWATER_FOTO"].replace(".png", "_calibracao.png"))
    return 0


QDialog.exec = exec_calibrar
estado = cal.calibracao(n)
res = estado["res"]
checar(res is not None and res.get("ok"), f"calibração rodou ({res and res['avaliacoes']} avaliações)")
if res:
    c_cal = res["solucoes"][0]["parametros"][0]["calibrado"]
    checar(abs(c_cal - 85) < 2, f"recuperou o C verdadeiro: {c_cal} (verdade 85)")
    checar(res["solucoes"][0]["indicadores"]["pressao"]["erro_medio"] < 0.05, "leituras ajustadas depois da calibração")
    checar(any(a["campo"] == "rugosidade_hw" for a in res["solucoes"][0]["alteracoes"]), "solução vira alterações")

print("\n== exibir e relatório: medições no gráfico, rótulos de resultados, detalhes do elemento")
from programa import graficos as gfx, relatorios as rel_, vistas as vis  # noqa: E402
n.janela.acionar("simular")
checar(n.res is not None, "rede calculada")
no_med = momentos[0]["observacoes"][0]["elemento"]
checar(len(gfx.medicoes_de(n, no_med, "pressao")) == 2, f"leituras de campo de {no_med} achadas para o gráfico")
g = gfx.Grafico(n, [("no_juncao", no_med)])
g.var.setCurrentText("Pressão (mca)")
g.desenhar()
rot = [t.get_text() for t in g.fig.axes[0].get_legend().get_texts()] if g.fig.axes[0].get_legend() else []
checar(any("medido em campo" in t for t in rot), f"gráfico mostra o medido em campo: {rot}")
vis.rotulos_resultados(n, "p", "q", 1)
checar(n.res.tr.labelsEnabled() and "q" in n.res.tr.labeling().settings().fieldName, "rótulos de vazão nas tubulações")
abas0 = n.janela.findChildren(rel_.Relatorio)
fn_ = next(n.camada("no_juncao").getFeatures(QgsFeatureRequest().setFilterExpression(f"\"id\" = '{no_med}'")))
rel_.detalhes_elemento(n, [(n.camada("no_juncao"), [fn_.id()])])
novos = [r_ for r_ in n.janela.findChildren(rel_.Relatorio) if r_ not in abas0]
html = novos[0].html if novos else ""
checar(bool(novos) and "Resultados hora a hora" in html and "Leituras de campo" in html and novos[0].recursos,
       "detalhes do elemento: dados, resultados, gráfico e leituras de campo")

print("\n== revisão: comparação de cenários e histórico de alterações")
from programa import revisao as rv  # noqa: E402
difs = rv.diferencas_dados([{"camada": "trecho", "id": "T1", "campo": "diametro_nominal", "valor": 150}],
                           [{"camada": "trecho", "id": "T1", "campo": "diametro_nominal", "valor": 200},
                            {"camada": "global", "id": "", "campo": "fator_demanda", "valor": 1.2}])
checar(len(difs) == 2 and ["trecho", "T1", "diametro_nominal", "150", "200"] in difs,
       f"diferenças de dados entre os cenários: {difs}")
t_alvo = str(next(trl.getFeatures())["id"])
r = motor.analise("comparar", n.cadastro(), False,
                  cenario_b=[{"camada": "trecho", "id": t_alvo, "campo": "diametro_nominal", "valor": 50}],
                  limites={"limite_pressao_min": 15, "limite_pressao_max": 40, "limite_velocidade": 1.0}, hora=7)
checar(r.get("ok") and "q_a" in r["tubos"][0] and any(x["dif"] or x["dif_q"] for x in r["tubos"]),
       f"comparação às 07:00 com vazões: {r['tubos'][0] if r.get('ok') else r}")
fh = next(trl.getFeatures())
mat0 = fh["material"]
trl.startEditing()
trl.changeAttributeValue(fh.id(), trl.fields().indexOf("material"), "PEAD")
trl.commitChanges()
hist = rv.ler_historico(n, elemento=str(fh["id"]), campo="material")
checar(bool(hist) and hist[0][7] == "PEAD", f"histórico registrou a troca de material: {hist[:1]}")
linha_tab = [hist[0][3], *hist[0][:3], *hist[0][4:]]
rv.desfazer_registros(n, [linha_tab])
checar(trl.getFeature(fh.id())["material"] == mat0, f"desfazer pelo histórico volta o material ({mat0})")
trl.rollBack()

print("\n== códigos repetidos")
trl = n.camada("trecho")
fs_ = list(trl.getFeatures())[:3]
trl.startEditing()
for f_ in fs_:
    trl.changeAttributeValue(f_.id(), trl.fields().indexOf("id"), "projeto")
trl.commitChanges()
r = motor.rodar("validar", n.cadastro())
checar(any("'projeto' repetido em 3 tubulações" in i["msg"] for i in r.get("itens", [])),
       "validar aponta o código de tubulação repetido")
from programa.tabelas import TabelaFlex  # noqa: E402
t2 = TabelaFlex(n, "trecho")
c_id = t2.campos.index("id")
antes_ids = sorted(str(f["id"]) for f in trl.getFeatures())
t2._gravar([(0, c_id, "X1"), (1, c_id, "X1")], "teste")
checar(sorted(str(f["id"]) for f in trl.getFeatures()) == antes_ids, "tabela recusa gravar código repetido")
QDialog.exec = lambda self: 1
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
from programa.ferramentas_modelo import ids as centro_codigos  # noqa: E402
centro_codigos(n)  # Trechos é o primeiro tipo da lista; "só os repetidos" vem marcado
ids_agora = [str(f["id"]) for f in trl.getFeatures()]
checar(ids_agora.count("projeto") == 1 and len(set(ids_agora)) == len(ids_agora),
       f"Centro de códigos renumera só os repetidos: {sorted(ids_agora)[:6]}")
trl.commitChanges()
checar(motor.rodar("validar", n.cadastro()).get("ok"), "rede volta a validar")

print("\n== salvamento automático")
from programa import desempenho as dsp  # noqa: E402
cfg0 = dsp.ler()
dsp.gravar(cfg0["nucleos"], cfg0["cache_mb"], cfg0["mapa_paralelo"], 1)
trl = n.camada("trecho")
trl.startEditing()
f_a = next(trl.getFeatures())
trl.changeAttributeValue(f_a.id(), trl.fields().indexOf("observacao"), "auto")
app.processEvents()
j._ultimo_salvar = j._ultima_edicao = -1e9  # como se já tivesse passado o intervalo e o usuário estivesse parado
QDialog.exec = lambda self: 0
j._talvez_salvar()
checar(not trl.isModified() and trl.isEditable(), "salvou sozinho e continua em edição")
gravado = next(QgsVectorLayer(f"{n.cadastro()}|layername=trecho", "x", "ogr").getFeatures(
    QgsFeatureRequest().setFilterExpression(f"\"id\" = '{f_a['id']}'")))
checar(gravado["observacao"] == "auto", "a alteração está no arquivo do cadastro")
trl.changeAttributeValue(f_a.id(), trl.fields().indexOf("observacao"), "agora")
app.processEvents()
j._ultimo_salvar = -1e9
j._talvez_salvar()  # acabou de editar: espera o usuário parar
checar(trl.isModified(), "não salva no meio da edição (espera alguns segundos parado)")
trl.rollBack()
dsp.gravar(cfg0["nucleos"], cfg0["cache_mb"], cfg0["mapa_paralelo"], cfg0["auto_min"])

j.fechar_projeto(False)
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
