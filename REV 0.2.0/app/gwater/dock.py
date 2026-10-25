"""Painel lateral do GWATER no QGIS (Central GWATER).

Abas: Central (botões por etapa; a explicação de cada um aparece no quadro de baixo ao passar o
mouse), Problemas (validação) e Resultados (linha do tempo da simulação).
O visual é o mesmo do Centro de Operações web (estilo.py), independente do tema do QGIS.
"""
import os

from qgis.PyQt.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QBoxLayout, QCheckBox, QComboBox, QDockWidget, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLayout, QPushButton, QScrollArea, QSizePolicy, QSlider, QTableWidget, QTableWidgetItem, QTabWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from . import acoes, estilo

ICONES = os.path.join(os.path.dirname(__file__), "icones")
DNS = ["50", "75", "100", "150", "200", "250", "300", "350", "400", "500", "600"]
MATERIAIS = ["PVC PBA", "PVC DEFoFo", "PEAD", "Ferro fundido dúctil", "Ferro fundido cinzento", "Aço",
             "Cimento-amianto"]
SITUACOES = ["EXISTENTE", "PROJETADO"]
AJUDA_INICIAL = ("Passe o mouse sobre um botão", "A explicação do que ele faz aparece aqui. Clique para usar.")
# faixa horizontal (painel embaixo do mapa): quantos botões por linha em cada grupo
COLUNAS = {"cadastro": 3, "desenho": 5, "modelo": 2, "simular": 2, "web": 2, "ajuda": 1}
BOTAO = QSize(84, 70)
LARGURA_AJUDA = 280


def icone(nome):
    return QIcon(os.path.join(ICONES, nome + ".svg"))


def dica(texto, desc):
    return f"<b>{texto}</b><br>{desc}"


class Fluxo(QLayout):
    """Layout que quebra linha como texto: os botões se ajeitam à largura do painel."""

    def __init__(self, pai=None, espaco=6):
        super().__init__(pai)
        self.itens, self.espaco = [], espaco
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.itens.append(item)

    def count(self):
        return len(self.itens)

    def itemAt(self, i):
        return self.itens[i] if 0 <= i < len(self.itens) else None

    def takeAt(self, i):
        return self.itens.pop(i) if 0 <= i < len(self.itens) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, largura):
        return self._arrumar(QRect(0, 0, largura, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._arrumar(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self.itens:
            s = s.expandedTo(it.minimumSize())
        return s

    def _arrumar(self, r, so_medir):
        x, y, alt = r.x(), r.y(), 0
        for it in self.itens:
            w = it.sizeHint()
            if x + w.width() > r.right() + 1 and alt > 0:
                x, y, alt = r.x(), y + alt + self.espaco, 0
            if not so_medir:
                it.setGeometry(QRect(QPoint(x, y), w))
            x += w.width() + self.espaco
            alt = max(alt, w.height())
        return y + alt - r.y()


class GwaterDock(QDockWidget):
    def __init__(self, plugin):
        super().__init__("Central GWATER")
        self.setObjectName("GwaterCentral")  # nome novo: o QGIS não reaproveita a posição antiga (flutuante)
        self.plugin, self.res = plugin, None
        self.botoes, self.cards, self.subs, self.horizontal = {}, [], [], None
        corpo = QWidget()
        corpo.setObjectName("gwater")
        corpo.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.corpo = corpo
        lay = QVBoxLayout(corpo)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self.topo = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.topo.setSpacing(8)
        self.cab = self._cabecalho()
        self.topo.addWidget(self.cab)
        self.status = QLabel("Abra um cadastro GWATER (ou crie um em 1 · Cadastro) para começar.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.topo.addWidget(self.status, 1)
        lay.addLayout(self.topo)

        self.abas = QTabWidget()
        # fonte das abas no próprio widget (fonte vinda só da folha de estilo corta o texto: o Qt mede com outra)
        self.abas.tabBar().setFont(estilo.fonte("mono", 8, True, 4))
        self.abas.tabBar().setExpanding(False)
        self.abas.addTab(self._aba_central(), "Central")
        # ---- aba problemas
        self.tabela = QTableWidget(0, 2)
        self.tabela.setHorizontalHeaderLabels(["Nível", "Problema (clique duplo = ir até o elemento)"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setWordWrap(True)
        self.tabela.cellDoubleClicked.connect(self._ir_ate)
        self.aba_problemas = self.abas.addTab(self.tabela, "Problemas")
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
        cores = QHBoxLayout()
        cores.addWidget(QLabel("Cor dos tubos:"))
        self.cor_tubos = QComboBox()
        for k, t in (("v", "Velocidade (m/s)"), ("hl", "Perda de carga (m/km)"), ("q", "Vazão (L/s)")):
            self.cor_tubos.addItem(t, k)
        self.cor_tubos.setToolTip("Variável que colore as tubulações no mapa (os nós são sempre a pressão)")
        self.cor_tubos.currentIndexChanged.connect(lambda _=0: self.plugin.mudar_cor_tubos(self.cor_tubos.currentData()))
        cores.addWidget(self.cor_tubos, 1)
        bfx = QPushButton("Faixas e cores…")
        bfx.setToolTip("Define as faixas (de/até), as cores e a legenda de pressão, velocidade, perda de carga e vazão")
        bfx.clicked.connect(lambda: self.plugin.executar("cores"))
        cores.addWidget(bfx)
        rl.addLayout(cores)
        self.resumo = QLabel("Simule a rede para ver os resultados.")
        self.resumo.setWordWrap(True)
        self.resumo.setTextFormat(Qt.TextFormat.RichText)
        self.resumo.setAlignment(Qt.AlignmentFlag.AlignTop)
        rl.addWidget(self.resumo, 1)
        self.aba_resultados = self.abas.addTab(res, "Resultados")
        lay.addWidget(self.abas, 1)
        self.setWidget(corpo)

        self.timer = QTimer(self)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self._avancar)
        self._modo(False)

    # ------------------------------------------------ aba Central
    def _estilo(self):
        self.corpo.setStyleSheet(estilo.qss())

    def _cabecalho(self):
        """Igual ao topo do painel web: marca, título e etiqueta do motor."""
        card = QFrame()
        card.setObjectName("card")
        h = QHBoxLayout(card)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(10)
        marca = QLabel()
        marca.setPixmap(icone("marca").pixmap(QSize(38, 38)))
        h.addWidget(marca)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        titulo = QLabel("GWATER · Central")
        titulo.setFont(estilo.fonte("display", 15, True, 4))
        sub = QLabel("Cadastro, desenho e simulação da rede")
        sub.setObjectName("sub")
        textos.addWidget(titulo)
        textos.addWidget(sub)
        h.addLayout(textos, 1)
        chip = QLabel("MOTOR EPANET")
        chip.setObjectName("chip")
        chip.setFont(estilo.fonte("mono", 7.5, True, 6))
        h.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        return card

    def _botao(self, chave):
        texto, ic, desc, _ = acoes.todas()[chave]
        b = QToolButton()
        b.setObjectName("acao")
        b.setIcon(icone(ic))
        b.setIconSize(QSize(28, 28))
        b.setText(acoes.CURTO.get(chave, texto))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setFixedSize(QSize(84, 70))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(dica(texto, desc))
        b.setProperty("ajuda", (texto, desc, ic))
        b.installEventFilter(self)
        b.clicked.connect(lambda _=False, k=chave: self.plugin.executar(k))
        self.botoes[chave] = b
        return b

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Enter and obj.property("ajuda"):
            self._mostrar_ajuda(*obj.property("ajuda"))
        if ev.type() == QEvent.Type.Wheel and self.horizontal and obj is self.rolar.viewport():
            # na faixa horizontal a rodinha do mouse anda para os lados
            barra = self.rolar.horizontalScrollBar()
            barra.setValue(barra.value() - ev.angleDelta().y())
            return True
        return False

    def _mostrar_ajuda(self, titulo, texto, ic=None):
        self.ajuda_icone.setPixmap(icone(ic).pixmap(QSize(32, 32)) if ic else icone("ajuda").pixmap(QSize(32, 32)))
        self.ajuda_texto.setText(f"<b>{titulo}</b><br>{texto}")
        self._ajustar_ajuda()

    def _ajustar_ajuda(self):
        """Altura FIXA do quadro de explicação, medida pelo texto e pela largura atual (no máximo 7 linhas).

        Altura fixa: o quadro nunca disputa espaço com os botões (antes ele podia crescer e esmagar a lista)."""
        lb = self.ajuda_texto
        if self.horizontal:
            largura, maximo = LARGURA_AJUDA - 64, 16
        else:
            largura, maximo = (lb.width() if lb.width() > 80 else max(self.width() - 90, 220)), 7
        linha = lb.fontMetrics().lineSpacing()
        altura = min(max(lb.heightForWidth(largura), 2 * linha), maximo * linha) + 4
        lb.setFixedHeight(altura)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if hasattr(self, "ajuda_texto"):
            # largo e baixo (embaixo do mapa) = faixa horizontal; alto (na lateral) = coluna
            self._modo(self.width() >= 760 and self.width() > 1.4 * self.height())
            self._ajustar_ajuda()

    ALTURA_FAIXA = 330  # duas linhas de botões + abas + status

    def _modo(self, horizontal):
        """Arruma a Central em faixa horizontal (grupos lado a lado) ou em coluna (grupos um embaixo do outro)."""
        if horizontal == self.horizontal:
            return
        self.horizontal = horizontal
        D = QBoxLayout.Direction
        # na faixa, altura vale ouro: sem o cabeçalho e sem os subtítulos (a explicação está no quadro da direita)
        self.cab.setVisible(not horizontal)
        for lb in self.subs:
            lb.setVisible(not horizontal)
        self.lista.setDirection(D.LeftToRight if horizontal else D.TopToBottom)
        self.corpo_central.setDirection(D.LeftToRight if horizontal else D.TopToBottom)
        for gid, card, caixa, n in self.cards:
            if horizontal:
                cols = COLUNAS.get(gid, 2) if n else 0
                largura = cols * BOTAO.width() + max(cols - 1, 0) * 6 + 26 if n else 300
                card.setFixedWidth(largura)
                if caixa is not None:
                    linhas = -(-n // cols)
                    caixa.setMinimumHeight(linhas * BOTAO.height() + (linhas - 1) * 6)
            else:
                card.setMinimumWidth(0)
                card.setMaximumWidth(16777215)
                if caixa is not None:
                    caixa.setMinimumHeight(0)
        pol = Qt.ScrollBarPolicy
        self.rolar.setHorizontalScrollBarPolicy(pol.ScrollBarAsNeeded if horizontal else pol.ScrollBarAlwaysOff)
        self.rolar.setVerticalScrollBarPolicy(pol.ScrollBarAlwaysOff if horizontal else pol.ScrollBarAsNeeded)
        if horizontal:
            self.quadro_ajuda.setFixedWidth(LARGURA_AJUDA)
            self.quadro_ajuda.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        else:
            self.quadro_ajuda.setMinimumWidth(0)
            self.quadro_ajuda.setMaximumWidth(16777215)
            self.quadro_ajuda.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._ajustar_ajuda()

    def _aba_central(self):
        aba = QWidget()
        externo = QVBoxLayout(aba)
        externo.setContentsMargins(0, 0, 0, 0)

        conteudo = QWidget()
        self.lista = QBoxLayout(QBoxLayout.Direction.TopToBottom, conteudo)
        self.lista.setContentsMargins(0, 8, 4, 8)
        self.lista.setSpacing(10)

        def cartao(gid, titulo, sub):
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 12)
            cl.setSpacing(6)
            cab = QLabel(titulo)
            cab.setObjectName("h3")
            cab.setFont(estilo.fonte("mono", 8.5, True, 8))
            cl.addWidget(cab)
            if sub:
                lb = QLabel(sub)
                lb.setObjectName("sub")
                lb.setWordWrap(True)
                cl.addWidget(lb)
                self.subs.append(lb)
            self.lista.addWidget(card)
            return card, cl

        for gid, titulo, sub, lista in acoes.GRUPOS:
            card, cl = cartao(gid, titulo.upper() if gid != "ajuda" else "AJUDA", sub)
            caixa = QWidget()
            fluxo = Fluxo(caixa)
            for chave, *_ in lista:
                fluxo.addWidget(self._botao(chave))
            cl.addWidget(caixa)
            if gid == "simular":
                self.projetados = QCheckBox("Incluir PROJETADOS")
                self.projetados.setToolTip("Simular a obra proposta. Desmarcado: só entra o que é EXISTENTE. "
                                           "Marcado: entram também os elementos com situação PROJETADO.")
                cl.addWidget(self.projetados)
            cl.addStretch(1)
            self.cards.append((gid, card, caixa, len(lista)))
            if gid == "desenho":  # valores do desenho logo depois dos botões de desenho
                card, cl = cartao("prototipo", "AO DESENHAR, USAR", "")
                cl.addWidget(self._prototipo())
                cl.addStretch(1)
                self.cards.append(("prototipo", card, None, 0))
        self.lista.addStretch(1)
        self.rolar = rolar = QScrollArea()
        rolar.setWidgetResizable(True)
        rolar.setFrameShape(QFrame.Shape.NoFrame)
        rolar.setWidget(conteudo)
        rolar.viewport().installEventFilter(self)
        self.corpo_central = QBoxLayout(QBoxLayout.Direction.TopToBottom)
        self.corpo_central.setSpacing(8)
        self.corpo_central.addWidget(rolar, 1)
        externo.addLayout(self.corpo_central, 1)

        # quadro fixo embaixo: explica o botão sob o mouse
        ajuda = QFrame()
        ajuda.setObjectName("ajuda")
        h = QHBoxLayout(ajuda)
        h.setContentsMargins(8, 6, 8, 6)
        self.ajuda_icone = QLabel()
        self.ajuda_icone.setFixedSize(QSize(34, 34))
        self.ajuda_icone.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.ajuda_texto = QLabel()
        self.ajuda_texto.setWordWrap(True)
        self.ajuda_texto.setTextFormat(Qt.TextFormat.RichText)
        self.ajuda_texto.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.ajuda_texto.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        ajuda.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        h.addWidget(self.ajuda_icone, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(self.ajuda_texto, 1, Qt.AlignmentFlag.AlignTop)
        self.quadro_ajuda = ajuda
        self.corpo_central.addWidget(ajuda)
        self._mostrar_ajuda(*AJUDA_INICIAL)
        self._estilo()
        return aba

    def _prototipo(self):
        """Valores usados em tudo o que for desenhado (o 'protótipo' do WaterGEMS)."""
        caixa = QFrame()
        caixa.setObjectName("prototipo")
        g = QGridLayout(caixa)
        g.setContentsMargins(0, 2, 0, 0)
        g.setHorizontalSpacing(8)
        self.dn = QComboBox()
        self.dn.setEditable(True)
        self.dn.addItems(DNS)
        self.dn.setCurrentText("100")
        self.material = QComboBox()
        self.material.addItems(MATERIAIS)
        self.situacao = QComboBox()
        self.situacao.addItems(SITUACOES)
        for i, (rot, w, t) in enumerate((
                ("DN (mm)", self.dn, "Diâmetro nominal (mm) das tubulações novas"),
                ("Material", self.material, "Material das tubulações novas (define a rugosidade C)"),
                ("Situação", self.situacao, "EXISTENTE = rede que já existe; PROJETADO = obra proposta (só entra "
                                            "na simulação com a caixa PROJETADOS marcada)")), start=1):
            lb = QLabel(rot)
            lb.setObjectName("rotulo")
            w.setToolTip(t)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            g.addWidget(lb, i, 0)
            g.addWidget(w, i, 1)
        self.auto = QCheckBox("Ligar automaticamente (nós e divisões)")
        self.auto.setChecked(True)
        self.auto.setToolTip("Desligado, o GWATER não mexe em nada enquanto você desenha.")
        self.formulario = QCheckBox("Abrir o formulário a cada elemento")
        self.formulario.setChecked(True)
        self.formulario.setToolTip("Desligado, os elementos entram direto com os valores acima; edite depois "
                                   "com Ver / editar dados.")
        g.addWidget(self.auto, 4, 0, 1, 2)
        g.addWidget(self.formulario, 5, 0, 1, 2)
        g.setColumnStretch(1, 1)
        self.dn.editTextChanged.connect(self.plugin.prototipo_mudou)
        self.material.currentTextChanged.connect(self.plugin.prototipo_mudou)
        self.situacao.currentTextChanged.connect(self.plugin.prototipo_mudou)
        self.auto.toggled.connect(self.plugin.prototipo_mudou)
        self.formulario.toggled.connect(self.plugin.prototipo_mudou)
        return caixa

    def ler_prototipo(self):
        try:
            dn = float(self.dn.currentText().replace(",", "."))
        except ValueError:
            dn = None
        return {"dn": dn, "material": self.material.currentText(), "situacao": self.situacao.currentText(),
                "auto": self.auto.isChecked(), "formulario": self.formulario.isChecked()}

    def mostrar_prototipo(self, p):
        ws = (self.dn, self.material, self.situacao, self.auto, self.formulario)
        for w in ws:
            w.blockSignals(True)
        if p.get("dn"):
            self.dn.setCurrentText(f"{p['dn']:g}")
        self.material.setCurrentText(p.get("material") or "PVC PBA")
        self.situacao.setCurrentText(p.get("situacao") or "EXISTENTE")
        self.auto.setChecked(p.get("auto", True))
        self.formulario.setChecked(p.get("formulario", True))
        for w in ws:
            w.blockSignals(False)

    # ------------------------------------------------ problemas
    def mostrar_problemas(self, itens):
        self.tabela.setUpdatesEnabled(False)
        self.tabela.setRowCount(0)
        self.tabela.setRowCount(len(itens))
        for r, it in enumerate(itens):
            nivel = QTableWidgetItem(it["nivel"])
            nivel.setForeground(QColor(estilo.COR["crit"] if it["nivel"] == "ERRO" else estilo.COR["warn"]))
            nivel.setData(Qt.ItemDataRole.UserRole, (it.get("camada"), it.get("id")))
            self.tabela.setItem(r, 0, nivel)
            self.tabela.setItem(r, 1, QTableWidgetItem(it["msg"]))
        if len(itens) <= 300:  # altura pelo texto só em listas curtas (medir milhares de linhas trava)
            self.tabela.resizeRowsToContents()
        self.tabela.setUpdatesEnabled(True)
        erros = sum(1 for i in itens if i["nivel"] == "ERRO")
        self.abas.setTabText(self.aba_problemas, f"Problemas ({len(itens)})")
        if itens:
            self.abas.setCurrentIndex(self.aba_problemas)
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
        self.abas.setCurrentIndex(self.aba_resultados)
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

    def limpar_resultados(self):
        self.parar()
        self.res = None
        self.resumo.setText("Simule a rede para ver os resultados.")

    def parar(self):
        self.timer.stop()
        self.play.setText("▶")
