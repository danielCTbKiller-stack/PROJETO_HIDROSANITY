"""Painel lateral do GWATER no QGIS: problemas da rede e linha do tempo dos resultados."""
import os

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QDockWidget, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QSlider, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

ICONES = os.path.join(os.path.dirname(__file__), "icones")


def icone(nome):
    return QIcon(os.path.join(ICONES, nome + ".svg"))


class GwaterDock(QDockWidget):
    def __init__(self, plugin):
        super().__init__("GWATER · Simulação hidráulica")
        self.setObjectName("GwaterDock")
        self.plugin, self.res = plugin, None
        corpo = QWidget()
        lay = QVBoxLayout(corpo)

        botoes = QHBoxLayout()
        for texto, nome, acao in (("Validar", "validar", plugin.validar), ("Simular", "simular", plugin.simular),
                                  ("Painel web", "painel", plugin.abrir_painel)):
            b = QPushButton(icone(nome), texto)
            b.clicked.connect(acao)
            botoes.addWidget(b)
        lay.addLayout(botoes)
        self.projetados = QCheckBox("Incluir elementos PROJETADOS (simular proposta)")
        lay.addWidget(self.projetados)
        self.status = QLabel("Abra um projeto com o cadastro GWATER e clique em Validar ou Simular.")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.abas = QTabWidget()
        # ---- aba problemas
        self.tabela = QTableWidget(0, 2)
        self.tabela.setHorizontalHeaderLabels(["Nível", "Problema (clique duplo = ir até o elemento)"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setWordWrap(True)
        self.tabela.cellDoubleClicked.connect(self._ir_ate)
        self.abas.addTab(self.tabela, "Problemas")
        # ---- aba resultados
        res = QWidget()
        rl = QVBoxLayout(res)
        tempo = QHBoxLayout()
        self.play = QPushButton("▶")
        self.play.setFixedWidth(36)
        self.play.setToolTip("Reproduzir as 24 h")
        self.play.clicked.connect(self._alternar)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._passo)
        self.critico = QPushButton("Pior momento")
        self.critico.setToolTip("Vai para o passo com a menor pressão da rede")
        self.critico.clicked.connect(lambda: self.res and self.slider.setValue(self.res.pior_momento()))
        tempo.addWidget(self.play)
        tempo.addWidget(self.slider, 1)
        tempo.addWidget(self.critico)
        rl.addLayout(tempo)
        self.resumo = QLabel("Simule a rede para ver os resultados.")
        self.resumo.setWordWrap(True)
        self.resumo.setTextFormat(Qt.TextFormat.RichText)
        self.resumo.setAlignment(Qt.AlignmentFlag.AlignTop)
        rl.addWidget(self.resumo, 1)
        self.abas.addTab(res, "Resultados")
        lay.addWidget(self.abas, 1)
        self.setWidget(corpo)

        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self._avancar)

    # ------------------------------------------------ problemas
    def mostrar_problemas(self, itens):
        self.tabela.setRowCount(0)
        for it in itens:
            r = self.tabela.rowCount()
            self.tabela.insertRow(r)
            nivel = QTableWidgetItem(it["nivel"])
            nivel.setForeground(QColor("#e5484d" if it["nivel"] == "ERRO" else "#d48806"))
            nivel.setData(Qt.ItemDataRole.UserRole, (it.get("camada"), it.get("id")))
            self.tabela.setItem(r, 0, nivel)
            self.tabela.setItem(r, 1, QTableWidgetItem(it["msg"]))
        self.tabela.resizeRowsToContents()
        erros = sum(1 for i in itens if i["nivel"] == "ERRO")
        self.abas.setTabText(0, f"Problemas ({len(itens)})")
        if erros:
            self.abas.setCurrentIndex(0)
        return erros

    def _ir_ate(self, linha, _col):
        camada, fid = self.tabela.item(linha, 0).data(Qt.ItemDataRole.UserRole)
        if camada and fid:
            self.plugin.ir_ate(camada, fid)

    # ------------------------------------------------ resultados
    def carregar(self, res):
        self.res = res
        self.slider.blockSignals(True)
        self.slider.setRange(0, len(res.horas) - 1)
        self.slider.blockSignals(False)
        self.abas.setCurrentIndex(1)
        self.slider.setValue(res.pior_momento())
        self._passo(self.slider.value())

    def _passo(self, k):
        if self.res:
            self.res.aplicar(k)
            self.resumo.setText(self.res.resumo(k))

    def _alternar(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play.setText("▶")
        elif self.res:
            self.timer.start()
            self.play.setText("❚❚")

    def _avancar(self):
        self.slider.setValue((self.slider.value() + 1) % (self.slider.maximum() + 1))

    def parar(self):
        self.timer.stop()
        self.play.setText("▶")
