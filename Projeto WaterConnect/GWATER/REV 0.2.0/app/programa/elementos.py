"""Os elementos do WaterGEMS que o GWATER não tinha (Element Symbology completo).

Cada um é um tipo numa camada que já existe, menos o SCADA, que tem camada própria:
  nó (no_juncao.tipo): Tomada (Tap) e os de transiente: Ventosa (Air Valve), Válvula de alívio (Surge Valve),
      Disco de ruptura, Descarga para a atmosfera, Tanque hidropneumático, Chaminé de equilíbrio (Surge Tank) e
      Carga-vazão periódica (Periodic Head-Flow);
  válvula (valvula.tipo, entre dois tubos): Retenção (Check Valve), Turbina, Orifício entre tubos e Válvula de
      área linear;
  tubulação (trecho.tipo): Lateral (ramal até o consumidor);
  bomba (bomba.tipo): Bateria de bombas de rotação variável (VFD);
  SCADA: ponto ligado a um elemento da rede, com a grandeza e a tag do supervisório.

No cálculo (EPANET, regime permanente) os de transiente se comportam como no regime permanente do WaterGEMS: os nós
são nós comuns; a retenção vira um tubo curto que só deixa passar num sentido; turbina, orifício e válvula de área
linear viram uma válvula com a perda localizada informada (motor/cadastro_para_inp.py).
Cadastros antigos ganham os campos, as listas e a camada SCADA ao abrir.
"""
from qgis.core import (
    QgsCoordinateTransformContext, QgsDefaultValue, QgsEditorWidgetSetup, QgsField, QgsFields, QgsProject,
    QgsVectorFileWriter, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QMetaType

# tipo: (nome na lista do formulário)
NOS = {"TOMADA": "TOMADA - tomada do ramal (Tap)", "VENTOSA": "VENTOSA - válvula de ar (Air Valve)",
       "VALVULA_ALIVIO": "VALVULA_ALIVIO - válvula de alívio (Surge Valve)",
       "DISCO_RUPTURA": "DISCO_RUPTURA - disco de ruptura (Rupture Disk)",
       "DESCARGA_ATMOSFERA": "DESCARGA_ATMOSFERA - descarga para a atmosfera",
       "TANQUE_HIDROPNEUMATICO": "TANQUE_HIDROPNEUMATICO - tanque hidropneumático",
       "CHAMINE_EQUILIBRIO": "CHAMINE_EQUILIBRIO - chaminé de equilíbrio (Surge Tank)",
       "CARGA_PERIODICA": "CARGA_PERIODICA - carga-vazão periódica (Periodic Head-Flow)"}
VALVULAS = {"TCV": "TCV - registro/estrangulamento", "RETENCAO": "RETENCAO - válvula de retenção (Check Valve)",
            "TURBINA": "TURBINA - turbina", "ORIFICIO": "ORIFICIO - orifício entre tubos",
            "AREA_LINEAR": "AREA_LINEAR - válvula de área linear"}
TRECHOS = {"TUBULACAO": "TUBULACAO - tubulação", "LATERAL": "LATERAL - ramal (Lateral)"}
BOMBAS = {"BOMBA": "BOMBA - bomba", "BATERIA_VFD": "BATERIA_VFD - bateria de bombas de rotação variável"}
GRANDEZAS = ["PRESSAO", "VAZAO", "NIVEL", "STATUS", "ROTACAO", "CLORO"]
SCADA = "Elementos SCADA"
CAMPOS_SCADA = [("id", QMetaType.Type.QString), ("nome", QMetaType.Type.QString), ("elemento", QMetaType.Type.QString),
                ("grandeza", QMetaType.Type.QString), ("tag", QMetaType.Type.QString),
                ("situacao", QMetaType.Type.QString), ("setor", QMetaType.Type.QString),
                ("observacao", QMetaType.Type.QString)]


def _lista(lyr, campo, pares):
    """Acrescenta valores à lista (ValueMap) do campo; sem lista, cria uma com os existentes e os novos."""
    i = lyr.fields().indexOf(campo)
    if i < 0:
        return
    cfg = lyr.editorWidgetSetup(i)
    mapa = cfg.config().get("map", []) if cfg.type() == "ValueMap" else []
    if isinstance(mapa, dict):
        mapa = [{k: v} for k, v in mapa.items()]
    faltam = [{rotulo: valor} for valor, rotulo in pares.items() if not any(valor in d.values() for d in mapa)]
    if faltam:
        lyr.setEditorWidgetSetup(i, QgsEditorWidgetSetup("ValueMap", {"map": list(mapa) + faltam}))


def preparar_arquivo(qgz):
    """Antes de abrir o projeto: o campo tipo na tubulação e na bomba dos cadastros antigos, direto no GeoPackage
    (mudar a estrutura de uma tabela com as camadas já abertas atrapalha as consultas que o QGIS tem prontas)."""
    import re
    import zipfile
    try:
        if qgz.lower().endswith(".qgz"):
            with zipfile.ZipFile(qgz) as z:
                xml = z.read(next(n for n in z.namelist() if n.endswith(".qgs"))).decode("utf-8", "replace")
        else:
            with open(qgz, encoding="utf-8", errors="replace") as fh:
                xml = fh.read()
    except (OSError, StopIteration, zipfile.BadZipFile):
        return
    m = re.search(r">([^<>]*?\.gpkg)\|layername=trecho<", xml)
    if not m:
        return
    import os
    gpkg = m.group(1)
    if not os.path.isabs(gpkg):
        gpkg = os.path.normpath(os.path.join(os.path.dirname(qgz), gpkg))
    if not os.path.exists(gpkg):
        return
    from osgeo import ogr
    ds = ogr.Open(gpkg, 1)
    if ds is None:
        return
    try:
        for tabela, padrao in (("trecho", "TUBULACAO"), ("bomba", "BOMBA")):
            lyr = ds.GetLayerByName(tabela)
            if lyr is None or lyr.GetLayerDefn().GetFieldIndex("tipo") >= 0:
                continue
            lyr.CreateField(ogr.FieldDefn("tipo", ogr.OFTString))
            ds.ExecuteSQL(f"UPDATE {tabela} SET tipo = '{padrao}'")
    finally:
        ds = None


def _campo_tipo(lyr, padrao, pares):
    """O campo tipo (texto) nas camadas antigas, preenchido com o padrão; e a lista de valores."""
    if lyr.fields().indexOf("tipo") < 0:
        if lyr.isEditable():
            return  # com edição aberta não mexe na estrutura; fica para a próxima vez que abrir
        lyr.dataProvider().addAttributes([QgsField("tipo", QMetaType.Type.QString)])
        lyr.updateFields()
        i = lyr.fields().indexOf("tipo")
        lyr.dataProvider().changeAttributeValues({f.id(): {i: padrao} for f in lyr.getFeatures()})
    _lista(lyr, "tipo", pares)


def _camada_scada(nucleo):
    gpkg = nucleo.cadastro()
    try:
        return nucleo.camada("scada")
    except LookupError:
        pass
    lyr = QgsVectorLayer(f"{gpkg}|layername=scada", SCADA, "ogr")
    if not lyr.isValid():
        flds = QgsFields()
        for n, t in CAMPOS_SCADA:
            flds.append(QgsField(n, t))
        mem = QgsVectorLayer(f"Point?crs={nucleo.camada('no_juncao').crs().authid()}", "scada", "memory")
        mem.dataProvider().addAttributes(flds.toList())
        mem.updateFields()
        opt = QgsVectorFileWriter.SaveVectorOptions()
        opt.driverName, opt.layerName, opt.fileEncoding = "GPKG", "scada", "UTF-8"
        opt.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer
        err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, gpkg, QgsCoordinateTransformContext(), opt)
        if err[0] != QgsVectorFileWriter.WriterError.NoError:
            raise RuntimeError(f"não consegui criar a camada SCADA: {err[1]}")
        lyr = QgsVectorLayer(f"{gpkg}|layername=scada", SCADA, "ogr")
    prj = QgsProject.instance()
    prj.addMapLayer(lyr, False)
    no = prj.layerTreeRoot().findLayer(nucleo.camada("no_juncao").id())
    grupo = no.parent() if no is not None else prj.layerTreeRoot()
    grupo.insertLayer(0, lyr)
    nucleo._invalidar_camadas()
    return lyr


def garantir(nucleo):
    """Campos, listas e a camada SCADA no cadastro aberto (os novos já vêm com tudo; os antigos ganham agora)."""
    if not nucleo.cadastro():
        return
    _lista(nucleo.camada("no_juncao"), "tipo", NOS)
    _lista(nucleo.camada("valvula"), "tipo", VALVULAS)
    _campo_tipo(nucleo.camada("trecho"), "TUBULACAO", TRECHOS)
    _campo_tipo(nucleo.camada("bomba"), "BOMBA", BOMBAS)
    sc = _camada_scada(nucleo)
    idx = sc.fields().indexOf
    sc.setDefaultValueDefinition(idx("id"), QgsDefaultValue(
        "'SC-' || lpad(to_string(coalesce(maximum(to_int(regexp_substr(\"id\", '^SC-(\\\\d+)$'))), 0) + 1), 4, '0')"))
    sc.setDefaultValueDefinition(idx("situacao"), QgsDefaultValue("'EXISTENTE'"))
    _lista(sc, "grandeza", {g: g for g in GRANDEZAS})


# ---------------------------------------------------------------- anotação: polígono
def poligono(nucleo):
    """Polígono de anotação: clique os vértices e clique direito para fechar; pede um nome (opcional), escrito no
    meio. Fica na camada de anotações do projeto, como a borda, o texto e a linha."""
    from qgis.core import QgsAnnotationPointTextItem, QgsTextFormat
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtWidgets import QInputDialog
    from .ferramentas_mapa import FerramentaPoligono, anotar
    janela = nucleo.janela

    def fechou(g):
        if g is None or g.isEmpty():
            return
        item = anotar("poligono", g)
        try:
            from qgis.core import QgsFillSymbol
            item.setSymbol(QgsFillSymbol.createSimple({"color": "53,153,224,45", "outline_color": "#1c6fae",
                                                       "outline_width": "0.6"}))
        except (AttributeError, TypeError):
            pass
        nome, ok = QInputDialog.getText(janela, "Polígono", "Nome escrito no meio do polígono (opcional):")
        if ok and nome.strip():
            texto = QgsAnnotationPointTextItem(nome.strip(), g.centroid().asPoint())
            fmt = QgsTextFormat()
            fmt.setSize(11)
            fmt.setColor(QColor("#0d2650"))
            texto.setFormat(fmt)
            QgsProject.instance().mainAnnotationLayer().addItem(texto)
        QgsProject.instance().mainAnnotationLayer().triggerRepaint()

    f = FerramentaPoligono(janela.canvas, True)
    f.concluido.connect(fechou)
    janela.usar_ferramenta(f, "poligono")
    nucleo.dock.status.setText("<b>Polígono de anotação</b>: clique os vértices e clique direito para fechar. Fica "
                               "salvo no projeto. Esc para parar.")


def scada(nucleo):
    """Elemento SCADA: um ponto ligado a um elemento da rede (campo elemento), com a grandeza e a tag."""
    if not nucleo._cadastro_ok():
        return
    try:
        lyr = nucleo.camada("scada")
    except LookupError:  # cadastro aberto antes de o GWATER ter a camada
        garantir(nucleo)
        lyr = nucleo.camada("scada")
    from .consumidores import formulario
    formulario(nucleo, lyr)  # o formulário abre ou não como nas outras camadas
    if not lyr.isEditable():
        lyr.startEditing()
    nucleo.janela.desenhar(lyr, "scada")
    nucleo.dock.status.setText("<b>Elemento SCADA</b>: clique perto do elemento medido e informe o código dele, a "
                               "grandeza (pressão, vazão, nível…) e a tag do supervisório. Esc para parar.")


ACOES = {"poligono": poligono, "scada": scada}
