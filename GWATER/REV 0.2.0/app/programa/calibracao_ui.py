"""Calibração (Darwin Calibrator do WaterGEMS), em quatro passos numa janela só:

  1 · Dados de campo      momentos de medição: hora, fator de demanda, leituras e condições de contorno
  2 · Grupos de ajuste    rugosidade (por material, setor, diâmetro, idade…), demanda e status
  3 · Critérios           tipo de aptidão, mca e L/s por ponto, método e esforço
  4 · Resultados          as melhores soluções, leituras antes × depois e gráfico; vira cenário ou vai ao cadastro

O estudo fica salvo no projeto (entrada "calibracao"); o cálculo é do motor (motor/darwin.py).
"""
import csv
import io
import re

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                                 QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                                 QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                                 QVBoxLayout, QWidget)

from gwater.estilo import COR

from .util import Dialogo, eixo, figura, ids_selecionados, num, selecionar_ids

GRANDEZAS = [("pressao", "Pressão (mca)"), ("carga", "Carga / HGL (m)"), ("vazao", "Vazão (L/s)"),
             ("nivel", "Nível do reservatório (m)")]
CONTORNOS = [("NIVEL", "Nível do reservatório (m)"), ("STATUS", "Status (ABERTA / FECHADA)"),
             ("AJUSTE", "Ajuste da válvula / rotação da bomba")]
AGRUPAR_C = [("material", "Material"), ("setor", "Zona (setor)"), ("diametro", "Diâmetro"),
             ("material_diametro", "Material e diâmetro"), ("idade", "Idade (faixas de 10 anos)"),
             ("unico", "Um grupo só"), ("conjuntos", "Conjuntos de seleção")]
AGRUPAR_D = [("setor", "Zona (setor)"), ("unico", "Um grupo só"), ("conjuntos", "Conjuntos de seleção")]
OBJETIVOS = [("quadrados", "Minimizar a soma dos quadrados das diferenças"),
             ("absoluto", "Minimizar a soma das diferenças absolutas"),
             ("maximo", "Minimizar a maior diferença")]
METODOS = [("genetico", "Genético (busca global, como o Darwin)"), ("gradiente", "Gradiente (rápido, ajuste fino)")]


def _txt(v):
    return "" if v is None or str(v) == "NULL" else str(v)


def _num(t, padrao=0.0):
    try:
        return float(str(t).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def estudo_padrao():
    return {"momentos": [], "agrupar_c": "material", "grupos_c": [], "agrupar_d": "setor", "grupos_d": [],
            "status": [], "objetivo": "quadrados", "mca_por_ponto": 1.0, "lps_por_ponto": 1.0, "metodo": "genetico",
            "max_avaliacoes": 3000, "solucoes": 3}


# ---------------------------------------------------------------- grupos a partir do cadastro
def gerar_grupos_c(nucleo, por):
    tr = nucleo.camada("trecho")
    conj = nucleo.janela._ler_json("conjuntos", {}) if por == "conjuntos" else {}
    grupos = {}
    from datetime import date
    for f in tr.getFeatures():
        if _txt(f["situacao"]).upper() not in ("", "EXISTENTE"):
            continue
        tid = _txt(f["id"])
        if por == "conjuntos":
            chaves = [k for k, ids in conj.items() if tid in ids]
        elif por == "unico":
            chaves = ["Todas as tubulações"]
        elif por == "diametro":
            chaves = [f"DN {_num(f['diametro_nominal']):g}"]
        elif por == "material_diametro":
            chaves = [f"{_txt(f['material']) or '(sem material)'} DN {_num(f['diametro_nominal']):g}"]
        elif por == "idade":
            ano = _num(f["ano_instalacao"], 0) if tr.fields().indexOf("ano_instalacao") >= 0 else 0
            if not ano:
                chaves = ["(sem ano)"]
            else:
                ida = max(0, date.today().year - int(ano))
                chaves = [f"{ida // 10 * 10} a {ida // 10 * 10 + 10} anos"]
        else:
            chaves = [_txt(f[por]) or f"(sem {por})"]
        for k in chaves:
            g = grupos.setdefault(k, {"nome": k, "ids": [], "C": []})
            g["ids"].append(tid)
            g["C"].append(_num(f["rugosidade_hw"], 130))
    out = []
    for k, g in sorted(grupos.items()):
        cm = sum(g["C"]) / len(g["C"])
        out.append({"nome": k, "ids": g["ids"], "c_medio": round(cm, 1), "modo": "valor",
                    "min": max(20.0, round(cm - 50)), "max": min(160.0, round(cm + 20)), "usar": True})
    return out


def gerar_grupos_d(nucleo, por):
    nos = nucleo.camada("no_juncao")
    conj = nucleo.janela._ler_json("conjuntos", {}) if por == "conjuntos" else {}
    grupos = {}
    for f in nos.getFeatures():
        if _num(f["demanda_base"]) <= 0:
            continue
        nid = _txt(f["id"])
        chaves = ["Todos os nós" if por == "unico" else None] if por != "conjuntos" else \
            [k for k, ids in conj.items() if nid in ids]
        if por == "setor":
            chaves = [_txt(f["setor"]) or "(sem setor)"]
        for k in chaves:
            g = grupos.setdefault(k, {"nome": k, "ids": [], "q": 0.0})
            g["ids"].append(nid)
            g["q"] += _num(f["demanda_base"])
    return [{"nome": k, "ids": g["ids"], "q": round(g["q"], 3), "min": 0.5, "max": 1.5, "usar": True}
            for k, g in sorted(grupos.items())]


def ler_csv(texto):
    """CSV elemento;grandeza;hora;valor (o mesmo da calibração web) → momentos, um por hora."""
    texto = texto.lstrip("﻿")
    sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
    linhas = list(csv.DictReader(io.StringIO(texto), delimiter=sep))
    if not linhas:
        raise ValueError("arquivo vazio")
    cols = {c.strip().lower(): c for c in linhas[0]}
    falta = {"elemento", "grandeza", "hora", "valor"} - set(cols)
    if falta:
        raise ValueError(f"faltam as colunas {sorted(falta)} (esperado: elemento, grandeza, hora, valor)")
    momentos = {}
    for l in linhas:
        h = str(l[cols["hora"]]).strip()
        m = re.search(r"(\d{1,2}):(\d{2})", h)
        hora = int(m[1]) + int(m[2]) / 60 if m else _num(h)
        gr = str(l[cols["grandeza"]]).strip().lower().replace("ã", "a").replace("í", "i")
        if gr not in dict(GRANDEZAS):
            raise ValueError(f"grandeza '{gr}' desconhecida (pressao, carga, vazao ou nivel)")
        nome = f"{int(hora):02d}:{int(round(hora % 1 * 60)):02d}"
        mo = momentos.setdefault(nome, {"nome": nome, "hora": round(hora, 4), "fator_demanda": 1.0,
                                        "observacoes": [], "contorno": []})
        mo["observacoes"].append({"elemento": str(l[cols["elemento"]]).strip(), "grandeza": gr,
                                  "valor": _num(l[cols["valor"]]), "peso": 1.0})
    return list(momentos.values())


# ---------------------------------------------------------------- janela
def calibracao(nucleo):
    if not nucleo.cadastro():
        return
    janela = nucleo.janela
    est = {**estudo_padrao(), **janela._ler_json("calibracao", {})}
    pontos = [_txt(f["id"]) for c in ("no_juncao", "reservatorio", "captacao") if nucleo_tem(nucleo, c)
              for f in nucleo.camada(c).getFeatures()]
    links = [_txt(f["id"]) for c in ("bomba", "valvula", "trecho") if nucleo_tem(nucleo, c)
             for f in nucleo.camada(c).getFeatures()]
    medidos = sorted(set(pontos + links))
    d = Dialogo(janela, "Calibração (Darwin Calibrator)",
                "Como no WaterGEMS: 1) os momentos em que você mediu em campo, com as leituras e as condições daquele "
                "momento; 2) o que pode ser ajustado (rugosidade por grupo, demanda, status); 3) como medir o ajuste; "
                "4) rodar e escolher a solução, que vira um cenário ou vai direto ao cadastro.", largura=1250)
    abas = QTabWidget()
    d.lay.addWidget(abas, 1)
    estado = {"mo": None, "mexendo": False, "res": None}

    # ======================================================== 1 · dados de campo
    p1 = QWidget()
    h1 = QHBoxLayout(p1)
    esq = QVBoxLayout()
    lista = QListWidget()
    esq.addWidget(QLabel("Momentos de medição:"))
    esq.addWidget(lista, 1)
    bts = {}
    for t in ("Novo", "Duplicar", "Excluir", "Importar CSV…"):
        b = QPushButton(t)
        bts[t] = b
        esq.addWidget(b)
    h1.addLayout(esq, 1)
    dir1 = QVBoxLayout()
    f1 = QFormLayout()
    m_nome = QLineEdit()
    m_hora = QDoubleSpinBox()
    m_hora.setRange(0, 23.99)
    m_hora.setDecimals(2)
    m_hora.setToolTip("Hora do dia da medição: o modelo é congelado nessa hora da simulação de 24 h (demandas, "
                      "níveis e bombas daquele momento)")
    m_fd = QDoubleSpinBox()
    m_fd.setRange(0.01, 10)
    m_fd.setDecimals(3)
    m_fd.setToolTip("Multiplica as demandas do momento (ex.: dia de teste de hidrante, consumo atípico)")
    f1.addRow("Nome:", m_nome)
    f1.addRow("Hora do dia (h):", m_hora)
    f1.addRow("Fator de demanda:", m_fd)
    dir1.addLayout(f1)
    cx_obs = QGroupBox("Leituras de campo (observado)")
    vo = QVBoxLayout(cx_obs)
    t_obs = QTableWidget(0, 4)
    t_obs.setHorizontalHeaderLabels(["Elemento", "Grandeza", "Valor medido", "Peso"])
    t_obs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_obs.verticalHeader().setVisible(False)
    vo.addWidget(t_obs, 1)
    ho = QHBoxLayout()
    b_obs, b_obs_sel, b_obs_del = QPushButton("+ leitura"), QPushButton("+ selecionados no mapa"), QPushButton("− remover")
    for b in (b_obs, b_obs_sel, b_obs_del):
        ho.addWidget(b)
    ho.addStretch(1)
    vo.addLayout(ho)
    dir1.addWidget(cx_obs, 3)
    cx_ct = QGroupBox("Condições de contorno do momento (opcional)")
    vc = QVBoxLayout(cx_ct)
    t_ct = QTableWidget(0, 3)
    t_ct.setHorizontalHeaderLabels(["Elemento", "O que", "Valor"])
    t_ct.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_ct.verticalHeader().setVisible(False)
    vc.addWidget(t_ct, 1)
    hc = QHBoxLayout()
    b_ct, b_ct_del = QPushButton("+ condição"), QPushButton("− remover")
    hc.addWidget(b_ct)
    hc.addWidget(b_ct_del)
    hc.addStretch(1)
    vc.addLayout(hc)
    dir1.addWidget(cx_ct, 2)
    h1.addLayout(dir1, 3)
    abas.addTab(p1, "1 · Dados de campo")

    def combo(itens, atual, editavel=False):
        c = QComboBox()
        c.setEditable(editavel)
        for it in itens:
            k, t = it if isinstance(it, tuple) else (it, it)
            c.addItem(t, k)
        i = c.findData(atual)
        if i >= 0:
            c.setCurrentIndex(i)
        elif editavel:
            c.setCurrentText(_txt(atual))
        c.currentIndexChanged.connect(lambda _: guardar_mo())
        if editavel:
            c.editTextChanged.connect(lambda _: guardar_mo())
        return c

    def campo_num(v, dec=3):
        e = QLineEdit(f"{_num(v):g}")
        e.textChanged.connect(lambda _: guardar_mo())
        return e

    def linha_obs(o):
        i = t_obs.rowCount()
        t_obs.insertRow(i)
        for j, w in enumerate((combo(medidos, o.get("elemento"), True), combo(GRANDEZAS, o.get("grandeza", "pressao")),
                               campo_num(o.get("valor", 0)), campo_num(o.get("peso", 1)))):
            t_obs.setCellWidget(i, j, w)

    def linha_ct(c):
        i = t_ct.rowCount()
        t_ct.insertRow(i)
        for j, w in enumerate((combo(medidos, c.get("elemento"), True), combo(CONTORNOS, c.get("atributo", "NIVEL")),
                               combo(["ABERTA", "FECHADA"], c.get("valor", ""), True))):
            t_ct.setCellWidget(i, j, w)

    def guardar_mo():
        mo = estado["mo"]
        if estado["mexendo"] or mo is None:
            return
        mo["nome"] = m_nome.text().strip() or mo["nome"]
        mo["hora"], mo["fator_demanda"] = m_hora.value(), m_fd.value()
        mo["observacoes"] = [{"elemento": t_obs.cellWidget(i, 0).currentText().strip(),
                              "grandeza": t_obs.cellWidget(i, 1).currentData(),
                              "valor": _num(t_obs.cellWidget(i, 2).text()), "peso": _num(t_obs.cellWidget(i, 3).text(), 1)}
                             for i in range(t_obs.rowCount())]
        mo["contorno"] = [{"elemento": t_ct.cellWidget(i, 0).currentText().strip(),
                           "atributo": t_ct.cellWidget(i, 1).currentData(),
                           "valor": t_ct.cellWidget(i, 2).currentText().strip()} for i in range(t_ct.rowCount())]
        it = lista.currentItem()
        if it:
            it.setText(f"{mo['nome']}  ·  {len(mo['observacoes'])} leitura(s)")

    def mostrar_mo():
        r = lista.currentRow()
        estado["mo"] = est["momentos"][r] if 0 <= r < len(est["momentos"]) else None
        estado["mexendo"] = True
        t_obs.setRowCount(0)
        t_ct.setRowCount(0)
        mo = estado["mo"]
        for w in (m_nome, m_hora, m_fd, cx_obs, cx_ct):
            w.setEnabled(mo is not None)
        if mo:
            m_nome.setText(mo["nome"])
            m_hora.setValue(_num(mo.get("hora"), 7))
            m_fd.setValue(_num(mo.get("fator_demanda"), 1))
            for o in mo.get("observacoes", []):
                linha_obs(o)
            for c in mo.get("contorno", []):
                linha_ct(c)
        estado["mexendo"] = False

    def recarregar(sel=None):
        lista.blockSignals(True)
        lista.clear()
        for mo in est["momentos"]:
            lista.addItem(f"{mo['nome']}  ·  {len(mo.get('observacoes', []))} leitura(s)")
        lista.blockSignals(False)
        if est["momentos"]:
            lista.setCurrentRow(min(sel if sel is not None else 0, len(est["momentos"]) - 1))
        mostrar_mo()

    def novo_mo():
        est["momentos"].append({"nome": f"Momento {len(est['momentos']) + 1}", "hora": 7.0, "fator_demanda": 1.0,
                                "observacoes": [], "contorno": []})
        recarregar(len(est["momentos"]) - 1)

    def duplicar_mo():
        if estado["mo"]:
            import copy
            c = copy.deepcopy(estado["mo"])
            c["nome"] += " (cópia)"
            est["momentos"].append(c)
            recarregar(len(est["momentos"]) - 1)

    def excluir_mo():
        r = lista.currentRow()
        if r >= 0:
            est["momentos"].pop(r)
            recarregar(max(0, r - 1))

    def importar():
        arq, _ = QFileDialog.getOpenFileName(d, "Leituras de campo", janela.pasta_padrao(), "CSV (*.csv *.txt)")
        if not arq:
            return
        try:
            with open(arq, encoding="utf-8-sig", errors="replace") as fh:
                novos = ler_csv(fh.read())
        except ValueError as e:
            return nucleo.aviso(f"Não consegui ler o CSV: {e}")
        est["momentos"] += novos
        recarregar(len(est["momentos"]) - len(novos))
        nucleo.informar(f"{len(novos)} momento(s) importado(s), {sum(len(m['observacoes']) for m in novos)} leituras.")

    def obs_selecionados():
        if not estado["mo"]:
            return
        for nid in ids_selecionados(nucleo):
            linha_obs({"elemento": nid, "grandeza": "vazao" if nid in links else "pressao", "valor": 0, "peso": 1})
        guardar_mo()

    def remover(t):
        r = t.currentRow() if t.currentRow() >= 0 else t.rowCount() - 1
        if r >= 0:
            t.removeRow(r)
            guardar_mo()

    lista.currentRowChanged.connect(lambda _: mostrar_mo())
    bts["Novo"].clicked.connect(novo_mo)
    bts["Duplicar"].clicked.connect(duplicar_mo)
    bts["Excluir"].clicked.connect(excluir_mo)
    bts["Importar CSV…"].clicked.connect(importar)
    bts["Importar CSV…"].setToolTip("CSV com as colunas elemento; grandeza; hora; valor (uma leitura por linha). "
                                    "Cada hora diferente vira um momento.")
    b_obs.clicked.connect(lambda: (linha_obs({"elemento": pontos[0] if pontos else "", "grandeza": "pressao"}),
                                   guardar_mo()))
    b_obs_sel.clicked.connect(obs_selecionados)
    b_obs_del.clicked.connect(lambda: remover(t_obs))
    b_ct.clicked.connect(lambda: (linha_ct({}), guardar_mo()))
    b_ct_del.clicked.connect(lambda: remover(t_ct))
    for w in (m_nome,):
        w.editingFinished.connect(guardar_mo)
    m_hora.valueChanged.connect(lambda _: guardar_mo())
    m_fd.valueChanged.connect(lambda _: guardar_mo())

    # ======================================================== 2 · grupos de ajuste
    p2 = QWidget()
    v2 = QVBoxLayout(p2)
    cx_c = QGroupBox("Rugosidade (C de Hazen-Williams)")
    vcc = QVBoxLayout(cx_c)
    hcc = QHBoxLayout()
    ag_c = QComboBox()
    for k, t in AGRUPAR_C:
        ag_c.addItem(t, k)
    ag_c.setCurrentIndex(max(0, ag_c.findData(est["agrupar_c"])))
    b_gc = QPushButton("Gerar grupos")
    hcc.addWidget(QLabel("Agrupar as tubulações por:"))
    hcc.addWidget(ag_c)
    hcc.addWidget(b_gc)
    hcc.addStretch(1)
    vcc.addLayout(hcc)
    t_gc = QTableWidget(0, 7)
    t_gc.setHorizontalHeaderLabels(["Usar", "Grupo", "Tubulações", "C médio atual", "Ajuste", "Mínimo", "Máximo"])
    t_gc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_gc.verticalHeader().setVisible(False)
    vcc.addWidget(t_gc)
    v2.addWidget(cx_c, 3)
    cx_d = QGroupBox("Demanda (multiplicador)")
    vdd = QVBoxLayout(cx_d)
    hdd = QHBoxLayout()
    ag_d = QComboBox()
    for k, t in AGRUPAR_D:
        ag_d.addItem(t, k)
    ag_d.setCurrentIndex(max(0, ag_d.findData(est["agrupar_d"])))
    b_gd = QPushButton("Gerar grupos")
    hdd.addWidget(QLabel("Agrupar os nós por:"))
    hdd.addWidget(ag_d)
    hdd.addWidget(b_gd)
    hdd.addStretch(1)
    vdd.addLayout(hdd)
    t_gd = QTableWidget(0, 5)
    t_gd.setHorizontalHeaderLabels(["Usar", "Grupo", "Nós", "Demanda (L/s)", "Mínimo – Máximo"])
    t_gd.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_gd.verticalHeader().setVisible(False)
    vdd.addWidget(t_gd)
    v2.addWidget(cx_d, 2)
    cx_s = QGroupBox("Status desconhecido (registros, válvulas, bombas): o calibrador escolhe aberta ou fechada")
    vss = QVBoxLayout(cx_s)
    t_st = QTableWidget(0, 1)
    t_st.setHorizontalHeaderLabels(["Elemento"])
    t_st.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_st.verticalHeader().setVisible(False)
    vss.addWidget(t_st)
    hs = QHBoxLayout()
    b_st, b_st_del = QPushButton("+ elemento"), QPushButton("− remover")
    hs.addWidget(b_st)
    hs.addWidget(b_st_del)
    hs.addStretch(1)
    vss.addLayout(hs)
    v2.addWidget(cx_s, 1)
    abas.addTab(p2, "2 · Grupos de ajuste")

    def faixa(lo, hi, dec=1, lim=(0, 1000)):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        a, b = QDoubleSpinBox(), QDoubleSpinBox()
        for s, v in ((a, lo), (b, hi)):
            s.setRange(*lim)
            s.setDecimals(dec)
            s.setValue(v)
            h.addWidget(s)
        return w, a, b

    def mostrar_gc():
        t_gc.setRowCount(0)
        for g in est["grupos_c"]:
            i = t_gc.rowCount()
            t_gc.insertRow(i)
            u = QCheckBox()
            u.setChecked(g.get("usar", True))
            t_gc.setCellWidget(i, 0, u)
            for j, v in ((1, g["nome"]), (2, len(g["ids"])), (3, g.get("c_medio", ""))):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t_gc.setItem(i, j, it)
            modo = QComboBox()
            modo.addItem("C novo (valor)", "valor")
            modo.addItem("Multiplicar o C de cada uma", "multiplicador")
            modo.setCurrentIndex(max(0, modo.findData(g.get("modo", "valor"))))
            t_gc.setCellWidget(i, 4, modo)
            for j, v in ((5, g["min"]), (6, g["max"])):
                s = QDoubleSpinBox()
                s.setRange(0.01, 200)
                s.setDecimals(2)
                s.setValue(v)
                t_gc.setCellWidget(i, j, s)

            def trocar_modo(_=0, mo=modo, a=t_gc.cellWidget(i, 5), b=t_gc.cellWidget(i, 6), cm=g.get("c_medio", 100)):
                if mo.currentData() == "multiplicador":
                    a.setValue(0.5)
                    b.setValue(1.2)
                else:
                    a.setValue(max(20, round(cm - 50)))
                    b.setValue(min(160, round(cm + 20)))
            modo.currentIndexChanged.connect(trocar_modo)

    def mostrar_gd():
        t_gd.setRowCount(0)
        for g in est["grupos_d"]:
            i = t_gd.rowCount()
            t_gd.insertRow(i)
            u = QCheckBox()
            u.setChecked(g.get("usar", True))
            t_gd.setCellWidget(i, 0, u)
            for j, v in ((1, g["nome"]), (2, len(g["ids"])), (3, g.get("q", ""))):
                it = QTableWidgetItem(str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                t_gd.setItem(i, j, it)
            w, _, _ = faixa(g["min"], g["max"], 2, (0.01, 10))
            t_gd.setCellWidget(i, 4, w)

    def mostrar_st():
        t_st.setRowCount(0)
        for s in est["status"]:
            i = t_st.rowCount()
            t_st.insertRow(i)
            c = QComboBox()
            c.setEditable(True)
            c.addItems(links)
            c.setCurrentText(s["elemento"])
            t_st.setCellWidget(i, 0, c)

    def ler_grupos():
        for i, g in enumerate(est["grupos_c"]):
            g["usar"] = t_gc.cellWidget(i, 0).isChecked()
            g["modo"] = t_gc.cellWidget(i, 4).currentData()
            g["min"], g["max"] = t_gc.cellWidget(i, 5).value(), t_gc.cellWidget(i, 6).value()
        for i, g in enumerate(est["grupos_d"]):
            g["usar"] = t_gd.cellWidget(i, 0).isChecked()
            a, b = t_gd.cellWidget(i, 4).findChildren(QDoubleSpinBox)
            g["min"], g["max"] = a.value(), b.value()
        est["status"] = [{"elemento": t_st.cellWidget(i, 0).currentText().strip(), "opcoes": ["ABERTA", "FECHADA"]}
                         for i in range(t_st.rowCount()) if t_st.cellWidget(i, 0).currentText().strip()]
        est["agrupar_c"], est["agrupar_d"] = ag_c.currentData(), ag_d.currentData()

    def gerar_c():
        est["grupos_c"] = gerar_grupos_c(nucleo, ag_c.currentData())
        if not est["grupos_c"]:
            nucleo.aviso("Nenhum grupo: confira o agrupamento (conjuntos de seleção precisam existir).")
        mostrar_gc()

    def gerar_d():
        est["grupos_d"] = gerar_grupos_d(nucleo, ag_d.currentData())
        mostrar_gd()
    b_gc.clicked.connect(gerar_c)
    b_gd.clicked.connect(gerar_d)
    b_st.clicked.connect(lambda: (ler_grupos(), est["status"].append(
        {"elemento": (ids_selecionados(nucleo) or links or [""])[0], "opcoes": ["ABERTA", "FECHADA"]}), mostrar_st()))
    b_st_del.clicked.connect(lambda: (t_st.removeRow(t_st.currentRow() if t_st.currentRow() >= 0
                                                      else t_st.rowCount() - 1), ler_grupos()))
    if not est["grupos_c"]:
        est["grupos_c"] = gerar_grupos_c(nucleo, est["agrupar_c"])
    if not est["grupos_d"]:
        est["grupos_d"] = gerar_grupos_d(nucleo, est["agrupar_d"])
        for g in est["grupos_d"]:
            g["usar"] = False  # por padrão calibra só a rugosidade, como o primeiro passo usual
    mostrar_gc()
    mostrar_gd()
    mostrar_st()

    # ======================================================== 3 · critérios
    p3 = QWidget()
    f3 = QFormLayout(p3)
    obj = QComboBox()
    for k, t in OBJETIVOS:
        obj.addItem(t, k)
    obj.setCurrentIndex(max(0, obj.findData(est["objetivo"])))
    mca = QDoubleSpinBox()
    mca.setRange(0.01, 100)
    mca.setValue(est["mca_por_ponto"])
    mca.setSuffix(" mca por ponto")
    mca.setToolTip("Head per fitness point: 1 mca de diferença vale 1 ponto. Aumente para dar menos peso à pressão.")
    lps = QDoubleSpinBox()
    lps.setRange(0.01, 1000)
    lps.setValue(est["lps_por_ponto"])
    lps.setSuffix(" L/s por ponto")
    lps.setToolTip("Flow per fitness point: quantos L/s de diferença valem 1 ponto")
    met = QComboBox()
    for k, t in METODOS:
        met.addItem(t, k)
    met.setCurrentIndex(max(0, met.findData(est["metodo"])))
    aval = QSpinBox()
    aval.setRange(50, 200000)
    aval.setSingleStep(500)
    aval.setValue(int(est["max_avaliacoes"]))
    aval.setToolTip("Máximo de cálculos da rede (Maximum Trials). Mais = busca mais completa e mais demorada.")
    nsol = QSpinBox()
    nsol.setRange(1, 10)
    nsol.setValue(int(est["solucoes"]))
    nsol.setToolTip("Quantas soluções diferentes guardar (Solutions to Keep)")
    f3.addRow("Tipo de aptidão (Fitness Type):", obj)
    f3.addRow("Pressão:", mca)
    f3.addRow("Vazão:", lps)
    f3.addRow("Método:", met)
    f3.addRow("Máximo de avaliações:", aval)
    f3.addRow("Soluções a guardar:", nsol)
    dica3 = QLabel("Aptidão = soma das diferenças entre o calculado e o medido, em pontos. Comece pela rugosidade com o "
                   "método genético; depois, se precisar, ajuste a demanda e refine com o gradiente. O status "
                   "desconhecido só é buscado pelo método genético.")
    dica3.setWordWrap(True)
    dica3.setStyleSheet(f"color:{COR['muted']}")
    f3.addRow(dica3)
    abas.addTab(p3, "3 · Critérios")

    # ======================================================== 4 · resultados
    p4 = QWidget()
    v4 = QVBoxLayout(p4)
    h4 = QHBoxLayout()
    b_rodar = QPushButton("▶  Calibrar")
    b_rodar.setStyleSheet(f"font-weight:600; padding:6px 18px; background:{COR['btn_on']}")
    sol = QComboBox()
    sol.setMinimumWidth(300)
    resumo = QLabel("Monte os dados de campo e os grupos e clique em Calibrar.")
    resumo.setWordWrap(True)
    h4.addWidget(b_rodar)
    h4.addWidget(QLabel("Solução:"))
    h4.addWidget(sol)
    h4.addWidget(resumo, 1)
    v4.addLayout(h4)
    sp = QSplitter()
    esq4 = QWidget()
    ve4 = QVBoxLayout(esq4)
    ve4.setContentsMargins(0, 0, 0, 0)
    t_par = QTableWidget(0, 5)
    t_par.setHorizontalHeaderLabels(["Ajuste", "Grupo", "Elementos", "Antes", "Calibrado"])
    t_par.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_par.verticalHeader().setVisible(False)
    t_par.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    ve4.addWidget(t_par, 1)
    t_lei = QTableWidget(0, 7)
    t_lei.setHorizontalHeaderLabels(["Momento", "Elemento", "Grandeza", "Medido", "Antes", "Calibrado", "Diferença"])
    t_lei.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    t_lei.verticalHeader().setVisible(False)
    t_lei.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t_lei.setSortingEnabled(True)
    t_lei.cellDoubleClicked.connect(lambda r, _c: selecionar_ids(nucleo, [t_lei.item(r, 1).text()]))
    ve4.addWidget(t_lei, 2)
    sp.addWidget(esq4)
    gw, fig = figura(d, 3)
    sp.addWidget(gw)
    sp.setSizes([700, 500])
    v4.addWidget(sp, 1)
    h4b = QHBoxLayout()
    b_cen, b_cad, b_csv = (QPushButton("Criar cenário com esta solução"), QPushButton("Aplicar ao cadastro"),
                           QPushButton("Exportar CSV…"))
    b_cen.setToolTip("Grava a solução como cenário (a rede atual não muda): ative e calcule para conferir")
    b_cad.setToolTip("Leva a rugosidade, a demanda e o status calibrados para o cadastro (fica na edição: Salvar "
                     "edições grava; Ctrl+Z desfaz)")
    for b in (b_cen, b_cad, b_csv):
        b.setEnabled(False)
        h4b.addWidget(b)
    h4b.addStretch(1)
    v4.addLayout(h4b)
    abas.addTab(p4, "4 · Resultados")

    def mostrar_sol():
        res = estado["res"]
        k = sol.currentIndex()
        if not res or k < 0:
            return
        s = res["solucoes"][k]
        t_par.setRowCount(0)
        for p in s["parametros"]:
            i = t_par.rowCount()
            t_par.insertRow(i)
            tipo = {"rugosidade": "Rugosidade" + (" (×)" if p["modo"] == "multiplicador" else " (C)"),
                    "demanda": "Demanda (×)", "status": "Status"}[p["tipo"]]
            vals = [tipo, p["grupo"], p["n"], "" if p["inicial"] is None else p["inicial"], p["calibrado"]]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if j == 4 and p.get("no_limite"):
                    it.setForeground(Qt.GlobalColor.yellow)
                    it.setToolTip("Ficou no limite da faixa: talvez a faixa seja estreita ou falte medição")
                t_par.setItem(i, j, it)
        t_lei.setSortingEnabled(False)
        t_lei.setRowCount(0)
        for l in s["leituras"]:
            i = t_lei.rowCount()
            t_lei.insertRow(i)
            for j, v in enumerate([l["momento"], l["elemento"], f"{dict(GRANDEZAS)[l['grandeza']]}", l["observado"],
                                   l["antes"], l["depois"], l["dif_depois"]]):
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, v if isinstance(v, (int, float)) else ("" if v is None else str(v)))
                t_lei.setItem(i, j, it)
        t_lei.setSortingEnabled(True)
        ind0, ind1 = res["indicadores_inicial"], s["indicadores"]
        partes = []
        for gr, un in (("pressao", "mca"), ("carga", "m"), ("vazao", "L/s"), ("nivel", "m")):
            if gr in ind1:
                partes.append(f"{dict(GRANDEZAS)[gr].split(' (')[0]}: erro médio {num(ind0[gr]['erro_medio'], 2)} → "
                              f"<b>{num(ind1[gr]['erro_medio'], 2)} {un}</b>"
                              + (f" · R² {num(ind1[gr]['r2'], 3)}" if ind1[gr]["r2"] is not None else ""))
        resumo.setText(f"Aptidão {num(res['aptidao_inicial'], 3)} → <b>{num(s['aptidao'], 3)}</b> · "
                       f"{res['avaliacoes']} avaliações ({res['metodo']})<br>" + " · ".join(partes))
        fig.clear()
        ax = eixo(fig, titulo="Medido × calculado", x="medido", y="calculado")
        obs = [l["observado"] for l in s["leituras"]]
        if obs:
            lo, hi = min(obs), max(obs)
            ax.plot([lo, hi], [lo, hi], color=COR["muted"], linestyle=":", linewidth=1)
            ax.scatter(obs, [l["antes"] for l in s["leituras"]], color=COR["muted"], s=18, label="antes", alpha=0.7)
            ax.scatter(obs, [l["depois"] for l in s["leituras"]], color=COR["cyan"], s=22, label="calibrado")
            ax.legend(fontsize=7, frameon=False, labelcolor=COR["muted"])
        gw.canvas.draw_idle()

    def ler_criterios():
        ler_grupos()
        est.update({"objetivo": obj.currentData(), "mca_por_ponto": mca.value(), "lps_por_ponto": lps.value(),
                    "metodo": met.currentData(), "max_avaliacoes": aval.value(), "solucoes": nsol.value()})
        janela.gravar_json("calibracao", est)

    def rodar():
        from .analise_ui import rodar as rodar_motor
        guardar_mo()
        ler_criterios()
        momentos = [m for m in est["momentos"] if m.get("observacoes")]
        if not momentos:
            abas.setCurrentIndex(0)
            return nucleo.aviso("Cadastre pelo menos um momento com leituras de campo (aba 1).")
        gc = [{k: g[k] for k in ("nome", "ids", "min", "max", "modo")} for g in est["grupos_c"] if g.get("usar")]
        gd = [{k: g[k] for k in ("nome", "ids", "min", "max")} for g in est["grupos_d"] if g.get("usar")]
        if not gc and not gd and not est["status"]:
            abas.setCurrentIndex(1)
            return nucleo.aviso("Marque pelo menos um grupo de ajuste (aba 2).")
        r = rodar_motor(nucleo, "calibrar_darwin", "Calibrando (Darwin)…", momentos=momentos, grupos_c=gc,
                        grupos_d=gd, status=est["status"], objetivo=est["objetivo"],
                        mca_por_ponto=est["mca_por_ponto"], lps_por_ponto=est["lps_por_ponto"],
                        metodo=est["metodo"], max_avaliacoes=est["max_avaliacoes"], solucoes=est["solucoes"])
        if not r:
            return
        estado["res"] = r
        sol.blockSignals(True)
        sol.clear()
        for k, s in enumerate(r["solucoes"]):
            sol.addItem(f"Solução {k + 1} · aptidão {num(s['aptidao'], 3)}")
        sol.blockSignals(False)
        sol.setCurrentIndex(0)
        for b in (b_cen, b_cad, b_csv):
            b.setEnabled(True)
        abas.setCurrentIndex(3)
        mostrar_sol()

    def criar_cenario():
        from . import cenarios_ui
        s = estado["res"]["solucoes"][sol.currentIndex()]
        nome, ok = QInputDialog.getText(d, "Cenário calibrado", "Nome do cenário:", text="Calibrado")
        if not ok or not nome.strip():
            return
        gpkg = nucleo.cadastro()
        todos = cenarios_ui.listar(gpkg)
        from datetime import datetime
        cid = cenarios_ui._novo_id(nome, {c["id"] for c in todos})
        todos.append({"id": cid, "nome": nome.strip(), "descricao": f"Calibração Darwin · aptidão {s['aptidao']}",
                      "com_projetados": nucleo.projetados(), "fator_demanda": 1.0,
                      "atualizado_em": f"{datetime.now():%Y-%m-%d %H:%M}", "alteracoes": s["alteracoes"]})
        if cenarios_ui.gravar(gpkg, todos):
            cenarios_ui.atualizar_combo(janela)
            nucleo.informar(f"Cenário {nome} criado com {len(s['alteracoes'])} alteração(ões). Ative-o na caixa de "
                            "cenário e calcule para conferir.")

    def aplicar_cadastro():
        s = estado["res"]["solucoes"][sol.currentIndex()]
        por = {}
        for a in s["alteracoes"]:
            por.setdefault(a["camada"], []).append(a)
        n = 0
        for camada, alts in por.items():
            lyr = nucleo.camada(camada)
            if not lyr.isEditable():
                lyr.startEditing()
            fid = {_txt(f["id"]): f.id() for f in lyr.getFeatures()}
            lyr.beginEditCommand("Calibração Darwin")
            for a in alts:
                if a["id"] in fid:
                    lyr.changeAttributeValue(fid[a["id"]], lyr.fields().indexOf(a["campo"]), a["valor"])
                    n += 1
            lyr.endEditCommand()
        janela.canvas.refresh()
        nucleo.informar(f"{n} valor(es) calibrado(s) levados ao cadastro. Confira e clique em Salvar edições "
                        "(Ctrl+Z desfaz).")

    def exportar():
        s = estado["res"]["solucoes"][sol.currentIndex()]
        arq, _ = QFileDialog.getSaveFileName(d, "Exportar calibração", "calibracao.csv", "CSV (*.csv)")
        if not arq:
            return
        with open(arq, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["ajuste", "grupo", "elementos", "antes", "calibrado"])
            for p in s["parametros"]:
                w.writerow([p["tipo"], p["grupo"], p["n"], p["inicial"], p["calibrado"]])
            w.writerow([])
            w.writerow(["momento", "elemento", "grandeza", "medido", "antes", "calibrado", "diferenca"])
            for l in s["leituras"]:
                w.writerow([l["momento"], l["elemento"], l["grandeza"], l["observado"], l["antes"], l["depois"],
                            l["dif_depois"]])
        nucleo.informar(f"Calibração exportada para {arq}.")

    b_rodar.clicked.connect(rodar)
    sol.currentIndexChanged.connect(lambda _: mostrar_sol())
    b_cen.clicked.connect(criar_cenario)
    b_cad.clicked.connect(aplicar_cadastro)
    b_csv.clicked.connect(exportar)
    recarregar()
    estado["rodar"] = rodar  # para o teste
    d.resize(1250, 780)
    d.botoes(None, "Fechar")
    d.exec()
    guardar_mo()
    ler_criterios()
    return estado


def nucleo_tem(nucleo, c):
    try:
        nucleo.camada(c)
        return True
    except LookupError:
        return False


def calibrador_watergems(nucleo):
    """Calibrador WaterGEMS (calibrador_watergems.html, ferramenta web da EFFICO) numa aba do programa."""
    import os
    from qgis.PyQt.QtCore import QUrl
    arq = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrador_watergems.html")
    url = QUrl.fromLocalFile(arq).toString()
    if not nucleo.janela.abrir_web(url, "Calibrador WaterGEMS"):
        import webbrowser
        webbrowser.open(url)  # sem o navegador embutido: abre no navegador do Windows
        return
    from qgis.PyQt.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    v = nucleo.janela.web["Calibrador WaterGEMS"]
    if not getattr(v, "perfil_calibrador", False):
        # perfil próprio e permanente: o login, a senha cadastrada e o trabalho (localStorage) ficam entre as
        # sessões; o perfil padrão do navegador embutido é temporário
        base = os.environ.get("GWATER_DADOS") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                                                              "GWATER")
        pasta = os.path.join(base, "calibrador_watergems")  # versão portátil: vai junto no pen drive
        os.makedirs(pasta, exist_ok=True)
        perfil = QWebEngineProfile("gwater_calibrador", nucleo.janela)
        perfil.setPersistentStoragePath(pasta)
        perfil.setCachePath(os.path.join(pasta, "cache"))
        pagina = QWebEnginePage(perfil, v)
        # a página é local (file://) mas carrega Chart.js, a leitura de planilhas e as fontes da internet
        pagina.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        v.setPage(pagina)
        v.perfil_calibrador = True
    v.setUrl(QUrl(url))


ACOES = {"calibracao_darwin": calibracao, "calibrador_watergems": calibrador_watergems}
