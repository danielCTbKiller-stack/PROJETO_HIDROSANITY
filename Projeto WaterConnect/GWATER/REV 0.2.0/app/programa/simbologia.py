"""Tipos de elemento do GWATER e o painel Simbologia dos elementos (como o Element Symbology do WaterGEMS).

Cada tipo (tubulação, nó, hidrante, PRV, TCV, registro...) é uma regra da simbologia da camada do cadastro,
com ícone próprio no mapa e na lista. A caixinha de cada tipo liga e desliga só aquele tipo no mapa.
O mesmo catálogo serve ao ModelBuilder (o que cada arquivo vira) e ao desenho.
"""
import os

from qgis.core import (
    QgsFeatureRequest, QgsLineSymbol, QgsMarkerSymbol, QgsProperty, QgsRuleBasedRenderer, QgsSimpleLineSymbolLayer,
    QgsSvgMarkerSymbolLayer, QgsSymbolLayer,
)
from qgis.PyQt.QtCore import QSize, Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QDockWidget, QLabel, QLineEdit, QMenu, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .tema import ICONES, icone

OUTROS_NO = ("('CONSUMO', 'HIDRANTE', 'PONTA', 'TOMADA', 'VENTOSA', 'VALVULA_ALIVIO', 'DISCO_RUPTURA', "
             "'DESCARGA_ATMOSFERA', 'TANQUE_HIDROPNEUMATICO', 'CHAMINE_EQUILIBRIO', 'CARGA_PERIODICA')")
VALVULAS = ("PRV", "PSV", "PBV", "FCV", "TCV", "GPV", "REGISTRO", "VRE", "VSE", "RETENCAO", "TURBINA", "ORIFICIO",
            "AREA_LINEAR")
LATERAL = "coalesce(\"tipo\", '') <> 'LATERAL'"
# chave, nome, camada, filtro (expressão; None = todos), valores do elemento novo, ícone, geometria, tamanho (mm)
TIPOS = [
    ("tubulacao", "Tubulação", "trecho", f"coalesce(\"status\", 'ABERTO') NOT IN ('FECHADO', 'CV') AND {LATERAL}", {},
     "elem_tubulacao", "linha", 0),
    ("tubulacao_fechada", "Tubulação fechada", "trecho", f"\"status\" = 'FECHADO' AND {LATERAL}", {"status": "FECHADO"},
     "elem_tubulacao_fechada", "linha", 0),
    ("tubulacao_cv", "Tubulação com retenção (CV)", "trecho", f"\"status\" = 'CV' AND {LATERAL}", {"status": "CV"},
     "elem_tubulacao_cv", "linha", 0),
    ("lateral", "Lateral (ramal)", "trecho", "\"tipo\" = 'LATERAL'", {"tipo": "LATERAL"}, "elem_lateral", "linha", 0),
    ("no", "Nó / junção", "no_juncao", f"\"tipo\" IS NULL OR \"tipo\" NOT IN {OUTROS_NO}", {"tipo": "JUNCAO"},
     "elem_no", "ponto", 2.2),
    ("ponto_consumo", "Nó de consumo", "no_juncao", "\"tipo\" = 'CONSUMO'", {"tipo": "CONSUMO"},
     "elem_consumo", "ponto", 3.2),
    ("hidrante", "Hidrante", "no_juncao", "\"tipo\" = 'HIDRANTE'", {"tipo": "HIDRANTE"}, "elem_hidrante", "ponto", 4.2),
    ("ponta", "Ponta de rede", "no_juncao", "\"tipo\" = 'PONTA'", {"tipo": "PONTA"}, "elem_ponta", "ponto", 2.6),
    ("tomada", "Tomada (tap)", "no_juncao", "\"tipo\" = 'TOMADA'", {"tipo": "TOMADA"}, "elem_tomada", "ponto", 4.4),
    ("ventosa", "Ventosa", "no_juncao", "\"tipo\" = 'VENTOSA'", {"tipo": "VENTOSA"}, "elem_ventosa", "ponto", 4.4),
    ("valvula_alivio", "Válvula de alívio", "no_juncao", "\"tipo\" = 'VALVULA_ALIVIO'", {"tipo": "VALVULA_ALIVIO"}, "elem_valvula_alivio", "ponto", 4.4),
    ("disco_ruptura", "Disco de ruptura", "no_juncao", "\"tipo\" = 'DISCO_RUPTURA'", {"tipo": "DISCO_RUPTURA"}, "elem_disco_ruptura", "ponto", 4.4),
    ("descarga_atmosfera", "Descarga para a atmosfera", "no_juncao", "\"tipo\" = 'DESCARGA_ATMOSFERA'", {"tipo": "DESCARGA_ATMOSFERA"}, "elem_descarga_atmosfera", "ponto", 4.4),
    ("tanque_hidropneumatico", "Tanque hidropneumático", "no_juncao", "\"tipo\" = 'TANQUE_HIDROPNEUMATICO'", {"tipo": "TANQUE_HIDROPNEUMATICO"}, "elem_tanque_hidropneumatico", "ponto", 4.4),
    ("chamine_equilibrio", "Chaminé de equilíbrio", "no_juncao", "\"tipo\" = 'CHAMINE_EQUILIBRIO'", {"tipo": "CHAMINE_EQUILIBRIO"}, "elem_chamine_equilibrio", "ponto", 4.4),
    ("carga_periodica", "Carga-vazão periódica", "no_juncao", "\"tipo\" = 'CARGA_PERIODICA'", {"tipo": "CARGA_PERIODICA"}, "elem_carga_periodica", "ponto", 4.4),
    ("reservatorio", "Reservatório", "reservatorio", None, {}, "elem_reservatorio", "ponto", 6),
    ("captacao", "Captação", "captacao", None, {}, "elem_captacao", "ponto", 6),
    ("bomba", "Bomba", "bomba", "coalesce(\"tipo\", 'BOMBA') <> 'BATERIA_VFD'", {"tipo": "BOMBA"}, "elem_bomba", "ponto", 5),
    ("scada", "Elemento SCADA", "scada", None, {}, "elem_scada", "ponto", 5),
    ("bateria_vfd", "Bateria de bombas VFD", "bomba", "\"tipo\" = 'BATERIA_VFD'", {"tipo": "BATERIA_VFD"}, "elem_bateria_vfd",
     "ponto", 6),
    ("valvula_prv", "PRV · redutora de pressão", "valvula", "\"tipo\" = 'PRV'", {"tipo": "PRV"}, "elem_prv", "ponto", 5),
    ("valvula_psv", "PSV · sustentadora de pressão", "valvula", "\"tipo\" = 'PSV'", {"tipo": "PSV"}, "elem_psv", "ponto", 5),
    ("valvula_pbv", "PBV · quebra-pressão", "valvula", "\"tipo\" = 'PBV'", {"tipo": "PBV"}, "elem_pbv", "ponto", 5),
    ("valvula_fcv", "FCV · controladora de vazão", "valvula", "\"tipo\" = 'FCV'", {"tipo": "FCV"}, "elem_fcv", "ponto", 5),
    ("valvula_vre", "VRE · válvula do reservatório", "valvula", "\"tipo\" = 'VRE'", {"tipo": "VRE", "status": "ABERTA"},
     "elem_vre", "ponto", 5),
    ("valvula_vse", "VSE · válvula de setor", "valvula", "\"tipo\" = 'VSE'", {"tipo": "VSE", "status": "ABERTA"},
     "elem_vse", "ponto", 5),
    ("retencao", "Retenção (check valve)", "valvula", "\"tipo\" = 'RETENCAO'", {"tipo": "RETENCAO", "status": "ABERTA"}, "elem_retencao", "ponto", 5),
    ("turbina", "Turbina", "valvula", "\"tipo\" = 'TURBINA'", {"tipo": "TURBINA", "status": "ABERTA"}, "elem_turbina", "ponto", 5),
    ("orificio", "Orifício entre tubos", "valvula", "\"tipo\" = 'ORIFICIO'", {"tipo": "ORIFICIO", "status": "ABERTA"}, "elem_orificio", "ponto", 5),
    ("area_linear", "Válvula de área linear", "valvula", "\"tipo\" = 'AREA_LINEAR'", {"tipo": "AREA_LINEAR", "status": "ABERTA"}, "elem_area_linear", "ponto", 5),
    ("valvula_tcv", "TCV · estrangulamento", "valvula", "\"tipo\" = 'TCV'", {"tipo": "TCV", "status": "ABERTA"}, "elem_tcv", "ponto", 5),
    ("valvula_gpv", "GPV · perda genérica", "valvula", "\"tipo\" = 'GPV'", {"tipo": "GPV"}, "elem_gpv", "ponto", 5),
    ("registro", "Registro (manobra)", "valvula", "\"tipo\" = 'REGISTRO'", {"tipo": "REGISTRO", "status": "ABERTA"},
     "elem_registro", "ponto", 4.6),
    ("valvula_outra", "Válvula (tipo não informado)", "valvula",
     f"\"tipo\" IS NULL OR \"tipo\" NOT IN {VALVULAS}", {}, "elem_valvula", "ponto", 5),
]
POR_CHAVE = {t[0]: t for t in TIPOS}
# grupos da lista (como no WaterGEMS, a tubulação abre nos seus estados)
FILHOS = {"tubulacao": ["tubulacao_fechada", "tubulacao_cv"]}


def _svg(nome):
    return os.path.join(ICONES, nome + ".svg").replace("\\", "/")


def config():
    """Escolhas do usuário por tipo, salvas no projeto: {chave: {"tam", "rotulo": {...}, "cores": {...}}}."""
    import json
    from qgis.core import QgsProject
    try:
        return json.loads(QgsProject.instance().readEntry("GWATER", "simbologia", "")[0] or "{}")
    except ValueError:
        return {}


def gravar_config(cfg):
    import json
    from qgis.core import QgsProject
    QgsProject.instance().writeEntry("GWATER", "simbologia", json.dumps(cfg, ensure_ascii=False))


def _simbolo(t, tam=None, cor=None):
    """Símbolo do tipo; com `cor` (color coding) o ponto vira um círculo daquela cor e a linha muda de cor."""
    _, _, camada, _, _, ic, geo, tam0 = t
    if geo == "linha":
        base = {"elem_tubulacao": "#1c7ed6", "elem_tubulacao_fechada": "#868e96", "elem_tubulacao_cv": "#ae3ec9",
                "elem_lateral": "#2fae74"}[ic]
        s = QgsLineSymbol.createSimple({"color": cor or base, "width": "0.7", "capstyle": "round", "joinstyle": "round"})
        s.symbolLayer(0).setDataDefinedProperty(
            QgsSymbolLayer.PropertyStrokeWidth,
            QgsProperty.fromExpression(f'({tam or 1.0}) * (0.45 + coalesce("diametro_nominal", 100) / 250)'))
        if ic in ("elem_tubulacao_fechada", "elem_lateral"):
            s.symbolLayer(0).setPenStyle(Qt.PenStyle.DashLine)
        return s
    tam = tam or tam0
    if cor:
        return QgsMarkerSymbol.createSimple({"name": "circle", "color": cor, "size": str(tam),
                                             "outline_color": "#0b1f3a", "outline_width": "0.3"})
    s = QgsMarkerSymbol()
    s.deleteSymbolLayer(0)
    s.appendSymbolLayer(QgsSvgMarkerSymbolLayer(_svg(ic), tam))
    return s


def _filtro_classe(campo, c, modo):
    q = '"' + campo + '"'
    if modo == "categorias":
        v = c[0]
        if v in (None, ""):
            return f"{q} IS NULL"
        if isinstance(v, (int, float)):
            return f"{q} = {v}"
        return f"{q} = '" + str(v).replace("'", "''") + "'"
    de, ate = c[0], c[1]
    partes = ([f"{q} >= {de}"] if de is not None else []) + ([f"{q} < {ate}"] if ate is not None else [])
    return " AND ".join(partes) or "TRUE"


def aplicar_simbologia(nucleo):
    """Uma regra por tipo em cada camada (tamanho, color coding e rótulos escolhidos pelo usuário)."""
    from qgis.core import QgsPalLayerSettings, QgsRuleBasedLabeling, QgsTextBufferSettings, QgsTextFormat
    from qgis.PyQt.QtGui import QColor
    cfg = config()
    for camada in ("trecho", "no_juncao", "reservatorio", "captacao", "bomba", "valvula", "scada"):
        try:
            lyr = nucleo.camada(camada)
        except LookupError:
            continue
        r = QgsRuleBasedRenderer(QgsRuleBasedRenderer.Rule(None))
        raiz = r.rootRule()
        rot_raiz = QgsRuleBasedLabeling.Rule(None)
        mexeu_rotulos = False
        for t in TIPOS:
            if t[2] != camada:
                continue
            c = cfg.get(t[0], {})
            cores = c.get("cores") or {}
            if cores.get("campo") and cores.get("classes"):
                regra = QgsRuleBasedRenderer.Rule(None, 0, 0, t[3] or "", t[1])
                for cl in cores["classes"]:
                    regra.appendChild(QgsRuleBasedRenderer.Rule(
                        _simbolo(t, c.get("tam"), cl[-2]), 0, 0,
                        _filtro_classe(cores["campo"], cl, cores.get("modo", "faixas")), cl[-1]))
            else:
                regra = QgsRuleBasedRenderer.Rule(_simbolo(t, c.get("tam")), 0, 0, t[3] or "", t[1])
            regra.setRuleKey(t[0])  # chave fixa: o painel acha a regra pelo tipo
            raiz.appendChild(regra)
            ro = c.get("rotulo") or {}
            if "on" in ro:
                mexeu_rotulos = True
            if ro.get("on") and ro.get("campo"):
                ps = QgsPalLayerSettings()
                ps.fieldName = ("'" + ro.get("prefixo", "").replace("'", "''") + "' || coalesce(to_string(\"" +
                                ro["campo"] + "\"), '') || '" + ro.get("sufixo", "").replace("'", "''") + "'")
                ps.isExpression = True
                fmt = QgsTextFormat()
                fmt.setSize(float(ro.get("tam", 8)))
                fmt.setColor(QColor(ro.get("cor", "#0b1f3a")))
                buf = QgsTextBufferSettings()
                buf.setEnabled(True)
                buf.setSize(0.8)
                fmt.setBuffer(buf)
                ps.setFormat(fmt)
                rot_raiz.appendChild(QgsRuleBasedLabeling.Rule(ps, 0, 0, t[3] or "", t[1]))
        lyr.setRenderer(r)
        if mexeu_rotulos:  # o usuário mexeu nos rótulos de algum tipo desta camada: os rótulos são os dele
            tem = len(rot_raiz.children()) > 0
            lyr.setLabeling(QgsRuleBasedLabeling(rot_raiz))
            lyr.setLabelsEnabled(tem)
        lyr.triggerRepaint()
    _dominio_registro(nucleo)
    _dominio_status(nucleo)


def _dominio_registro(nucleo):
    """Os tipos REGISTRO, VRE e VSE na lista do formulário da válvula (cadastros criados antes deles)."""
    from qgis.core import QgsEditorWidgetSetup
    try:
        lyr = nucleo.camada("valvula")
    except LookupError:
        return
    i = lyr.fields().indexOf("tipo")
    if i < 0:
        return
    cfg = lyr.editorWidgetSetup(i)
    if cfg.type() != "ValueMap":
        return
    mapa = cfg.config().get("map", [])
    if isinstance(mapa, dict):
        mapa = [{k: v} for k, v in mapa.items()]
    novos = [("REGISTRO - registro de manobra", "REGISTRO"),
             ("VRE - válvula do reservatório (aberta/fechada, aparece no sinótico)", "VRE"),
             ("VSE - válvula de setor (aberta/fechada, não aparece no sinótico)", "VSE")]
    faltam = [{k: v} for k, v in novos if not any(v in d.values() for d in mapa)]
    if not faltam:
        return
    mapa = list(mapa) + faltam
    lyr.setEditorWidgetSetup(i, QgsEditorWidgetSetup("ValueMap", {"map": mapa}))


def _dominio_status(nucleo):
    """Lista do status da válvula com INATIVA (PRV/PSV/FCV/PBV 100% aberta, sem regular), também nos cadastros
    criados antes dela."""
    from qgis.core import QgsEditorWidgetSetup
    try:
        lyr = nucleo.camada("valvula")
    except LookupError:
        return
    i = lyr.fields().indexOf("status")
    if i < 0:
        return
    mapa = [{"ATIVA - regulando (PRV, PSV, FCV, PBV)": "ATIVA"},
            {"INATIVA - 100% aberta, sem regular": "INATIVA"},
            {"ABERTA": "ABERTA"}, {"FECHADA": "FECHADA"}]
    cfg = lyr.editorWidgetSetup(i)
    if cfg.type() == "ValueMap" and cfg.config().get("map") == mapa:
        return
    lyr.setEditorWidgetSetup(i, QgsEditorWidgetSetup("ValueMap", {"map": mapa}))


def contar(nucleo):
    """{chave do tipo: quantidade} (uma passada por camada)."""
    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
    out = {}
    for camada in ("trecho", "no_juncao", "reservatorio", "captacao", "bomba", "valvula", "scada"):
        try:
            lyr = nucleo.camada(camada)
        except LookupError:
            continue
        tipos = [t for t in TIPOS if t[2] == camada]
        exprs = [(t[0], QgsExpression(t[3]) if t[3] else None) for t in tipos]
        ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        for k, _ in exprs:
            out[k] = 0
        campos = [c for c in ("tipo", "status") if lyr.fields().indexOf(c) >= 0]
        req = QgsFeatureRequest().setSubsetOfAttributes(campos, lyr.fields())
        try:
            req.setFlags(QgsFeatureRequest.Flag.NoGeometry)
        except AttributeError:
            from qgis.core import Qgis
            req.setFlags(Qgis.FeatureRequestFlag.NoGeometry)
        for f in lyr.getFeatures(req):
            ctx.setFeature(f)
            for k, e in exprs:
                if e is None or e.evaluate(ctx):
                    out[k] += 1
                    break
    return out


class PainelSimbologia(QDockWidget):
    """Lista dos tipos de elemento com caixinha (liga/desliga no mapa) e, embaixo, as outras camadas."""

    def __init__(self, janela, arvore):
        super().__init__("Simbologia dos elementos", janela)
        self.setObjectName("GwaterSimbologia")
        self.janela = janela
        corpo = QWidget()
        v = QVBoxLayout(corpo)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Procurar…")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self._filtrar)
        v.addWidget(self.busca)
        sp = QSplitter(Qt.Orientation.Vertical)
        self.lista = QTreeWidget()
        self.lista.setHeaderHidden(True)
        self.lista.setIconSize(QSize(18, 18))
        self.lista.setIndentation(14)
        self.lista.setRootIsDecorated(True)
        self.itens = {}
        for t in TIPOS:
            if any(t[0] in fs for fs in FILHOS.values()):
                continue
            it = self._item(t)
            self.lista.addTopLevelItem(it)
            for k in FILHOS.get(t[0], []):
                it.addChild(self._item(POR_CHAVE[k]))
        self.lista.itemChanged.connect(self._marcou)
        self.lista.itemDoubleClicked.connect(self._duplo)
        self.lista.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lista.customContextMenuRequested.connect(self._menu)
        sp.addWidget(self.lista)
        baixo = QWidget()
        vb = QVBoxLayout(baixo)
        vb.setContentsMargins(0, 0, 0, 0)
        rot = QLabel("Camadas do mapa (resultados, análises, mapa de fundo)")
        rot.setStyleSheet(f"color:{COR['muted']}; padding:4px 2px 2px 2px")
        vb.addWidget(rot)
        vb.addWidget(arvore, 1)
        sp.addWidget(baixo)
        sp.setSizes([480, 220])
        v.addWidget(sp, 1)
        self.setWidget(corpo)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(800)
        self._timer.timeout.connect(self.recontar)
        self._ligadas = set()

    def _item(self, t):
        it = QTreeWidgetItem([t[1]])
        it.setIcon(0, icone(t[5]))
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(0, Qt.CheckState.Checked)
        it.setData(0, Qt.ItemDataRole.UserRole, t[0])
        it.setToolTip(0, f"{t[1]} · camada {t[2]}" + (f" · {t[3]}" if t[3] else ""))
        self.itens[t[0]] = it
        return it

    # ------------------------------------------------ projeto
    def projeto_aberto(self):
        nucleo = self.janela.nucleo
        if not nucleo.cadastro():
            return
        aplicar_simbologia(nucleo)
        self.lista.blockSignals(True)
        for it in self.itens.values():
            it.setCheckState(0, Qt.CheckState.Checked)
        self.lista.blockSignals(False)
        self.lista.expandAll()
        for lyr in nucleo.camadas_rede():
            if lyr.id() in self._ligadas:
                continue
            self._ligadas.add(lyr.id())
            for sinal in (lyr.featureAdded, lyr.featuresDeleted, lyr.attributeValueChanged, lyr.afterRollBack):
                sinal.connect(lambda *_: self._timer.start())
        self.recontar()

    def projeto_fechado(self):
        self._ligadas.clear()
        for k, it in self.itens.items():
            it.setText(0, POR_CHAVE[k][1])

    def recontar(self):
        try:
            n = contar(self.janela.nucleo)
        except RuntimeError:
            return
        self.lista.blockSignals(True)
        for k, it in self.itens.items():
            it.setText(0, f"{POR_CHAVE[k][1]}  ({n.get(k, 0)})")
        self.lista.blockSignals(False)

    # ------------------------------------------------ caixinhas
    def _marcou(self, it, _col):
        chave = it.data(0, Qt.ItemDataRole.UserRole)
        ligado = it.checkState(0) == Qt.CheckState.Checked
        self.lista.blockSignals(True)
        for i in range(it.childCount()):  # o grupo liga e desliga os filhos junto
            it.child(i).setCheckState(0, it.checkState(0))
        self.lista.blockSignals(False)
        for k in [chave] + [it.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(it.childCount())]:
            self.mostrar(k, ligado)

    def mostrar(self, chave, ligado):
        t = POR_CHAVE[chave]
        try:
            lyr = self.janela.nucleo.camada(t[2])
        except LookupError:
            return
        r = lyr.renderer()
        if isinstance(r, QgsRuleBasedRenderer):
            r.checkLegendSymbolItem(chave, ligado)
            lyr.triggerRepaint()
            self.janela.arvore.refreshLayerSymbology(lyr.id())

    def _filtrar(self, txt):
        t = txt.strip().lower()
        for i in range(self.lista.topLevelItemCount()):
            it = self.lista.topLevelItem(i)
            filhos = [it.child(j) for j in range(it.childCount())]
            vis = [not t or t in f.text(0).lower() for f in filhos]
            for f, v in zip(filhos, vis):
                f.setHidden(not v)
            it.setHidden(bool(t) and t not in it.text(0).lower() and not any(vis))

    # ------------------------------------------------ menu e clique duplo
    def _camada(self, it):
        t = POR_CHAVE[it.data(0, Qt.ItemDataRole.UserRole)]
        try:
            return t, self.janela.nucleo.camada(t[2])
        except LookupError:
            return t, None

    def _duplo(self, it, _c):
        t, lyr = self._camada(it)
        if lyr is not None and editar_tipo(self.janela, t, lyr):
            self.projeto_aberto()

    def _menu(self, pos):
        it = self.lista.itemAt(pos)
        if it is None:
            return
        t, lyr = self._camada(it)
        if lyr is None:
            return
        m = QMenu(self)
        m.addAction(icone("selecionar"), f"Selecionar todos: {t[1]}").triggered.connect(
            lambda: (lyr.selectByExpression(t[3] or "TRUE"), self.janela._selecao_mudou()))
        m.addAction(icone("tabelas"), "Abrir a tabela").triggered.connect(
            lambda: __import__("programa.tabelas", fromlist=["abrir_tabela"]).abrir_tabela(self.janela.nucleo,
                                                                                           camada=t[2]))
        m.addAction(icone("simbologia"), "Símbolo, rótulos e cores…").triggered.connect(lambda: self._duplo(it, 0))
        m.addAction(icone("atualizar"), "Voltar à simbologia padrão do GWATER").triggered.connect(
            lambda: (gravar_config({k: v for k, v in config().items() if k != t[0]}), self.projeto_aberto()))
        m.exec(self.lista.mapToGlobal(pos))


# ================================================================ editor de um tipo (como o do WaterGEMS)
RAMPA = ["#1c7ed6", "#22b8cf", "#2fb36f", "#f59f00", "#e5484d", "#ae3ec9", "#495057", "#74b816", "#f76707", "#4263eb"]


def _rampa(n):
    """Cores de azul a vermelho em n passos (faixas)."""
    base = [(28, 126, 214), (47, 179, 111), (245, 159, 0), (229, 72, 77)]
    if n <= 1:
        return ["#1c7ed6"]
    out = []
    for i in range(n):
        x = i / (n - 1) * (len(base) - 1)
        k = min(int(x), len(base) - 2)
        f = x - k
        out.append("#%02x%02x%02x" % tuple(int(a + (b - a) * f) for a, b in zip(base[k], base[k + 1])))
    return out


def editar_tipo(janela, t, lyr):
    """Tamanho do símbolo, rótulos e color coding de um tipo de elemento. True se mudou."""
    from qgis.core import QgsFeatureRequest as Req
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                                     QHeaderView, QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem)
    from .util import Dialogo
    cfg = config()
    c = cfg.get(t[0], {})
    linha = t[6] == "linha"
    d = Dialogo(janela, f"Simbologia · {t[1]}", "Tamanho do símbolo, rótulos e cores por valor (color coding), como no "
                "WaterGEMS. Vale só para este tipo de elemento e fica salvo no projeto.", largura=660)
    abas = QTabWidget()

    # ---- símbolo
    w1 = QWidget()
    f1 = QFormLayout(w1)
    tam = QDoubleSpinBox()
    tam.setRange(0.2, 30)
    tam.setDecimals(2 if linha else 1)
    tam.setSingleStep(0.25 if linha else 0.5)
    tam.setValue(float(c.get("tam") or (1.0 if linha else t[7])))
    tam.setSuffix(" × o padrão" if linha else " mm")
    f1.addRow("Espessura:" if linha else "Tamanho do símbolo:", tam)
    prev = QLabel()
    prev.setFixedSize(96, 96)
    prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
    prev.setStyleSheet("background:#f4f7fb; border-radius:8px")

    def ver():
        px = int(min(90, tam.value() * (24 if linha else 6)))
        prev.setPixmap(icone(t[5]).pixmap(QSize(max(px, 8), max(px, 8))))
    tam.valueChanged.connect(ver)
    ver()
    f1.addRow("Prévia:", prev)
    abas.addTab(w1, "Símbolo")

    # ---- rótulos
    ro = c.get("rotulo") or {}
    w2 = QWidget()
    f2 = QFormLayout(w2)
    rot_on = QCheckBox("Mostrar rótulos deste tipo no mapa")
    rot_on.setChecked(bool(ro.get("on")))
    f2.addRow(rot_on)
    rot_campo = QComboBox()
    rot_campo.addItems([f.name() for f in lyr.fields() if f.name() != "fid"])
    rot_campo.setCurrentText(ro.get("campo", "id"))
    f2.addRow("Campo:", rot_campo)
    pre, suf = QLineEdit(ro.get("prefixo", "")), QLineEdit(ro.get("sufixo", ""))
    pre.setPlaceholderText("ex.: DN ")
    suf.setPlaceholderText("ex.:  mm")
    f2.addRow("Texto antes:", pre)
    f2.addRow("Texto depois:", suf)
    rot_tam = QSpinBox()
    rot_tam.setRange(5, 30)
    rot_tam.setValue(int(ro.get("tam", 8)))
    f2.addRow("Tamanho da letra:", rot_tam)
    cor_rot = {"v": ro.get("cor", "#0b1f3a")}
    b_cor = QPushButton("Cor do texto")
    b_cor.setStyleSheet(f"background:{cor_rot['v']}; color:white")

    def esc_cor():
        q = QColorDialog.getColor(QColor(cor_rot["v"]), d)
        if q.isValid():
            cor_rot["v"] = q.name()
            b_cor.setStyleSheet(f"background:{q.name()}; color:white")
    b_cor.clicked.connect(esc_cor)
    f2.addRow("Cor:", b_cor)
    abas.addTab(w2, "Rótulos")

    # ---- cores por valor (color coding)
    co = c.get("cores") or {}
    w3 = QWidget()
    v3 = QVBoxLayout(w3)
    h3 = QHBoxLayout()
    cor_campo = QComboBox()
    cor_campo.addItem("(sem cores por valor)", None)
    for f in lyr.fields():
        if f.name() not in ("fid", "id", "nome", "observacao"):
            cor_campo.addItem(f.name(), f.name())
    cor_campo.setCurrentIndex(max(0, cor_campo.findData(co.get("campo"))))
    modo = QComboBox()
    modo.addItem("Faixas (números)", "faixas")
    modo.addItem("Categorias (cada valor)", "categorias")
    modo.setCurrentIndex(1 if co.get("modo") == "categorias" else 0)
    ncl = QSpinBox()
    ncl.setRange(2, 12)
    ncl.setValue(len(co.get("classes") or []) or 5)
    bger = QPushButton("Gerar classes")
    for w in (QLabel("Campo:"), cor_campo, modo, QLabel("Classes:"), ncl, bger):
        h3.addWidget(w)
    v3.addLayout(h3)
    tab = QTableWidget(0, 4)
    tab.setHorizontalHeaderLabels(["De / valor", "Até", "Cor", "Legenda"])
    tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    tab.verticalHeader().setVisible(False)
    v3.addWidget(tab, 1)
    dica = QLabel("Clique na cor para trocar. Faixa: de ≤ valor < até (vazio = sem limite). Os pontos com cores por "
                  "valor viram círculos coloridos; as tubulações mudam de cor.")
    dica.setWordWrap(True)
    dica.setStyleSheet(f"color:{COR['muted']}")
    v3.addWidget(dica)
    abas.addTab(w3, "Cores por valor")

    def por_linha(a, b, cor, rot):
        i = tab.rowCount()
        tab.insertRow(i)
        for col, val in enumerate((a, b)):
            tab.setItem(i, col, QTableWidgetItem("" if val is None else (f"{val:g}" if isinstance(val, float) else str(val))))
        bc = QPushButton()
        bc.setProperty("cor", cor)
        bc.setStyleSheet(f"background:{cor}")

        def trocar(_=False, botao=bc):
            q = QColorDialog.getColor(QColor(botao.property("cor")), d)
            if q.isValid():
                botao.setProperty("cor", q.name())
                botao.setStyleSheet(f"background:{q.name()}")
        bc.clicked.connect(trocar)
        tab.setCellWidget(i, 2, bc)
        tab.setItem(i, 3, QTableWidgetItem(rot))

    for cl in co.get("classes") or []:
        if co.get("modo") == "categorias":
            por_linha(cl[0], None, cl[1], cl[2])
        else:
            por_linha(cl[0], cl[1], cl[2], cl[3])

    def gerar():
        tab.setRowCount(0)
        campo = cor_campo.currentData()
        if not campo:
            return
        req = Req()
        if t[3]:
            req.setFilterExpression(t[3])
        vals = [f[campo] for f in lyr.getFeatures(req)]
        vals = [v for v in vals if v is not None and str(v) != "NULL"]
        if modo.currentData() == "categorias":
            for v, cor in zip(sorted(set(vals), key=str)[:30], RAMPA * 3):
                por_linha(v, None, cor, str(v))
            return
        nums = []
        for v in vals:
            try:
                nums.append(float(v))
            except (TypeError, ValueError):
                pass
        if not nums:
            return
        k = ncl.value()
        lo, hi = min(nums), max(nums)
        passo = (hi - lo) / k if hi > lo else 1.0
        for i, cor in enumerate(_rampa(k)):
            a = None if i == 0 else round(lo + passo * i, 3)
            b = None if i == k - 1 else round(lo + passo * (i + 1), 3)
            por_linha(a, b, cor, f"< {b:g}" if a is None else f"≥ {a:g}" if b is None else f"{a:g} a {b:g}")
    bger.clicked.connect(gerar)
    d.lay.addWidget(abas, 1)
    d.resize(700, 540)
    d.botoes("Aplicar")
    if not d.exec():
        return False

    def valor(txt):
        txt = (txt or "").strip()
        try:
            return float(txt.replace(",", ".")) if txt else None
        except ValueError:
            return txt
    classes = []
    for i in range(tab.rowCount()):
        a = valor(tab.item(i, 0).text() if tab.item(i, 0) else "")
        b = valor(tab.item(i, 1).text() if tab.item(i, 1) else "")
        cor = tab.cellWidget(i, 2).property("cor")
        rot = tab.item(i, 3).text() if tab.item(i, 3) else ""
        classes.append([a, cor, rot] if modo.currentData() == "categorias" else [a, b, cor, rot])
    cfg[t[0]] = {"tam": tam.value(),
                 "rotulo": {"on": rot_on.isChecked(), "campo": rot_campo.currentText(), "tam": rot_tam.value(),
                            "cor": cor_rot["v"], "prefixo": pre.text(), "sufixo": suf.text()},
                 "cores": {"campo": cor_campo.currentData(), "modo": modo.currentData(), "classes": classes}
                 if cor_campo.currentData() and classes else {}}
    gravar_config(cfg)
    return True
