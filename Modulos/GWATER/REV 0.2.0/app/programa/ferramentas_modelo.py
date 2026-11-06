"""Ferramentas de criação do modelo: LoadBuilder, polígonos de Thiessen, centro de códigos, esqueletizador,
ferramentas externas (QGIS, EPANET, pasta) e salvar o cadastro com outro nome."""
import glob
import os
import shutil
import subprocess
import zipfile

from qgis.core import (
    QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, QgsMapLayerProxyModel, QgsPointXY, QgsProject,
    QgsSpatialIndex, QgsVectorLayer, QgsWkbTypes,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QLineEdit, QMessageBox, QRadioButton, QSpinBox,
)

from gwater.estilo import COR

from .util import NOMES, PONTOS, Dialogo, grupo_analises, janela_resultado, num, remover_analise, selecionar_ids


# ================================================================ LoadBuilder
UNIDADES = {"L/s": 1.0, "m³/h": 1000 / 3600, "m³/dia": 1000 / 86400, "m³/mês (30 dias)": 1000 / (30 * 86400),
            "L/dia": 1 / 86400}


def _filtro_camada(cmb, tipo):
    try:
        from qgis.core import Qgis
        cmb.setFilters({"ponto": Qgis.LayerFilter.PointLayer, "poligono": Qgis.LayerFilter.PolygonLayer}[tipo])
    except AttributeError:
        cmb.setFilters({"ponto": QgsMapLayerProxyModel.PointLayer, "poligono": QgsMapLayerProxyModel.PolygonLayer}[tipo])


def distribuir_cargas(nucleo, lyr, campo, k, pontos, metodo):
    """Cálculo do LoadBuilder: {nó: L/s} e quantos registros ficaram sem valor ou fora.
    k: fator do valor do campo para L/s; pontos: camada de pontos (True) ou polígonos; metodo: no, tubo,
    tubo_igual, igual, comprimento ou area."""
    nos = nucleo.camada("no_juncao")
    from qgis.core import QgsCoordinateTransform
    tr = QgsCoordinateTransform(lyr.crs(), nos.crs(), QgsProject.instance())
    destino = {}
    idx_n = QgsSpatialIndex(nos.getFeatures(), flags=QgsSpatialIndex.Flag.FlagStoreFeatureGeometries)
    id_de = {f.id(): str(f["id"]) for f in nos.getFeatures()}
    codigos_nos = set(id_de.values())
    sem = 0
    if pontos:
        tubos = nucleo.camada("trecho")
        idx_t = QgsSpatialIndex(tubos.getFeatures(), flags=QgsSpatialIndex.Flag.FlagStoreFeatureGeometries)
        tf = {f.id(): f for f in tubos.getFeatures()}
        for f in lyr.getFeatures():
            v = f[campo]
            try:
                q = float(v) * k
            except (TypeError, ValueError):
                sem += 1
                continue
            g = QgsGeometry(f.geometry())
            g.transform(tr)
            p = g.asPoint() if not g.isMultipart() else QgsPointXY(g.vertexAt(0))
            if metodo == "no":
                viz = idx_n.nearestNeighbor(p, 1)
                if viz:
                    destino[id_de[viz[0]]] = destino.get(id_de[viz[0]], 0) + q
            else:
                viz = idx_t.nearestNeighbor(p, 1)
                if not viz:
                    continue
                t = tf[viz[0]]
                gt = t.geometry()
                frac = gt.lineLocatePoint(QgsGeometry.fromPointXY(p)) / max(gt.length(), 1e-9)
                if metodo == "tubo_igual":
                    frac = 0.5
                for nid, w in ((str(t["no_inicial"]), 1 - frac), (str(t["no_final"]), frac)):
                    if nid in codigos_nos:
                        destino[nid] = destino.get(nid, 0) + q * w
                    else:  # ponta numa bomba/válvula: vai tudo para a outra ponta
                        outra = str(t["no_final"]) if nid == str(t["no_inicial"]) else str(t["no_inicial"])
                        destino[outra] = destino.get(outra, 0) + q * w
    else:
        tubos = nucleo.camada("trecho")
        celulas = {}
        if metodo == "area":  # área de influência de cada nó (Voronoi), uma vez só
            pts_n = [(id_de[i], idx_n.geometry(i).asPoint()) for i in id_de]
            env = QgsGeometry.fromMultiPointXY([p for _, p in pts_n])
            caixa = env.boundingBox()
            caixa.grow(max(caixa.width(), caixa.height(), 100.0))
            vor = env.voronoiDiagram(QgsGeometry.fromRect(caixa))
            pols = list(vor.asGeometryCollection())
            for nid, p in pts_n:
                cel = next((g for g in pols if g.contains(QgsGeometry.fromPointXY(p))), None)
                if cel is not None:
                    celulas[nid] = cel
        for f in lyr.getFeatures():
            try:
                q = float(f[campo]) * k
            except (TypeError, ValueError):
                sem += 1
                continue
            g = QgsGeometry(f.geometry())
            g.transform(tr)
            if metodo == "area":
                pesos = {nid: cel.intersection(g).area() for nid, cel in celulas.items()
                         if cel.boundingBox().intersects(g.boundingBox())}
                pesos = {nid: a for nid, a in pesos.items() if a > 0}
                tot = sum(pesos.values())
                if not tot:
                    sem += 1
                    continue
                for nid, a in pesos.items():
                    destino[nid] = destino.get(nid, 0) + q * a / tot
                continue
            dentro = [id_de[i] for i in idx_n.intersects(g.boundingBox())
                      if g.contains(idx_n.geometry(i))]
            if not dentro:
                sem += 1
                continue
            if metodo == "igual":
                for nid in dentro:
                    destino[nid] = destino.get(nid, 0) + q / len(dentro)
            else:
                peso = {nid: 0.0 for nid in dentro}
                for t in tubos.getFeatures(QgsFeatureRequest().setFilterRect(g.boundingBox())):
                    L = t.geometry().intersection(g).length() / 2
                    for nid in (str(t["no_inicial"]), str(t["no_final"])):
                        if nid in peso:
                            peso[nid] += L
                tot = sum(peso.values())
                for nid in dentro:
                    destino[nid] = destino.get(nid, 0) + q * (peso[nid] / tot if tot else 1 / len(dentro))
    return destino, sem


def loadbuilder(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "LoadBuilder",
                "Distribui consumos medidos para os nós do modelo, como o LoadBuilder do WaterGEMS. Pontos (hidrômetros, "
                "ligações): cada consumo vai para o nó mais próximo ou para as pontas da tubulação mais próxima. "
                "Polígonos (setores, quadras, setores censitários): o consumo ou a população do polígono é dividido "
                "entre os nós, igual, pelo comprimento de tubulação ou pela área de influência de cada nó.",
                largura=680)
    pts = QRadioButton("Pontos com consumo (hidrômetros)")
    pts.setChecked(True)
    pol = QRadioButton("Polígonos com consumo (setores, quadras)")
    d.lay.addWidget(pts)
    d.lay.addWidget(pol)
    camada = QgsMapLayerComboBox()
    _filtro_camada(camada, "ponto")
    d.linha("Camada (abra o arquivo antes, por Mapa de fundo › Arquivo):", camada)
    campo = QgsFieldComboBox()
    campo.setLayer(camada.currentLayer())
    camada.layerChanged.connect(campo.setLayer)
    d.linha("Campo do consumo:", campo)
    natureza = QComboBox()
    natureza.addItem("Consumo (vazão ou volume)", "consumo")
    natureza.addItem("População (habitantes × consumo per capita)", "populacao")
    d.linha("O campo é:", natureza)
    un = QComboBox()
    un.addItems(list(UNIDADES))
    un.setCurrentText("m³/mês (30 dias)")
    d.linha("Unidade do consumo:", un)
    percap = d.linha("Consumo per capita:", QDoubleSpinBox(), "L por habitante por dia (ex.: 150)")
    percap.setRange(1, 2000)
    percap.setValue(150)
    percap.setSuffix(" L/hab/dia")
    percap.setEnabled(False)
    natureza.currentIndexChanged.connect(lambda _: (un.setEnabled(natureza.currentData() == "consumo"),
                                                    percap.setEnabled(natureza.currentData() == "populacao")))
    metodo = QComboBox()
    d.linha("Método:", metodo)

    def metodos():
        metodo.clear()
        if pts.isChecked():
            metodo.addItem("Nó mais próximo (Nearest Node)", "no")
            metodo.addItem("Tubulação mais próxima, proporcional à distância das pontas", "tubo")
            metodo.addItem("Tubulação mais próxima, metade para cada ponta", "tubo_igual")
        else:
            metodo.addItem("Igual entre os nós de dentro (Equal Distribution)", "igual")
            metodo.addItem("Proporcional ao comprimento de tubulação de dentro", "comprimento")
            metodo.addItem("Proporcional à área de influência (Thiessen) dentro do polígono", "area")
        _filtro_camada(camada, "ponto" if pts.isChecked() else "poligono")
    pts.toggled.connect(metodos)
    metodos()
    fator = d.linha("Fator (perdas, pico):", QDoubleSpinBox(), "1 = consumo medido; 1,25 = 25% a mais (perdas)")
    fator.setRange(0, 10)
    fator.setDecimals(3)
    fator.setValue(1.0)
    somar = QCheckBox("Somar às demandas que os nós já têm (desmarcado: substitui)")
    d.lay.addWidget(somar)
    categoria = QLineEdit()
    categoria.setPlaceholderText("vazio = direto na demanda base do nó")
    d.linha("Gravar como demanda da categoria:", categoria,
            "Ex.: 'Hidrômetros 2025': entra como mais uma demanda de cada nó na Central de demanda (substitui a "
            "da mesma categoria, sem mexer nas outras)")
    padrao = QLineEdit()
    d.linha("Padrão para os nós que receberem demanda:", padrao, "vazio = não muda o padrão")
    d.botoes("Calcular")
    if not d.exec():
        return
    lyr = camada.currentLayer()
    if lyr is None or not campo.currentField():
        return nucleo.aviso("Escolha a camada e o campo do consumo.")
    nos = nucleo.camada("no_juncao")
    k = (percap.value() / 86400 if natureza.currentData() == "populacao" else UNIDADES[un.currentText()]) * fator.value()
    destino, sem = distribuir_cargas(nucleo, lyr, campo.currentField(), k, pts.isChecked(), metodo.currentData())
    if not destino:
        return nucleo.aviso("Nenhum consumo foi distribuído (confira a camada, o campo e o sistema de coordenadas).")
    total = sum(destino.values())
    if QMessageBox.question(nucleo.janela, "LoadBuilder",
                            f"{num(total, 3)} L/s distribuídos em {len(destino)} nós"
                            f"{f' ({sem} registros sem valor ou fora)' if sem else ''}.\n\nAplicar nos nós? "
                            "(fica na edição até Salvar edições)") != QMessageBox.StandardButton.Yes:
        return
    if categoria.text().strip():
        _loadbuilder_categoria(nucleo, destino, categoria.text().strip(), padrao.text().strip())
        return janela_resultado(nucleo, "LoadBuilder", f"{num(total, 3)} L/s ({num(total * 86.4, 0)} m³/dia) "
                                f"distribuídos como a categoria '{categoria.text().strip()}' na Central de demanda.",
                                ["Nó", "Demanda atribuída (L/s)"],
                                [[k2, round(v, 5)] for k2, v in sorted(destino.items())], "loadbuilder")
    if not nos.isEditable():
        nos.startEditing()
    i_d, i_p = nos.fields().indexOf("demanda_base"), nos.fields().indexOf("padrao")
    nos.beginEditCommand("LoadBuilder")
    por_id = {str(f["id"]): f for f in nos.getFeatures()}
    for nid, q in destino.items():
        f = por_id.get(nid)
        if f is None:
            continue
        base = float(f["demanda_base"] or 0) if somar.isChecked() and str(f["demanda_base"]) != "NULL" else 0
        nos.changeAttributeValue(f.id(), i_d, round(base + q, 5))
        if padrao.text().strip():
            nos.changeAttributeValue(f.id(), i_p, padrao.text().strip())
    nos.endEditCommand()
    janela_resultado(nucleo, "LoadBuilder", f"{num(total, 3)} L/s ({num(total * 86.4, 0)} m³/dia) distribuídos.",
                     ["Nó", "Demanda atribuída (L/s)"], [[k2, round(v, 5)] for k2, v in sorted(destino.items())],
                     "loadbuilder")


def _loadbuilder_categoria(nucleo, destino, cat, padrao):
    """Resultado do LoadBuilder como uma categoria da coleção de demandas de cada nó (troca a categoria se já existir)."""
    from .componentes import _substituir, ler_colecao, tabela_demandas
    col = ler_colecao(nucleo)
    nos = nucleo.camada("no_juncao")
    if not nos.isEditable():
        nos.startEditing()
    nos.beginEditCommand(f"LoadBuilder: {cat}")
    for f in nos.getFeatures():
        nid = str(f["id"])
        tem = nid in col
        lst = col.get(nid)
        if lst is None:
            base = float(f["demanda_base"] or 0) if str(f["demanda_base"]) != "NULL" else 0.0
            p0 = "" if f["padrao"] is None or str(f["padrao"]) == "NULL" else str(f["padrao"])
            lst = [[base, p0, ""]] if base else []
        lst = [x for x in lst if x[2] != cat]
        if nid in destino:
            lst.append([round(destino[nid], 6), padrao, cat])
        if nid in destino or tem:
            col[nid] = lst
            nos.changeAttributeValue(f.id(), nos.fields().indexOf("demanda_base"), round(sum(x[0] for x in lst), 6))
    nos.endEditCommand()
    linhas = [{"no_id": k, "demanda": a, "padrao": b or None, "categoria": c or None}
              for k, lst in col.items() for a, b, c in lst]
    _substituir(nucleo, tabela_demandas(nucleo), linhas, ["no_id", "demanda", "padrao", "categoria"])


# ================================================================ Thiessen
def thiessen(nucleo):
    if not nucleo.cadastro():
        return
    nos = nucleo.camada("no_juncao")
    feats = [f for f in nos.getFeatures() if f.hasGeometry()]
    if len(feats) < 3:
        return nucleo.aviso("São precisos pelo menos 3 nós.")
    d = Dialogo(nucleo.janela, "Polígonos de Thiessen",
                "Área de influência de cada nó (polígonos de Voronoi), usada para alocar consumo por área. Recortados "
                "pela envoltória da rede mais uma folga.")
    folga = d.linha("Folga em volta da rede:", QDoubleSpinBox())
    folga.setRange(0, 5000)
    folga.setValue(100)
    folga.setSuffix(" m")
    d.botoes("Gerar")
    if not d.exec():
        return
    multi = QgsGeometry.fromMultiPointXY([f.geometry().asPoint() for f in feats])
    envolt = multi.convexHull().buffer(folga.value(), 8)
    vor = multi.voronoiDiagram(envolt)
    nome = "Polígonos de Thiessen"
    remover_analise(nome)
    lyr = QgsVectorLayer(f"Polygon?crs={nos.crs().authid()}", nome, "memory")
    lyr.dataProvider().addAttributes([QgsField("no", QVariant.String), QgsField("area_m2", QVariant.Double)])
    lyr.updateFields()
    idx = QgsSpatialIndex()
    for i, f in enumerate(feats):
        idx.addFeature(i, f.geometry().boundingBox())
    novos = []
    for parte in vor.asGeometryCollection():
        pg = parte.intersection(envolt)
        if pg.isEmpty():
            continue
        dono = next((feats[i] for i in idx.intersects(pg.boundingBox()) if pg.contains(feats[i].geometry())), None)
        f = QgsFeature(lyr.fields())
        f.setGeometry(pg)
        f.setAttributes([str(dono["id"]) if dono else None, round(pg.area(), 1)])
        novos.append(f)
    lyr.dataProvider().addFeatures(novos)
    from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
    lyr.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "53,208,255,30", "outline_color": "#1c7ed6", "outline_width": "0.3"})))
    QgsProject.instance().addMapLayer(lyr, False)
    grupo_analises().addLayer(lyr)
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{len(novos)} polígonos de Thiessen gerados (camada em Análises GWATER; use no LoadBuilder por "
                    "polígonos ou exporte).")


# ================================================================ centro de códigos
def ids(nucleo):
    if not nucleo.cadastro():
        return
    from .consultas import codigos_repetidos
    rep = codigos_repetidos(nucleo)
    d = Dialogo(nucleo.janela, "Centro de códigos",
                f"Códigos repetidos ou vazios hoje: <b>{len(rep)}</b>. Renumerar troca os códigos dos elementos "
                "(todos do tipo, ou só os selecionados) e atualiza as tubulações (nó inicial/final) e os controles. "
                "Os cenários que citam os códigos antigos precisam ser revistos.")
    tipo = QComboBox()
    for c in ("trecho",) + PONTOS:
        try:
            nucleo.camada(c)
            tipo.addItem(NOMES[c], c)
        except LookupError:
            pass
    d.linha("Elemento:", tipo)
    so_sel = QCheckBox("Só os selecionados no mapa")
    d.lay.addWidget(so_sel)
    so_rep = QCheckBox("Só os códigos repetidos ou vazios (o primeiro de cada código fica como está)")
    so_rep.setChecked(bool(rep))
    d.lay.addWidget(so_rep)
    pref = d.linha("Prefixo:", QLineEdit("T-"))
    tipo.currentIndexChanged.connect(lambda _i: pref.setText(
        {"trecho": "T-", "no_juncao": "N-", "valvula": "V-", "bomba": "B-", "reservatorio": "R-",
         "captacao": "C-"}[tipo.currentData()]))
    ini = QSpinBox()
    ini.setRange(0, 10 ** 6)
    ini.setValue(1)
    d.linha("Começar em:", ini)
    dig = QSpinBox()
    dig.setRange(1, 8)
    dig.setValue(4)
    d.linha("Dígitos:", dig)
    ver = QCheckBox("Só mostrar os repetidos/vazios (não renumerar)")
    d.lay.addWidget(ver)
    d.botoes("Executar")
    if not d.exec():
        return
    if ver.isChecked():
        return nucleo.janela.dock_consultas.mostrar("Códigos repetidos ou vazios", rep)
    c = tipo.currentData()
    lyr = nucleo.camada(c)
    fids = list(lyr.selectedFeatureIds()) if so_sel.isChecked() else [f.id() for f in lyr.getFeatures()]
    if so_rep.isChecked():
        vistos, so = set(), []
        for f in sorted(lyr.getFeatures(fids), key=lambda x: x.id()):
            cod = "" if f["id"] is None or str(f["id"]) == "NULL" else str(f["id"]).strip()
            if not cod or cod in vistos:
                so.append(f.id())
            vistos.add(cod)
        fids = so
    if not fids:
        return nucleo.informar("Nada para renumerar.")
    existentes = {str(f["id"]) for l in nucleo.camadas_rede() for f in l.getFeatures()}
    mapa, n = {}, ini.value()
    for f in sorted(lyr.getFeatures(fids), key=lambda x: (x.geometry().boundingBox().yMaximum() * -1,
                                                          x.geometry().boundingBox().xMinimum())):
        while True:
            novo = f"{pref.text()}{n:0{dig.value()}d}"
            n += 1
            if novo not in existentes or novo == str(f["id"]):
                break
        mapa[f.id()] = (str(f["id"]), novo)
        existentes.add(novo)
    if QMessageBox.question(nucleo.janela, "Renumerar", f"Renumerar {len(mapa)} {NOMES[c].lower()}(s) "
                            f"({next(iter(mapa.values()))[0]} → {next(iter(mapa.values()))[1]} …)?") \
            != QMessageBox.StandardButton.Yes:
        return
    for l in nucleo.camadas_rede():
        if not l.isEditable():
            l.startEditing()
    i = lyr.fields().indexOf("id")
    for fid, (_, novo) in mapa.items():
        lyr.changeAttributeValue(fid, i, novo)
    # repetidos: o código velho continua existindo (no primeiro), então as tubulações não são trocadas de nó
    troca = {} if so_rep.isChecked() else {velho: novo for velho, novo in mapa.values()}
    if c != "trecho":
        tr = nucleo.camada("trecho")
        ia, ib = tr.fields().indexOf("no_inicial"), tr.fields().indexOf("no_final")
        for f in tr.getFeatures():
            if str(f["no_inicial"]) in troca:
                tr.changeAttributeValue(f.id(), ia, troca[str(f["no_inicial"])])
            if str(f["no_final"]) in troca:
                tr.changeAttributeValue(f.id(), ib, troca[str(f["no_final"])])
        try:
            ctl = nucleo.camada("controle")
            if not ctl.isEditable():
                ctl.startEditing()
            for f in ctl.getFeatures():
                for campo in ("elemento", "no_ref"):
                    if str(f[campo]) in troca:
                        ctl.changeAttributeValue(f.id(), ctl.fields().indexOf(campo), troca[str(f[campo])])
        except LookupError:
            pass
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{len(mapa)} código(s) trocado(s). Salvar edições grava no cadastro.")


# ================================================================ esqueletizador
def esqueletizar(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    d = Dialogo(nucleo.janela, "Esqueletizador",
                "Cria uma CÓPIA simplificada da rede (o cadastro original não muda), como o Skelebrator do WaterGEMS: "
                "corta ramais de ponta finos (a demanda vai para o nó de onde o ramal sai), une tubulações em série e "
                "em paralelo em tubulações equivalentes (mesma perda de carga). Bombas, válvulas, reservatórios e os nós "
                "protegidos ficam.")
    dn = d.linha("Ramais até DN:", QDoubleSpinBox(), "Só ramais de ponta com diâmetro até este são cortados")
    dn.setRange(0, 2000)
    dn.setValue(75)
    dn.setSuffix(" mm")
    comp = d.linha("Ramais até o comprimento:", QDoubleSpinBox(), "0 = qualquer comprimento")
    comp.setRange(0, 100000)
    comp.setSuffix(" m")
    tol = d.linha("Série: diferença de DN aceita:", QDoubleSpinBox(),
                  "0 = só une tubos de mesmo DN e material; ex.: 30% une 100 com 75 num tubo equivalente")
    tol.setRange(0, 100)
    tol.setSuffix(" %")
    ramais = QCheckBox("Cortar ramais de ponta (Branch Trimming)")
    ramais.setChecked(True)
    serie = QCheckBox("Unir tubulações em série (Series Pipe Merging)")
    serie.setChecked(True)
    paral = QCheckBox("Unir tubulações em paralelo (Parallel Pipe Merging)")
    paral.setChecked(True)
    proteger = QCheckBox("Proteger os nós selecionados no mapa e os pontos de medição da calibração")
    proteger.setChecked(True)
    for w in (ramais, serie, paral, proteger):
        d.lay.addWidget(w)
    destino = d.linha("Salvar a cópia em:", QLineEdit(os.path.splitext(gpkg)[0] + "_esqueleto.gpkg"))
    abrir = QCheckBox("Abrir a cópia depois")
    abrir.setChecked(True)
    d.lay.addWidget(abrir)
    d.botoes("Esqueletizar")
    if not d.exec():
        return
    from .analise_ui import rodar
    prot = []
    if proteger.isChecked():
        from .util import ids_selecionados
        prot = list(ids_selecionados(nucleo))
        for mo in nucleo.janela._ler_json("calibracao", {}).get("momentos", []):
            prot += [o["elemento"] for o in mo.get("observacoes", [])]
    r = rodar(nucleo, "esqueletizar", "Esqueletizando…", destino=destino.text(), dn_max=dn.value(),
              cortar_ramais=ramais.isChecked(), unir_serie=serie.isChecked(), unir_paralelos=paral.isChecked(),
              comprimento_max=comp.value() or None, tol_dn_pct=tol.value(), protegidos=sorted(set(prot)))
    if not r:
        return
    msg = (f"Esqueleto gravado em {os.path.basename(r['gpkg'])}: {r['tubos_final']} tubulações e {r['nos_final']} nós "
           f"({r['tubos_removidos']} ramais cortados, {r['tubos_unidos']} uniões em série, "
           f"{r.get('paralelos_unidos', 0)} paralelos unidos). Demanda total "
           f"conservada: {num(r['demanda_total'], 3)} L/s.")
    if abrir.isChecked() and r.get("qgz") and nucleo.janela.fechar_projeto(True):
        nucleo.janela.abrir_projeto(r["qgz"])
    QMessageBox.information(nucleo.janela, "Esqueletizador", msg)


# ================================================================ ferramentas externas
def _qgis_exe():
    for padrao in (r"C:\Program Files\QGIS 4*\bin\qgis-bin.exe", r"C:\Program Files\QGIS 3*\bin\qgis-ltr-bin.exe",
                   r"C:\Program Files\QGIS 3*\bin\qgis-bin.exe", r"C:\OSGeo4W\bin\qgis-bin.exe"):
        achados = sorted(glob.glob(padrao), reverse=True)
        if achados:
            return achados[0]
    return None


def abrir_qgis(nucleo):
    prj = QgsProject.instance().fileName()
    if not prj:
        return nucleo.aviso("Abra um cadastro primeiro.")
    if any(l.isEditable() and l.isModified() for l in nucleo.camadas_rede()):
        nucleo.executar("salvar")
    QgsProject.instance().write()
    exe = _qgis_exe()
    if not exe:
        return nucleo.aviso("Não achei o QGIS instalado.")
    bat = os.path.join(os.path.dirname(exe), os.path.basename(exe).replace("-bin.exe", ".bat"))
    subprocess.Popen([bat if os.path.exists(bat) else exe, prj], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    nucleo.informar("Abrindo o cadastro no QGIS (com o plugin GWATER, se instalado).")


def _epanet_exe():
    for padrao in (r"C:\Program Files*\EPANET 2.2\epanet2w.exe", r"C:\Program Files*\EPANET*\epanet2w.exe",
                   r"C:\Program Files*\EPANET*\*.exe"):
        achados = glob.glob(padrao)
        if achados:
            return achados[0]
    return None


def abrir_epanet(nucleo):
    gpkg = nucleo._preparar()
    if not gpkg:
        return
    arq = os.path.splitext(gpkg)[0] + ".inp"
    dados = nucleo._motor("exportar", gpkg, [f"--inp={arq}"], "Gerando o .inp…")
    if not dados or not dados.get("ok"):
        return
    exe = _epanet_exe()
    if exe:
        subprocess.Popen([exe, arq])
    else:
        os.startfile(os.path.dirname(arq))
        nucleo.aviso(f"Não achei o EPANET 2.2 instalado: o modelo está em {arq}.")


def abrir_pasta(nucleo):
    gpkg = nucleo.cadastro()
    if gpkg:
        os.startfile(os.path.dirname(gpkg))


# ================================================================ salvar como
def salvar_como(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    nucleo.executar("salvar")
    novo, _ = QFileDialog.getSaveFileName(nucleo.janela, "Salvar cadastro como", os.path.splitext(gpkg)[0] + "_copia.gpkg",
                                          "Cadastro GWATER (*.gpkg)")
    if not novo:
        return
    from gwater.ferramentas import arquivo_gpkg
    novo = arquivo_gpkg(novo)
    if os.path.abspath(novo) == os.path.abspath(gpkg):
        return
    QgsProject.instance().write()
    shutil.copyfile(gpkg, novo)
    base_velho = os.path.splitext(os.path.basename(gpkg))[0]
    base_novo = os.path.splitext(os.path.basename(novo))[0]
    for suf in ("_dados_recebidos.json", "_historico.sqlite"):
        if os.path.exists(os.path.splitext(gpkg)[0] + suf):
            shutil.copyfile(os.path.splitext(gpkg)[0] + suf, os.path.splitext(novo)[0] + suf)
    prj = QgsProject.instance().fileName()
    qgz = os.path.join(os.path.dirname(novo), f"GWATER_{base_novo}.qgz")
    with zipfile.ZipFile(prj) as zin, zipfile.ZipFile(qgz, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename.endswith(".qgs"):
                dados = dados.replace(os.path.basename(gpkg).encode(), os.path.basename(novo).encode())
            zout.writestr(item, dados)
    if nucleo.janela.fechar_projeto(True):
        nucleo.janela.abrir_projeto(qgz)
    nucleo.informar(f"Cadastro salvo como {os.path.basename(novo)} (agora aberto).")


ACOES = {"loadbuilder": loadbuilder, "thiessen": thiessen, "ids": ids, "esqueletizar": esqueletizar,
         "abrir_qgis": abrir_qgis, "abrir_epanet": abrir_epanet, "abrir_pasta": abrir_pasta,
         "externas": abrir_qgis, "salvar_como": salvar_como}
