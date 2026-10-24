"""Camadas de resultado no mapa: pressão nos nós e velocidade nos trechos, por passo de tempo."""
from qgis.core import (
    QgsFeature, QgsField, QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol,
    QgsPalLayerSettings, QgsProject, QgsProperty, QgsRendererRange, QgsRuleBasedRenderer, QgsSymbolLayer,
    QgsTextBufferSettings, QgsTextFormat, QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QVariant

GRUPO = "Resultados GWATER"
FAIXA_P = [(-1e9, 10, "#e5484d", "< 10 mca (abaixo da NBR 12218)"),
           (10, 50, "#2fb36f", "10 a 50 mca (adequada)"),
           (50, 1e9, "#f59f00", "> 50 mca (acima da NBR 12218)")]
FAIXA_V = [(-1, 0.1, "#9aa5b1", "< 0,1 m/s (parada)"),
           (0.1, 0.6, "#74c0fc", "0,1 a 0,6 m/s"),
           (0.6, 1.5, "#1c7ed6", "0,6 a 1,5 m/s"),
           (1.5, 2.5, "#f59f00", "1,5 a 2,5 m/s"),
           (2.5, 1e9, "#e5484d", "> 2,5 m/s (alta)")]
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


def _graduado(campo, faixas, criar):
    return QgsGraduatedSymbolRenderer(campo, [QgsRendererRange(a, b, criar(cor), rot) for a, b, cor, rot in faixas])


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

        ponto = lambda c: QgsMarkerSymbol.createSimple(
            {"name": "circle", "color": c, "size": "2.8", "outline_color": "#1b1b1b", "outline_width": "0.2"})
        regras = QgsRuleBasedRenderer(ponto("#9aa5b1"))
        raiz = regras.rootRule()
        raiz.removeChildAt(0)
        for a, b, cor, rot in FAIXA_P:
            raiz.appendChild(QgsRuleBasedRenderer.Rule(ponto(cor), 0, 0,
                                                       f'"avalia" = 1 AND "p" >= {a} AND "p" < {b}', rot))
        raiz.appendChild(QgsRuleBasedRenderer.Rule(ponto("#9aa5b1"), 0, 0, '"avalia" = 0',
                                                   "fora da avaliação (recalque, entrada de reservatório)"))
        self.nos.setRenderer(regras)
        _rotulo(self.nos, "format_number(\"p\", 1)")

        # ---- trechos
        self.tr = QgsVectorLayer(f"LineString?crs={crs}", "Velocidade nos trechos (m/s)", "memory")
        self.tr.dataProvider().addAttributes([QgsField("id", QVariant.String), QgsField("dn", QVariant.Double),
                                              QgsField("q", QVariant.Double), QgsField("v", QVariant.Double),
                                              QgsField("perda_m_km", QVariant.Double),
                                              QgsField("v_max", QVariant.Double)])
        self.tr.updateFields()
        feats, rids = [], []
        for f in trecho.getFeatures():
            if f["id"] not in dados["links"]:
                continue
            l = dados["links"][f["id"]]
            nf = QgsFeature(self.tr.fields())
            nf.setGeometry(f.geometry())
            nf.setAttributes([f["id"], f["diametro_nominal"], l["q"][0], abs(l["v"][0]), l["hl"][0],
                              max(abs(x) for x in l["v"])])
            feats.append(nf)
            rids.append(f["id"])
        _, feats = self.tr.dataProvider().addFeatures(feats)
        self.fid_tr = [(f.id(), rid) for f, rid in zip(feats, rids)]
        self.rid_tr = rids

        def linha(cor):
            s = QgsLineSymbol.createSimple({"color": cor, "width": "1", "capstyle": "round"})
            s.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeWidth,
                                                    QgsProperty.fromExpression('0.5 + coalesce("dn", 100) / 100'))
            return s
        self.tr.setRenderer(_graduado("v", FAIXA_V, linha))

        for lyr in (self.nos, self.tr):
            prj.addMapLayer(lyr, False)
            grupo.addLayer(lyr)
        self.ids = [self.nos.id(), self.tr.id()]

    def _limpar(self):
        prj = QgsProject.instance()
        g = prj.layerTreeRoot().findGroup(GRUPO)
        if g:
            prj.removeMapLayers([n.layerId() for n in g.findLayers()])
            g.parent().removeChildNode(g)

    def aplicar(self, k):
        """Mostra o passo k (0..n-1) no mapa."""
        ip = self.nos.fields().indexOf("p")
        self.nos.dataProvider().changeAttributeValues(
            {fid: {ip: self.d["nos"][rid]["p"][k]} for fid, rid in self.fid_nos})
        iq, iv, ih = (self.tr.fields().indexOf(c) for c in ("q", "v", "perda_m_km"))
        mud = {}
        for fid, rid in self.fid_tr:
            l = self.d["links"][rid]
            mud[fid] = {iq: l["q"][k], iv: abs(l["v"][k]), ih: l["hl"][k]}
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
        baixo = sum(1 for x in p.values() if x < 10)
        alto = sum(1 for x in p.values() if x > 50)
        cor = lambda ok: "#2fb36f" if ok else "#e5484d"
        html = [f"<b style='font-size:15px'>{_hora(h)}</b> &nbsp; passo {k + 1}/{len(self.horas)}<br>",
                f"Pressão nos pontos de consumo: mín <b>{p[nmin]:.1f}</b> mca ({nmin}) · "
                f"máx <b>{p[nmax]:.1f}</b> mca ({nmax})<br>",
                f"<span style='color:{cor(not baixo)}'>{baixo} de {len(p)} nós abaixo de 10 mca</span> · "
                f"<span style='color:{cor(not alto)}'>{alto} acima de 50 mca</span><br>",
                f"Velocidade máx <b>{v[vmax]:.2f}</b> m/s ({vmax})<br>"]
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
