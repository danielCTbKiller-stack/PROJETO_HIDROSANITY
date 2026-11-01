"""Faixa de menus no estilo do GWATER: abas em cima e, em cada aba, grupos de botões grandes."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from gui.symbols import icon


class RibbonGroup(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("grupo")
        col = QVBoxLayout(self)
        col.setContentsMargins(6, 2, 10, 2)
        col.setSpacing(2)
        self.body = QHBoxLayout()
        self.body.setSpacing(2)
        col.addLayout(self.body, 1)
        t = QLabel(title)
        t.setObjectName("grupoTitulo")
        t.setAlignment(Qt.AlignCenter)
        col.addWidget(t)

    def button(self, text, icon_name, slot=None, tip="", checkable=False, group: QButtonGroup = None):
        b = QToolButton()
        b.setObjectName("acao")
        b.setText(text)
        b.setIcon(icon(icon_name))
        b.setIconSize(QSize(30, 30))
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        b.setMinimumWidth(58)
        b.setCheckable(checkable)
        b.setToolTip(tip or text)
        if group is not None:
            group.addButton(b)
        if slot is not None:
            b.clicked.connect(slot)
        self.body.addWidget(b)
        return b

    def widgets(self, rows):
        """Coluna de controles pequenos: [(rótulo, widget), ...]."""
        grid = QGridLayout()
        grid.setVerticalSpacing(3)
        grid.setHorizontalSpacing(6)
        for r, (label, w) in enumerate(rows):
            if label:
                lb = QLabel(label)
                lb.setObjectName("rotulo")
                grid.addWidget(lb, r, 0)
            grid.addWidget(w, r, 1)
        holder = QWidget()
        holder.setLayout(grid)
        self.body.addWidget(holder)
        return holder


class Ribbon(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("faixa")
        col = QVBoxLayout(self)
        col.setContentsMargins(6, 4, 6, 0)
        col.setSpacing(2)
        self.top = QHBoxLayout()  # linha de cima, como no GWATER: gota, Arquivo e acesso rápido
        self.top.setSpacing(4)
        col.addLayout(self.top)
        self.tabs = QHBoxLayout()
        self.tabs.setSpacing(2)
        self.tabs.addStretch(1)
        col.addLayout(self.tabs)
        self.stack = QStackedWidget()
        self.stack.setObjectName("corpoFaixa")
        # a altura acompanha o conteúdo (fontes e cantos mudam com o tema): rótulos de duas linhas e as colunas de
        # três campos não podem ser cortados
        self.stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        col.addWidget(self.stack)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)

    def page(self, title):
        btn = QToolButton()
        btn.setObjectName("aba")
        btn.setText(title)
        btn.setCheckable(True)
        self._tab_group.addButton(btn)
        self.tabs.insertWidget(self.tabs.count() - 1, btn)
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)
        index = self.stack.addWidget(page)
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(index))
        if index == 0:
            btn.setChecked(True)

        def group(title):
            g = RibbonGroup(title)
            row.insertWidget(row.count() - 1, g)
            return g
        page.group = group
        page.tab_button = btn
        return page

    def top_row(self, brand_icon, on_brand, file_menu, quick, title):
        """Linha de cima no padrão do GWATER. `quick`: [(ícone, dica, slot)]."""
        marca = QToolButton()
        marca.setObjectName("rapido")
        marca.setIcon(brand_icon)
        marca.setIconSize(QSize(22, 22))
        marca.setToolTip("<b>Programas integrados</b><br>Abrir o GWATER ou outro programa do GeoLogic Water")
        marca.clicked.connect(on_brand)
        self.top.addWidget(marca)
        arq = QToolButton()
        arq.setObjectName("arquivo")
        arq.setText("Arquivo")
        arq.setMenu(file_menu)
        arq.setPopupMode(QToolButton.InstantPopup)
        self.top.addWidget(arq)
        self.top.addSpacing(6)
        for icon_name, tip, slot in quick:
            b = QToolButton()
            b.setObjectName("rapido")
            b.setIcon(icon(icon_name))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.clicked.connect(slot)
            self.top.addWidget(b)
        self.top.addStretch(1)
        t = QLabel(title)
        t.setObjectName("marcaTitulo")
        self.top.addWidget(t)
        self.brand_button, self.file_button = marca, arq
        return marca

    def show_page(self, page):
        self.stack.setCurrentWidget(page)
        page.tab_button.setChecked(True)
