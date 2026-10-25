"""Sinótico automático: o esquema do sistema montado a partir do cadastro aberto.

Em vez de um desenho fixo, o sinótico sai da topologia da rede, como num SCADA:
  - equipamentos viram blocos: captação, bomba, reservatório e válvula;
  - as tubulações e nós entre equipamentos viram "redes" (áreas de consumo). Um trecho de
    ligação sem consumo entre só dois equipamentos vira uma linha direta; com três ou mais
    equipamentos, vira um ponto de derivação;
  - as colunas seguem o caminho da água, a partir das captações (ou dos reservatórios).
Cada bloco diz quais resultados do EPANET são dele (nós, ligações e sentido dos tubos), e a
tela (painel/sinotico.html) só precisa ler a simulação de /api/simular-rede.

Uso:  python sinotico.py [cadastro.gpkg]
"""
from collections import defaultdict, deque

from cadastro_para_inp import GPKG_PADRAO, ler_cadastro

EQUIP = ["captacao", "bomba", "reservatorio", "valvula"]
CONSUMO = {"CONSUMO", "HIDRANTE", "PONTA"}


def _num(v, padrao=0.0):
    try:
        return float(v) if v is not None else padrao
    except (TypeError, ValueError):
        return padrao


def montar(gpkg=GPKG_PADRAO, com_projetados=False):
    c = ler_cadastro(gpkg)
    situacoes = {"EXISTENTE", "PROJETADO"} if com_projetados else {"EXISTENTE"}
    ativo = lambda r: r.get("situacao") in situacoes or r.get("situacao") is None

    elem = {}  # id -> (camada, registro)
    for camada in EQUIP + ["no_juncao"]:
        for r in c[camada].to_dict("records"):
            if ativo(r) and r.get("id"):
                elem[str(r["id"])] = (camada, r)
    tubos = [r for r in c["trecho"].to_dict("records")
             if ativo(r) and str(r.get("no_inicial")) in elem and str(r.get("no_final")) in elem]

    # ---- redes: componentes de nós comuns ligados por tubos (equipamentos cortam a rede)
    eh_eq = lambda nid: elem[nid][0] in EQUIP
    viz = defaultdict(list)
    for t in tubos:
        a, b = str(t["no_inicial"]), str(t["no_final"])
        if not eh_eq(a) and not eh_eq(b):
            viz[a].append(b)
            viz[b].append(a)
    zona_de, zonas = {}, []
    for nid, (camada, _) in elem.items():
        if camada != "no_juncao" or nid in zona_de:
            continue
        membros, fila = [], deque([nid])
        zona_de[nid] = len(zonas)
        while fila:
            x = fila.popleft()
            membros.append(x)
            for y in viz[x]:
                if y not in zona_de:
                    zona_de[y] = len(zonas)
                    fila.append(y)
        zonas.append(membros)

    # ---- arestas: equipamento <-> rede (pelos tubos de fronteira) e equipamento <-> equipamento
    fronteira = defaultdict(list)  # (equip, zona) -> [(tubo, sinal: +1 = tubo vai do equip para a rede)]
    diretas = defaultdict(list)    # (equip_a, equip_b) ordenado -> [(tubo, sinal: +1 = de a para b)]
    for t in tubos:
        a, b = str(t["no_inicial"]), str(t["no_final"])
        if eh_eq(a) and eh_eq(b):
            k = tuple(sorted((a, b)))
            diretas[k].append((str(t["id"]), 1 if a == k[0] else -1))
        elif eh_eq(a):
            fronteira[(a, zona_de[b])].append((str(t["id"]), 1))
        elif eh_eq(b):
            fronteira[(b, zona_de[a])].append((str(t["id"]), -1))
    adj_zona = defaultdict(set)
    for (e, z) in fronteira:
        adj_zona[z].add(e)

    dn = {str(t["id"]): _num(t.get("diametro_nominal")) for t in tubos}
    blocos, arestas = {}, []
    for nid, (camada, r) in elem.items():
        if camada not in EQUIP:
            continue
        b = {"id": nid, "tipo": camada, "rotulo": r.get("nome") or nid}
        if camada == "reservatorio":
            b.update(nivel_max=_num(r.get("nivel_max"), 1), nivel_min=_num(r.get("nivel_min")),
                     volume_util=_num(r.get("volume_util")), diametro=_num(r.get("diametro")))
        elif camada == "valvula":
            b.update(tipo_valvula=r.get("tipo") or "", ajuste=_num(r.get("ajuste")))
        elif camada == "bomba":
            b.update(curva=r.get("curva") or "")
        elif camada == "captacao":
            b.update(carga=_num(r.get("carga_hidraulica")))
        blocos[nid] = b

    for z, membros in enumerate(zonas):
        eqs = sorted(adj_zona[z])
        recs = [elem[m][1] for m in membros]
        dem = sum(_num(r.get("demanda_base")) for r in recs)
        consumo = [m for m, r in zip(membros, recs) if _num(r.get("demanda_base")) > 0 or r.get("tipo") in CONSUMO]
        if dem <= 0 and not consumo and len(eqs) == 2:
            # ligação sem consumo entre dois equipamentos: vira linha direta
            a, b = eqs
            tubs = fronteira[(a, z)]
            arestas.append({"de": a, "para": b, "tubos": [[t, s] for t, s in tubs],
                            "dn": max(dn.get(t, 0) for t, _ in tubs + fronteira[(b, z)])})
            continue
        if not eqs and not consumo:
            continue  # pedaço solto, sem nada para mostrar
        zid = f"rede:{z}"
        setores = sorted({str(r.get("setor")) for r in recs if r.get("setor")})
        tipo = "zona" if consumo or dem > 0 else "derivacao"
        rot = (f"Setor {setores[0]}" if len(setores) == 1 else "Rede") if tipo == "zona" else "Derivação"
        blocos[zid] = {"id": zid, "tipo": tipo, "rotulo": rot, "nos": membros,
                       "consumo": consumo or membros, "n_nos": len(membros), "demanda_base": round(dem, 3)}
        for e in eqs:
            tubs = fronteira[(e, z)]
            arestas.append({"de": e, "para": zid, "tubos": [[t, s] for t, s in tubs],
                            "dn": max(dn.get(t, 0) for t, _ in tubs)})
    for (a, b), tubs in diretas.items():
        arestas.append({"de": a, "para": b, "tubos": [[t, s] for t, s in tubs], "dn": max(dn.get(t, 0) for t, _ in tubs)})
    # redes sem equipamento nenhum (consumo isolado) ainda aparecem, sem ligação
    nomes = defaultdict(int)
    for b in blocos.values():
        if b["tipo"] in ("zona", "derivacao"):
            nomes[b["rotulo"]] += 1
    cont = defaultdict(int)
    for b in sorted(blocos.values(), key=lambda b: b["id"]):
        if b["tipo"] in ("zona", "derivacao") and nomes[b["rotulo"]] > 1:
            cont[b["rotulo"]] += 1
            b["rotulo"] = f"{b['rotulo']} {cont[b['rotulo']]}"

    _posicionar(blocos, arestas)
    return {"blocos": list(blocos.values()), "arestas": arestas,
            "colunas": 1 + max((b["col"] for b in blocos.values()), default=0),
            "linhas": 1 + max((b["lin"] for b in blocos.values()), default=0)}


def _posicionar(blocos, arestas):
    """Colunas pelo caminho da água (BFS a partir das fontes); linhas sem cruzar, pela média dos vizinhos."""
    viz = defaultdict(set)
    for a in arestas:
        viz[a["de"]].add(a["para"])
        viz[a["para"]].add(a["de"])
    fontes = [b for b, x in blocos.items() if x["tipo"] == "captacao"] or \
             [b for b, x in blocos.items() if x["tipo"] == "reservatorio"] or sorted(blocos)[:1]
    col = {}
    pendentes = sorted(blocos)
    while pendentes:
        inicio = [f for f in fontes if f not in col] or [pendentes[0]]
        fila = deque(inicio)
        base = 0
        for f in inicio:
            col[f] = base
        while fila:
            x = fila.popleft()
            for y in sorted(viz[x]):
                if y not in col:
                    col[y] = col[x] + 1
                    fila.append(y)
        pendentes = [b for b in pendentes if b not in col]
        fontes = []
    # cada aresta passa a ir "da coluna menor para a maior"; sinal dos tubos: +1 = sentido do tubo é de -> para
    # (vazão da aresta = soma de sinal × vazão do tubo; positiva = água indo de -> para)
    for a in arestas:
        if col[a["de"]] > col[a["para"]]:
            a["de"], a["para"] = a["para"], a["de"]
            a["tubos"] = [[t, -s] for t, s in a["tubos"]]
    por_col = defaultdict(list)
    for b, c in col.items():
        por_col[c].append(b)
    lin = {}
    for c in sorted(por_col):
        def chave(b):
            ant = [lin[v] for v in viz[b] if v in lin and col[v] < c]
            return (sum(ant) / len(ant) if ant else 0, b)
        for i, b in enumerate(sorted(por_col[c], key=chave)):
            lin[b] = i
    for b, x in blocos.items():
        x["col"], x["lin"] = col[b], lin[b]


if __name__ == "__main__":
    import json
    import sys
    s = montar(sys.argv[1] if len(sys.argv) > 1 else GPKG_PADRAO)
    for b in sorted(s["blocos"], key=lambda b: (b["col"], b["lin"])):
        print(f"  col {b['col']} lin {b['lin']}  {b['tipo']:<12} {b['rotulo']:<16} "
              f"{('nós: ' + str(b['n_nos']) + '  demanda: ' + str(b['demanda_base'])) if 'n_nos' in b else ''}")
    for a in s["arestas"]:
        print(f"  {a['de']:>10} -> {a['para']:<10} tubos {a["tubos"]}")
    print(json.dumps(s)[:120], "...")
