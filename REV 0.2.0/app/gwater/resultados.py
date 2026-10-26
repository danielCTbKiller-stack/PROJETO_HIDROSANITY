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
    v = QgsProject.instance().readEntry(CHAVE, "cor_tubos", "hl")[0]
    return v if v in ("v", "hl", "q") else "hl"


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
        if getattr(self, "_k", None) is not None:  # trocou a variável dos tubos: preenche a nova na hora atual
            self.aplicar(self._k)
        arvore = getattr(self.plugin.iface, "layerTreeView", lambda: None)()
        for lyr in (self.nos, self.tr):
            lyr.triggerRepaint()
            if arvore is not None:  # legenda do painel de camadas com as faixas novas
                arvore.refreshLayerSymbology(lyr.id())

    # ------------------------------------------------ fluxo da água (setas animadas no sentido da vazão)
    INTERVALO_SETA = 7.0  # mm de tela entre as setas

    def fluxo(self, ligar, fps=15):
        """Liga ou desliga a animação do fluxo: setas correndo nas tubulações, no sentido da vazão da hora mostrada,
        mais rápidas onde a velocidade é maior. É um símbolo animado do próprio QGIS: só esta camada é redesenhada
        a cada quadro (o resto do mapa fica no cache), e as setas são espaçadas na tela, então o custo não cresce
        com o tamanho da rede."""
        from qgis.core import (Qgis, QgsMarkerLineSymbolLayer, QgsSymbolAnimationSettings, QgsVectorSimplifyMethod)
        prj = QgsProject.instance()
        fl = getattr(self, "fl", None)
        try:
            vivo = fl is not None and prj.mapLayer(fl.id()) is not None
        except RuntimeError:
            vivo = False
        if not ligar:
            if vivo:
                prj.removeMapLayer(fl.id())
            self.fl = None
            return None
        if not vivo:
            crs = self.tr.crs().authid()
            fl = QgsVectorLayer(f"LineString?crs={crs}", "Fluxo da água", "memory")
            fl.dataProvider().addAttributes([QgsField("id", QVariant.String), QgsField("q", QVariant.Double),
                                             QgsField("v", QVariant.Double)])
            fl.updateFields()
            feats = []
            for f in self.tr.getFeatures():
                nf = QgsFeature(fl.fields())
                nf.setGeometry(f.geometry())
                nf.setAttributes([f["id"], 0.0, 0.0])
                feats.append(nf)
            _, feats = fl.dataProvider().addFeatures(feats)
            self.fid_fl = [(nf.id(), rid) for nf, (_, rid) in zip(feats, self.fid_tr)]
            self.__dict__.pop("_serie_fl", None)
            simp = QgsVectorSimplifyMethod()
            simp.setSimplifyHints(QgsVectorSimplifyMethod.SimplifyHint.GeometrySimplification)
            simp.setThreshold(1.0)
            fl.setSimplifyMethod(simp)
            self.fl = fl
            prj.addMapLayer(fl, False)
            grupo = prj.layerTreeRoot().findGroup(GRUPO)
            (grupo or prj.layerTreeRoot()).insertLayer(0, fl)  # por cima das cores dos tubos
        seta = QgsMarkerSymbol.createSimple({"name": "filled_arrowhead", "size": "2.6", "color": "#e8f7ff",
                                             "outline_color": "#06315c", "outline_width": "0.25"})
        seta.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.Property.Angle,
                                                   QgsProperty.fromExpression('CASE WHEN "q" < 0 THEN 180 ELSE 0 END'))
        linha = QgsMarkerLineSymbolLayer(True, self.INTERVALO_SETA)
        linha.setSubSymbol(seta)
        try:
            linha.setIntervalUnit(Qgis.RenderUnit.Millimeters)
            linha.setOffsetAlongLineUnit(Qgis.RenderUnit.Millimeters)
        except AttributeError:
            pass
        i = self.INTERVALO_SETA
        # sempre andando (mesmo com água devagar) e mais rápido onde a velocidade é maior; independe dos quadros/s
        # (least/coalesce não funcionam nesta expressão de símbolo animado: CASE simples)
        anda = (f'(@symbol_frame * (0.35 + 0.6 * (CASE WHEN "v" > 3 THEN 3 WHEN "v" > 0 THEN "v" ELSE 0 END)) '
                f'/ {max(fps, 1) / 15:g}) % {i:g}')
        linha.setDataDefinedProperty(QgsSymbolLayer.Property.OffsetAlongLine, QgsProperty.fromExpression(
            f'CASE WHEN "q" >= 0 THEN {anda} ELSE {i:g} - {anda} END'))
        simbolo = QgsLineSymbol()
        simbolo.changeSymbolLayer(0, linha)
        anim = QgsSymbolAnimationSettings()
        anim.setIsAnimated(True)
        anim.setFrameRate(fps)
        simbolo.setAnimationSettings(anim)
        regras = QgsRuleBasedRenderer(simbolo)
        raiz = regras.rootRule()
        # sem setas no tubo parado (o zoom afastado demais é cortado pela escala da camada, logo abaixo)
        raiz.children()[0].setFilterExpression('abs("q") > 0.01 AND "v" > 0.005')
        self.fl.setRenderer(regras)
        # zoom tão afastado que nenhum tubo comporta uma seta: a camada nem é desenhada (nada de custo à toa)
        comps = sorted(f.geometry().length() for f in self.fl.getFeatures())
        if comps:
            tipico = comps[int(len(comps) * 0.75)]
            self.fl.setScaleBasedVisibility(True)
            self.fl.setMinimumScale(max(500.0, tipico * 1000 / i))
            self.fl.setMaximumScale(0.0)
        self.fl.setAutoRefreshInterval(int(1000 / max(fps, 1)))
        try:
            self.fl.setAutoRefreshMode(Qgis.AutoRefreshMode.RedrawOnly)
        except AttributeError:
            self.fl.setAutoRefreshEnabled(True)
        if getattr(self, "_k", None) is not None:
            self.aplicar(self._k)
        return self.fl

    def rotulos_animacao(self, ligar):
        """Durante a animação hora a hora: os rótulos de pressão saem (voltam como estavam ao pausar) e o fluxo deixa
        de pedir redesenho sozinho (as setas andam junto com cada hora; dois pedidos ao mesmo tempo cortariam o
        quadro)."""
        fl = getattr(self, "fl", None)
        if fl is not None:
            try:
                from qgis.core import Qgis
                fl.setAutoRefreshMode(Qgis.AutoRefreshMode.RedrawOnly if ligar else Qgis.AutoRefreshMode.Disabled)
            except (AttributeError, RuntimeError):
                pass
        if not ligar:
            self._rotulos = self.nos.labelsEnabled()
            self.nos.setLabelsEnabled(False)
        elif getattr(self, "_rotulos", None) is not None:
            self.nos.setLabelsEnabled(self._rotulos)
            self._rotulos = None
        self.nos.triggerRepaint()

    def _series_tubos(self, var):
        """[(feição, série já em módulo)] da variável que colore os tubos (montada uma vez por variável)."""
        cache = self.__dict__.setdefault("_cache_tr", {})
        if var not in cache:
            chave = {"v": "v", "hl": "hl", "q": "q"}[var]
            cache[var] = [(fid, [abs(x) for x in self.d["links"][rid][chave]]) for fid, rid in self.fid_tr]
        return cache[var]

    def aplicar(self, k):
        """Mostra o passo k (0..n-1) no mapa. Só os campos que estão no mapa mudam (pressão nos nós e a variável
        dos tubos): é o que deixa a animação hora a hora leve em redes grandes."""
        self._k = k
        if "_serie_p" not in self.__dict__:
            self._serie_p = [(fid, self.d["nos"][rid]["p"]) for fid, rid in self.fid_nos]
        ip = self.nos.fields().indexOf("p")
        self.nos.dataProvider().changeAttributeValues({fid: {ip: s[k]} for fid, s in self._serie_p})
        var = var_tubos()
        i = self.tr.fields().indexOf(VARIAVEIS[var][2])
        mud = {fid: {i: s[k]} for fid, s in self._series_tubos(var)}
        rot = {"q": "q", "v": "v", "perda_m_km": "hl"}.get(getattr(self, "campo_rotulo_tr", None))
        if rot and rot != var:  # o rótulo dos tubos mostra outra variável: ela também anda com a hora
            j = self.tr.fields().indexOf(self.campo_rotulo_tr)
            for fid, s in self._series_tubos(rot):
                mud.setdefault(fid, {})[j] = s[k]
        self.tr.dataProvider().changeAttributeValues(mud)
        fl = getattr(self, "fl", None)
        if fl is not None:  # o fluxo segue a hora: sentido e velocidade daquele momento
            try:
                if "_serie_fl" not in self.__dict__:
                    self._serie_fl = [(fid, self.d["links"][rid]["q"], [abs(x) for x in self.d["links"][rid]["v"]])
                                      for fid, rid in self.fid_fl]
                iq, iv = fl.fields().indexOf("q"), fl.fields().indexOf("v")
                fl.dataProvider().changeAttributeValues({fid: {iq: q[k], iv: v[k]} for fid, q, v in self._serie_fl})
            except RuntimeError:  # a camada foi tirada do mapa
                self.fl = None
        # adiado: espera o quadro em andamento terminar em vez de cortá-lo (sem mapa pela metade)
        for lyr in (self.nos, self.tr, getattr(self, "fl", None)):
            if lyr is not None:
                lyr.triggerRepaint(True)

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
