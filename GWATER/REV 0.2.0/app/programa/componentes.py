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
# (chave, rótulo, padrão, aba, mínimo, máximo, casas, dica) · combos: valor da lista em LISTAS_OPCOES
OPCOES = [
    ("tipo_analise", "Tipo de análise", "EPS", "Tempo", 0, 0, 0,
     "Período estendido (EPS): simula o dia, passo a passo. Regime permanente (Steady State): um instante só."),
    ("inicio_h", "Hora de início", "0", "Tempo", 0, 23.99, 2, "Hora do relógio do primeiro passo (0 = meia-noite)."),
    ("duracao_h", "Duração (h)", "24", "Tempo", 0, 8760, 0, "Período estendido: quantas horas simular."),
    ("passo_hidraulico_min", "Passo hidráulico (min)", "15", "Tempo", 1, 1440, 0, ""),
    ("passo_relatorio_min", "Passo dos resultados (min)", "15", "Tempo", 1, 1440, 0,
     "De quanto em quanto tempo os resultados ficam guardados (linha do tempo, gráficos)."),
    ("passo_padrao_min", "Passo dos padrões (min)", "15", "Tempo", 1, 1440, 0,
     "Duração de cada multiplicador dos padrões de consumo."),
    ("perda_carga", "Fórmula de perda de carga", "H-W", "Hidráulica", 0, 0, 0,
     "Hazen-Williams, com o C de cada tubulação (campo rugosidade_hw)."),
    ("multiplicador_demanda", "Multiplicador global de demanda", "1", "Hidráulica", 0, 100, 3,
     "Multiplica todas as demandas (ex.: 1,2 para o dia de maior consumo). Os cenários podem ter o seu."),
    ("unidades", "Unidades de vazão", "LPS", "Hidráulica", 0, 0, 0, "O cadastro trabalha em L/s."),
    ("precisao", "Precisão (Accuracy)", "0.001", "Hidráulica", 0.000001, 0.1, 6,
     "Critério de convergência do EPANET: menor = mais preciso e mais lento."),
    ("tentativas", "Máximo de iterações (Trials)", "100", "Hidráulica", 1, 10000, 0, ""),
    ("se_nao_convergir", "Se não convergir", "CONTINUAR", "Hidráulica", 0, 0, 0,
     "Continuar: segue com aviso (como o WaterGEMS). Parar: interrompe o cálculo."),
    ("viscosidade_relativa", "Viscosidade relativa", "1", "Hidráulica", 0.01, 100, 3,
     "Em relação à água a 20 °C (1 = água)."),
    ("densidade_relativa", "Densidade relativa", "1", "Hidráulica", 0.01, 100, 3, "1 = água."),
    ("expoente_emissor", "Expoente do emissor", "0.5", "Hidráulica", 0.1, 3, 2,
     "Vazamentos e sprinklers: q = K · p^expoente."),
    ("modelo_demanda", "Modelo de demanda", "PDA", "Pressão (PDD)", 0, 0, 0,
     "PDA: abaixo da pressão requerida o nó recebe menos água (Pressure Dependent Demand do WaterGEMS). "
     "DDA: a demanda é entregue sempre (podem aparecer pressões negativas)."),
    ("pressao_minima", "Pressão mínima (mca)", "0", "Pressão (PDD)", 0, 200, 1, "Abaixo dela o nó não recebe água."),
    ("pressao_requerida", "Pressão requerida (mca)", "10", "Pressão (PDD)", 0, 200, 1,
     "A partir dela o nó recebe toda a demanda."),
    ("expoente_pressao", "Expoente da pressão", "0.5", "Pressão (PDD)", 0.1, 3, 2, ""),
    ("limite_pressao_min", "Pressão mínima aceitável (mca)", "10", "Limites", 0, 200, 1,
     "Alertas e consultas: abaixo disso o nó é sinalizado (NBR 12218: 10 mca)."),
    ("limite_pressao_max", "Pressão máxima aceitável (mca)", "50", "Limites", 0, 300, 1,
     "Alertas e consultas: acima disso o nó é sinalizado (NBR 12218: 50 mca)."),
    ("limite_velocidade", "Velocidade máxima (m/s)", "2.5", "Limites", 0.1, 20, 2, ""),
    ("limite_perda", "Perda de carga máxima (m/km)", "10", "Limites", 0.1, 1000, 1, ""),
]


def limites(nucleo):
    """Limites de pressão, velocidade e perda de carga das Opções (aba Limites), com os padrões da NBR 12218."""
    out = {"limite_pressao_min": 10.0, "limite_pressao_max": 50.0, "limite_velocidade": 2.5, "limite_perda": 10.0}
    try:
        for f in nucleo.camada("opcoes_simulacao").getFeatures():
            if f["chave"] in out:
                try:
                    out[f["chave"]] = float(str(f["valor"]).replace(",", "."))
                except ValueError:
                    pass
    except LookupError:
        pass
    return out
LISTAS_OPCOES = {
    "tipo_analise": [("Período estendido (EPS)", "EPS"), ("Regime permanente (Steady State)", "PERMANENTE")],
    "perda_carga": [("Hazen-Williams", "H-W")],
    "unidades": [("L/s", "LPS")],
    "se_nao_convergir": [("Continuar com aviso", "CONTINUAR"), ("Parar o cálculo", "PARAR")],
    "modelo_demanda": [("PDA - demanda dependente da pressão", "PDA"), ("DDA - demanda fixa", "DDA")],
}


def opcoes(nucleo):
    lyr = _tabela_camada(nucleo, "opcoes_simulacao")
    if lyr is None:
        return
    atual = {f["chave"]: str(f["valor"]) for f in lyr.getFeatures()}
    d = Dialogo(nucleo.janela, "Opções de cálculo",
                "Valem para o Calcular e para todas as análises. Com demanda dependente da pressão (PDA, padrão do "
                "GWATER) o nó com pressão abaixo da requerida recebe menos água, em vez de o cálculo falhar; com DDA "
                "a demanda é entregue sempre (podem aparecer pressões negativas).")
    from qgis.PyQt.QtWidgets import QFormLayout, QTabWidget
    abas, formas = QTabWidget(), {}
    w = {}
    for chave, rot, padrao, aba, lo, hi, casas, dica in OPCOES:
        if aba not in formas:
            pg = QWidget()
            formas[aba] = QFormLayout(pg)
            abas.addTab(pg, aba)
        if chave in LISTAS_OPCOES:
            c = QComboBox()
            for texto, valor in LISTAS_OPCOES[chave]:
                c.addItem(texto, valor)
            c.setCurrentIndex(max(0, c.findData(str(atual.get(chave, padrao)).upper())))
        else:
            c = QDoubleSpinBox()
            c.setRange(lo, hi)
            c.setDecimals(casas)
            try:
                c.setValue(float(str(atual.get(chave, padrao) or padrao).replace(",", ".")))
            except ValueError:
                c.setValue(float(padrao))
        c.setToolTip(dica)
        formas[aba].addRow(rot + ":", c)
        w[chave] = c

    def permanente():
        ep = w["tipo_analise"].currentData() == "EPS"
        for k in ("duracao_h", "passo_hidraulico_min", "passo_relatorio_min"):
            w[k].setEnabled(ep)

    def pdd():
        for k in ("pressao_minima", "pressao_requerida", "expoente_pressao"):
            w[k].setEnabled(w["modelo_demanda"].currentData() == "PDA")
    w["tipo_analise"].currentIndexChanged.connect(lambda _: permanente())
    w["modelo_demanda"].currentIndexChanged.connect(lambda _: pdd())
    permanente()
    pdd()
    d.lay.addWidget(abas)
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
    if novos.get("pressao_requerida") and float(novos["pressao_requerida"]) <= float(novos.get("pressao_minima", 0)):
        return nucleo.aviso("A pressão requerida tem que ser maior que a mínima.")
    for k, v in atual.items():
        novos.setdefault(k, v)
    if _substituir(nucleo, lyr, [{"chave": k, "valor": v} for k, v in novos.items()], ["chave", "valor"]):
        nucleo.dock.projetados.setChecked(proj.isChecked())
        nucleo.informar("Opções de cálculo gravadas.")


# ================================================================ padrões de consumo
def passos_padrao(formato, pontos, passo_min, ciclo_h=24.0):
    """Multiplicadores do EPANET de um padrão do WaterGEMS (a mesma regra de motor/cadastro_para_inp.py).
    DEGRAUS: vale o último ponto já alcançado. CONTINUO: reta entre os pontos, fechando o ciclo no multiplicador
    inicial; cada passo leva o valor do meio do passo."""
    pts = sorted(pontos)
    if not pts:
        return [1.0]
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    ciclo = max(ciclo_h, pts[-1][0])
    n = max(1, int(round(ciclo * 60 / passo_min)))
    out = []
    for k in range(n):
        if str(formato).upper().startswith("CONT"):
            t = (k + 0.5) * passo_min / 60
            fim = pts + ([(ciclo, pts[0][1])] if pts[-1][0] < ciclo else [])
            a = max(i for i, (h, _) in enumerate(fim) if h <= t)
            if a + 1 < len(fim):
                (h0, m0), (h1, m1) = fim[a], fim[a + 1]
                v = m0 + (m1 - m0) * (t - h0) / (h1 - h0) if h1 > h0 else m1
            else:
                v = fim[a][1]
        else:
            t = k * passo_min / 60 + 1e-9
            v = [m for h, m in pts if h <= t][-1]
        out.append(round(v, 4))
    return out


CAMPOS_PADRAO_DEF = ["id_padrao:string", "formato:string", "hora:double", "multiplicador:double"]


def padroes(nucleo):
    """Padrões de consumo como os Patterns do WaterGEMS: em degraus ou contínuo, multiplicador inicial e os pontos
    (hora desde o início, multiplicador). Os passos do EPANET são gerados no passo dos padrões das Opções."""
    lyr = _tabela_camada(nucleo, "padrao_consumo")
    if lyr is None:
        return
    passo_min = 15
    try:
        for f in nucleo.camada("opcoes_simulacao").getFeatures():
            if f["chave"] == "passo_padrao_min":
                passo_min = int(float(f["valor"]))
    except LookupError:
        pass
    # definições: as gravadas; padrões antigos (só passos) viram degraus nos pontos onde o valor muda
    dados = {}
    passos = {}
    for f in lyr.getFeatures():
        passos.setdefault(str(f["id_padrao"]), []).append((int(f["passo"]), float(f["multiplicador"] or 0)))
    for k, v in passos.items():
        ms = [m for _, m in sorted(v)]
        pts = [(i * passo_min / 60, m) for i, m in enumerate(ms) if i == 0 or m != ms[i - 1]]
        dados[k] = {"formato": "DEGRAUS", "pts": pts}
    defs = tabela_sem_geometria(nucleo, "padrao_def", CAMPOS_PADRAO_DEF, "Padrões (definição)", criar=False)
    if defs is not None:
        lidos = {}
        for f in defs.getFeatures():
            if str(f["hora"]) == "NULL" or str(f["multiplicador"]) == "NULL":
                continue
            d_ = lidos.setdefault(str(f["id_padrao"]), {"formato": str(f["formato"] or "DEGRAUS"), "pts": []})
            d_["pts"].append((float(f["hora"]), float(f["multiplicador"])))
        for k, v in lidos.items():
            v["pts"].sort()
            dados[k] = v
    d = Dialogo(nucleo.janela, "Padrões de consumo",
                "Como os Patterns do WaterGEMS: o formato (em degraus ou contínuo), o multiplicador inicial (hora 0) e "
                "os pontos seguintes (hora desde o início e multiplicador). A demanda de cada nó é a demanda base × o "
                f"multiplicador do momento. O EPANET recebe um valor a cada {passo_min} min (passo dos padrões nas "
                "Opções). Ctrl+V cola uma coluna do Excel nos multiplicadores.", largura=1100)
    h = QHBoxLayout()
    esq = QVBoxLayout()
    lista = QListWidget()
    lista.addItems(sorted(dados))
    esq.addWidget(lista, 1)
    for texto in ("Novo", "Duplicar", "Renomear", "Excluir"):
        b = QPushButton(texto)
        b.setObjectName(texto)
        esq.addWidget(b)
    h.addLayout(esq)
    meio = QVBoxLayout()
    from qgis.PyQt.QtWidgets import QFormLayout
    form = QFormLayout()
    formato = QComboBox()
    formato.addItem("Em degraus (Stepwise)", "DEGRAUS")
    formato.addItem("Contínuo (Continuous)", "CONTINUO")
    formato.setToolTip("Em degraus: o multiplicador vale até o próximo ponto. Contínuo: varia em linha reta entre "
                       "os pontos e volta ao inicial no fim do ciclo de 24 h.")
    form.addRow("Formato:", formato)
    inicial = QDoubleSpinBox()
    inicial.setRange(0, 100)
    inicial.setDecimals(4)
    inicial.setToolTip("Multiplicador no início do ciclo (hora 0), o Starting Multiplier do WaterGEMS")
    form.addRow("Multiplicador inicial:", inicial)
    meio.addLayout(form)
    tab = QTableWidget(0, 2)
    tab.setHorizontalHeaderLabels(["Hora desde o início (h)", "Multiplicador"])
    tab.verticalHeader().setVisible(False)
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    meio.addWidget(tab, 1)
    hp = QHBoxLayout()
    b_mais, b_menos = QPushButton("+ ponto"), QPushButton("− ponto")
    hp.addWidget(b_mais)
    hp.addWidget(b_menos)
    meio.addLayout(hp)
    info = QLabel()
    info.setWordWrap(True)
    meio.addWidget(info)
    hb = QHBoxLayout()
    b_norm = QPushButton("Normalizar média = 1")
    b_norm.setToolTip("Divide todos os multiplicadores pela média do dia: a demanda base passa a ser a média")
    b_24 = QPushButton("Digitar 24 valores (por hora)")
    hb.addWidget(b_norm)
    hb.addWidget(b_24)
    meio.addLayout(hb)
    h.addLayout(meio, 1)
    gw, fig = figura(d, 3)
    h.addWidget(gw, 2)
    d.lay.addLayout(h, 1)
    estado = {"atual": None, "mexendo": False}

    def mostrar():
        it = lista.currentItem()
        estado["mexendo"] = True
        tab.setRowCount(0)
        for w in (formato, inicial, tab, b_mais, b_menos):
            w.setEnabled(it is not None)
        if not it:
            estado["atual"] = None
            estado["mexendo"] = False
            grafico()
            return
        estado["atual"] = it.text()
        p = dados[it.text()]
        formato.setCurrentIndex(max(0, formato.findData(p["formato"].upper())))
        pts = sorted(p["pts"]) or [(0.0, 1.0)]
        inicial.setValue(pts[0][1] if pts[0][0] <= 0 else 1.0)
        resto = [x for x in pts if x[0] > 0]
        tab.setRowCount(len(resto))
        for i, (hh, m) in enumerate(resto):
            tab.setItem(i, 0, QTableWidgetItem(f"{hh:g}"))
            tab.setItem(i, 1, QTableWidgetItem(f"{m:g}"))
        estado["mexendo"] = False
        grafico()

    def guardar():
        if estado["mexendo"] or not estado["atual"]:
            return
        pts = [(0.0, inicial.value())]
        for i in range(tab.rowCount()):
            try:
                hh = float(tab.item(i, 0).text().replace(",", "."))
                m = float(tab.item(i, 1).text().replace(",", "."))
            except (AttributeError, ValueError):
                continue
            if hh > 0:
                pts.append((hh, m))
        dados[estado["atual"]] = {"formato": formato.currentData(), "pts": sorted(pts)}
        grafico()

    def grafico():
        fig.clear()
        ax = eixo(fig, titulo=estado["atual"] or "", x="hora", y="multiplicador")
        p = dados.get(estado["atual"])
        if p:
            pts = sorted(p["pts"])
            ms = passos_padrao(p["formato"], pts, passo_min)
            xs = [i * passo_min / 60 for i in range(len(ms) + 1)]
            ax.fill_between(xs, ms + [ms[-1]], step="post", color=COR["cyan"], alpha=0.15, linewidth=0,
                            label=f"EPANET (a cada {passo_min} min)")
            if p["formato"] == "CONTINUO":
                fim = pts + ([(xs[-1], pts[0][1])] if pts[-1][0] < xs[-1] else [])
                ax.plot([x for x, _ in fim], [m for _, m in fim], color=COR["cyan"], linewidth=1.8, marker="o",
                        markersize=4, label="definição")
            else:
                ax.step([x for x, _ in pts] + [xs[-1]], [m for _, m in pts] + [pts[-1][1]], where="post",
                        color=COR["cyan"], linewidth=1.8, label="definição")
                ax.plot([x for x, _ in pts], [m for _, m in pts], "o", color=COR["warn"], markersize=4)
            ax.axhline(1, color=COR["muted"], linestyle=":", linewidth=0.8)
            ax.set_xlim(0, xs[-1])
            ax.set_xticks(range(0, int(xs[-1]) + 1, 3))
            ax.legend(loc="upper left", fontsize=7, frameon=False, labelcolor=COR["muted"])
            media = sum(ms) / len(ms)
            info.setText(f"Ciclo de {xs[-1]:g} h · {len(ms)} passos no EPANET · média {num(media, 3)} · "
                         f"mín {num(min(ms), 2)} · máx {num(max(ms), 2)}"
                         + ("" if abs(media - 1) < 0.02 else "<br>⚠ a média não é 1: a demanda base não é a média "
                            "do dia (use Normalizar)"))
        else:
            info.setText("")
        gw.canvas.draw_idle()

    def colar_evento(e):
        from qgis.PyQt.QtWidgets import QApplication
        if e.key() == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier and estado["atual"]:
            linhas = [l.strip().split("\t") for l in QApplication.clipboard().text().strip().splitlines()]
            ini = max(tab.currentRow(), 0)
            estado["mexendo"] = True
            for i, cols in enumerate(linhas):
                r = ini + i
                if r >= tab.rowCount():
                    tab.insertRow(r)
                    tab.setItem(r, 0, QTableWidgetItem(f"{(r + 1) * passo_min / 60:g}"))
                if len(cols) >= 2:  # hora e multiplicador
                    tab.setItem(r, 0, QTableWidgetItem(cols[-2].strip()))
                tab.setItem(r, 1, QTableWidgetItem(cols[-1].strip()))
            estado["mexendo"] = False
            guardar()
        else:
            QTableWidget.keyPressEvent(tab, e)
    tab.keyPressEvent = colar_evento

    def mais_ponto():
        if not estado["atual"]:
            return
        pts = dados[estado["atual"]]["pts"]
        ult = max(hh for hh, _ in pts)
        dados[estado["atual"]]["pts"] = sorted(pts + [(min(ult + 1, 24.0) if ult < 24 else ult + 1, pts[-1][1])])
        mostrar()

    def menos_ponto():
        r = tab.currentRow() if tab.currentRow() >= 0 else tab.rowCount() - 1
        if r >= 0:
            tab.removeRow(r)
            guardar()
            mostrar()

    def novo():
        nome, ok = QInputDialog.getText(d, "Novo padrão", "Nome do padrão (ex.: PAD_COMERCIAL):")
        if ok and nome.strip() and nome.strip() not in dados:
            dados[nome.strip()] = {"formato": "DEGRAUS", "pts": [(0.0, 1.0)]}
            lista.addItem(nome.strip())
            lista.setCurrentRow(lista.count() - 1)

    def duplicar():
        if estado["atual"]:
            nome, ok = QInputDialog.getText(d, "Duplicar", "Nome da cópia:", text=estado["atual"] + "_2")
            if ok and nome.strip() and nome.strip() not in dados:
                dados[nome.strip()] = {"formato": dados[estado["atual"]]["formato"],
                                       "pts": list(dados[estado["atual"]]["pts"])}
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
        p = dados.get(estado["atual"])
        if p:
            ms = passos_padrao(p["formato"], p["pts"], passo_min)
            m = sum(ms) / len(ms)
            if m > 0:
                p["pts"] = [(hh, round(x / m, 4)) for hh, x in p["pts"]]
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
        dados[estado["atual"]]["pts"] = [(float(i), v) for i, v in enumerate(vals)]
        mostrar()

    for b in d.findChildren(QPushButton):
        f = {"Novo": novo, "Duplicar": duplicar, "Renomear": renomear, "Excluir": excluir}.get(b.objectName())
        if f:
            b.clicked.connect(f)
    b_norm.clicked.connect(normalizar)
    b_24.clicked.connect(vinte_quatro)
    b_mais.clicked.connect(mais_ponto)
    b_menos.clicked.connect(menos_ponto)
    formato.currentIndexChanged.connect(lambda _: guardar())
    inicial.valueChanged.connect(lambda _: guardar())
    tab.itemChanged.connect(lambda _: guardar())
    lista.currentItemChanged.connect(lambda *_: mostrar())
    if lista.count():
        lista.setCurrentRow(0)
    d.resize(1150, 620)
    d.botoes("Gravar")
    if not d.exec():
        return
    gravar_padroes(nucleo, dados, passo_min, estado.get("renomes", {}))


def gravar_padroes(nucleo, dados, passo_min, renomes=None):
    """Grava a definição (padrao_def) e os passos do EPANET (padrao_consumo) de cada padrão."""
    lyr = nucleo.camada("padrao_consumo")
    defs = tabela_sem_geometria(nucleo, "padrao_def", CAMPOS_PADRAO_DEF, "Padrões (definição)")
    if defs is None:
        return
    linhas = [{"id_padrao": k, "passo": i, "multiplicador": m} for k, p in dados.items()
              for i, m in enumerate(passos_padrao(p["formato"], p["pts"], passo_min))]
    linhas_def = [{"id_padrao": k, "formato": p["formato"], "hora": hh, "multiplicador": m}
                  for k, p in dados.items() for hh, m in sorted(p["pts"])]
    if not (_substituir(nucleo, lyr, linhas, ["id_padrao", "passo", "multiplicador"])
            and _substituir(nucleo, defs, linhas_def, ["id_padrao", "formato", "hora", "multiplicador"])):
        return
    if renomes:
        for camada, campo in (("no_juncao", "padrao"),):
            nos = nucleo.camada(camada)
            if not nos.isEditable():
                nos.startEditing()
            i = nos.fields().indexOf(campo)
            for f in nos.getFeatures():
                if str(f[campo]) in renomes:
                    nos.changeAttributeValue(f.id(), i, renomes[str(f[campo])])
        dem = tabela_demandas(nucleo, criar=False)
        if dem is not None:
            if not dem.isEditable():
                dem.startEditing()
            i = dem.fields().indexOf("padrao")
            for f in dem.getFeatures():
                if str(f["padrao"]) in renomes:
                    dem.changeAttributeValue(f.id(), i, renomes[str(f["padrao"])])
            dem.commitChanges()
    nucleo.informar(f"{len(dados)} padrão(ões) gravado(s).")


# ================================================================ controles
CONDICOES = {"NIVEL_ABAIXO": "nível do reservatório abaixo de", "NIVEL_ACIMA": "nível do reservatório acima de",
             "PRESSAO_ABAIXO": "pressão no nó abaixo de", "PRESSAO_ACIMA": "pressão no nó acima de",
             "HORA": "na hora do relógio (h)", "TEMPO": "depois de (h desde o início)"}


def controles(nucleo):
    lyr = _tabela_camada(nucleo, "controle")
    if lyr is None:
        return
    d = Dialogo(nucleo.janela, "Controles",
                "Regras de operação, como os Controls do WaterGEMS: a bomba ou válvula muda de estado ou de ajuste "
                "quando a condição acontece. Ex.: B1 ABERTA se o nível de R1 ficar abaixo de 2,5 m; B1 FECHADA se "
                "passar de 5,3 m; VRP1 AJUSTE 20 às 23 h (pressão noturna menor).",
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
        a.setEditable(True)  # "AJUSTE 25": muda o ajuste da válvula (mca, L/s) ou a rotação relativa da bomba
        a.addItems(["ABERTA", "FECHADA", "AJUSTE 0"])
        a.setToolTip("ABERTA / FECHADA, ou AJUSTE seguido do valor: pressão (PRV/PSV/PBV, mca), vazão (FCV, L/s), "
                     "coeficiente (TCV) ou rotação relativa da bomba (1 = nominal)")
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
    b = QPushButton("Controles lógicos (SE / E / OU / SENÃO)…")
    b.setToolTip("Regras com várias condições e prioridade, como os Logical Controls do WaterGEMS")
    b.clicked.connect(lambda: nucleo.executar("controles_logicos"))
    h.addWidget(b)
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
        acao = a.currentText().strip().upper().replace(",", ".")
        if acao not in ("ABERTA", "FECHADA"):
            try:
                acao = f"AJUSTE {float(acao.replace('AJUSTE', '').strip()):g}"
            except ValueError:
                return nucleo.aviso(f"Ação '{a.currentText()}' inválida: use ABERTA, FECHADA ou AJUSTE e o valor.")
        linhas.append({"elemento": e.currentText().strip(), "acao": acao, "condicao": c.currentData(),
                       "no_ref": n.currentText().strip() or None, "valor": v.value()})
    if _substituir(nucleo, lyr, linhas, ["elemento", "acao", "condicao", "no_ref", "valor"]):
        nucleo.informar(f"{len(linhas)} controle(s) gravado(s).")


# ================================================================ central de demanda
def tabela_sem_geometria(nucleo, nome, campos, apelido, criar=True):
    """Tabela sem geometria do cadastro; criada no GeoPackage (e posta no projeto) se ainda não existir.
    campos: "campo:tipo" no formato da camada de memória (string, double, integer)."""
    try:
        return nucleo.camada(nome)
    except LookupError:
        if not criar or not nucleo.cadastro():
            return None
    gpkg = nucleo.cadastro()
    mem = QgsVectorLayer("None?" + "&".join(f"field={c}" for c in campos), nome, "memory")
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = "GPKG"
    opt.layerName = nome
    opt.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsProject.instance().transformContext(), opt)
    if err[0] != QgsVectorFileWriter.WriterError.NoError:
        nucleo.aviso(f"Não consegui criar a tabela {apelido}: {err[1]}")
        return None
    lyr = QgsVectorLayer(f"{gpkg}|layername={nome}", apelido, "ogr")
    QgsProject.instance().addMapLayer(lyr, False)
    return lyr


def tabela_demandas(nucleo, criar=True):
    """Tabela "demanda" do cadastro (várias demandas por nó)."""
    return tabela_sem_geometria(nucleo, "demanda", ["no_id:string", "demanda:double", "padrao:string",
                                                    "categoria:string"], "Demandas por nó", criar)


def ler_colecao(nucleo):
    """{no_id: [[demanda, padrão, categoria], ...]} das demandas do cadastro."""
    out = {}
    lyr = tabela_demandas(nucleo, criar=False)
    if lyr is None:
        return out
    for f in lyr.getFeatures():
        if f["no_id"] in (None, "") or str(f["no_id"]) == "NULL":
            continue
        q = float(f["demanda"] or 0) if str(f["demanda"]) != "NULL" else 0.0
        p = "" if f["padrao"] is None or str(f["padrao"]) == "NULL" else str(f["padrao"])
        c = "" if f["categoria"] is None or str(f["categoria"]) == "NULL" else str(f["categoria"])
        out.setdefault(str(f["no_id"]), []).append([q, p, c])
    return out


def central_demanda(nucleo):
    """Central de demanda (Demand Control Center do WaterGEMS): cada nó com a sua lista de demandas, cada uma com
    padrão e categoria. A demanda_base do nó guarda o total e o campo padrao, o padrão da primeira demanda."""
    if not nucleo.cadastro():
        return
    from qgis.PyQt.QtWidgets import QSplitter
    nos = nucleo.camada("no_juncao")
    pads = sorted({str(f["id_padrao"]) for f in nucleo.camada("padrao_consumo").getFeatures()}) \
        if _tem(nucleo, "padrao_consumo") else []
    d = Dialogo(nucleo.janela, "Central de demanda",
                "Como o Demand Control Center do WaterGEMS: cada nó pode ter várias demandas (residencial, comercial, "
                "industrial, perdas…), cada uma com o seu padrão de consumo. À esquerda os nós com o total; à direita "
                "as demandas do nó escolhido. Selecione vários nós para mudar todos de uma vez pelos botões.",
                largura=1100)
    colecao = ler_colecao(nucleo)
    info = {}  # no_id → (fid, tipo, setor)
    tocados = set()
    estado = {"mexendo": False, "no": None}

    def lista_de(nid):
        """Demandas do nó; sem coleção, a demanda base do próprio nó é a única."""
        if nid in colecao:
            return colecao[nid]
        f = nos.getFeature(info[nid][0])
        q = float(f["demanda_base"] or 0) if str(f["demanda_base"]) != "NULL" else 0.0
        p = "" if f["padrao"] is None or str(f["padrao"]) == "NULL" else str(f["padrao"])
        return [[q, p, ""]] if q else []

    split = QSplitter()
    esq = QWidget()
    ve = QVBoxLayout(esq)
    ve.setContentsMargins(0, 0, 0, 0)
    filtro = QLineEdit()
    filtro.setPlaceholderText("Filtrar nós por código, setor ou padrão…")
    ve.addWidget(filtro)
    tab = QTableWidget(0, 6)
    tab.setHorizontalHeaderLabels(["Nó", "Tipo", "Demanda total (L/s)", "Nº de demandas", "Padrão", "Setor"])
    tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tab.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tab.setSortingEnabled(True)
    ve.addWidget(tab, 1)
    total = QLabel()
    total.setStyleSheet(f"color:{COR['cyan']}; font-weight:600")
    ve.addWidget(total)
    split.addWidget(esq)

    dir_ = QWidget()
    vd = QVBoxLayout(dir_)
    vd.setContentsMargins(0, 0, 0, 0)
    titulo = QLabel("Escolha um nó na lista")
    titulo.setStyleSheet("font-weight:600")
    vd.addWidget(titulo)
    dem = QTableWidget(0, 3)
    dem.setHorizontalHeaderLabels(["Demanda (L/s)", "Padrão", "Categoria"])
    dem.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    dem.verticalHeader().setVisible(False)
    vd.addWidget(dem, 1)
    hd = QHBoxLayout()
    b_add, b_del = QPushButton("Adicionar demanda"), QPushButton("Remover demanda")
    hd.addWidget(b_add)
    hd.addWidget(b_del)
    vd.addLayout(hd)
    sub = QLabel()
    sub.setStyleSheet(f"color:{COR['muted']}")
    vd.addWidget(sub)
    split.addWidget(dir_)
    split.setSizes([620, 440])
    d.lay.addWidget(split, 1)

    def gravar_no(nid):
        """Total e padrão principal no nó (fica na edição do cadastro)."""
        lst = colecao.get(nid, [])
        if not nos.isEditable():
            nos.startEditing()
        fid = info[nid][0]
        nos.changeAttributeValue(fid, nos.fields().indexOf("demanda_base"), round(sum(q for q, _, _ in lst), 6))
        nos.changeAttributeValue(fid, nos.fields().indexOf("padrao"), (lst[0][1] if lst else None) or None)
        tocados.add(nid)

    def linha_no(i, f):
        nid = str(f["id"])
        lst = lista_de(nid)
        vals = [nid, f["tipo"], round(sum(q for q, _, _ in lst), 6), len(lst),
                ", ".join(dict.fromkeys(p for _, p, _ in lst if p)), f["setor"]]
        for j, v in enumerate(vals):
            it = QTableWidgetItem()
            if j in (2, 3):
                it.setData(Qt.ItemDataRole.DisplayRole, v)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                it.setText("" if v is None or str(v) == "NULL" else str(v))
            tab.setItem(i, j, it)

    def carregar():
        estado["mexendo"] = True
        tab.setSortingEnabled(False)
        tab.setUpdatesEnabled(False)
        feats = [f for f in nos.getFeatures()]
        info.clear()
        for f in feats:
            info[str(f["id"])] = (f.id(), f["tipo"], f["setor"])
        tab.setRowCount(len(feats))
        for i, f in enumerate(feats):
            linha_no(i, f)
        tab.setSortingEnabled(True)
        tab.setUpdatesEnabled(True)
        estado["mexendo"] = False
        filtrar()
        somar()

    def somar():
        s = n = 0
        por_cat = {}
        for nid in info:
            lst = lista_de(nid)
            q = sum(x for x, _, _ in lst)
            s += q
            n += q > 0
            for x, _, c in lst:
                por_cat[c or "(sem categoria)"] = por_cat.get(c or "(sem categoria)", 0) + x
        cats = " · ".join(f"{c}: {num(v, 3)}" for c, v in sorted(por_cat.items(), key=lambda kv: -kv[1])[:5])
        qc, nc = total_consumidores(nucleo)
        cons = (f"<br>Consumidores: {num(qc, 3)} L/s em {nc} (somados ao nó ou às pontas da tubulação a que "
                f"estão ligados)") if nc else ""
        total.setText(f"Total: {num(s, 3)} L/s ({num(s * 86.4, 0)} m³/dia) em {n} nós com demanda"
                      + (f"<br><span style='font-weight:400'>{cats}</span>" if len(por_cat) > 1 else "") + cons)

    def filtrar():
        t = filtro.text().strip().lower()
        for i in range(tab.rowCount()):
            txt = " ".join((tab.item(i, j).text() if tab.item(i, j) else "") for j in (0, 4, 5)).lower()
            tab.setRowHidden(i, bool(t) and t not in txt)

    def nos_sel():
        return [tab.item(r, 0).text() for r in sorted({i.row() for i in tab.selectedIndexes()})
                if not tab.isRowHidden(r)]

    def mostrar_no():
        sel = nos_sel()
        nid = sel[0] if len(sel) == 1 else None
        estado["no"] = nid
        estado["mexendo"] = True
        dem.setRowCount(0)
        b_add.setEnabled(nid is not None)
        b_del.setEnabled(nid is not None)
        if nid is None:
            titulo.setText(f"{len(sel)} nós selecionados: use os botões de baixo" if sel else "Escolha um nó na lista")
            sub.setText("")
            estado["mexendo"] = False
            return
        titulo.setText(f"Demandas do nó {nid}")
        for q, p, c in lista_de(nid):
            por_linha(q, p, c)
        estado["mexendo"] = False
        resumo_no()

    def por_linha(q, p, c):
        i = dem.rowCount()
        dem.insertRow(i)
        it = QTableWidgetItem()
        it.setData(Qt.ItemDataRole.DisplayRole, float(q))
        dem.setItem(i, 0, it)
        cb = QComboBox()
        cb.addItem("(constante)", "")
        for x in pads:
            cb.addItem(x, x)
        cb.setCurrentIndex(max(0, cb.findData(p)))
        cb.currentIndexChanged.connect(lambda _: guardar())
        dem.setCellWidget(i, 1, cb)
        dem.setItem(i, 2, QTableWidgetItem(c))

    def resumo_no():
        lst = colecao.get(estado["no"]) or lista_de(estado["no"])
        sub.setText(f"Total do nó: {num(sum(q for q, _, _ in lst), 4)} L/s em {len(lst)} demanda(s)")

    def guardar():
        """Tabela da direita → coleção do nó → total no nó e na lista da esquerda."""
        nid = estado["no"]
        if estado["mexendo"] or nid is None:
            return
        lst = []
        for i in range(dem.rowCount()):
            try:
                q = float(str(dem.item(i, 0).data(Qt.ItemDataRole.DisplayRole) or 0).replace(",", "."))
            except ValueError:
                q = 0.0
            lst.append([q, dem.cellWidget(i, 1).currentData() or "", dem.item(i, 2).text().strip() if dem.item(i, 2) else ""])
        colecao[nid] = lst
        gravar_no(nid)
        atualizar_linhas([nid])
        resumo_no()
        somar()

    def atualizar_linhas(ids):
        alvo = set(ids)
        estado["mexendo"] = True
        tab.setSortingEnabled(False)
        for i in range(tab.rowCount()):
            if tab.item(i, 0).text() in alvo:
                linha_no(i, nos.getFeature(info[tab.item(i, 0).text()][0]))
        tab.setSortingEnabled(True)
        estado["mexendo"] = False

    def adicionar():
        if estado["no"] is None:
            return
        estado["mexendo"] = True
        por_linha(0.0, pads[0] if pads else "", "")
        estado["mexendo"] = False
        guardar()

    def remover():
        r = dem.currentRow()
        if r >= 0:
            dem.removeRow(r)
            guardar()

    def em_lote(func, titulo_cmd):
        ids = nos_sel() or [tab.item(r, 0).text() for r in range(tab.rowCount()) if not tab.isRowHidden(r)]
        if not ids:
            return
        nos.startEditing() if not nos.isEditable() else None
        nos.beginEditCommand(titulo_cmd)
        try:
            for nid in ids:
                colecao[nid] = func([list(x) for x in lista_de(nid)])
                gravar_no(nid)
        finally:
            nos.endEditCommand()
        atualizar_linhas(ids)
        mostrar_no()
        somar()
        nucleo.informar(f"{titulo_cmd}: {len(ids)} nó(s).")

    def multiplicar():
        f, ok = QInputDialog.getDouble(d, "Multiplicar", "Fator (ex.: 1,2 = +20%) para os nós selecionados (ou todos "
                                       "os da lista):", 1.0, 0, 100, 3)
        if ok:
            em_lote(lambda lst: [[round(q * f, 6), p, c] for q, p, c in lst], "Multiplicar demandas")

    def padrao():
        p, ok = QInputDialog.getItem(d, "Padrão", "Padrão para todas as demandas dos nós selecionados (ou de todos):",
                                     ["(constante)"] + pads, 0, False)
        if ok:
            p = "" if p == "(constante)" else p
            em_lote(lambda lst: [[q, p, c] for q, _, c in lst], "Trocar o padrão")

    def nova_em_todos():
        dd = Dialogo(d, "Adicionar demanda", "Acrescenta uma demanda a cada nó selecionado (ou a todos da lista), "
                     "sem mexer nas que eles já têm. Ex.: perdas de 0,01 L/s por nó com o padrão de perdas.")
        q = dd.linha("Demanda (L/s):", QDoubleSpinBox())
        q.setDecimals(4)
        q.setRange(0, 1e6)
        p = dd.linha("Padrão:", QComboBox())
        p.addItem("(constante)", "")
        for x in pads:
            p.addItem(x, x)
        c = dd.linha("Categoria:", QLineEdit())
        c.setPlaceholderText("ex.: comercial, perdas, industrial")
        dd.botoes("Adicionar")
        if dd.exec():
            em_lote(lambda lst: lst + [[q.value(), p.currentData() or "", c.text().strip()]], "Adicionar demanda")

    def distribuir():
        nucleo.executar("demanda")
        colecao_nova = ler_colecao(nucleo)
        colecao.clear()
        colecao.update(colecao_nova)
        carregar()

    def no_mapa():
        selecionar_ids(nucleo, nos_sel())

    def nos_consumidores():
        if distribuir_consumidores(nucleo, d, pads):
            somar()

    h = QHBoxLayout()
    for texto, f, dica in (("Multiplicar…", multiplicar, "Multiplica todas as demandas dos nós"),
                           ("Padrão…", padrao, "Mesmo padrão em todas as demandas dos nós"),
                           ("Adicionar demanda aos nós…", nova_em_todos, "Uma demanda a mais em cada nó"),
                           ("Distribuir uma vazão total…", distribuir, "Reparte uma vazão pelos nós"),
                           ("Distribuir nos consumidores…", nos_consumidores,
                            "Reparte uma vazão pelos consumidores (casas), que levam a demanda ao nó ou à tubulação"),
                           ("Selecionar no mapa", no_mapa, "")):
        b = QPushButton(texto)
        b.setToolTip(dica)
        b.clicked.connect(f)
        h.addWidget(b)
    h.addStretch(1)
    d.lay.addLayout(h)
    tab.itemSelectionChanged.connect(mostrar_no)
    filtro.textChanged.connect(lambda _: filtrar())
    dem.itemChanged.connect(lambda _: guardar())
    b_add.clicked.connect(adicionar)
    b_del.clicked.connect(remover)
    carregar()
    mostrar_no()
    d.resize(1150, 660)
    d.botoes("Gravar", "Fechar")
    if not d.exec() or not tocados:
        if tocados:
            nucleo.informar("Os totais dos nós ficaram na edição (Salvar edições grava); as demandas por categoria "
                            "só são gravadas pelo botão Gravar.")
        return
    lyr = tabela_demandas(nucleo)
    if lyr is None:
        return
    linhas = []
    for nid, lst in colecao.items():
        if nid not in info:
            continue
        if len(lst) == 1 and not lst[0][2]:  # uma demanda só, sem categoria: o próprio nó já guarda
            continue
        linhas += [{"no_id": nid, "demanda": q, "padrao": p or None, "categoria": c or None} for q, p, c in lst]
    if _substituir(nucleo, lyr, linhas, ["no_id", "demanda", "padrao", "categoria"]):
        nucleo.informar(f"Demandas gravadas: {len(linhas)} linha(s) em {len({l['no_id'] for l in linhas})} nó(s) com "
                        "mais de uma demanda. Os totais dos nós ficaram na edição: Salvar edições grava.")


def total_consumidores(nucleo):
    """(vazão, quantos) dos consumidores com demanda."""
    try:
        cons = nucleo.camada("consumidor")
    except LookupError:
        return 0.0, 0
    q = [float(f["demanda_base"]) for f in cons.getFeatures()
         if f["demanda_base"] not in (None, "") and str(f["demanda_base"]) != "NULL" and float(f["demanda_base"]) > 0]
    return sum(q), len(q)


def distribuir_consumidores(nucleo, pai, pads):
    """Reparte uma vazão total entre os consumidores (todos, de um setor ou os selecionados no mapa): igual para cada
    um ou proporcional a um campo numérico (ex.: economias, consumo medido). Fica na edição da camada."""
    from qgis.core import QgsFeatureRequest
    try:
        cons = nucleo.camada("consumidor")
    except LookupError:
        nucleo.aviso("Este cadastro não tem consumidores: desenhe com o botão Consumidor (aba Desenho).")
        return False
    feats = list(cons.getFeatures())
    if not feats:
        nucleo.aviso("Nenhum consumidor no cadastro: desenhe com o botão Consumidor (aba Desenho).")
        return False
    dd = Dialogo(pai, "Distribuir nos consumidores",
                 "Reparte uma vazão total entre os consumidores, como o LoadBuilder do WaterGEMS com os Customer "
                 "Meters. Cada consumidor leva a sua parte para o nó, ou para as pontas da tubulação, a que está ligado.")
    q = dd.linha("Vazão total (L/s):", QDoubleSpinBox())
    q.setRange(0, 1e6)
    q.setDecimals(4)
    q.setValue(10)
    escopo = dd.linha("Distribuir entre:", QComboBox())
    escopo.addItem(f"Todos os consumidores ({len(feats)})", ("todos", None))
    for st in sorted({str(f["setor"]) for f in feats if f["setor"] not in (None, "") and str(f["setor"]) != "NULL"}):
        escopo.addItem(f"Consumidores do setor {st}", ("setor", st))
    if cons.selectedFeatureCount():
        escopo.addItem(f"Selecionados no mapa ({cons.selectedFeatureCount()})", ("selecao", None))
    metodo = dd.linha("Método:", QComboBox())
    metodo.addItem("Igual para todos", None)
    for fld in cons.fields():
        if fld.isNumeric() and fld.name() not in ("fid", "demanda_base"):
            metodo.addItem(f"Proporcional ao campo {fld.name()}", fld.name())
    pad = dd.linha("Padrão:", QComboBox())
    pad.addItem("(manter o de cada consumidor)", None)
    pad.addItem("(nenhum: o do nó)", "")
    for x in pads:
        pad.addItem(x, x)
    dd.botoes("Distribuir")
    if not dd.exec():
        return False
    tipo, setor = escopo.currentData()
    if tipo == "selecao":
        alvo = list(cons.getFeatures(QgsFeatureRequest().setFilterFids(list(cons.selectedFeatureIds()))))
    elif tipo == "setor":
        alvo = [f for f in feats if str(f["setor"]) == setor]
    else:
        alvo = feats
    campo = metodo.currentData()

    def peso(f):
        if campo is None:
            return 1.0
        v = f[campo]
        return float(v) if v not in (None, "") and str(v) != "NULL" else 0.0
    pesos = {f.id(): peso(f) for f in alvo}
    soma = sum(pesos.values())
    if not alvo or soma <= 0:
        nucleo.aviso("Nenhum consumidor com peso maior que zero no grupo escolhido.")
        return False
    if not cons.isEditable():
        cons.startEditing()
    i_q, i_p = cons.fields().indexOf("demanda_base"), cons.fields().indexOf("padrao")
    cons.beginEditCommand("Distribuir nos consumidores")
    for f in alvo:
        cons.changeAttributeValue(f.id(), i_q, round(q.value() * pesos[f.id()] / soma, 6))
        if pad.currentData() is not None:
            cons.changeAttributeValue(f.id(), i_p, pad.currentData() or None)
    cons.endEditCommand()
    nucleo.informar(f"{num(q.value(), 3)} L/s distribuídos entre {len(alvo)} consumidor(es). Salvar edições grava.")
    return True


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
    "valvula": [("tipo", ["PRV", "PSV", "PBV", "FCV", "VRE", "VSE", "TCV", "GPV", "RETENCAO", "TURBINA",
                           "ORIFICIO", "AREA_LINEAR"]), ("diametro", float), ("ajuste", float),
                ("status", ["ATIVA", "INATIVA", "ABERTA", "FECHADA"])],
    "bomba": [("curva", str), ("status_inicial", ["ABERTA", "FECHADA"]), ("rotacao_relativa", float),
              ("elevatoria", str)],
    "reservatorio": [("cota_fundo", float), ("nivel_ini", float), ("nivel_min", float), ("nivel_max", float),
                     ("diametro", float)],
    "captacao": [("carga_hidraulica", float)],
    "trecho": [("status", ["ABERTO", "FECHADO", "CV"]), ("ano_instalacao", "ano"), ("setor", str)],
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
        if tipo == "ano":  # aceita 1998 ou 15/03/1998
            from gwater.modelbuilder import ano
            if ano(txt) is not None:
                novos.setdefault(c, {})[nome] = float(ano(txt))
        elif tipo is float:
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
