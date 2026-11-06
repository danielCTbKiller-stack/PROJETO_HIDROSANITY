"""Seleção: excluir, localizar, por tipo, por atributo, inverter, limpar e conjuntos de seleção."""
from qgis.core import QgsExpression, QgsFeatureRequest
from qgis.gui import QgsExpressionBuilderDialog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout,
)

from .tema import icone
from .util import NOMES, PONTOS, Dialogo, achar, selecionar_ids


def excluir(nucleo):
    janela = nucleo.janela
    sel = janela.selecionados()
    if not sel:
        return nucleo.informar("Selecione os elementos a excluir.")
    total = sum(len(f) for _, f in sel)
    pontos = [(l, fids) for l, fids in sel if l.name() and l in [nucleo.camada(c) for c in PONTOS if _tem(nucleo, c)]]
    ids_pontos = {str(f["id"]) for l, fids in pontos for f in l.getFeatures(fids)}
    tr = nucleo.camada("trecho")
    ligados = [f.id() for f in tr.getFeatures()
               if (str(f["no_inicial"]) in ids_pontos or str(f["no_final"]) in ids_pontos)
               and f.id() not in tr.selectedFeatureIds()] if ids_pontos else []
    msg = f"Excluir {total} elemento(s) selecionado(s)?"
    if ligados:
        msg += f"\n\n{len(ligados)} tubulação(ões) ligada(s) a esses nós também serão excluídas (como no WaterGEMS)."
    if QMessageBox.question(janela, "GWATER · Excluir", msg + "\n\nVocê pode desfazer com Ctrl+Z até salvar.") \
            != QMessageBox.StandardButton.Yes:
        return
    if ligados:
        sel = [(l, f) for l, f in sel if l != tr] + [(tr, list(tr.selectedFeatureIds()) + ligados)]
    for lyr, fids in sel:
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand("Excluir")
        lyr.deleteFeatures(fids)
        lyr.endEditCommand()
    janela.canvas.refresh()
    janela._selecao_mudou()
    nucleo.dock.status.setText(f"{total + len(ligados)} elemento(s) excluído(s). Ctrl+Z desfaz; <b>Salvar edições</b> grava.")


def _tem(nucleo, c):
    try:
        nucleo.camada(c)
        return True
    except LookupError:
        return False


def localizar(nucleo):
    if not nucleo.cadastro():
        return nucleo.aviso("Abra um cadastro primeiro.")
    d = Dialogo(nucleo.janela, "Localizar", "Digite o código (ou parte dele) e escolha o elemento. Clique duplo vai até ele.")
    campo = QLineEdit()
    campo.setPlaceholderText("ex.: N-0012, T-0105, VRP1")
    d.lay.addWidget(campo)
    lista = QListWidget()
    lista.setMinimumHeight(260)
    d.lay.addWidget(lista)
    todos = []
    for lyr in nucleo.camadas_rede():
        nome = lyr.name()
        for f in lyr.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(["id"], lyr.fields())):
            todos.append((str(f["id"]), nome))

    def filtrar(txt):
        lista.clear()
        t = txt.strip().lower()
        for eid, nome in [x for x in todos if t in x[0].lower()][:500]:
            it = QListWidgetItem(f"{eid}    ·  {nome}")
            it.setData(Qt.ItemDataRole.UserRole, eid)
            lista.addItem(it)

    campo.textChanged.connect(filtrar)
    lista.itemDoubleClicked.connect(lambda it: (selecionar_ids(nucleo, [it.data(Qt.ItemDataRole.UserRole)]), d.accept()))
    campo.returnPressed.connect(lambda: lista.count() and (selecionar_ids(nucleo, [lista.item(0).data(Qt.ItemDataRole.UserRole)]), d.accept()))
    filtrar("")
    d.botoes("Ir até", "Fechar")
    if d.exec() and lista.currentItem():
        selecionar_ids(nucleo, [lista.currentItem().data(Qt.ItemDataRole.UserRole)])


def por_tipo(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Selecionar por tipo de elemento", "Marque os tipos a selecionar. Opcional: só os EXISTENTES "
                "ou só os PROJETADOS.")
    caixas = {}
    for c in ("trecho",) + PONTOS:
        if _tem(nucleo, c):
            cb = QCheckBox(f"{NOMES[c]} ({nucleo.camada(c).featureCount()})")
            caixas[c] = cb
            d.lay.addWidget(cb)
    sit = QComboBox()
    sit.addItems(["Todos", "EXISTENTE", "PROJETADO", "DESATIVADO"])
    d.linha("Situação:", sit)
    soma = QCheckBox("Somar à seleção atual")
    d.lay.addWidget(soma)
    d.botoes("Selecionar")
    if not d.exec():
        return
    from qgis.core import Qgis
    modo = Qgis.SelectBehavior.AddToSelection if soma.isChecked() else Qgis.SelectBehavior.SetSelection
    expr = "TRUE" if sit.currentText() == "Todos" else f"\"situacao\" = '{sit.currentText()}'"
    for c, cb in caixas.items():
        lyr = nucleo.camada(c)
        if cb.isChecked():
            lyr.selectByExpression(expr, modo)
        elif not soma.isChecked():
            lyr.removeSelection()
    nucleo.janela._selecao_mudou()


def por_atributo(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Selecionar por atributo",
                "Escolha o tipo de elemento e escreva a condição (o botão ε abre o construtor com os campos e funções). "
                "Exemplos: \"diametro_nominal\" < 100 · \"material\" = 'Cimento-amianto' · \"ano_instalacao\" < 1990")
    tipo = QComboBox()
    for c in ("trecho",) + PONTOS:
        if _tem(nucleo, c):
            tipo.addItem(NOMES[c], c)
    d.linha("Elemento:", tipo)
    h = QHBoxLayout()
    expr = QLineEdit()
    h.addWidget(expr, 1)
    b = QPushButton("ε")
    b.setToolTip("Construtor de expressões")
    h.addWidget(b)
    d.form.addRow("Condição:", h)

    def construtor():
        dlg = QgsExpressionBuilderDialog(nucleo.camada(tipo.currentData()), expr.text(), nucleo.janela)
        if dlg.exec():
            expr.setText(dlg.expressionText())
    b.clicked.connect(construtor)
    modo = QComboBox()
    modo.addItems(["Nova seleção", "Somar à seleção", "Tirar da seleção", "Dentro da seleção"])
    d.linha("Modo:", modo)
    d.botoes("Selecionar")
    if not d.exec() or not expr.text().strip():
        return
    e = QgsExpression(expr.text())
    if e.hasParserError():
        return nucleo.aviso(f"Condição inválida: {e.parserErrorString()}")
    from qgis.core import Qgis
    m = [Qgis.SelectBehavior.SetSelection, Qgis.SelectBehavior.AddToSelection,
         Qgis.SelectBehavior.RemoveFromSelection, Qgis.SelectBehavior.IntersectSelection][modo.currentIndex()]
    lyr = nucleo.camada(tipo.currentData())
    lyr.selectByExpression(expr.text(), m)
    nucleo.janela._selecao_mudou()
    nucleo.informar(f"{lyr.selectedFeatureCount()} elemento(s) selecionado(s) em {lyr.name()}.")


def inverter(nucleo):
    for lyr in nucleo.camadas_rede():
        if lyr.selectedFeatureCount():
            lyr.invertSelection()
    nucleo.janela._selecao_mudou()


def limpar(nucleo):
    for lyr in nucleo.camadas_rede():
        lyr.removeSelection()
    nucleo.janela._selecao_mudou()


# ---------------------------------------------------------------- conjuntos de seleção
def conjuntos(nucleo):
    janela = nucleo.janela
    if not nucleo.cadastro():
        return
    dados = janela._ler_json("conjuntos", {})
    d = Dialogo(janela, "Conjuntos de seleção", "Guarde a seleção atual com um nome e recupere depois (fica salvo no "
                "projeto). Clique duplo seleciona o conjunto.")
    lista = QListWidget()
    lista.setMinimumHeight(240)
    d.lay.addWidget(lista)

    def recarregar():
        lista.clear()
        for nome, ids in sorted(dados.items()):
            it = QListWidgetItem(icone("conjuntos"), f"{nome}  ({len(ids)} elementos)")
            it.setData(Qt.ItemDataRole.UserRole, nome)
            lista.addItem(it)

    def novo():
        from .util import ids_selecionados
        ids = ids_selecionados(nucleo)
        if not ids:
            return nucleo.informar("Selecione os elementos no mapa antes de criar o conjunto.")
        nome, ok = QInputDialog.getText(janela, "Novo conjunto", f"Nome do conjunto ({len(ids)} elementos):")
        if ok and nome.strip():
            dados[nome.strip()] = ids
            janela.gravar_json("conjuntos", dados)
            recarregar()

    def usar(it=None):
        it = it or lista.currentItem()
        if it:
            selecionar_ids(nucleo, dados[it.data(Qt.ItemDataRole.UserRole)])

    def apagar():
        it = lista.currentItem()
        if it:
            dados.pop(it.data(Qt.ItemDataRole.UserRole), None)
            janela.gravar_json("conjuntos", dados)
            recarregar()

    def somar():
        from .util import ids_selecionados
        it = lista.currentItem()
        if it:
            nome = it.data(Qt.ItemDataRole.UserRole)
            dados[nome] = sorted(set(dados[nome]) | set(ids_selecionados(nucleo)))
            janela.gravar_json("conjuntos", dados)
            recarregar()

    h = QHBoxLayout()
    for texto, f in (("Novo da seleção", novo), ("Somar a seleção", somar), ("Selecionar", usar), ("Apagar", apagar)):
        b = QPushButton(texto)
        b.clicked.connect(f)
        h.addWidget(b)
    d.lay.addLayout(h)
    lista.itemDoubleClicked.connect(usar)
    recarregar()
    d.botoes(None, "Fechar")
    d.exec()


ACOES = {"excluir": excluir, "localizar": localizar, "sel_tipo": por_tipo, "sel_atributo": por_atributo,
         "sel_inverter": inverter, "sel_limpar": limpar, "conjuntos": conjuntos}
