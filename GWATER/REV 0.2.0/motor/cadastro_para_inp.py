"""Converte o cadastro (GeoPackage do QGIS) em modelo EPANET (.inp), validando a rede.

Uso:  python cadastro_para_inp.py [cadastro.gpkg] [saida.inp] [--com-projetados]

Regras (ver cadastro/MODELO_DE_DADOS.md):
- bomba e válvula são pontos no cadastro; no EPANET viram um link entre dois
  nós internos  <id>__M (montante) e <id>__J (jusante), na cota do ponto;
- o trecho que chega no ponto liga em <id>__M, o que sai liga em <id>__J;
- elementos DESATIVADOS são ignorados; PROJETADOS só entram com --com-projetados.
"""
import math
import os
import sys
from collections import defaultdict

import pyogrio

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPKG_PADRAO = os.path.join(RAIZ, "cadastro", "gwater_cadastro.gpkg")
TOL_PONTA = 0.05  # m: distância máxima entre a ponta do trecho e o nó

STATUS_TRECHO = {"ABERTO": "Open", "FECHADO": "Closed", "CV": "CV"}
STATUS_LINK = {"ABERTA": "Open", "INATIVA": "Open", "FECHADA": "Closed"}
CONDICAO = {"NIVEL_ABAIXO": "BELOW", "NIVEL_ACIMA": "ABOVE",
            "PRESSAO_ABAIXO": "BELOW", "PRESSAO_ACIMA": "ABOVE"}


class Relatorio:
    """Erros e avisos; ref=(camada, id) aponta a feição para o QGIS dar zoom."""

    def __init__(self):
        self.erros, self.avisos, self.refs = [], [], {}

    def erro(self, msg, ref=None):
        self.erros.append(msg)
        self.refs[msg] = ref

    def aviso(self, msg, ref=None):
        self.avisos.append(msg)
        self.refs[msg] = ref

    @property
    def ok(self):
        return not self.erros

    def itens(self):
        return [{"nivel": nivel, "msg": m, "camada": (self.refs.get(m) or (None, None))[0],
                 "id": (self.refs.get(m) or (None, None))[1]}
                for nivel, lista in (("ERRO", self.erros), ("AVISO", self.avisos)) for m in lista]

    def texto(self):
        linhas = [f"ERRO   {m}" for m in self.erros] + [f"AVISO  {m}" for m in self.avisos]
        return "\n".join(linhas) or "Rede sem erros nem avisos."


def _vazio(v):
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v.strip())


# ---------------------------------------------------------------- controles lógicos (Logical Controls)
# tabela regra: uma linha por condição ou ação
#   id_regra, prioridade, ordem, secao (SE | ENTAO | SENAO), conector (SE | E | OU; nas ações, E),
#   elemento (código, ou SISTEMA), atributo, operador, valor
ATRIB_CONDICAO = {"PRESSAO": "PRESSURE", "CARGA": "HEAD", "NIVEL": "LEVEL", "DEMANDA": "DEMAND", "VAZAO": "FLOW",
                  "STATUS": "STATUS", "AJUSTE": "SETTING", "HORA_RELOGIO": "CLOCKTIME", "TEMPO": "TIME",
                  "DEMANDA_SISTEMA": "DEMAND"}
OPERADORES = {"=": "=", "<>": "<>", "<": "<", ">": ">", "<=": "<=", ">=": ">="}
VALOR_STATUS = {"ABERTA": "OPEN", "FECHADA": "CLOSED", "ATIVA": "ACTIVE", "ABERTO": "OPEN", "FECHADO": "CLOSED"}


def regras_epanet(df, nos, tubos, rel):
    """Linhas da seção [RULES] do EPANET a partir da tabela regra (vazia se não houver)."""
    if df is None or not len(df):
        return []
    out = []
    df = df.sort_values(["id_regra", "ordem"])
    links = {n for n, (cam, _, _) in nos.items() if cam in ("bomba", "valvula")} | set(tubos)
    nos_hid = {n for n, (cam, _, _) in nos.items() if cam not in ("bomba", "valvula")}

    def tempo(v):
        h = float(str(v).replace(",", "."))
        return f"{int(h)}:{int(round((h - int(h)) * 60)):02d}"

    for rid, g in df.groupby("id_regra", sort=False):
        linhas, erro = [f"RULE {str(rid).replace(' ', '_')}"], False
        conds = g[g["secao"] == "SE"]
        if not len(conds) or not len(g[g["secao"] == "ENTAO"]):
            rel.erro(f"controle lógico {rid}: precisa de pelo menos uma condição (SE) e uma ação (ENTÃO)")
            continue
        for k, (_, r) in enumerate(conds.iterrows()):
            con = "IF" if k == 0 else ("OR" if str(r["conector"]).upper() == "OU" else "AND")
            el, at = str(r["elemento"] or "").strip(), str(r["atributo"] or "").upper()
            op = OPERADORES.get(str(r["operador"] or "=").strip())
            if not op or at not in ATRIB_CONDICAO:
                rel.erro(f"controle lógico {rid}: condição com atributo '{at}' ou operador '{r['operador']}' inválido")
                erro = True
                continue
            if el.upper() == "SISTEMA" or at in ("HORA_RELOGIO", "TEMPO", "DEMANDA_SISTEMA"):
                v = tempo(r["valor"]) if at in ("HORA_RELOGIO", "TEMPO") else f"{float(r['valor']):g}"
                linhas.append(f"{con} SYSTEM {ATRIB_CONDICAO[at]} {op} {v}")
            elif el in links and at in ("VAZAO", "STATUS", "AJUSTE"):
                v = VALOR_STATUS.get(str(r["valor"]).upper(), str(r["valor"])) if at == "STATUS" else \
                    f"{float(str(r['valor']).replace(',', '.')):g}"
                linhas.append(f"{con} LINK {el} {ATRIB_CONDICAO[at]} {op if at != 'STATUS' else ('IS' if op == '=' else 'NOT')} {v}")
            elif el in nos_hid and at in ("PRESSAO", "CARGA", "NIVEL", "DEMANDA"):
                linhas.append(f"{con} NODE {el} {ATRIB_CONDICAO[at]} {op} {float(str(r['valor']).replace(',', '.')):g}")
            else:
                rel.erro(f"controle lógico {rid}: '{el}' não existe ou não tem {at.lower()}")
                erro = True
        for secao, palavra in (("ENTAO", "THEN"), ("SENAO", "ELSE")):
            for k, (_, r) in enumerate(g[g["secao"] == secao].iterrows()):
                el, at = str(r["elemento"] or "").strip(), str(r["atributo"] or "").upper()
                if el not in links:
                    rel.erro(f"controle lógico {rid}: a ação tem que ser numa bomba, válvula ou tubulação ('{el}')")
                    erro = True
                    continue
                if at == "STATUS":
                    v = VALOR_STATUS.get(str(r["valor"]).upper())
                    if not v:
                        rel.erro(f"controle lógico {rid}: status '{r['valor']}' inválido (ABERTA ou FECHADA)")
                        erro = True
                        continue
                    acao = f"LINK {el} STATUS IS {v}"
                else:
                    try:
                        acao = f"LINK {el} SETTING IS {float(str(r['valor']).replace(',', '.')):g}"
                    except ValueError:
                        rel.erro(f"controle lógico {rid}: ajuste '{r['valor']}' não é número")
                        erro = True
                        continue
                linhas.append(f"{palavra if k == 0 else 'AND'} {acao}")
        pri = g["prioridade"].dropna()
        if len(pri) and float(pri.iloc[0]) > 0:
            linhas.append(f"PRIORITY {float(pri.iloc[0]):g}")
        if not erro:
            out += linhas + [""]
    return out


def passos_padrao(formato, pontos, passo_min, ciclo_h=24.0):
    """Multiplicadores do EPANET (um por passo de `passo_min`) de um padrão do WaterGEMS.
    pontos: [(hora desde o início, multiplicador)], com a hora 0 = multiplicador inicial. O ciclo tem 24 h (ou
    vai até o último ponto, se passar disso). DEGRAUS: vale o último ponto já alcançado. CONTINUO: reta entre os
    pontos, fechando o ciclo no multiplicador inicial; cada passo leva o valor do meio do passo."""
    pts = sorted(pontos)
    if not pts:
        return [1.0]
    if pts[0][0] > 0:
        pts.insert(0, (0.0, pts[0][1]))
    ciclo = max(ciclo_h, pts[-1][0])
    n = max(1, int(round(ciclo * 60 / passo_min)))
    out = []
    for k in range(n):
        if str(formato).upper().startswith("CONT"):
            t = (k + 0.5) * passo_min / 60
            fim = pts + ([(ciclo, pts[0][1])] if pts[-1][0] < ciclo else [])
            a = max(i for i, (h, _) in enumerate(fim) if h <= t)
            if a + 1 < len(fim):
                (h0, m0), (h1, m1) = fim[a], fim[a + 1]
                v = m0 + (m1 - m0) * (t - h0) / (h1 - h0) if h1 > h0 else m1
            else:
                v = fim[a][1]
        else:
            t = k * passo_min / 60 + 1e-9
            v = [m for h, m in pts if h <= t][-1]
        out.append(round(v, 4))
    return out


def curva_rendimento(pts):
    """Pontos (vazão L/s, rendimento %) para o EPANET a partir da definição do rendimento, como no WaterGEMS:
    1 ponto em vazão 0 = constante; 1 ponto com vazão = melhor rendimento (BEP), parábola que zera em 0 e em 2·Q;
    vários pontos = a própria curva."""
    pts = sorted(pts)
    if len(pts) == 1 and pts[0][0] <= 0:
        return [(0.0, pts[0][1]), (100000.0, pts[0][1])]
    if len(pts) == 1:
        qb, eb = pts[0]
        return [(round(qb * k / 5, 4), round(max(1.0, eb * (2 * k / 5 - (k / 5) ** 2)), 2)) for k in range(11)]
    return pts


def ler_cadastro(gpkg):
    camadas = {}
    for nome, _ in pyogrio.list_layers(gpkg):
        df = pyogrio.read_dataframe(gpkg, layer=nome)
        camadas[nome] = df.astype(object).where(df.notna(), None)
    return camadas


# campos que uma proposta pode alterar, por camada (o resto do cadastro fica como está)
EDITAVEIS = {
    "trecho": {"diametro_nominal": float, "rugosidade_hw": float, "status": str, "situacao": str,
               "perda_localizada": float},
    "valvula": {"ajuste": float, "status": str, "situacao": str},
    "bomba": {"status_inicial": str, "rotacao_relativa": float, "situacao": str},
    "no_juncao": {"demanda_base": float, "cota": float},
    "reservatorio": {"nivel_ini": float},
    "captacao": {"carga_hidraulica": float},
}


def aplicar_alteracoes(c, alteracoes, rel):
    """Aplica uma proposta sobre o cadastro lido: [{camada, id, campo, valor}, ...].

    camada 'global' + campo 'fator_demanda' multiplica todas as demandas.
    Forçar bomba desligada (status_inicial FECHADA) ou válvula FECHADA remove os
    controles automáticos daquele elemento, senão eles religariam o equipamento.
    """
    for a in alteracoes or []:
        camada, eid, campo, valor = a.get("camada"), a.get("id"), a.get("campo"), a.get("valor")
        if camada == "global" and campo == "fator_demanda":
            f = float(valor)
            c["no_juncao"]["demanda_base"] = c["no_juncao"]["demanda_base"].map(lambda d: None if d is None else d * f)
            if "consumidor" in c:
                c["consumidor"]["demanda_base"] = c["consumidor"]["demanda_base"].map(
                    lambda d: None if d is None else d * f)
            continue
        if camada == "global" and campo == "modelo_demanda":  # PDA (padrão) ou DDA
            o = c["opcoes_simulacao"]
            o = o[o["chave"] != "modelo_demanda"].copy()
            o.loc[len(o) + 1000] = {"chave": "modelo_demanda", "valor": str(valor).upper()}
            c["opcoes_simulacao"] = o
            continue
        tipo = EDITAVEIS.get(camada, {}).get(campo)
        if not tipo:
            rel.erro(f"proposta: o campo '{campo}' de {camada} não pode ser alterado", ref=(camada, eid))
            continue
        df = c[camada]
        m = df["id"] == eid
        if not m.any():
            rel.erro(f"proposta altera '{eid}', que não existe em {camada}", ref=(camada, eid))
            continue
        try:
            df.loc[m, campo] = tipo(valor)
        except (TypeError, ValueError):
            rel.erro(f"proposta: valor '{valor}' inválido para {camada} {eid}.{campo}", ref=(camada, eid))
            continue
        if (camada, campo, str(valor)) in (("bomba", "status_inicial", "FECHADA"), ("valvula", "status", "FECHADA")):
            ctl = c["controle"]
            if (ctl["elemento"] == eid).any():
                c["controle"] = ctl[ctl["elemento"] != eid]
                rel.aviso(f"proposta: controles automáticos de {eid} desconsiderados (forçado fechado)",
                          ref=(camada, eid))
            rg = c.get("regra")
            if rg is not None and len(rg):
                alvo = rg[(rg["secao"] != "SE") & (rg["elemento"] == eid)]["id_regra"].unique()
                if len(alvo):
                    c["regra"] = rg[~rg["id_regra"].isin(alvo)]
                    rel.aviso(f"proposta: controles lógicos que mexem em {eid} desconsiderados (forçado fechado)",
                              ref=(camada, eid))


def consumidores(c, ativos, nos, ligados, pipes, trechos, rel):
    """Consumidores (Customer Meter do WaterGEMS): cada um é ligado a um nó ou a uma tubulação, sem trecho próprio.
    Ligado a nó, a demanda vai para o nó; ligado a tubulação, metade para cada ponta (só pontas que são nós de
    junção; se uma ponta é bomba, válvula ou reservatório, a outra fica com tudo). Sem ligação válida, vai para o
    nó ou o meio de tubulação mais perto. Devolve {nó: [(demanda, padrão, categoria)]}."""
    out = defaultdict(list)
    df = c.get("consumidor")
    if df is None or not len(df):
        return out
    juncoes = {nid: xy for nid, (cam, _, xy) in nos.items() if cam == "no_juncao" and nid in ligados}
    validos = {p["id"]: (p["a"], p["b"]) for p in pipes}
    meios = {}
    for _, t in trechos.iterrows():
        if t["id"] in validos and t.geometry is not None:
            m = t.geometry.interpolate(0.5, normalized=True)
            meios[t["id"]] = (m.x, m.y)
    for _, r in ativos(df).iterrows():
        cid = r["id"] or "(sem id)"
        q = r["demanda_base"]
        if _vazio(q) or q == 0:
            continue
        alvo, tipo = r.get("ligado_a"), (r.get("tipo_ligacao") or "").upper()
        if _vazio(alvo) or (alvo not in juncoes and alvo not in validos):
            if r.geometry is None:
                rel.erro(f"consumidor {cid}: sem posição e sem ligação", ref=("consumidor", cid))
                continue
            xy = (r.geometry.x, r.geometry.y)
            cand = [(math.dist(xy, p), k, "NO") for k, p in juncoes.items()] +                    [(math.dist(xy, p), k, "TRECHO") for k, p in meios.items()]
            if not cand:
                rel.erro(f"consumidor {cid}: não há nó nem tubulação para ligar", ref=("consumidor", cid))
                continue
            _, alvo, tipo = min(cand)
            if not _vazio(r.get("ligado_a")):
                rel.aviso(f"consumidor {cid}: '{r['ligado_a']}' não existe mais, ligado a {alvo} (o mais perto)",
                          ref=("consumidor", cid))
        elif alvo in validos and (tipo == "TRECHO" or alvo not in juncoes):
            tipo = "TRECHO"
        else:
            tipo = "NO"
        cat = f"consumidor {cid}"
        pad = r.get("padrao") or ""
        if tipo == "NO":
            out[alvo].append((float(q), pad, cat))
            continue
        pontas = [n for n in validos[alvo] if n in juncoes]
        if not pontas:  # tubulação entre válvulas, bombas ou reservatórios: o nó de junção mais perto
            if not juncoes or r.geometry is None:
                rel.erro(f"consumidor {cid}: a tubulação {alvo} não tem nó de junção nas pontas",
                         ref=("consumidor", cid))
                continue
            xy = (r.geometry.x, r.geometry.y)
            pontas = [min(juncoes, key=lambda k: math.dist(xy, juncoes[k]))]
            rel.aviso(f"consumidor {cid}: a tubulação {alvo} não tem nó de junção nas pontas, demanda no nó "
                      f"{pontas[0]} (o mais perto)", ref=("consumidor", cid))
        for n in pontas:
            out[n].append((float(q) / len(pontas), pad, cat))
    return out


def converter(gpkg=GPKG_PADRAO, com_projetados=False, alteracoes=None, camadas=None):
    """Retorna (texto_inp, relatorio). Se houver erros, o texto vem vazio.

    camadas: cadastro já lido (ler_cadastro) - a calibração usa para não reler o arquivo a cada rodada.
    """
    rel = Relatorio()
    c = {k: v.copy() for k, v in camadas.items()} if camadas is not None else ler_cadastro(gpkg)
    aplicar_alteracoes(c, alteracoes, rel)
    ativos = lambda df: df[df["situacao"].isin(["EXISTENTE", "PROJETADO"] if com_projetados else ["EXISTENTE"])
                           | df["situacao"].isna()]

    # ---------------------------------------------------- nós (todas as camadas de pontos)
    nos = {}  # id -> (camada, registro, (x, y))
    for camada in ("captacao", "reservatorio", "bomba", "valvula", "no_juncao"):
        for _, r in ativos(c[camada]).iterrows():
            nid = r["id"]
            if _vazio(nid):
                rel.erro(f"{camada}: elemento sem código (id)", ref=(camada, None))
                continue
            if nid in nos:
                rel.erro(f"código '{nid}' repetido ({nos[nid][0]} e {camada})", ref=(camada, nid))
                continue
            nos[nid] = (camada, r, (r.geometry.x, r.geometry.y))

    # ---------------------------------------------------- trechos e topologia
    trechos = ativos(c["trecho"])
    rugos = dict(zip(c["dominio_material"]["material"], c["dominio_material"]["rugosidade_hw"]))
    pipes, chegam, saem, ligados = [], defaultdict(list), defaultdict(list), set()
    # códigos repetidos: no EPANET tubulações, bombas e válvulas dividem o mesmo espaço de nomes
    cont = defaultdict(int)
    for v in trechos["id"]:
        if not _vazio(v):
            cont[str(v)] += 1
    for v, n in cont.items():
        if n > 1:
            rel.erro(f"código '{v}' repetido em {n} tubulações: cada tubulação precisa de um código só dela "
                     "(Ferramentas > Centro de códigos renumera os repetidos)", ref=("trecho", v))
        elif v in nos and nos[v][0] in ("bomba", "valvula"):
            rel.erro(f"código '{v}' é de uma tubulação e de uma {nos[v][0]} ao mesmo tempo: troque um dos dois",
                     ref=("trecho", v))
    for _, t in trechos.iterrows():
        tid = t["id"] or "(sem id)"
        a, b = t["no_inicial"], t["no_final"]
        g = t.geometry
        ok = True
        for campo, nid, ponta in (("no_inicial", a, g.coords[0]), ("no_final", b, g.coords[-1])):
            if _vazio(nid):
                rel.erro(f"trecho {tid}: {campo} vazio (a ponta não está encaixada em um nó)", ref=("trecho", tid))
                ok = False
            elif nid not in nos:
                rel.erro(f"trecho {tid}: {campo} '{nid}' não existe ou está desativado", ref=("trecho", tid))
                ok = False
            elif math.dist(ponta, nos[nid][2]) > TOL_PONTA:
                rel.erro(f"trecho {tid}: {campo} diz '{nid}', mas a ponta está a "
                         f"{math.dist(ponta, nos[nid][2]):.2f} m dele (atributo desatualizado?)", ref=("trecho", tid))
                ok = False
        if a == b and not _vazio(a):
            rel.erro(f"trecho {tid}: começa e termina no mesmo nó '{a}'", ref=("trecho", tid))
            ok = False
        dn = t["diametro_nominal"]
        if _vazio(dn) or dn <= 0:
            rel.erro(f"trecho {tid}: diâmetro inválido ({dn})", ref=("trecho", tid))
            ok = False
        C = t["rugosidade_hw"]
        if _vazio(C):
            C = rugos.get(t["material"])
            if _vazio(C):
                rel.erro(f"trecho {tid}: sem rugosidade e material '{t['material']}' sem C padrão", ref=("trecho", tid))
                ok = False
            else:
                rel.aviso(f"trecho {tid}: rugosidade vazia, usado C={C:g} do material {t['material']}", ref=("trecho", tid))
        L = t["comprimento"] if not _vazio(t["comprimento"]) else g.length
        if L <= 0:
            rel.erro(f"trecho {tid}: comprimento zero", ref=("trecho", tid))
            ok = False
        if not ok:
            continue
        saem[a].append(tid)
        chegam[b].append(tid)
        ligados.update((a, b))
        pipes.append(dict(id=tid, a=a, b=b, L=L, D=dn, C=C, km=t["perda_localizada"] or 0,
                          st=STATUS_TRECHO.get(t["status"] or "ABERTO", "Open"), vert=list(g.coords)[1:-1]))

    # bombas e válvulas: exatamente um trecho chegando e um saindo
    for nid, (camada, r, _) in nos.items():
        if camada in ("bomba", "valvula"):
            if len(chegam[nid]) != 1 or len(saem[nid]) != 1:
                rel.erro(f"{camada} {nid}: precisa de 1 trecho chegando e 1 saindo "
                         f"(tem {len(chegam[nid])} chegando e {len(saem[nid])} saindo)", ref=(camada, nid))
        elif nid not in ligados:
            rel.aviso(f"{camada} {nid}: nó isolado (nenhum trecho ligado), será ignorado", ref=(camada, nid))

    def no_epanet(nid, lado):
        return f"{nid}__{lado}" if nos[nid][0] in ("bomba", "valvula") else nid

    for p in pipes:
        p["a"], p["b"] = no_epanet(p["a"], "J"), no_epanet(p["b"], "M")

    # conectividade: todo nó precisa alcançar uma fonte (captação ou reservatório)
    viz = defaultdict(set)
    for nid in nos:
        for t in chegam[nid] + saem[nid]:
            viz[nid].add(t)
    por_trecho = defaultdict(set)
    for nid, ts in viz.items():
        for t in ts:
            por_trecho[t].add(nid)
    fontes = [n for n, (cam, _, _) in nos.items() if cam in ("captacao", "reservatorio")]
    if not fontes:
        rel.erro("a rede não tem captação nem reservatório (nenhuma fonte de água)")
    visto, pilha = set(fontes), list(fontes)
    while pilha:
        n = pilha.pop()
        for t in viz[n]:
            for m in por_trecho[t] - visto:
                visto.add(m)
                pilha.append(m)
    for nid in ligados - visto:
        rel.erro(f"{nos[nid][0]} {nid}: sem ligação com nenhuma fonte (rede desconexa)", ref=(nos[nid][0], nid))

    # mesma busca respeitando trechos e válvulas FECHADOS: o que fica isolado pela operação.
    # Com PDA o EPANET resolve o nó isolado (recebe zero): é uma manobra, vira aviso.
    pda = dict(zip(c["opcoes_simulacao"]["chave"], c["opcoes_simulacao"]["valor"])) \
        .get("modelo_demanda", "PDA").upper() == "PDA"
    fechados = {p["id"] for p in pipes if p["st"] == "Closed"}
    bloqueia = {n for n, (cam, r, _) in nos.items() if cam == "valvula" and r["status"] == "FECHADA"}
    alcanca, pilha = set(fontes), list(fontes)
    while pilha:
        n = pilha.pop()
        if n in bloqueia:
            continue
        for t in viz[n] - fechados:
            for m in por_trecho[t] - alcanca:
                alcanca.add(m)
                pilha.append(m)
    for nid in sorted((visto & ligados) - alcanca):
        cam, r, _ = nos[nid]
        if cam == "no_juncao" and (r["demanda_base"] or 0) > 0:
            (rel.aviso if pda else rel.erro)(
                f"nó {nid}: fica SEM ABASTECIMENTO - trechos/válvulas fechados isolam este ponto "
                f"de consumo de qualquer fonte", ref=(cam, nid))
        else:
            rel.aviso(f"{cam} {nid}: fica isolado pelos trechos/válvulas fechados", ref=(cam, nid))

    # ---------------------------------------------------- tabelas do modelo
    # tabela curva: tipo BOMBA = altura × vazão; POTENCIA = bomba de potência constante (y = kW);
    # RENDIMENTO = rendimento (%) × vazão da mesma definição de bomba (1 ponto em vazão 0 = constante;
    # 1 ponto com vazão = ponto de melhor rendimento; vários = curva)
    curvas, potencia, rend, gpv = defaultdict(list), {}, defaultdict(list), defaultdict(list)
    for _, r in c["curva"].iterrows():
        tipo = str(r.get("tipo") or "BOMBA").upper()
        if tipo == "POTENCIA":
            potencia[r["id_curva"]] = float(r["y"])
        elif tipo == "RENDIMENTO":
            rend[r["id_curva"]].append((float(r["x"]), float(r["y"])))
        elif tipo == "GPV":  # curva perda de carga × vazão de uma válvula GPV (id_curva = código da válvula)
            gpv[r["id_curva"]].append((float(r["x"]), float(r["y"])))
        elif tipo in ("BOMBA", "PUMP", "NONE", "NULL", ""):
            curvas[r["id_curva"]].append((r["x"], r["y"]))
    curvas = {k: sorted(v) for k, v in curvas.items()}  # o EPANET exige vazão crescente
    energia = []
    padroes = defaultdict(list)
    for _, r in c["padrao_consumo"].sort_values("passo").iterrows():
        padroes[r["id_padrao"]].append(r["multiplicador"])
    opc = dict(zip(c["opcoes_simulacao"]["chave"], c["opcoes_simulacao"]["valor"]))
    # padrões definidos como no WaterGEMS (em degraus ou contínuo, com multiplicador inicial): os passos do
    # EPANET saem da definição, no passo dos padrões das opções
    if "padrao_def" in c and len(c["padrao_def"]):
        defs = defaultdict(list)
        for _, r in c["padrao_def"].iterrows():
            if not _vazio(r["hora"]) and not _vazio(r["multiplicador"]):
                defs[r["id_padrao"]].append((r["formato"] or "DEGRAUS", float(r["hora"]), float(r["multiplicador"])))
        passo_p = float(str(opc.get("passo_padrao_min", 15)).replace(",", "."))
        for pid, linhas in defs.items():
            padroes[pid] = passos_padrao(linhas[0][0], [(h, m) for _, h, m in linhas], passo_p)

    # várias demandas por nó (Demand Collection do WaterGEMS): tabela "demanda" (no_id, demanda, padrao, categoria).
    # A demanda_base do nó é o total: as linhas dizem como ele se divide e o padrão de cada parte. Se o total mudou
    # por fora (cenário, calibração, LoadBuilder), as partes acompanham na mesma proporção.
    colecao = defaultdict(list)
    if "demanda" in c:
        for _, r in c["demanda"].iterrows():
            if not _vazio(r["no_id"]) and not _vazio(r["demanda"]):
                colecao[str(r["no_id"])].append((float(r["demanda"]), r["padrao"] or "", r.get("categoria") or ""))
    demandas = []
    extras = consumidores(c, ativos, nos, ligados, pipes, trechos, rel)

    juncs, reserv, tanques, bombas, valvulas, status, coords = [], [], [], [], [], [], []
    usados = set()
    for nid, (camada, r, (x, y)) in nos.items():
        if nid not in ligados:
            continue
        if camada == "no_juncao":
            if _vazio(r["cota"]):
                rel.erro(f"nó {nid}: sem cota", ref=("no_juncao", nid))
            pad = r["padrao"] or ""
            if pad and pad not in padroes:
                rel.erro(f"nó {nid}: padrão de consumo '{pad}' não existe", ref=("no_juncao", nid))
            usados.add(pad)
            partes = colecao.get(nid)
            soma = sum(q for q, _, _ in partes) if partes else 0
            dos_consumidores = [(q, p or pad, cat) for q, p, cat in extras.get(nid, [])]
            if (partes and soma > 0) or dos_consumidores:
                if partes and soma > 0:
                    k = (r["demanda_base"] if not _vazio(r["demanda_base"]) else soma) / soma
                    proprias = [(q * k, p, cat) for q, p, cat in partes]
                else:
                    proprias = [(r["demanda_base"], pad, "")] if (r["demanda_base"] or 0) > 0 else []
                for q, p, cat in proprias + dos_consumidores:
                    if p and p not in padroes:
                        rel.erro(f"nó {nid}: padrão '{p}' da demanda {cat or ''} não existe", ref=("no_juncao", nid))
                    usados.add(p)
                    demandas.append(f"{nid:<14} {q:<10g} {p:<12} ;{cat}")
                juncs.append(f"{nid:<14} {r['cota'] or 0:<9g} 0")
            else:
                juncs.append(f"{nid:<14} {r['cota'] or 0:<9g} {r['demanda_base'] or 0:<10g} {pad}")
            coords.append((nid, x, y))
        elif camada == "captacao":
            cota_t = r.get("cota")
            if not _vazio(cota_t) and not _vazio(r["carga_hidraulica"]) and r["carga_hidraulica"] < cota_t - 0.5:
                rel.erro(f"captação {nid}: carga hidráulica {r['carga_hidraulica']:g} m está ABAIXO do terreno "
                         f"({cota_t:g} m). A carga é o nível da água em cota absoluta (ex.: terreno {cota_t:g} m + "
                         f"lâmina 2 m = {cota_t + 2:g} m), não a altura da água", ref=("captacao", nid))
            reserv.append(f"{nid:<14} {r['carga_hidraulica']:<9g} {r['padrao_carga'] or ''}")
            coords.append((nid, x, y))
        elif camada == "reservatorio":
            for campo in ("cota_fundo", "nivel_ini", "nivel_max", "diametro"):
                if _vazio(r[campo]):
                    rel.erro(f"reservatório {nid}: campo {campo} vazio", ref=("reservatorio", nid))
            if not _vazio(r["cota_fundo"]) and not _vazio(r["nivel_max"]) and r["cota_fundo"] > 20 \
                    and r["nivel_max"] > 0.5 * r["cota_fundo"]:
                rel.erro(f"reservatório {nid}: os níveis ({r['nivel_ini']:g} / {r['nivel_min'] or 0:g} / "
                         f"{r['nivel_max']:g} m) parecem COTAS. Os níveis são a lâmina d'água acima do fundo: com "
                         f"fundo em {r['cota_fundo']:g} m e nível máximo na cota {r['nivel_max']:g} m, o nível "
                         f"máximo é {r['nivel_max'] - r['cota_fundo']:.2f} m", ref=("reservatorio", nid))
            tanques.append(f"{nid:<14} {r['cota_fundo']:<9g} {r['nivel_ini']:<8g} {r['nivel_min'] or 0:<8g} "
                           f"{r['nivel_max']:<8g} {r['diametro']:<8g} 0")
            coords.append((nid, x, y))
        else:  # bomba / válvula: dois nós internos na cota do ponto
            if _vazio(r["cota"]):
                rel.erro(f"{camada} {nid}: sem cota", ref=(camada, nid))
            for lado in ("M", "J"):
                juncs.append(f"{nid + '__' + lado:<14} {r['cota'] or 0:<9g} 0")
                coords.append((f"{nid}__{lado}", x, y))
            if camada == "bomba":
                if r["curva"] in potencia:
                    if potencia[r["curva"]] <= 0:
                        rel.erro(f"bomba {nid}: a potência da definição {r['curva']} tem que ser maior que zero",
                                 ref=("bomba", nid))
                elif r["curva"] not in curvas:
                    rel.erro(f"bomba {nid}: curva '{r['curva']}' não existe na tabela de curvas"
                             if not _vazio(r["curva"]) else f"bomba {nid}: escolha a curva da bomba "
                             "(Curvas de bomba, no menu GWATER)", ref=("bomba", nid))
                else:
                    pts = curvas[r["curva"]]
                    qs = [q for q, _ in pts]
                    if len(pts) == 2:
                        rel.erro(f"curva {r['curva']} (bomba {nid}): o EPANET não aceita 2 pontos; use 1, 3 ou mais",
                                 ref=("bomba", nid))
                    elif any(b <= a for a, b in zip(qs, qs[1:])):
                        rel.erro(f"curva {r['curva']} (bomba {nid}): as vazões têm que crescer ponto a ponto",
                                 ref=("bomba", nid))
                vel = r["rotacao_relativa"] if not _vazio(r["rotacao_relativa"]) else 1
                if r["curva"] in potencia:
                    bombas.append(f"{nid:<10} {nid}__M  {nid}__J  POWER {potencia[r['curva']]:g}  SPEED {vel:g}")
                else:
                    bombas.append(f"{nid:<10} {nid}__M  {nid}__J  HEAD {r['curva']}  SPEED {vel:g}")
                if rend.get(r["curva"]):
                    energia.append(f"Pump {nid:<10} Efficiency {r['curva']}__EF")
                if r["status_inicial"] == "FECHADA":
                    status.append(f"{nid:<10} Closed")
            else:
                if r["tipo"] == "REGISTRO":  # registro de manobra: TCV sem perda (aberto) ou fechado pelo status
                    dns = [p["D"] for p in pipes if p["a"] == f"{nid}__J" or p["b"] == f"{nid}__M"]
                    r = r.copy()
                    r["tipo"] = "TCV"
                    r["ajuste"] = 0 if _vazio(r["ajuste"]) else r["ajuste"]
                    if _vazio(r["diametro"]) and dns:
                        r["diametro"] = max(dns)
                if r["tipo"] == "GPV":  # GPV: o "ajuste" é a curva perda × vazão (Valve Characteristics)
                    if not gpv.get(nid):
                        rel.erro(f"válvula {nid} (GPV): falta a curva perda de carga × vazão (Componentes > "
                                 "Curvas de válvula)", ref=("valvula", nid))
                        continue
                    if _vazio(r["diametro"]):
                        rel.erro(f"válvula {nid}: tipo e diâmetro são obrigatórios", ref=("valvula", nid))
                        continue
                    curvas[f"{nid}__GPV"] = sorted(gpv[nid])
                    valvulas.append(f"{nid:<10} {nid}__M  {nid}__J  {r['diametro']:<6g} GPV  {nid}__GPV  "
                                    f"{r['perda_localizada'] or 0:g}")
                    if r["status"] in STATUS_LINK:
                        status.append(f"{nid:<10} {STATUS_LINK[r['status']]}")
                    continue
                if r["tipo"] == "TCV":  # TCV é aberta (sem perda) ou fechada: não tem ajuste
                    r = r.copy()
                    r["ajuste"] = 0
                    r["status"] = "FECHADA" if r["status"] == "FECHADA" else "ABERTA"
                elif r["status"] in ("INATIVA", "ABERTA", "FECHADA") and _vazio(r["ajuste"]):
                    r = r.copy()  # fora de regulação o ajuste não é usado
                    r["ajuste"] = 0
                if _vazio(r["diametro"]) or _vazio(r["tipo"]):
                    rel.erro(f"válvula {nid}: tipo e diâmetro são obrigatórios", ref=("valvula", nid))
                    continue
                if _vazio(r["ajuste"]):
                    rel.erro(f"válvula {nid} ({r['tipo']}): falta o ajuste (pressão ou vazão que ela regula). Para "
                             "deixá-la 100% aberta, use o status INATIVA", ref=("valvula", nid))
                    continue
                if r["tipo"] in ("PRV", "PSV") and r["ajuste"] < 5 and r.get("status") == "ATIVA":
                    rel.aviso(f"válvula {nid} ({r['tipo']}): ajuste de {r['ajuste']:g} mca é muito baixo. O ajuste é "
                              f"a pressão que a válvula mantém (redutora: na saída; normalmente 15 a 30 mca)",
                              ref=("valvula", nid))
                valvulas.append(f"{nid:<10} {nid}__M  {nid}__J  {r['diametro']:<6g} {r['tipo']:<4} "
                                f"{r['ajuste']:<8g} {r['perda_localizada'] or 0:g}")
                if r["status"] in STATUS_LINK:
                    status.append(f"{nid:<10} {STATUS_LINK[r['status']]}")

    controles = []
    for _, r in c["controle"].iterrows():
        acao = str(r["acao"] or "").strip().upper()
        if acao.startswith("AJUSTE"):  # novo ajuste da válvula ou rotação relativa da bomba
            try:
                acao = f"{float(acao.replace('AJUSTE', '').replace(',', '.').strip()):g}"
            except ValueError:
                rel.erro(f"controle de {r['elemento']}: ação '{r['acao']}' sem valor (use AJUSTE e o número)")
                continue
        else:
            acao = STATUS_LINK.get(acao, acao).upper()
        if r["condicao"] == "HORA":
            controles.append(f"LINK {r['elemento']} {acao} AT CLOCKTIME {r['valor']:g}")
        elif r["condicao"] == "TEMPO":
            controles.append(f"LINK {r['elemento']} {acao} AT TIME {r['valor']:g}")
        elif r["condicao"] in CONDICAO:
            controles.append(f"LINK {r['elemento']} {acao} IF NODE {r['no_ref']} {CONDICAO[r['condicao']]} {r['valor']:g}")
        else:
            rel.erro(f"controle de {r['elemento']}: condição '{r['condicao']}' desconhecida")
        if r["elemento"] not in nos:
            rel.erro(f"controle: elemento '{r['elemento']}' não existe")

    regras = regras_epanet(c.get("regra"), nos, {p["id"] for p in pipes}, rel)

    if not rel.ok:
        return "", rel

    passo = int(opc.get("passo_hidraulico_min", 15))
    sec = lambda titulo, linhas: f"[{titulo}]\n" + "\n".join(linhas) + "\n\n"
    inp = "[TITLE]\nGWATER - gerado a partir do cadastro " + os.path.basename(gpkg) + "\n\n"
    inp += sec("JUNCTIONS", [";ID            Elev      Demand     Pattern"] + juncs)
    inp += sec("RESERVOIRS", reserv)
    inp += sec("TANKS", tanques)
    inp += sec("PIPES", [f"{p['id']:<14} {p['a']:<12} {p['b']:<12} {p['L']:<9.2f} {p['D']:<6g} "
                         f"{p['C']:<6g} {p['km']:<4g} {p['st']}" for p in pipes])
    inp += sec("DEMANDS", demandas)
    inp += sec("PUMPS", bombas)
    inp += sec("VALVES", valvulas)
    inp += sec("STATUS", status)
    for cid, pts in rend.items():  # curva de rendimento de cada definição usada
        if not any(e.endswith(f" {cid}__EF") for e in energia):
            continue
        curvas[f"{cid}__EF"] = curva_rendimento(pts)
    inp += sec("CURVES", [f"{cid:<12} {x:<8g} {y:g}" for cid, pts in curvas.items() for x, y in pts])
    inp += sec("ENERGY", energia)
    inp += sec("PATTERNS", [f"{pid:<12} " + " ".join(f"{m:g}" for m in ms[i:i + 8])
                            for pid, ms in padroes.items() for i in range(0, len(ms), 8)])
    inp += sec("CONTROLS", controles)
    inp += sec("RULES", regras)
    def hm(minutos):  # minutos → h:mm do EPANET
        m = int(round(float(minutos)))
        return f"{m // 60}:{m % 60:02d}"

    def num(chave, padrao):
        try:
            return float(str(opc.get(chave, padrao)).replace(",", "."))
        except ValueError:
            return float(padrao)
    permanente = str(opc.get("tipo_analise", "EPS")).upper() == "PERMANENTE"  # Steady State do WaterGEMS
    duracao = 0 if permanente else num("duracao_h", 24) * 60
    rel_passo = num("passo_relatorio_min", passo)
    inp += sec("TIMES", [f"Duration {hm(duracao)}", f"Hydraulic Timestep {hm(passo)}",
                         f"Quality Timestep {hm(min(5, passo))}",
                         f"Pattern Timestep {hm(num('passo_padrao_min', 15))}",
                         f"Pattern Start {hm(num('inicio_h', 0) * 60)}",
                         f"Report Timestep {hm(rel_passo)}", "Report Start 0:00",
                         f"Start ClockTime {hm(num('inicio_h', 0) * 60)}"])
    # PDA (demanda dependente da pressão, EPANET 2.2): abaixo da pressão requerida o nó recebe menos
    # água, em vez de o cálculo falhar. As linhas de PDA precisam vir depois de Units/Headloss.
    nao_conv = str(opc.get("se_nao_convergir", "CONTINUAR")).upper()
    opcoes = [f"Units {opc.get('unidades', 'LPS')}", f"Headloss {opc.get('perda_carga', 'H-W')}",
              f"Trials {int(num('tentativas', 100))}", f"Accuracy {num('precisao', 0.001):g}",
              f"Unbalanced {'Stop' if nao_conv == 'PARAR' else 'Continue 10'}",
              f"Demand Multiplier {num('multiplicador_demanda', 1):g}",
              f"Viscosity {num('viscosidade_relativa', 1):g}", f"Specific Gravity {num('densidade_relativa', 1):g}",
              f"Emitter Exponent {num('expoente_emissor', 0.5):g}"]
    if pda:
        opcoes += ["Demand Model PDA", f"Minimum Pressure {opc.get('pressao_minima', '0')}",
                   f"Required Pressure {opc.get('pressao_requerida', '10')}",
                   f"Pressure Exponent {num('expoente_pressao', 0.5):g}"]
    inp += sec("OPTIONS", opcoes)
    inp += sec("COORDINATES", [f"{n:<14} {x:.3f} {y:.3f}" for n, x, y in coords])
    inp += sec("VERTICES", [f"{p['id']:<14} {x:.3f} {y:.3f}" for p in pipes for x, y in p["vert"]])
    return inp + "[END]\n", rel


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    gpkg = args[0] if args else GPKG_PADRAO
    saida = args[1] if len(args) > 1 else os.path.join(RAIZ, "modelo", "cadastro.inp")
    inp, rel = converter(gpkg, com_projetados="--com-projetados" in sys.argv)
    print(rel.texto())
    if not rel.ok:
        sys.exit(f"\n{len(rel.erros)} erro(s): corrija o cadastro e rode de novo.")
    with open(saida, "w", encoding="utf-8") as f:
        f.write(inp)
    print("\nModelo EPANET gravado em", saida)
