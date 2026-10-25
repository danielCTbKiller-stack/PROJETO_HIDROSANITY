"""GWATER para QGIS: menu GWATER, barras Desenho e Modelo, e o painel Central GWATER.

Todos os botões vêm de acoes.py; cada chave chama o método acao_<chave> desta classe.
O que precisa de WNTR/EPANET roda no Python do projeto (motor.py); o desenho roda aqui dentro.
"""
import os
import time

from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox

try:
    from qgis.PyQt.QtGui import QAction  # Qt6 / QGIS 4
except ImportError:
    from qgis.PyQt.QtWidgets import QAction  # Qt5 / QGIS 3

from . import acoes, curvas, estilo, ferramentas, motor
from .desenho import Topologia, aplicar_prototipo
from .dock import GwaterDock, dica, icone
from .resultados import Resultados, limpar as limpar_resultados

PAGINAS = {"dados": "dados.html", "mapa": "mapa.html", "calibracao": "calibracao.html", "aovivo": "aovivo.html", "sinotico": "sinotico.html"}
DESENHO = {"tubulacao": "trecho", "no": "no_juncao", "valvula": "valvula", "bomba": "bomba",
           "reservatorio": "reservatorio", "captacao": "captacao"}
CHAVE_PROJETO = "GWATER"


class GwaterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock = self.res = self.servidor = self.menu = None
        self.qacoes, self.barras, self.janelas = {}, [], []
        self.topologia = Topologia(self)

    # ------------------------------------------------ ciclo de vida
    def initGui(self):
        janela = self.iface.mainWindow()
        for chave, (texto, ic, desc, _) in acoes.todas().items():
            a = QAction(icone(ic), texto, janela)
            a.setToolTip(dica(texto, desc))
            a.setStatusTip(desc)
            a.setWhatsThis(desc)
            a.setObjectName(f"gwater_{chave}")
            a.triggered.connect(lambda _=False, k=chave: self.executar(k))
            self.qacoes[chave] = a

        # menu próprio na barra de menus, antes de Ajuda
        self.menu = QMenu("&GWATER", janela.menuBar())
        self.menu.setObjectName("GwaterMenu")
        self.menu.setToolTipsVisible(True)
        self.menu.addAction(self.qacoes["central"])
        self.menu.addSeparator()
        for gid, titulo, _, lista in acoes.GRUPOS:
            if gid == "ajuda":
                self.menu.addSeparator()
                destino = self.menu
            else:
                destino = self.menu.addMenu(titulo)
                destino.setToolTipsVisible(True)
            for chave, *_ in lista:
                destino.addAction(self.qacoes[chave])
        try:
            janela.menuBar().insertMenu(self.iface.helpMenu().menuAction(), self.menu)
        except AttributeError:
            janela.menuBar().addMenu(self.menu)

        for nome, chaves in (("GWATER · Desenho", acoes.BARRA_DESENHO), ("GWATER · Modelo", acoes.BARRA_MODELO)):
            barra = self.iface.addToolBar(nome)
            barra.setObjectName(nome.replace(" · ", "_").replace(" ", ""))
            for k in chaves:
                barra.addAction(self.qacoes[k])
            self.barras.append(barra)

        self.dock = GwaterDock(self)
        # embaixo do mapa, em faixa horizontal (na lateral ela vira coluna sozinha)
        self.iface.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()

        prj = QgsProject.instance()
        prj.readProject.connect(self._projeto_aberto)
        prj.layersAdded.connect(self._camadas_adicionadas)
        prj.layersWillBeRemoved.connect(self.topologia.camadas_saindo)
        prj.cleared.connect(self.topologia.desconectar)
        self._projeto_aberto()

    def unload(self):
        prj = QgsProject.instance()
        for sinal, slot in ((prj.readProject, self._projeto_aberto), (prj.layersAdded, self._camadas_adicionadas),
                            (prj.layersWillBeRemoved, self.topologia.camadas_saindo),
                            (prj.cleared, self.topologia.desconectar)):
            try:
                sinal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.topologia.desconectar()
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
            self.menu.deleteLater()
        for barra in self.barras:
            self.iface.mainWindow().removeToolBar(barra)
            barra.deleteLater()
        if self.dock:
            self.dock.parar()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
        if self.servidor:
            self.servidor.terminate()

    def executar(self, chave):
        getattr(self, f"acao_{chave}")()

    # ------------------------------------------------ mensagens
    def aviso(self, texto, nivel=Qgis.MessageLevel.Warning):
        self.iface.messageBar().pushMessage("GWATER", texto, level=nivel, duration=8)

    def informar(self, texto):
        self.iface.messageBar().pushMessage("GWATER", texto, level=Qgis.MessageLevel.Info, duration=4)

    def mostrar_dock(self):
        primeira = not self.dock.isVisible()
        self.dock.show()
        self.dock.raise_()
        janela = self.iface.mainWindow()
        if primeira and not self.dock.isFloating() and                 janela.dockWidgetArea(self.dock) == Qt.DockWidgetArea.BottomDockWidgetArea:
            janela.resizeDocks([self.dock], [self.dock.ALTURA_FAIXA], Qt.Orientation.Vertical)

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

    def _projeto_aberto(self, *_):
        if not self.topologia.conectar():
            self.dock.status.setText("Abra um cadastro GWATER (ou crie um em 1 · Cadastro) para começar.")
            return
        prj = QgsProject.instance()
        ler = lambda k, padrao: prj.readEntry(CHAVE_PROJETO, k, padrao)[0]
        try:
            dn = float(ler("dn", "100"))
        except ValueError:
            dn = 100.0
        self.dock.mostrar_prototipo({"dn": dn, "material": ler("material", "PVC PBA"),
                                     "situacao": ler("situacao", "EXISTENTE"),
                                     "auto": ler("auto", "1") == "1", "formulario": ler("formulario", "1") == "1"})
        self.atualizar_lista_curvas()
        from .resultados import var_tubos
        self.dock.cor_tubos.blockSignals(True)
        self.dock.cor_tubos.setCurrentIndex(["v", "hl", "q"].index(var_tubos()))
        self.dock.cor_tubos.blockSignals(False)
        self.topologia.mdt = self._fonte_cota_salva()
        self.prototipo_mudou(salvar=False)
        self.dock.status.setText(f"Cadastro: <b>{os.path.basename(self.cadastro())}</b>. "
                                 "Desenhe em 2 · Desenhar a rede ou rode Validar / Simular.")

    def _camadas_adicionadas(self, camadas):
        if not self.topologia.camadas and any(isinstance(l, QgsVectorLayer) for l in camadas):
            self._projeto_aberto()

    def _cadastro_ok(self):
        if not self.cadastro():
            self.aviso("Nenhum cadastro GWATER aberto. Use Novo cadastro, Novo cadastro de shapefile ou Abrir cadastro.")
            self.mostrar_dock()
            self.dock.status.setText(f"<b style='color:{estilo.COR['warn']}'>Nenhum cadastro aberto.</b> Para desenhar, "
                                     "abra um projeto GWATER em <b>Abrir cadastro</b> (ex.: GWATER_rede_desenhada.qgz) "
                                     "ou crie um em <b>Novo cadastro</b>.")
            return False
        if not self.topologia.camadas:
            self.topologia.conectar()
        return True

    # ------------------------------------------------ protótipo de desenho
    def prototipo(self, campo):
        return self.dock.ler_prototipo()[campo]

    def prototipo_mudou(self, *_, salvar=True):
        p = self.dock.ler_prototipo()
        self.topologia.ativo = p["auto"]
        if self.topologia.camadas:
            aplicar_prototipo(self.topologia.camadas, p["dn"], p["material"], p["situacao"], p["formulario"])
        if salvar:
            prj = QgsProject.instance()
            for k in ("material", "situacao"):
                prj.writeEntry(CHAVE_PROJETO, k, p[k])
            prj.writeEntry(CHAVE_PROJETO, "dn", f"{p['dn'] or ''}")
            prj.writeEntry(CHAVE_PROJETO, "auto", "1" if p["auto"] else "0")
            prj.writeEntry(CHAVE_PROJETO, "formulario", "1" if p["formulario"] else "0")

    def atualizar_lista_curvas(self):
        """Campo curva das bombas vira lista com as curvas cadastradas."""
        try:
            curvas.lista_na_bomba(self.camada("bomba"), curvas.ler(self.camada("curva")))
        except LookupError:
            pass

    def garantir_encaixe(self):
        """Encaixe em vértices e segmentos de todas as camadas (a ponta gruda no elemento ou no meio do tubo)."""
        prj = QgsProject.instance()
        snap = prj.snappingConfig()
        snap.setEnabled(True)
        try:
            snap.setMode(Qgis.SnappingMode.AllLayers)
        except AttributeError:
            from qgis.core import QgsSnappingConfig
            snap.setMode(QgsSnappingConfig.AllLayers)
        tipos = Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment
        try:
            snap.setTypeFlag(tipos)
        except TypeError:
            snap.setTypeFlag(Qgis.SnappingTypes(tipos))
        prj.setSnappingConfig(snap)
        prj.setTopologicalEditing(True)

    def _editar_rede(self):
        for lyr in self.topologia.camadas.values():
            if not lyr.isEditable():
                lyr.startEditing()

    # ================================================ 1 · Cadastro
    def acao_central(self):
        self.mostrar_dock()
        self.dock.abas.setCurrentIndex(0)

    def _abrir_projeto(self, qgz, crs=None):
        """Abre o projeto recém-criado; acerta o sistema e o enquadramento; salva."""
        if not self.iface.newProject(True):  # o QGIS pergunta se quer salvar o projeto atual
            return False
        self.iface.addProject(qgz)
        prj = QgsProject.instance()
        if crs:
            sistema = QgsCoordinateReferenceSystem(crs)
            for _, _, lyr in self._camadas_gpkg():
                if lyr.isSpatial():
                    lyr.setCrs(lyr.dataProvider().crs())
            prj.setCrs(sistema)
        canvas = self.iface.mapCanvas()
        try:
            tr = self.camada("trecho")
            if tr.featureCount() > 0:
                ext = tr.extent()
                ext.grow(max(ext.width(), ext.height()) * 0.05 + 20)
                canvas.setDestinationCrs(prj.crs())
                canvas.setExtent(ext)
            elif crs and crs != ferramentas.CRS_PADRAO:
                limites = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), prj.crs(), prj) \
                    .transformBoundingBox(prj.crs().bounds())
                canvas.setDestinationCrs(prj.crs())
                canvas.setExtent(limites)
            canvas.refresh()
        except LookupError:
            pass
        prj.write()
        self._projeto_aberto()
        return True

    def acao_novo(self):
        r = ferramentas.janela_novo(self.iface.mainWindow())
        if not r:
            return
        if "erro" in r:
            return self.aviso(r["erro"])
        dados = self._motor("novo", r["gpkg"], [f"--crs={r['crs']}"], "Criando o cadastro…")
        if dados and dados.get("ok") and self._abrir_projeto(dados["qgz"], r["crs"]):
            self.mostrar_dock()
            self.dock.status.setText(f"Cadastro novo criado: <b>{os.path.basename(dados['gpkg'])}</b>. "
                                     "Navegue até a sua área e comece pela Captação ou Reservatório, depois "
                                     "Tubulação.")

    def acao_importar(self):
        cfg = ferramentas.janela_importar(self.iface.mainWindow())
        if not cfg:
            return
        if "erro" in cfg:
            return self.aviso(cfg["erro"])
        import json
        import tempfile
        fd, arq = tempfile.mkstemp(suffix=".json", prefix="gwater_importar_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        try:
            dados = self._motor("importar", arq, [], "Importando o shapefile…")
        finally:
            os.remove(arq)
        if dados and dados.get("ok") and self._abrir_projeto(dados["qgz"], cfg["crs"]):
            self.mostrar_dock()
            self.dock.mostrar_problemas(dados.get("itens", []))
            self.dock.status.setText(f"Importados <b>{dados['n_trechos']} tubulações e {dados['n_nos']} nós</b> "
                                     f"em {os.path.basename(dados['gpkg'])}. Agora desenhe a Captação ou o "
                                     "Reservatório e as válvulas e bombas. Avisos da importação na aba Problemas.")

    def acao_abrir(self):
        arq, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Abrir cadastro GWATER", "",
                                             "Projeto GWATER (*.qgz *.qgs)")
        if arq and self.iface.newProject(True):
            self.iface.addProject(arq)
            self._projeto_aberto()

    def acao_salvar(self):
        if not self._cadastro_ok():
            return
        salvas, erros = [], []
        for lyr in self.topologia.camadas.values():
            if lyr.isEditable() and lyr.isModified():
                if lyr.commitChanges(False):
                    salvas.append(lyr.name())
                else:
                    erros.append(f"{lyr.name()}: {'; '.join(lyr.commitErrors())}")
        if erros:
            self.aviso("Não consegui salvar " + " | ".join(erros), Qgis.MessageLevel.Critical)
        elif salvas:
            self.aviso("Salvo: " + ", ".join(salvas), Qgis.MessageLevel.Success)
        else:
            self.informar("Nada para salvar.")

    # ================================================ 2 · Desenho
    def _desenhar(self, chave):
        if not self._cadastro_ok():
            return
        lyr = self.camada(DESENHO[chave])
        self._editar_rede()
        self.garantir_encaixe()
        self.iface.setActiveLayer(lyr)
        self.iface.actionAddFeature().trigger()
        texto, _, desc, _ = acoes.todas()[chave]
        self.dock.status.setText(f"<b>Desenhando: {texto}</b>. {desc}")

    def acao_tubulacao(self):
        self._desenhar("tubulacao")

    def acao_no(self):
        self._desenhar("no")

    def acao_valvula(self):
        self._desenhar("valvula")

    def acao_bomba(self):
        self._desenhar("bomba")
        if self.cadastro() and not curvas.ler(self.camada("curva")):
            self.aviso("Ainda não há curvas de bomba no cadastro: cadastre em Curvas de bomba (3 · Preparar o modelo) "
                       "para escolher a curva no formulário.")

    def acao_reservatorio(self):
        self._desenhar("reservatorio")

    def acao_captacao(self):
        self._desenhar("captacao")

    def acao_mover(self):
        if self._cadastro_ok():
            self._editar_rede()
            self.garantir_encaixe()
            self.iface.actionVertexTool().trigger()
            self.dock.status.setText("<b>Mover / editar vértices</b>: arraste um elemento ou vértice. As tubulações "
                                     "ligadas acompanham.")

    def acao_dividir(self):
        if not self._cadastro_ok():
            return
        tr = self.camada("trecho")
        r = ferramentas.janela_dividir(self.iface.mainWindow(), tr.selectedFeatureCount())
        if not r:
            return
        fids = list(tr.selectedFeatureIds()) if r["selecionadas"] else None
        res = self.topologia.dividir_rede(r["tol"], fids, nos=r["nos"], em_t=r["em_t"], encaixar=r["encaixar"])
        msg = (f"Tolerância {r['tol']:g} m: {res['encaixadas']} ponta(s) encaixada(s), {res['divididas']} divisão(ões) "
               f"de tubulação, {res['nos_criados']} nó(s) criado(s).")
        self.dock.status.setText(msg + " Confira no mapa e clique em <b>Salvar edições</b>.")
        self.aviso(msg, Qgis.MessageLevel.Success)
        self.iface.mapCanvas().refresh()

    def acao_atributos(self):
        if self._cadastro_ok():
            self.iface.actionIdentify().trigger()
            self.dock.status.setText("<b>Ver / editar dados</b>: clique num elemento. Para alterar, ative a edição "
                                     "(qualquer botão de desenho já ativa) e use o formulário.")

    # ================================================ 3 · Preparar o modelo
    def _fonte_cota_salva(self):
        """Fonte de cota automática guardada no projeto (camada do projeto ou arquivo)."""
        import json
        from . import cotas
        prj = QgsProject.instance()
        try:
            cfg = json.loads(prj.readEntry(CHAVE_PROJETO, "cotas", "")[0] or "{}")
        except ValueError:
            cfg = {}
        if not cfg:  # projetos da versão anterior: só raster, pelo id da camada
            lyr = prj.mapLayer(prj.readEntry(CHAVE_PROJETO, "mdt", "")[0])
            return lyr if isinstance(lyr, QgsRasterLayer) else None
        lyr = prj.mapLayer(cfg.get("camada", "")) if cfg.get("camada") else \
            cotas.abrir_arquivo(cfg.get("arquivo", ""), cfg.get("sub")) if cfg.get("arquivo") else None
        if lyr is None:
            return None
        return cotas.Fonte(cfg["tipo"], lyr, self.camada("trecho").crs(), cfg.get("campo"),
                           usar_z=cfg.get("usar_z", False))

    def acao_cotas(self):
        if not self._cadastro_ok():
            return
        import json
        prj = QgsProject.instance()
        try:
            atual = json.loads(prj.readEntry(CHAVE_PROJETO, "cotas", "")[0] or "{}")
        except ValueError:
            atual = {}
        r = ferramentas.janela_cotas(self.iface.mainWindow(), self.camada("trecho").crs(), atual, self)
        if not r:
            return
        if "erro" in r:
            return self.aviso(r["erro"])
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            feitos, fora = ferramentas.preencher_cotas(self, r["fonte"], r["todas"], r["camadas"],
                                                       r["so_selecionados"])
        finally:
            QApplication.restoreOverrideCursor()
        self.topologia.mdt = r["fonte"] if r["auto"] else None
        prj.writeEntry(CHAVE_PROJETO, "cotas", json.dumps(r["config"]) if r["auto"] else "")
        prj.writeEntry(CHAVE_PROJETO, "mdt", "")
        msg = f"{feitos} cota(s) preenchida(s) a partir de {r['fonte'].nome()}."
        if fora:
            msg += (f" {len(fora)} elemento(s) sem cota (fora do raster ou fonte sem valores de cota): "
                    f"{', '.join(fora[:6])}.")
        self.dock.status.setText(msg + " Confira e clique em <b>Salvar edições</b>.")
        self.aviso(msg, Qgis.MessageLevel.Success if not fora else Qgis.MessageLevel.Warning)

    def acao_demanda(self):
        if not self._cadastro_ok():
            return
        r = ferramentas.janela_demanda(self.iface.mainWindow(), self)
        if not r:
            return
        try:
            n, q = ferramentas.distribuir_demanda(self, **r)
        except ValueError as e:
            return self.aviso(str(e))
        msg = f"{q:.3f} L/s distribuídos entre {n} nós."
        self.dock.status.setText(msg + " Confira e clique em <b>Salvar edições</b>.")
        self.aviso(msg, Qgis.MessageLevel.Success)

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

    def _motor(self, acao, alvo, extras, texto):
        """Chama o motor com cursor de espera; devolve o JSON ou None (avisando o erro)."""
        self.mostrar_dock()
        self.dock.status.setText(texto)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            dados = motor.rodar(acao, alvo, self.dock.projetados.isChecked(), extras)
        except Exception as e:
            self.dock.status.setText("Falha ao chamar o motor.")
            self.aviso(f"falha ao chamar o motor: {e}", Qgis.MessageLevel.Critical)
            return None
        finally:
            QApplication.restoreOverrideCursor()
        if not dados.get("ok"):
            erros = self.dock.mostrar_problemas(dados.get("itens", []))
            self.dock.status.setText(f"<b style='color:#e5484d'>{erros} erro(s)</b>. Veja a aba Problemas.")
        return dados

    def _rodar(self, acao):
        gpkg = self._preparar()
        if not gpkg:
            return None
        t0 = time.perf_counter()
        dados = self._motor(acao, gpkg, [], "Calculando no EPANET…" if acao == "simular" else "Validando a rede…")
        if dados is None:
            return None
        erros = self.dock.mostrar_problemas(dados.get("itens", []))
        avisos = len(dados.get("itens", [])) - erros
        if erros:
            self.dock.status.setText(f"<b style='color:#e5484d'>{erros} erro(s)</b> e {avisos} aviso(s). "
                                     "Corrija e rode de novo (clique duplo na aba Problemas leva até o elemento).")
            return None
        self.dock.status.setText(f"Rede válida · {avisos} aviso(s) · {time.perf_counter() - t0:.1f} s")
        return dados

    def acao_curvas(self):
        if not self._cadastro_ok():
            return
        j = curvas.JanelaCurvas(self.iface.mainWindow(), self)
        j.exec()
        self.atualizar_lista_curvas()

    def acao_modelbuilder(self):
        if not self._cadastro_ok():
            return
        from .modelbuilder import ModelBuilder
        j = ModelBuilder(self.iface.mainWindow(), self)
        if j.exec() and j.resultado:
            r = j.resultado
            self.mostrar_dock()
            self.dock.mostrar_problemas([{"nivel": "AVISO", "camada": None, "id": None, "msg": a}
                                         for a in r["avisos"]])
            msg = (f"ModelBuilder: {r['importados']} elemento(s) importado(s), {r['nos_criados']} nó(s) criado(s), "
                   f"{r['ligados_existentes']} ligação(ões) a elementos existentes, {r['divididas']} divisão(ões).")
            self.dock.status.setText(msg + " Confira no mapa e clique em <b>Salvar edições</b>.")
            self.aviso(msg, Qgis.MessageLevel.Success)
            self.iface.mapCanvas().refresh()

    def acao_validar(self):
        if self._rodar("validar"):
            self.aviso("Rede válida: pronta para simular.", Qgis.MessageLevel.Success)

    validar = acao_validar

    # ================================================ 4 · Simular
    def acao_simular(self):
        dados = self._rodar("simular")
        if not dados:
            return
        self.dock.parar()
        self.res = Resultados(self, dados)
        self.dock.carregar(self.res)
        self.dock.status.setText(self.dock.status.text() +
                                 f" · EPANET {dados['tempo_calculo_s'] * 1000:.0f} ms · modelo salvo em {dados['inp']}")

    simular = acao_simular

    def mudar_cor_tubos(self, var):
        from .resultados import escolher_var_tubos
        escolher_var_tubos(var)
        if self.res:
            self.res.estilizar()

    def acao_cores(self):
        from .faixas import JanelaFaixas
        from .resultados import var_tubos

        def aplicar(var):
            if var in ("v", "hl", "q") and var != var_tubos():  # editou outra variável dos tubos: passa a mostrá-la
                self.dock.cor_tubos.setCurrentIndex(["v", "hl", "q"].index(var))
            elif self.res:
                self.res.estilizar()
        JanelaFaixas(self.iface.mainWindow(), var_tubos(), aplicar).exec()

    def acao_limpar(self):
        limpar_resultados()
        self.res = None
        self.dock.limpar_resultados()
        self.informar("Resultados removidos do mapa.")

    def acao_exportar(self):
        gpkg = self._preparar()
        if not gpkg:
            return
        arq, _ = QFileDialog.getSaveFileName(self.iface.mainWindow(), "Exportar modelo EPANET",
                                             os.path.splitext(gpkg)[0] + ".inp", "Modelo EPANET (*.inp)")
        if not arq:
            return
        dados = self._motor("exportar", gpkg, [f"--inp={arq}"], "Gerando o .inp…")
        if dados and dados.get("ok"):
            self.dock.mostrar_problemas(dados.get("itens", []))
            self.dock.status.setText(f"Modelo exportado: <b>{arq}</b> (abre no EPANET 2.2).")
            self.aviso(f"Modelo exportado: {arq}", Qgis.MessageLevel.Success)

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

    # ================================================ 5 · Centro de Operações
    def abrir_painel(self, pagina="mapa"):
        gpkg = self.cadastro()
        if not gpkg:
            return self.aviso("Abra um projeto com o cadastro GWATER primeiro.")
        if motor.painel_no_ar() and motor.versao_painel() < motor.VERSAO_PAINEL:
            # servidor de uma versão anterior (sem as telas novas): troca por um novo
            if not motor.encerrar_painel() and self.servidor:
                self.servidor.terminate()
                for _ in range(30):
                    if not motor.painel_no_ar():
                        break
                    time.sleep(0.1)
            self.servidor = None
        if motor.painel_no_ar() and motor.trocar_cadastro(gpkg) is None:
            self.aviso("Há um painel antigo aberto (de outra versão do GWATER) na porta 8765. Feche o QGIS e abra "
                       "de novo para o painel mostrar as telas novas e este cadastro.")
        if not motor.painel_no_ar():
            self.servidor = motor.iniciar_painel(gpkg)
            for _ in range(40):  # até ~8 s para o servidor subir
                QApplication.processEvents()
                time.sleep(0.2)
                if motor.painel_no_ar():
                    break
        QDesktopServices.openUrl(QUrl(f"http://localhost:{motor.PORTA_PAINEL}/{PAGINAS[pagina]}"))

    def acao_mapa(self):
        self.abrir_painel("mapa")

    def acao_calibracao(self):
        self.abrir_painel("calibracao")

    def acao_aovivo(self):
        self.abrir_painel("aovivo")

    def acao_dados(self):
        self.abrir_painel("dados")

    def acao_sinotico(self):
        self.abrir_painel("sinotico")

    # ================================================ Ajuda
    def acao_guia(self):
        self.janelas.append(ferramentas.janela_guia(self.iface.mainWindow()))
