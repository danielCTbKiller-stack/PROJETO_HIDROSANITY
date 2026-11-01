"""Componentes do WaterGEMS que faltavam:

  Curvas de válvula     Valve Characteristics: a curva perda de carga × vazão de cada válvula GPV
                        (tabela curva, tipo GPV, id_curva = código da válvula)
  Demandas unitárias    Unit Demands: consumo por unidade (habitante, ligação, m², leito…) e quantas unidades cada
                        nó atende; viram demandas na Central de demanda, com categoria e padrão
  Tarifas de energia    Energy Pricing: tabelas de preço por hora do dia, usadas no Custo de energia
"""
from qgis.core import QgsFeature
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QComboBox, QDoubleSpinBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                                 QListWidget, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from gwater.estilo import COR

from .util import Dialogo, eixo, figura, ids_selecionados, num


def _num(t, padrao=0.0):
    try:
        return float(str(t).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _lista_editavel(d, titulo_novo, dados, novo_valor):
    """Lista à esquerda com Novo / Renomear / Excluir sobre o dicionário `dados`."""
    v = QVBoxLayout()
    lista = QListWidget()
    lista.addItems(sorted(dados))
    v.addWidget(lista, 1)
    h = QHBoxLayout()
    bn, br, bx = QPushButton("Novo"), QPushButton("Renomear"), QPushButton("Excluir")
    for b in (bn, br, bx):
        h.addWidget(b)
    v.addLayout(h)

    def novo():
        nome, ok = QInputDialog.getText(d, titulo_novo, "Nome:")
        if ok and nome.strip() and nome.strip() not in dados:
            dados[nome.strip()] = novo_valor()
            lista.addItem(nome.strip())
            lista.setCurrentRow(lista.count() - 1)

    def renomear():
        it = lista.currentItem()
        if it:
            nome, ok = QInputDialog.getText(d, "Renomear", "Novo nome:", text=it.text())
            if ok and nome.strip() and nome.strip() not in dados:
                dados[nome.strip()] = dados.pop(it.text())
                it.setText(nome.strip())

    def excluir():
        it = lista.currentItem()
        if it:
            dados.pop(it.text(), None)
            lista.takeItem(lista.row(it))
    bn.clicked.connect(novo)
    br.clicked.connect(renomear)
    bx.clicked.connect(excluir)
    return v, lista


# ================================================================ curvas de válvula (GPV)
def curvas_valvula(nucleo):
    if not nucleo.cadastro():
        return
    try:
        cv, val = nucleo.camada("curva"), nucleo.camada("valvula")
    except LookupError:
        return nucleo.aviso("O cadastro não tem as tabelas de curvas ou de válvulas.")
    gpvs = sorted(str(f["id"]) for f in val.getFeatures() if str(f["tipo"]).upper() == "GPV")
    dados = {g: [] for g in gpvs}
    for f in cv.getFeatures():
        if str(f["tipo"]).upper() == "GPV":
            dados.setdefault(str(f["id_curva"]), []).append((_num(f["x"]), _num(f["y"])))
    d = Dialogo(nucleo.janela, "Curvas de válvula (GPV)",
                "Como o Valve Characteristics do WaterGEMS: a válvula de perda genérica (GPV) perde a carga da curva "
                "conforme a vazão que passa. Uma curva por válvula GPV do cadastro (desenhe a válvula como GPV antes).",
                largura=900)
    if not dados:
        d.lay.addWidget(QLabel("Nenhuma válvula GPV no cadastro."))
    h = QHBoxLayout()
    lista = QListWidget()
    lista.addItems(sorted(dados))
    lista.setFixedWidth(200)
    h.addWidget(lista)
    tab = QTableWidget(0, 2)
    tab.setHorizontalHeaderLabels(["Vazão (L/s)", "Perda de carga (m)"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    v = QVBoxLayout()
    v.addWidget(tab, 1)
    hb = QHBoxLayout()
    bm, bmenos = QPushButton("+ ponto"), QPushButton("− ponto")
    hb.addWidget(bm)
    hb.addWidget(bmenos)
    v.addLayout(hb)
    h.addLayout(v, 1)
    gw, fig = figura(d, 3)
    h.addWidget(gw, 2)
    d.lay.addLayout(h, 1)
    estado = {"atual": None, "mexendo": False}

    def grafico():
        fig.clear()
        ax = eixo(fig, titulo=estado["atual"] or "", x="vazão (L/s)", y="perda (m)")
        pts = sorted(dados.get(estado["atual"]) or [])
        if pts:
            ax.plot([q for q, _ in pts], [p for _, p in pts], color=COR["cyan"], marker="o", linewidth=1.8)
        gw.canvas.draw_idle()

    def mostrar():
        it = lista.currentItem()
        estado["atual"] = it.text() if it else None
        estado["mexendo"] = True
        tab.setRowCount(0)
        for q, p in sorted(dados.get(estado["atual"]) or []):
            i = tab.rowCount()
            tab.insertRow(i)
            tab.setItem(i, 0, QTableWidgetItem(f"{q:g}"))
            tab.setItem(i, 1, QTableWidgetItem(f"{p:g}"))
        estado["mexendo"] = False
        grafico()

    def guardar(_=None):
        if estado["mexendo"] or not estado["atual"]:
            return
        pts = []
        for i in range(tab.rowCount()):
            q, p = (tab.item(i, j).text() if tab.item(i, j) else "" for j in (0, 1))
            if q.strip() and p.strip():
                pts.append((_num(q), _num(p)))
        dados[estado["atual"]] = pts
        grafico()

    def mais():
        if estado["atual"]:
            pts = sorted(dados[estado["atual"]]) or [(0.0, 0.0)]
            q, p = pts[-1]
            dados[estado["atual"]] = pts + [(q + 5, round(p + 1 + p * 0.5, 2))]
            mostrar()

    def menos():
        r = tab.currentRow() if tab.currentRow() >= 0 else tab.rowCount() - 1
        if r >= 0:
            tab.removeRow(r)
            guardar()
    lista.currentRowChanged.connect(lambda _: mostrar())
    tab.itemChanged.connect(guardar)
    bm.clicked.connect(mais)
    bmenos.clicked.connect(menos)
    if lista.count():
        lista.setCurrentRow(0)
    d.resize(950, 520)
    d.botoes("Gravar")
    if not d.exec():
        return
    gravar_curvas_valvula(nucleo, dados)


def gravar_curvas_valvula(nucleo, dados):
    cv = nucleo.camada("curva")
    ruins = [k for k, pts in dados.items() if pts and any(b[0] <= a[0] for a, b in zip(sorted(pts), sorted(pts)[1:]))]
    if ruins:
        return nucleo.aviso(f"As vazões têm que crescer ponto a ponto: {', '.join(ruins)}.")
    if not cv.isEditable():
        cv.startEditing()
    cv.deleteFeatures([f.id() for f in cv.getFeatures() if str(f["tipo"]).upper() == "GPV"])
    novas = []
    for k, pts in dados.items():
        for q, p in sorted(pts):
            f = QgsFeature(cv.fields())
            f["id_curva"], f["tipo"], f["x"], f["y"] = k, "GPV", float(q), float(p)
            novas.append(f)
    cv.addFeatures(novas)
    if cv.commitChanges():
        nucleo.informar(f"Curvas de {sum(1 for p in dados.values() if p)} válvula(s) GPV gravadas.")
    else:
        nucleo.aviso("Não consegui gravar: " + "; ".join(cv.commitErrors()))


# ================================================================ demandas unitárias (Unit Demands)
UNIDADES = ["habitante", "ligação", "economia", "m²", "leito", "aluno", "funcionário", "unidade"]
PADRAO_UNITARIAS = {"Residencial (per capita)": {"valor": 150.0, "unidade": "habitante", "padrao": ""},
                    "Comercial": {"valor": 6.0, "unidade": "m²", "padrao": ""},
                    "Escola": {"valor": 50.0, "unidade": "aluno", "padrao": ""},
                    "Hospital": {"valor": 250.0, "unidade": "leito", "padrao": ""}}


def demandas_unitarias(nucleo):
    if not nucleo.cadastro():
        return
    janela = nucleo.janela
    dados = janela._ler_json("demandas_unitarias", {}) or {k: dict(v) for k, v in PADRAO_UNITARIAS.items()}
    try:
        pads = sorted({str(f["id_padrao"]) for f in nucleo.camada("padrao_consumo").getFeatures()})
    except LookupError:
        pads = []
    d = Dialogo(janela, "Demandas unitárias",
                "Como o Unit Demands do WaterGEMS: consumo por unidade (L/dia por habitante, por m², por leito…). "
                "Escolha uma demanda unitária, selecione os nós no mapa e informe quantas unidades cada um atende: "
                "a demanda entra na Central de demanda com a categoria e o padrão desta demanda unitária.",
                largura=760)
    h = QHBoxLayout()
    esq, lista = _lista_editavel(d, "Nova demanda unitária", dados,
                                 lambda: {"valor": 100.0, "unidade": "habitante", "padrao": ""})
    h.addLayout(esq, 1)
    dir_ = QVBoxLayout()
    val = QDoubleSpinBox()
    val.setRange(0, 1e6)
    val.setDecimals(3)
    val.setSuffix(" L/dia por unidade")
    uni = QComboBox()
    uni.setEditable(True)
    uni.addItems(UNIDADES)
    pad = QComboBox()
    pad.addItem("(constante)", "")
    for p in pads:
        pad.addItem(p, p)
    from qgis.PyQt.QtWidgets import QFormLayout
    f = QFormLayout()
    f.addRow("Consumo:", val)
    f.addRow("Unidade:", uni)
    f.addRow("Padrão de consumo:", pad)
    dir_.addLayout(f)
    eq = QLabel()
    eq.setStyleSheet(f"color:{COR['muted']}")
    dir_.addWidget(eq)
    sel = ids_selecionados(nucleo, "no_juncao")
    qtd = QDoubleSpinBox()
    qtd.setRange(0, 1e7)
    qtd.setDecimals(1)
    qtd.setValue(10)
    f2 = QFormLayout()
    f2.addRow(f"Unidades por nó ({len(sel)} nó(s) selecionado(s)):", qtd)
    dir_.addLayout(f2)
    b_apl = QPushButton("Adicionar aos nós selecionados")
    b_apl.setEnabled(bool(sel))
    b_apl.setToolTip("Selecione os nós no mapa antes de abrir esta janela")
    dir_.addWidget(b_apl)
    dir_.addStretch(1)
    h.addLayout(dir_, 2)
    d.lay.addLayout(h, 1)
    estado = {"atual": None, "mexendo": False}

    def mostrar():
        it = lista.currentItem()
        estado["atual"] = it.text() if it else None
        if not it:
            return
        estado["mexendo"] = True
        u = dados[it.text()]
        val.setValue(_num(u.get("valor"), 0))
        uni.setCurrentText(u.get("unidade", "unidade"))
        pad.setCurrentIndex(max(0, pad.findData(u.get("padrao", ""))))
        estado["mexendo"] = False
        conta()

    def guardar(_=None):
        if estado["mexendo"] or not estado["atual"]:
            return
        dados[estado["atual"]] = {"valor": val.value(), "unidade": uni.currentText().strip() or "unidade",
                                  "padrao": pad.currentData() or ""}
        conta()

    def conta():
        q = val.value() * qtd.value() / 86400
        eq.setText(f"{num(val.value(), 1)} L/dia × {num(qtd.value(), 1)} {uni.currentText()} = {num(q, 4)} L/s por nó")

    def aplicar():
        guardar()
        nome = estado["atual"]
        if not nome or not sel:
            return
        u = dados[nome]
        n = adicionar_unitaria(nucleo, sel, nome, u, qtd.value())
        nucleo.informar(f"{nome}: {num(u['valor'] * qtd.value() / 86400, 4)} L/s em {n} nó(s), na Central de demanda.")
    lista.currentRowChanged.connect(lambda _: mostrar())
    for w in (val, qtd):
        w.valueChanged.connect(guardar)
    uni.currentTextChanged.connect(guardar)
    pad.currentIndexChanged.connect(guardar)
    b_apl.clicked.connect(aplicar)
    if lista.count():
        lista.setCurrentRow(0)
    d.resize(800, 420)
    d.botoes("Gravar", "Fechar")
    d.exec()
    guardar()
    janela.gravar_json("demandas_unitarias", dados)


def adicionar_unitaria(nucleo, nos_ids, nome, u, quantidade):
    """Acrescenta a demanda unitária a cada nó (coleção de demandas + total do nó). Devolve quantos nós."""
    from .componentes import _substituir, ler_colecao, tabela_demandas
    q = u["valor"] * quantidade / 86400
    col = ler_colecao(nucleo)
    nos = nucleo.camada("no_juncao")
    alvo = set(nos_ids)
    if not nos.isEditable():
        nos.startEditing()
    nos.beginEditCommand(f"Demanda unitária {nome}")
    n = 0
    for f in nos.getFeatures():
        nid = str(f["id"])
        if nid not in alvo:
            continue
        lst = col.get(nid)
        if lst is None:  # o nó ainda não tem coleção: a demanda base dele vira a primeira linha
            base = _num(f["demanda_base"], 0)
            p0 = "" if f["padrao"] is None or str(f["padrao"]) == "NULL" else str(f["padrao"])
            lst = [[base, p0, ""]] if base else []
        lst.append([round(q, 6), u.get("padrao", ""), f"{nome} ({num(quantidade, 1)} {u['unidade']})"])
        col[nid] = lst
        nos.changeAttributeValue(f.id(), nos.fields().indexOf("demanda_base"), round(sum(x[0] for x in lst), 6))
        if not (f["padrao"] and str(f["padrao"]) != "NULL") and lst[0][1]:
            nos.changeAttributeValue(f.id(), nos.fields().indexOf("padrao"), lst[0][1])
        n += 1
    nos.endEditCommand()
    lyr = tabela_demandas(nucleo)
    linhas = [{"no_id": k, "demanda": a, "padrao": b or None, "categoria": c or None}
              for k, lst in col.items() for a, b, c in lst]
    _substituir(nucleo, lyr, linhas, ["no_id", "demanda", "padrao", "categoria"])
    return n


# ================================================================ tarifas de energia (Energy Pricing)
TARIFA_PADRAO = {"Convencional (ponta 18–21 h)": [0.55] * 18 + [2.10] * 3 + [0.55] * 3}


def tarifas(nucleo):
    janela = nucleo.janela
    dados = janela._ler_json("tarifas", {}) or {k: list(v) for k, v in TARIFA_PADRAO.items()}
    d = Dialogo(janela, "Tarifas de energia",
                "Como o Energy Pricing do WaterGEMS: o preço da energia (R$/kWh) em cada hora do dia. O Custo de energia "
                "usa a tarifa escolhida. Cole 24 valores do Excel na coluna.", largura=820)
    h = QHBoxLayout()
    esq, lista = _lista_editavel(d, "Nova tarifa", dados, lambda: [0.55] * 24)
    h.addLayout(esq, 1)
    tab = QTableWidget(24, 2)
    tab.setHorizontalHeaderLabels(["Hora", "R$/kWh"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    for i in range(24):
        it = QTableWidgetItem(f"{i:02d}:00")
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tab.setItem(i, 0, it)
    h.addWidget(tab, 1)
    gw, fig = figura(d, 3)
    h.addWidget(gw, 2)
    d.lay.addLayout(h, 1)
    estado = {"atual": None, "mexendo": False}

    def grafico():
        fig.clear()
        ax = eixo(fig, titulo=estado["atual"] or "", x="hora", y="R$/kWh")
        v = dados.get(estado["atual"])
        if v:
            ax.step(list(range(25)), v + [v[-1]], where="post", color=COR["warn"], linewidth=1.8)
            ax.set_xlim(0, 24)
            ax.set_xticks(range(0, 25, 3))
        gw.canvas.draw_idle()

    def mostrar():
        it = lista.currentItem()
        estado["atual"] = it.text() if it else None
        estado["mexendo"] = True
        for i, x in enumerate(dados.get(estado["atual"]) or [0] * 24):
            tab.setItem(i, 1, QTableWidgetItem(f"{x:g}"))
        estado["mexendo"] = False
        grafico()

    def guardar(_=None):
        if estado["mexendo"] or not estado["atual"]:
            return
        dados[estado["atual"]] = [_num(tab.item(i, 1).text() if tab.item(i, 1) else 0) for i in range(24)]
        grafico()

    def colar(e):
        from qgis.PyQt.QtWidgets import QApplication
        if e.key() == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            vals = [l.split("\t")[-1].strip() for l in QApplication.clipboard().text().strip().splitlines()]
            r0 = max(tab.currentRow(), 0)
            estado["mexendo"] = True
            for k, t in enumerate(vals):
                if r0 + k < 24:
                    tab.setItem(r0 + k, 1, QTableWidgetItem(t))
            estado["mexendo"] = False
            guardar()
        else:
            QTableWidget.keyPressEvent(tab, e)
    tab.keyPressEvent = colar
    lista.currentRowChanged.connect(lambda _: mostrar())
    tab.itemChanged.connect(guardar)
    if lista.count():
        lista.setCurrentRow(0)
    d.resize(900, 600)
    d.botoes("Gravar")
    if d.exec():
        janela.gravar_json("tarifas", dados)
        nucleo.informar(f"{len(dados)} tarifa(s) gravada(s) no projeto.")


ACOES = {"curvas_valvula": curvas_valvula, "demandas_unitarias": demandas_unitarias, "tarifas": tarifas}
