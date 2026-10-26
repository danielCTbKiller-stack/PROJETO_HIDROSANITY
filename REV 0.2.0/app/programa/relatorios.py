"""Relatórios: personalizado (seções à escolha, com o mapa), resumo do cenário, inventário do modelo e
inventário de tubulações. Abrem numa aba e salvam em PDF ou HTML, ou vão para a impressora."""
import base64
import os
from collections import defaultdict
from datetime import datetime

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, QUrl
from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from .util import NOMES, PONTOS, Dialogo, num

ESTILO = """<style>
body{font-family:'Segoe UI';color:#14243b;background:white}
h1{color:#0d2650;font-family:'Bahnschrift';border-bottom:3px solid #35d0ff;padding-bottom:4px}
h2{color:#0e4a8c;font-family:'Bahnschrift';margin-top:18px}
table{border-collapse:collapse;margin:6px 0}
th{background:#0d2650;color:white;padding:4px 8px;text-align:left;font-size:9pt}
td{border-bottom:1px solid #c9d6e8;padding:3px 8px;font-size:9pt}
td.n{text-align:right}
.sub{color:#5b6f8a}
</style>"""


def _tabela(cab, linhas):
    h = "<table><tr>" + "".join(f"<th>{c}</th>" for c in cab) + "</tr>"
    for lin in linhas:
        h += "<tr>" + "".join(f"<td class='n'>{num(v, 2 if isinstance(v, float) else 0)}</td>"
                              if isinstance(v, (int, float)) and not isinstance(v, bool) else f"<td>{v}</td>"
                              for v in lin) + "</tr>"
    return h + "</table>"


# ---------------------------------------------------------------- seções
def secao_cabecalho(nucleo):
    gpkg = nucleo.cadastro()
    cen = nucleo.cenario["nome"] if nucleo.cenario else "Rede atual"
    return (f"<h1>GWATER · {os.path.basename(gpkg)}</h1><p class='sub'>Cenário: <b>{cen}</b> · "
            f"{'com' if nucleo.projetados() else 'sem'} elementos PROJETADOS · gerado em "
            f"{datetime.now():%d/%m/%Y %H:%M} · {gpkg}</p>")


def secao_opcoes(nucleo):
    try:
        ops = [(f["chave"], f["valor"]) for f in nucleo.camada("opcoes_simulacao").getFeatures()]
    except LookupError:
        return ""
    return "<h2>Opções de cálculo</h2>" + _tabela(["Opção", "Valor"], ops)


def secao_inventario(nucleo):
    linhas = []
    for c in ("trecho",) + PONTOS:
        try:
            lyr = nucleo.camada(c)
        except LookupError:
            continue
        por = defaultdict(int)
        for f in lyr.getFeatures():
            por[str(f["situacao"])] += 1
        linhas.append([NOMES[c], lyr.featureCount(), por.get("EXISTENTE", 0) + por.get("NULL", 0), por.get("PROJETADO", 0),
                       por.get("DESATIVADO", 0)])
    tr = nucleo.camada("trecho")
    L = sum(float(f["comprimento"] or f.geometry().length()) for f in tr.getFeatures() if str(f["situacao"]) != "DESATIVADO")
    dem = sum(float(f["demanda_base"] or 0) for f in nucleo.camada("no_juncao").getFeatures()
              if str(f["demanda_base"]) != "NULL")
    return ("<h2>Inventário do modelo</h2>" + _tabela(["Elemento", "Total", "Existentes", "Projetados", "Desativados"], linhas)
            + f"<p>Extensão de rede ativa: <b>{num(L / 1000, 3)} km</b> · demanda base total: <b>{num(dem, 3)} L/s</b> "
              f"({num(dem * 86.4, 0)} m³/dia).</p>")


def secao_tubos(nucleo):
    tr = nucleo.camada("trecho")
    por_dn, por_mat, por_dn_mat = defaultdict(float), defaultdict(float), defaultdict(float)
    for f in tr.getFeatures():
        if str(f["situacao"]) == "DESATIVADO":
            continue
        L = float(f["comprimento"] or f.geometry().length())
        dn = f["diametro_nominal"]
        dn = int(dn) if dn not in (None, "") and str(dn) != "NULL" else "sem DN"
        mat = str(f["material"]) if str(f["material"]) not in ("NULL", "") else "sem material"
        por_dn[dn] += L
        por_mat[mat] += L
        por_dn_mat[(dn, mat)] += L
    tot = sum(por_dn.values()) or 1
    h = "<h2>Inventário de tubulações</h2>"
    h += "<p>Por diâmetro:</p>" + _tabela(["DN (mm)", "Comprimento (m)", "%"],
                                          [[k, round(v, 1), round(100 * v / tot, 1)]
                                           for k, v in sorted(por_dn.items(), key=lambda x: (isinstance(x[0], str), x[0]))])
    h += "<p>Por material:</p>" + _tabela(["Material", "Comprimento (m)", "%"],
                                          [[k, round(v, 1), round(100 * v / tot, 1)] for k, v in sorted(por_mat.items())])
    h += "<p>Por diâmetro e material:</p>" + _tabela(
        ["DN (mm)", "Material", "Comprimento (m)"],
        [[dn, mat, round(v, 1)] for (dn, mat), v in sorted(por_dn_mat.items(), key=lambda x: (str(x[0][0]), x[0][1]))])
    return h


def secao_resultados(nucleo):
    res = nucleo.res
    if not res:
        return "<h2>Resultados</h2><p class='sub'>A rede não foi calculada nesta sessão.</p>"
    d = res.d
    pres = [(nid, min(d["nos"][nid]["p"]), max(d["nos"][nid]["p"])) for nid in res.rid_consumo]
    vel = [(t, max(abs(x) for x in d["links"][t]["v"])) for t in res.rid_tr]
    h = "<h2>Resultados do cálculo</h2>"
    if pres:
        pmin = min(pres, key=lambda x: x[1])
        pmax = max(pres, key=lambda x: x[2])
        from .componentes import limites
        lim = limites(nucleo)
        lo, hi = lim["limite_pressao_min"], lim["limite_pressao_max"]
        h += (f"<p>Pressão mínima <b>{num(pmin[1], 1)} mca</b> ({pmin[0]}) · máxima <b>{num(pmax[2], 1)} mca</b> "
              f"({pmax[0]}) · {sum(1 for p in pres if p[1] < lo)} nó(s) abaixo de {num(lo, 1)} mca · "
              f"{sum(1 for p in pres if p[2] > hi)} acima de {num(hi, 1)} mca.</p>")
    if vel:
        vmax = max(vel, key=lambda x: x[1])
        h += f"<p>Velocidade máxima <b>{num(vmax[1], 2)} m/s</b> ({vmax[0]}).</p>"
    h += "<p>Pressões por nó (mínima e máxima do dia):</p>" + _tabela(
        ["Nó", "Pressão mín (mca)", "Pressão máx (mca)"], [[n, round(a, 1), round(b, 1)] for n, a, b in sorted(pres)])
    linhas = []
    try:
        for f in nucleo.camada("bomba").getFeatures():
            l = d["links"].get(str(f["id"]))
            if l:
                linhas.append([str(f["id"]), round(sum(1 for s in l["s"] if s) * 24 / max(len(l["s"]) - 1, 1), 1),
                               round(max(abs(q) for q in l["q"]), 1)])
    except LookupError:
        pass
    if linhas:
        h += "<p>Bombas:</p>" + _tabela(["Bomba", "Horas ligada", "Vazão máx (L/s)"], linhas)
    return h


def secao_mapa(nucleo, recursos):
    img = nucleo.janela.canvas.grab().toImage()
    recursos["mapa.png"] = img
    return "<h2>Mapa</h2><img src='mapa.png' width='900'>"


SECOES = [("cab", "Cabeçalho (cadastro, cenário, data)", secao_cabecalho),
          ("opcoes", "Opções de cálculo", secao_opcoes),
          ("inventario", "Inventário do modelo", secao_inventario),
          ("tubos", "Inventário de tubulações", secao_tubos),
          ("resultados", "Resultados do cálculo", secao_resultados),
          ("mapa", "Imagem do mapa (vista atual)", None)]


# ---------------------------------------------------------------- tela do relatório
class Relatorio(QWidget):
    def __init__(self, nucleo, html, recursos):
        super().__init__()
        self.nucleo, self.html, self.recursos = nucleo, html, recursos
        v = QVBoxLayout(self)
        self.t = QTextBrowser()
        self.t.setStyleSheet("background:white; color:#14243b")
        for nome, img in recursos.items():
            self.t.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(nome), img)
        self.t.setHtml(html)
        v.addWidget(self.t, 1)
        h = QHBoxLayout()
        h.addStretch(1)
        for texto, f in (("Salvar PDF…", self.pdf), ("Salvar HTML…", self.salvar_html), ("Imprimir…", self.imprimir)):
            b = QPushButton(texto)
            b.clicked.connect(f)
            h.addWidget(b)
        v.addLayout(h)

    def _html_embutido(self):
        html = self.html
        for nome, img in self.recursos.items():
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            img.save(buf, "PNG")
            html = html.replace(f"src='{nome}'", f"src='data:image/png;base64,{base64.b64encode(bytes(ba)).decode()}'")
        return html

    def _pasta(self):
        return os.path.dirname(self.nucleo.cadastro() or "")

    def salvar_html(self):
        arq, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", os.path.join(self._pasta(), "relatorio_gwater.html"),
                                             "HTML (*.html)")
        if arq:
            with open(arq, "w", encoding="utf-8") as f:
                f.write("<html><head><meta charset='utf-8'></head><body>" + self._html_embutido() + "</body></html>")
            self.nucleo.informar(f"Relatório salvo: {arq}")

    def pdf(self):
        from qgis.PyQt.QtPrintSupport import QPrinter
        arq, _ = QFileDialog.getSaveFileName(self, "Salvar PDF", os.path.join(self._pasta(), "relatorio_gwater.pdf"),
                                             "PDF (*.pdf)")
        if not arq:
            return
        p = QPrinter(QPrinter.PrinterMode.HighResolution)
        p.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        p.setOutputFileName(arq)
        self.t.document().print(p)
        self.nucleo.informar(f"PDF salvo: {arq}")

    def imprimir(self):
        from qgis.PyQt.QtPrintSupport import QPrintDialog, QPrinter
        p = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(p, self).exec():
            self.t.document().print(p)


def gerar(nucleo, chaves, titulo):
    if not nucleo.cadastro():
        return nucleo.aviso("Abra um cadastro primeiro.")
    recursos = {}
    partes = [ESTILO]
    for chave, _, f in SECOES:
        if chave not in chaves:
            continue
        partes.append(secao_mapa(nucleo, recursos) if chave == "mapa" else f(nucleo))
    nucleo.janela.abrir_aba(Relatorio(nucleo, "".join(partes), recursos), titulo, "relatorio")


def personalizado(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Relatório personalizado", "Marque as seções do relatório. Depois dá para salvar em PDF "
                "ou HTML, ou imprimir.")
    caixas = {}
    for chave, rot, _ in SECOES:
        cb = QCheckBox(rot)
        cb.setChecked(True)
        caixas[chave] = cb
        d.lay.addWidget(cb)
    d.botoes("Gerar")
    if d.exec():
        gerar(nucleo, {k for k, cb in caixas.items() if cb.isChecked()}, "Relatório")


def detalhes_elemento(nucleo, alvo=None):
    """Element Details do WaterGEMS: todos os dados do elemento selecionado, os resultados hora a hora, o gráfico e as
    leituras de campo da calibração."""
    from .tabelas import RESULTADOS
    sel = [(lyr, fids) for lyr, fids in nucleo.janela.selecionados()] if alvo is None else alvo
    itens = []
    for lyr, fids in sel:
        camada = next((c for c in ("trecho",) + PONTOS if _eh(nucleo, c, lyr)), None)
        for f in lyr.getFeatures(fids):
            itens.append((camada, f))
    if not itens:
        return nucleo.informar("Selecione no mapa o(s) elemento(s) do relatório.")
    recursos, partes = {}, [ESTILO, secao_cabecalho(nucleo)]
    res = nucleo.res
    for k, (camada, f) in enumerate(itens[:30]):
        eid = str(f["id"])
        partes.append(f"<h2>{NOMES.get(camada, camada)} {eid}</h2>")
        partes.append(_tabela(["Campo", "Valor"], [[c.name(), "" if f[c.name()] is None or str(f[c.name()]) == "NULL"
                                                     else f[c.name()]] for c in f.fields() if c.name() != "fid"]))
        if not res:
            partes.append("<p class='sub'>Calcule a rede para ver os resultados.</p>")
            continue
        cols = [(nome, fn) for nome, fn in RESULTADOS.get(camada, []) if "dia" not in nome]
        linhas = []
        for i, hh in enumerate(res.horas):
            lin = [f"{int(hh) % 24:02d}:{int(round(hh % 1 * 60)) % 60:02d}"]
            for _, fn in cols:
                try:
                    v = fn(res.d, eid, i)
                except (KeyError, IndexError, TypeError):
                    v = None
                lin.append(round(v, 3) if isinstance(v, float) else ("" if v is None else v))
            linhas.append(lin)
        if cols:
            img = _grafico_elemento(nucleo, camada, eid, cols, res)
            if img is not None:
                recursos[f"el{k}.png"] = img
                partes.append(f"<img src='el{k}.png' width='820'>")
            partes.append("<p>Resultados hora a hora:</p>" + _tabela(["Hora"] + [c for c, _ in cols], linhas))
        from .graficos import medicoes_de
        med = [(gr, h_, v) for gr in ("pressao", "vazao", "nivel", "carga") for h_, v in medicoes_de(nucleo, eid, gr)]
        if med:
            partes.append("<p>Leituras de campo (Calibração):</p>" + _tabela(
                ["Grandeza", "Hora", "Medido"], [[g, f"{h_:g} h", v] for g, h_, v in med]))
    nucleo.janela.abrir_aba(Relatorio(nucleo, "".join(partes), recursos), "Detalhes do elemento", "relatorio")


def _eh(nucleo, c, lyr):
    try:
        return nucleo.camada(c).id() == lyr.id()
    except LookupError:
        return False


def _grafico_elemento(nucleo, camada, eid, cols, res):
    """Imagem (QImage) do gráfico do dia da primeira variável do elemento, com as leituras de campo."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from qgis.PyQt.QtGui import QImage
    from .graficos import GRANDEZA_VAR, medicoes_de
    nome, fn = cols[0]
    try:
        ys = [fn(res.d, eid, i) for i in range(len(res.horas))]
    except (KeyError, IndexError, TypeError):
        return None
    if any(y is None or isinstance(y, str) for y in ys):
        return None
    fig = Figure(figsize=(8.2, 2.6), dpi=100)
    ax = fig.add_subplot(111)
    ax.plot(res.horas, ys, color="#1c7ed6", linewidth=1.8, label="calculado")
    gr = next((g for k, g in GRANDEZA_VAR.items() if nome.startswith(k)), None)
    pts = medicoes_de(nucleo, eid, gr) if gr else []
    if pts:
        ax.scatter([h for h, _ in pts], [v for _, v in pts], color="#f59f00", s=26, zorder=5, label="medido")
    ax.set_title(f"{eid} · {nome}", fontsize=9, loc="left")
    ax.set_xlabel("hora", fontsize=8)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, frameon=False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return QImage.fromData(buf.getvalue(), "PNG")


ACOES = {"relatorio_personalizado": personalizado, "detalhes_elemento": detalhes_elemento,
         "resumo_cenario": lambda n: gerar(n, {"cab", "opcoes", "inventario", "resultados"}, "Resumo do cenário"),
         "inventario": lambda n: gerar(n, {"cab", "inventario"}, "Inventário do modelo"),
         "inventario_tubos": lambda n: gerar(n, {"cab", "tubos"}, "Inventário de tubulações")}
