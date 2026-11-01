"""Controles lógicos (Logical Controls do WaterGEMS): SE / E / OU … ENTÃO … SENÃO, com prioridade.

Cada regra fica na tabela `regra` do cadastro, uma linha por condição ou ação:
  id_regra, prioridade, ordem, secao (SE | ENTAO | SENAO), conector (SE | E | OU), elemento, atributo, operador, valor
O motor (cadastro_para_inp.regras_epanet) monta a seção [RULES] do EPANET.
"""
from html import escape

from qgis.PyQt.QtWidgets import (QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                                 QLineEdit, QListWidget, QPushButton, QSplitter, QTableWidget, QVBoxLayout, QWidget)

from gwater.estilo import COR

from .util import Dialogo

CAMPOS = ["id_regra:string", "prioridade:double", "ordem:integer", "secao:string", "conector:string",
          "elemento:string", "atributo:string", "operador:string", "valor:string"]
NOMES_CAMPOS = [c.split(":")[0] for c in CAMPOS]
# atributo: (texto, de quem) · nó = nós e reservatórios; link = bombas, válvulas e tubulações
ATRIBUTOS = {"PRESSAO": ("pressão (mca)", "no"), "CARGA": ("carga hidráulica (m)", "no"),
             "NIVEL": ("nível do reservatório (m)", "no"), "DEMANDA": ("demanda (L/s)", "no"),
             "VAZAO": ("vazão (L/s)", "link"), "STATUS": ("status", "link"), "AJUSTE": ("ajuste / rotação", "link"),
             "HORA_RELOGIO": ("hora do relógio (h)", "sistema"), "TEMPO": ("tempo desde o início (h)", "sistema"),
             "DEMANDA_SISTEMA": ("demanda total da rede (L/s)", "sistema")}
OPERADORES = ["=", "<>", "<", ">", "<=", ">="]


def _ids(nucleo, camadas):
    out = []
    for c in camadas:
        try:
            out += sorted(str(f["id"]) for f in nucleo.camada(c).getFeatures())
        except LookupError:
            pass
    return out


def ler(nucleo):
    """{id_regra: {"prioridade": p, "SE": [...], "ENTAO": [...], "SENAO": [...]}} em ordem."""
    from .componentes import tabela_sem_geometria
    lyr = tabela_sem_geometria(nucleo, "regra", CAMPOS, "Controles lógicos", criar=False)
    regras = {}
    if lyr is None:
        return regras
    linhas = sorted(lyr.getFeatures(), key=lambda f: (str(f["id_regra"]), int(f["ordem"] or 0)))
    for f in linhas:
        txt = lambda c: "" if f[c] is None or str(f[c]) == "NULL" else str(f[c])  # noqa: E731
        r = regras.setdefault(txt("id_regra"), {"prioridade": float(f["prioridade"] or 0)
                                                if str(f["prioridade"]) != "NULL" else 0.0,
                                                "SE": [], "ENTAO": [], "SENAO": []})
        r.get(txt("secao").upper(), r["SE"]).append({c: txt(c) for c in ("conector", "elemento", "atributo",
                                                                         "operador", "valor")})
    return regras


def em_texto(nome, r):
    """A regra como frase, para conferir: SE … E … ENTÃO … SENÃO …"""
    def cond(c, k):
        con = "SE" if k == 0 else c["conector"] or "E"
        at = ATRIBUTOS.get(c["atributo"], (c["atributo"].lower(), ""))[0]
        quem = "" if c["elemento"].upper() == "SISTEMA" or ATRIBUTOS.get(c["atributo"], ("", ""))[1] == "sistema" \
            else f" de {c['elemento']}"
        return f"<b>{con}</b> {at}{quem} {escape(c['operador'])} {escape(c['valor'])}"

    def acao(a, k, palavra):
        o = f"{a['elemento']} {'fica ' + a['valor'] if a['atributo'] == 'STATUS' else 'com ajuste ' + a['valor']}"
        return f"<b>{palavra if k == 0 else 'E'}</b> {o}"
    partes = [cond(c, k) for k, c in enumerate(r["SE"])] + \
        [acao(a, k, "ENTÃO") for k, a in enumerate(r["ENTAO"])] + \
        [acao(a, k, "SENÃO") for k, a in enumerate(r["SENAO"])]
    pri = f" · prioridade {r['prioridade']:g}" if r["prioridade"] else ""
    return f"<b>{nome}</b>{pri}<br>" + "<br>".join(partes)


def controles_logicos(nucleo):
    if not nucleo.cadastro():
        return
    regras = ler(nucleo)
    nos = _ids(nucleo, ("no_juncao", "reservatorio", "captacao"))
    links = _ids(nucleo, ("bomba", "valvula"))
    tubos = _ids(nucleo, ("trecho",))
    d = Dialogo(nucleo.janela, "Controles lógicos",
                "Regras com várias condições, como os Logical Controls do WaterGEMS: SE (condição) E / OU (outras) "
                "ENTÃO (ações) SENÃO (ações quando a condição não vale). Quando duas regras mandam no mesmo "
                "elemento ao mesmo tempo, vale a de maior prioridade.", largura=1100)
    split = QSplitter()
    esq = QWidget()
    ve = QVBoxLayout(esq)
    ve.setContentsMargins(0, 0, 0, 0)
    lista = QListWidget()
    ve.addWidget(lista, 1)
    hb = QHBoxLayout()
    b_nova, b_dup, b_del = QPushButton("Nova"), QPushButton("Duplicar"), QPushButton("Excluir")
    for b in (b_nova, b_dup, b_del):
        hb.addWidget(b)
    ve.addLayout(hb)
    split.addWidget(esq)

    dir_ = QWidget()
    vd = QVBoxLayout(dir_)
    vd.setContentsMargins(0, 0, 0, 0)
    topo = QHBoxLayout()
    nome = QLineEdit()
    pri = QDoubleSpinBox()
    pri.setRange(0, 100)
    pri.setDecimals(0)
    pri.setToolTip("0 = sem prioridade. Maior número vence quando duas regras disputam o mesmo elemento.")
    topo.addWidget(QLabel("Nome:"))
    topo.addWidget(nome, 1)
    topo.addWidget(QLabel("Prioridade:"))
    topo.addWidget(pri)
    vd.addLayout(topo)
    tabelas = {}
    for secao, titulo in (("SE", "SE (condições)"), ("ENTAO", "ENTÃO (ações)"), ("SENAO", "SENÃO (ações, opcional)")):
        caixa = QGroupBox(titulo)
        vc = QVBoxLayout(caixa)
        cols = ["Conector", "Elemento", "Atributo", "Operador", "Valor"] if secao == "SE" else \
            ["Elemento", "O que muda", "Valor"]
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(30)
        vc.addWidget(t)
        hl = QHBoxLayout()
        ba, br = QPushButton("+ condição" if secao == "SE" else "+ ação"), QPushButton("− remover")
        hl.addWidget(ba)
        hl.addWidget(br)
        hl.addStretch(1)
        vc.addLayout(hl)
        vd.addWidget(caixa, 2 if secao == "SE" else 1)
        tabelas[secao] = (t, ba, br)
    frase = QLabel()
    frase.setWordWrap(True)
    frase.setStyleSheet(f"background:{COR['panel2']}; padding:8px; border-radius:6px")
    vd.addWidget(frase)
    split.addWidget(dir_)
    split.setSizes([240, 860])
    d.lay.addWidget(split, 1)
    estado = {"atual": None, "mexendo": False}

    def combo(itens, atual, editavel=False, dados=None):
        c = QComboBox()
        c.setEditable(editavel)
        for k, it in enumerate(itens):
            c.addItem(it, dados[k] if dados else it)
        i = c.findData(atual)
        if i >= 0:
            c.setCurrentIndex(i)
        elif editavel:
            c.setCurrentText(atual)
        c.currentIndexChanged.connect(lambda _: guardar())
        if editavel:
            c.editTextChanged.connect(lambda _: guardar())
        return c

    def linha_cond(t, c, primeira):
        i = t.rowCount()
        t.insertRow(i)
        con = combo(["SE"] if primeira else ["E", "OU"], c.get("conector") or ("SE" if primeira else "E"))
        el = combo(["SISTEMA"] + nos + links + tubos, c.get("elemento") or (nos[0] if nos else "SISTEMA"), True)
        at = combo([v[0] for v in ATRIBUTOS.values()], c.get("atributo") or "NIVEL", dados=list(ATRIBUTOS))
        op = combo(OPERADORES, c.get("operador") or "<")
        va = QLineEdit(c.get("valor") or "0")
        va.textChanged.connect(lambda _: guardar())
        for j, w in enumerate((con, el, at, op, va)):
            t.setCellWidget(i, j, w)

    def linha_acao(t, a):
        i = t.rowCount()
        t.insertRow(i)
        el = combo(links + tubos, a.get("elemento") or (links[0] if links else ""), True)
        at = combo(["status", "ajuste (mca, L/s ou rotação)"], a.get("atributo") or "STATUS", dados=["STATUS", "AJUSTE"])
        va = combo(["ABERTA", "FECHADA"], a.get("valor") or "ABERTA", True)
        for j, w in enumerate((el, at, va)):
            t.setCellWidget(i, j, w)

    def ler_tela():
        r = {"prioridade": pri.value(), "SE": [], "ENTAO": [], "SENAO": []}
        t = tabelas["SE"][0]
        for i in range(t.rowCount()):
            w = [t.cellWidget(i, j) for j in range(5)]
            r["SE"].append({"conector": w[0].currentData(), "elemento": w[1].currentText().strip(),
                            "atributo": w[2].currentData(), "operador": w[3].currentData(), "valor": w[4].text().strip()})
        for secao in ("ENTAO", "SENAO"):
            t = tabelas[secao][0]
            for i in range(t.rowCount()):
                w = [t.cellWidget(i, j) for j in range(3)]
                r[secao].append({"conector": "E", "elemento": w[0].currentText().strip(), "atributo": w[1].currentData(),
                                 "operador": "=", "valor": w[2].currentText().strip().upper()})
        return r

    def guardar():
        if estado["mexendo"] or estado["atual"] is None:
            return
        regras[estado["atual"]] = ler_tela()
        frase.setText(em_texto(estado["atual"], regras[estado["atual"]]))

    def mostrar(item=None):
        nm = lista.currentItem().text() if lista.currentItem() else None
        estado["atual"], estado["mexendo"] = nm, True
        for secao, (t, ba, br) in tabelas.items():
            t.setRowCount(0)
            for w in (t, ba, br):
                w.setEnabled(nm is not None)
        nome.setEnabled(nm is not None)
        pri.setEnabled(nm is not None)
        if nm is None:
            nome.setText("")
            frase.setText("Nenhuma regra. Clique em <b>Nova</b>.")
            estado["mexendo"] = False
            return
        r = regras[nm]
        nome.setText(nm)
        pri.setValue(r["prioridade"])
        for k, c in enumerate(r["SE"]):
            linha_cond(tabelas["SE"][0], c, k == 0)
        for secao in ("ENTAO", "SENAO"):
            for a in r[secao]:
                linha_acao(tabelas[secao][0], a)
        estado["mexendo"] = False
        frase.setText(em_texto(nm, r))

    def preencher(escolher=None):
        lista.blockSignals(True)
        lista.clear()
        lista.addItems(list(regras))
        lista.blockSignals(False)
        if regras:
            lista.setCurrentRow(list(regras).index(escolher) if escolher in regras else 0)
        mostrar()

    def livre(base):
        k, n = 1, base
        while n in regras:
            k += 1
            n = f"{base}_{k}"
        return n

    def nova():
        n = livre("REGRA")
        regras[n] = {"prioridade": 0.0, "SE": [{"conector": "SE", "elemento": nos[0] if nos else "SISTEMA",
                                                "atributo": "NIVEL", "operador": "<", "valor": "2"}],
                     "ENTAO": [{"conector": "E", "elemento": links[0] if links else "", "atributo": "STATUS",
                                "operador": "=", "valor": "ABERTA"}], "SENAO": []}
        preencher(n)

    def duplicar():
        if estado["atual"]:
            import copy
            n = livre(estado["atual"] + "_COPIA")
            regras[n] = copy.deepcopy(regras[estado["atual"]])
            preencher(n)

    def excluir():
        if estado["atual"]:
            del regras[estado["atual"]]
            preencher()

    def renomear():
        novo = nome.text().strip().replace(" ", "_")
        atual = estado["atual"]
        if not atual or not novo or novo == atual or novo in regras:
            nome.setText(atual or "")
            return
        regras[novo] = regras.pop(atual)
        preencher(novo)

    def mais(secao):
        guardar()
        r = regras[estado["atual"]]
        if secao == "SE":
            r["SE"].append({"conector": "E", "elemento": "SISTEMA", "atributo": "HORA_RELOGIO", "operador": ">=",
                            "valor": "6"})
        else:
            r[secao].append({"conector": "E", "elemento": links[0] if links else "", "atributo": "STATUS",
                             "operador": "=", "valor": "FECHADA" if secao == "SENAO" else "ABERTA"})
        mostrar()

    def menos(secao):
        t = tabelas[secao][0]
        i = t.currentRow() if t.currentRow() >= 0 else t.rowCount() - 1
        if i >= 0:
            t.removeRow(i)
            guardar()
            mostrar()

    lista.currentRowChanged.connect(lambda _: mostrar())
    b_nova.clicked.connect(nova)
    b_dup.clicked.connect(duplicar)
    b_del.clicked.connect(excluir)
    nome.editingFinished.connect(renomear)
    pri.valueChanged.connect(lambda _: guardar())
    for secao, (t, ba, br) in tabelas.items():
        ba.clicked.connect(lambda _=False, s=secao: mais(s))
        br.clicked.connect(lambda _=False, s=secao: menos(s))
    preencher()
    d.resize(1150, 720)
    d.botoes("Gravar")
    if not d.exec():
        return
    gravar(nucleo, regras)


def gravar(nucleo, regras):
    from .componentes import _substituir, tabela_sem_geometria
    ruins = [n for n, r in regras.items() if not r["SE"] or not r["ENTAO"]]
    if ruins:
        return nucleo.aviso(f"Regra(s) sem condição ou sem ação, não gravadas: {', '.join(ruins)}.")
    lyr = tabela_sem_geometria(nucleo, "regra", CAMPOS, "Controles lógicos")
    if lyr is None:
        return
    linhas = []
    for n, r in regras.items():
        k = 0
        for secao in ("SE", "ENTAO", "SENAO"):
            for x in r[secao]:
                k += 1
                linhas.append({"id_regra": n, "prioridade": r["prioridade"], "ordem": k, "secao": secao, **x})
    if _substituir(nucleo, lyr, linhas, NOMES_CAMPOS):
        nucleo.informar(f"{len(regras)} controle(s) lógico(s) gravado(s). Rode Calcular para ver o efeito.")


ACOES = {"controles_logicos": controles_logicos}
