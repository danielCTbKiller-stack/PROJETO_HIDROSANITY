"""Janelas das ferramentas do GWATER: cotas do MDT, distribuição de demanda, novo cadastro,
importação de shapefile e guia dos botões. Cada função monta a janela e devolve o que o usuário escolheu."""
import html
import re
from collections import defaultdict

from qgis.core import QgsCoordinateReferenceSystem, QgsProject
from qgis.gui import QgsFieldComboBox, QgsFileWidget, QgsMapLayerComboBox, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit,
    QRadioButton, QTextBrowser, QVBoxLayout,
)

from . import acoes, estilo

CRS_PADRAO = "EPSG:31983"  # SIRGAS 2000 / UTM 23S (o do cadastro de exemplo)


def arquivo_gpkg(caminho):
    """Uma extensão .gpkg só (a janela de arquivo do Windows às vezes junta a do filtro: teste.gpkg.gpkg)."""
    base = re.sub(r"(\.gpkg)+$", "", caminho.strip(), flags=re.IGNORECASE)
    return base + ".gpkg"


def _filtro(combo, tipo):
    """Filtra um QgsMapLayerComboBox por tipo ('raster', 'linha', 'ponto') no QGIS 3.28 a 4."""
    try:
        from qgis.core import Qgis
        f = {"raster": Qgis.LayerFilter.RasterLayer, "linha": Qgis.LayerFilter.LineLayer,
             "ponto": Qgis.LayerFilter.PointLayer}[tipo]
    except AttributeError:
        from qgis.core import QgsMapLayerProxyModel as M
        f = {"raster": M.RasterLayer, "linha": M.LineLayer, "ponto": M.PointLayer}[tipo]
    combo.setFilters(f)


class _Janela(QDialog):
    def __init__(self, pai, titulo, explicacao):
        super().__init__(pai)
        self.setWindowTitle(f"GWATER · {titulo}")
        self.setMinimumWidth(520)
        self.setObjectName("gwater")
        self.setStyleSheet(estilo.qss())
        self.lay = QVBoxLayout(self)
        txt = QLabel(explicacao)
        txt.setWordWrap(True)
        txt.setObjectName("sub")
        self.lay.addWidget(txt)
        self.form = QFormLayout()
        self.lay.addLayout(self.form)

    def linha(self, rotulo, widget, dica=""):
        if dica:
            widget.setToolTip(dica)
        self.form.addRow(rotulo, widget)
        return widget

    def executar(self, ok="Aplicar"):
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(ok)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.lay.addWidget(bb)
        return self.exec() == QDialog.DialogCode.Accepted


# ---------------------------------------------------------------- cotas do terreno (como o TRex)
def janela_cotas(pai, crs_cadastro, config_atual=None, plugin=None):
    """Escolhe a fonte de cota: raster, curvas de nível ou pontos cotados; de uma camada do projeto ou de um
    arquivo (shp, gpkg com várias camadas, GeoTIFF...). Devolve {"fonte": cotas.Fonte, "config", "todas", "auto"}."""
    from . import cotas
    j = _Janela(pai, "Cotas do terreno (TRex)",
                "Lê a cota do terreno (campo cota) para nós, válvulas, bombas, reservatórios e captações, como o TRex do "
                "WaterGEMS. A fonte pode ser um "
                "raster (MDT/MDE), curvas de nível (linhas) ou pontos cotados, de uma camada aberta no QGIS ou "
                "direto de um arquivo. Com curvas, a cota é interpolada entre as duas curvas mais próximas, a qualquer "
                "distância (sem raio de busca): todo elemento da rede recebe cota. "
                "Arquivos grandes (o estado inteiro) não são carregados no mapa: só a região da rede é lida. "
                "O resultado vai no campo cota (cota do terreno) de cada elemento.")
    tipo = j.linha("Fonte das cotas:", QComboBox())
    for k, t in cotas.TIPOS.items():
        tipo.addItem(t, k)
    camada = j.linha("Fonte no projeto:", QgsMapLayerComboBox(), "Camada já aberta no QGIS com as curvas, pontos "
                                                                     "ou raster de elevação")
    camada.setAllowEmptyLayer(True)
    arq = j.linha("ou arquivo:", QgsFileWidget(), "shapefile, GeoPackage, GeoJSON, DXF, GeoTIFF...")
    arq.setFilter("Arquivos de cota (*.shp *.gpkg *.geojson *.json *.dxf *.gml *.tif *.tiff *.asc *.img *.vrt);;"
                  "Todos (*.*)")
    sub = j.linha("Camada do arquivo:", QComboBox(), "O GeoPackage tem várias camadas: escolha a das cotas")
    campo = j.linha("Campo da cota:", QgsFieldComboBox(), "Coluna com a cota em metros")
    try:
        from qgis.core import QgsFieldProxyModel
        campo.setFilters(QgsFieldProxyModel.Filter.Numeric)
    except AttributeError:
        pass
    usar_z = j.linha("", QCheckBox("Usar o Z da geometria (linhas 3D) em vez de um campo"))
    info = QLabel()
    info.setObjectName("status")
    info.setWordWrap(True)
    j.lay.addWidget(info)
    # ---- onde aplicar (campo "cota" = cota do terreno em todo elemento pontual)
    from qgis.PyQt.QtWidgets import QGridLayout, QWidget
    caixa = QWidget()
    grade = QGridLayout(caixa)
    grade.setContentsMargins(0, 0, 0, 0)
    tudo = QCheckBox("Tudo")
    tudo.setToolTip("Todos os elementos pontuais do cadastro")
    grade.addWidget(tudo, 0, 0)
    alvos = {}
    for i, (nome, rot) in enumerate(cotas.ELEMENTOS, start=1):
        n = ""
        if plugin is not None:
            try:
                n = f" ({plugin.camada(nome).featureCount()})"
            except LookupError:
                pass
        cb = QCheckBox(rot + n)
        cb.setChecked(True)
        alvos[nome] = cb
        grade.addWidget(cb, i // 3, i % 3)
    tudo.setChecked(True)
    tudo.toggled.connect(lambda v: [cb.setChecked(v) for cb in alvos.values()])
    j.linha("Aplicar em:", caixa, "Camadas do cadastro que recebem a cota do terreno (campo cota)")
    nsel = 0
    if plugin is not None:
        for nome in alvos:
            try:
                nsel += plugin.camada(nome).selectedFeatureCount()
            except LookupError:
                pass
    escopo = j.linha("Elementos:", QComboBox())
    escopo.addItem("Toda a rede", False)
    if nsel:
        escopo.addItem(f"Só os selecionados no mapa ({nsel})", True)
    escopo.setMaximumWidth(260)
    todas = QRadioButton("Todos (substitui as cotas existentes)")
    vazias = QRadioButton("Só os elementos sem cota")
    todas.setChecked(True)
    j.linha("Preencher:", todas)
    j.linha("", vazias)
    auto = j.linha("", QCheckBox("Usar esta fonte para dar cota aos elementos novos que eu desenhar"))
    auto.setChecked(True)
    estado = {"arquivo": None}

    def origem():
        return estado["arquivo"] or camada.currentLayer()

    def atualizar_info():
        lyr, k = origem(), tipo.currentData()
        vetor = k != "raster"
        for w in (campo, usar_z):
            w.setEnabled(vetor)
        if lyr is None:
            info.setText("Escolha a camada (arraste o arquivo para o QGIS) ou aponte o arquivo acima.")
            return
        from qgis.core import QgsRasterLayer, QgsWkbTypes
        if (k == "raster") != isinstance(lyr, QgsRasterLayer):
            info.setText(f"<span style='color:#ff6b7a'>{lyr.name()} não é {cotas.TIPOS[k].lower()}.</span>")
            return
        if vetor:
            quer = QgsWkbTypes.GeometryType.LineGeometry if k == "curvas" else QgsWkbTypes.GeometryType.PointGeometry
            if QgsWkbTypes.geometryType(lyr.wkbType()) != quer:
                info.setText(f"<span style='color:#ff6b7a'>{lyr.name()} não é de "
                             f"{'linhas' if k == 'curvas' else 'pontos'}.</span>")
                return
        n = "" if not vetor else f" · {lyr.featureCount():,} feições".replace(",", ".")
        info.setText(f"<b>{lyr.name()}</b>{n} · {lyr.crs().authid() or 'sem sistema de coordenadas!'}"
                     + (" · distâncias medidas em metros no sistema do cadastro" if lyr.crs().isGeographic() else ""))

    def escolher_campo():
        lyr = origem()
        from qgis.core import QgsVectorLayer
        if isinstance(lyr, QgsVectorLayer):
            campo.setLayer(lyr)
            sug = cotas.campo_cota(lyr)
            if sug:
                campo.setField(sug)
            usar_z.setEnabled(cotas.tem_z(lyr))
            usar_z.setChecked(cotas.tem_z(lyr) and sug is None)
        else:
            campo.setLayer(None)
        atualizar_info()

    def mudou_tipo():
        _filtro(camada, {"raster": "raster", "curvas": "linha", "pontos": "ponto"}[tipo.currentData()])
        camada.setLayer(None)
        escolher_campo()

    def mudou_camada(_lyr=None):
        if camada.currentLayer() is not None:
            estado["arquivo"] = None
            arq.blockSignals(True)
            arq.setFilePath("")
            arq.blockSignals(False)
            sub.clear()
            sub.setEnabled(False)
        escolher_campo()

    def abrir_sub():
        caminho = arq.filePath()
        estado["arquivo"] = cotas.abrir_arquivo(caminho, sub.currentText() or None) if caminho else None
        escolher_campo()

    def mudou_arquivo(caminho):
        sub.blockSignals(True)
        sub.clear()
        nomes = cotas.subcamadas(caminho) if caminho else []
        sub.addItems(nomes)
        sub.setEnabled(len(nomes) > 1)
        sub.blockSignals(False)
        if caminho:
            camada.blockSignals(True)
            camada.setLayer(None)
            camada.blockSignals(False)
            if caminho.lower().endswith((".tif", ".tiff", ".asc", ".img", ".vrt")):
                tipo.setCurrentIndex(list(cotas.TIPOS).index("raster"))
        abrir_sub()

    tipo.currentIndexChanged.connect(mudou_tipo)
    camada.layerChanged.connect(mudou_camada)
    arq.fileChanged.connect(mudou_arquivo)
    sub.currentIndexChanged.connect(abrir_sub)
    usar_z.toggled.connect(lambda v: campo.setEnabled(not v and tipo.currentData() != "raster"))
    sub.setEnabled(False)
    cfg = config_atual or {}
    tipo.setCurrentIndex(list(cotas.TIPOS).index(cfg.get("tipo", "curvas")))
    mudou_tipo()
    if cfg.get("arquivo"):
        arq.setFilePath(cfg["arquivo"])
        if cfg.get("sub"):
            sub.setCurrentText(cfg["sub"])
    elif cfg.get("camada"):
        lyr = QgsProject.instance().mapLayer(cfg["camada"])
        if lyr is not None:
            camada.setLayer(lyr)
    if cfg.get("campo"):
        campo.setField(cfg["campo"])
    j.setMinimumWidth(600)

    if not j.executar("Preencher cotas"):
        return None
    lyr, k = origem(), tipo.currentData()
    if lyr is None:
        return {"erro": "escolha a camada ou o arquivo das cotas."}
    camadas = [n for n, cb in alvos.items() if cb.isChecked()]
    if not camadas:
        return {"erro": "marque pelo menos um tipo de elemento em Aplicar em."}
    from qgis.core import QgsRasterLayer
    if (k == "raster") != isinstance(lyr, QgsRasterLayer):
        return {"erro": f"{lyr.name()} não é {cotas.TIPOS[k].lower()}."}
    z = usar_z.isChecked() and usar_z.isEnabled()
    if k != "raster" and not z and not campo.currentField():
        return {"erro": "escolha o campo que tem a cota (ou marque Usar o Z da geometria)."}
    fonte = cotas.Fonte(k, lyr, crs_cadastro, None if z else campo.currentField(), usar_z=z)
    config = {"tipo": k, "campo": fonte.campo, "usar_z": z}
    if estado["arquivo"] is not None:
        config.update(arquivo=arq.filePath(), sub=sub.currentText() or None)
    else:
        config["camada"] = lyr.id()
    return {"fonte": fonte, "config": config, "todas": todas.isChecked(), "auto": auto.isChecked(),
            "camadas": camadas, "so_selecionados": bool(escopo.currentData())}


def preencher_cotas(plugin, fonte, todas, camadas=None, so_selecionados=False, progresso=None):
    """Campo cota (terreno) dos elementos. `fonte`: cotas.Fonte ou um raster. Devolve (preenchidos, sem cota)."""
    from . import cotas
    if not isinstance(fonte, cotas.Fonte):
        fonte = cotas.Fonte("raster", fonte, plugin.camada("trecho").crs())
    return cotas.preencher(plugin, fonte, todas, camadas, so_selecionados, progresso)


# ---------------------------------------------------------------- distribuir demanda
def janela_demanda(pai, plugin):
    nos = plugin.camada("no_juncao")
    setores = sorted({str(f["setor"]) for f in nos.getFeatures() if f["setor"] not in (None, "") and
                      str(f["setor"]) != "NULL"})
    padroes = sorted({str(f["id_padrao"]) for f in plugin.camada("padrao_consumo").getFeatures()})
    j = _Janela(pai, "Distribuir demanda",
                "Reparte uma vazão total entre os nós. No método por comprimento, cada nó recebe a parte "
                "proporcional à metade do comprimento das tubulações ligadas a ele, que é o método usual de "
                "alocação de demanda (como o LoadBuilder do WaterGEMS). Válvulas, bombas e reservatórios não "
                "recebem demanda.")
    q = j.linha("Vazão total (L/s):", QDoubleSpinBox(), "Demanda média da área: população × consumo per capita "
                                                          "÷ 86 400, ou a vazão medida na entrada do setor")
    q.setRange(0, 1e6)
    q.setDecimals(3)
    q.setValue(10)
    escopo = j.linha("Distribuir entre:", QComboBox())
    escopo.addItem("Todos os nós da rede", ("todos", None))
    for s in setores:
        escopo.addItem(f"Nós do setor {s}", ("setor", s))
    nsel = nos.selectedFeatureCount()
    if nsel:
        escopo.addItem(f"Nós selecionados no mapa ({nsel})", ("selecao", None))
    metodo = j.linha("Método:", QComboBox())
    metodo.addItem("Proporcional ao comprimento de rede", "comprimento")
    metodo.addItem("Igual para todos os nós", "igual")
    padrao = j.linha("Padrão de consumo:", QComboBox(), "Curva de 24 h que multiplica a demanda (tabela "
                                                        "Padrões de consumo)")
    padrao.addItem("(nenhum: demanda constante)", None)
    for p in padroes:
        padrao.addItem(p, p)
    if "PAD_CONS" in padroes:
        padrao.setCurrentIndex(padroes.index("PAD_CONS") + 1)
    if not j.executar("Distribuir"):
        return None
    tipo, setor = escopo.currentData()
    return {"q": q.value(), "escopo": tipo, "setor": setor, "metodo": metodo.currentData(),
            "padrao": padrao.currentData()}


def distribuir_demanda(plugin, q, escopo, setor, metodo, padrao):
    """Devolve (nós alterados, vazão distribuída). Fica no buffer de edição."""
    nos, tr = plugin.camada("no_juncao"), plugin.camada("trecho")
    if escopo == "selecao":
        alvo = list(nos.getSelectedFeatures())
    elif escopo == "setor":
        alvo = [f for f in nos.getFeatures() if str(f["setor"]) == setor]
    else:
        alvo = list(nos.getFeatures())
    if not alvo:
        raise ValueError("nenhum nó no grupo escolhido")
    meio = defaultdict(float)
    for t in tr.getFeatures():
        if str(t["situacao"]) == "DESATIVADO":
            continue
        comp = t["comprimento"] if t["comprimento"] not in (None, "") and str(t["comprimento"]) != "NULL" \
            else t.geometry().length()
        for campo in ("no_inicial", "no_final"):
            meio[str(t[campo])] += float(comp) / 2
    peso = {f.id(): (meio[str(f["id"])] if metodo == "comprimento" else 1.0) for f in alvo}
    total = sum(peso.values())
    if total <= 0:
        raise ValueError("os nós escolhidos não têm tubulações ligadas (salve e valide a rede antes)")
    if not nos.isEditable():
        nos.startEditing()
    idx = nos.fields().indexOf
    for f in alvo:
        d = round(q * peso[f.id()] / total, 4)
        nos.changeAttributeValue(f.id(), idx("demanda_base"), d)
        nos.changeAttributeValue(f.id(), idx("padrao"), padrao if d > 0 else None)
        if d > 0 and str(f["tipo"]) in ("JUNCAO", "NULL", "None", ""):
            nos.changeAttributeValue(f.id(), idx("tipo"), "CONSUMO")
    return len(alvo), q


# ---------------------------------------------------------------- novo cadastro
def janela_novo(pai):
    j = _Janela(pai, "Novo cadastro",
                "Cria um GeoPackage vazio com todas as camadas da rede e as tabelas do modelo (padrão de consumo, "
                "curva-modelo, materiais, opções), e o projeto QGIS GWATER_<nome>.qgz na mesma pasta, já com "
                "estilos, formulários e encaixe. O projeto aberto agora será fechado (o QGIS pergunta se quer salvar).")
    arq = j.linha("Arquivo do cadastro:", QgsFileWidget(), "Pasta e nome do GeoPackage novo")
    arq.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
    arq.setFilter("GeoPackage (*.gpkg)")
    crs = j.linha("Sistema de coordenadas:", QgsProjectionSelectionWidget(),
                  "Use um sistema projetado em metros (UTM). O exemplo é SIRGAS 2000 / UTM 23S.")
    crs.setCrs(QgsCoordinateReferenceSystem(CRS_PADRAO))
    if not j.executar("Criar cadastro"):
        return None
    caminho = arq.filePath().strip()
    if not caminho:
        return {"erro": "escolha onde salvar o cadastro."}
    caminho = arquivo_gpkg(caminho)
    if crs.crs().isGeographic():
        return {"erro": "escolha um sistema projetado em metros (UTM); em graus o comprimento sai errado."}
    return {"gpkg": caminho, "crs": crs.crs().authid()}


# ---------------------------------------------------------------- importar shapefile
def janela_importar(pai):
    j = _Janela(pai, "Importar shapefile",
                "Gera um cadastro novo a partir de uma rede em linhas. Abra o shapefile no QGIS antes "
                "(arraste para o mapa). As pontas a menos da tolerância viram o mesmo nó e as ligações em “T” "
                "não segmentadas são divididas. Captação, reservatórios, bombas e válvulas você desenha depois.")
    lin = j.linha("Rede (linhas):", QgsMapLayerComboBox())
    _filtro(lin, "linha")
    campos = {}
    for chave, rotulo, dica in (("id", "Campo do código:", "Opcional: vira o código da tubulação"),
                                ("diametro", "Campo do diâmetro (mm):", "Aceita 100, 'DN100', '100 mm'"),
                                ("material", "Campo do material:", "Opcional"),
                                ("ano", "Campo do ano de instalação:", "Opcional")):
        c = j.linha(rotulo, QgsFieldComboBox(), dica)
        c.setAllowEmptyFieldName(True)
        c.setLayer(lin.currentLayer())
        lin.layerChanged.connect(c.setLayer)
        campos[chave] = c
    mat = j.linha("Materiais (opcional):", QLineEdit(),
                  "Converte o texto do shapefile no material do cadastro. Ex.: PVC=PVC PBA; FOFO=Ferro fundido dúctil")
    mat.setPlaceholderText("PVC=PVC PBA; FOFO=Ferro fundido dúctil")
    cot = j.linha("Pontos de cota (opcional):", QgsMapLayerComboBox(),
                  "Camada de pontos com a cota; cada nó usa o ponto mais próximo")
    _filtro(cot, "ponto")
    cot.setAllowEmptyLayer(True)
    cot.setLayer(None)
    ccota = j.linha("Campo da cota:", QgsFieldComboBox())
    ccota.setAllowEmptyFieldName(True)
    cot.layerChanged.connect(ccota.setLayer)
    tol = j.linha("Tolerância de ligação (m):", QDoubleSpinBox(),
                  "Pontas mais próximas que isso viram o mesmo nó")
    tol.setRange(0.01, 50)
    tol.setValue(0.5)
    q = j.linha("Vazão total a distribuir (L/s):", QDoubleSpinBox(), "0 = não distribuir agora")
    q.setRange(0, 1e6)
    q.setDecimals(3)
    arq = j.linha("Salvar cadastro em:", QgsFileWidget())
    arq.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
    arq.setFilter("GeoPackage (*.gpkg)")
    crs = j.linha("Sistema do cadastro:", QgsProjectionSelectionWidget(),
                  "A rede é reprojetada para este sistema (projetado, em metros)")
    crs.setCrs(QgsCoordinateReferenceSystem(CRS_PADRAO))
    if not j.executar("Importar"):
        return None
    lyr = lin.currentLayer()
    if lyr is None:
        return {"erro": "abra no QGIS a camada de linhas da rede."}
    fonte = lyr.source().split("|")[0]
    if not fonte.lower().endswith((".shp", ".gpkg", ".geojson", ".json", ".kml", ".dxf", ".gml", ".tab")):
        return {"erro": f"a camada '{lyr.name()}' não é um arquivo (shapefile, GeoPackage…). Exporte-a para "
                        "shapefile e tente de novo."}
    caminho = arq.filePath().strip()
    if not caminho:
        return {"erro": "escolha onde salvar o cadastro."}
    caminho = arquivo_gpkg(caminho)
    materiais = {}
    for par in mat.text().split(";"):
        if "=" in par:
            k, v = par.split("=", 1)
            materiais[k.strip()] = v.strip()
    cfg = {"trechos": fonte, "destino": caminho, "crs": crs.crs().authid(),
           "campos": {k: c.currentField() for k, c in campos.items() if c.currentField()},
           "materiais": materiais, "tolerancia_m": tol.value(), "padrao": "PAD_CONS"}
    if q.value() > 0:
        cfg["vazao_total_lps"] = q.value()
    if cot.currentLayer() is not None and ccota.currentField():
        cfg["pontos_cota"] = cot.currentLayer().source().split("|")[0]
        cfg["campos"]["cota"] = ccota.currentField()
    return cfg


# ---------------------------------------------------------------- dividir tubulações
def janela_dividir(pai, nsel):
    j = _Janela(pai, "Dividir tubulações",
                "Corrige a ligação da rede usando uma tolerância (como o Split do WaterGEMS). O que estiver a menos "
                "dessa distância é considerado ligado. Tudo fica no buffer de edição: confira no mapa e use "
                "Salvar edições.")
    tol = j.linha("Tolerância:", QDoubleSpinBox(), "Distância máxima, em metros, para considerar dois elementos ligados")
    tol.setRange(0.01, 100)
    tol.setDecimals(2)
    tol.setValue(0.5)
    tol.setSuffix(" m")
    escopo = j.linha("Tubulações:", QComboBox())
    escopo.addItem("Toda a rede", False)
    if nsel:
        escopo.addItem(f"Só as selecionadas ({nsel})", True)
        escopo.setCurrentIndex(1)
    encaixar = j.linha("", QCheckBox("Encaixar pontas soltas no elemento mais próximo"))
    em_t = j.linha("", QCheckBox("Dividir onde a ponta de uma tubulação encosta no meio de outra (“T”)"))
    nos = j.linha("", QCheckBox("Dividir onde um nó, válvula, bomba ou reservatório está sobre a tubulação"))
    for c in (encaixar, em_t, nos):
        c.setChecked(True)
    if not j.executar("Dividir"):
        return None
    return {"tol": tol.value(), "selecionadas": escopo.currentData(), "encaixar": encaixar.isChecked(),
            "em_t": em_t.isChecked(), "nos": nos.isChecked()}


# ---------------------------------------------------------------- guia
def html_guia():
    e = html.escape
    partes = ["<h2 style='margin-bottom:2px'>GWATER · Guia dos botões</h2>",
              "<p><i>Os mesmos botões estão no menu <b>GWATER</b>, nas barras "
              "<b>GWATER · Desenho</b> e <b>GWATER · Modelo</b> e na <b>Central GWATER</b> (painel lateral). "
              "Passe o mouse sobre qualquer botão para ver esta explicação.</i></p>",
              "<h3>Passo a passo para montar uma rede</h3><ol>"]
    partes += [f"<li><b>{e(t)}</b>: {e(d)}</li>" for t, d in acoes.PASSO_A_PASSO]
    partes.append("</ol>")
    for _, titulo, sub, lista in acoes.GRUPOS:
        partes.append(f"<h3 style='margin-bottom:0'>{e(titulo)}</h3>")
        if sub:
            partes.append(f"<p style='margin-top:2px'><i>{e(sub)}</i></p>")
        partes.append("<table cellspacing='0' cellpadding='4' width='100%'>")
        for _, texto, _, desc in lista:
            partes.append(f"<tr><td valign='top' width='170'><b>{e(texto)}</b></td><td>{e(desc)}</td></tr>")
        partes.append("</table>")
    partes.append("<h3>Regras do desenho</h3><ul>"
                  "<li>Desenhe as tubulações no sentido do escoamento: em válvulas e bombas, a tubulação que "
                  "chega é montante e a que sai é jusante.</li>"
                  "<li>O encaixe (snapping) fica ligado em vértices e segmentos: a ponta da tubulação gruda no "
                  "elemento ou na outra tubulação.</li>"
                  "<li>Tubulações que só se cruzam no desenho, sem vértice comum, <b>não</b> são ligadas "
                  "(como em viadutos e travessias).</li>"
                  "<li>Desligue <i>Ligar automaticamente</i> na Central para editar livremente, sem criar nós.</li>"
                  "<li>Nada vai para o arquivo até <b>Salvar edições</b>. Para desfazer, use Ctrl+Z na camada.</li>"
                  "</ul>")
    return "".join(partes)


def janela_guia(pai):
    j = QDialog(pai)
    j.setWindowTitle("GWATER · Guia dos botões")
    j.resize(760, 680)
    j.setObjectName("gwater")
    j.setStyleSheet(estilo.qss())
    lay = QVBoxLayout(j)
    t = QTextBrowser()
    t.setOpenExternalLinks(True)
    t.setHtml(estilo.css_html() + html_guia())
    lay.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    bb.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
    bb.rejected.connect(j.reject)
    lay.addWidget(bb)
    j.setWindowModality(Qt.WindowModality.NonModal)
    j.show()
    return j
