"""Janela Faixas e cores: o usuário define as faixas (de/até), a cor e o texto da legenda de cada variável
do resultado — pressão nos nós; velocidade, perda de carga e vazão nos trechos. Fica salvo no projeto."""
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QVBoxLayout,
)

from . import estilo
from .resultados import PADRAO, VARIAVEIS, faixas, rotulo, salvar_faixas


def _num(txt):
    txt = txt.strip().replace(",", ".")
    if not txt:
        return None
    return float(txt)


class JanelaFaixas(QDialog):
    def __init__(self, pai, var="v", ao_aplicar=None):
        super().__init__(pai)
        self.ao_aplicar = ao_aplicar
        self.setWindowTitle("GWATER · Faixas e cores dos resultados")
        self.setObjectName("gwater")
        self.setStyleSheet(estilo.qss())
        self.resize(620, 460)
        lay = QVBoxLayout(self)
        exp = QLabel("Escolha a variável e defina as faixas: o valor entra na faixa quando é maior ou igual ao "
                     "<b>De</b> e menor que o <b>Até</b>. Deixe <b>De</b> vazio na primeira faixa e <b>Até</b> vazio "
                     "na última para não ter limite. O texto da legenda é opcional: vazio, o GWATER escreve os limites.")
        exp.setObjectName("sub")
        exp.setWordWrap(True)
        lay.addWidget(exp)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Variável:"))
        self.var = QComboBox()
        for k, (nome, un, _, cam) in VARIAVEIS.items():
            self.var.addItem(f"{'Nós' if cam == 'nos' else 'Trechos'} · {nome} ({un})", k)
        self.var.setCurrentIndex(list(VARIAVEIS).index(var))
        self.var.currentIndexChanged.connect(lambda _=0: self._carregar())
        topo.addWidget(self.var, 1)
        lay.addLayout(topo)

        self.tab = QTableWidget(0, 4)
        self.tab.setHorizontalHeaderLabels(["De", "Até", "Cor", "Texto da legenda"])
        h = self.tab.horizontalHeader()
        for c in (0, 1, 2):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tab.verticalHeader().setVisible(False)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lay.addWidget(self.tab, 1)

        bts = QHBoxLayout()
        for txt, f, dica in (("+ faixa", self._mais, "Divide a última faixa em duas"),
                             ("− faixa", self._menos, "Remove a faixa selecionada (ou a última)"),
                             ("Restaurar padrão", self._padrao, "Volta às faixas do GWATER")):
            b = QPushButton(txt)
            b.setToolTip(dica)
            b.clicked.connect(f)
            bts.addWidget(b)
        bts.addStretch(1)
        self.aplicar = QPushButton("Aplicar")
        self.aplicar.setDefault(True)
        self.aplicar.clicked.connect(self._aplicar)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.reject)
        bts.addWidget(self.aplicar)
        bts.addWidget(fechar)
        lay.addLayout(bts)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self._carregar()

    # ------------------------------------------------ tabela
    def _linha(self, de, ate, cor, rot):
        r = self.tab.rowCount()
        self.tab.insertRow(r)
        for c, v in ((0, de), (1, ate)):
            e = QLineEdit("" if v is None else f"{v:g}".replace(".", ","))
            e.setPlaceholderText("sem limite")
            e.setAlignment(Qt.AlignmentFlag.AlignRight)
            e.setMaximumWidth(110)
            self.tab.setCellWidget(r, c, e)
        b = QgsColorButton()
        b.setColor(QColor(cor))
        b.setMinimumWidth(70)
        self.tab.setCellWidget(r, 2, b)
        e = QLineEdit(rot or "")
        e.setPlaceholderText(rotulo(de, ate, VARIAVEIS[self.var.currentData()][1]) if (de is not None or ate is not None)
                             else "")
        self.tab.setCellWidget(r, 3, e)

    def _carregar(self, lista=None):
        self.tab.setRowCount(0)
        for de, ate, cor, rot in (lista if lista is not None else faixas(self.var.currentData())):
            self._linha(de, ate, cor, rot)
        self.msg.setText("")

    def _ler(self):
        lista = []
        for r in range(self.tab.rowCount()):
            de, ate = _num(self.tab.cellWidget(r, 0).text()), _num(self.tab.cellWidget(r, 1).text())
            if de is not None and ate is not None and ate <= de:
                raise ValueError(f"linha {r + 1}: o 'Até' ({ate:g}) tem que ser maior que o 'De' ({de:g})")
            lista.append([de, ate, self.tab.cellWidget(r, 2).color().name(), self.tab.cellWidget(r, 3).text().strip()])
        if not lista:
            raise ValueError("crie pelo menos uma faixa")
        return lista

    def _mais(self):
        try:
            lista = self._ler()
        except ValueError:
            lista = faixas(self.var.currentData())
        de, ate, cor, _ = lista[-1]
        if de is not None and ate is None:  # divide a última faixa (aberta) em duas
            passo = (de - (lista[-2][0] or 0)) if len(lista) > 1 else max(abs(de), 1)
            lista[-1] = [de, de + passo, cor, ""]
            lista.append([de + passo, None, "#a78bfa", ""])
        else:
            lista.append([ate, None, "#a78bfa", ""])
        self._carregar(lista)

    def _menos(self):
        r = self.tab.currentRow()
        r = r if r >= 0 else self.tab.rowCount() - 1
        if self.tab.rowCount() > 1:
            self.tab.removeRow(r)

    def _padrao(self):
        self._carregar([list(x) for x in PADRAO[self.var.currentData()]])

    def _aplicar(self):
        try:
            lista = self._ler()
        except ValueError as e:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>{e}</span>")
            return
        salvar_faixas(self.var.currentData(), lista)
        if self.ao_aplicar:
            self.ao_aplicar(self.var.currentData())
        self._carregar()
        self.msg.setText(f"<span style='color:{estilo.COR['ok']}'>✓ faixas aplicadas e salvas no projeto</span>")
