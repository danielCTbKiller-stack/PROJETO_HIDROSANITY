"""Gráficos: série do dia dos elementos, gráfico rápido (clique), perfil entre dois nós e contornos."""
import math
from collections import defaultdict

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSlider, QSpinBox,
    QSplitter, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .tabelas import RESULTADOS
from .util import CORES, NOMES, Dialogo, achar, eixo, figura, ids_selecionados, legenda, ligar, num


def _camada_de(nucleo, lyr):
    for c in NOMES:
        try:
            if nucleo.camada(c) == lyr:
                return c
        except LookupError:
            pass
    return None


def _precisa_resultado(nucleo):
    if not nucleo.res:
        nucleo.aviso("Calcule a rede primeiro (Calcular, F5): os gráficos mostram os resultados da simulação.")
        return False
    return True


# ================================================================ gráfico de série
class Grafico(QWidget):
    """Lista de elementos à esquerda e o gráfico do dia da variável escolhida à direita."""

    def __init__(self, nucleo, elementos):
        super().__init__()
        self.nucleo = nucleo
        h = QHBoxLayout(self)
        esq = QVBoxLayout()
        esq.addWidget(QLabel("Elementos"))
        self.lista = QListWidget()
        self.lista.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for camada, eid in elementos:
            it = QListWidgetItem(f"{NOMES.get(camada, camada)} {eid}")
            it.setData(Qt.ItemDataRole.UserRole, (camada, eid))
            self.lista.addItem(it)
            it.setSelected(True)
        esq.addWidget(self.lista, 1)
        b = QPushButton("Somar os selecionados no mapa")
        b.clicked.connect(self._somar)
        esq.addWidget(b)
        b = QPushButton("Tirar da lista")
        b.clicked.connect(lambda: [self.lista.takeItem(self.lista.row(i)) for i in self.lista.selectedItems()])
        esq.addWidget(b)
        esq.addWidget(QLabel("Variável"))
        self.var = QComboBox()
        esq.addWidget(self.var)
        caixa = QWidget()
        caixa.setLayout(esq)
        caixa.setMaximumWidth(280)
        h.addWidget(caixa)
        self.w, self.fig = figura(self, 4)
        h.addWidget(self.w, 1)
        self.lista.itemSelectionChanged.connect(self._variaveis)
        self.var.currentIndexChanged.connect(self.desenhar)
        ligar(nucleo.janela.resultados, self, lambda *_: self.desenhar())
        ligar(nucleo.dock.hora_lenta, self, lambda *_: self.desenhar())
        self._variaveis()

    def _somar(self):
        for lyr, fids in self.nucleo.janela.selecionados():
            camada = _camada_de(self.nucleo, lyr)
            for f in lyr.getFeatures(fids):
                it = QListWidgetItem(f"{NOMES.get(camada, camada)} {f['id']}")
                it.setData(Qt.ItemDataRole.UserRole, (camada, str(f["id"])))
                self.lista.addItem(it)
                it.setSelected(True)

    def _variaveis(self):
        tipos = {self.lista.item(i).data(Qt.ItemDataRole.UserRole)[0] for i in range(self.lista.count())
                 if self.lista.item(i).isSelected()}
        nomes = []
        for t in tipos:
            for c, _ in RESULTADOS.get(t, []):
                if "dia" not in c and c not in nomes and c not in ("Estado", "Horas ligada"):
                    nomes.append(c)
        atual = self.var.currentText()
        self.var.blockSignals(True)
        self.var.clear()
        self.var.addItems(nomes)
        if atual in nomes:
            self.var.setCurrentText(atual)
        self.var.blockSignals(False)
        self.desenhar()

    def desenhar(self):
        self.fig.clear()
        res = self.nucleo.res
        var = self.var.currentText()
        ax = eixo(self.fig, titulo=var, x="hora", y=var)
        if not res or not var:
            ax.text(0.5, 0.5, "Calcule a rede (F5) para ver os gráficos", color=COR["muted"], ha="center",
                    transform=ax.transAxes)
            self.w.canvas.draw_idle()
            return
        horas = res.horas
        n = 0
        for i in range(self.lista.count()):
            it = self.lista.item(i)
            if not it.isSelected():
                continue
            camada, eid = it.data(Qt.ItemDataRole.UserRole)
            fn = dict(RESULTADOS.get(camada, [])).get(var)
            if fn is None:
                continue
            try:
                ys = [fn(res.d, eid, k) for k in range(len(horas))]
            except (KeyError, IndexError, TypeError):
                continue
            if any(y is None for y in ys):
                continue
            ax.plot(horas, ys, color=CORES[n % len(CORES)], linewidth=1.8, label=it.text())
            n += 1
        k = self.nucleo.janela.passo()
        ax.axvline(horas[k], color=COR["warn"], linestyle="--", linewidth=1)
        ax.set_xlim(horas[0], horas[-1])
        ax.set_xticks(range(0, int(math.ceil(horas[-1])) + 1, 3))
        if "Pressão" in var and "sucção" not in var:
            from .componentes import limites
            lim = limites(self.nucleo)
            ax.axhline(lim["limite_pressao_min"], color=COR["crit"], linewidth=0.8, linestyle=":")
            ax.axhline(lim["limite_pressao_max"], color=COR["warn"], linewidth=0.8, linestyle=":")
        n += self._medicoes(ax, var)
        if n:
            legenda(ax)
        self.w.canvas.draw_idle()


GRANDEZA_VAR = {"Pressão": "pressao", "Vazão": "vazao", "Nível": "nivel", "Carga": "carga"}


def medicoes_de(nucleo, eid, grandeza):
    """[(hora, valor)] das leituras de campo do estudo de calibração para o elemento."""
    out = []
    for mo in nucleo.janela._ler_json("calibracao", {}).get("momentos", []):
        for o in mo.get("observacoes", []):
            if str(o.get("elemento")) == str(eid) and o.get("grandeza") == grandeza:
                try:
                    out.append((float(mo.get("hora") or 0), float(o["valor"])))
                except (TypeError, ValueError):
                    pass
    return sorted(out)


def _medicoes(self, ax, var):
    """Leituras de campo (Calibração) do mesmo elemento e grandeza, como pontos sobre a curva calculada."""
    gr = next((g for k, g in GRANDEZA_VAR.items() if var.startswith(k)), None)
    if not gr:
        return 0
    n = 0
    for i in range(self.lista.count()):
        it = self.lista.item(i)
        if not it.isSelected():
            continue
        _, eid = it.data(Qt.ItemDataRole.UserRole)
        pts = medicoes_de(self.nucleo, eid, gr)
        if pts:
            ax.scatter([h for h, _ in pts], [v for _, v in pts], color=COR["warn"], edgecolor=COR["bg"], s=34,
                       zorder=5, label=f"medido em campo · {eid}")
            n += 1
    return n


Grafico._medicoes = _medicoes


def graficos(nucleo):
    if not nucleo.cadastro():
        return nucleo.aviso("Abra um cadastro primeiro.")
    elems = []
    for lyr, fids in nucleo.janela.selecionados():
        camada = _camada_de(nucleo, lyr)
        elems += [(camada, str(f["id"])) for f in lyr.getFeatures(fids)][:30]
    if not elems:
        nucleo.informar("Selecione um ou mais elementos no mapa para o gráfico (ou use Gráfico rápido e clique num "
                        "elemento).")
    if not nucleo.res:
        nucleo.aviso("Ainda não há resultados: calcule a rede (F5) e o gráfico se atualiza sozinho.")
    nucleo.janela.abrir_aba(Grafico(nucleo, elems), "Gráfico", "graficos")


def grafico_rapido(nucleo):
    if not nucleo.cadastro():
        return
    from .ferramentas_mapa import FerramentaClique
    janela = nucleo.janela

    def clicou(lyr, fid, _p):
        if lyr is None:
            return
        f = lyr.getFeature(fid)
        camada = _camada_de(nucleo, lyr)
        if not _precisa_resultado(nucleo):
            return
        d = Dialogo(janela, f"Gráfico rápido · {NOMES.get(camada, '')} {f['id']}", largura=640)
        g = Grafico(nucleo, [(camada, str(f["id"]))])
        g.setMinimumHeight(360)
        d.lay.addWidget(g)
        d.botoes(None, "Fechar")
        d.setModal(False)
        d.show()
        janela._graficos_rapidos = getattr(janela, "_graficos_rapidos", []) + [d]

    janela.usar_ferramenta(FerramentaClique(janela.canvas, nucleo.camadas_rede, clicou), "grafico_rapido")
    nucleo.dock.status.setText("<b>Gráfico rápido</b>: clique num elemento. Esc para parar.")


# ================================================================ perfil
def _grafo(nucleo):
    """Rede do cadastro: nós (todas as camadas de pontos) e tubulações com comprimento."""
    import networkx as nx
    g = nx.Graph()
    for f in nucleo.camada("trecho").getFeatures():
        a, b = str(f["no_inicial"]), str(f["no_final"])
        if a and b and a != "NULL" and b != "NULL":
            L = f["comprimento"] if f["comprimento"] not in (None, "") and str(f["comprimento"]) != "NULL" \
                else f.geometry().length()
            g.add_edge(a, b, id=str(f["id"]), L=float(L))
    return g


class Perfil(QWidget):
    def __init__(self, nucleo, caminho, g):
        super().__init__()
        self.nucleo, self.caminho, self.g = nucleo, caminho, g
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.info = QLabel()
        topo.addWidget(self.info, 1)
        v.addLayout(topo)
        self.w, self.fig = figura(self, 4)
        v.addWidget(self.w, 1)
        cotas = {}
        for lyr in nucleo.camadas_rede():
            if lyr.fields().indexOf("cota") >= 0:
                for f in lyr.getFeatures():
                    cotas[str(f["id"])] = f["cota"]
        self.cotas = cotas
        self.dist = [0.0]
        for a, b in zip(caminho, caminho[1:]):
            self.dist.append(self.dist[-1] + g[a][b]["L"])
        L = self.dist[-1]
        self.info.setText(f"Perfil de <b>{caminho[0]}</b> a <b>{caminho[-1]}</b>: {len(caminho)} nós, "
                          f"{num(L, 1)} m. A linha piezométrica é da hora escolhida (linha do tempo).")
        ligar(nucleo.dock.hora_lenta, self, lambda *_: self.desenhar())
        ligar(nucleo.janela.resultados, self, lambda *_: self.desenhar())
        self.desenhar()

    def desenhar(self):
        self.fig.clear()
        ax = eixo(self.fig, titulo="Perfil hidráulico", x="distância (m)", y="cota (m)")
        xs, terreno = [], []
        for d, n in zip(self.dist, self.caminho):
            c = self.cotas.get(n)
            if c is not None and str(c) != "NULL":
                xs.append(d)
                terreno.append(float(c))
        if xs:
            ax.fill_between(xs, terreno, min(terreno) - 5, color="#6b4f2a", alpha=0.35)
            ax.plot(xs, terreno, color="#c49a5a", linewidth=1.6, label="terreno")
        res = self.nucleo.res
        if res:
            k = self.nucleo.janela.passo()
            hx, hy = [], []
            for d, n in zip(self.dist, self.caminho):
                for nome in (n, f"{n}__M", f"{n}__J"):
                    no = res.d["nos"].get(nome)
                    if no:
                        hx.append(d)
                        hy.append(no["h"][k])
            if hx:
                from .componentes import limites
                pmin = limites(self.nucleo)["limite_pressao_min"]
                ax.plot(hx, hy, color=COR["cyan"], linewidth=2, label="linha piezométrica")
                ax.plot([x for x, n in zip(self.dist, self.caminho) if self.cotas.get(n) not in (None, "NULL")],
                        [float(self.cotas[n]) + pmin for n in self.caminho if self.cotas.get(n) not in (None, "NULL")],
                        color=COR["crit"], linewidth=0.8, linestyle=":", label=f"terreno + {pmin:g} mca")
            from gwater.resultados import _hora
            ax.set_title(f"Perfil hidráulico · {_hora(res.horas[k])}", color=COR["text"], fontsize=10, loc="left")
        for d, n in zip(self.dist, self.caminho):
            if len(self.caminho) <= 25:
                ax.annotate(n, (d, ax.get_ylim()[0]), color=COR["muted"], fontsize=7, rotation=90, va="bottom")
        legenda(ax)
        self.w.canvas.draw_idle()


def perfis(nucleo):
    if not nucleo.cadastro():
        return
    import networkx as nx
    janela = nucleo.janela
    sel = [i for i in ids_selecionados(nucleo) if i]
    pontos = [i for i in sel if achar(nucleo, i)[0] is not None and achar(nucleo, i)[0] != nucleo.camada("trecho")]
    g = _grafo(nucleo)

    def montar(a, b):
        try:
            caminho = nx.shortest_path(g, a, b, weight="L")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return nucleo.aviso(f"Não há caminho pela rede entre {a} e {b}.")
        from .util import selecionar_ids
        selecionar_ids(nucleo, caminho + [g[x][y]["id"] for x, y in zip(caminho, caminho[1:])], zoom=False)
        janela.abrir_aba(Perfil(nucleo, caminho, g), f"Perfil {a} → {b}", "perfis")

    if len(pontos) == 2:
        return montar(*pontos)
    from .ferramentas_mapa import FerramentaClique
    escolhidos = []

    def clicou(lyr, fid, _p):
        if lyr is None or lyr == nucleo.camada("trecho"):
            return
        escolhidos.append(str(lyr.getFeature(fid)["id"]))
        if len(escolhidos) == 1:
            nucleo.dock.status.setText(f"<b>Perfil</b>: início em {escolhidos[0]}. Agora clique no nó final.")
        else:
            janela.usar("selecionar")
            montar(*escolhidos[:2])

    janela.usar_ferramenta(FerramentaClique(janela.canvas, nucleo.camadas_rede, clicou), "perfis")
    nucleo.dock.status.setText("<b>Perfil</b>: clique no nó inicial e depois no nó final (ou selecione dois nós e "
                               "clique em Perfis).")


# ================================================================ contornos
def contornos(nucleo):
    if not nucleo.cadastro():
        return
    janela = nucleo.janela
    d = Dialogo(janela, "Contornos", "Curvas de mesmo valor interpoladas entre os nós, desenhadas sobre o mapa "
                "(pressão e carga da hora escolhida, ou a cota do terreno).")
    var = QComboBox()
    var.addItems(["Pressão (mca)", "Carga hidráulica (m)", "Cota do terreno (m)", "Pressão mínima do dia (mca)"])
    d.linha("Variável:", var)
    passo = QSpinBox()
    passo.setRange(1, 100)
    passo.setValue(5)
    passo.setSuffix(" (intervalo)")
    d.linha("Intervalo entre curvas:", passo)
    d.botoes("Desenhar")
    if not d.exec():
        return
    i = var.currentIndex()
    if i in (0, 1, 3) and not _precisa_resultado(nucleo):
        return
    pts, vals = [], []
    k = janela.passo()
    for lyr in nucleo.camadas_rede():
        if lyr == nucleo.camada("trecho"):
            continue
        for f in lyr.getFeatures():
            eid = str(f["id"])
            if i == 2:
                v = f["cota"] if lyr.fields().indexOf("cota") >= 0 else None
                v = None if v is None or str(v) == "NULL" else float(v)
            else:
                no = nucleo.res.d["nos"].get(eid) or nucleo.res.d["nos"].get(f"{eid}__J")
                if not no or lyr.name().lower().startswith("reserv"):
                    continue
                v = no["p"][k] if i == 0 else no["h"][k] if i == 1 else min(no["p"])
            if v is None:
                continue
            p = f.geometry().asPoint() if not f.geometry().isMultipart() else f.geometry().vertexAt(0)
            pts.append((p.x(), p.y()))
            vals.append(v)
    if len(pts) < 4:
        return nucleo.aviso("São precisos pelo menos 4 nós com valor para desenhar contornos.")
    import numpy as np
    from scipy.interpolate import griddata
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    P = np.array(pts)
    V = np.array(vals)
    xs = np.linspace(P[:, 0].min(), P[:, 0].max(), 220)
    ys = np.linspace(P[:, 1].min(), P[:, 1].max(), 220)
    X, Y = np.meshgrid(xs, ys)
    Z = griddata(P, V, (X, Y), method="linear")
    passo_v = float(passo.value())
    niveis = np.arange(math.floor(np.nanmin(Z) / passo_v) * passo_v, np.nanmax(Z) + passo_v, passo_v)
    cs = Figure().add_subplot(111).contour(X, Y, Z, levels=niveis)
    nome = f"Contornos · {var.currentText()}"
    from .util import camada_resultado, remover_analise, grupo_analises
    remover_analise(nome)
    crs = nucleo.camada("trecho").crs().authid()
    lyr = QgsVectorLayer(f"LineString?crs={crs}", nome, "memory")
    lyr.dataProvider().addAttributes([QgsField("valor", QVariant.Double)])
    lyr.updateFields()
    feats = []
    for nivel, segs in zip(cs.levels, cs.allsegs):
        for seg in segs:
            if len(seg) < 2:
                continue
            f = QgsFeature(lyr.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in seg]))
            f.setAttributes([float(nivel)])
            feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    from qgis.core import (QgsGradientColorRamp, QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsPalLayerSettings,
                           QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling, Qgis)
    from qgis.PyQt.QtGui import QColor
    r = QgsGraduatedSymbolRenderer("valor")
    r.setSourceSymbol(QgsLineSymbol.createSimple({"width": "0.6"}))
    r.setSourceColorRamp(QgsGradientColorRamp(QColor("#e5484d"), QColor("#1c7ed6")))
    try:
        r.updateClasses(lyr, QgsGraduatedSymbolRenderer.Mode.EqualInterval, 8)
    except AttributeError:
        r.updateClasses(lyr, QgsGraduatedSymbolRenderer.EqualInterval, 8)
    lyr.setRenderer(r)
    s = QgsPalLayerSettings()
    s.fieldName = "format_number(\"valor\", 0)"
    s.isExpression = True
    try:
        s.placement = Qgis.LabelPlacement.Line
    except AttributeError:
        pass
    fmt = QgsTextFormat()
    fmt.setSize(7)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)
    QgsProject.instance().addMapLayer(lyr, False)
    grupo_analises().insertLayer(0, lyr)
    janela.canvas.refresh()
    nucleo.informar(f"{len(feats)} curvas de {var.currentText()} desenhadas (camada em Análises GWATER).")


ACOES = {"graficos": graficos, "grafico_rapido": grafico_rapido, "perfis": perfis, "contornos": contornos}
