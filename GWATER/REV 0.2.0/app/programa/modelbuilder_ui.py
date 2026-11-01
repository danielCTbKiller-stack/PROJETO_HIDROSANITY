"""ModelBuilder do GWATER.exe: vários arquivos de uma vez, cada um com o seu tipo de elemento.

1 · Arquivos ...... adicione os .shp (ou GeoPackage, GeoJSON, KML, DXF, camadas do projeto). Para cada um,
                    escolha o que ele é: linhas só podem ser tubulações; pontos podem ser nó, ponto de consumo,
                    hidrante, reservatório, captação, bomba, PRV, PSV, PBV, FCV, TCV, GPV, registro ou
                    "válvula com o tipo numa coluna". O nome do arquivo já sugere o tipo (vrp, registro...).
2 · De → para ..... para cada arquivo, que coluna vira cada campo do cadastro.
3 · Valores ....... tradução dos valores de lista (material, status...).
4 · Opções ........ tolerância, criar nós, dividir em T, dividir tubulações nos elementos, substituir nós.
O cálculo é do importador rápido (programa/importador.py).
"""
import os

from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressDialog, QPushButton, QScrollArea,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gwater.desenho import _vazio
from gwater.estilo import COR
from gwater.modelbuilder import DESCRICAO, campos_do, dominio, norm, sugerir_coluna, sugerir_valor

from .simbologia import POR_CHAVE
from .tema import icone

PASSOS = ["Arquivos", "De → para", "Valores", "Opções"]
# o que cada geometria pode ser: (chave, nome, camada, valores fixos, ícone)
OPCOES_LINHA = [("tubulacao", "Tubulações", "trecho", {}, "elem_tubulacao")]
_P = ["no", "ponto_consumo", "hidrante", "ponta", "reservatorio", "captacao", "bomba", "valvula_prv", "valvula_psv",
      "valvula_pbv", "valvula_fcv", "valvula_vre", "valvula_vse", "valvula_tcv", "valvula_gpv", "registro"]
OPCOES_PONTO = [(k, POR_CHAVE[k][1], POR_CHAVE[k][2], POR_CHAVE[k][4], POR_CHAVE[k][5]) for k in _P] + \
    [("valvula_coluna", "Válvulas (o tipo vem de uma coluna)", "valvula", {}, "elem_valvula"),
     ("consumidor", "Consumidores (casa, ligados ao nó ou tubulação mais perto)", "consumidor", {}, "elem_consumidor")]
# polígonos: estação de bomba (pump station do WaterGEMS); a bomba entra no nó/tubo dentro do polígono
OPCOES_POLIGONO = [("estacao_bomba", "Estação de bomba", "bomba", POR_CHAVE["bomba"][4], POR_CHAVE["bomba"][5]),
                   ("estacao_reservatorio", "Reservatório (área)", "reservatorio", POR_CHAVE["reservatorio"][4],
                    POR_CHAVE["reservatorio"][5])]
GEOS = ("linha", "ponto", "poligono")
# palavras do nome do arquivo -> tipo sugerido
PISTAS = [("registro", "registro"), ("reg", "registro"), ("vrp", "valvula_prv"), ("prv", "valvula_prv"),
          ("redutora", "valvula_prv"), ("psv", "valvula_psv"), ("sustent", "valvula_psv"), ("pbv", "valvula_pbv"),
          ("fcv", "valvula_fcv"), ("tcv", "valvula_tcv"), ("gpv", "valvula_gpv"), ("valv", "valvula_coluna"),
          ("hidrant", "hidrante"), ("hid", "hidrante"), ("reserv", "reservatorio"), ("rap", "reservatorio"),
          ("rel", "reservatorio"), ("capta", "captacao"), ("manancial", "captacao"), ("bomba", "bomba"),
          ("eea", "bomba"), ("eeat", "bomba"), ("elevat", "bomba"), ("booster", "bomba"), ("consumo", "consumidor"),
          ("ligac", "consumidor"), ("hidrom", "consumidor"), ("no", "no"), ("node", "no"), ("junc", "no")]


def geometria(lyr):
    t = QgsWkbTypes.geometryType(lyr.wkbType())
    if t == QgsWkbTypes.GeometryType.LineGeometry:
        return "linha"
    if t == QgsWkbTypes.GeometryType.PointGeometry:
        return "ponto"
    if t == QgsWkbTypes.GeometryType.PolygonGeometry:
        return "poligono"
    return "outra"


def sugerir_tipo(nome, geo):
    if geo == "linha":
        return "tubulacao"
    if geo == "poligono":
        n = norm(os.path.basename(nome))
        return "estacao_reservatorio" if any(k in n for k in ("reserv", "rap", "rel")) else "estacao_bomba"
    n = norm(os.path.splitext(os.path.basename(nome))[0])
    partes = n.split("_")
    for pista, tipo in PISTAS:
        if any(p.startswith(pista) for p in partes) or (len(pista) > 3 and pista in n):
            return tipo
    return "no"


class ModelBuilderApp(QDialog):
    def __init__(self, pai, nucleo):
        super().__init__(pai)
        self.nucleo = nucleo
        self.fontes = []  # [{"lyr", "nome", "geo", "combo", "so_sel", "estado"}]
        self.resultado = None
        self.setWindowTitle("GWATER · ModelBuilder: importar elementos")
        self.resize(1040, 680)
        raiz = QVBoxLayout(self)
        cab = QHBoxLayout()
        self.marcas = []
        for i, nome in enumerate(PASSOS):
            lb = QLabel(f"{i + 1} · {nome.upper()}")
            lb.setStyleSheet("font-weight:700; letter-spacing:1px")
            self.marcas.append(lb)
            cab.addWidget(lb)
            if i < len(PASSOS) - 1:
                cab.addWidget(QLabel("›"))
        cab.addStretch(1)
        raiz.addLayout(cab)
        self.pilha = QStackedWidget()
        for f in (self._pagina_arquivos, self._pagina_depara, self._pagina_valores, self._pagina_opcoes):
            self.pilha.addWidget(f())
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
        for b in (self.voltar, self.avancar, cancelar):
            b.setAutoDefault(False)
            pe.addWidget(b)
        raiz.addLayout(pe)
        self._ir(0)

    # ================================================================ navegação
    def _ir(self, i):
        i = max(0, min(i, len(PASSOS) - 1))
        if i in (1, 2):
            self._listas_arquivos(i)
        if i == 3:
            self._resumo()
        self.pilha.setCurrentIndex(i)
        for k, lb in enumerate(self.marcas):
            lb.setStyleSheet(f"font-weight:700; color:{COR['cyan'] if k == i else COR['muted']}")
        self.voltar.setEnabled(i > 0)
        self.avancar.setText("Importar" if i == len(PASSOS) - 1 else "Avançar ›")
        self.msg.setText("")

    def _proximo(self):
        i = self.pilha.currentIndex()
        if i == 0:
            validos = [f for f in self.fontes if f["geo"] in GEOS]
            if not validos:
                return self._erro("Adicione pelo menos um arquivo de linhas, pontos ou polígonos.")
        if i < len(PASSOS) - 1:
            self._ir(i + 1)
        else:
            self._executar()

    def _erro(self, txt):
        self.msg.setText(f"<span style='color:{COR['crit']}'>{txt}</span>")

    # ================================================================ 1 · arquivos
    def _pagina_arquivos(self):
        w = QWidget()
        v = QVBoxLayout(w)
        txt = QLabel("Adicione os arquivos da rede (pode ser vários de uma vez) e diga o que cada um é. Arquivo de "
                     "<b>linhas</b> vira <b>tubulações</b>; arquivo de <b>pontos</b> pode ser nós, hidrantes, "
                     "reservatórios, bombas e cada tipo de válvula (PRV, PSV, PBV, FCV, TCV, GPV, registro). O nome do "
                     "arquivo já sugere o tipo. Os elementos pontuais entram primeiro, e as tubulações ligam neles.")
        txt.setWordWrap(True)
        txt.setStyleSheet(f"color:{COR['muted']}")
        v.addWidget(txt)
        h = QHBoxLayout()
        b = QPushButton(icone("abrir"), "Adicionar arquivos…")
        b.clicked.connect(self._adicionar_arquivos)
        h.addWidget(b)
        b = QPushButton(icone("camadas"), "Adicionar camada do projeto")
        b.clicked.connect(self._adicionar_camada)
        h.addWidget(b)
        b = QPushButton(icone("excluir"), "Remover")
        b.clicked.connect(self._remover)
        h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        self.tab_arq = QTableWidget(0, 5)
        self.tab_arq.setHorizontalHeaderLabels(["Arquivo", "Geometria", "Feições", "Importar como", "Só selecionadas"])
        hh = self.tab_arq.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tab_arq.setColumnWidth(3, 300)
        self.tab_arq.verticalHeader().setVisible(False)
        self.tab_arq.setIconSize(QSize(18, 18))
        v.addWidget(self.tab_arq, 1)
        return w

    def _adicionar_arquivos(self):
        arqs, _ = QFileDialog.getOpenFileNames(self, "Arquivos da rede", self.nucleo.janela.pasta_padrao(),
                                               "Vetoriais (*.shp *.gpkg *.geojson *.json *.kml *.dxf *.gml *.tab "
                                               "*.sqlite);;Todos (*.*)")
        for arq in arqs:
            if arq.lower().endswith((".gpkg", ".sqlite")):
                from gwater.cotas import subcamadas
                for sub in subcamadas(arq) or [None]:
                    lyr = QgsVectorLayer(f"{arq}|layername={sub}" if sub else arq, sub or os.path.basename(arq), "ogr")
                    self._por(lyr, f"{os.path.basename(arq)} › {sub}" if sub else os.path.basename(arq))
            else:
                self._por(QgsVectorLayer(arq, os.path.basename(arq), "ogr"), os.path.basename(arq))

    def _adicionar_camada(self):
        cadastro = set(l.id() for l in self.nucleo.camadas_rede())
        m = QMenu(self)
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.isSpatial() and lyr.id() not in cadastro \
                    and geometria(lyr) in GEOS:
                m.addAction(lyr.name()).triggered.connect(lambda _=False, l=lyr: self._por(l, l.name()))
        if m.isEmpty():
            m.addAction("(nenhuma camada de linhas, pontos ou polígonos fora do cadastro)").setEnabled(False)
        m.exec(self.cursor().pos())

    def _por(self, lyr, nome):
        if not lyr.isValid():
            return self._erro(f"Não consegui abrir {nome}.")
        geo = geometria(lyr)
        i = self.tab_arq.rowCount()
        self.tab_arq.insertRow(i)
        it = QTableWidgetItem(nome)
        it.setToolTip(lyr.source())
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        self.tab_arq.setItem(i, 0, it)
        g = QTableWidgetItem({"linha": "linhas", "ponto": "pontos", "poligono": "polígonos"}.get(geo, "não suportada"))
        g.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if geo == "outra":
            g.setForeground(Qt.GlobalColor.red)
        self.tab_arq.setItem(i, 1, g)
        n = QTableWidgetItem()
        n.setData(Qt.ItemDataRole.DisplayRole, lyr.featureCount())
        n.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.tab_arq.setItem(i, 2, n)
        cmb = QComboBox()
        cmb.setIconSize(QSize(18, 18))
        for chave, rot, _camada, _fixos, ic in {"linha": OPCOES_LINHA, "ponto": OPCOES_PONTO,
                                                "poligono": OPCOES_POLIGONO}.get(geo, []):
            cmb.addItem(icone(ic), rot, chave)
        if geo != "outra":
            cmb.setCurrentIndex(max(0, cmb.findData(sugerir_tipo(nome, geo))))
        cmb.setEnabled(geo in ("ponto", "poligono"))
        cmb.currentIndexChanged.connect(lambda _=0, k=i: self._mudou_tipo(k))
        self.tab_arq.setCellWidget(i, 3, cmb)
        so = QCheckBox()
        so.setEnabled(lyr.selectedFeatureCount() > 0)
        so.setToolTip(f"{lyr.selectedFeatureCount()} selecionada(s)")
        self.tab_arq.setCellWidget(i, 4, so)
        self.fontes.append({"lyr": lyr, "nome": nome, "geo": geo, "combo": cmb, "so_sel": so, "estado": None})

    def _remover(self):
        for i in sorted({x.row() for x in self.tab_arq.selectedIndexes()}, reverse=True):
            self.tab_arq.removeRow(i)
            self.fontes.pop(i)

    def _mudou_tipo(self, k):
        if k < len(self.fontes):
            self.fontes[k]["estado"] = None  # o de-para depende da camada de destino

    def tipo_de(self, fonte):
        chave = fonte["combo"].currentData()
        for op in OPCOES_LINHA + OPCOES_PONTO + OPCOES_POLIGONO:
            if op[0] == chave:
                return op
        return None

    # ================================================================ 2 · de → para (um por arquivo)
    def _pagina_depara(self):
        w = QWidget()
        v = QVBoxLayout(w)
        txt = QLabel("Escolha o arquivo à esquerda e, para cada campo do cadastro, a coluna do arquivo. Nomes "
                     "parecidos já vêm ligados. Se a coluna vier vazia numa feição, vale o <b>valor fixo</b>. O tipo "
                     "(PRV, hidrante...) já vem da escolha do passo anterior.")
        txt.setWordWrap(True)
        txt.setStyleSheet(f"color:{COR['muted']}")
        v.addWidget(txt)
        sp = QSplitter()
        self.lista_dp = QListWidget()
        self.lista_dp.setIconSize(QSize(18, 18))
        self.lista_dp.currentRowChanged.connect(self._mostrar_depara)
        sp.addWidget(self.lista_dp)
        self.pilha_dp = QStackedWidget()
        sp.addWidget(self.pilha_dp)
        sp.setSizes([260, 740])
        v.addWidget(sp, 1)
        return w

    def _listas_arquivos(self, passo):
        validas = [f for f in self.fontes if f["geo"] in GEOS]
        for lista in (self.lista_dp, self.lista_val):
            lista.blockSignals(True)
            lista.clear()
            for f in validas:
                op = self.tipo_de(f)
                it = QListWidgetItem(icone(op[4]), f"{f['nome']}\n→ {op[1]}")
                lista.addItem(it)
            lista.blockSignals(False)
        for f in validas:
            self._garantir_estado(f)
        while self.pilha_dp.count():
            self.pilha_dp.removeWidget(self.pilha_dp.widget(0))
        for f in validas:
            self.pilha_dp.addWidget(f["estado"]["tabela"])
        if passo == 1:
            self.lista_dp.setCurrentRow(0)
        else:
            self._montar_valores(validas)
            self.lista_val.setCurrentRow(0)

    def _mostrar_depara(self, i):
        if 0 <= i < self.pilha_dp.count():
            self.pilha_dp.setCurrentIndex(i)

    def _garantir_estado(self, fonte):
        if fonte["estado"] is not None:
            return
        op = self.tipo_de(fonte)
        dest = self.nucleo.camada(op[2])
        lyr = fonte["lyr"]
        colunas = [f.name() for f in lyr.fields()]
        exemplo = next(lyr.getFeatures(), None)
        campos = [c for c in campos_do(dest) if c not in op[3]]  # o tipo escolhido não se mapeia
        t = QTableWidget(len(campos), 4)
        t.setHorizontalHeaderLabels(["Campo do GWATER", "Coluna do arquivo", "Valor fixo", "Exemplo"])
        h = t.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        t.verticalHeader().setVisible(False)
        combos, fixos = {}, {}
        for r, campo in enumerate(campos):
            it = QTableWidgetItem(f"{campo}\n{DESCRICAO.get(campo, '')}")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            t.setItem(r, 0, it)
            cb = QComboBox()
            cb.addItem("(não importar)", None)
            for c in colunas:
                cb.addItem(c, c)
            sug = sugerir_coluna(campo, colunas)
            if sug:
                cb.setCurrentIndex(colunas.index(sug) + 1)

            def exemplo_de(_=0, rr=r, cc=cb):
                col = cc.currentData()
                val = exemplo[col] if (col and exemplo is not None) else ""
                e = QTableWidgetItem("" if _vazio(val) else str(val))
                e.setFlags(Qt.ItemFlag.ItemIsEnabled)
                t.setItem(rr, 3, e)
            cb.currentIndexChanged.connect(exemplo_de)
            t.setCellWidget(r, 1, cb)
            fx = QLineEdit()
            fx.setPlaceholderText("—")
            dom = dominio(dest, campo)
            if dom:
                fx.setToolTip("Valores aceitos: " + ", ".join(map(str, dom)))
            t.setCellWidget(r, 2, fx)
            combos[campo], fixos[campo] = cb, fx
            exemplo_de()
        t.resizeRowsToContents()
        fonte["estado"] = {"tabela": t, "combos": combos, "fixos": fixos, "dest": dest, "trad": {}, "valores": None}

    def mapa(self, fonte):
        return {c: cb.currentData() for c, cb in fonte["estado"]["combos"].items() if cb.currentData()}

    # ================================================================ 3 · valores
    def _pagina_valores(self):
        w = QWidget()
        v = QVBoxLayout(w)
        txt = QLabel("Para os campos de lista (material, status, tipo da válvula...), diga o que cada valor do arquivo "
                     "significa no cadastro. Valores sem correspondência ficam vazios (e usam o valor fixo, se houver).")
        txt.setWordWrap(True)
        txt.setStyleSheet(f"color:{COR['muted']}")
        v.addWidget(txt)
        sp = QSplitter()
        self.lista_val = QListWidget()
        self.lista_val.setIconSize(QSize(18, 18))
        self.lista_val.currentRowChanged.connect(lambda i: 0 <= i < self.pilha_val.count() and self.pilha_val.setCurrentIndex(i))
        sp.addWidget(self.lista_val)
        self.pilha_val = QStackedWidget()
        sp.addWidget(self.pilha_val)
        sp.setSizes([260, 740])
        v.addWidget(sp, 1)
        return w

    def _montar_valores(self, validas):
        while self.pilha_val.count():
            self.pilha_val.removeWidget(self.pilha_val.widget(0))
        for f in validas:
            est = f["estado"]
            assinatura = tuple(sorted(self.mapa(f).items()))
            if est["valores"] is None or est.get("assinatura") != assinatura:
                est["assinatura"] = assinatura
                caixa = QWidget()
                lay = QVBoxLayout(caixa)
                est["trad"] = {}
                for campo, col in self.mapa(f).items():
                    dom = dominio(est["dest"], campo)
                    if not dom:
                        continue
                    idx = f["lyr"].fields().indexOf(col)
                    distintos = sorted({str(x) for x in f["lyr"].uniqueValues(idx, 300) if not _vazio(x)})
                    if not distintos:
                        continue
                    lay.addWidget(QLabel(f"<b>{campo}</b> ← coluna {col}"))
                    t = QTableWidget(len(distintos), 2)
                    t.setHorizontalHeaderLabels(["Valor no arquivo", "Valor no cadastro"])
                    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                    t.verticalHeader().setVisible(False)
                    est["trad"][campo] = {}
                    for r, val in enumerate(distintos):
                        it = QTableWidgetItem(val)
                        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                        t.setItem(r, 0, it)
                        cb = QComboBox()
                        cb.addItem("(vazio)", None)
                        for d in dom:
                            cb.addItem(str(d), d)
                        sug = sugerir_valor(val, dom)
                        if sug is not None:
                            cb.setCurrentIndex(dom.index(sug) + 1)
                        t.setCellWidget(r, 1, cb)
                        est["trad"][campo][val] = cb
                    t.setMinimumHeight(min(320, 34 + 30 * len(distintos)))
                    lay.addWidget(t)
                if not est["trad"]:
                    lb = QLabel("Nenhuma coluna ligada a um campo de lista neste arquivo.")
                    lb.setStyleSheet(f"color:{COR['muted']}")
                    lay.addWidget(lb)
                lay.addStretch(1)
                rolar = QScrollArea()
                rolar.setWidgetResizable(True)
                rolar.setWidget(caixa)
                est["valores"] = rolar
            self.pilha_val.addWidget(est["valores"])

    # ================================================================ 4 · opções
    def _pagina_opcoes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        self.tol = QDoubleSpinBox()
        self.tol.setRange(0.0, 100.0)
        self.tol.setDecimals(2)
        self.tol.setValue(0.5)
        self.tol.setSuffix(" m")
        self.tol.setMaximumWidth(160)
        self.tol.setToolTip("Pontas e elementos mais próximos que isso são ligados no mesmo nó")
        form.addRow("Tolerância de ligação:", self.tol)
        self.situacao = QComboBox()
        self.situacao.addItems(["EXISTENTE", "PROJETADO"])
        self.situacao.setMaximumWidth(160)
        form.addRow("Situação padrão:", self.situacao)
        v.addLayout(form)
        self.criar_nos = QCheckBox("Criar nós nas pontas das tubulações (pontas a menos da tolerância viram o mesmo nó; "
                                   "ponta perto de um elemento liga nele)")
        self.dividir_t = QCheckBox("Dividir ligações em “T” (ponta que encosta no meio de outra tubulação a divide)")
        self.dividir_tubos = QCheckBox("Dividir a tubulação onde um elemento pontual (válvula, bomba, hidrante...) cair "
                                       "no meio dela: o elemento fica entre os dois pedaços")
        self.substituir = QCheckBox("Substituir o nó do cadastro que estiver no mesmo lugar de um elemento importado")
        for c in (self.criar_nos, self.dividir_t, self.dividir_tubos, self.substituir):
            c.setChecked(True)
            v.addWidget(c)
        self.existentes = QComboBox()
        self.existentes.addItem("Atualizar os dados deles (sincronizar)", "atualizar")
        self.existentes.addItem("Atualizar os dados e a posição", "mover")
        self.existentes.addItem("Criar de novo, com outro código", "criar")
        self.existentes.setToolTip("Synchronize do WaterGEMS: o elemento do arquivo com o mesmo código (campo ligado "
                                   "ao id) de um que já está no cadastro é atualizado, não duplicado")
        form2 = QFormLayout()
        form2.addRow("Elementos que já existem (mesmo código):", self.existentes)
        v.addLayout(form2)
        self.resumo = QTableWidget(0, 3)
        self.resumo.setHorizontalHeaderLabels(["Arquivo", "Importar como", "Campos ligados"])
        self.resumo.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.resumo.verticalHeader().setVisible(False)
        v.addWidget(self.resumo, 1)
        aviso = QLabel("Tudo fica na edição: confira no mapa e use <b>Salvar edições</b>. <b>Ctrl+Z</b> desfaz a "
                       "importação.")
        aviso.setStyleSheet(f"color:{COR['muted']}")
        v.addWidget(aviso)
        return w

    def _resumo(self):
        validas = [f for f in self.fontes if f["geo"] in GEOS]
        self.resumo.setRowCount(len(validas))
        for i, f in enumerate(validas):
            self._garantir_estado(f)
            op = self.tipo_de(f)
            self.resumo.setItem(i, 0, QTableWidgetItem(f"{f['nome']} ({f['lyr'].featureCount()})"))
            it = QTableWidgetItem(icone(op[4]), op[1])
            self.resumo.setItem(i, 1, it)
            self.resumo.setItem(i, 2, QTableWidgetItem(", ".join(f"{c} ← {col}" for c, col in self.mapa(f).items())
                                                       or "nenhum"))
        self.resumo.resizeColumnsToContents()

    # ================================================================ importar
    def trabalhos(self):
        out = []
        for f in self.fontes:
            if f["geo"] not in GEOS:
                continue
            self._garantir_estado(f)
            op = self.tipo_de(f)
            est = f["estado"]
            out.append({"nome": f["nome"], "camada": op[2], "fixos_tipo": dict(op[3]), "origem": f["lyr"],
                        "mapa": self.mapa(f), "fixos": {c: fx.text() for c, fx in est["fixos"].items() if fx.text().strip()},
                        "traducoes": {c: {v: cb.currentData() for v, cb in d.items()} for c, d in est["trad"].items()},
                        "so_sel": f["so_sel"].isChecked()})
        return out

    def _executar(self):
        from .importador import Cancelado, importar_lote
        trabalhos = self.trabalhos()
        total = sum((t["origem"].selectedFeatureCount() if t["so_sel"] else t["origem"].featureCount()) for t in trabalhos)
        prog = QProgressDialog("Importando…", "Cancelar", 0, max(total, 1), self)
        prog.setWindowTitle("GWATER · ModelBuilder")
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.setMinimumDuration(0)
        prog.setMinimumWidth(460)
        prog.show()
        try:
            atualizados = {}
            if self.existentes.currentData() != "criar":
                from .importador import sincronizar
                prog.setLabelText("Atualizando os elementos que já existem…")
                atualizados = sincronizar(self.nucleo, trabalhos, mover=self.existentes.currentData() == "mover")
            self.resultado = importar_lote(self.nucleo, trabalhos, {
                "tolerancia": self.tol.value(), "situacao": self.situacao.currentText(),
                "criar_nos": self.criar_nos.isChecked(), "dividir_t": self.dividir_t.isChecked(),
                "dividir_tubos": self.dividir_tubos.isChecked(), "substituir_nos": self.substituir.isChecked()}, prog)
            self.resultado["atualizados"] = atualizados
        except Cancelado:
            prog.close()
            return self._erro("Importação cancelada (nada foi gravado no cadastro).")
        except Exception as e:
            prog.close()
            import traceback
            traceback.print_exc()
            return self._erro(f"Falhou: {e}")
        prog.close()
        self.accept()


def abrir(nucleo):
    if not nucleo._cadastro_ok():
        return
    j = ModelBuilderApp(nucleo.janela, nucleo)
    if not j.exec() or not j.resultado:
        return
    r = j.resultado
    nucleo.mostrar_dock()
    nucleo.dock.mostrar_problemas([{"nivel": "AVISO", "camada": None, "id": None, "msg": a} for a in r["avisos"]])
    partes = ", ".join(f"{n}: {q}" for n, q in r["por_tipo"].items())
    msg = (f"ModelBuilder: {r['importados']} elemento(s) importado(s) ({partes}); {r['nos_criados']} nó(s) criado(s), "
           f"{r['ligados_existentes']} ponta(s) ligada(s) a elementos, {r['divididas']} divisão(ões).")
    if r.get("atualizados"):
        msg += " Atualizados (já existiam): " + ", ".join(f"{c}: {q}" for c, q in r["atualizados"].items()) + "."
    nucleo.dock.status.setText(msg + " Confira no mapa e clique em <b>Salvar edições</b> (Ctrl+Z desfaz).")
    nucleo.informar(msg)
    nucleo.janela.dock_arvore.recontar()
    nucleo.janela.zoom_total()


ACOES = {"modelbuilder": abrir}
