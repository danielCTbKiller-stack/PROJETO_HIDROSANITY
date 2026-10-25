"""Componentes do modelo: opções de cálculo, padrões, controles, central de demanda, zonas, bibliotecas,
protótipos, perdas localizadas, extensões de dados, estação elevatória, rotação variável, topologia
ativa, ponto cotado e anotações.

As tabelas sem geometria (padrões, controles, opções, materiais) são gravadas no cadastro ao clicar em
OK, porque o motor lê o arquivo. Mudanças em elementos ficam na edição até Salvar edições, como no desenho.
"""
import os

from qgis.core import QgsFeature, QgsFeatureRequest, QgsField, QgsProject, QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .util import NOMES, PONTOS, Dialogo, eixo, figura, ids_selecionados, num, selecionar_ids

MATERIAIS = ["PVC PBA", "PVC DEFoFo", "PEAD", "Ferro fundido dúctil", "Ferro fundido cinzento", "Aço", "Cimento-amianto"]


def _tabela_camada(nucleo, nome):
    try:
        return nucleo.camada(nome)
    except LookupError:
        nucleo.aviso(f"O cadastro não tem a tabela '{nome}'.")
        return None


def _gravar(nucleo, lyr):
    if lyr.isEditable() and lyr.isModified():
        if not lyr.commitChanges(False):
            nucleo.aviso(f"Não consegui gravar {lyr.name()}: {'; '.join(lyr.commitErrors())}")
            return False
        lyr.startEditing()
    return True


def _substituir(nucleo, lyr, linhas, campos):
    """Troca todo o conteúdo de uma tabela sem geometria pelas linhas [{campo: valor}] e grava."""
    if not lyr.isEditable():
        lyr.startEditing()
    lyr.deleteFeatures([f.id() for f in lyr.getFeatures()])
    feats = []
    for lin in linhas:
        f = QgsFeature(lyr.fields())
        for c in campos:
            f[c] = lin.get(c)
        feats.append(f)
    lyr.addFeatures(feats)
    ok = lyr.commitChanges(False)
    if not ok:
        nucleo.aviso(f"Não consegui gravar {lyr.name()}: {'; '.join(lyr.commitErrors())}")
        lyr.rollBack()
    return ok


# ================================================================ opções de cálculo
OPCOES = [("duracao_h", "Duração (h)", "24"), ("passo_hidraulico_min", "Passo hidráulico (min)", "15"),
          ("passo_padrao_min", "Passo dos padrões (min)", "15"), ("perda_carga", "Fórmula de perda de carga", "H-W"),
          ("unidades", "Unidades de vazão", "LPS"), ("modelo_demanda", "Modelo de demanda", "PDA"),
          ("pressao_minima", "Pressão mínima PDA (mca)", "0"), ("pressao_requerida", "Pressão requerida PDA (mca)", "10")]


def opcoes(nucleo):
    lyr = _tabela_camada(nucleo, "opcoes_simulacao")
    if lyr is None:
        return
    atual = {f["chave"]: str(f["valor"]) for f in lyr.getFeatures()}
    d = Dialogo(nucleo.janela, "Opções de cálculo",
                "Valem para o Calcular e para todas as análises. Com demanda dependente da pressão (PDA, padrão do "
                "GWATER) o nó com pressão abaixo da requerida recebe menos água, em vez de o cálculo falhar; com DDA "
                "a demanda é entregue sempre (podem aparecer pressões negativas).")
    w = {}
    for chave, rot, padrao in OPCOES:
        if chave == "perda_carga":
            c = QComboBox()
            c.addItems(["H-W", "D-W", "C-M"])
            c.setToolTip("H-W = Hazen-Williams (C dos materiais). D-W = Darcy-Weisbach (rugosidade em mm). "
                         "C-M = Chezy-Manning.")
            c.setCurrentText(atual.get(chave, padrao))
        elif chave == "modelo_demanda":
            c = QComboBox()
            c.addItem("PDA - demanda dependente da pressão", "PDA")
            c.addItem("DDA - demanda fixa", "DDA")
            c.setCurrentIndex(0 if atual.get(chave, padrao).upper() == "PDA" else 1)
        elif chave == "unidades":
            c = QComboBox()
            c.addItems(["LPS"])
            c.setToolTip("O cadastro trabalha em L/s")
        else:
            c = QDoubleSpinBox()
            c.setRange(0, 10000)
            c.setDecimals(1 if "pressao" in chave else 0)
            c.setValue(float(atual.get(chave, padrao) or padrao))
        w[chave] = d.linha(rot + ":", c)
    proj = QCheckBox("Incluir os elementos PROJETADOS no cálculo (obra proposta)")
    proj.setChecked(nucleo.projetados())
    d.lay.addWidget(proj)
    d.botoes("Gravar")
    if not d.exec():
        return
    novos = {}
    for chave, c in w.items():
        if isinstance(c, QComboBox):
            novos[chave] = c.currentData() or c.currentText()
        else:
            novos[chave] = f"{c.value():g}"
    for k, v in atual.items():
        novos.setdefault(k, v)
    if _substituir(nucleo, lyr, [{"chave": k, "valor": v} for k, v in novos.items()], ["chave", "valor"]):
        nucleo.dock.projetados.setChecked(proj.isChecked())
        nucleo.informar("Opções de cálculo gravadas.")


# ================================================================ padrões de consumo
def padroes(nucleo):
    lyr = _tabela_camada(nucleo, "padrao_consumo")
    if lyr is None:
        return
    dados = {}
    for f in lyr.getFeatures():
        dados.setdefault(str(f["id_padrao"]), []).append((int(f["passo"]), float(f["multiplicador"] or 0)))
    dados = {k: [m for _, m in sorted(v)] for k, v in dados.items()}
    passo_min = 15
    try:
        for f in nucleo.camada("opcoes_simulacao").getFeatures():
            if f["chave"] == "passo_padrao_min":
                passo_min = int(float(f["valor"]))
    except LookupError:
        pass
    d = Dialogo(nucleo.janela, "Padrões de consumo",
                f"Multiplicadores da demanda ao longo do dia (um por passo de {passo_min} min). A demanda de cada nó "
                "é a demanda base × o multiplicador do momento. Cole uma coluna do Excel na tabela para preencher.",
                largura=900)
    h = QHBoxLayout()
    esq = QVBoxLayout()
    lista = QListWidget()
    lista.addItems(sorted(dados))
    esq.addWidget(lista, 1)
    for texto, f in (("Novo", None), ("Duplicar", None), ("Renomear", None), ("Excluir", None)):
        b = QPushButton(texto)
        b.setObjectName(texto)
        esq.addWidget(b)
    h.addLayout(esq)
    meio = QVBoxLayout()
    tab = QTableWidget(0, 2)
    tab.setHorizontalHeaderLabels(["Hora", "Multiplicador"])
    tab.verticalHeader().setVisible(False)
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    meio.addWidget(tab, 1)
    info = QLabel()
    meio.addWidget(info)
    hb = QHBoxLayout()
    b_norm = QPushButton("Normalizar média = 1")
    b_norm.setToolTip("Divide todos os multiplicadores pela média: a demanda base passa a ser a média do dia")
    b_24 = QPushButton("Digitar 24 valores (por hora)")
    hb.addWidget(b_norm)
    hb.addWidget(b_24)
    meio.addLayout(hb)
    h.addLayout(meio, 1)
    gw, fig = figura(d, 3)
    h.addWidget(gw, 2)
    d.lay.addLayout(h, 1)
    estado = {"atual": None, "mexendo": False}

    def hora(i):
        m = i * passo_min
        return f"{m // 60:02d}:{m % 60:02d}"

    def mostrar():
        it = lista.currentItem()
        estado["mexendo"] = True
        tab.setRowCount(0)
        if not it:
            estado["mexendo"] = False
            return
        estado["atual"] = it.text()
        ms = dados[it.text()]
        tab.setRowCount(len(ms))
        for i, m in enumerate(ms):
            a = QTableWidgetItem(hora(i))
            a.setFlags(a.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tab.setItem(i, 0, a)
            tab.setItem(i, 1, QTableWidgetItem(f"{m:g}"))
        estado["mexendo"] = False
        grafico()

    def grafico():
        fig.clear()
        ax = eixo(fig, titulo=estado["atual"] or "", x="hora", y="multiplicador")
        ms = dados.get(estado["atual"], [])
        if ms:
            xs = [i * passo_min / 60 for i in range(len(ms) + 1)]
            ax.step(xs, ms + [ms[-1]], where="post", color=COR["cyan"], linewidth=1.8)
            ax.axhline(1, color=COR["muted"], linestyle=":", linewidth=0.8)
            ax.set_xlim(0, xs[-1])
            ax.set_xticks(range(0, int(xs[-1]) + 1, 3))
            media = sum(ms) / len(ms)
            info.setText(f"{len(ms)} passos · média {num(media, 3)} · mín {num(min(ms), 2)} · máx {num(max(ms), 2)}"
                         + ("" if abs(media - 1) < 0.02 else "  ⚠ a média não é 1: a demanda base não é a média do dia"))
        gw.canvas.draw_idle()

    def editou(it):
        if estado["mexendo"] or it.column() != 1 or not estado["atual"]:
            return
        try:
            dados[estado["atual"]][it.row()] = float(it.text().replace(",", "."))
        except ValueError:
            it.setText(f"{dados[estado['atual']][it.row()]:g}")
        grafico()

    def colar_evento(e):
        from qgis.PyQt.QtWidgets import QApplication
        if e.key() == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier and estado["atual"]:
            linhas = [l.strip().split("\t")[-1] for l in QApplication.clipboard().text().strip().splitlines()]
            ini = max(tab.currentRow(), 0)
            for i, t in enumerate(linhas):
                if ini + i < len(dados[estado["atual"]]):
                    try:
                        dados[estado["atual"]][ini + i] = float(t.replace(",", "."))
                    except ValueError:
                        pass
            mostrar()
        else:
            QTableWidget.keyPressEvent(tab, e)
    tab.keyPressEvent = colar_evento

    def novo():
        nome, ok = QInputDialog.getText(d, "Novo padrão", "Nome do padrão (ex.: PAD_COMERCIAL):")
        if ok and nome.strip() and nome.strip() not in dados:
            dados[nome.strip()] = [1.0] * (24 * 60 // passo_min)
            lista.addItem(nome.strip())
            lista.setCurrentRow(lista.count() - 1)

    def duplicar():
        if estado["atual"]:
            nome, ok = QInputDialog.getText(d, "Duplicar", "Nome da cópia:", text=estado["atual"] + "_2")
            if ok and nome.strip() and nome.strip() not in dados:
                dados[nome.strip()] = list(dados[estado["atual"]])
                lista.addItem(nome.strip())

    def renomear():
        it = lista.currentItem()
        if it:
            nome, ok = QInputDialog.getText(d, "Renomear", "Novo nome:", text=it.text())
            if ok and nome.strip() and nome.strip() not in dados:
                dados[nome.strip()] = dados.pop(it.text())
                estado.setdefault("renomes", {})[it.text()] = nome.strip()
                it.setText(nome.strip())
                estado["atual"] = nome.strip()

    def excluir():
        it = lista.currentItem()
        if it and QMessageBox.question(d, "Excluir", f"Excluir o padrão {it.text()}? Os nós que usam este padrão "
                                       "ficarão com demanda constante.") == QMessageBox.StandardButton.Yes:
            dados.pop(it.text())
            lista.takeItem(lista.row(it))

    def normalizar():
        if estado["atual"]:
            ms = dados[estado["atual"]]
            m = sum(ms) / len(ms)
            if m > 0:
                dados[estado["atual"]] = [round(x / m, 4) for x in ms]
                mostrar()

    def vinte_quatro():
        if not estado["atual"]:
            return
        txt, ok = QInputDialog.getMultiLineText(d, "24 valores", "Um multiplicador por hora (00 h a 23 h), um por linha "
                                                "ou separados por ponto e vírgula:")
        if not ok:
            return
        vals = [float(x.replace(",", ".")) for x in txt.replace(";", "\n").split() if x.strip()]
        if len(vals) != 24:
            return nucleo.aviso(f"São 24 valores; vieram {len(vals)}.")
        por_hora = 60 // passo_min
        dados[estado["atual"]] = [v for v in vals for _ in range(por_hora)]
        mostrar()

    for b in d.findChildren(QPushButton):
        f = {"Novo": novo, "Duplicar": duplicar, "Renomear": renomear, "Excluir": excluir}.get(b.objectName())
        if f:
            b.clicked.connect(f)
    b_norm.clicked.connect(normalizar)
    b_24.clicked.connect(vinte_quatro)
    lista.currentItemChanged.connect(lambda *_: mostrar())
    tab.itemChanged.connect(editou)
    if lista.count():
        lista.setCurrentRow(0)
    d.resize(1100, 600)
    d.botoes("Gravar")
    if not d.exec():
        return
    linhas = [{"id_padrao": k, "passo": i, "multiplicador": m} for k, ms in dados.items() for i, m in enumerate(ms)]
    if _substituir(nucleo, lyr, linhas, ["id_padrao", "passo", "multiplicador"]):
        ren = estado.get("renomes", {})
        if ren:
            nos = nucleo.camada("no_juncao")
            if not nos.isEditable():
                nos.startEditing()
            i = nos.fields().indexOf("padrao")
            for f in nos.getFeatures():
                if str(f["padrao"]) in ren:
                    nos.changeAttributeValue(f.id(), i, ren[str(f["padrao"])])
        nucleo.informar(f"{len(dados)} padrão(ões) gravado(s).")


# ================================================================ controles
CONDICOES = {"NIVEL_ABAIXO": "nível do reservatório abaixo de", "NIVEL_ACIMA": "nível do reservatório acima de",
             "PRESSAO_ABAIXO": "pressão no nó abaixo de", "PRESSAO_ACIMA": "pressão no nó acima de",
             "HORA": "na hora do dia (h)"}


def controles(nucleo):
    lyr = _tabela_camada(nucleo, "controle")
    if lyr is None:
        return
    d = Dialogo(nucleo.janela, "Controles",
                "Regras de operação, como os Controls do WaterGEMS: a bomba ou válvula muda de estado quando a "
                "condição acontece. Ex.: B1 ABERTA se o nível de R1 ficar abaixo de 2,5 m; B1 FECHADA se passar de 5,3 m.",
                largura=820)
    tab = QTableWidget(0, 5)
    tab.setHorizontalHeaderLabels(["Elemento (bomba/válvula)", "Ação", "Condição", "Nó de referência", "Valor"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    d.lay.addWidget(tab, 1)
    elementos = []
    for c in ("bomba", "valvula"):
        try:
            elementos += [str(f["id"]) for f in nucleo.camada(c).getFeatures()]
        except LookupError:
            pass
    refs = []
    for c in ("reservatorio", "no_juncao", "captacao"):
        try:
            refs += [str(f["id"]) for f in nucleo.camada(c).getFeatures()]
        except LookupError:
            pass

    def linha(r=None):
        r = r or {}
        i = tab.rowCount()
        tab.insertRow(i)
        e = QComboBox()
        e.setEditable(True)
        e.addItems(elementos)
        e.setCurrentText(str(r.get("elemento") or (elementos[0] if elementos else "")))
        a = QComboBox()
        a.addItems(["ABERTA", "FECHADA"])
        a.setCurrentText(str(r.get("acao") or "ABERTA"))
        c = QComboBox()
        for k, t in CONDICOES.items():
            c.addItem(t, k)
        c.setCurrentIndex(max(0, c.findData(r.get("condicao") or "NIVEL_ABAIXO")))
        n = QComboBox()
        n.setEditable(True)
        n.addItems([""] + refs)
        n.setCurrentText(str(r.get("no_ref") or ""))
        v = QDoubleSpinBox()
        v.setRange(-1000, 10000)
        v.setDecimals(2)
        v.setValue(float(r.get("valor") or 0))
        for j, w in enumerate((e, a, c, n, v)):
            tab.setCellWidget(i, j, w)

    for f in lyr.getFeatures():
        linha({k: f[k] for k in ("elemento", "acao", "condicao", "no_ref", "valor")})
    h = QHBoxLayout()
    b = QPushButton("Novo controle")
    b.clicked.connect(lambda: linha())
    h.addWidget(b)
    b = QPushButton("Excluir linha")
    b.clicked.connect(lambda: tab.removeRow(tab.currentRow()) if tab.currentRow() >= 0 else None)
    h.addWidget(b)
    h.addStretch(1)
    d.lay.addLayout(h)
    d.resize(900, 420)
    d.botoes("Gravar")
    if not d.exec():
        return
    linhas = []
    for i in range(tab.rowCount()):
        e, a, c, n, v = (tab.cellWidget(i, j) for j in range(5))
        if not e.currentText().strip():
            continue
        linhas.append({"elemento": e.currentText().strip(), "acao": a.currentText(), "condicao": c.currentData(),
                       "no_ref": n.currentText().strip() or None, "valor": v.value()})
    if _substituir(nucleo, lyr, linhas, ["elemento", "acao", "condicao", "no_ref", "valor"]):
        nucleo.informar(f"{len(linhas)} controle(s) gravado(s).")


# ================================================================ central de demanda
def central_demanda(nucleo):
    if not nucleo.cadastro():
        return
    nos = nucleo.camada("no_juncao")
    pads = sorted({str(f["id_padrao"]) for f in nucleo.camada("padrao_consumo").getFeatures()}) \
        if _tem(nucleo, "padrao_consumo") else []
    d = Dialogo(nucleo.janela, "Central de demanda",
                "Todos os nós com demanda base (L/s), padrão e setor. Edite na tabela, ou selecione linhas e use os "
                "botões. As mudanças ficam na edição: Salvar edições grava no cadastro.", largura=900)
    tab = QTableWidget(0, 5)
    tab.setHorizontalHeaderLabels(["Nó", "Tipo", "Demanda base (L/s)", "Padrão", "Setor"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tab.setSortingEnabled(True)
    d.lay.addWidget(tab, 1)
    total = QLabel()
    total.setStyleSheet(f"color:{COR['cyan']}; font-weight:600")
    d.lay.addWidget(total)
    estado = {"mexendo": False}
    fids = {}

    def carregar():
        estado["mexendo"] = True
        tab.setSortingEnabled(False)
        feats = list(nos.getFeatures())
        tab.setRowCount(len(feats))
        for i, f in enumerate(feats):
            fids[i] = f.id()
            vals = [f["id"], f["tipo"], f["demanda_base"], f["padrao"], f["setor"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem()
                if j == 2:
                    it.setData(Qt.ItemDataRole.DisplayRole, float(v or 0) if str(v) != "NULL" else 0.0)
                else:
                    it.setText("" if v is None or str(v) == "NULL" else str(v))
                if j in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setData(Qt.ItemDataRole.UserRole, f.id())
                tab.setItem(i, j, it)
        tab.setSortingEnabled(True)
        estado["mexendo"] = False
        somar()

    def somar():
        s = sum(float(f["demanda_base"] or 0) for f in nos.getFeatures() if str(f["demanda_base"]) != "NULL")
        n = sum(1 for f in nos.getFeatures() if float(f["demanda_base"] or 0) > 0)
        total.setText(f"Total: {num(s, 3)} L/s ({num(s * 86.4, 0)} m³/dia) em {n} nós com demanda")

    def mudar(it):
        if estado["mexendo"] or it.column() < 2:
            return
        if not nos.isEditable():
            nos.startEditing()
        campo = {2: "demanda_base", 3: "padrao", 4: "setor"}[it.column()]
        v = it.text().strip()
        if campo == "demanda_base":
            try:
                v = float(v.replace(",", ".") or 0)
            except ValueError:
                return
        nos.changeAttributeValue(it.data(Qt.ItemDataRole.UserRole), nos.fields().indexOf(campo), v or None)
        somar()

    def linhas_sel():
        return sorted({i.row() for i in tab.selectedIndexes()}) or list(range(tab.rowCount()))

    def multiplicar():
        f, ok = QInputDialog.getDouble(d, "Multiplicar", "Fator (ex.: 1,2 = +20%; vale para as linhas selecionadas ou "
                                       "todas):", 1.0, 0, 100, 3)
        if not ok:
            return
        if not nos.isEditable():
            nos.startEditing()
        i = nos.fields().indexOf("demanda_base")
        fids = [tab.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in linhas_sel()]
        req = QgsFeatureRequest().setFilterFids(fids).setSubsetOfAttributes(["demanda_base"], nos.fields())
        atuais = {g.id(): g["demanda_base"] for g in nos.getFeatures(req)}
        nos.beginEditCommand("Multiplicar demandas")
        for fid in fids:
            nos.changeAttributeValue(fid, i, round(float(atuais.get(fid) or 0) * f, 5))
        nos.endEditCommand()
        carregar()

    def padrao():
        p, ok = QInputDialog.getItem(d, "Padrão", "Padrão para as linhas selecionadas (ou todas):", [""] + pads, 0, True)
        if not ok:
            return
        if not nos.isEditable():
            nos.startEditing()
        i = nos.fields().indexOf("padrao")
        for r in linhas_sel():
            nos.changeAttributeValue(tab.item(r, 0).data(Qt.ItemDataRole.UserRole), i, p or None)
        carregar()

    def distribuir():
        nucleo.executar("demanda")
        carregar()

    def no_mapa():
        selecionar_ids(nucleo, [tab.item(r, 0).text() for r in sorted({i.row() for i in tab.selectedIndexes()})])

    h = QHBoxLayout()
    for texto, f in (("Multiplicar…", multiplicar), ("Padrão…", padrao), ("Distribuir uma vazão total…", distribuir),
                     ("Selecionar no mapa", no_mapa)):
        b = QPushButton(texto)
        b.clicked.connect(f)
        h.addWidget(b)
    h.addStretch(1)
    d.lay.addLayout(h)
    tab.itemChanged.connect(mudar)
    carregar()
    d.resize(950, 620)
    d.botoes(None, "Fechar")
    d.exec()


def _tem(nucleo, c):
    try:
        nucleo.camada(c)
        return True
    except LookupError:
        return False


# ================================================================ zonas (setores)
def zonas(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Zonas",
                "Setores da rede (campo setor de cada elemento), como as Zones do WaterGEMS. Selecione elementos no "
                "mapa e atribua a uma zona; Colorir mostra as zonas no mapa.", largura=620)
    lista = QListWidget()
    d.lay.addWidget(lista, 1)

    def contar():
        cont = {}
        for lyr in nucleo.camadas_rede():
            if lyr.fields().indexOf("setor") < 0:
                continue
            for f in lyr.getFeatures():
                s = f["setor"]
                s = "(sem zona)" if s is None or str(s) in ("", "NULL") else str(s)
                cont[s] = cont.get(s, 0) + 1
        lista.clear()
        for s, n in sorted(cont.items()):
            lista.addItem(f"{s}  ·  {n} elementos")
            lista.item(lista.count() - 1).setData(Qt.ItemDataRole.UserRole, s)

    def atribuir(zona=None):
        if zona is None:
            it = lista.currentItem()
            zona, ok = QInputDialog.getText(d, "Zona", "Nome da zona para os elementos selecionados:",
                                            text=(it.data(Qt.ItemDataRole.UserRole) if it else "") .replace("(sem zona)", ""))
            if not ok:
                return
        n = 0
        for lyr, fids in nucleo.janela.selecionados():
            i = lyr.fields().indexOf("setor")
            if i < 0:
                continue
            if not lyr.isEditable():
                lyr.startEditing()
            lyr.beginEditCommand("Zona")
            for fid in fids:
                lyr.changeAttributeValue(fid, i, zona.strip() or None)
                n += 1
            lyr.endEditCommand()
        if not n:
            nucleo.informar("Selecione os elementos no mapa antes de atribuir a zona.")
        contar()

    def selecionar():
        it = lista.currentItem()
        if not it:
            return
        z = it.data(Qt.ItemDataRole.UserRole)
        expr = "\"setor\" IS NULL OR \"setor\" = ''" if z == "(sem zona)" else f"\"setor\" = '{z}'"
        for lyr in nucleo.camadas_rede():
            lyr.selectByExpression(expr)
        nucleo.janela._selecao_mudou()

    def renomear():
        it = lista.currentItem()
        if not it or it.data(Qt.ItemDataRole.UserRole) == "(sem zona)":
            return
        velho = it.data(Qt.ItemDataRole.UserRole)
        novo, ok = QInputDialog.getText(d, "Renomear zona", "Novo nome:", text=velho)
        if not ok or not novo.strip():
            return
        for lyr in nucleo.camadas_rede():
            i = lyr.fields().indexOf("setor")
            if i < 0:
                continue
            if not lyr.isEditable():
                lyr.startEditing()
            for f in lyr.getFeatures(f"\"setor\" = '{velho}'"):
                lyr.changeAttributeValue(f.id(), i, novo.strip())
        contar()

    def colorir():
        from .util import camada_resultado, cores_categorias
        valores = {}
        for lyr in nucleo.camadas_rede():
            if lyr.fields().indexOf("setor") >= 0:
                for f in lyr.getFeatures():
                    if f["setor"] not in (None, "") and str(f["setor"]) != "NULL":
                        valores[str(f["id"])] = str(f["setor"])
        zs = sorted(set(valores.values()))
        cores = cores_categorias(len(zs))
        cat = {z: (c, z) for z, c in zip(zs, cores)}
        camada_resultado(nucleo, "Zonas (setores) · tubulações", valores, "zona", categorias=cat, camadas=["trecho"])
        camada_resultado(nucleo, "Zonas (setores) · nós", valores, "zona", categorias=cat,
                         camadas=[c for c in PONTOS if _tem(nucleo, c)])

    h = QHBoxLayout()
    for texto, f in (("Atribuir à seleção…", atribuir), ("Selecionar a zona", selecionar), ("Renomear…", renomear),
                     ("Colorir no mapa", colorir)):
        b = QPushButton(texto)
        b.clicked.connect(lambda _=False, fn=f: fn())
        h.addWidget(b)
    d.lay.addLayout(h)
    contar()
    d.botoes(None, "Fechar")
    d.exec()


# ================================================================ bibliotecas de engenharia
CUSTO_PADRAO = {50: 180, 75: 220, 100: 280, 150: 390, 200: 520, 250: 680, 300: 850, 350: 1050, 400: 1250, 500: 1700,
                600: 2200}
VIDA_PADRAO = {"PVC PBA": 50, "PVC DEFoFo": 50, "PEAD": 60, "Ferro fundido dúctil": 80, "Ferro fundido cinzento": 70,
               "Aço": 50, "Cimento-amianto": 40}


def biblioteca(nucleo):
    """{"custos": {dn: R$/m}, "vida": {material: anos}} guardados no projeto."""
    b = nucleo.janela._ler_json("biblioteca", {})
    return {"custos": {int(k): float(v) for k, v in (b.get("custos") or CUSTO_PADRAO).items()},
            "vida": {**VIDA_PADRAO, **(b.get("vida") or {})}}


def bibliotecas(nucleo):
    lyr = _tabela_camada(nucleo, "dominio_material")
    if lyr is None:
        return
    bib = biblioteca(nucleo)
    d = Dialogo(nucleo.janela, "Bibliotecas de engenharia",
                "Materiais (C de Hazen-Williams usado quando a tubulação não tem rugosidade, e vida útil usada na "
                "Renovação de redes) e diâmetros comerciais com custo por metro (Dimensionamento e Renovação).",
                largura=760)
    h = QHBoxLayout()
    t1 = QTableWidget(0, 3)
    t1.setHorizontalHeaderLabels(["Material", "C (Hazen-Williams)", "Vida útil (anos)"])
    t1.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t1.verticalHeader().setVisible(False)
    for f in lyr.getFeatures():
        i = t1.rowCount()
        t1.insertRow(i)
        t1.setItem(i, 0, QTableWidgetItem(str(f["material"])))
        t1.setItem(i, 1, QTableWidgetItem(f"{float(f['rugosidade_hw'] or 0):g}"))
        t1.setItem(i, 2, QTableWidgetItem(f"{bib['vida'].get(str(f['material']), 50):g}"))
    v1 = QVBoxLayout()
    v1.addWidget(QLabel("<b>Materiais</b>"))
    v1.addWidget(t1, 1)
    b = QPushButton("Novo material")
    b.clicked.connect(lambda: (t1.insertRow(t1.rowCount()),
                               [t1.setItem(t1.rowCount() - 1, j, QTableWidgetItem(x)) for j, x in
                                enumerate(("Novo material", "130", "50"))]))
    v1.addWidget(b)
    h.addLayout(v1, 3)
    t2 = QTableWidget(0, 2)
    t2.setHorizontalHeaderLabels(["DN (mm)", "Custo (R$/m)"])
    t2.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t2.verticalHeader().setVisible(False)
    for dn, c in sorted(bib["custos"].items()):
        i = t2.rowCount()
        t2.insertRow(i)
        t2.setItem(i, 0, QTableWidgetItem(str(dn)))
        t2.setItem(i, 1, QTableWidgetItem(f"{c:g}"))
    v2 = QVBoxLayout()
    v2.addWidget(QLabel("<b>Diâmetros comerciais</b>"))
    v2.addWidget(t2, 1)
    b = QPushButton("Novo diâmetro")
    b.clicked.connect(lambda: (t2.insertRow(t2.rowCount()), t2.setItem(t2.rowCount() - 1, 0, QTableWidgetItem("700")),
                               t2.setItem(t2.rowCount() - 1, 1, QTableWidgetItem("2800"))))
    v2.addWidget(b)
    h.addLayout(v2, 2)
    d.lay.addLayout(h, 1)
    d.resize(820, 480)
    d.botoes("Gravar")
    if not d.exec():
        return
    linhas, vida = [], {}
    for i in range(t1.rowCount()):
        m = t1.item(i, 0).text().strip() if t1.item(i, 0) else ""
        if not m:
            continue
        try:
            linhas.append({"material": m, "rugosidade_hw": float(t1.item(i, 1).text().replace(",", "."))})
            vida[m] = float(t1.item(i, 2).text().replace(",", ".")) if t1.item(i, 2) else 50
        except (ValueError, AttributeError):
            pass
    custos = {}
    for i in range(t2.rowCount()):
        try:
            custos[int(float(t2.item(i, 0).text()))] = float(t2.item(i, 1).text().replace(",", "."))
        except (ValueError, AttributeError):
            pass
    if _substituir(nucleo, lyr, linhas, ["material", "rugosidade_hw"]):
        nucleo.janela.gravar_json("biblioteca", {"custos": custos, "vida": vida})
        nucleo.informar("Bibliotecas gravadas.")


# ================================================================ protótipos
CAMPOS_PROTOTIPO = {
    "no_juncao": [("tipo", ["JUNCAO", "CONSUMO", "HIDRANTE", "PONTA"]), ("demanda_base", float), ("padrao", str),
                  ("setor", str)],
    "valvula": [("tipo", ["PRV", "PSV", "PBV", "FCV", "TCV", "GPV"]), ("diametro", float), ("ajuste", float),
                ("status", ["ATIVA", "INATIVA", "ABERTA", "FECHADA"])],
    "bomba": [("curva", str), ("status_inicial", ["ABERTA", "FECHADA"]), ("rotacao_relativa", float),
              ("elevatoria", str)],
    "reservatorio": [("cota_fundo", float), ("nivel_ini", float), ("nivel_min", float), ("nivel_max", float),
                     ("diametro", float)],
    "captacao": [("carga_hidraulica", float)],
    "trecho": [("status", ["ABERTO", "FECHADO", "CV"]), ("ano_instalacao", float), ("setor", str)],
}


def prototipos(nucleo):
    if not nucleo.cadastro():
        return
    janela, dock = nucleo.janela, nucleo.dock
    d = Dialogo(janela, "Protótipos",
                "Valores que cada elemento desenhado já recebe, como os Prototypes do WaterGEMS. Vazio = sem valor "
                "padrão (o formulário pede).", largura=720)
    from qgis.PyQt.QtWidgets import QFormLayout, QGroupBox, QTabWidget
    abas = QTabWidget()
    # tubulação: DN, material e situação ficam nos campos do núcleo (os mesmos do plugin)
    g = QWidget()
    f = QFormLayout(g)
    dn = QComboBox()
    dn.setEditable(True)
    dn.addItems(["50", "75", "100", "150", "200", "250", "300", "350", "400", "500", "600"])
    dn.setCurrentText(dock.dn.currentText())
    mat = QComboBox()
    mat.addItems([dock.material.itemText(i) for i in range(dock.material.count())])
    mat.setCurrentText(dock.material.currentText())
    sit = QComboBox()
    sit.addItems(["EXISTENTE", "PROJETADO"])
    sit.setCurrentText(dock.situacao.currentText())
    f.addRow("DN (mm):", dn)
    f.addRow("Material:", mat)
    f.addRow("Situação (todos os elementos):", sit)
    auto = QCheckBox("Ligar automaticamente (nós nas pontas e divisões)")
    auto.setChecked(dock.auto.isChecked())
    form = QCheckBox("Abrir o formulário a cada elemento desenhado")
    form.setChecked(dock.formulario.isChecked())
    f.addRow(auto)
    f.addRow(form)
    campos = {}
    extras = janela.prototipos_tipo
    for c, lista in CAMPOS_PROTOTIPO.items():
        w = g if c == "trecho" else QWidget()
        fl = f if c == "trecho" else QFormLayout(w)
        for nome, tipo in lista:
            atual = extras.get(c, {}).get(nome)
            if isinstance(tipo, list):
                ed = QComboBox()
                ed.addItems([""] + tipo)
                ed.setCurrentText("" if atual is None else str(atual))
            else:
                ed = QLineEdit("" if atual is None else str(atual))
            campos[(c, nome)] = (ed, tipo)
            fl.addRow(nome + ":", ed)
        if c != "trecho":
            abas.addTab(w, NOMES[c])
    abas.insertTab(0, g, "Tubulação e geral")
    abas.setCurrentIndex(0)
    d.lay.addWidget(abas, 1)
    d.botoes("Gravar")
    if not d.exec():
        return
    for w in (dock.dn, dock.material, dock.situacao, dock.auto, dock.formulario):
        w.blockSignals(True)
    dock.dn.setCurrentText(dn.currentText())
    dock.material.setCurrentText(mat.currentText())
    dock.situacao.setCurrentText(sit.currentText())
    dock.auto.setChecked(auto.isChecked())
    dock.formulario.setChecked(form.isChecked())
    for w in (dock.dn, dock.material, dock.situacao, dock.auto, dock.formulario):
        w.blockSignals(False)
    nucleo.prototipo_mudou()
    novos = {}
    for (c, nome), (ed, tipo) in campos.items():
        txt = ed.currentText() if isinstance(ed, QComboBox) else ed.text().strip()
        if txt == "":
            continue
        if tipo is float:
            try:
                novos.setdefault(c, {})[nome] = float(txt.replace(",", "."))
            except ValueError:
                continue
        else:
            novos.setdefault(c, {})[nome] = txt
    janela.prototipos_tipo = novos
    janela.gravar_json("prototipos_tipo", novos)
    # valores padrão nas camadas (o desenho já nasce com eles)
    from qgis.core import QgsDefaultValue
    for c, vals in novos.items():
        try:
            lyr = nucleo.camada(c)
        except LookupError:
            continue
        for nome, v in vals.items():
            i = lyr.fields().indexOf(nome)
            if i >= 0:
                lyr.setDefaultValueDefinition(i, QgsDefaultValue(repr(v) if isinstance(v, str) else f"{v:g}"))
    nucleo.informar("Protótipos gravados: os próximos elementos desenhados já nascem com esses valores.")


# ================================================================ perdas localizadas
PECAS_K = [("Curva 90°", 0.9), ("Curva 45°", 0.4), ("Curva 22,5°", 0.2), ("Tê passagem direta", 0.6),
           ("Tê saída lateral", 1.3), ("Registro de gaveta aberto", 0.2), ("Registro de globo aberto", 10.0),
           ("Válvula de retenção", 2.5), ("Válvula de pé com crivo", 1.75), ("Entrada de canalização", 0.5),
           ("Saída de canalização", 1.0), ("Redução gradual", 0.15), ("Ampliação gradual", 0.3),
           ("Hidrômetro / medidor", 2.5)]


def perdas(nucleo):
    if not nucleo.cadastro():
        return
    tr = nucleo.camada("trecho")
    n = tr.selectedFeatureCount()
    d = Dialogo(nucleo.janela, "Perdas localizadas",
                "Monte o coeficiente K somando as peças de cada tubulação (valores de referência, como a biblioteca "
                f"Minor Loss do WaterGEMS). Será aplicado em {n} tubulação(ões) selecionada(s)."
                if n else "Selecione as tubulações no mapa primeiro: o K é aplicado nelas.")
    qtd = {}
    for nome, k in PECAS_K:
        s = QSpinBox()
        s.setRange(0, 50)
        qtd[nome] = (s, k)
        d.linha(f"{nome} (K = {num(k, 2)}):", s)
    total = QLabel("K total = 0")
    total.setStyleSheet(f"color:{COR['cyan']}; font-weight:700")
    d.lay.addWidget(total)

    def somar():
        total.setText(f"K total = {num(sum(s.value() * k for s, k in qtd.values()), 2)}")
    for s, _ in qtd.values():
        s.valueChanged.connect(somar)
    somente = QCheckBox("Somar ao K que já existe (desmarcado: substitui)")
    d.lay.addWidget(somente)
    d.botoes("Aplicar" if n else None, "Fechar")
    if not d.exec() or not n:
        return
    K = sum(s.value() * k for s, k in qtd.values())
    if not tr.isEditable():
        tr.startEditing()
    i = tr.fields().indexOf("perda_localizada")
    tr.beginEditCommand("Perdas localizadas")
    for f in tr.getFeatures(tr.selectedFeatureIds()):
        base = float(f["perda_localizada"] or 0) if somente.isChecked() and str(f["perda_localizada"]) != "NULL" else 0
        tr.changeAttributeValue(f.id(), i, round(base + K, 3))
    tr.endEditCommand()
    nucleo.informar(f"K = {num(K, 2)} aplicado em {n} tubulação(ões).")


# ================================================================ extensões de dados
def extensoes(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Extensões de dados",
                "Cria um campo novo nos elementos (User Data Extensions do WaterGEMS), por exemplo 'bairro', "
                "'data_vistoria', 'pressao_campo'. O campo aparece no formulário, nas Tabelas e nas Consultas.")
    tipo = QComboBox()
    for c in ("trecho",) + PONTOS:
        if _tem(nucleo, c):
            tipo.addItem(NOMES[c], c)
    d.linha("Elemento:", tipo)
    nome = d.linha("Nome do campo:", QLineEdit(), "Só letras minúsculas, números e _")
    t = QComboBox()
    t.addItem("Texto", QVariant.String)
    t.addItem("Número decimal", QVariant.Double)
    t.addItem("Número inteiro", QVariant.Int)
    t.addItem("Data", QVariant.Date)
    d.linha("Tipo:", t)
    d.botoes("Criar campo")
    if not d.exec():
        return
    import re
    n = re.sub(r"[^a-z0-9_]", "_", nome.text().strip().lower())
    if not n:
        return
    lyr = nucleo.camada(tipo.currentData())
    if lyr.fields().indexOf(n) >= 0:
        return nucleo.aviso(f"{lyr.name()} já tem o campo {n}.")
    if lyr.isEditable() and lyr.isModified():
        return nucleo.aviso("Salve as edições antes de criar campos.")
    ok = lyr.dataProvider().addAttributes([QgsField(n, t.currentData())])
    lyr.updateFields()
    nucleo.informar(f"Campo {n} criado em {lyr.name()}." if ok else "Não consegui criar o campo.")


# ================================================================ bombas
def estacao(nucleo):
    if not nucleo.cadastro():
        return
    b = nucleo.camada("bomba")
    if not b.selectedFeatureCount():
        estacoes = {}
        for f in b.getFeatures():
            if f["elevatoria"] not in (None, "") and str(f["elevatoria"]) != "NULL":
                estacoes.setdefault(str(f["elevatoria"]), []).append(str(f["id"]))
        txt = "\n".join(f"{e}: {', '.join(v)}" for e, v in sorted(estacoes.items())) or "nenhuma ainda"
        return QMessageBox.information(nucleo.janela, "Estações elevatórias",
                                       f"Selecione as bombas no mapa e clique de novo para agrupá-las.\n\nEstações:\n{txt}")
    nome, ok = QInputDialog.getText(nucleo.janela, "Estação elevatória",
                                    f"Nome da estação das {b.selectedFeatureCount()} bomba(s) selecionada(s):")
    if not ok:
        return
    if not b.isEditable():
        b.startEditing()
    i = b.fields().indexOf("elevatoria")
    for fid in b.selectedFeatureIds():
        b.changeAttributeValue(fid, i, nome.strip() or None)
    nucleo.informar(f"Estação {nome} com {b.selectedFeatureCount()} bomba(s).")


def bomba_variavel(nucleo):
    if not nucleo.cadastro():
        return
    b = nucleo.camada("bomba")
    if not b.selectedFeatureCount():
        return nucleo.informar("Selecione as bombas no mapa (rotação relativa: 1 = nominal; 0,8 = 80% da rotação).")
    v, ok = QInputDialog.getDouble(nucleo.janela, "Rotação variável",
                                   "Rotação relativa (1 = nominal; a curva escala pelas leis de semelhança):",
                                   1.0, 0.1, 1.5, 3)
    if not ok:
        return
    if not b.isEditable():
        b.startEditing()
    i = b.fields().indexOf("rotacao_relativa")
    for fid in b.selectedFeatureIds():
        b.changeAttributeValue(fid, i, v)
    nucleo.informar(f"Rotação {num(v, 2)} em {b.selectedFeatureCount()} bomba(s).")


# ================================================================ topologia ativa
def topologia_ativa(nucleo):
    if not nucleo.cadastro():
        return
    sel = nucleo.janela.selecionados()
    inativos = sum(1 for lyr in nucleo.camadas_rede() for f in lyr.getFeatures("\"situacao\" = 'DESATIVADO'"))
    d = Dialogo(nucleo.janela, "Topologia ativa",
                "Elemento desativado continua no cadastro mas sai do cálculo (situação DESATIVADO), como o Active "
                f"Topology do WaterGEMS. Hoje há {inativos} elemento(s) desativado(s).")
    n = sum(len(f) for _, f in sel)
    acao = QComboBox()
    if n:
        acao.addItem(f"Desativar os {n} selecionados", "desativar")
        acao.addItem(f"Reativar os {n} selecionados (EXISTENTE)", "ativar")
    acao.addItem("Selecionar todos os desativados", "ver")
    acao.addItem("Reativar todos os desativados", "todos")
    d.linha("O que fazer:", acao)
    cinza = QCheckBox("Mostrar os desativados em cinza tracejado no mapa")
    cinza.setChecked(True)
    d.lay.addWidget(cinza)
    d.botoes("Aplicar")
    if not d.exec():
        return
    a = acao.currentData()
    if a == "ver":
        for lyr in nucleo.camadas_rede():
            lyr.selectByExpression("\"situacao\" = 'DESATIVADO'")
        nucleo.janela._selecao_mudou()
        return
    alvos = sel if a in ("desativar", "ativar") else \
        [(l, [f.id() for f in l.getFeatures("\"situacao\" = 'DESATIVADO'")]) for l in nucleo.camadas_rede()]
    valor = "DESATIVADO" if a == "desativar" else "EXISTENTE"
    total = 0
    for lyr, fids in alvos:
        i = lyr.fields().indexOf("situacao")
        if i < 0 or not fids:
            continue
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand("Topologia ativa")
        for fid in fids:
            lyr.changeAttributeValue(fid, i, valor)
            total += 1
        lyr.endEditCommand()
    if cinza.isChecked():
        _estilo_desativado(nucleo)
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{total} elemento(s) {'desativado(s)' if valor == 'DESATIVADO' else 'reativado(s)'}. "
                    "Salvar edições grava no cadastro.")


def _estilo_desativado(nucleo):
    """Desativados ficam em cinza tracejado: uma camada de destaque por cima (não mexe no estilo do cadastro)."""
    from .util import camada_resultado
    vals = {}
    for lyr in nucleo.camadas_rede():
        for f in lyr.getFeatures("\"situacao\" = 'DESATIVADO'"):
            vals[str(f["id"])] = "DESATIVADO"
    pontos = [c for c in PONTOS if _tem(nucleo, c)]
    camada_resultado(nucleo, "Desativados · tubulações", vals, "situacao", categorias={"DESATIVADO": ("#9aa5b1", "desativado")},
                     camadas=["trecho"])
    camada_resultado(nucleo, "Desativados · nós", vals, "situacao", categorias={"DESATIVADO": ("#9aa5b1", "desativado")},
                     camadas=pontos)


# ================================================================ ponto cotado e anotações
def ponto_cotado(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    prj = QgsProject.instance()
    lyr = next((l for l in prj.mapLayers().values() if isinstance(l, QgsVectorLayer)
                and l.source().replace("\\", "/").lower().startswith(gpkg.replace("\\", "/").lower())
                and "layername=ponto_cotado" in l.source()), None)
    if lyr is None:
        crs = nucleo.camada("trecho").crs()
        mem = QgsVectorLayer(f"Point?crs={crs.authid()}&field=id:string&field=cota:double&field=observacao:string",
                             "ponto_cotado", "memory")
        opt = QgsVectorFileWriter.SaveVectorOptions()
        opt.driverName, opt.layerName = "GPKG", "ponto_cotado"
        opt.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        erro = QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, prj.transformContext(), opt)
        if erro[0] != QgsVectorFileWriter.WriterError.NoError:
            return nucleo.aviso(f"Não consegui criar a camada de pontos cotados: {erro[1]}")
        lyr = QgsVectorLayer(f"{gpkg}|layername=ponto_cotado", "Pontos cotados", "ogr")
        from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
        lyr.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple(
            {"name": "triangle", "color": "#c49a5a", "size": "3", "outline_color": "#3d2b10"})))
        prj.addMapLayer(lyr)
    if not lyr.isEditable():
        lyr.startEditing()
    nucleo.janela.desenhar(lyr, "ponto_cotado")
    nucleo.dock.status.setText("<b>Ponto cotado</b>: clique no mapa e informe a cota. Depois use no TRex (fonte: "
                               "Pontos cotados, camada Pontos cotados).")


def _anotacao(nucleo, tipo):
    from .ferramentas_mapa import FerramentaPoligono, FerramentaRetangulo, anotar, FerramentaClique
    janela = nucleo.janela
    if tipo == "texto":
        def clicou(_l, _f, p):
            txt, ok = QInputDialog.getText(janela, "Texto", "Texto da anotação:")
            if ok and txt.strip():
                from qgis.core import QgsGeometry
                anotar("texto", QgsGeometry.fromPointXY(p), txt.strip())
        f = FerramentaClique(janela.canvas, lambda: [], clicou, Qt.CursorShape.IBeamCursor)
    elif tipo == "linha":
        f = FerramentaPoligono(janela.canvas, False)
        f.concluido.connect(lambda g: anotar("linha", g))
    else:
        f = FerramentaRetangulo(janela.canvas)
        f.concluido.connect(lambda g: anotar("borda", g))
    janela.usar_ferramenta(f, tipo)
    nucleo.dock.status.setText(f"<b>Anotação ({tipo})</b>: as anotações ficam salvas no projeto. Esc para parar.")


ACOES = {"opcoes": opcoes, "padroes": padroes, "controles": controles, "central_demanda": central_demanda,
         "zonas": zonas, "bibliotecas": bibliotecas, "prototipos": prototipos, "perdas": perdas,
         "extensoes": extensoes, "estacao": estacao, "bomba_variavel": bomba_variavel,
         "topologia_ativa": topologia_ativa, "ponto_cotado": ponto_cotado,
         "texto": lambda n: _anotacao(n, "texto"), "linha": lambda n: _anotacao(n, "linha"),
         "borda": lambda n: _anotacao(n, "borda")}
