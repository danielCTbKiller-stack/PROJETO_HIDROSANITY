"""Tabelas (FlexTables do WaterGEMS): uma tabela por tipo de elemento, com os campos do cadastro
(editáveis) e as colunas de resultado da hora escolhida e do dia.

Filtro: todos, só os selecionados no mapa ou uma condição. Colunas: escolha quais mostrar. Rodapé:
soma, média, mínimo e máximo da coluna clicada. Selecionar linhas seleciona no mapa (e vice-versa).
"""
from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils, QgsFeatureRequest, QgsVectorLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .util import NOMES, PONTOS, ligar, num

# colunas de resultado por tipo: (cabeçalho, função(res, id, k) -> valor)
def _no(d, eid):
    return d["nos"].get(eid)


def _lk(d, eid):
    return d["links"].get(eid)


def _min(s):
    return min(s) if s else None


RESULTADOS = {
    "trecho": [("Vazão (L/s)", lambda d, e, k: _lk(d, e) and _lk(d, e)["q"][k]),
               ("Velocidade (m/s)", lambda d, e, k: _lk(d, e) and abs(_lk(d, e)["v"][k])),
               ("Perda (m/km)", lambda d, e, k: _lk(d, e) and abs(_lk(d, e)["hl"][k])),
               ("Vel. máx dia (m/s)", lambda d, e, k: _lk(d, e) and max(abs(x) for x in _lk(d, e)["v"])),
               ("Vazão máx dia (L/s)", lambda d, e, k: _lk(d, e) and max(abs(x) for x in _lk(d, e)["q"]))],
    "no_juncao": [("Pressão (mca)", lambda d, e, k: _no(d, e) and _no(d, e)["p"][k]),
                  ("Carga (m)", lambda d, e, k: _no(d, e) and _no(d, e)["h"][k]),
                  ("Demanda (L/s)", lambda d, e, k: _no(d, e) and _no(d, e)["d"][k]),
                  ("Pressão mín dia", lambda d, e, k: _no(d, e) and min(_no(d, e)["p"])),
                  ("Pressão máx dia", lambda d, e, k: _no(d, e) and max(_no(d, e)["p"]))],
    "reservatorio": [("Nível (m)", lambda d, e, k: _no(d, e) and _no(d, e)["p"][k]),
                     ("Cota da água (m)", lambda d, e, k: _no(d, e) and _no(d, e)["h"][k]),
                     ("Nível mín dia", lambda d, e, k: _no(d, e) and min(_no(d, e)["p"])),
                     ("Nível máx dia", lambda d, e, k: _no(d, e) and max(_no(d, e)["p"]))],
    "captacao": [("Vazão fornecida (L/s)", lambda d, e, k: _no(d, e) and -_no(d, e)["d"][k]),
                 ("Carga (m)", lambda d, e, k: _no(d, e) and _no(d, e)["h"][k])],
    "bomba": [("Vazão (L/s)", lambda d, e, k: _lk(d, e) and _lk(d, e)["q"][k]),
              ("Estado", lambda d, e, k: _lk(d, e) and ("LIGADA" if _lk(d, e)["s"][k] else "DESLIGADA")),
              ("Altura (m)", lambda d, e, k: _no(d, f"{e}__J") and _no(d, f"{e}__J")["h"][k] - _no(d, f"{e}__M")["h"][k]),
              ("Pressão sucção (mca)", lambda d, e, k: _no(d, f"{e}__M") and _no(d, f"{e}__M")["p"][k]),
              ("Pressão recalque (mca)", lambda d, e, k: _no(d, f"{e}__J") and _no(d, f"{e}__J")["p"][k]),
              ("Horas ligada", lambda d, e, k: _lk(d, e) and round(sum(1 for s in _lk(d, e)["s"] if s) *
                                                                   24 / max(len(_lk(d, e)["s"]) - 1, 1), 2))],
    "valvula": [("Vazão (L/s)", lambda d, e, k: _lk(d, e) and _lk(d, e)["q"][k]),
                ("Estado", lambda d, e, k: _lk(d, e) and {0: "FECHADA", 1: "ABERTA", 2: "ATIVA"}.get(_lk(d, e)["s"][k])),
                ("Pressão montante (mca)", lambda d, e, k: _no(d, f"{e}__M") and _no(d, f"{e}__M")["p"][k]),
                ("Pressão jusante (mca)", lambda d, e, k: _no(d, f"{e}__J") and _no(d, f"{e}__J")["p"][k])],
}


class TabelaFlex(QWidget):
    def __init__(self, nucleo, camada=None, lyr=None):
        super().__init__()
        self.nucleo, self.janela = nucleo, nucleo.janela
        self.lyr_fixa = lyr
        self.ocultas = {}
        self.fids = []
        self._mexendo = False
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.tipo = QComboBox()
        if lyr is None:
            for c in ("trecho",) + PONTOS:
                try:
                    nucleo.camada(c)
                    self.tipo.addItem(NOMES[c], c)
                except LookupError:
                    pass
            if camada:
                self.tipo.setCurrentIndex(max(0, self.tipo.findData(camada)))
        else:
            self.tipo.addItem(lyr.name(), None)
            self.tipo.setEnabled(False)
        topo.addWidget(QLabel("Tabela:"))
        topo.addWidget(self.tipo)
        self.filtro = QComboBox()
        self.filtro.addItems(["Todos", "Só os selecionados no mapa", "Condição…"])
        self.expr = ""
        topo.addWidget(QLabel("Mostrar:"))
        topo.addWidget(self.filtro)
        b_col = QPushButton("Colunas…")
        b_col.clicked.connect(self._colunas)
        topo.addWidget(b_col)
        self.sync = QCheckBox("Seleção sincronizada com o mapa")
        self.sync.setChecked(True)
        topo.addWidget(self.sync)
        topo.addStretch(1)
        self.b_editar = QPushButton("Editar")
        self.b_editar.setToolTip("Liga a edição: as células do cadastro ficam editáveis (resultados são só leitura)")
        self.b_editar.clicked.connect(self._editar)
        topo.addWidget(self.b_editar)
        b = QPushButton("Atualizar")
        b.clicked.connect(self.carregar)
        topo.addWidget(b)
        v.addLayout(topo)
        self.t = QTableWidget()
        self.t.setAlternatingRowColors(True)
        # células (não linhas): dá para selecionar uma coluna inteira e colar nela; a linha inteira é pelo número
        self.t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.t.verticalHeader().setDefaultSectionSize(22)
        self.t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.t.setSortingEnabled(True)
        self.t.itemChanged.connect(self._mudou)
        self.t.itemSelectionChanged.connect(self._selecao_tabela)
        self.t.horizontalHeader().sectionClicked.connect(self._estatistica)  # o clique também seleciona a coluna
        self.t.cellDoubleClicked.connect(self._ir)
        v.addWidget(self.t, 1)
        baixo = QHBoxLayout()
        self.est = QLabel("Clique no título de uma coluna para ver soma, média, mínimo e máximo.")
        self.est.setStyleSheet(f"color:{COR['muted']}")
        baixo.addWidget(self.est, 1)
        for texto, f, dica in (
                ("Selecionar coluna", self._selecionar_coluna, "Seleciona a coluna inteira da célula atual (ou clique "
                 "no título da coluna). Depois, Ctrl+V cola em todas as linhas dela."),
                ("Edição global…", self._edicao_global, "Muda uma coluna inteira de uma vez (Global Edit do WaterGEMS): "
                 "definir, somar, multiplicar… nas linhas selecionadas ou em todas."),
                ("Zoom nos selecionados", self._zoom, ""), ("Copiar", self._copiar, "Copia as células (Ctrl+C)"),
                ("Exportar CSV…", self._exportar, "")):
            b = QPushButton(texto)
            b.setToolTip(dica)
            b.clicked.connect(f)
            baixo.addWidget(b)
        from qgis.PyQt.QtGui import QKeySequence, QShortcut
        for tecla, f in ((QKeySequence.StandardKey.Paste, self._colar), (QKeySequence.StandardKey.Copy, self._copiar)):
            atalho = QShortcut(tecla, self.t)
            atalho.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            atalho.activated.connect(f)
        v.addLayout(baixo)
        self.tipo.currentIndexChanged.connect(self.carregar)
        self.filtro.activated.connect(self._filtro)
        ligar(self.janela.resultados, self, lambda *_: self.carregar())
        ligar(nucleo.dock.hora_lenta, self, lambda _k: self._resultados())
        ligar(self.janela.selecao, self, lambda *_: self._selecao_mapa())
        self.carregar()

    # ------------------------------------------------
    def camada_nome(self):
        return self.tipo.currentData()

    def lyr(self):
        return self.lyr_fixa or self.nucleo.camada(self.camada_nome())

    def _filtro(self, i):
        if i == 2:
            expr, ok = QInputDialog.getText(self, "Condição", "Mostrar só os elementos onde (ex.: \"diametro_nominal\" "
                                            "< 100):", text=self.expr)
            if not ok:
                return
            self.expr = expr
        self.carregar()

    def _colunas(self):
        lyr = self.lyr()
        todas = [f.name() for f in lyr.fields()] + [c for c, _ in RESULTADOS.get(self.camada_nome(), [])]
        oc = self.ocultas.setdefault(self.camada_nome(), set())
        d = QDialog(self)
        d.setWindowTitle("Colunas")
        v = QVBoxLayout(d)
        lista = QListWidget()
        for c in todas:
            it = QListWidgetItem(c)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if c in oc else Qt.CheckState.Checked)
            lista.addItem(it)
        v.addWidget(lista)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec():
            oc.clear()
            oc.update(lista.item(i).text() for i in range(lista.count())
                      if lista.item(i).checkState() != Qt.CheckState.Checked)
            self.carregar()

    def carregar(self):
        try:
            lyr = self.lyr()
        except LookupError:
            return
        oc = self.ocultas.get(self.camada_nome(), {"fid"})
        self.campos = [f.name() for f in lyr.fields() if f.name() not in oc]
        self.res_cols = [(c, fn) for c, fn in RESULTADOS.get(self.camada_nome(), []) if c not in oc] \
            if self.nucleo.res and self.lyr_fixa is None else []
        req = QgsFeatureRequest()
        if self.filtro.currentIndex() == 1:
            req.setFilterFids(lyr.selectedFeatureIds())
        elif self.filtro.currentIndex() == 2 and self.expr:
            req.setFilterExpression(self.expr)
        feats = list(lyr.getFeatures(req))
        self._mexendo = True
        self.t.setSortingEnabled(False)
        self.t.clear()
        self.t.setColumnCount(len(self.campos) + len(self.res_cols))
        self.t.setRowCount(len(feats))
        self.t.setHorizontalHeaderLabels(self.campos + [c for c, _ in self.res_cols])
        for j in range(len(self.campos), len(self.campos) + len(self.res_cols)):
            self.t.horizontalHeaderItem(j).setForeground(QColor(COR["cyan"]))
        self.fids = []
        editavel = lyr.isEditable()
        self.t.setUpdatesEnabled(False)
        modelo = QTableWidgetItem()  # copiar um item pronto é mais rápido que montar flags e alinhamento em cada um
        so_ler = modelo.flags() & ~Qt.ItemFlag.ItemIsEditable
        num_ed, txt_ed = QTableWidgetItem(), QTableWidgetItem()
        num_ed.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        num_ro, txt_ro = num_ed.clone(), txt_ed.clone()
        num_ro.setFlags(so_ler)
        txt_ro.setFlags(so_ler)
        idx = [lyr.fields().indexOf(c) for c in self.campos]
        papel_d, papel_u = Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.UserRole
        for i, f in enumerate(feats):
            fid = f.id()
            self.fids.append(fid)
            attrs = f.attributes()
            for j, c in enumerate(self.campos):
                v = attrs[idx[j]]
                ro = not editavel or c == "fid"
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it = (num_ro if ro else num_ed).clone()
                    it.setData(papel_d, v)
                else:
                    it = (txt_ro if ro else txt_ed).clone()
                    it.setText("" if v is None or str(v) == "NULL" else str(v))
                it.setData(papel_u, fid)
                self.t.setItem(i, j, it)
        self.t.setSortingEnabled(True)
        self._resultados()
        self.t.horizontalHeader().setResizeContentsPrecision(300)  # largura pelas primeiras linhas
        self.t.resizeColumnsToContents()
        self.t.setUpdatesEnabled(True)
        for j in range(self.t.columnCount()):
            self.t.setColumnWidth(j, min(self.t.columnWidth(j) + 14, 260))
        self._mexendo = False
        self.b_editar.setText("Edição ligada" if editavel else "Editar")
        self.b_editar.setEnabled(not editavel)
        self._selecao_mapa()

    def _resultados(self):
        res = self.nucleo.res
        if not res or not self.res_cols:
            return
        k = self.janela.passo()
        lyr = self.lyr()
        ids = {f.id(): str(f["id"]) for f in lyr.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(["id"], lyr.fields()))}
        self._mexendo = True
        self.t.setSortingEnabled(False)
        base = len(self.campos)
        for i in range(self.t.rowCount()):
            fid = self.t.item(i, 0).data(Qt.ItemDataRole.UserRole) if self.t.item(i, 0) else None
            eid = ids.get(fid)
            for j, (_, fn) in enumerate(self.res_cols):
                try:
                    v = fn(res.d, eid, k) if eid else None
                except (KeyError, IndexError, TypeError):
                    v = None
                it = QTableWidgetItem()
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    it.setData(Qt.ItemDataRole.DisplayRole, round(float(v), 3))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    it.setText("" if v is None else str(v))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setForeground(QColor(COR["cyan"]))
                it.setData(Qt.ItemDataRole.UserRole, fid)
                self.t.setItem(i, base + j, it)
        self.t.setSortingEnabled(True)
        self._mexendo = False

    # ------------------------------------------------ edição e seleção
    def _editar(self):
        lyr = self.lyr()
        if not lyr.isEditable():
            lyr.startEditing()
        self.carregar()

    def _mudou(self, it):
        if self._mexendo or it.column() >= len(self.campos):
            return
        lyr = self.lyr()
        if not lyr.isEditable():
            return
        campo = self.campos[it.column()]
        i = lyr.fields().indexOf(campo)
        try:
            v = self._converter(lyr.fields()[i], it.text())
        except ValueError:
            self.nucleo.aviso(f"'{it.text()}' não é um número válido para {campo}.")
            return
        lyr.changeAttributeValue(it.data(Qt.ItemDataRole.UserRole), i, v)
        self.janela.canvas.refresh()

    @staticmethod
    def _converter(fld, txt):
        """Texto da célula → valor do campo (vírgula decimal aceita). ValueError se não for número."""
        txt = "" if txt is None else str(txt).strip()
        if txt == "":
            return None
        if not fld.isNumeric():
            return txt
        v = float(txt.replace(".", "").replace(",", ".") if txt.count(",") == 1 and "." in txt else txt.replace(",", "."))
        return int(round(v)) if fld.type() in (2, 4) else v

    def _gravar(self, mudancas, titulo):
        """mudancas: [(linha, coluna, texto)]. Grava no cadastro num só Ctrl+Z e atualiza as células."""
        lyr = self.lyr()
        if "id" in self.campos:  # o código é a identidade do elemento: não pode repetir
            c_id = self.campos.index("id")
            novos = [str(txt).strip() for r, c, txt in mudancas if c == c_id]
            if novos:
                mudando = {r for r, c, _ in mudancas if c == c_id}
                outros = {self.t.item(r, c_id).text() for r in range(self.t.rowCount())
                          if r not in mudando and self.t.item(r, c_id)}
                rep = sorted({v for v in novos if not v or novos.count(v) > 1 or v in outros})
                if rep:
                    self.nucleo.aviso("A coluna id não pode ter códigos repetidos ou vazios: "
                                      f"{', '.join(repr(v) for v in rep[:5])}. Nada foi alterado. Para renumerar "
                                      "use Ferramentas > Centro de códigos.")
                    return
        ja_editava = lyr.isEditable()
        if not ja_editava:
            lyr.startEditing()
        erros, feitos = [], 0
        self._mexendo = True
        self.t.setSortingEnabled(False)
        lyr.beginEditCommand(titulo)
        try:
            for r, c, txt in mudancas:
                if c >= len(self.campos) or self.campos[c] == "fid" or not self.t.item(r, c):
                    continue
                i = lyr.fields().indexOf(self.campos[c])
                try:
                    v = self._converter(lyr.fields()[i], txt)
                except ValueError:
                    erros.append(str(txt))
                    continue
                lyr.changeAttributeValue(self.t.item(r, c).data(Qt.ItemDataRole.UserRole), i, v)
                it = self.t.item(r, c)
                if isinstance(v, (int, float)):
                    it.setData(Qt.ItemDataRole.DisplayRole, v)
                else:
                    it.setText("" if v is None else str(v))
                feitos += 1
        finally:
            lyr.endEditCommand()
            self.t.setSortingEnabled(True)
            self._mexendo = False
        self.janela.canvas.refresh()
        msg = f"{feitos} célula(s) alterada(s) em {titulo.lower()}."
        if erros:
            msg += f" {len(erros)} valor(es) não numérico(s) ignorado(s): {', '.join(erros[:4])}."
        self.est.setText(msg + " Ctrl+Z desfaz; Salvar edições grava.")
        if not ja_editava:  # a edição acabou de ser ligada: as células passam a ser editáveis
            self.carregar()

    def _selecionar_coluna(self):
        c = self.t.currentColumn()
        if c < 0:
            return self.nucleo.aviso("Clique numa célula da coluna (ou no título dela) primeiro.")
        self.t.selectColumn(c)

    def _colar(self):
        """Ctrl+V: um valor só vai para todas as células selecionadas (a coluna inteira, se ela estiver
        selecionada); várias linhas/colunas copiadas do Excel colam a partir da célula atual, para baixo."""
        from qgis.PyQt.QtWidgets import QApplication
        txt = QApplication.clipboard().text()
        if not txt:
            return
        linhas = [l.split("\t") for l in txt.rstrip("\r\n").replace("\r\n", "\n").split("\n")]
        sel = self.t.selectedIndexes()
        if len(linhas) == 1 and len(linhas[0]) == 1:
            alvo = sel or ([self.t.model().index(self.t.currentRow(), self.t.currentColumn())]
                           if self.t.currentRow() >= 0 else [])
            mud = [(i.row(), i.column(), linhas[0][0]) for i in alvo]
        else:
            r0 = min((i.row() for i in sel), default=self.t.currentRow())
            c0 = min((i.column() for i in sel), default=self.t.currentColumn())
            if r0 < 0 or c0 < 0:
                return
            cols_inteiras = {c.column() for c in self.t.selectionModel().selectedColumns()}
            if cols_inteiras and all(len(l) == 1 for l in linhas) and len(linhas) < self.t.rowCount():
                # uma coluna do Excel colada numa coluna inteira: repete a lista até o fim
                mud = [(r, c, linhas[r % len(linhas)][0]) for c in sorted(cols_inteiras)
                       for r in range(self.t.rowCount())]
            else:
                mud = [(r0 + a, c0 + b, v) for a, lin in enumerate(linhas) for b, v in enumerate(lin)
                       if r0 + a < self.t.rowCount()]
        if not mud:
            return
        if any(c >= len(self.campos) for _, c, _ in mud):
            self.nucleo.aviso("As colunas de resultado (em ciano) são só leitura: a colagem nelas foi ignorada.")
        self._gravar(mud, "Colar")

    def _edicao_global(self):
        """Global Edit: uma operação numa coluna, nas linhas selecionadas ou em todas as da tabela."""
        from qgis.PyQt.QtWidgets import QFormLayout, QLineEdit
        lyr = self.lyr()
        editaveis = [c for c in self.campos if c != "fid"]
        if not editaveis:
            return
        d = QDialog(self)
        d.setWindowTitle("Edição global")
        f = QFormLayout(d)
        col = QComboBox()
        col.addItems(editaveis)
        atual = self.t.currentColumn()
        if 0 <= atual < len(self.campos) and self.campos[atual] in editaveis:
            col.setCurrentText(self.campos[atual])
        op = QComboBox()
        valor = QLineEdit()
        valor.setPlaceholderText("valor (use vírgula ou ponto)")

        def ops():
            num = lyr.fields()[lyr.fields().indexOf(col.currentText())].isNumeric()
            op.clear()
            op.addItems(["Definir", "Somar", "Subtrair", "Multiplicar", "Dividir", "Arredondar (casas)", "Limpar"]
                        if num else ["Definir", "Acrescentar no fim", "Acrescentar no início", "Substituir texto…",
                                     "Limpar"])
        col.currentIndexChanged.connect(lambda _: ops())
        ops()
        linhas_sel = sorted({i.row() for i in self.t.selectedIndexes()})
        escopo = QComboBox()
        escopo.addItem(f"Todas as linhas da tabela ({self.t.rowCount()})", "todas")
        if linhas_sel and len(linhas_sel) < self.t.rowCount():
            escopo.addItem(f"Só as linhas selecionadas ({len(linhas_sel)})", "sel")
            escopo.setCurrentIndex(1)
        f.addRow("Coluna:", col)
        f.addRow("Operação:", op)
        f.addRow("Valor:", valor)
        f.addRow("Aplicar em:", escopo)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if not d.exec():
            return
        c = self.campos.index(col.currentText())
        linhas = linhas_sel if escopo.currentData() == "sel" else range(self.t.rowCount())
        o, val = op.currentText(), valor.text().strip()
        de = para = ""
        if o == "Substituir texto…":
            de, ok = QInputDialog.getText(self, "Substituir", "Trocar o texto:")
            if not ok:
                return
            para = val
        try:
            n = float(val.replace(",", ".")) if o in ("Somar", "Subtrair", "Multiplicar", "Dividir",
                                                      "Arredondar (casas)") else None
        except ValueError:
            return self.nucleo.aviso(f"'{val}' não é um número.")
        if o == "Dividir" and n == 0:
            return self.nucleo.aviso("Divisão por zero.")
        mud = []
        for r in linhas:
            it = self.t.item(r, c)
            if not it:
                continue
            atual_v = it.data(Qt.ItemDataRole.DisplayRole)
            atual_t = it.text()
            if o == "Definir":
                novo = val
            elif o == "Limpar":
                novo = ""
            elif n is not None:
                if not isinstance(atual_v, (int, float)):
                    continue
                novo = {"Somar": lambda x: x + n, "Subtrair": lambda x: x - n, "Multiplicar": lambda x: x * n,
                        "Dividir": lambda x: x / n, "Arredondar (casas)": lambda x: round(x, int(n))}[o](atual_v)
                novo = repr(round(novo, 10))
            elif o == "Acrescentar no fim":
                novo = atual_t + val
            elif o == "Acrescentar no início":
                novo = val + atual_t
            else:
                novo = atual_t.replace(de, para)
            mud.append((r, c, novo))
        self._gravar(mud, f"Edição global de {col.currentText()}")

    def _selecao_tabela(self):
        if self._mexendo or not self.sync.isChecked():
            return
        if self.t.selectionModel().selectedColumns():  # coluna inteira: é para editar, não para selecionar no mapa
            return
        fids = {self.t.item(i.row(), 0).data(Qt.ItemDataRole.UserRole) for i in self.t.selectedIndexes()
                if self.t.item(i.row(), 0)}
        self._mexendo = True
        try:  # a seleção volta para a tabela pelo sinal da janela: ignorada, senão a célula atual pula de coluna
            self.lyr().selectByIds(list(fids))
            self.janela._selecao_mudou()
        finally:
            self._mexendo = False

    def _selecao_mapa(self):
        if self._mexendo or not self.sync.isChecked():
            return
        try:
            sel = set(self.lyr().selectedFeatureIds())
        except LookupError:
            return
        self._mexendo = True
        atual = self.t.currentIndex()
        self.t.clearSelection()
        modo = self.t.selectionMode()
        self.t.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        if self.t.selectionModel().selectedColumns():
            self.t.setSelectionMode(modo)
            self._mexendo = False
            return
        for i in range(self.t.rowCount()):
            it = self.t.item(i, 0)
            if it and it.data(Qt.ItemDataRole.UserRole) in sel:
                self.t.selectRow(i)
        self.t.setSelectionMode(modo)
        if atual.isValid():  # selecionar as linhas não muda a célula em que o usuário está
            self.t.selectionModel().setCurrentIndex(atual, self.t.selectionModel().SelectionFlag.NoUpdate)
        self._mexendo = False

    def _ir(self, i, _j):
        it = self.t.item(i, 0)
        if it:
            lyr = self.lyr()
            lyr.selectByIds([it.data(Qt.ItemDataRole.UserRole)])
            self._zoom()

    def _zoom(self):
        from .vistas import zoom_selecao
        self.janela.mostrar_mapa()
        zoom_selecao(self.nucleo)

    def _estatistica(self, j):
        vals = []
        for i in range(self.t.rowCount()):
            it = self.t.item(i, j)
            v = it.data(Qt.ItemDataRole.DisplayRole) if it else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(float(v))
        nome = self.t.horizontalHeaderItem(j).text()
        if not vals:
            self.est.setText(f"{nome}: sem valores numéricos.")
            return
        self.est.setText(f"<b>{nome}</b> · n {len(vals)} · soma <b>{num(sum(vals))}</b> · média "
                         f"<b>{num(sum(vals) / len(vals))}</b> · mín <b>{num(min(vals))}</b> · máx <b>{num(max(vals))}</b>")

    def _copiar(self):
        from qgis.PyQt.QtWidgets import QApplication
        sel = self.t.selectedIndexes()
        linhas = sorted({i.row() for i in sel}) or list(range(self.t.rowCount()))
        cols = sorted({i.column() for i in sel}) or list(range(self.t.columnCount()))
        cel = lambda i, j: self.t.item(i, j).text() if self.t.item(i, j) else ""  # noqa: E731
        txt = ["\t".join(cel(i, j) for j in cols) for i in linhas]
        if len(cols) > 1 or not sel:  # mais de uma coluna: vai com o cabeçalho, para colar no Excel
            txt.insert(0, "\t".join(self.t.horizontalHeaderItem(j).text() for j in cols))
        QApplication.clipboard().setText("\n".join(txt))

    def _exportar(self):
        import csv
        from qgis.PyQt.QtWidgets import QFileDialog
        arq, _ = QFileDialog.getSaveFileName(self, "Exportar tabela", f"{self.tipo.currentText()}.csv", "CSV (*.csv)")
        if not arq:
            return
        with open(arq, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([self.t.horizontalHeaderItem(j).text() for j in range(self.t.columnCount())])
            for i in range(self.t.rowCount()):
                lin = []
                for j in range(self.t.columnCount()):
                    it = self.t.item(i, j)
                    v = it.data(Qt.ItemDataRole.DisplayRole) if it else ""
                    lin.append(str(v).replace(".", ",") if isinstance(v, float) else (it.text() if it else ""))
                w.writerow(lin)
        self.nucleo.informar(f"Tabela exportada: {arq}")


def abrir_tabela(nucleo, lyr=None, camada=None):
    if not nucleo.cadastro() and lyr is None:
        return nucleo.aviso("Abra um cadastro primeiro.")
    w = TabelaFlex(nucleo, camada, lyr if lyr not in nucleo.camadas_rede() else None)
    if lyr in nucleo.camadas_rede():
        for c in NOMES:
            try:
                if nucleo.camada(c) == lyr:
                    w.tipo.setCurrentIndex(w.tipo.findData(c))
            except LookupError:
                pass
    titulo = f"Tabela · {w.tipo.currentText()}"
    nucleo.janela.abrir_aba(w, titulo, "tabelas")
    return w


ACOES = {"tabelas": lambda n: abrir_tabela(n),
         "tabela_trecho": lambda n: abrir_tabela(n, camada="trecho"),
         "tabela_no_juncao": lambda n: abrir_tabela(n, camada="no_juncao"),
         "tabela_bomba": lambda n: abrir_tabela(n, camada="bomba"),
         "tabela_valvula": lambda n: abrir_tabela(n, camada="valvula"),
         "tabela_reservatorio": lambda n: abrir_tabela(n, camada="reservatorio")}
