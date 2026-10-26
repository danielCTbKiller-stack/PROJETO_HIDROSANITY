"""Revisão: comparação de cenários, histórico de alterações (Change Tracking) e arquivo compactado.

O histórico grava, a cada Salvar edições, o que entrou, saiu ou mudou (campo, antes e depois, quem e
quando) em <cadastro>_historico.sqlite, ao lado do cadastro (o cadastro em si não muda de formato).
"""
import getpass
import os
import sqlite3
import zipfile
from datetime import datetime

from qgis.core import QgsFeatureRequest, QgsProject
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
    quando = QComboBox()
    quando.addItem("O dia todo (pressão mínima, velocidade e vazão máximas)", None)
    for h in range(24):
        quando.addItem(f"Às {h:02d}:00", float(h))
    d.linha("Comparar:", quando, "Scenario Comparison do WaterGEMS: o dia todo ou um instante")
    d.botoes("Comparar")
    if not d.exec():
        return
    alt = lambda cid: alteracoes_completas(next(c for c in todos if c["id"] == cid)) if cid else None
    from .analise_ui import rodar
    from .componentes import limites
    lim = limites(nucleo)
    r = rodar(nucleo, "comparar", "Comparando os cenários…", cenario_a=alt(a.currentData()), cenario_b=alt(b.currentData()),
              limites=lim, hora=quando.currentData())
    if not r:
        return
    nomes = {"p_min": "Pressão mínima (mca)", "p_media": "Pressão média (mca)", "p_max": "Pressão máxima (mca)",
             "nos_abaixo_10": f"Nós abaixo de {num(lim['limite_pressao_min'], 1)} mca",
             "nos_acima_50": f"Nós acima de {num(lim['limite_pressao_max'], 1)} mca",
             "v_max": "Velocidade máxima (m/s)", "perda_max_m_km": "Perda de carga máx (m/km)",
             "tubos_v_alta": f"Tubulações acima de {num(lim['limite_velocidade'], 2)} m/s",
             "atendimento_pct": "Atendimento da demanda (%)", "volume_entregue_m3": "Volume entregue no dia (m³)"}
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
    qual = "mínima do dia" if quando.currentData() is None else f"às {int(quando.currentData()):02d}:00"
    janela_resultado(nucleo, "Comparação · nós", f"Pressão {qual} em cada nó (maiores diferenças primeiro).",
                     ["Nó", "Pressão A (mca)", "Pressão B (mca)", "B − A"],
                     [[x["id"], x["p_min_a"], x["p_min_b"], x["dif"]] for x in r["nos"]], "comparacao_nos")
    janela_resultado(nucleo, "Comparação · tubulações",
                     f"Velocidade e vazão {'máximas do dia' if quando.currentData() is None else qual} em cada tubulação.",
                     ["Tubulação", "Velocidade A (m/s)", "Velocidade B (m/s)", "B − A", "Vazão A (L/s)", "Vazão B (L/s)",
                      "B − A (L/s)"],
                     [[x["id"], x["v_max_a"], x["v_max_b"], x["dif"], x.get("q_a"), x.get("q_b"), x.get("dif_q")]
                      for x in r["tubos"]], "comparacao_tubos")
    dados = diferencas_dados(alt(a.currentData()) or [], alt(b.currentData()) or [])
    janela_resultado(nucleo, "Comparação · dados",
                     f"O que muda nos dados de entrada entre A e B ({len(dados)} diferença(s)): os valores que cada cenário "
                     "altera em relação à rede atual. Vazio = igual à rede atual.",
                     ["Camada", "Elemento", "Campo", "Valor em A", "Valor em B"], dados, "comparacao_dados")
    nucleo.janela.centro.setCurrentWidget(w)


def diferencas_dados(alts_a, alts_b):
    """Linhas [camada, elemento, campo, valor A, valor B] onde os dois cenários diferem nos dados de entrada."""
    def mapa(alts):
        return {(x["camada"], str(x.get("id") or ""), x["campo"]): str(x["valor"]) for x in alts}
    ma, mb = mapa(alts_a), mapa(alts_b)
    out = []
    for k in sorted(set(ma) | set(mb)):
        if ma.get(k) != mb.get(k):
            out.append([k[0], k[1] or "(rede toda)", k[2], ma.get(k, ""), mb.get(k, "")])
    return out


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
    # só os elementos mexidos (ler a camada inteira travava o salvar em cadastros grandes)
    alvo = [fid for fid in set(apagados) | set(mudados) | set(geoms) if fid >= 0]
    originais = {f.id(): f for f in prov.getFeatures(QgsFeatureRequest().setFilterFids(alvo)
                                                    .setFlags(QgsFeatureRequest.Flag.NoGeometry))} if alvo else {}
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


def ler_historico(nucleo, de="", ate="", usuario="", elemento="", campo=""):
    """Registros do histórico com os filtros (datas AAAA-MM-DD; textos contidos), mais novos primeiro."""
    con = _banco(nucleo)
    sql, par = "SELECT * FROM historico WHERE 1=1", []
    if de:
        sql, par = sql + " AND quando >= ?", par + [de]
    if ate:
        sql, par = sql + " AND quando <= ?", par + [ate + " 99"]
    for col, v in (("usuario", usuario), ("elemento", elemento), ("campo", campo)):
        if v:
            sql, par = sql + f" AND {col} LIKE ?", par + [f"%{v}%"]
    linhas = [list(r) for r in con.execute(sql + " ORDER BY quando DESC LIMIT 20000", par)]
    con.close()
    return linhas


def rastreio_ver(nucleo):
    if not nucleo.cadastro():
        return
    arq = _arquivo(nucleo)
    if not os.path.exists(arq):
        return nucleo.informar("Ainda não há alterações registradas (o registro acontece a cada Salvar edições).")
    d = Dialogo(nucleo.janela, "Histórico de alterações",
                "Filtre o que quer ver (deixe em branco para tudo). Na lista, selecione linhas 'alterado' e use "
                "Desfazer as selecionadas para voltar ao valor de antes (fica na edição).")
    de, ate, usu, el, cp = (QLineEdit() for _ in range(5))
    de.setPlaceholderText("AAAA-MM-DD")
    ate.setPlaceholderText("AAAA-MM-DD")
    for rot, w in (("De:", de), ("Até:", ate), ("Usuário:", usu), ("Elemento:", el), ("Campo:", cp)):
        d.linha(rot, w)
    d.botoes("Ver")
    if not d.exec():
        return
    linhas = ler_historico(nucleo, de.text().strip(), ate.text().strip(), usu.text().strip(), el.text().strip(),
                           cp.text().strip())
    w = janela_resultado(nucleo, "Histórico de alterações",
                         f"{len(linhas)} registro(s) em {os.path.basename(arq)} · registro "
                         f"{'ligado' if ligado() else 'DESLIGADO'}. Clique duplo leva até o elemento.",
                         ["Elemento", "Quando", "Usuário", "Camada", "Ação", "Campo", "Antes", "Depois"],
                         [[r[3], *r[:3], *r[4:]] for r in linhas], "historico",
                         extras=[("Desfazer as selecionadas", lambda: desfazer_registros(nucleo, _linhas_sel(w)))])


def _linhas_sel(w):
    t = w.tabela
    rows = sorted({i.row() for i in t.selectedIndexes()})
    return [[t.item(r, c).text() if t.item(r, c) else "" for c in range(t.columnCount())] for r in rows]


def desfazer_registros(nucleo, linhas):
    """Volta ao valor de antes as alterações de campo do histórico (linhas no formato da tabela do histórico)."""
    feitos, pulados = 0, 0
    por_camada = {}
    for el, _q, _u, camada, acao, campo, antes, _dep in linhas:
        if acao != "alterado" or not campo:
            pulados += 1
            continue
        por_camada.setdefault(camada, []).append((el, campo, antes))
    for lyr in nucleo.camadas_rede():
        regs = por_camada.get(lyr.name())
        if not regs:
            continue
        fid = {str(f["id"]): f.id() for f in lyr.getFeatures()}
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.beginEditCommand("Desfazer pelo histórico")
        for el, campo, antes in regs:
            i = lyr.fields().indexOf(campo)
            if el not in fid or i < 0:
                pulados += 1
                continue
            fld = lyr.fields()[i]
            v = None if antes == "" else antes
            if v is not None and fld.isNumeric():
                try:
                    v = float(v.replace(",", "."))
                    v = int(v) if fld.type() in (2, 4) else v
                except ValueError:
                    pass
            lyr.changeAttributeValue(fid[el], i, v)
            feitos += 1
        lyr.endEditCommand()
    nucleo.janela.canvas.refresh()
    nucleo.informar(f"{feitos} alteração(ões) desfeita(s) (fica na edição: Salvar edições grava)"
                    + (f"; {pulados} linha(s) ignorada(s) (só 'alterado' volta)." if pulados else "."))
    return feitos


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
