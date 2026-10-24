"""GWATER para QGIS: barra de ferramentas + painel lateral."""
import time

from qgis.core import Qgis, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction  # Qt6 / QGIS 4
except ImportError:
    from qgis.PyQt.QtWidgets import QAction  # Qt5 / QGIS 3

from . import motor
from .dock import GwaterDock, icone
from .resultados import Resultados

MENU = "&GWATER"


class GwaterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock = self.res = self.servidor = None
        self.acoes = []

    # ------------------------------------------------ ciclo de vida
    def initGui(self):
        self.barra = self.iface.addToolBar("GWATER")
        self.barra.setObjectName("GwaterToolbar")
        for texto, nome, func in (("GWATER · painel de simulação", "gwater", self.mostrar_dock),
                                  ("Validar rede", "validar", self.validar),
                                  ("Simular no EPANET", "simular", self.simular),
                                  ("Abrir Centro de Operações (web)", "painel", self.abrir_painel)):
            a = QAction(icone(nome), texto, self.iface.mainWindow())
            a.triggered.connect(func)
            self.barra.addAction(a)
            self.iface.addPluginToMenu(MENU, a)
            self.acoes.append(a)
        self.dock = GwaterDock(self)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()

    def unload(self):
        for a in self.acoes:
            self.iface.removePluginMenu(MENU, a)
        self.iface.mainWindow().removeToolBar(self.barra)
        self.barra.deleteLater()
        if self.dock:
            self.dock.parar()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
        if self.servidor:
            self.servidor.terminate()

    def mostrar_dock(self):
        self.dock.show()
        self.dock.raise_()

    def aviso(self, texto, nivel=Qgis.MessageLevel.Warning):
        self.iface.messageBar().pushMessage("GWATER", texto, level=nivel, duration=8)

    # ------------------------------------------------ cadastro do projeto aberto
    def _camadas_gpkg(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.providerType() == "ogr" and "|layername=" in lyr.source():
                caminho, resto = lyr.source().split("|", 1)
                yield caminho, resto.split("layername=")[1].split("|")[0], lyr

    def cadastro(self):
        for caminho, nome, _ in self._camadas_gpkg():
            if nome == "trecho":
                return caminho
        return None

    def camada(self, nome):
        gpkg = self.cadastro()
        for caminho, n, lyr in self._camadas_gpkg():
            if caminho == gpkg and n == nome:
                return lyr
        raise LookupError(f"camada '{nome}' do cadastro não está no projeto")

    def _preparar(self):
        """Confere se há cadastro e salva edições pendentes (o motor lê o arquivo em disco)."""
        gpkg = self.cadastro()
        if not gpkg:
            self.aviso("Nenhum cadastro GWATER no projeto (falta a camada 'trecho' de um GeoPackage).")
            return None
        pendentes = [l for c, _, l in self._camadas_gpkg() if c == gpkg and l.isEditable() and l.isModified()]
        if pendentes:
            r = QMessageBox.question(
                self.iface.mainWindow(), "GWATER",
                "Há edições não salvas em: " + ", ".join(l.name() for l in pendentes) +
                ".\n\nSalvar antes de rodar? (o motor lê o cadastro gravado em disco)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                return None
            if r == QMessageBox.StandardButton.Yes:
                for l in pendentes:
                    if not l.commitChanges(False):
                        self.aviso(f"não consegui salvar {l.name()}: {'; '.join(l.commitErrors())}",
                                   Qgis.MessageLevel.Critical)
                        return None
        return gpkg

    def _rodar(self, acao):
        gpkg = self._preparar()
        if not gpkg:
            return None
        self.mostrar_dock()
        self.dock.status.setText("Calculando no EPANET…" if acao == "simular" else "Validando a rede…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        t0 = time.perf_counter()
        try:
            dados = motor.rodar(acao, gpkg, self.dock.projetados.isChecked())
        except Exception as e:
            self.dock.status.setText("Falha ao chamar o motor.")
            self.aviso(f"falha ao chamar o motor: {e}", Qgis.MessageLevel.Critical)
            return None
        finally:
            QApplication.restoreOverrideCursor()
        erros = self.dock.mostrar_problemas(dados.get("itens", []))
        avisos = len(dados.get("itens", [])) - erros
        if erros:
            self.dock.status.setText(f"<b style='color:#e5484d'>{erros} erro(s)</b> e {avisos} aviso(s). "
                                     "Corrija e rode de novo (clique duplo leva até o elemento).")
            return None
        self.dock.status.setText(f"Rede válida · {avisos} aviso(s) · {time.perf_counter() - t0:.1f} s")
        return dados

    # ------------------------------------------------ ações
    def validar(self):
        if self._rodar("validar"):
            self.aviso("Rede válida: pronta para simular.", Qgis.MessageLevel.Success)

    def simular(self):
        dados = self._rodar("simular")
        if not dados:
            return
        self.dock.parar()
        self.res = Resultados(self, dados)
        self.dock.carregar(self.res)
        self.dock.status.setText(self.dock.status.text() +
                                 f" · EPANET {dados['tempo_calculo_s'] * 1000:.0f} ms · modelo salvo em {dados['inp']}")

    def ir_ate(self, camada, fid):
        try:
            lyr = self.camada(camada)
        except LookupError as e:
            return self.aviso(str(e))
        lyr.selectByExpression(f"\"id\" = '{fid}'")
        if lyr.selectedFeatureCount():
            self.iface.setActiveLayer(lyr)
            self.iface.mapCanvas().zoomToSelected(lyr)
            self.iface.mapCanvas().flashFeatureIds(lyr, lyr.selectedFeatureIds())

    def abrir_painel(self):
        gpkg = self.cadastro()
        if not gpkg:
            return self.aviso("Abra um projeto com o cadastro GWATER primeiro.")
        if not motor.painel_no_ar():
            self.servidor = motor.iniciar_painel(gpkg)
            for _ in range(40):  # até ~8 s para o servidor subir
                QApplication.processEvents()
                time.sleep(0.2)
                if motor.painel_no_ar():
                    break
        QDesktopServices.openUrl(QUrl(f"http://localhost:{motor.PORTA_PAINEL}/mapa.html"))
