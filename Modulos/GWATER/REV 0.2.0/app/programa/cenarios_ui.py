"""Cenários e alternativas (Scenarios / Alternatives do WaterGEMS).

Um cenário é a rede atual + uma lista de alterações (DN, status, ajuste de válvula, demanda, nível...),
um fator de demanda global e a escolha de incluir os PROJETADOS. São as mesmas "propostas" do Centro de
Operações web: ficam nas tabelas `cenario` e `cenario_alteracao` do próprio cadastro (motor/cenarios.py).
O cenário ativo (caixa no alto do mapa) é o que Calcular e todas as análises usam.
"""
from datetime import datetime

from qgis.core import QgsFeature, QgsProject, QgsVectorFileWriter, QgsVectorLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from gwater.estilo import COR

from .tema import icone
from .util import NOMES, Dialogo, num

T_CEN, T_ALT = "cenario", "cenario_alteracao"
# campos que um cenário pode alterar (espelha EDITAVEIS de motor/cadastro_para_inp.py)
EDITAVEIS = {
    "trecho": {"diametro_nominal": float, "rugosidade_hw": float, "status": ["ABERTO", "FECHADO", "CV"],
               "situacao": ["EXISTENTE", "PROJETADO", "DESATIVADO"], "perda_localizada": float},
    "valvula": {"ajuste": float, "status": ["ATIVA", "INATIVA", "ABERTA", "FECHADA"],
                "situacao": ["EXISTENTE", "PROJETADO", "DESATIVADO"]},
    "bomba": {"status_inicial": ["ABERTA", "FECHADA"], "rotacao_relativa": float,
              "situacao": ["EXISTENTE", "PROJETADO", "DESATIVADO"]},
    "no_juncao": {"demanda_base": float, "cota": float},
    "reservatorio": {"nivel_ini": float},
    "captacao": {"carga_hidraulica": float},
}


def alteracoes_completas(c):
    alts = [dict(a) for a in c.get("alteracoes", [])]
    f = float(c.get("fator_demanda") or 1)
    if abs(f - 1) > 1e-9:
        alts.append({"camada": "global", "id": "", "campo": "fator_demanda", "valor": f})
    if c.get("modelo_demanda"):
        alts.append({"camada": "global", "id": "", "campo": "modelo_demanda", "valor": c["modelo_demanda"]})
    return alts


# ---------------------------------------------------------------- leitura e gravação no GeoPackage
def _tabela(gpkg, nome, criar=False):
    lyr = QgsVectorLayer(f"{gpkg}|layername={nome}", nome, "ogr")
    if lyr.isValid():
        return lyr
    if not criar:
        return None
    campos = {T_CEN: "field=id:string&field=nome:string&field=descricao:string&field=com_projetados:integer"
                     "&field=fator_demanda:double&field=atualizado_em:string",
              T_ALT: "field=cenario:string&field=camada:string&field=elemento:string&field=campo:string"
                     "&field=valor:string"}[nome]
    mem = QgsVectorLayer(f"None?{campos}", nome, "memory")
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName, opt.layerName = "GPKG", nome
    opt.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsProject.instance().transformContext(), opt)
    return QgsVectorLayer(f"{gpkg}|layername={nome}", nome, "ogr")


def listar(gpkg):
    cen, alt = _tabela(gpkg, T_CEN), _tabela(gpkg, T_ALT)
    if cen is None:
        return []
    alts = {}
    if alt is not None:
        for a in alt.getFeatures():
            alts.setdefault(str(a["cenario"]), []).append(
                {"camada": a["camada"], "id": a["elemento"], "campo": a["campo"], "valor": a["valor"]})
    out = []
    for c in cen.getFeatures():
        cid = str(c["id"])
        modelo = None
        lista = []
        for a in alts.get(cid, []):
            if a["camada"] == "global" and a["campo"] == "modelo_demanda":
                modelo = a["valor"]
            else:
                lista.append(a)
        out.append({"id": cid, "nome": c["nome"], "descricao": c["descricao"] if str(c["descricao"]) != "NULL" else "",
                    "com_projetados": bool(c["com_projetados"]), "fator_demanda": float(c["fator_demanda"] or 1),
                    "atualizado_em": c["atualizado_em"], "alteracoes": lista, "modelo_demanda": modelo})
    return out


def gravar(gpkg, todos):
    cen, alt = _tabela(gpkg, T_CEN, True), _tabela(gpkg, T_ALT, True)
    for lyr in (cen, alt):
        lyr.startEditing()
        lyr.deleteFeatures([f.id() for f in lyr.getFeatures()])
    for c in todos:
        f = QgsFeature(cen.fields())
        for k in ("id", "nome", "descricao", "atualizado_em"):
            f[k] = c.get(k) or ""
        f["com_projetados"] = int(bool(c.get("com_projetados")))
        f["fator_demanda"] = float(c.get("fator_demanda") or 1)
        cen.addFeature(f)
        extras = [{"camada": "global", "id": "", "campo": "modelo_demanda", "valor": c["modelo_demanda"]}] \
            if c.get("modelo_demanda") else []
        for a in c.get("alteracoes", []) + extras:
            g = QgsFeature(alt.fields())
            g["cenario"], g["camada"], g["elemento"], g["campo"], g["valor"] = \
                c["id"], a["camada"], a["id"], a["campo"], str(a["valor"])
            alt.addFeature(g)
    ok = cen.commitChanges() and alt.commitChanges()
    return ok


def _novo_id(nome, existentes):
    import re
    import unicodedata
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()[:30] or "CENARIO"
    cid, n = base, 2
    while cid in existentes:
        cid, n = f"{base}_{n}", n + 1
    return cid


# ---------------------------------------------------------------- cenário ativo
def atualizar_combo(janela):
    nucleo = janela.nucleo
    cmb = janela.cmb_cenario
    cmb.blockSignals(True)
    cmb.clear()
    cmb.addItem(icone("cenarios"), "Rede atual (base)", None)
    gpkg = nucleo.cadastro()
    ativo = nucleo.cenario["id"] if nucleo.cenario else None
    for c in (listar(gpkg) if gpkg else []):
        cmb.addItem(icone("alternativas"), f"{c['nome']}  ({len(c['alteracoes'])} alterações)", c["id"])
        if c["id"] == ativo:
            cmb.setCurrentIndex(cmb.count() - 1)
    cmb.blockSignals(False)


def ativar(nucleo, cid):
    gpkg = nucleo.cadastro()
    c = next((x for x in listar(gpkg) if x["id"] == cid), None) if cid else None
    nucleo.cenario = c
    if c is not None:
        nucleo.dock.projetados.setChecked(bool(c.get("com_projetados")))
    atualizar_combo(nucleo.janela)
    nome = c["nome"] if c else "Rede atual"
    nucleo.dock.status.setText(f"Cenário ativo: <b>{nome}</b>. Calcular (F5) roda este cenário.")
    if nucleo.res:
        nucleo.informar(f"Cenário {nome} ativo: calcule de novo para ver os resultados dele.")


# ---------------------------------------------------------------- gerenciador
def cenarios(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return nucleo.aviso("Abra um cadastro primeiro.")
    janela = nucleo.janela
    d = Dialogo(janela, "Cenários",
                "Cada cenário é a rede atual com alterações (DN, registros, ajustes de válvula, demandas, níveis), um "
                "fator de demanda e, se quiser, as obras PROJETADAS. Ative um cenário para que Calcular e as análises "
                "usem ele. São as mesmas propostas do Centro de Operações web.", largura=760)
    lista = QListWidget()
    lista.setMinimumHeight(260)
    d.lay.addWidget(lista, 1)
    info = QLabel()
    info.setWordWrap(True)
    info.setStyleSheet(f"color:{COR['muted']}")
    d.lay.addWidget(info)
    todos = listar(gpkg)

    def recarregar(sel=None):
        lista.clear()
        it = QListWidgetItem(icone("cenarios"), "Rede atual (base)")
        it.setData(Qt.ItemDataRole.UserRole, None)
        lista.addItem(it)
        for c in todos:
            ativo = " · ATIVO" if nucleo.cenario and nucleo.cenario["id"] == c["id"] else ""
            it = QListWidgetItem(icone("alternativas"), f"{c['nome']}  —  {len(c['alteracoes'])} alterações, demanda × "
                                 f"{num(c['fator_demanda'], 2)}{', com PROJETADOS' if c['com_projetados'] else ''}{ativo}")
            it.setData(Qt.ItemDataRole.UserRole, c["id"])
            lista.addItem(it)
            if c["id"] == sel:
                lista.setCurrentItem(it)
        if not nucleo.cenario:
            lista.item(0).setText("Rede atual (base) · ATIVO")

    def atual():
        it = lista.currentItem()
        cid = it.data(Qt.ItemDataRole.UserRole) if it else None
        return next((c for c in todos if c["id"] == cid), None)

    def salvar():
        if not gravar(gpkg, todos):
            nucleo.aviso("Não consegui gravar os cenários no cadastro.")
        atualizar_combo(janela)

    def novo(base=None):
        nome, ok = QInputDialog.getText(d, "Novo cenário", "Nome (ex.: Reforço do Setor S1, Demanda de 2035):")
        if not ok or not nome.strip():
            return
        c = {"id": _novo_id(nome, {x["id"] for x in todos}), "nome": nome.strip(), "descricao": "",
             "com_projetados": False, "fator_demanda": 1.0, "alteracoes": [],
             "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M")}
        if base:
            c.update({k: base[k] for k in ("com_projetados", "fator_demanda", "descricao", "modelo_demanda")
                      if k in base})
            c["alteracoes"] = [dict(a) for a in base["alteracoes"]]
        todos.append(c)
        salvar()
        recarregar(c["id"])
        alternativas(nucleo, c, todos, salvar)
        recarregar(c["id"])

    def duplicar():
        c = atual()
        if c:
            novo(c)

    def renomear():
        c = atual()
        if c:
            nome, ok = QInputDialog.getText(d, "Renomear", "Novo nome:", text=c["nome"])
            if ok and nome.strip():
                c["nome"] = nome.strip()
                salvar()
                recarregar(c["id"])

    def excluir():
        c = atual()
        if c and QMessageBox.question(d, "Excluir", f"Excluir o cenário {c['nome']}?") == QMessageBox.StandardButton.Yes:
            todos.remove(c)
            if nucleo.cenario and nucleo.cenario["id"] == c["id"]:
                nucleo.cenario = None
            salvar()
            recarregar()

    def editar():
        c = atual()
        if c:
            alternativas(nucleo, c, todos, salvar)
            recarregar(c["id"])
        else:
            nucleo.informar("A rede atual se altera direto no mapa. Para propor mudanças, crie um cenário.")

    def ativar_sel(calcular=False):
        c = atual()
        ativar(nucleo, c["id"] if c else None)
        recarregar(c["id"] if c else None)
        if calcular:
            d.accept()
            nucleo.executar("simular")

    def comparar():
        from .revisao import comparar_cenarios
        d.accept()
        comparar_cenarios(nucleo)

    def mostrar():
        c = atual()
        if not c:
            info.setText("Rede atual: o cadastro como está, sem alterações.")
            return
        alts = c["alteracoes"][:12]
        txt = "; ".join(f"{a['camada']} {a['id']}.{a['campo']} = {a['valor']}" for a in alts)
        info.setText((c.get("descricao") or "") + (" · " if c.get("descricao") else "") + (txt or "sem alterações") +
                     (" …" if len(c["alteracoes"]) > 12 else ""))

    h = QHBoxLayout()
    for texto, f in (("Novo", novo), ("Duplicar", duplicar), ("Renomear", renomear), ("Excluir", excluir),
                     ("Alternativas…", editar)):
        b = QPushButton(texto)
        b.clicked.connect(lambda _=False, fn=f: fn())
        h.addWidget(b)
    h.addStretch(1)
    for texto, f in (("Ativar", lambda: ativar_sel(False)), ("Ativar e calcular", lambda: ativar_sel(True)),
                     ("Comparar…", comparar)):
        b = QPushButton(texto)
        b.clicked.connect(f)
        h.addWidget(b)
    d.lay.addLayout(h)
    lista.currentItemChanged.connect(lambda *_: mostrar())
    lista.itemDoubleClicked.connect(lambda *_: ativar_sel(False))
    recarregar(nucleo.cenario["id"] if nucleo.cenario else None)
    d.botoes(None, "Fechar")
    d.exec()


# ---------------------------------------------------------------- alternativas (alterações de um cenário)
def alternativas(nucleo, c=None, todos=None, salvar=None):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    if c is None:
        if not nucleo.cenario:
            return nucleo.informar("Ative um cenário (caixa Cenário, no alto do mapa) ou crie um em Cenários.")
        todos = listar(gpkg)
        c = next((x for x in todos if x["id"] == nucleo.cenario["id"]), None)
        if c is None:
            return
        salvar = lambda: (gravar(gpkg, todos), atualizar_combo(nucleo.janela))
    d = Dialogo(nucleo.janela, f"Alternativas · {c['nome']}",
                "O que muda neste cenário em relação à rede atual. Para somar elementos: selecione no mapa, escolha o "
                "campo e o valor e clique em Adicionar seleção.", largura=860)
    desc = QLineEdit(c.get("descricao") or "")
    d.linha("Descrição:", desc)
    fator = QDoubleSpinBox()
    fator.setRange(0, 10)
    fator.setDecimals(3)
    fator.setSingleStep(0.05)
    fator.setValue(float(c.get("fator_demanda") or 1))
    d.linha("Fator de demanda (todos os nós):", fator, "1,2 = 20% a mais de consumo em toda a rede")
    proj = QCheckBox("Incluir os elementos PROJETADOS")
    proj.setChecked(bool(c.get("com_projetados")))
    d.lay.addWidget(proj)
    modelo = QComboBox()
    modelo.addItem("como nas Opções de cálculo", None)
    modelo.addItem("PDA - demanda dependente da pressão", "PDA")
    modelo.addItem("DDA - demanda fixa", "DDA")
    modelo.setCurrentIndex(max(0, modelo.findData(c.get("modelo_demanda"))))
    d.linha("Modelo de demanda:", modelo)
    tab = QTableWidget(0, 4)
    tab.setHorizontalHeaderLabels(["Tipo", "Elemento", "Campo", "Novo valor"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    d.lay.addWidget(tab, 1)
    atual = {}  # elemento atual no cadastro, para mostrar o valor de antes

    def linha(a):
        i = tab.rowCount()
        tab.insertRow(i)
        for j, v in enumerate((NOMES.get(a["camada"], a["camada"]), a["id"], a["campo"], str(a["valor"]))):
            it = QTableWidgetItem(v)
            it.setData(Qt.ItemDataRole.UserRole, a["camada"])
            if j < 3:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tab.setItem(i, j, it)

    for a in c["alteracoes"]:
        linha(a)
    add = QHBoxLayout()
    tipo = QComboBox()
    for k in EDITAVEIS:
        tipo.addItem(NOMES[k], k)
    campo = QComboBox()
    valor = QComboBox()
    valor.setEditable(True)

    def campos():
        campo.clear()
        campo.addItems(list(EDITAVEIS[tipo.currentData()]))

    def valores():
        valor.clear()
        t = EDITAVEIS[tipo.currentData()].get(campo.currentText())
        if isinstance(t, list):
            valor.addItems(t)
    tipo.currentIndexChanged.connect(campos)
    campo.currentIndexChanged.connect(valores)
    campos()
    add.addWidget(tipo)
    add.addWidget(campo)
    add.addWidget(valor, 1)

    def adicionar():
        cam = tipo.currentData()
        try:
            lyr = nucleo.camada(cam)
        except LookupError:
            return
        ids = [str(f["id"]) for f in lyr.getFeatures(lyr.selectedFeatureIds())]
        if not ids:
            return nucleo.informar(f"Selecione {NOMES[cam].lower()}(s) no mapa primeiro.")
        v = valor.currentText().strip().replace(",", ".") if EDITAVEIS[cam][campo.currentText()] is float else \
            valor.currentText().strip()
        if v == "":
            return
        existentes = {(tab.item(i, 1).text(), tab.item(i, 2).text()): i for i in range(tab.rowCount())}
        for eid in ids:
            if (eid, campo.currentText()) in existentes:
                tab.item(existentes[(eid, campo.currentText())], 3).setText(v)
            else:
                linha({"camada": cam, "id": eid, "campo": campo.currentText(), "valor": v})

    b = QPushButton("Adicionar seleção")
    b.setToolTip("Cria a alteração para cada elemento selecionado no mapa")
    b.clicked.connect(adicionar)
    add.addWidget(b)
    b = QPushButton("Excluir linha")
    b.clicked.connect(lambda: [tab.removeRow(r) for r in sorted({i.row() for i in tab.selectedIndexes()}, reverse=True)])
    add.addWidget(b)
    d.lay.addLayout(add)
    d.resize(900, 600)
    d.botoes("Gravar")
    if not d.exec():
        return
    c["descricao"] = desc.text()
    c["fator_demanda"] = fator.value()
    c["com_projetados"] = proj.isChecked()
    c["modelo_demanda"] = modelo.currentData()
    c["alteracoes"] = [{"camada": tab.item(i, 0).data(Qt.ItemDataRole.UserRole), "id": tab.item(i, 1).text(),
                        "campo": tab.item(i, 2).text(), "valor": tab.item(i, 3).text()} for i in range(tab.rowCount())]
    c["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    salvar()
    if nucleo.cenario and nucleo.cenario["id"] == c["id"]:
        nucleo.cenario = c
    nucleo.informar(f"Cenário {c['nome']}: {len(c['alteracoes'])} alteração(ões) gravada(s).")


ACOES = {"cenarios": cenarios, "alternativas": lambda n: alternativas(n)}
