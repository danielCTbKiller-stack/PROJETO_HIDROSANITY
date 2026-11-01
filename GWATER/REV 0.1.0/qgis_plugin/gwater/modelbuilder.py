"""ModelBuilder do GWATER: importa elementos de qualquer arquivo para o cadastro aberto.

Como o ModelBuilder do WaterGEMS: escolhe-se o tipo de elemento (tubulações, nós, válvulas...),
o arquivo de origem e, numa tabela "de → para", qual coluna do arquivo vira cada campo do cadastro.
Valores de lista (material, status, tipo de válvula...) são traduzidos num segundo quadro.

Tubulações: nas pontas são criados nós, unindo as pontas que estão a menos da tolerância
(e ligando em elementos que já existem no cadastro). Opcionalmente as ligações em "T" são divididas.
Elementos pontuais: podem dividir as tubulações sobre as quais caem e substituir nós no mesmo lugar.

Tudo vai para o buffer de edição: confira no mapa e use Salvar edições (ou descarte as edições).
"""
import re
import unicodedata
from collections import defaultdict

from qgis.core import (
    QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import estilo
from .desenho import PONTOS, TOL, _linha, _ponto, _vazio

ELEMENTOS = [  # camada, nome, ícone, geometria
    ("trecho", "Tubulações", "tubulacao", "linha"),
    ("no_juncao", "Nós / junções", "no", "ponto"),
    ("valvula", "Válvulas", "valvula", "ponto"),
    ("bomba", "Bombas", "bomba", "ponto"),
    ("reservatorio", "Reservatórios", "reservatorio", "ponto"),
    ("captacao", "Captações", "captacao", "ponto"),
]
CALCULADOS = {"fid", "comprimento", "no_inicial", "no_final", "volume_util"}
DESCRICAO = {
    "id": "Código do elemento (vazio ou repetido: o GWATER gera um)", "nome": "Nome",
    "diametro_nominal": "Diâmetro nominal (mm)", "material": "Material (define a rugosidade C)",
    "rugosidade_hw": "Rugosidade C de Hazen-Williams", "perda_localizada": "Coeficiente de perda localizada",
    "status": "Status (aberto/fechado...)", "ano_instalacao": "Ano de instalação", "situacao": "EXISTENTE / PROJETADO",
    "setor": "Setor de abastecimento", "observacao": "Observação", "cota": "Cota do terreno (m)",
    "demanda_base": "Demanda base (L/s)", "padrao": "Padrão de consumo", "tipo": "Tipo",
    "diametro": "Diâmetro (mm)", "ajuste": "Ajuste: pressão (mca) ou vazão (L/s)", "elevatoria": "Elevatória",
    "curva": "Curva da bomba", "status_inicial": "Status inicial", "rotacao_relativa": "Rotação relativa (1 = nominal)",
    "potencia_cv": "Potência (cv)", "cota_fundo": "Cota de fundo (m)", "nivel_ini": "Nível inicial (m)",
    "nivel_min": "Nível mínimo (m)", "nivel_max": "Nível máximo (m)", "carga_hidraulica": "Carga hidráulica (m)",
    "padrao_carga": "Padrão de carga",
}
SINONIMOS = {  # nomes comuns de coluna em cadastros de saneamento (comparação sem acento e maiúsculas)
    "id": ["cod", "codigo", "code", "id_trecho", "id_rede", "objectid", "gid", "num", "numero"],
    "nome": ["name", "descricao", "desc"],
    "diametro_nominal": ["dn", "diam", "diametro", "diameter", "dia", "bitola", "dn_mm"],
    "diametro": ["dn", "diam", "diametro_nominal", "diameter", "bitola"],
    "material": ["mat", "material_tubo", "tipo_material"],
    "rugosidade_hw": ["c", "hw", "rug", "rugosidade", "roughness", "coef_c"],
    "ano_instalacao": ["ano", "year", "ano_inst", "dt_inst", "data_inst"],
    "status": ["estado", "situacao_operacional"], "situacao": ["sit", "condicao"],
    "setor": ["sector", "zona", "dma", "zmc", "setor_abast"], "observacao": ["obs", "observacoes", "comentario"],
    "cota": ["z", "elev", "elevacao", "elevation", "cota_terreno", "ct", "altitude"],
    "demanda_base": ["demanda", "dem", "consumo", "demand", "q", "vazao", "q_lps"],
    "padrao": ["pattern", "padrao_consumo"], "tipo": ["type", "tipo_valvula"],
    "ajuste": ["setting", "set", "pressao", "setpoint", "consigna"], "curva": ["curve", "curva_bomba"],
    "cota_fundo": ["fundo", "cf", "elev_fundo", "cota_fundo_m"], "nivel_ini": ["nivel_inicial", "na_ini"],
    "nivel_min": ["nivel_minimo", "na_min"], "nivel_max": ["nivel_maximo", "na_max"],
    "carga_hidraulica": ["carga", "head", "nivel", "na"], "potencia_cv": ["potencia", "cv", "pot"],
}
TRADUZ = {  # palavras do arquivo -> valor do cadastro (a escolha final é do usuário no quadro de valores)
    "fofo": "Ferro fundido dúctil", "ff": "Ferro fundido dúctil", "fd": "Ferro fundido dúctil",
    "ferro": "Ferro fundido dúctil", "ductil": "Ferro fundido dúctil", "fg": "Ferro fundido cinzento",
    "cinzento": "Ferro fundido cinzento", "pead": "PEAD", "pe": "PEAD", "hdpe": "PEAD", "defofo": "PVC DEFoFo",
    "pvc": "PVC PBA", "pba": "PVC PBA", "aco": "Aço", "steel": "Aço", "ca": "Cimento-amianto",
    "amianto": "Cimento-amianto", "fibrocimento": "Cimento-amianto",
    "open": "ABERTO", "aberto": "ABERTO", "closed": "FECHADO", "fechado": "FECHADO", "cv": "CV",
    "existente": "EXISTENTE", "projetado": "PROJETADO", "projeto": "PROJETADO", "desativado": "DESATIVADO",
    "prv": "PRV", "vrp": "PRV", "redutora": "PRV", "psv": "PSV", "sustentadora": "PSV", "fcv": "FCV",
    "tcv": "TCV", "registro": "TCV", "pbv": "PBV", "gpv": "GPV",
}


def norm(texto):
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def numero(v):
    """'DN100', '100 mm', '0,15', 150 -> número (ou None)."""
    if _vazio(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def campos_do(lyr):
    return [f.name() for f in lyr.fields() if f.name() not in CALCULADOS]


def dominio(lyr, campo):
    """Valores da lista (ValueMap) do campo no formulário do cadastro, ou None se for campo livre."""
    idx = lyr.fields().indexOf(campo)
    if idx < 0:
        return None
    cfg = lyr.editorWidgetSetup(idx)
    if cfg.type() != "ValueMap":
        return None
    mapa = cfg.config().get("map", [])
    if isinstance(mapa, dict):
        return [v for v in mapa.values() if v not in (None, "")]
    return [v for d in mapa for v in d.values() if v not in (None, "") and not str(v).startswith("{")]


def sugerir_coluna(campo, colunas):
    nc = {norm(c): c for c in colunas}
    for cand in [campo] + SINONIMOS.get(campo, []):
        if norm(cand) in nc:
            return nc[norm(cand)]
    return None


def sugerir_valor(bruto, valores):
    b = norm(bruto)
    por_norma = {norm(v): v for v in valores}
    if b in por_norma:
        return por_norma[b]
    for pal in re.split(r"_+", b):
        if pal in TRADUZ and TRADUZ[pal] in valores:
            return TRADUZ[pal]
    for nv, v in por_norma.items():
        if b and (b in nv or nv in b):
            return v
    return None


# ================================================================ motor da importação
def importar(plugin, camada, origem, mapa, fixos, traducoes, opcoes, so_selecionadas=False):
    """Importa as feições de `origem` para a camada do cadastro.

    mapa: {campo_cadastro: coluna_origem}; fixos: {campo: texto} (usado quando a coluna vem vazia);
    traducoes: {campo: {valor_origem: valor_cadastro}}; opcoes: tolerancia, criar_nos, dividir_t,
    dividir_tubos, substituir_nos, situacao.
    Devolve {"importados", "nos_criados", "ligados_existentes", "divididas", "avisos"}.
    """
    topo = plugin.topologia
    if not topo.camadas:
        topo.conectar()
    dest = topo.camadas[camada]
    for lyr in topo.camadas.values():
        if not lyr.isEditable():
            lyr.startEditing()
    tol = float(opcoes.get("tolerancia", 0.5))
    ct = QgsCoordinateTransform(origem.crs(), dest.crs(), QgsProject.instance())
    eh_linha = camada == "trecho"
    campos = campos_do(dest)
    numericos = {f.name() for f in dest.fields() if f.isNumeric()}
    inteiros = {f.name() for f in dest.fields() if f.typeName().lower().startswith("int")}
    existentes = {str(f["id"]) for nome in (["trecho"] if eh_linha else PONTOS)
                  for f in topo.camadas[nome].getFeatures()}
    avisos, novos = [], []
    sem_geom = repetidos = 0
    topo.ocupado, topo.contador = True, {}
    topo.n_nos = topo.n_divisoes = 0
    try:
        feicoes = origem.getSelectedFeatures() if so_selecionadas else origem.getFeatures()
        for fo in feicoes:
            if not fo.hasGeometry() or fo.geometry().isEmpty():
                sem_geom += 1
                continue
            g = QgsGeometry(fo.geometry())
            g.transform(ct)
            if eh_linha:
                partes = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
                partes = [[QgsPointXY(p) for p in parte] for parte in partes if len(parte) >= 2]
            else:
                partes = [QgsPointXY(p) for p in g.asMultiPoint()] if g.isMultipart() else [QgsPointXY(g.asPoint())]
            for parte in partes:
                nf = QgsFeature(dest.fields())
                for campo in campos:
                    valor, col = None, mapa.get(campo)
                    if col:
                        bruto = fo[col]
                        if not _vazio(bruto):
                            if campo in traducoes:
                                valor = traducoes[campo].get(str(bruto))
                            elif campo in numericos:
                                valor = numero(bruto)
                            else:
                                valor = str(bruto).strip()
                    if valor is None and str(fixos.get(campo, "")).strip():
                        valor = numero(fixos[campo]) if campo in numericos else fixos[campo].strip()
                    if valor is not None and campo in inteiros:
                        valor = int(round(valor))  # campo inteiro (ano)
                    nf[campo] = valor
                cod = None if _vazio(nf["id"]) else str(nf["id"])
                if cod is None or cod in existentes:
                    if cod is not None:
                        repetidos += 1
                    cod = topo.proximo_id(camada)
                    while cod in existentes:
                        cod = topo.proximo_id(camada)
                    nf["id"] = cod
                existentes.add(cod)
                if _vazio(nf["situacao"]):
                    nf["situacao"] = opcoes.get("situacao", "EXISTENTE")
                if eh_linha:
                    geo = QgsGeometry.fromPolylineXY(parte)
                    if geo.length() <= 0:
                        continue
                    nf.setGeometry(geo)
                    nf["comprimento"] = round(geo.length(), 2)
                    if _vazio(nf["status"]):
                        nf["status"] = "ABERTO"
                    if _vazio(nf["rugosidade_hw"]) and not _vazio(nf["material"]):
                        nf["rugosidade_hw"] = topo.rugosidade(nf["material"])
                    if _vazio(nf["perda_localizada"]):
                        nf["perda_localizada"] = 0.0
                else:
                    nf.setGeometry(QgsGeometry.fromPointXY(parte))
                    for campo, padrao in {"no_juncao": {"tipo": "JUNCAO", "demanda_base": 0.0},
                                          "valvula": {"status": "ATIVA", "perda_localizada": 0.0},
                                          "bomba": {"status_inicial": "ABERTA", "rotacao_relativa": 1.0}
                                          }.get(camada, {}).items():
                        if _vazio(nf[campo]):
                            nf[campo] = padrao
                    if "cota" in campos and _vazio(nf["cota"]):
                        nf["cota"] = topo.cota_mdt(parte)
                dest.addFeature(nf)
                novos.append(nf.id())
    finally:
        topo.ocupado = False
    if repetidos:
        avisos.append(f"{repetidos} código(s) do arquivo já existiam no cadastro: receberam código novo")
    if sem_geom:
        avisos.append(f"{sem_geom} feição(ões) sem geometria foram ignoradas")

    out = {"importados": len(novos), "nos_criados": 0, "ligados_existentes": 0, "divididas": 0, "avisos": avisos}
    if eh_linha and opcoes.get("criar_nos", True):
        criados, ligados = ligar_pontas(topo, novos, tol)
        out["nos_criados"], out["ligados_existentes"] = criados, ligados
        if opcoes.get("dividir_t", True):
            r = topo.dividir_rede(tol, fids=novos, nos=True, em_t=True, encaixar=False)
            out["nos_criados"] += r["nos_criados"]
            out["divididas"] = r["divididas"]
    if not eh_linha:
        if opcoes.get("substituir_nos", True) and camada != "no_juncao":
            out["avisos"] += substituir_nos(topo, camada, novos)
        if opcoes.get("dividir_tubos", True):
            r = topo.dividir_rede(tol, fids=None, nos=True, em_t=False, encaixar=True)
            out["divididas"], out["ligados_existentes"] = r["divididas"], r["encaixadas"]
    topo.contador = None
    return out


def ligar_pontas(topo, fids, tol):
    """Cria nós nas pontas das tubulações importadas, unindo pontas a menos de tol.

    Pontas perto de um elemento do cadastro ligam nele. As pontas são movidas para o nó
    (o conversor exige ponta e nó no mesmo lugar). Devolve (nós criados, pontas ligadas a existentes)."""
    tr = topo.camadas["trecho"]
    pontas = []  # (fid, 0/-1, ponto)
    linhas = {}
    for fid in fids:
        f = tr.getFeature(fid)
        pts = _linha(f.geometry())
        linhas[fid] = (f, pts)
        pontas += [(fid, 0, pts[0]), (fid, -1, pts[-1])]
    # agrupa pontas próximas (grade do tamanho da tolerância + união de conjuntos)
    pai = list(range(len(pontas)))

    def raiz(k):
        while pai[k] != k:
            pai[k] = pai[pai[k]]
            k = pai[k]
        return k

    celula = max(tol, 1e-6)
    grade = defaultdict(list)
    for k, (_, _, p) in enumerate(pontas):
        cx, cy = int(p.x() // celula), int(p.y() // celula)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in grade.get((cx + dx, cy + dy), []):
                    if pontas[j][2].distance(p) <= tol:
                        pai[raiz(j)] = raiz(k)
        grade[(cx, cy)].append(k)
    grupos = defaultdict(list)
    for k in range(len(pontas)):
        grupos[raiz(k)].append(k)

    criados = ligados = 0
    novos_pts = {fid: list(pts) for fid, (_, pts) in linhas.items()}
    ids = {}
    topo.ocupado = True
    try:
        for membros in grupos.values():
            xs = [pontas[k][2] for k in membros]
            centro = QgsPointXY(sum(p.x() for p in xs) / len(xs), sum(p.y() for p in xs) / len(xs))
            achado = topo.elemento_em(centro, tol=tol)
            if achado:
                alvo, nid = _ponto(achado[1].geometry()), str(achado[1]["id"])
                ligados += len(membros)
            else:
                alvo = xs[0] if len(xs) == 1 else centro
                nid = topo.criar_no(alvo, obs="criado na importação")
                criados += 1
            for k in membros:
                fid, lado, _ = pontas[k]
                novos_pts[fid][lado] = alvo
                ids[(fid, lado)] = nid
        for fid, pts in novos_pts.items():
            pts = [p for i, p in enumerate(pts) if i == 0 or p.distance(pts[i - 1]) > 1e-9]
            if len(pts) < 2:
                continue
            topo._geometria_trecho(fid, pts)
            topo._mudar(tr, fid, "no_inicial", ids.get((fid, 0)))
            topo._mudar(tr, fid, "no_final", ids.get((fid, -1)))
    finally:
        topo.ocupado = False
    return criados, ligados


def substituir_nos(topo, camada, fids):
    """Válvula/bomba/reservatório importado em cima de um nó: o nó sai e as tubulações ligam no elemento."""
    lyr, nos, avisos = topo.camadas[camada], topo.camadas["no_juncao"], []
    n = 0
    topo.ocupado = True
    try:
        for fid in fids:
            f = lyr.getFeature(fid)
            p = _ponto(f.geometry())
            for no in nos.getFeatures(QgsFeatureRequest().setFilterRect(
                    QgsGeometry.fromPointXY(p).buffer(TOL, 4).boundingBox())):
                if _ponto(no.geometry()).distance(p) <= TOL:
                    topo.religar(no["id"], f["id"])
                    nos.deleteFeature(no.id())
                    n += 1
    finally:
        topo.ocupado = False
    if n:
        avisos.append(f"{n} nó(s) no mesmo lugar dos elementos importados foram substituídos por eles")
    return avisos


# ================================================================ janela (assistente em 4 passos)
PASSOS = ["Origem", "De → para", "Valores", "Opções"]


class ModelBuilder(QDialog):
    def __init__(self, pai, plugin):
        super().__init__(pai)
        self.plugin = plugin
        self.arquivo = None  # camada aberta a partir de arquivo (fora do projeto)
        self.setWindowTitle("GWATER · ModelBuilder: importar elementos")
        self.setObjectName("gwater")
        self.setStyleSheet(estilo.qss())
        self.resize(820, 600)
        raiz = QVBoxLayout(self)

        cab = QHBoxLayout()
        self.marcas = []
        for i, nome in enumerate(PASSOS):
            lb = QLabel(f"{i + 1} · {nome.upper()}")
            lb.setFont(estilo.fonte("mono", 8, True, 6))
            self.marcas.append(lb)
            cab.addWidget(lb)
            if i < len(PASSOS) - 1:
                seta = QLabel("›")
                seta.setObjectName("sub")
                cab.addWidget(seta)
        cab.addStretch(1)
        raiz.addLayout(cab)

        self.pilha = QStackedWidget()
        self.pilha.addWidget(self._pagina_origem())
        self.pilha.addWidget(self._pagina_depara())
        self.pilha.addWidget(self._pagina_valores())
        self.pilha.addWidget(self._pagina_opcoes())
        raiz.addWidget(self.pilha, 1)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        raiz.addWidget(self.msg)
        pe = QHBoxLayout()
        pe.addStretch(1)
        self.voltar, self.avancar, cancelar = QPushButton("‹ Voltar"), QPushButton("Avançar ›"), QPushButton("Cancelar")
        self.voltar.clicked.connect(lambda: self._ir(self.pilha.currentIndex() - 1))
        self.avancar.clicked.connect(self._proximo)
        cancelar.clicked.connect(self.reject)
        self.voltar.setAutoDefault(False)
        cancelar.setAutoDefault(False)
        self.avancar.setDefault(True)
        for b in (self.voltar, self.avancar, cancelar):
            pe.addWidget(b)
        raiz.addLayout(pe)
        self.resultado = None
        self._mudou_tipo()
        self._ir(0)

    # ------------------------------------------------ navegação
    def _ir(self, i):
        i = max(0, min(i, len(PASSOS) - 1))
        if i == 1:
            self._montar_depara()
        if i == 2:
            self._montar_valores()
        if i == 3:
            self._resumo()
        self.pilha.setCurrentIndex(i)
        for k, lb in enumerate(self.marcas):
            lb.setStyleSheet(f"color:{estilo.COR['cyan'] if k == i else estilo.COR['muted']};")
        self.voltar.setEnabled(i > 0)
        self.avancar.setText("Importar" if i == len(PASSOS) - 1 else "Avançar ›")
        self.msg.setText("")

    def _proximo(self):
        i = self.pilha.currentIndex()
        if i == 0 and self.origem() is None:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>Escolha uma camada do projeto ou um arquivo "
                             "com o tipo de geometria certo.</span>")
            return
        if i < len(PASSOS) - 1:
            self._ir(i + 1)
        else:
            self._executar()

    # ------------------------------------------------ 1 · origem
    def _pagina_origem(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        txt = QLabel("Escolha o que vai importar e de onde. Pode ser uma camada já aberta no QGIS ou um arquivo "
                     "(shapefile, GeoPackage, GeoJSON, KML, DXF...). O sistema de coordenadas é convertido sozinho.")
        txt.setObjectName("sub")
        txt.setWordWrap(True)
        lay.addWidget(txt)
        form = QFormLayout()
        self.tipo = QComboBox()
        from .dock import icone
        for camada, nome, ic, _ in ELEMENTOS:
            self.tipo.addItem(icone(ic), nome, camada)
        self.tipo.setIconSize(QSize(20, 20))
        self.tipo.currentIndexChanged.connect(self._mudou_tipo)
        form.addRow("Importar:", self.tipo)
        self.camada_proj = QgsMapLayerComboBox()
        self.camada_proj.setAllowEmptyLayer(True)
        self.camada_proj.layerChanged.connect(self._mudou_origem)
        form.addRow("Camada do projeto:", self.camada_proj)
        self.arq = QgsFileWidget()
        self.arq.setFilter("Arquivos vetoriais (*.shp *.gpkg *.geojson *.json *.kml *.dxf *.gml *.tab *.sqlite);;"
                           "Todos (*.*)")
        self.arq.fileChanged.connect(self._abrir_arquivo)
        form.addRow("ou arquivo:", self.arq)
        self.so_sel = QCheckBox("Só as feições selecionadas na camada")
        form.addRow("", self.so_sel)
        lay.addLayout(form)
        self.info = QLabel()
        self.info.setObjectName("status")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        lay.addStretch(1)
        return w

    def camada(self):
        return self.tipo.currentData()

    def geometria(self):
        return dict((c, g) for c, _, _, g in ELEMENTOS)[self.camada()]

    def origem(self):
        lyr = self.arquivo or self.camada_proj.currentLayer()
        if not isinstance(lyr, QgsVectorLayer) or not lyr.isValid():
            return None
        tipo = QgsWkbTypes.geometryType(lyr.wkbType())
        quer = QgsWkbTypes.GeometryType.LineGeometry if self.geometria() == "linha" else \
            QgsWkbTypes.GeometryType.PointGeometry
        return lyr if tipo == quer else None

    def _mudou_tipo(self):
        try:
            from qgis.core import Qgis
            filtro = Qgis.LayerFilter.LineLayer if self.geometria() == "linha" else Qgis.LayerFilter.PointLayer
        except AttributeError:
            from qgis.core import QgsMapLayerProxyModel as M
            filtro = M.LineLayer if self.geometria() == "linha" else M.PointLayer
        self.camada_proj.setFilters(filtro)
        try:  # não oferecer as camadas do próprio cadastro como origem
            self.camada_proj.setExceptedLayerList(list(self.plugin.topologia.camadas.values()))
        except Exception:
            pass
        self.camada_proj.setLayer(None)
        self._mudou_origem()

    def _abrir_arquivo(self, caminho):
        self.arquivo = None
        if caminho:
            lyr = QgsVectorLayer(caminho, caminho.replace("\\", "/").split("/")[-1], "ogr")
            if lyr.isValid():
                self.arquivo = lyr
                self.camada_proj.setLayer(None)
        self._mudou_origem()

    def _mudou_origem(self, *_):
        if self.camada_proj.currentLayer() is not None:
            self.arquivo = None
        lyr = self.origem()
        if lyr is None:
            outra = self.arquivo or self.camada_proj.currentLayer()
            self.info.setText("Nenhuma origem escolhida." if outra is None else
                              f"<span style='color:{estilo.COR['crit']}'>{outra.name()} não é uma camada de "
                              f"{'linhas' if self.geometria() == 'linha' else 'pontos'}.</span>")
            self.so_sel.setEnabled(False)
            return
        nsel = lyr.selectedFeatureCount()
        self.so_sel.setEnabled(nsel > 0)
        self.so_sel.setText(f"Só as feições selecionadas na camada ({nsel})")
        if not nsel:
            self.so_sel.setChecked(False)
        self.info.setText(f"<b>{lyr.name()}</b> · {lyr.featureCount()} feições · {len(lyr.fields())} colunas · "
                          f"{lyr.crs().authid() or 'sem sistema de coordenadas!'}")

    # ------------------------------------------------ 2 · de → para
    def _pagina_depara(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        txt = QLabel("Para cada campo do cadastro, escolha a coluna do arquivo que tem essa informação. Os nomes "
                     "parecidos já vêm ligados. Se a coluna estiver vazia numa feição, vale o <b>valor fixo</b>. "
                     "Comprimento e nós inicial/final são calculados pelo GWATER.")
        txt.setObjectName("sub")
        txt.setWordWrap(True)
        lay.addWidget(txt)
        self.tab = QTableWidget(0, 4)
        self.tab.setHorizontalHeaderLabels(["Campo do GWATER", "Coluna do arquivo", "Valor fixo", "Exemplo"])
        h = self.tab.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.tab.verticalHeader().setVisible(False)
        lay.addWidget(self.tab, 1)
        return w

    def _montar_depara(self):
        dest = self.plugin.camada(self.camada())
        lyr = self.origem()
        colunas = [f.name() for f in lyr.fields()]
        self.exemplo = next(lyr.getFeatures(), None)
        anterior = getattr(self, "_mapa_de", None)
        self._mapa_de = (self.camada(), lyr.id())
        if anterior == self._mapa_de and self.tab.rowCount():
            return  # mantém o que o usuário já ligou
        self.combos, self.fixos = {}, {}
        campos = campos_do(dest)
        self.tab.setRowCount(len(campos))
        for r, campo in enumerate(campos):
            it = QTableWidgetItem(f"{campo}\n{DESCRICAO.get(campo, '')}")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tab.setItem(r, 0, it)
            cb = QComboBox()
            cb.addItem("(não importar)", None)
            for c in colunas:
                cb.addItem(c, c)
            sug = sugerir_coluna(campo, colunas)
            if sug:
                cb.setCurrentIndex(colunas.index(sug) + 1)
            cb.currentIndexChanged.connect(lambda _=0, rr=r: self._exemplo(rr))
            self.tab.setCellWidget(r, 1, cb)
            fx = QLineEdit()
            fx.setPlaceholderText("—")
            dom = dominio(dest, campo)
            if dom:
                fx.setToolTip("Valores aceitos: " + ", ".join(map(str, dom)))
            self.tab.setCellWidget(r, 2, fx)
            self.combos[campo], self.fixos[campo] = cb, fx
            self._exemplo(r)
        self.tab.resizeRowsToContents()

    def _exemplo(self, r):
        campo = self.tab.item(r, 0).text().split("\n")[0]
        col = self.combos[campo].currentData()
        v = self.exemplo[col] if (col and self.exemplo is not None) else ""
        it = QTableWidgetItem("" if _vazio(v) else str(v))
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tab.setItem(r, 3, it)

    def mapa(self):
        return {c: cb.currentData() for c, cb in self.combos.items() if cb.currentData()}

    # ------------------------------------------------ 3 · valores
    def _pagina_valores(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        txt = QLabel("Campos com lista de valores: diga o que cada valor do arquivo significa no cadastro. "
                     "Valores sem correspondência ficam vazios (e podem usar o valor fixo do passo anterior).")
        txt.setObjectName("sub")
        txt.setWordWrap(True)
        lay.addWidget(txt)
        rolar = QScrollArea()
        rolar.setWidgetResizable(True)
        self.caixa_valores = QWidget()
        self.lay_valores = QVBoxLayout(self.caixa_valores)
        rolar.setWidget(self.caixa_valores)
        lay.addWidget(rolar, 1)
        return w

    def _montar_valores(self):
        while self.lay_valores.count():
            it = self.lay_valores.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        dest, lyr = self.plugin.camada(self.camada()), self.origem()
        self.trad = {}
        for campo, col in self.mapa().items():
            dom = dominio(dest, campo)
            if not dom:
                continue
            idx = lyr.fields().indexOf(col)
            distintos = sorted({str(v) for v in lyr.uniqueValues(idx, 200) if not _vazio(v)})
            if not distintos:
                continue
            titulo = QLabel(f"{campo.upper()}  ←  coluna {col}")
            titulo.setObjectName("h3")
            titulo.setFont(estilo.fonte("mono", 8.5, True, 6))
            self.lay_valores.addWidget(titulo)
            t = QTableWidget(len(distintos), 2)
            t.setHorizontalHeaderLabels(["Valor no arquivo", "Valor no cadastro"])
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            t.verticalHeader().setVisible(False)
            self.trad[campo] = {}
            for r, v in enumerate(distintos):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                t.setItem(r, 0, it)
                cb = QComboBox()
                cb.addItem("(vazio)", None)
                for d in dom:
                    cb.addItem(str(d), d)
                sug = sugerir_valor(v, dom)
                if sug is not None:
                    cb.setCurrentIndex(dom.index(sug) + 1)
                t.setCellWidget(r, 1, cb)
                self.trad[campo][v] = cb
            t.setMinimumHeight(min(320, 34 + 30 * len(distintos)))
            self.lay_valores.addWidget(t)
        if not self.trad:
            lb = QLabel("Nenhuma coluna ligada a um campo de lista. Pode avançar.")
            lb.setObjectName("sub")
            self.lay_valores.addWidget(lb)
        self.lay_valores.addStretch(1)

    def traducoes(self):
        return {c: {v: cb.currentData() for v, cb in d.items()} for c, d in getattr(self, "trad", {}).items()}

    # ------------------------------------------------ 4 · opções
    def _pagina_opcoes(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.tol = QDoubleSpinBox()
        self.tol.setRange(0.0, 100.0)
        self.tol.setDecimals(2)
        self.tol.setValue(0.5)
        self.tol.setSuffix(" m")
        self.tol.setToolTip("Pontas (ou elementos) mais próximas que isso são ligadas no mesmo nó")
        form.addRow("Tolerância:", self.tol)
        self.situacao = QComboBox()
        self.situacao.addItems(["EXISTENTE", "PROJETADO"])
        self.situacao.setToolTip("Situação dos elementos que vierem sem essa informação")
        self.tol.setMaximumWidth(160)
        self.situacao.setMaximumWidth(160)
        form.addRow("Situação padrão:", self.situacao)
        lay.addLayout(form)
        self.criar_nos = QCheckBox("Criar nós nas pontas das tubulações (pontas a menos da tolerância viram o mesmo nó; "
                                   "pontas perto de um elemento do cadastro ligam nele)")
        self.dividir_t = QCheckBox("Dividir ligações em “T”: ponta que encosta no meio de outra tubulação divide essa "
                                   "tubulação e cria o nó")
        self.dividir_tubos = QCheckBox("Dividir as tubulações onde o elemento cair (e encaixar pontas soltas nele)")
        self.substituir = QCheckBox("Substituir o nó que estiver no mesmo lugar do elemento importado")
        for c in (self.criar_nos, self.dividir_t, self.dividir_tubos, self.substituir):
            c.setChecked(True)
            c.setStyleSheet("QCheckBox{padding:3px 0;}")
            lay.addWidget(c)
        self.resumo = QLabel()
        self.resumo.setObjectName("status")
        self.resumo.setWordWrap(True)
        lay.addWidget(self.resumo)
        lay.addStretch(1)
        return w

    def _resumo(self):
        linha = self.geometria() == "linha"
        for c in (self.criar_nos, self.dividir_t):
            c.setVisible(linha)
        self.dividir_tubos.setVisible(not linha)
        self.substituir.setVisible(not linha and self.camada() != "no_juncao")
        lyr = self.origem()
        n = lyr.selectedFeatureCount() if self.so_sel.isChecked() else lyr.featureCount()
        nome = self.tipo.currentText().lower()
        ligados = ", ".join(f"{c} ← {col}" for c, col in self.mapa().items()) or "nenhum campo"
        self.resumo.setText(f"Serão importadas <b>{n}</b> feições de <b>{lyr.name()}</b> como <b>{nome}</b> no "
                            f"cadastro aberto.<br>Campos: {ligados}.<br>Tudo fica no buffer de edição: confira e use "
                            "<b>Salvar edições</b>.")

    def opcoes(self):
        return {"tolerancia": self.tol.value(), "situacao": self.situacao.currentText(),
                "criar_nos": self.criar_nos.isChecked(), "dividir_t": self.dividir_t.isChecked(),
                "dividir_tubos": self.dividir_tubos.isChecked(), "substituir_nos": self.substituir.isChecked()}

    def _executar(self):
        fixos = {c: fx.text() for c, fx in self.fixos.items() if fx.text().strip()}
        self.msg.setText("Importando…")
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.processEvents()
        try:
            self.resultado = importar(self.plugin, self.camada(), self.origem(), self.mapa(), fixos,
                                      self.traducoes(), self.opcoes(), self.so_sel.isChecked())
        except Exception as e:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>Falhou: {e}</span>")
            return
        self.accept()
