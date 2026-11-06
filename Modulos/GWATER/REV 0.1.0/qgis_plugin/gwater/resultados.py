"""Camadas de resultado no mapa: pressão nos nós e, nos trechos, velocidade, perda de carga ou vazão.

As faixas de cor de cada variável são do usuário (janela Faixas e cores) e ficam salvas no projeto.
"""
import json
import math
from qgis.core import (
    QgsFeature, QgsField, QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol,
    QgsPalLayerSettings, QgsProject, QgsProperty, QgsRendererRange, QgsRuleBasedRenderer, QgsSymbolLayer,
    QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QVariant

GRUPO = "Resultados GWATER"
CHAVE = "GWATER"
# variável: (nome, unidade, campo na camada de resultado, camada "nos" ou "tr")
VARIAVEIS = {
    "p": ("Pressão", "mca", "p", "nos"),
    "v": ("Velocidade", "m/s", "v", "tr"),
    "hl": ("Perda de carga", "m/km", "perda_m_km", "tr"),
    "q": ("Vazão", "L/s", "q_abs", "tr"),
}
# faixas padrão: [de, até, cor, rótulo]; None = sem limite; rótulo vazio = gerado pelos limites
PADRAO = {
    "p": [[None, 10, "#e5484d", "< 10 mca (abaixo da NBR 12218)"],
          [10, 50, "#2fb36f", "10 a 50 mca (adequada)"],
          [50, None, "#f59f00", "> 50 mca (acima da NBR 12218)"]],
    "v": [[None, 0.1, "#9aa5b1", "< 0,1 m/s (parada)"],
          [0.1, 0.6, "#74c0fc", ""],
          [0.6, 1.5, "#1c7ed6", ""],
          [1.5, 2.5, "#f59f00", ""],
          [2.5, None, "#e5484d", "> 2,5 m/s (alta)"]],
    "hl": [[None, 1, "#9aa5b1", ""],
           [1, 5, "#74c0fc", ""],
           [5, 10, "#1c7ed6", ""],
           [10, 20, "#f59f00", ""],
           [20, None, "#e5484d", "> 20 m/km (alta)"]],
    "q": [[None, 1, "#9aa5b1", ""],
          [1, 5, "#74c0fc", ""],
          [5, 20, "#1c7ed6", ""],
          [20, 50, "#f59f00", ""],
          [50, None, "#e5484d", ""]],
}


def _num_br(x):
    return f"{x:g}".replace(".", ",")


def rotulo(de, ate, unidade, texto=""):
    if texto:
        return texto
    if de is None:
        return f"< {_num_br(ate)} {unidade}"
    if ate is None:
        return f"> {_num_br(de)} {unidade}"
    return f"{_num_br(de)} a {_num_br(ate)} {unidade}"


def _config():
    try:
        return json.loads(QgsProject.instance().readEntry(CHAVE, "faixas", "")[0] or "{}")
    except ValueError:
        return {}


def faixas(var):
    """Faixas da variável: as do projeto, ou as padrão."""
    f = _config().get(var)
    return [list(x) for x in (f if f else PADRAO[var])]


def salvar_faixas(var, lista):
    cfg = _config()
    cfg[var] = sorted(lista, key=lambda x: -math.inf if x[0] is None else x[0])
    QgsProject.instance().writeEntry(CHAVE, "faixas", json.dumps(cfg))


def var_tubos():
    v = QgsProject.instance().readEntry(CHAVE, "cor_tubos", "v")[0]
    return v if v in ("v", "hl", "q") else "v"


def escolher_var_tubos(var):
    QgsProject.instance().writeEntry(CHAVE, "cor_tubos", var)
STATUS = {0: "fechada", 1: "aberta", 2: "ativa"}


def _hora(h):
    return f"{int(h) % 24:02d}:{int(round(h % 1 * 60)) % 60:02d}" if h < 24 else "24:00"


def _rotulo(lyr, expr):
    s = QgsPalLayerSettings()
    s.fieldName, s.isExpression = expr, True
    fmt = QgsTextFormat()
    fmt.setSize(7)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.7)
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def limpar():
    """Remove do mapa o grupo de camadas de resultado (o cadastro não é tocado)."""
    prj = QgsProject.instance()
    g = prj.layerTreeRoot().findGroup(GRUPO)
    if g:
        prj.removeMapLayers([n.layerId() for n in g.findLayers()])
        g.parent().removeChildNode(g)


def _graduado(campo, lista, unidade, criar):
    return QgsGraduatedSymbolRenderer(campo, [
        QgsRendererRange(-1e12 if a is None else a, 1e12 if b is None else b, criar(cor), rotulo(a, b, unidade, rot))
        for a, b, cor, rot in lista])


class Resultados:
    def __init__(self, plugin, dados):
        self.plugin, self.d = plugin, dados
        self.horas = dados["horas"]
        self._limpar()
        prj = QgsProject.instance()
        grupo = prj.layerTreeRoot().insertGroup(0, GRUPO)

        # ---- nós: junções, e o lado de jusante de válvulas e bombas
        trecho = plugin.camada("trecho")
        crs = trecho.crs().authid()
        self.nos = QgsVectorLayer(f"Point?crs={crs}", "Pressão nos nós (mca)", "memory")
        self.nos.dataProvider().addAttributes([QgsField("id", QVariant.String), QgsField("tipo", QVariant.String),
                                               QgsField("p", QVariant.Double), QgsField("p_min", QVariant.Double),
                                               QgsField("p_max", QVariant.Double), QgsField("avalia", QVariant.Int)])
        self.nos.updateFields()
        feats, rids, self.rid_consumo = [], [], []
        for camada, sufixo, tipo in (("no_juncao", "", "nó"), ("valvula", "__J", "válvula (jusante)"),
                                     ("bomba", "__J", "bomba (recalque)")):
            for f in plugin.camada(camada).getFeatures():
                rid = f"{f['id']}{sufixo}"
                if rid not in dados["nos"]:
                    continue  # desativado ou isolado: ficou fora do modelo
                # a faixa da NBR 12218 vale para pontos de consumo, não para recalques e chegadas em reservatório
                consumo = camada == "no_juncao" and (f["tipo"] in ("CONSUMO", "HIDRANTE", "PONTA")
                                                    or (f["demanda_base"] or 0) > 0)
                serie = dados["nos"][rid]["p"]
                nf = QgsFeature(self.nos.fields())
                nf.setGeometry(f.geometry())
                nf.setAttributes([f["id"], tipo, serie[0], min(serie), max(serie), int(consumo)])
                feats.append(nf)
                rids.append(rid)
                if consumo:
                    self.rid_consumo.append(rid)
        _, feats = self.nos.dataProvider().addFeatures(feats)
        self.fid_nos = [(f.id(), rid) for f, rid in zip(feats, rids)]  # feição do mapa -> nó do EPANET
        self.rid_nos = rids
        if not self.rid_consumo:  # rede sem nós de consumo marcados: avalia todos
            self.rid_consumo = [r for r in rids if "__" not in r] or rids

        _rotulo(self.nos, "format_number(\"p\", 1)")

        # ---- trechos
        self.tr = QgsVectorLayer(f"LineString?crs={crs}", "Trechos", "memory")
        self.tr.dataProvider().addAttributes([QgsField("id", QVariant.String), QgsField("dn", QVariant.Double),
                                              QgsField("q", QVariant.Double), QgsField("v", QVariant.Double),
                                              QgsField("perda_m_km", QVariant.Double),
                                              QgsField("v_max", QVariant.Double), QgsField("q_abs", QVariant.Double)])
        self.tr.updateFields()
        feats, rids = [], []
        for f in trecho.getFeatures():
            if f["id"] not in dados["links"]:
                continue
            l = dados["links"][f["id"]]
            nf = QgsFeature(self.tr.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes([f["id"], f["diametro_nominal"], l["q"][0], abs(l["v"][0]), abs(l["hl"][0]),
                              max(abs(x) for x in l["v"]), abs(l["q"][0])])
            feats.append(nf)
            rids.append(f["id"])
        _, feats = self.tr.dataProvider().addFeatures(feats)
        self.fid_tr = [(f.id(), rid) for f, rid in zip(feats, rids)]
        self.rid_tr = rids

        self.estilizar()
        for lyr in (self.nos, self.tr):
            prj.addMapLayer(lyr, False)
            grupo.addLayer(lyr)
        self.ids = [self.nos.id(), self.tr.id()]

    def _limpar(self):
        limpar()

    def estilizar(self):
        """Cores dos nós (pressão) e dos trechos (velocidade, perda de carga ou vazão) pelas faixas do projeto."""
        ponto = lambda c: QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": c, "size": "2.8", "outline_color": "#1b1b1b", "outline_width": "0.2"})
        regras = QgsRuleBasedRenderer(ponto("#9aa5b1"))
        raiz = regras.rootRule()
        raiz.removeChildAt(0)
        for a, b, cor, rot in faixas("p"):
            cond = ['"avalia" = 1'] + ([f'"p" >= {a}'] if a is not None else []) + ([f'"p" < {b}'] if b is not None else [])
            raiz.appendChild(QgsRuleBasedRenderer.Rule(ponto(cor), 0, 0, " AND ".join(cond), rotulo(a, b, "mca", rot)))
        raiz.appendChild(QgsRuleBasedRenderer.Rule(ponto("#9aa5b1"), 0, 0, '"avalia" = 0',
                                                   "fora da avaliação (recalque, entrada de reservatório)"))
        self.nos.setRenderer(regras)
        self.nos.setName("Pressão nos nós (mca)")

        def linha(cor):
            s = QgsLineSymbol.createSimple({"color": cor, "width": "1", "capstyle": "round"})
            s.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth,
                                                    QgsProperty.fromExpression('0.5 + coalesce("dn", 100) / 100'))
            return s
        var = var_tubos()
        nome, un, campo, _ = VARIAVEIS[var]
        self.tr.setRenderer(_graduado(campo, faixas(var), un, linha))
        self.tr.setName(f"{nome} nos trechos ({un})")
        arvore = getattr(self.plugin.iface, "layerTreeView", lambda: None)()
        for lyr in (self.nos, self.tr):
            lyr.triggerRepaint()
            if arvore is not None:  # legenda do painel de camadas com as faixas novas
                arvore.refreshLayerSymbology(lyr.id())

    def aplicar(self, k):
        """Mostra o passo k (0..n-1) no mapa."""
        ip = self.nos.fields().indexOf("p")
        self.nos.dataProvider().changeAttributeValues(
            {fid: {ip: self.d["nos"][rid]["p"][k]} for fid, rid in self.fid_nos})
        iq, iv, ih, ia = (self.tr.fields().indexOf(c) for c in ("q", "v", "perda_m_km", "q_abs"))
        mud = {}
        for fid, rid in self.fid_tr:
            l = self.d["links"][rid]
            mud[fid] = {iq: l["q"][k], iv: abs(l["v"][k]), ih: abs(l["hl"][k]), ia: abs(l["q"][k])}
        self.tr.dataProvider().changeAttributeValues(mud)
        self.nos.triggerRepaint()
        self.tr.triggerRepaint()

    def resumo(self, k):
        """Texto (HTML) do passo k: extremos, reservatórios, bombas e válvulas."""
        d, h = self.d, self.horas[k]
        p = {rid: d["nos"][rid]["p"][k] for rid in self.rid_consumo}
        v = {rid: abs(d["links"][rid]["v"][k]) for rid in self.rid_tr}
        nmin, nmax = min(p, key=p.get), max(p, key=p.get)
        vmax = max(v, key=v.get)
        hl = {rid: abs(d["links"][rid]["hl"][k]) for rid in self.rid_tr}
        hmax = max(hl, key=hl.get)
        baixo = sum(1 for x in p.values() if x < 10)
        alto = sum(1 for x in p.values() if x > 50)
        cor = lambda ok: "#2fb36f" if ok else "#e5484d"
        html = [f"<b style='font-size:15px'>{_hora(h)}</b> &nbsp; passo {k + 1}/{len(self.horas)}<br>",
                f"Pressão nos pontos de consumo: mín <b>{p[nmin]:.1f}</b> mca ({nmin}) · "
                f"máx <b>{p[nmax]:.1f}</b> mca ({nmax})<br>",
                f"<span style='color:{cor(not baixo)}'>{baixo} de {len(p)} nós abaixo de 10 mca</span> · "
                f"<span style='color:{cor(not alto)}'>{alto} acima de 50 mca</span><br>",
                f"Velocidade máx <b>{v[vmax]:.2f}</b> m/s ({vmax}) · "
                f"perda de carga máx <b>{hl[hmax]:.1f}</b> m/km ({hmax})<br>"]
        for f in self.plugin.camada("reservatorio").getFeatures():
            if f["id"] in d["nos"] and f["nivel_max"]:
                nivel = d["nos"][f["id"]]["p"][k]
                html.append(f"Reservatório {f['id']}: nível {nivel:.2f} m ({nivel / f['nivel_max'] * 100:.0f}%)<br>")
        for f in self.plugin.camada("bomba").getFeatures():
            if f["id"] in d["links"]:
                l = d["links"][f["id"]]
                html.append(f"Bomba {f['id']}: {'LIGADA' if l['s'][k] else 'DESLIGADA'} · {l['q'][k]:.1f} L/s<br>")
        for f in self.plugin.camada("valvula").getFeatures():
            if f["id"] in d["links"]:
                l = d["links"][f["id"]]
                pj = d["nos"].get(f"{f['id']}__J", {}).get("p", [0] * (k + 1))[k]
                html.append(f"Válvula {f['id']} ({f['tipo']}): {STATUS.get(l['s'][k], l['s'][k])} · "
                            f"{l['q'][k]:.1f} L/s · jusante {pj:.1f} mca<br>")
        return "".join(html)

    def pior_momento(self):
        """Passo com a menor pressão da rede (útil para abrir a análise já no ponto crítico)."""
        mins = [min(self.d["nos"][rid]["p"][k] for rid in self.rid_consumo) for k in range(len(self.horas))]
        return mins.index(min(mins))
