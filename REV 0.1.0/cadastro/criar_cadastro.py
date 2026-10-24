"""Cria o cadastro GWATER (GeoPackage + projeto QGIS) com a rede de exemplo.

Rodar com o Python do QGIS:
  "C:\\Program Files\\QGIS 3.44.14\\bin\\python-qgis-ltr.bat" criar_cadastro.py

Gera nesta pasta:
  gwater_cadastro.gpkg  - camadas e tabelas do cadastro
  GWATER_cadastro.qgz   - projeto QGIS (estilos, formulários, snapping)
"""
import os
import sys

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext,
    QgsDefaultValue, QgsEditorWidgetSetup, QgsFeature, QgsField, QgsFields,
    QgsGeometry, QgsLineSymbol, QgsMarkerSymbol, QgsPalLayerSettings, QgsPointXY,
    QgsProject, QgsProperty, QgsRasterLayer, QgsReferencedRectangle, QgsSnappingConfig,
    QgsSymbolLayer, QgsTextBufferSettings, QgsTextFormat, QgsTolerance,
    QgsVectorFileWriter, QgsVectorLayer, QgsVectorLayerSimpleLabeling, QgsWkbTypes, Qgis,
)

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
from modelo import padrao_consumo  # noqa: E402

GPKG = os.path.join(AQUI, "gwater_cadastro.gpkg")
PROJETO = os.path.join(AQUI, "GWATER_cadastro.qgz")
CRS = QgsCoordinateReferenceSystem("EPSG:31983")  # SIRGAS 2000 / UTM 23S
E0, N0 = 333000.0, 7394000.0  # origem fictícia da rede de exemplo

S, D, I = QVariant.String, QVariant.Double, QVariant.Int

# ---------------------------------------------------------------- domínios
SITUACAO = ["EXISTENTE", "PROJETADO", "DESATIVADO"]
MATERIAIS = {  # material: C de Hazen-Williams sugerido para tubo novo
    "PVC PBA": 140, "PVC DEFoFo": 140, "PEAD": 140,
    "Ferro fundido dúctil": 130, "Ferro fundido cinzento": 100,
    "Aço": 120, "Cimento-amianto": 120,
}
STATUS_TRECHO = ["ABERTO", "FECHADO", "CV"]
TIPO_VALVULA = {"PRV": "PRV - redutora de pressão", "PSV": "PSV - sustentadora de pressão",
                "PBV": "PBV - quebra-pressão", "FCV": "FCV - controladora de vazão",
                "TCV": "TCV - registro/estrangulamento", "GPV": "GPV - perda genérica"}
STATUS_VALVULA = ["ATIVA", "ABERTA", "FECHADA"]
TIPO_NO = ["JUNCAO", "CONSUMO", "HIDRANTE", "PONTA"]

# ---------------------------------------------------------------- esquema
COMUNS = [("situacao", S), ("setor", S), ("observacao", S)]
CAMADAS = {
    "captacao": ("Point", [("id", S), ("nome", S), ("carga_hidraulica", D), ("padrao_carga", S)] + COMUNS),
    "reservatorio": ("Point", [("id", S), ("nome", S), ("cota_fundo", D), ("nivel_ini", D),
                               ("nivel_min", D), ("nivel_max", D), ("diametro", D),
                               ("volume_util", D)] + COMUNS),
    "bomba": ("Point", [("id", S), ("nome", S), ("elevatoria", S), ("cota", D), ("curva", S),
                        ("status_inicial", S), ("rotacao_relativa", D), ("potencia_cv", D)] + COMUNS),
    "valvula": ("Point", [("id", S), ("nome", S), ("tipo", S), ("cota", D), ("diametro", D),
                          ("ajuste", D), ("status", S), ("perda_localizada", D)] + COMUNS),
    "no_juncao": ("Point", [("id", S), ("nome", S), ("tipo", S), ("cota", D), ("demanda_base", D),
                            ("padrao", S)] + COMUNS),
    "trecho": ("LineString", [("id", S), ("no_inicial", S), ("no_final", S), ("comprimento", D),
                              ("diametro_nominal", D), ("material", S), ("rugosidade_hw", D),
                              ("perda_localizada", D), ("status", S), ("ano_instalacao", I)] + COMUNS),
    # tabelas sem geometria
    "padrao_consumo": ("None", [("id_padrao", S), ("passo", I), ("multiplicador", D)]),
    "curva": ("None", [("id_curva", S), ("tipo", S), ("x", D), ("y", D)]),
    "controle": ("None", [("elemento", S), ("acao", S), ("condicao", S), ("no_ref", S), ("valor", D)]),
    "opcoes_simulacao": ("None", [("chave", S), ("valor", S)]),
    "dominio_material": ("None", [("material", S), ("rugosidade_hw", D)]),
}
PONTOS = ["captacao", "reservatorio", "bomba", "valvula", "no_juncao"]
# nomes exibidos no QGIS (as expressões do formulário referenciam estes nomes)
APELIDOS = {"captacao": "Captação", "reservatorio": "Reservatórios", "bomba": "Bombas", "valvula": "Válvulas",
            "no_juncao": "Nós / junções", "trecho": "Trechos (tubulações)", "padrao_consumo": "Padrões de consumo",
            "curva": "Curvas", "controle": "Controles", "opcoes_simulacao": "Opções de simulação",
            "dominio_material": "Domínio · material"}

# ---------------------------------------------------------------- rede de exemplo
# Mesmo sistema da Fase 0 (motor/modelo.py), agora georreferenciado.
# Coordenadas locais em metros (somadas à origem E0, N0).
def P(x, y):
    return QgsPointXY(E0 + x, N0 + y)


mult, media = padrao_consumo()
EX = {
    "captacao": [({"id": "CAP", "nome": "Captação", "carga_hidraulica": 100.0}, (0, 0))],
    "reservatorio": [({"id": "R1", "nome": "Reservatório R1", "cota_fundo": 130.0, "nivel_ini": 3.48,
                       "nivel_min": 0.0, "nivel_max": 6.0, "diametro": 10.505, "volume_util": 520.0},
                      (930, 600))],
    "bomba": [({"id": "B1", "nome": "Bomba 1", "elevatoria": "EEAT-01", "cota": 98.0,
                "curva": "CURVA_B1", "status_inicial": "ABERTA", "rotacao_relativa": 1.0}, (20, 0))],
    "valvula": [
        ({"id": "VRP1", "nome": "VRP 1", "tipo": "PRV", "cota": 92.0, "diametro": 150.0, "ajuste": 30.0,
          "status": "ATIVA", "perda_localizada": 0.0, "setor": "S1"}, (1760, 600)),
        ({"id": "VRP2", "nome": "VRP 2", "tipo": "PRV", "cota": 85.0, "diametro": 150.0, "ajuste": 18.0,
          "status": "ATIVA", "perda_localizada": 0.0, "setor": "S1"}, (2360, 600)),
        ({"id": "VRP3", "nome": "VRP 3", "tipo": "PRV", "cota": 90.0, "diametro": 150.0, "ajuste": 22.0,
          "status": "ATIVA", "perda_localizada": 0.0, "setor": "S2"}, (1160, 100)),
    ],
    "no_juncao": [
        ({"id": "R1_ENT", "nome": "Entrada R1", "tipo": "JUNCAO", "cota": 129.0, "demanda_base": 0.0}, (920, 600)),
        ({"id": "J_SAI", "nome": "Saída R1", "tipo": "JUNCAO", "cota": 104.0, "demanda_base": 0.0}, (960, 600)),
        ({"id": "S1", "nome": "Setor S1", "tipo": "CONSUMO", "cota": 82.0, "demanda_base": round(media * 0.62, 3),
          "padrao": "PAD_CONS", "setor": "S1"}, (2360, 1100)),
        ({"id": "S2", "nome": "Setor S2", "tipo": "CONSUMO", "cota": 87.0, "demanda_base": round(media * 0.38, 3),
          "padrao": "PAD_CONS", "setor": "S2"}, (1560, 100)),
    ],
}
# trechos: id, de, para, DN, material, status, vértices (comprimentos iguais aos da Fase 0)
TRECHOS = [
    ("T_SUCCAO", "CAP", "B1", 250, "Ferro fundido dúctil", "ABERTO", [(0, 0), (20, 0)]),
    ("T_RECALQUE", "B1", "R1_ENT", 200, "Ferro fundido dúctil", "CV", [(20, 0), (920, 0), (920, 600)]),
    ("T_ENT_R1", "R1_ENT", "R1", 200, "Ferro fundido dúctil", "ABERTO", [(920, 600), (930, 600)]),
    ("T_SAI_R1", "R1", "J_SAI", 250, "Ferro fundido dúctil", "ABERTO", [(930, 600), (960, 600)]),
    ("T_S1_A", "J_SAI", "VRP1", 200, "PVC DEFoFo", "ABERTO", [(960, 600), (1760, 600)]),
    ("T_S1_B", "VRP1", "VRP2", 150, "PVC DEFoFo", "ABERTO", [(1760, 600), (2360, 600)]),
    ("T_S1_C", "VRP2", "S1", 150, "PVC DEFoFo", "ABERTO", [(2360, 600), (2360, 1100)]),
    ("T_S2_A", "J_SAI", "VRP3", 150, "PVC DEFoFo", "ABERTO", [(960, 600), (960, 100), (1160, 100)]),
    ("T_S2_B", "VRP3", "S2", 150, "PVC DEFoFo", "ABERTO", [(1160, 100), (1560, 100)]),
]
TABELAS = {
    "padrao_consumo": [{"id_padrao": "PAD_CONS", "passo": i, "multiplicador": round(m, 4)} for i, m in enumerate(mult)],
    "curva": [{"id_curva": "CURVA_B1", "tipo": "BOMBA", "x": x, "y": y} for x, y in [(0, 55), (26, 42), (40, 30)]],
    "controle": [
        {"elemento": "B1", "acao": "ABERTA", "condicao": "NIVEL_ABAIXO", "no_ref": "R1", "valor": 2.52},
        {"elemento": "B1", "acao": "FECHADA", "condicao": "NIVEL_ACIMA", "no_ref": "R1", "valor": 5.28},
    ],
    "opcoes_simulacao": [{"chave": k, "valor": v} for k, v in [
        ("unidades", "LPS"), ("perda_carga", "H-W"), ("duracao_h", "24"), ("passo_hidraulico_min", "15"),
        ("passo_padrao_min", "15")]],
    "dominio_material": [{"material": k, "rugosidade_hw": v} for k, v in MATERIAIS.items()],
}

# ---------------------------------------------------------------- expressões do formulário
def expr_id(prefixo):
    """Próximo código livre: N-0001, N-0002..."""
    return (f"'{prefixo}-' || lpad(to_string(coalesce(maximum(to_int("
            f"regexp_substr(\"id\", '^{prefixo}-(\\\\d+)$'))), 0) + 1), 4, '0')")


def expr_no(ponta):
    """Código do nó (de qualquer camada de pontos) que toca a ponta do trecho."""
    partes = [f"aggregate('{APELIDOS[c]}', 'concatenate', \"id\", "
              f"intersects($geometry, buffer({ponta}_point(geometry(@parent)), 0.05)))" for c in PONTOS]
    return "coalesce(" + ", ".join(f"nullif({p}, '')" for p in partes) + ")"


RUG_MAPA = "map(" + ", ".join(f"'{k}', {v}" for k, v in MATERIAIS.items()) + ")"
FORM = {
    "no_juncao": {"id": (expr_id("N"), False), "situacao": ("'EXISTENTE'", False), "tipo": ("'JUNCAO'", False),
                  "demanda_base": ("0", False)},
    "valvula": {"id": (expr_id("V"), False), "situacao": ("'EXISTENTE'", False), "status": ("'ATIVA'", False),
                "perda_localizada": ("0", False)},
    "bomba": {"id": (expr_id("B"), False), "situacao": ("'EXISTENTE'", False),
              "status_inicial": ("'ABERTA'", False), "rotacao_relativa": ("1", False)},
    "reservatorio": {"id": (expr_id("R"), False), "situacao": ("'EXISTENTE'", False),
                     "volume_util": ("round(pi() * \"diametro\"^2 / 4 * (\"nivel_max\" - \"nivel_min\"), 1)", True)},
    "captacao": {"id": (expr_id("C"), False), "situacao": ("'EXISTENTE'", False)},
    "trecho": {"id": (expr_id("T"), False), "situacao": ("'EXISTENTE'", False), "status": ("'ABERTO'", False),
               "perda_localizada": ("0", False),
               "comprimento": ("round($length, 2)", True),
               "no_inicial": (expr_no("start"), True), "no_final": (expr_no("end"), True),
               "rugosidade_hw": (f"coalesce(\"rugosidade_hw\", map_get({RUG_MAPA}, \"material\"))", True)},
}
LISTAS = {
    "situacao": SITUACAO, "material": list(MATERIAIS), "tipo": None, "status": None,
    "status_inicial": ["ABERTA", "FECHADA"],
}


def value_map(valores):
    if isinstance(valores, dict):
        return QgsEditorWidgetSetup("ValueMap", {"map": [{v: k} for k, v in valores.items()]})
    return QgsEditorWidgetSetup("ValueMap", {"map": [{v: v} for v in valores]})


# ---------------------------------------------------------------- 1) GeoPackage
def criar_gpkg():
    if os.path.exists(GPKG):
        os.remove(GPKG)
    ctx = QgsCoordinateTransformContext()
    for i, (nome, (geom, campos)) in enumerate(CAMADAS.items()):
        uri = geom + (f"?crs={CRS.authid()}" if geom != "None" else "")
        mem = QgsVectorLayer(uri, nome, "memory")
        flds = QgsFields()
        for c, t in campos:
            flds.append(QgsField(c, t))
        mem.dataProvider().addAttributes(flds.toList())
        mem.updateFields()

        feats = []
        if nome in EX:
            for attrs, xy in EX[nome]:
                f = QgsFeature(mem.fields())
                for k, v in attrs.items():
                    f[k] = v
                if f["situacao"] in (None, "") or str(f["situacao"]) == "NULL":
                    f["situacao"] = "EXISTENTE"
                f.setGeometry(QgsGeometry.fromPointXY(P(*xy)))
                feats.append(f)
        elif nome == "trecho":
            for tid, a, b, dn, mat, st, pts in TRECHOS:
                f = QgsFeature(mem.fields())
                g = QgsGeometry.fromPolylineXY([P(*p) for p in pts])
                setor = "S1" if "_S1_" in tid else "S2" if "_S2_" in tid else None
                for k, v in {"id": tid, "no_inicial": a, "no_final": b, "comprimento": round(g.length(), 2),
                             "diametro_nominal": dn, "material": mat, "rugosidade_hw": 130.0,
                             "perda_localizada": 0.0, "status": st, "situacao": "EXISTENTE", "setor": setor}.items():
                    f[k] = v
                f.setGeometry(g)
                feats.append(f)
        else:
            for attrs in TABELAS.get(nome, []):
                f = QgsFeature(mem.fields())
                for k, v in attrs.items():
                    f[k] = v
                feats.append(f)
        mem.dataProvider().addFeatures(feats)

        opt = QgsVectorFileWriter.SaveVectorOptions()
        opt.driverName = "GPKG"
        opt.layerName = nome
        opt.fileEncoding = "UTF-8"
        opt.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if i == 0
                                    else QgsVectorFileWriter.CreateOrOverwriteLayer)
        err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, GPKG, ctx, opt)
        if err[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f"{nome}: {err}")
        print(f"  {nome:18s} {len(feats):3d} registros")


# ---------------------------------------------------------------- 2) Projeto QGIS
ESTILO_PONTO = {
    "captacao": {"name": "triangle", "color": "#1d8fd6", "size": "5", "outline_color": "#0b3470"},
    "reservatorio": {"name": "square", "color": "#35d0ff", "size": "5", "outline_color": "#0b3470"},
    "bomba": {"name": "circle", "color": "#ff6b7a", "size": "4.5", "outline_color": "#5a0d17"},
    "valvula": {"name": "diamond", "color": "#3ddc97", "size": "4.5", "outline_color": "#0f4d34"},
    "no_juncao": {"name": "circle", "color": "#ffffff", "size": "2.2", "outline_color": "#0b3470"},
}

def rotular(lyr, expr, tamanho=8):
    s = QgsPalLayerSettings()
    s.fieldName = expr
    s.isExpression = True
    fmt = QgsTextFormat()
    fmt.setSize(tamanho)
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    fmt.setBuffer(buf)
    s.setFormat(fmt)
    if lyr.geometryType() == QgsWkbTypes.LineGeometry:
        s.placement = Qgis.LabelPlacement.Line
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)


def criar_projeto():
    prj = QgsProject.instance()
    prj.clear()
    prj.setCrs(CRS)
    prj.setTitle("GWATER - Cadastro da rede de água")
    raiz = prj.layerTreeRoot()
    g_rede = raiz.addGroup("Rede de água")
    g_tab = raiz.addGroup("Tabelas do modelo")

    camadas = {}
    for nome in ["captacao", "reservatorio", "bomba", "valvula", "no_juncao", "trecho"] + \
                [n for n, (g, _) in CAMADAS.items() if g == "None"]:
        lyr = QgsVectorLayer(f"{GPKG}|layername={nome}", APELIDOS[nome], "ogr")
        assert lyr.isValid(), nome
        prj.addMapLayer(lyr, False)
        (g_rede if CAMADAS[nome][0] != "None" else g_tab).addLayer(lyr)
        camadas[nome] = lyr

        idx = lyr.fields().indexOf
        for campo, (expr, ao_atualizar) in FORM.get(nome, {}).items():
            lyr.setDefaultValueDefinition(idx(campo), QgsDefaultValue(expr, ao_atualizar))
        for campo, valores in LISTAS.items():
            if idx(campo) < 0:
                continue
            if campo == "tipo":
                valores = TIPO_VALVULA if nome == "valvula" else TIPO_NO if nome == "no_juncao" else None
            if campo == "status":
                valores = STATUS_VALVULA if nome == "valvula" else STATUS_TRECHO
            if valores:
                lyr.setEditorWidgetSetup(idx(campo), value_map(valores))

        if nome in ESTILO_PONTO:
            lyr.renderer().setSymbol(QgsMarkerSymbol.createSimple(ESTILO_PONTO[nome]))
            rotular(lyr, '"id"' if nome != "no_juncao" else "if(\"tipo\"='CONSUMO', \"id\", '')")
        elif nome == "trecho":
            sym = QgsLineSymbol.createSimple({"color": "#1668b0", "width": "0.8", "capstyle": "round"})
            sym.symbolLayer(0).setDataDefinedProperty(
                QgsSymbolLayer.PropertyStrokeWidth, QgsProperty.fromExpression('0.3 + "diametro_nominal" / 120'))
            sym.symbolLayer(0).setDataDefinedProperty(
                QgsSymbolLayer.PropertyStrokeColor,
                QgsProperty.fromExpression("CASE WHEN \"situacao\"='PROJETADO' THEN '#ffb547' "
                                           "WHEN \"situacao\"='DESATIVADO' THEN '#9aa5b1' ELSE '#1668b0' END"))
            lyr.renderer().setSymbol(sym)
            rotular(lyr, "'DN' || to_int(\"diametro_nominal\") || ' · ' || round(\"comprimento\") || ' m'", 7)

    osm = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
                         "OpenStreetMap", "wms")
    if osm.isValid():
        prj.addMapLayer(osm, False)
        raiz.addLayer(osm)

    snap = QgsSnappingConfig(prj)
    snap.setEnabled(True)
    snap.setMode(QgsSnappingConfig.AllLayers)
    snap.setTypeFlag(Qgis.SnappingType.Vertex)
    snap.setTolerance(12)
    snap.setUnits(QgsTolerance.Pixels)
    snap.setIntersectionSnapping(False)
    prj.setSnappingConfig(snap)
    prj.setTopologicalEditing(True)

    ext = camadas["trecho"].extent()
    ext.grow(250)
    prj.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, CRS))
    assert prj.write(PROJETO), "falha ao salvar o projeto"
    return camadas


def conferir(camadas):
    """Confere se as expressões do formulário reconhecem a topologia de exemplo."""
    from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
    lyr = camadas["trecho"]
    erros = 0
    for f in lyr.getFeatures():
        ctx = QgsExpressionContext(QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        ctx.setFeature(f)
        for campo, ponta in (("no_inicial", "start"), ("no_final", "end")):
            ex = QgsExpression(expr_no(ponta))
            calc = ex.evaluate(ctx)
            if calc != f[campo]:
                erros += 1
                print(f"  ! {f['id']}.{campo}: cadastro={f[campo]} expressão={calc} {ex.evalErrorString()}")
    print("  topologia conferida:", "OK" if not erros else f"{erros} divergências")


if __name__ == "__main__":
    qgs = QgsApplication([], False)
    qgs.initQgis()
    print("Criando", GPKG)
    criar_gpkg()
    camadas = criar_projeto()
    print("Projeto salvo em", PROJETO)
    conferir(camadas)
    qgs.exitQgis()
