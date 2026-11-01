"""Núcleo do GWATER.exe: o mesmo código do plugin (gwater/plugin.py) rodando fora do QGIS.

`Iface` imita a parte da interface do QGIS que o plugin usa (janela, mapa, barra de mensagens, desenhar,
abrir projeto). `Nucleo` herda do plugin todas as ações que já existiam (desenhar, validar, calcular,
TRex, ModelBuilder, curvas, cores...) e junta as novas, que ficam nos outros módulos de `programa`.
"""
import os
import time

from qgis.core import Qgis, QgsProject
from qgis.PyQt.QtCore import QObject, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from gwater import motor
from gwater.desenho import aplicar_prototipo
from gwater.dock import GwaterDock
from gwater.plugin import DESENHO, PAGINAS, GwaterPlugin

NOMES_WEB = {"mapa": "Mapa e propostas", "calibracao": "Calibração", "aovivo": "Ao vivo", "dados": "Dados recebidos",
             "sinotico": "Sinótico"}
# botões de desenho que são uma camada com um valor já escolhido (como os tipos do WaterGEMS)
DESENHO_TIPO = {
    "hidrante": ("no_juncao", {"tipo": "HIDRANTE"}), "ponto_consumo": ("consumidor", {}),
    "no": ("no_juncao", {"tipo": "JUNCAO"}),
    "valvula": ("valvula", {"tipo": "PRV"}), "valvula_prv": ("valvula", {"tipo": "PRV"}),
    "valvula_psv": ("valvula", {"tipo": "PSV"}), "valvula_pbv": ("valvula", {"tipo": "PBV"}),
    "valvula_fcv": ("valvula", {"tipo": "FCV"}), "valvula_tcv": ("valvula", {"tipo": "TCV", "status": "ABERTA"}),
    "valvula_gpv": ("valvula", {"tipo": "GPV"}), "registro": ("valvula", {"tipo": "REGISTRO", "status": "ABERTA"}),
}


class Iface(QObject):
    """O pedaço da interface do QGIS que o código do plugin usa, apontando para a janela do GWATER."""

    def __init__(self, janela):
        super().__init__(janela)
        self.janela = janela
        self._ativa = None
        self._add = QAction(self)
        self._add.triggered.connect(lambda: janela.desenhar(self._ativa))
        self._vertices = QAction(self)
        self._vertices.triggered.connect(lambda: janela.usar("mover"))
        self._identificar = QAction(self)
        self._identificar.triggered.connect(lambda: janela.usar("selecionar"))

    def mainWindow(self):
        return self.janela

    def mapCanvas(self):
        return self.janela.canvas

    def messageBar(self):
        return self.janela.barra_msg

    def layerTreeView(self):
        return self.janela.arvore

    def activeLayer(self):
        return self._ativa

    def setActiveLayer(self, lyr):
        self._ativa = lyr
        return True

    def actionAddFeature(self):
        return self._add

    def actionVertexTool(self):
        return self._vertices

    def actionIdentify(self):
        return self._identificar

    def newProject(self, perguntar=True):
        return self.janela.fechar_projeto(perguntar)

    def addProject(self, arq):
        return self.janela.abrir_projeto(arq)

    def addDockWidget(self, area, dock):
        self.janela.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        self.janela.removeDockWidget(dock)

    def addToolBar(self, nome):
        return self.janela.addToolBar(nome)


class Nucleo(GwaterPlugin):
    def __init__(self, janela):
        super().__init__(janela.iface)
        self.janela = janela
        self.cenario = None  # cenário ativo: {"id", "nome", "alteracoes", ...} ou None = rede atual

    # ------------------------------------------------ início (no lugar do initGui do plugin)
    def iniciar(self):
        self.dock = GwaterDock(self)
        self.dock.setWindowTitle("Cálculo")
        self.dock.setObjectName("GwaterCalculo")
        self.dock.cab.hide()
        self.dock.abas.removeTab(0)  # os botões da Central estão na faixa de menus
        self.dock.abas.setTabText(self.dock.aba_problemas - 1, "Notificações")
        self.dock.aba_problemas -= 1
        self.dock.aba_resultados -= 1
        self.dock.ALTURA_FAIXA = 230
        # notificações agrupadas por tipo de problema (como o User Notifications do WaterGEMS), no lugar da lista
        from .notificacoes import ArvoreNotificacoes
        self.arvore_notif = ArvoreNotificacoes(self)
        k = self.dock.aba_problemas
        self.dock.abas.removeTab(k)
        self.dock.abas.insertTab(k, self.arvore_notif, "Notificações")

        def mostrar_notificacoes(itens):
            self.arvore_notif.mostrar(itens)
            self.dock.abas.setTabText(self.dock.aba_problemas, f"Notificações ({len(itens)})")
            if itens:
                self.dock.abas.setCurrentIndex(self.dock.aba_problemas)
            return sum(1 for i in itens if i["nivel"] == "ERRO")
        self.dock.mostrar_problemas = mostrar_notificacoes
        # resumo do cálculo com rolagem: o painel não cresce a cada simulação
        from qgis.PyQt.QtWidgets import QScrollArea
        caixa = self.dock.resumo.parentWidget()
        rolar = QScrollArea()
        rolar.setWidgetResizable(True)
        lay = caixa.layout()
        lay.removeWidget(self.dock.resumo)
        rolar.setWidget(self.dock.resumo)
        lay.addWidget(rolar, 1)
        prj = QgsProject.instance()
        prj.layersAdded.connect(self._camadas_adicionadas)
        prj.layersWillBeRemoved.connect(self.topologia.camadas_saindo)
        prj.cleared.connect(self.topologia.desconectar)

    def tem(self, chave):
        return hasattr(self, f"acao_{chave}")

    def executar(self, chave):
        f = getattr(self, f"acao_{chave}", None)
        if f is None:
            return self.aviso(f"'{chave}' ainda não está disponível nesta versão.")
        try:
            f()
        except LookupError as e:  # camada do cadastro que falta no projeto
            self.aviso(str(e))

    def mostrar_dock(self):
        self.dock.show()
        self.dock.raise_()

    def projetados(self):
        return self.dock.projetados.isChecked()

    def alteracoes(self):
        """Alterações do cenário ativo (formato do conversor), ou None para a rede atual."""
        if not self.cenario:
            return None
        from .cenarios_ui import alteracoes_completas
        return alteracoes_completas(self.cenario)

    def camadas_rede(self):
        out = []
        for n in ("captacao", "reservatorio", "bomba", "valvula", "no_juncao", "trecho", "consumidor"):
            try:
                out.append(self.camada(n))
            except LookupError:
                pass
        return out

    # ------------------------------------------------ desenho
    def _desenhar(self, chave, valores=None):
        if not self._cadastro_ok():
            return
        nome = DESENHO.get(chave) or DESENHO_TIPO[chave][0]
        lyr = self.camada(nome)
        self._editar_rede()
        self.garantir_encaixe()
        # protótipo do botão (tipo do nó, tipo da válvula...) como valor padrão do formulário
        from qgis.core import QgsDefaultValue
        padroes = self.janela.prototipos_tipo.get(nome, {})
        for campo, valor in {**padroes, **(valores or {})}.items():
            i = lyr.fields().indexOf(campo)
            if i >= 0:
                lyr.setDefaultValueDefinition(i, QgsDefaultValue(repr(valor) if isinstance(valor, str) else str(valor)))
        self.iface.setActiveLayer(lyr)
        self.janela.desenhar(lyr, chave)
        from . import catalogo
        texto, _, desc = catalogo.todos().get(chave, (chave, "", ""))
        self.dock.status.setText(f"<b>Desenhando: {texto}</b>. {desc} Esc para parar.")

    def _tipo(self, chave):
        nome, valores = DESENHO_TIPO[chave]
        self._desenhar(chave, valores)

    def acao_mover(self):
        if self._cadastro_ok():
            self._editar_rede()
            self.garantir_encaixe()
            self.janela.usar("mover")
            self.dock.status.setText("<b>Mover</b>: arraste um elemento ou um vértice de tubulação. As tubulações "
                                     "ligadas acompanham.")

    def acao_atributos(self):
        self.janela.usar("selecionar")
        self.janela.mostrar_painel("propriedades")

    def prototipo_mudou(self, *a, salvar=True):
        GwaterPlugin.prototipo_mudou(self, *a, salvar=salvar)
        from .consumidores import formulario
        formulario(self)

    # ------------------------------------------------ cálculo com o cenário ativo
    def _motor(self, acao, alvo, extras, texto):
        """Como no plugin, mas validar/simular/exportar levam as alterações do cenário ativo."""
        alts = self.alteracoes()
        if not alts or acao not in ("validar", "simular", "exportar"):
            return GwaterPlugin._motor(self, acao, alvo, extras, texto)
        import json
        import tempfile
        fd, arq = tempfile.mkstemp(suffix=".json", prefix="gwater_cen_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(alts, f, ensure_ascii=False)
        try:
            return GwaterPlugin._motor(self, acao, alvo, list(extras) + [f"--alteracoes={arq}"],
                                       texto + f" (cenário {self.cenario['nome']})")
        finally:
            os.remove(arq)

    def acao_simular(self):
        GwaterPlugin.acao_simular(self)
        if self.res:
            self.janela.resultados_mudaram()

    simular = acao_simular

    def acao_limpar(self):
        GwaterPlugin.acao_limpar(self)
        self.janela.resultados_mudaram()

    # ------------------------------------------------ Centro de Operações dentro do programa
    def abrir_painel(self, pagina="mapa"):
        gpkg = self.cadastro()
        if not gpkg:
            return self.aviso("Abra um cadastro GWATER primeiro.")
        if motor.painel_no_ar() and motor.versao_painel() < motor.VERSAO_PAINEL:
            if not motor.encerrar_painel() and self.servidor:
                self.servidor.terminate()
            self.servidor = None
        if motor.painel_no_ar() and motor.trocar_cadastro(gpkg) is None:
            motor.encerrar_painel()
        if not motor.painel_no_ar():
            self.servidor = motor.iniciar_painel(gpkg)
            for _ in range(50):
                QApplication.processEvents()
                time.sleep(0.2)
                if motor.painel_no_ar():
                    break
        url = f"http://127.0.0.1:{motor.PORTA_PAINEL}/{PAGINAS[pagina]}"  # o servidor só escuta no IPv4
        if not self.janela.abrir_web(url, NOMES_WEB.get(pagina, pagina)):
            QDesktopServices.openUrl(QUrl(url))

    def acao_central(self):
        self.mostrar_dock()

    # ------------------------------------------------ arquivo
    def acao_abrir(self):
        arq, _ = QFileDialog.getOpenFileName(self.janela, "Abrir cadastro GWATER", self.janela.pasta_padrao(),
                                             "Projeto GWATER (*.qgz *.qgs);;Cadastro (*.gpkg)")
        if not arq:
            return
        if arq.lower().endswith(".gpkg"):
            arq = self.janela.projeto_do_gpkg(arq)
            if not arq:
                return
        if self.iface.newProject(True):
            self.iface.addProject(arq)

    def acao_salvar(self):
        """Ctrl+S: grava todas as camadas do cadastro com edições (rede e tabelas), sem sair da edição."""
        if not self._cadastro_ok():
            return
        salvas, erros = self.janela.salvar_camadas()
        if erros:
            return
        if salvas:
            self.aviso("Salvo: " + ", ".join(salvas), Qgis.MessageLevel.Success)
        else:
            self.informar("Nada para salvar.")

    def acao_salvar_projeto(self):
        if QgsProject.instance().fileName():
            QgsProject.instance().write()
            self.informar("Projeto salvo.")

    def acao_sair(self):
        self.janela.close()

    def acao_desfazer(self):
        self.janela.desfazer()

    def acao_refazer(self):
        self.janela.refazer()

    def acao_sobre(self):
        QMessageBox.about(self.janela, "GWATER",
                          "<h3>GWATER · REV 0.2.0</h3><p>Cadastro, modelagem hidráulica (EPANET 2.2) e operação de "
                          "redes de água, em software livre.</p><p>Mapa e edição: bibliotecas do QGIS "
                          f"{Qgis.version()}.<br>Cálculo: EPANET 2.2 pelo WNTR.</p>")

    def acao_guia(self):
        from . import ajuda
        ajuda.guia(self)


for _k in DESENHO_TIPO:
    setattr(Nucleo, f"acao_{_k}", (lambda k: lambda self: self._tipo(k))(_k))
del _k


def instalar_acoes():
    """Liga as ações dos módulos ao Núcleo (cada módulo tem um dicionário ACOES {chave: função(nucleo)})."""
    from . import (analise_ui, ajuda, assistente, calibracao_ui, cenarios_ui, componentes, consumidores, componentes_extra, desenho_extra, consultas, ferramentas_modelo, graficos,
                   modelbuilder_ui, regras, relatorios, revisao, selecao, tabelas, vistas)
    for mod in (analise_ui, ajuda, assistente, calibracao_ui, cenarios_ui, componentes, consumidores, componentes_extra, desenho_extra, consultas, ferramentas_modelo, graficos, modelbuilder_ui,
                regras, relatorios, revisao, selecao, tabelas, vistas):
        for chave, func in getattr(mod, "ACOES", {}).items():
            setattr(Nucleo, f"acao_{chave}", (lambda f: lambda self: f(self))(func))
