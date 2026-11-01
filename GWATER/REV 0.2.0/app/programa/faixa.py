"""Faixa de menus (ribbon) do GWATER.exe, no formato do WaterGEMS.

Linha de cima: botão Arquivo, acesso rápido (novo, abrir, salvar, desfazer, refazer, calcular) e o
nome do cadastro. Embaixo, as abas; cada aba tem grupos com botões grandes (ícone em cima) e pequenos
(empilhados de três em três), e o nome do grupo no rodapé. Clicar emite `acionado(chave)`.
"""
from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy, QTabWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from . import catalogo
from .tema import icone

ALTURA_GRUPO = 92


def _dica(texto, desc):
    return f"<b>{texto}</b><br>{desc}" if desc else f"<b>{texto}</b>"


class Faixa(QWidget):
    acionado = pyqtSignal(str)

    def __init__(self, pai=None, tem_acao=lambda k: True):
        super().__init__(pai)
        self.setObjectName("faixa")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.tem_acao = tem_acao
        self.botoes = {}  # chave -> [QToolButton] (a mesma chave aparece em várias abas)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 0)
        lay.setSpacing(2)

        topo = QHBoxLayout()
        topo.setSpacing(4)
        marca = QToolButton()
        marca.setObjectName("rapido")
        marca.setIcon(icone("marca"))
        marca.setIconSize(QSize(22, 22))
        marca.setToolTip("<b>Programas integrados</b><br>Abrir o GPREDIAL ou outro programa do HIDROSANITY")
        marca.clicked.connect(self._programas)
        topo.addWidget(marca)
        self.menu_arquivo = QMenu(self)
        self.menu_recentes = None
        for item in catalogo.ARQUIVO:
            if item is None:
                self.menu_arquivo.addSeparator()
                continue
            chave, texto, ic, desc = item
            if chave == "recentes":
                self.menu_recentes = self.menu_arquivo.addMenu(icone(ic), texto)
                continue
            a = self.menu_arquivo.addAction(icone(ic), texto)
            a.setToolTip(desc)
            a.triggered.connect(lambda _=False, k=chave: self.acionado.emit(k))
        self.menu_arquivo.setToolTipsVisible(True)
        arq = QToolButton()
        arq.setObjectName("arquivo")
        arq.setText("Arquivo")
        arq.setMenu(self.menu_arquivo)
        arq.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        topo.addWidget(arq)
        topo.addSpacing(6)
        for chave, ic, dica in catalogo.ACESSO_RAPIDO:
            b = QToolButton()
            b.setObjectName("rapido")
            b.setIcon(icone(ic))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(dica)
            b.clicked.connect(lambda _=False, k=chave: self.acionado.emit(k))
            self.botoes.setdefault(chave, []).append(b)
            topo.addWidget(b)
        topo.addStretch(1)
        self.titulo = QLabel("GWATER")
        self.titulo.setObjectName("titulo")
        topo.addWidget(self.titulo)
        topo.addStretch(1)
        marca2 = QLabel("GWATER")
        marca2.setObjectName("marcaTitulo")
        topo.addWidget(marca2)
        lay.addLayout(topo)

        self.abas = QTabWidget()
        self.abas.setObjectName("abasFaixa")
        self.abas.setDocumentMode(True)
        for aid, nome, grupos in catalogo.FAIXA:
            self.abas.addTab(self._pagina(grupos), nome)
            self.abas.widget(self.abas.count() - 1).setObjectName(f"aba_{aid}")
        lay.addWidget(self.abas)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _programas(self):
        from .integrados import escolher
        escolher(self.window(), "gwater")

    def ir_para(self, aid):
        for i in range(self.abas.count()):
            if self.abas.widget(i).objectName() == f"aba_{aid}":
                self.abas.setCurrentIndex(i)

    # ------------------------------------------------ construção
    def _pagina(self, grupos):
        corpo = QWidget()
        h = QHBoxLayout(corpo)
        h.setContentsMargins(2, 3, 2, 2)
        h.setSpacing(0)
        for titulo, botoes in grupos:
            h.addWidget(self._grupo(titulo, botoes))
        h.addStretch(1)
        rolar = QScrollArea()
        rolar.setWidget(corpo)
        rolar.setWidgetResizable(True)
        rolar.setFrameShape(QFrame.Shape.NoFrame)
        rolar.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        rolar.setFixedHeight(ALTURA_GRUPO + 30)
        return rolar

    def _grupo(self, titulo, botoes):
        g = QFrame()
        g.setObjectName("grupoFaixa")
        v = QVBoxLayout(g)
        v.setContentsMargins(5, 0, 5, 1)
        v.setSpacing(0)
        area = QWidget()
        grade = QGridLayout(area)
        grade.setContentsMargins(0, 0, 0, 0)
        grade.setHorizontalSpacing(2)
        grade.setVerticalSpacing(1)
        col, linha = 0, 0
        for b in botoes:
            chave, texto, ic, tam, desc = b[:5]
            sub = b[5] if len(b) > 5 else None
            if tam == "G":
                if linha:
                    col, linha = col + 1, 0
                grade.addWidget(self._botao(chave, texto, ic, desc, sub, True), 0, col, 3, 1,
                                Qt.AlignmentFlag.AlignTop)
                col += 1
            else:
                grade.addWidget(self._botao(chave, texto, ic, desc, sub, False), linha, col,
                                Qt.AlignmentFlag.AlignLeft)
                linha += 1
                if linha == 3:
                    col, linha = col + 1, 0
        area.setFixedHeight(ALTURA_GRUPO - 16)
        v.addWidget(area)
        rot = QLabel(titulo)
        rot.setObjectName("tituloGrupo")
        rot.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(rot)
        return g

    def _botao(self, chave, texto, ic, desc, sub, grande):
        b = QToolButton()
        b.setObjectName("botaoFaixa")
        b.setText(texto)
        b.setIcon(icone(ic))
        b.setToolTip(_dica(texto, desc))
        b.setAutoRaise(True)
        if grande:
            b.setIconSize(QSize(30, 30))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedHeight(ALTURA_GRUPO - 18)
            if " " in texto and len(texto) > 11:  # duas linhas, como no WaterGEMS
                meio = texto.rfind(" ", 0, len(texto) // 2 + 4)
                b.setText(texto[:meio] + "\n" + texto[meio + 1:])
            largura = max(b.fontMetrics().horizontalAdvance(x) for x in b.text().split("\n")) + 16
            b.setMinimumWidth(max(58, largura) + (16 if sub else 0))  # a setinha do submenu ocupa espaço
            b.setMaximumWidth(140)
        else:
            b.setIconSize(QSize(16, 16))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setFixedHeight(24)
        if sub:
            m = QMenu(b)
            m.setToolTipsVisible(True)
            for s_chave, s_texto, s_ic, s_desc in sub:
                a = m.addAction(icone(s_ic), s_texto)
                a.setToolTip(s_desc)
                a.triggered.connect(lambda _=False, k=s_chave: self.acionado.emit(k))
            b.setMenu(m)
            if self.tem_acao(chave):
                b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                b.clicked.connect(lambda _=False, k=chave: self.acionado.emit(k))
            else:
                b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            b.clicked.connect(lambda _=False, k=chave: self.acionado.emit(k))
        self.botoes.setdefault(chave, []).append(b)
        return b

    # ------------------------------------------------ estado
    def marcar(self, chave):
        """Deixa marcado o botão da ferramenta de mapa ativa (selecionar, mover, desenhar...)."""
        for k, lista in self.botoes.items():
            for b in lista:
                if b.objectName() != "botaoFaixa":
                    continue
                b.setCheckable(k == chave)
                b.setChecked(k == chave)
