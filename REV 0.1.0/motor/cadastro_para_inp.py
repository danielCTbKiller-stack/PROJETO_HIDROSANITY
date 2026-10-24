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
STATUS_LINK = {"ABERTA": "Open", "FECHADA": "Closed"}
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
    curvas = defaultdict(list)
    for _, r in c["curva"].iterrows():
        curvas[r["id_curva"]].append((r["x"], r["y"]))
    padroes = defaultdict(list)
    for _, r in c["padrao_consumo"].sort_values("passo").iterrows():
        padroes[r["id_padrao"]].append(r["multiplicador"])
    opc = dict(zip(c["opcoes_simulacao"]["chave"], c["opcoes_simulacao"]["valor"]))

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
            juncs.append(f"{nid:<14} {r['cota'] or 0:<9g} {r['demanda_base'] or 0:<10g} {pad}")
            coords.append((nid, x, y))
        elif camada == "captacao":
            reserv.append(f"{nid:<14} {r['carga_hidraulica']:<9g} {r['padrao_carga'] or ''}")
            coords.append((nid, x, y))
        elif camada == "reservatorio":
            for campo in ("cota_fundo", "nivel_ini", "nivel_max", "diametro"):
                if _vazio(r[campo]):
                    rel.erro(f"reservatório {nid}: campo {campo} vazio", ref=("reservatorio", nid))
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
                if r["curva"] not in curvas:
                    rel.erro(f"bomba {nid}: curva '{r['curva']}' não existe na tabela de curvas", ref=("bomba", nid))
                vel = r["rotacao_relativa"] if not _vazio(r["rotacao_relativa"]) else 1
                bombas.append(f"{nid:<10} {nid}__M  {nid}__J  HEAD {r['curva']}  SPEED {vel:g}")
                if r["status_inicial"] == "FECHADA":
                    status.append(f"{nid:<10} Closed")
            else:
                if _vazio(r["diametro"]) or _vazio(r["ajuste"]) or _vazio(r["tipo"]):
                    rel.erro(f"válvula {nid}: tipo, diâmetro e ajuste são obrigatórios", ref=("valvula", nid))
                    continue
                valvulas.append(f"{nid:<10} {nid}__M  {nid}__J  {r['diametro']:<6g} {r['tipo']:<4} "
                                f"{r['ajuste']:<8g} {r['perda_localizada'] or 0:g}")
                if r["status"] in STATUS_LINK:
                    status.append(f"{nid:<10} {STATUS_LINK[r['status']]}")

    controles = []
    for _, r in c["controle"].iterrows():
        acao = STATUS_LINK.get(r["acao"], r["acao"]).upper()
        if r["condicao"] == "HORA":
            controles.append(f"LINK {r['elemento']} {acao} AT CLOCKTIME {r['valor']:g}")
        elif r["condicao"] in CONDICAO:
            controles.append(f"LINK {r['elemento']} {acao} IF NODE {r['no_ref']} {CONDICAO[r['condicao']]} {r['valor']:g}")
        else:
            rel.erro(f"controle de {r['elemento']}: condição '{r['condicao']}' desconhecida")
        if r["elemento"] not in nos:
            rel.erro(f"controle: elemento '{r['elemento']}' não existe")

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
    inp += sec("PUMPS", bombas)
    inp += sec("VALVES", valvulas)
    inp += sec("STATUS", status)
    inp += sec("CURVES", [f"{cid:<12} {x:<8g} {y:g}" for cid, pts in curvas.items() for x, y in pts])
    inp += sec("PATTERNS", [f"{pid:<12} " + " ".join(f"{m:g}" for m in ms[i:i + 8])
                            for pid, ms in padroes.items() for i in range(0, len(ms), 8)])
    inp += sec("CONTROLS", controles)
    inp += sec("TIMES", [f"Duration {opc.get('duracao_h', '24')}:00",
                         f"Hydraulic Timestep 0:{passo:02d}",
                         f"Pattern Timestep 0:{int(opc.get('passo_padrao_min', 15)):02d}",
                         f"Report Timestep 0:{passo:02d}", "Report Start 0:00"])
    # PDA (demanda dependente da pressão, EPANET 2.2): abaixo da pressão requerida o nó recebe menos
    # água, em vez de o cálculo falhar. As linhas de PDA precisam vir depois de Units/Headloss.
    opcoes = [f"Units {opc.get('unidades', 'LPS')}", f"Headloss {opc.get('perda_carga', 'H-W')}",
              "Trials 100", "Accuracy 0.001"]
    if pda:
        opcoes += ["Demand Model PDA", f"Minimum Pressure {opc.get('pressao_minima', '0')}",
                   f"Required Pressure {opc.get('pressao_requerida', '10')}", "Pressure Exponent 0.5"]
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
