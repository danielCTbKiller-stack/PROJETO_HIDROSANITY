"""Configurações do GPREDIAL: o tema (os mesmos cinco do GWATER, em temas.json). A escolha fica gravada e vale ao
abrir o programa de novo."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QVBoxLayout)

from gui import theme


def _amostra(cores, w=150, h=34):
    """Faixas com as cores principais do tema (fundo, painel, destaque, água, ok, alerta)."""
    pm = QPixmap(w, h)
    pm.fill(QColor(cores["bg"]))
    p = QPainter(pm)
    ks = ["panel", "line", "cyan", "water", "ok", "crit"]
    lw = w / len(ks)
    for i, k in enumerate(ks):
        p.fillRect(int(i * lw) + 3, 5, int(lw) - 6, h - 10, QColor(cores[k]))
    p.end()
    return pm


def abrir(janela):
    """Escolher o tema. Devolve o nome aplicado, ou None se cancelou."""
    if not theme.TEMAS:
        return None
    d = QDialog(janela)
    d.setWindowTitle("Configurações")
    d.resize(560, 420)
    col = QVBoxLayout(d)
    t = QLabel("TEMA")
    t.setObjectName("h3")
    col.addWidget(t)
    s = QLabel("O mesmo tema vale para o GPREDIAL e o hub GeoLogic Water (o GWATER tem o seu, nas Configurações dele). A escolha fica gravada para as próximas vezes.")
    s.setObjectName("sub")
    s.setWordWrap(True)
    col.addWidget(s)
    lista = QListWidget()
    lista.setIconSize(_amostra(theme.COR).size())
    atual = theme.tema_atual()
    for nome, t_ in theme.TEMAS.items():
        it = QListWidgetItem(f"{nome}{'  ·  padrão' if nome == theme.PADRAO else ''}\n{t_.get('descricao', '')}")
        it.setIcon(_amostra(t_["cores"]))
        it.setData(Qt.UserRole, nome)
        lista.addItem(it)
        if nome == atual:
            lista.setCurrentItem(it)
    col.addWidget(lista, 1)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText("Aplicar")
    bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    h = QHBoxLayout()
    h.addStretch(1)
    h.addWidget(bb)
    col.addLayout(h)
    lista.itemDoubleClicked.connect(lambda _: d.accept())
    if not d.exec() or lista.currentItem() is None:
        return None
    nome = theme.aplicar_tema(lista.currentItem().data(Qt.UserRole), QApplication.instance())
    for w in QApplication.allWidgets():  # desenhos próprios (planta, sinótico, gráficos) leem as cores ao pintar
        w.update()
    return nome
