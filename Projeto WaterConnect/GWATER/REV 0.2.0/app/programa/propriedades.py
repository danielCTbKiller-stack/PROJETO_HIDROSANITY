"""Painel Propriedades (como o do WaterGEMS): dados e resultados do elemento selecionado.

Um elemento: formulário do cadastro (editável) e os resultados da hora escolhida (pressão, carga,
demanda; vazão, velocidade, perda; nível do reservatório; mínimo e máximo do dia).
Vários elementos do mesmo tipo: muda um campo em todos de uma vez.
"""
from qgis.core import QgsFeatureRequest
from qgis.gui import QgsAttributeEditorContext, QgsAttributeForm
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox, QDockWidget, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from gwater.estilo import COR

from .util import NOMES, num


def _nome_camada(nucleo, lyr):
    for c in NOMES:
        try:
            if nucleo.camada(c) == lyr:
                return c
        except LookupError:
            pass
    return None


def resultados_elemento(res, camada, eid, k):
    """[(rótulo, valor no passo k, unidade, mín do dia, máx do dia)] de um elemento."""
    if res is None:
        return []
    d = res.d
    out = []

    def serie(rot, s, un, casas=2):
        out.append((rot, s[k], un, min(s), max(s), casas))

    if camada == "trecho" or camada in ("bomba", "valvula"):
        l = d["links"].get(eid)
        if l:
            serie("Vazão", l["q"], "L/s")
            serie("Velocidade", [abs(x) for x in l["v"]], "m/s")
            if camada == "trecho":
                serie("Perda de carga", [abs(x) for x in l["hl"]], "m/km")
            st = {0: "fechado(a)", 1: "aberto(a)", 2: "ativo(a)"}.get(l["s"][k], str(l["s"][k]))
            out.append(("Estado", st, "", None, None, 0))
    if camada in ("bomba", "valvula"):
        for lado, rot in (("M", "montante"), ("J", "jusante")):
            n = d["nos"].get(f"{eid}__{lado}")
            if n:
                serie(f"Pressão {rot}", n["p"], "mca", 1)
        m, j = d["nos"].get(f"{eid}__M"), d["nos"].get(f"{eid}__J")
        if m and j:
            serie("Altura (jusante − montante)" if camada == "bomba" else "Perda na válvula",
                  [b - a if camada == "bomba" else a - b for a, b in zip(m["h"], j["h"])], "m", 1)
    if camada in ("no_juncao", "captacao", "reservatorio"):
        n = d["nos"].get(eid)
        if n:
            if camada == "reservatorio":
                serie("Nível", n["p"], "m")
                serie("Cota da água", n["h"], "m")
            elif camada == "captacao":
                serie("Carga", n["h"], "m")
                serie("Vazão fornecida", [-x for x in n["d"]], "L/s")
            else:
                serie("Pressão", n["p"], "mca", 1)
                serie("Carga hidráulica", n["h"], "m", 1)
                serie("Demanda entregue", n["d"], "L/s", 3)
                if "de" in n:
                    pedido = n["de"][k]
                    out.append(("Atendimento", 100 * n["d"][k] / pedido if pedido > 1e-9 else 100.0, "%",
                                None, None, 0))
    return out


class PainelPropriedades(QDockWidget):
    def __init__(self, janela):
        super().__init__("Propriedades", janela)
        self.setObjectName("GwaterPropriedades")
        self.janela = janela
        self.form = None
        corpo = QWidget()
        self.v = QVBoxLayout(corpo)
        self.v.setContentsMargins(6, 6, 6, 6)
        self.titulo = QLabel("Nada selecionado")
        self.titulo.setStyleSheet(f"font-size:11pt; font-weight:700; color:{COR['cyan']}")
        self.titulo.setWordWrap(True)
        self.v.addWidget(self.titulo)
        self.sub = QLabel("Clique num elemento no mapa (ferramenta Selecionar) para ver e editar os dados dele.")
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet(f"color:{COR['muted']}")
        self.v.addWidget(self.sub)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.Shape.NoFrame)
        self.v.addWidget(self.area, 1)
        self.botoes = QHBoxLayout()
        self.b_editar = QPushButton("Editar")
        self.b_editar.setToolTip("Liga a edição do cadastro para mudar os valores")
        self.b_editar.clicked.connect(self._editar)
        self.b_aplicar = QPushButton("Aplicar")
        self.b_aplicar.setToolTip("Passa os valores do formulário para o elemento (grava no arquivo com Salvar edições)")
        self.b_aplicar.clicked.connect(self._aplicar)
        self.botoes.addWidget(self.b_editar)
        self.botoes.addStretch(1)
        self.botoes.addWidget(self.b_aplicar)
        self.v.addLayout(self.botoes)
        self.setWidget(corpo)
        janela.selecao.connect(self.atualizar)
        janela.resultados.connect(self.atualizar)

    # ------------------------------------------------
    def atualizar(self):
        if not self.isVisible():
            return
        nucleo = self.janela.nucleo
        sel = self.janela.selecionados()
        self.form = None
        self.lyr = self.fid = None
        conteudo = QWidget()
        lay = QVBoxLayout(conteudo)
        lay.setContentsMargins(0, 0, 0, 0)
        total = sum(len(f) for _, f in sel)
        if total == 0:
            self.titulo.setText("Nada selecionado")
            self.sub.setText("Clique num elemento no mapa (ferramenta Selecionar) para ver e editar os dados dele.")
            self.sub.show()
            self.b_editar.hide()
            self.b_aplicar.hide()
        elif total == 1:
            lyr, fids = sel[0]
            f = lyr.getFeature(fids[0])
            self.lyr, self.fid = lyr, f.id()
            camada = _nome_camada(nucleo, lyr)
            self.titulo.setText(f"{NOMES.get(camada, lyr.name())} {f['id'] if 'id' in f.fields().names() else ''}")
            self.sub.hide()
            res = resultados_elemento(nucleo.res, camada, str(f["id"]), self.janela.passo()) if nucleo.res else []
            if res:
                caixa = QFrame()
                caixa.setStyleSheet(f"QFrame{{background:{COR['panel2']}; border:1px solid {COR['line']};"
                                    f"border-radius:8px}} QLabel{{border:none}}")
                g = QFormLayout(caixa)
                from gwater.resultados import _hora
                cab = QLabel(f"<b>Resultados às {_hora(nucleo.res.horas[self.janela.passo()])}</b>"
                             f"{' · cenário ' + nucleo.cenario['nome'] if nucleo.cenario else ''}")
                g.addRow(cab)
                for rot, v, un, mn, mx, casas in res:
                    txt = f"<b>{num(v, casas) if isinstance(v, (int, float)) else v}</b> {un}"
                    if mn is not None:
                        txt += f"  <span style='color:{COR['muted']}'>(dia: {num(mn, casas)} a {num(mx, casas)})</span>"
                    g.addRow(rot + ":", QLabel(txt))
                lay.addWidget(caixa)
            ctx = QgsAttributeEditorContext()
            ctx.setMapCanvas(self.janela.canvas)
            self.form = QgsAttributeForm(lyr, f, ctx)
            lay.addWidget(self.form, 1)
            self.b_editar.setVisible(not lyr.isEditable())
            self.b_aplicar.setVisible(lyr.isEditable())
        else:
            self.titulo.setText(f"{total} elementos selecionados")
            self.sub.setText("Para mudar um campo em todos de uma vez, escolha o tipo, o campo e o valor.")
            self.sub.show()
            lay.addWidget(self._multipla(sel))
            self.b_editar.hide()
            self.b_aplicar.hide()
        lay.addStretch(1)
        self.area.setWidget(conteudo)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.atualizar()

    def _editar(self):
        if self.lyr is not None:
            self.janela.nucleo._editar_rede()
            self.atualizar()

    def _aplicar(self):
        if self.form is not None and self.lyr is not None and self.lyr.isEditable():
            self.form.save()
            self.janela.canvas.refresh()
            self.janela.nucleo.informar("Valores aplicados. Clique em Salvar edições para gravar no cadastro.")

    # ------------------------------------------------ vários elementos
    def _multipla(self, sel):
        w = QWidget()
        f = QFormLayout(w)
        tipo = QComboBox()
        for lyr, fids in sel:
            tipo.addItem(f"{lyr.name()} ({len(fids)})", lyr.id())
        campo = QComboBox()
        valor = QLineEdit()
        valor.setPlaceholderText("novo valor (vazio = apagar o valor)")
        dica = QLabel()
        dica.setWordWrap(True)
        dica.setStyleSheet(f"color:{COR['muted']}")

        def camada():
            from qgis.core import QgsProject
            return QgsProject.instance().mapLayer(tipo.currentData())

        def campos():
            campo.clear()
            lyr = camada()
            for fld in lyr.fields():
                if fld.name() not in ("fid", "id"):
                    campo.addItem(fld.name())
            mostrar()

        def mostrar():
            lyr = camada()
            if lyr is None or not campo.currentText():
                return
            vals = {str(x[campo.currentText()]) for x in lyr.getFeatures(lyr.selectedFeatureIds())}
            dica.setText("Valores atuais: " + ", ".join(sorted(vals)[:12]) + (" …" if len(vals) > 12 else ""))

        def aplicar():
            lyr = camada()
            if lyr is None:
                return
            i = lyr.fields().indexOf(campo.currentText())
            texto = valor.text().strip().replace(",", ".") if lyr.fields()[i].isNumeric() else valor.text()
            v = None if texto == "" else (float(texto) if lyr.fields()[i].isNumeric() else texto)
            if not lyr.isEditable():
                lyr.startEditing()
            lyr.beginEditCommand(f"Alterar {campo.currentText()}")
            for fid in lyr.selectedFeatureIds():
                lyr.changeAttributeValue(fid, i, v)
            lyr.endEditCommand()
            self.janela.canvas.refresh()
            self.janela.nucleo.informar(f"{campo.currentText()} = {valor.text()} em {lyr.selectedFeatureCount()} "
                                        f"elemento(s). Salvar edições grava no cadastro.")
            mostrar()

        tipo.currentIndexChanged.connect(campos)
        campo.currentIndexChanged.connect(mostrar)
        f.addRow("Tipo:", tipo)
        f.addRow("Campo:", campo)
        f.addRow("Valor:", valor)
        f.addRow(dica)
        b = QPushButton("Aplicar em todos")
        b.clicked.connect(aplicar)
        f.addRow(b)
        campos()
        return w
