"""Peças comuns das janelas do GWATER.exe: diálogo padrão, tabela de resultados (copiar / exportar CSV),
gráfico (matplotlib no tema do GWATER), camada de resultado colorida, busca de elementos pelo código."""
import csv
import os

from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsFeature, QgsField, QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol,
    QgsProject, QgsRendererCategory, QgsRendererRange, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

PONTOS = ("captacao", "reservatorio", "bomba", "valvula", "no_juncao")
NOMES = {"captacao": "Captação", "reservatorio": "Reservatório", "bomba": "Bomba", "valvula": "Válvula",
         "no_juncao": "Nó", "trecho": "Tubulação"}
GRUPO_ANALISES = "Análises GWATER"


def num(x, d=2):
    if x is None or x == "":
        return "–"
    try:
        return f"{float(x):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(x)


class Dialogo(QDialog):
    """Janela padrão: título, texto de explicação, formulário e botões."""

    def __init__(self, pai, titulo, explicacao="", largura=560):
        super().__init__(pai)
        self.setWindowTitle(f"GWATER · {titulo}")
        self.setMinimumWidth(largura)
        self.lay = QVBoxLayout(self)
        if explicacao:
            lb = QLabel(explicacao)
            lb.setWordWrap(True)
            lb.setStyleSheet(f"color:{COR['muted']}; padding:2px 2px 8px 2px")
            self.lay.addWidget(lb)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.lay.addLayout(self.form)

    def linha(self, rotulo, w, dica=""):
        if dica:
            w.setToolTip(dica)
        self.form.addRow(rotulo, w)
        return w

    def botoes(self, ok="OK", cancelar="Cancelar"):
        bb = QDialogButtonBox()
        if ok:
            b = bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
            b.setDefault(True)
        if cancelar:
            bb.addButton(cancelar, QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.lay.addWidget(bb)
        return bb


class Tabela(QTableWidget):
    """Tabela só de leitura com ordenação, cópia (Ctrl+C) e exportação para CSV (abre no Excel)."""

    def __init__(self, colunas, pai=None):
        super().__init__(0, len(colunas), pai)
        self.setHorizontalHeaderLabels(colunas)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSortingEnabled(True)

    def preencher(self, linhas, cores=None):
        """linhas: listas de valores; números ficam ordenáveis como número. cores: {linha: cor do texto}."""
        self.setSortingEnabled(False)
        self.setUpdatesEnabled(False)
        self.setRowCount(len(linhas))
        for i, lin in enumerate(linhas):
            for j, v in enumerate(lin):
                it = QTableWidgetItem()
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it.setData(Qt.ItemDataRole.DisplayRole, v)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    it.setText("" if v is None else str(v))
                if cores and i in cores:
                    it.setForeground(QColor(cores[i]))
                self.setItem(i, j, it)
        self.horizontalHeader().setResizeContentsPrecision(300)  # largura pelas primeiras linhas
        self.resizeColumnsToContents()
        for j in range(self.columnCount()):
            self.setColumnWidth(j, min(self.columnWidth(j) + 12, 340))
        self.setSortingEnabled(True)
        self.setUpdatesEnabled(True)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copiar()
        else:
            super().keyPressEvent(e)

    def copiar(self):
        linhas = sorted({i.row() for i in self.selectedIndexes()}) or range(self.rowCount())
        cab = [self.horizontalHeaderItem(j).text() for j in range(self.columnCount())]
        txt = ["\t".join(cab)] + ["\t".join((self.item(i, j).text() if self.item(i, j) else "")
                                            for j in range(self.columnCount())) for i in linhas]
        QApplication.clipboard().setText("\n".join(txt))

    def exportar(self, pai, nome="tabela"):
        arq, _ = QFileDialog.getSaveFileName(pai, "Exportar tabela", nome + ".csv", "CSV (Excel) (*.csv)")
        if not arq:
            return
        with open(arq, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([self.horizontalHeaderItem(j).text() for j in range(self.columnCount())])
            for i in range(self.rowCount()):
                lin = []
                for j in range(self.columnCount()):
                    it = self.item(i, j)
                    v = it.data(Qt.ItemDataRole.DisplayRole) if it else ""
                    lin.append(str(v).replace(".", ",") if isinstance(v, float) else (it.text() if it else ""))
                w.writerow(lin)
        return arq


def barra_tabela(tabela, pai, nome, extras=()):
    """Linha de botões embaixo de uma tabela: Copiar, Exportar CSV e botões extras [(texto, função)]."""
    h = QHBoxLayout()
    for texto, func in extras:
        b = QPushButton(texto)
        b.clicked.connect(func)
        h.addWidget(b)
    h.addStretch(1)
    b = QPushButton("Copiar")
    b.setToolTip("Copia as linhas selecionadas (ou todas) para colar no Excel")
    b.clicked.connect(tabela.copiar)
    h.addWidget(b)
    b = QPushButton("Exportar CSV…")
    b.clicked.connect(lambda: tabela.exportar(pai, nome))
    h.addWidget(b)
    return h


# ---------------------------------------------------------------- gráficos
def figura(pai=None, altura=3.2):
    """(widget, figura) do matplotlib no tema do GWATER."""
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
    from matplotlib.figure import Figure
    fig = Figure(figsize=(6, altura), facecolor=COR["panel"], tight_layout=True)
    can = FigureCanvasQTAgg(fig)
    w = QWidget(pai)
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    barra = NavigationToolbar2QT(can, w)
    barra.setStyleSheet(f"background:{COR['panel']}; border:none")
    v.addWidget(barra)
    v.addWidget(can, 1)
    w.canvas, w.figura = can, fig
    return w, fig


def eixo(fig, sub=111, titulo="", x="", y=""):
    ax = fig.add_subplot(sub)
    ax.set_facecolor(COR["panel"])
    for s in ax.spines.values():
        s.set_color(COR["line"])
    ax.tick_params(colors=COR["muted"], labelsize=8)
    ax.grid(True, color=COR["grid"], linewidth=0.6)
    if titulo:
        ax.set_title(titulo, color=COR["text"], fontsize=10, loc="left")
    ax.set_xlabel(x, color=COR["muted"], fontsize=8)
    ax.set_ylabel(y, color=COR["muted"], fontsize=8)
    return ax


CORES = ["#35d0ff", "#3ddc97", "#ffb547", "#a78bfa", "#ff6b7a", "#7fd0ff", "#f0abfc", "#fde68a"]


def legenda(ax):
    leg = ax.legend(fontsize=8, facecolor=COR["panel2"], edgecolor=COR["line"], labelcolor=COR["text"])
    return leg


# ---------------------------------------------------------------- elementos e seleção
def achar(nucleo, eid):
    """(camada, feição) de um código, procurando em todas as camadas do cadastro."""
    eid = str(eid).split("__")[0]
    for lyr in nucleo.camadas_rede():
        for f in lyr.getFeatures(f"\"id\" = '{eid}'"):
            return lyr, f
    return None, None


def selecionar_ids(nucleo, ids, zoom=True):
    """Seleciona elementos pelos códigos (em qualquer camada) e enquadra."""
    ids = {str(i).split("__")[0] for i in ids}
    janela = nucleo.janela
    ext = None
    for lyr in nucleo.camadas_rede():
        fids = [f.id() for f in lyr.getFeatures() if str(f["id"]) in ids]
        lyr.selectByIds(fids)
        if fids:
            e = janela.canvas.mapSettings().layerExtentToOutputExtent(lyr, lyr.boundingBoxOfSelected())
            ext = e if ext is None else (ext.combineExtentWith(e) or ext)
    if zoom and ext is not None:
        if ext.width() < 50:
            ext.grow(60)
        else:
            ext.grow(max(ext.width(), ext.height()) * 0.1)
        janela.canvas.setExtent(ext)
        janela.canvas.refresh()
    janela._selecao_mudou()


def ids_selecionados(nucleo, camada=None):
    out = []
    for lyr, fids in nucleo.janela.selecionados():
        if camada and lyr != nucleo.camada(camada):
            continue
        out += [str(f["id"]) for f in lyr.getFeatures(fids)]
    return out


def gpkg_salvo(nucleo):
    """Cadastro gravado em disco (pergunta para salvar as edições: o motor lê o arquivo)."""
    return nucleo._preparar()


# ---------------------------------------------------------------- camadas de resultado das análises
def grupo_analises():
    raiz = QgsProject.instance().layerTreeRoot()
    g = raiz.findGroup(GRUPO_ANALISES)
    return g or raiz.insertGroup(0, GRUPO_ANALISES)


def remover_analise(nome):
    prj = QgsProject.instance()
    for lyr in list(prj.mapLayersByName(nome)):
        prj.removeMapLayer(lyr.id())


def camada_resultado(nucleo, nome, valores, campo, faixas=None, categorias=None, camadas=None, unidade=""):
    """Camada de memória com os elementos do cadastro e um valor por código, colorida.
    valores: {código: valor}; faixas: [(de, até, cor, rótulo)]; categorias: {valor: (cor, rótulo)}."""
    remover_analise(nome)
    camadas = camadas or ["no_juncao"]
    lyr0 = nucleo.camada(camadas[0])
    geo = "Point" if camadas[0] != "trecho" else "LineString"
    lyr = QgsVectorLayer(f"{geo}?crs={lyr0.crs().authid()}", nome, "memory")
    tipo = QVariant.Double if faixas else QVariant.String if categorias and any(isinstance(k, str) for k in categorias) \
        else QVariant.Double
    lyr.dataProvider().addAttributes([QgsField("id", QVariant.String), QgsField(campo, tipo)])
    lyr.updateFields()
    feats = []
    for c in camadas:
        for f in nucleo.camada(c).getFeatures():
            v = valores.get(str(f["id"]))
            if v is None:
                continue
            nf = QgsFeature(lyr.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes([f["id"], v])
            feats.append(nf)
    lyr.dataProvider().addFeatures(feats)
    simbolo = (lambda cor: QgsLineSymbol.createSimple({"color": cor, "width": "1.6", "capstyle": "round"})) \
        if geo == "LineString" else \
        (lambda cor: QgsMarkerSymbol.createSimple({"name": "circle", "color": cor, "size": "3.4",
                                                   "outline_color": "#1b1b1b", "outline_width": "0.25"}))
    if faixas:
        lyr.setRenderer(QgsGraduatedSymbolRenderer(campo, [
            QgsRendererRange(-1e12 if a is None else a, 1e12 if b is None else b, simbolo(cor), rot)
            for a, b, cor, rot in faixas]))
    elif categorias:
        lyr.setRenderer(QgsCategorizedSymbolRenderer(campo, [
            QgsRendererCategory(k, simbolo(cor), rot) for k, (cor, rot) in categorias.items()]))
    QgsProject.instance().addMapLayer(lyr, False)
    grupo_analises().insertLayer(0, lyr)
    nucleo.janela.canvas.refresh()
    return lyr


def cores_categorias(n):
    base = ["#1c7ed6", "#2fb36f", "#f59f00", "#ae3ec9", "#e5484d", "#0ca678", "#f76707", "#4263eb", "#d6336c",
            "#74b816", "#1098ad", "#7048e8"]
    return [base[i % len(base)] for i in range(n)]


def janela_resultado(nucleo, titulo, explicacao, colunas, linhas, nome_csv, ao_clicar=None, extras=(), cores=None,
                     topo=None):
    """Aba no centro do programa com explicação, um widget opcional no topo, a tabela e os botões.
    ao_clicar(código): clique duplo numa linha (padrão: seleciona e enquadra o elemento)."""
    w = QWidget()
    v = QVBoxLayout(w)
    if explicacao:
        lb = QLabel(explicacao)
        lb.setWordWrap(True)
        lb.setTextFormat(Qt.TextFormat.RichText)
        lb.setStyleSheet(f"color:{COR['text']}; padding:4px")
        v.addWidget(lb)
    if topo is not None:
        v.addWidget(topo)
    t = Tabela(colunas)
    t.preencher(linhas, cores)
    t.cellDoubleClicked.connect(lambda i, _j: (ao_clicar or (lambda c: selecionar_ids(nucleo, [c])))(t.item(i, 0).text()))
    v.addWidget(t, 1)
    v.addLayout(barra_tabela(t, w, nome_csv, extras))
    w.tabela = t
    nucleo.janela.abrir_aba(w, titulo, "relatorio")
    return w


def ligar(sinal, widget, funcao):
    """Conecta `funcao` ao `sinal` enquanto o `widget` existir (abas fechadas não recebem mais avisos)."""
    def slot(*a):
        try:
            funcao(*a)
        except RuntimeError:  # o widget foi apagado entre o aviso e a chamada
            pass
    sinal.connect(slot)

    def soltar(*_):
        try:
            sinal.disconnect(slot)
        except (TypeError, RuntimeError):
            pass
    widget.destroyed.connect(soltar)
