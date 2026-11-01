"""Curvas de bomba, como as "Pump Definitions" do WaterGEMS.

Cada curva tem um nome e pontos vazão (L/s) × altura manométrica (m), na tabela `curva`
do cadastro (id_curva, tipo='BOMBA', x, y). O EPANET entende três formas:
  - 1 ponto (ponto de projeto): ele monta a curva com shutoff em 133% da altura e vazão
    máxima em 200% da vazão;
  - 3 pontos começando em vazão 0: ajusta H = A − B·Q^C;
  - 4 ou mais pontos: liga os pontos (curva por trechos).
Duas curvas de 2 pontos não existem no EPANET.

Na camada de bombas, o campo `curva` vira uma lista com as curvas cadastradas.
"""
import math

from qgis.core import QgsEditorWidgetSetup, QgsExpression, QgsFeature, QgsFeatureRequest
from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QMessageBox, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from . import estilo

FORMAS = [("1", "Ponto de projeto (1 ponto)"), ("3", "Padrão (3 pontos: shutoff, projeto, máxima)"),
          ("n", "Vários pontos (4 ou mais)")]
TIPO_BOMBA = "BOMBA"


# ---------------------------------------------------------------- regras da curva (as mesmas do EPANET)
def forma(pts):
    return "1" if len(pts) == 1 else "3" if len(pts) == 3 else "n"


def problemas(pts):
    """Lista de problemas (vazia = curva válida para o EPANET)."""
    if not pts:
        return ["a curva não tem pontos"]
    if len(pts) == 2:
        return ["o EPANET não aceita curva de 2 pontos: use 1 (ponto de projeto), 3 ou mais"]
    out = []
    qs, hs = [q for q, _ in pts], [h for _, h in pts]
    if any(q < 0 for q in qs) or any(h <= 0 for h in hs):
        out.append("vazão não pode ser negativa e altura tem que ser maior que zero")
    if len(pts) == 1 and qs[0] <= 0:
        out.append("o ponto de projeto precisa de vazão maior que zero")
    if any(b <= a for a, b in zip(qs, qs[1:])):
        out.append("as vazões têm que crescer de um ponto para o outro")
    if any(b >= a for a, b in zip(hs, hs[1:])):
        out.append("as alturas têm que diminuir conforme a vazão aumenta")
    if len(pts) == 3 and qs[0] != 0:
        out.append("na curva padrão o primeiro ponto é o shutoff: vazão 0")
    return out


def tracado(pts, n=60):
    """Pontos da curva como o EPANET a usa (para o gráfico)."""
    if problemas(pts):
        return sorted(pts)
    if len(pts) == 1:
        q, h = pts[0]
        a, c = 1.3333 * h, 2.0
        b = (a - h) / q ** c
        qmax = (a / b) ** (1 / c)
        return [(qmax * i / n, a - b * (qmax * i / n) ** c) for i in range(n + 1)]
    if len(pts) == 3:
        (_, h0), (q1, h1), (q2, h2) = pts
        try:
            c = math.log((h0 - h2) / (h0 - h1)) / math.log(q2 / q1)
            b = (h0 - h1) / q1 ** c
            qmax = (h0 / b) ** (1 / c)
            return [(qmax * i / n, max(0.0, h0 - b * (qmax * i / n) ** c)) for i in range(n + 1)]
        except (ValueError, ZeroDivisionError):
            return pts
    return pts


# ---------------------------------------------------------------- leitura e gravação no cadastro
def ler(camada):
    """{nome: [(q, h), ...]} só das curvas de bomba."""
    curvas = {}
    for f in camada.getFeatures():
        tipo = str(f["tipo"] or TIPO_BOMBA).upper()
        if tipo not in (TIPO_BOMBA, "NULL", "PUMP"):
            continue
        curvas.setdefault(str(f["id_curva"]), []).append((float(f["x"]), float(f["y"])))
    return {k: sorted(v) for k, v in curvas.items()}


def gravar(camada, curvas, removidas=()):
    """Substitui na tabela as curvas editadas e remove as excluídas; salva a tabela."""
    if not camada.isEditable():
        camada.startEditing()
    tirar = set(curvas) | set(removidas)
    apagar = [f.id() for f in camada.getFeatures() if str(f["id_curva"]) in tirar
              and str(f["tipo"] or TIPO_BOMBA).upper() in (TIPO_BOMBA, "NULL", "PUMP")]
    camada.deleteFeatures(apagar)
    novas = []
    for nome, pts in curvas.items():
        for q, h in sorted(pts):
            f = QgsFeature(camada.fields())
            f["id_curva"], f["tipo"], f["x"], f["y"] = nome, TIPO_BOMBA, float(q), float(h)
            novas.append(f)
    camada.addFeatures(novas)
    if not camada.commitChanges():
        raise RuntimeError("; ".join(camada.commitErrors()))


def lista_na_bomba(bombas, nomes):
    """Campo `curva` da camada de bombas vira lista com as curvas cadastradas (como no WaterGEMS)."""
    idx = bombas.fields().indexOf("curva")
    if idx < 0:
        return
    mapa = [{"(sem curva)": None}] + [{n: n} for n in sorted(nomes)]
    bombas.setEditorWidgetSetup(idx, QgsEditorWidgetSetup("ValueMap", {"map": mapa}))


def usada_por(bombas, nome):
    filtro = f'"curva" = {QgsExpression.quotedValue(nome)}'
    return [str(f["id"]) for f in bombas.getFeatures(QgsFeatureRequest().setFilterExpression(filtro))]


# ---------------------------------------------------------------- gráfico
class Grafico(QWidget):
    def __init__(self):
        super().__init__()
        self.pts, self.curva, self.ok = [], [], True
        self.setMinimumSize(320, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def mostrar(self, pts):
        self.pts = sorted(pts)
        self.ok = not problemas(self.pts)
        self.curva = tracado(self.pts)
        self.update()

    def paintEvent(self, _):
        c = estilo.COR
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(c["panel"]))
        m = QRectF(46, 14, self.width() - 60, self.height() - 46)
        todos = self.curva + self.pts
        qmax = max([q for q, _ in todos] + [1]) * 1.08
        hmax = max([h for _, h in todos] + [1]) * 1.12
        xy = lambda q, h: QPointF(m.left() + q / qmax * m.width(), m.bottom() - h / hmax * m.height())
        p.setFont(estilo.fonte("mono", 7))
        for i in range(6):  # grade e eixos
            x = m.left() + m.width() * i / 5
            y = m.bottom() - m.height() * i / 5
            p.setPen(QPen(QColor(c["grid"]), 1))
            p.drawLine(QPointF(x, m.top()), QPointF(x, m.bottom()))
            p.drawLine(QPointF(m.left(), y), QPointF(m.right(), y))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(x - 25, m.bottom() + 4, 50, 14), Qt.AlignmentFlag.AlignCenter, f"{qmax * i / 5:.0f}")
            p.drawText(QRectF(0, y - 7, 40, 14), Qt.AlignmentFlag.AlignRight, f"{hmax * i / 5:.0f}")
        p.drawText(QRectF(m.left(), self.height() - 16, m.width(), 14), Qt.AlignmentFlag.AlignCenter,
                   "VAZÃO (L/s)")
        p.save()
        p.translate(10, m.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-60, -6, 120, 14), Qt.AlignmentFlag.AlignCenter, "ALTURA (m)")
        p.restore()
        if len(self.curva) >= 2:
            cam = QPainterPath(xy(*self.curva[0]))
            for q, h in self.curva[1:]:
                cam.lineTo(xy(q, h))
            p.setPen(QPen(QColor(c["cyan"] if self.ok else c["crit"]), 2.2))
            p.drawPath(cam)
        p.setPen(QPen(QColor(c["bg"]), 1.5))
        p.setBrush(QColor(c["warn"]))
        for q, h in self.pts:
            p.drawEllipse(xy(q, h), 4.5, 4.5)
        p.end()


# ---------------------------------------------------------------- janela
class JanelaCurvas(QDialog):
    def __init__(self, pai, plugin):
        super().__init__(pai)
        self.plugin = plugin
        self.tabela_cad, self.bombas = plugin.camada("curva"), plugin.camada("bomba")
        self.curvas = ler(self.tabela_cad)
        self.originais = set(self.curvas)
        self.removidas, self.renomes = set(), {}
        self.atual = None
        self.setWindowTitle("GWATER · Curvas de bomba")
        self.setObjectName("gwater")
        self.setStyleSheet(estilo.qss())
        self.resize(860, 560)

        raiz = QVBoxLayout(self)
        exp = QLabel("Cadastre aqui as curvas das bombas (vazão × altura manométrica). Depois, no formulário de cada "
                     "bomba, escolha a curva na lista do campo <b>curva</b>, ou selecione bombas no mapa e use "
                     "<b>Usar nas bombas selecionadas</b>.")
        exp.setObjectName("sub")
        exp.setWordWrap(True)
        raiz.addWidget(exp)
        corpo = QHBoxLayout()
        raiz.addLayout(corpo, 1)

        # ---- lista de curvas
        esq = QVBoxLayout()
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._selecionar)
        esq.addWidget(self.lista, 1)
        bts = QHBoxLayout()
        for txt, f, dica in (("Nova", self._nova, "Cria uma curva nova"),
                             ("Duplicar", self._duplicar, "Copia a curva selecionada com outro nome"),
                             ("Excluir", self._excluir, "Remove a curva (avisa se alguma bomba usa)")):
            b = QPushButton(txt)
            b.setToolTip(dica)
            b.clicked.connect(f)
            bts.addWidget(b)
        esq.addLayout(bts)
        caixa_esq = QWidget()
        caixa_esq.setLayout(esq)
        caixa_esq.setFixedWidth(230)
        corpo.addWidget(caixa_esq)

        # ---- edição
        dir_ = QVBoxLayout()
        form = QFormLayout()
        self.nome = QLineEdit()
        self.nome.setToolTip("Nome da curva (é o que aparece na lista da bomba). Ex.: KSB_MEGANORM_65-200")
        self.nome.editingFinished.connect(self._renomear)
        form.addRow("Nome:", self.nome)
        self.forma = QComboBox()
        for k, t in FORMAS:
            self.forma.addItem(t, k)
        self.forma.setToolTip("Como o EPANET monta a curva a partir dos pontos")
        self.forma.activated.connect(self._mudar_forma)
        form.addRow("Definição:", self.forma)
        dir_.addLayout(form)
        meio = QHBoxLayout()
        tab = QVBoxLayout()
        self.pontos = QTableWidget(0, 2)
        self.pontos.setHorizontalHeaderLabels(["Vazão (L/s)", "Altura (m)"])
        self.pontos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pontos.verticalHeader().setVisible(False)
        self.pontos.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pontos.itemChanged.connect(self._editou)
        self.pontos.setFixedWidth(230)
        tab.addWidget(self.pontos, 1)
        bp = QHBoxLayout()
        self.mais, self.menos = QPushButton("+ ponto"), QPushButton("− ponto")
        self.mais.clicked.connect(self._mais_ponto)
        self.menos.clicked.connect(self._menos_ponto)
        bp.addWidget(self.mais)
        bp.addWidget(self.menos)
        tab.addLayout(bp)
        meio.addLayout(tab)
        self.grafico = Grafico()
        meio.addWidget(self.grafico, 1)
        dir_.addLayout(meio, 1)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        dir_.addWidget(self.msg)
        corpo.addLayout(dir_, 1)

        # ---- rodapé
        pe = QHBoxLayout()
        self.aplicar = QPushButton()
        self.aplicar.setToolTip("Coloca a curva atual no campo curva das bombas selecionadas no mapa")
        self.aplicar.clicked.connect(self._aplicar_selecionadas)
        pe.addWidget(self.aplicar)
        pe.addStretch(1)
        salvar, fechar = QPushButton("Salvar"), QPushButton("Fechar")
        salvar.setDefault(True)
        salvar.clicked.connect(self.salvar)
        fechar.clicked.connect(self.reject)
        pe.addWidget(salvar)
        pe.addWidget(fechar)
        raiz.addLayout(pe)

        self._preencher_lista()
        self._atualizar_aplicar()

    # ------------------------------------------------ lista
    def _preencher_lista(self, escolher=None):
        self.lista.blockSignals(True)
        self.lista.clear()
        self.lista.addItems(sorted(self.curvas))
        self.lista.blockSignals(False)
        alvo = escolher or (sorted(self.curvas)[0] if self.curvas else None)
        if alvo:
            self.lista.setCurrentRow(sorted(self.curvas).index(alvo))
        else:
            self._selecionar(None)

    def _nome_livre(self, base):
        n, nome = 1, base
        while nome in self.curvas:
            n += 1
            nome = f"{base}_{n}"
        return nome

    def _nova(self):
        nome = self._nome_livre("CURVA_NOVA")
        self.curvas[nome] = [(10.0, 30.0)]
        self._preencher_lista(nome)
        self.nome.setFocus()
        self.nome.selectAll()

    def _duplicar(self):
        if self.atual:
            nome = self._nome_livre(self.atual + "_COPIA")
            self.curvas[nome] = list(self.curvas[self.atual])
            self._preencher_lista(nome)

    def _excluir(self):
        if not self.atual:
            return
        usam = usada_por(self.bombas, self.atual)
        if usam:
            r = QMessageBox.question(self, "GWATER", f"A curva {self.atual} é usada por: {', '.join(usam)}.\n\n"
                                     "Excluir mesmo assim? Essas bombas vão aparecer como erro na validação.")
            if r != QMessageBox.StandardButton.Yes:
                return
        if self.atual in self.originais:
            self.removidas.add(self.atual)
        del self.curvas[self.atual]
        self._preencher_lista()

    def _renomear(self):
        novo = self.nome.text().strip().replace(" ", "_")
        if not self.atual or not novo or novo == self.atual:
            self.nome.setText(self.atual or "")
            return
        if novo in self.curvas:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>Já existe uma curva {novo}.</span>")
            self.nome.setText(self.atual)
            return
        self.curvas[novo] = self.curvas.pop(self.atual)
        if self.atual in self.originais:
            self.removidas.add(self.atual)
        origem = next((k for k, v in self.renomes.items() if v == self.atual), self.atual)
        self.renomes[origem] = novo
        self._preencher_lista(novo)

    # ------------------------------------------------ pontos
    def _selecionar(self, nome):
        self.atual = nome or None
        tem = self.atual is not None
        for w in (self.nome, self.forma, self.pontos, self.mais, self.menos):
            w.setEnabled(tem)
        self.nome.setText(self.atual or "")
        self.pontos.blockSignals(True)
        self.pontos.setRowCount(0)
        for q, h in (self.curvas.get(self.atual, []) if tem else []):
            r = self.pontos.rowCount()
            self.pontos.insertRow(r)
            self.pontos.setItem(r, 0, QTableWidgetItem(f"{q:g}"))
            self.pontos.setItem(r, 1, QTableWidgetItem(f"{h:g}"))
        self.pontos.blockSignals(False)
        if tem:
            self.forma.setCurrentIndex([k for k, _ in FORMAS].index(forma(self.curvas[self.atual])))
        self._conferir()

    def _ler_tabela(self):
        pts = []
        for r in range(self.pontos.rowCount()):
            try:
                q = float(self.pontos.item(r, 0).text().replace(",", "."))
                h = float(self.pontos.item(r, 1).text().replace(",", "."))
                pts.append((q, h))
            except (AttributeError, ValueError):
                pass
        return pts

    def _editou(self, _item=None):
        if self.atual:
            self.curvas[self.atual] = self._ler_tabela()
            self._conferir()

    def _escrever(self, pts):
        self.curvas[self.atual] = pts
        self._selecionar(self.atual)

    def _mudar_forma(self):
        if not self.atual:
            return
        pts, k = sorted(self.curvas[self.atual]), self.forma.currentData()
        proj = pts[len(pts) // 2] if pts else (10.0, 30.0)
        if k == "1":
            self._escrever([proj] if proj[0] > 0 else [(10.0, 30.0)])
        elif k == "3":
            q, h = proj if proj[0] > 0 else (10.0, 30.0)
            self._escrever([(0.0, round(h * 1.33, 2)), (q, h), (round(q * 1.5, 2), round(h * 0.6, 2))])
        elif len(pts) < 4:
            q, h = proj if proj[0] > 0 else (10.0, 30.0)
            self._escrever([(0.0, round(h * 1.33, 2)), (round(q * 0.5, 2), round(h * 1.2, 2)), (q, h),
                            (round(q * 1.5, 2), round(h * 0.6, 2))])

    def _mais_ponto(self):
        if self.atual:
            pts = sorted(self.curvas[self.atual]) or [(0.0, 40.0)]
            q, h = pts[-1]
            self._escrever(pts + [(round(q * 1.2 + 1, 2), round(h * 0.8, 2))])

    def _menos_ponto(self):
        if self.atual and self.curvas[self.atual]:
            linha = self.pontos.currentRow()
            pts = sorted(self.curvas[self.atual])
            pts.pop(linha if 0 <= linha < len(pts) else -1)
            self._escrever(pts)

    def _conferir(self):
        if not self.atual:
            self.grafico.mostrar([])
            self.msg.setText("Nenhuma curva cadastrada. Clique em <b>Nova</b>.")
            return
        pts = sorted(self.curvas[self.atual])
        self.grafico.mostrar(pts)
        erros = problemas(pts)
        usam = usada_por(self.bombas, self.atual)
        uso = f" · usada por {', '.join(usam)}" if usam else " · nenhuma bomba usa esta curva ainda"
        if erros:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>✗ {'; '.join(erros)}</span>")
        else:
            self.msg.setText(f"<span style='color:{estilo.COR['ok']}'>✓ curva válida para o EPANET</span>"
                             f"<span style='color:{estilo.COR['muted']}'>{uso}</span>")

    # ------------------------------------------------ bombas
    def _atualizar_aplicar(self):
        n = self.bombas.selectedFeatureCount()
        self.aplicar.setText(f"Usar nas bombas selecionadas ({n})")
        self.aplicar.setEnabled(n > 0)

    def _aplicar_selecionadas(self):
        if not self.atual:
            return
        if not self.bombas.isEditable():
            self.bombas.startEditing()
        idx = self.bombas.fields().indexOf("curva")
        for f in self.bombas.getSelectedFeatures():
            self.bombas.changeAttributeValue(f.id(), idx, self.atual)
        self._conferir()
        self.plugin.informar(f"curva {self.atual} aplicada a {self.bombas.selectedFeatureCount()} bomba(s). "
                             "Clique em Salvar edições.")

    # ------------------------------------------------ salvar
    def salvar(self):
        ruins = {n: problemas(sorted(p)) for n, p in self.curvas.items() if problemas(sorted(p))}
        if ruins:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>Corrija antes de salvar: " +
                             " | ".join(f"{n}: {e[0]}" for n, e in ruins.items()) + "</span>")
            self.lista.setCurrentRow(sorted(self.curvas).index(next(iter(ruins))))
            return
        try:
            gravar(self.tabela_cad, self.curvas, self.removidas)
        except RuntimeError as e:
            self.msg.setText(f"<span style='color:{estilo.COR['crit']}'>Não consegui salvar: {e}</span>")
            return
        if self.renomes:  # bombas que usavam o nome antigo passam a usar o novo
            idx = self.bombas.fields().indexOf("curva")
            for antigo, novo in self.renomes.items():
                for f in self.bombas.getFeatures():
                    if f["curva"] == antigo:
                        if not self.bombas.isEditable():
                            self.bombas.startEditing()
                        self.bombas.changeAttributeValue(f.id(), idx, novo)
        lista_na_bomba(self.bombas, self.curvas)
        self.plugin.informar(f"{len(self.curvas)} curva(s) de bomba salvas.")
        self.accept()
