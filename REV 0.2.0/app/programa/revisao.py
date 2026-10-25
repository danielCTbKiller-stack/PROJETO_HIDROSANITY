"""Revisão: comparação de cenários, histórico de alterações (Change Tracking) e arquivo compactado.

O histórico grava, a cada Salvar edições, o que entrou, saiu ou mudou (campo, antes e depois, quem e
quando) em <cadastro>_historico.sqlite, ao lado do cadastro (o cadastro em si não muda de formato).
"""
import getpass
import os
import sqlite3
import zipfile
from datetime import datetime

from qgis.core import QgsProject
from qgis.PyQt.QtWidgets import QComboBox, QFileDialog, QLineEdit

from gwater.estilo import COR

from .util import Dialogo, camada_resultado, janela_resultado, num, PONTOS

CHAVE = "GWATER"


# ================================================================ comparação de cenários
def comparar_cenarios(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    from .cenarios_ui import alteracoes_completas, listar
    todos = listar(gpkg)
    d = Dialogo(nucleo.janela, "Comparação de cenários",
                "Roda os dois cenários e compara: indicadores da rede (pressões, velocidades, atendimento) e a diferença "
                "elemento por elemento (B − A). Como o Scenario Comparison do WaterGEMS.")
    a, b = QComboBox(), QComboBox()
    for cmb in (a, b):
        cmb.addItem("Rede atual (base)", None)
        for c in todos:
            cmb.addItem(c["nome"], c["id"])
    if todos:
        b.setCurrentIndex(1)
    d.linha("Cenário A:", a)
    d.linha("Cenário B:", b)
    d.botoes("Comparar")
    if not d.exec():
        return
    alt = lambda cid: alteracoes_completas(next(c for c in todos if c["id"] == cid)) if cid else None
    from .analise_ui import rodar
    r = rodar(nucleo, "comparar", "Comparando os cenários…", cenario_a=alt(a.currentData()), cenario_b=alt(b.currentData()))
    if not r:
        return
    nomes = {"p_min": "Pressão mínima (mca)", "p_media": "Pressão média (mca)", "p_max": "Pressão máxima (mca)",
             "nos_abaixo_10": "Nós abaixo de 10 mca", "nos_acima_50": "Nós acima de 50 mca",
             "v_max": "Velocidade máxima (m/s)", "perda_max_m_km": "Perda de carga máx (m/km)",
             "tubos_v_alta": "Tubulações acima de 2,5 m/s", "atendimento_pct": "Atendimento da demanda (%)",
             "volume_entregue_m3": "Volume entregue no dia (m³)"}
    linhas = []
    for k, rot in nomes.items():
        va, vb = r["a"].get(k), r["b"].get(k)
        dif = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else ""
        linhas.append([rot, va, vb, round(dif, 3) if dif != "" else ""])
    camada_resultado(nucleo, "Comparação · pressão mínima B − A (mca)", {x["id"]: x["dif"] for x in r["nos"]}, "dif",
                     faixas=[(None, -2, "#e5484d", "B perde mais de 2 mca"), (-2, -0.1, "#f59f00", "B perde até 2 mca"),
                             (-0.1, 0.1, "#9aa5b1", "igual"), (0.1, 2, "#74c0fc", "B ganha até 2 mca"),
                             (2, None, "#1c7ed6", "B ganha mais de 2 mca")],
                     camadas=[c for c in PONTOS if _tem(nucleo, c)])
    w = janela_resultado(nucleo, "Comparação de cenários",
                         f"<b>A</b> = {a.currentText()} · <b>B</b> = {b.currentText()}. A camada 'Comparação' pinta os "
                         "nós pela diferença de pressão mínima. As tabelas de nós e tubulações estão nas abas seguintes.",
                         ["Indicador", "A", "B", "B − A"], linhas, "comparacao_indicadores", ao_clicar=lambda _c: None)
    janela_resultado(nucleo, "Comparação · nós", "Pressão mínima do dia em cada nó (maiores diferenças primeiro).",
                     ["Nó", "Pressão mín A (mca)", "Pressão mín B (mca)", "B − A"],
                     [[x["id"], x["p_min_a"], x["p_min_b"], x["dif"]] for x in r["nos"]], "comparacao_nos")
    janela_resultado(nucleo, "Comparação · tubulações", "Velocidade máxima do dia em cada tubulação.",
                     ["Tubulação", "Vel. máx A (m/s)", "Vel. máx B (m/s)", "B − A"],
                     [[x["id"], x["v_max_a"], x["v_max_b"], x["dif"]] for x in r["tubos"]], "comparacao_tubos")
    nucleo.janela.centro.setCurrentWidget(w)


def _tem(nucleo, c):
    try:
        nucleo.camada(c)
        return True
    except LookupError:
        return False


# ================================================================ histórico de alterações
def _arquivo(nucleo):
    gpkg = nucleo.cadastro()
    return os.path.splitext(gpkg)[0] + "_historico.sqlite" if gpkg else None


def _banco(nucleo):
    con = sqlite3.connect(_arquivo(nucleo))
    con.execute("CREATE TABLE IF NOT EXISTS historico (quando TEXT, usuario TEXT, camada TEXT, elemento TEXT, "
                "acao TEXT, campo TEXT, antes TEXT, depois TEXT)")
    return con


def ligado():
    return QgsProject.instance().readEntry(CHAVE, "rastreio", "1")[0] == "1"


def conectar(nucleo):
    """Liga o registro nas camadas do cadastro (chamado ao abrir o cadastro)."""
    for lyr in nucleo.camadas_rede():
        if lyr.property("gwater_rastreio"):
            continue
        lyr.setProperty("gwater_rastreio", True)
        lyr.beforeCommitChanges.connect(lambda *_a, l=lyr: _antes(nucleo, l))
        lyr.afterCommitChanges.connect(lambda l=lyr: _depois(nucleo, l))


def _antes(nucleo, lyr):
    if not ligado():
        return
    buf = lyr.editBuffer()
    if buf is None:
        return
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quem = getpass.getuser()
    nomes = lyr.fields().names()
    linhas = []
    idx_id = lyr.fields().indexOf("id")
    for fid, f in buf.addedFeatures().items():
        linhas.append((agora, quem, lyr.name(), str(f.attribute(idx_id)) if idx_id >= 0 else str(fid), "criado", "",
                       "", ""))
    prov = lyr.dataProvider()
    apagados = list(buf.deletedFeatureIds())
    mudados = buf.changedAttributeValues()
    geoms = buf.changedGeometries()
    originais = {f.id(): f for f in prov.getFeatures()} if (apagados or mudados or geoms) else {}
    for fid in apagados:
        o = originais.get(fid)
        linhas.append((agora, quem, lyr.name(), str(o.attribute(idx_id)) if o and idx_id >= 0 else str(fid),
                       "apagado", "", "", ""))
    for fid, mud in mudados.items():
        if fid < 0:
            continue
        o = originais.get(fid)
        for i, novo in mud.items():
            antes = o.attribute(i) if o else None
            linhas.append((agora, quem, lyr.name(), str(o.attribute(idx_id)) if o and idx_id >= 0 else str(fid),
                           "alterado", nomes[i] if i < len(nomes) else str(i),
                           "" if antes is None or str(antes) == "NULL" else str(antes),
                           "" if novo is None or str(novo) == "NULL" else str(novo)))
    for fid in geoms:
        if fid < 0:
            continue
        o = originais.get(fid)
        linhas.append((agora, quem, lyr.name(), str(o.attribute(idx_id)) if o and idx_id >= 0 else str(fid),
                       "movido", "geometria", "", ""))
    lyr.setProperty("gwater_pendente", linhas)


def _depois(nucleo, lyr):
    linhas = lyr.property("gwater_pendente") or []
    lyr.setProperty("gwater_pendente", [])
    if not linhas or not ligado():
        return
    try:
        con = _banco(nucleo)
        con.executemany("INSERT INTO historico VALUES (?,?,?,?,?,?,?,?)", linhas)
        con.commit()
        con.close()
    except sqlite3.Error as e:
        nucleo.aviso(f"Histórico de alterações: não consegui gravar ({e}).")


def rastreio_ligar(nucleo):
    novo = "0" if ligado() else "1"
    QgsProject.instance().writeEntry(CHAVE, "rastreio", novo)
    nucleo.informar("Histórico de alterações " + ("ligado: cada Salvar edições fica registrado." if novo == "1"
                                                  else "desligado."))


def rastreio_ver(nucleo):
    if not nucleo.cadastro():
        return
    arq = _arquivo(nucleo)
    if not os.path.exists(arq):
        return nucleo.informar("Ainda não há alterações registradas (o registro acontece a cada Salvar edições).")
    con = _banco(nucleo)
    linhas = [list(r) for r in con.execute("SELECT * FROM historico ORDER BY quando DESC LIMIT 20000")]
    con.close()
    janela_resultado(nucleo, "Histórico de alterações",
                     f"{len(linhas)} registro(s) em {os.path.basename(arq)} · registro "
                     f"{'ligado' if ligado() else 'DESLIGADO'}. Clique duplo leva até o elemento.",
                     ["Elemento", "Quando", "Usuário", "Camada", "Ação", "Campo", "Antes", "Depois"],
                     [[r[3], *r[:3], *r[4:]] for r in linhas], "historico")


def rastreio(nucleo):
    rastreio_ver(nucleo)


# ================================================================ arquivo compactado
def arquivar(nucleo):
    gpkg = nucleo.cadastro()
    if not gpkg:
        return
    base = os.path.splitext(gpkg)[0]
    nome = os.path.basename(base)
    padrao = os.path.join(os.path.dirname(gpkg), f"{nome}_{datetime.now():%Y%m%d_%H%M}.zip")
    arq, _ = QFileDialog.getSaveFileName(nucleo.janela, "Arquivo compactado do cadastro", padrao, "ZIP (*.zip)")
    if not arq:
        return
    pendentes = [l for l in nucleo.camadas_rede() if l.isEditable() and l.isModified()]
    if pendentes:
        nucleo.aviso("Há edições não salvas: o arquivo leva o cadastro como está gravado em disco.")
    pasta = os.path.dirname(gpkg)
    arquivos = [gpkg, QgsProject.instance().fileName()]
    for suf in ("_dados_recebidos.json", "_historico.sqlite", "_telemetria.sqlite", ".inp"):
        if os.path.exists(base + suf):
            arquivos.append(base + suf)
    with zipfile.ZipFile(arq, "w", zipfile.ZIP_DEFLATED) as z:
        for a in arquivos:
            if a and os.path.exists(a):
                z.write(a, os.path.relpath(a, pasta))
    nucleo.informar(f"Arquivo criado: {arq} ({len(arquivos)} arquivos).")


ACOES = {"comparar_cenarios": comparar_cenarios, "rastreio": rastreio, "rastreio_ligar": rastreio_ligar,
         "rastreio_ver": rastreio_ver, "arquivar": arquivar}
