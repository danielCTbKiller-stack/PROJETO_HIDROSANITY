"""Notificações do cálculo agrupadas por tipo de problema (como o User Notifications do WaterGEMS).

Cada aviso do motor vira uma linha dentro do grupo do seu tipo: "ERRO · sem ligação com nenhuma fonte (12)".
O tipo sai do próprio texto, sem o código do elemento e sem os números (ajuste de 3 mca e de 4 mca = mesmo tipo).
Clique duplo num elemento leva até ele no mapa.
"""
import re

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                                 QVBoxLayout, QWidget)

from gwater.estilo import COR

NOMES = {"no_juncao": "Nó", "trecho": "Tubulação", "valvula": "Válvula", "bomba": "Bomba",
         "reservatorio": "Reservatório", "captacao": "Captação", "curva": "Curva", "padrao_consumo": "Padrão"}


def tipo_do_aviso(it):
    """Texto do tipo de problema: a mensagem sem o elemento e sem os números."""
    msg = str(it.get("msg", ""))
    eid = str(it.get("id") or "")
    if ":" in msg:
        cab, resto = msg.split(":", 1)
        if eid and eid in cab or len(cab) < 40:  # "válvula V12 (PRV): ..." → a parte depois dos dois-pontos
            msg = resto
    if eid:
        msg = re.sub(rf"(?<![\w-]){re.escape(eid)}(?![\w-])", "…", msg)
    msg = re.sub(r"-?\d+(?:[.,]\d+)?", "#", msg)
    msg = re.sub(r"\s+", " ", msg).strip(" .;")
    return (msg[:1].upper() + msg[1:]) if msg else "Outros"


class ArvoreNotificacoes(QWidget):
    def __init__(self, nucleo):
        super().__init__()
        self.nucleo = nucleo
        self.itens = []
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        h = QHBoxLayout()
        self.nivel = QComboBox()
        self.nivel.addItems(["Erros e avisos", "Só erros", "Só avisos"])
        self.nivel.currentIndexChanged.connect(lambda _: self.mostrar(self.itens))
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Filtrar por texto ou código…")
        self.busca.textChanged.connect(lambda _: self.mostrar(self.itens))
        b_abrir, b_fechar = QPushButton("Expandir tudo"), QPushButton("Recolher")
        self.resumo = QLabel()
        for w in (self.nivel, self.busca, b_abrir, b_fechar):
            h.addWidget(w)
        h.addWidget(self.resumo, 1)
        v.addLayout(h)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Tipo de problema / elemento", "Qtde.", "Mensagem"])
        self.arvore.setColumnWidth(0, 420)
        self.arvore.setColumnWidth(1, 60)
        self.arvore.setUniformRowHeights(True)
        self.arvore.itemDoubleClicked.connect(self._ir_ate)
        v.addWidget(self.arvore, 1)
        b_abrir.clicked.connect(self.arvore.expandAll)
        b_fechar.clicked.connect(self.arvore.collapseAll)

    def mostrar(self, itens):
        self.itens = list(itens)
        filtro = self.nivel.currentIndex()
        txt = self.busca.text().strip().lower()
        grupos = {}
        for it in self.itens:
            if (filtro == 1 and it["nivel"] != "ERRO") or (filtro == 2 and it["nivel"] == "ERRO"):
                continue
            if txt and txt not in str(it.get("msg", "")).lower() and txt not in str(it.get("id") or "").lower():
                continue
            grupos.setdefault((it["nivel"], tipo_do_aviso(it)), []).append(it)
        self.arvore.setUpdatesEnabled(False)
        self.arvore.clear()
        ordem = sorted(grupos.items(), key=lambda kv: (kv[0][0] != "ERRO", -len(kv[1]), kv[0][1]))
        for (nivel, tipo), lista in ordem:
            cor = QColor(COR["crit"] if nivel == "ERRO" else COR["warn"])
            g = QTreeWidgetItem([f"{'ERRO' if nivel == 'ERRO' else 'AVISO'} · {tipo}", str(len(lista)), ""])
            g.setForeground(0, cor)
            f = g.font(0)
            f.setBold(True)
            g.setFont(0, f)
            g.setToolTip(0, tipo)
            filhos = []
            for it in lista[:2000]:  # milhares de linhas iguais não ajudam e travam a lista
                nome = NOMES.get(it.get("camada"), it.get("camada") or "")
                c = QTreeWidgetItem([f"{nome} {it.get('id') or ''}".strip() or "(geral)", "", it["msg"]])
                c.setToolTip(2, it["msg"])
                c.setData(0, Qt.ItemDataRole.UserRole, (it.get("camada"), it.get("id")))
                filhos.append(c)
            if len(lista) > 2000:
                filhos.append(QTreeWidgetItem([f"… mais {len(lista) - 2000}", "", ""]))
            g.addChildren(filhos)
            self.arvore.addTopLevelItem(g)
        if len(grupos) <= 3:
            self.arvore.expandAll()
        self.arvore.setUpdatesEnabled(True)
        erros = sum(1 for i in self.itens if i["nivel"] == "ERRO")
        self.resumo.setText(f"  {erros} erro(s), {len(self.itens) - erros} aviso(s) em {len(grupos)} tipo(s)")

    def _ir_ate(self, item, _col):
        ref = item.data(0, Qt.ItemDataRole.UserRole)
        if ref and ref[0] and ref[1]:
            self.nucleo.ir_ate(ref[0], ref[1])
