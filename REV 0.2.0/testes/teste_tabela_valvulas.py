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
from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsPointXY  # noqa: E402
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

j.fechar_projeto(False)
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
