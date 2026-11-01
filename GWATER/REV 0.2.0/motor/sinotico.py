"""Sinótico automático: o esquema do sistema montado a partir do cadastro aberto.

Em vez de um desenho fixo, o sinótico sai da topologia da rede, como num SCADA:
  - equipamentos viram blocos: captação, bomba, reservatório e válvula;
  - as tubulações e nós entre equipamentos viram "redes" (áreas de consumo). Um trecho de
    ligação sem consumo entre só dois equipamentos vira uma linha direta; com três ou mais
    equipamentos, vira um ponto de derivação;
  - com o campo setor preenchido, o setor manda: todos os nós do mesmo setor viram um bloco só
    (mesmo em pedaços separados da rede), uma rede com dois setores vira dois blocos, e as tubulações
    entre setores viram a ligação entre os blocos. Nó sem setor fica com o setor do vizinho mais perto;
  - as colunas seguem o caminho da água, a partir das captações (ou dos reservatórios);
  - a válvula de setor (VSE) não aparece: o sinótico passa direto por ela, como se o tubo fosse contínuo.
    A de reservatório (VRE) e as outras viram blocos.
Cada bloco diz quais resultados do EPANET são dele (nós, ligações e sentido dos tubos), e a
tela (painel/sinotico.html) só precisa ler a simulação de /api/simular-rede.

Uso:  python sinotico.py [cadastro.gpkg]
"""
from collections import defaultdict, deque

from cadastro_para_inp import GPKG_PADRAO, ler_cadastro

EQUIP = ["captacao", "bomba", "reservatorio", "valvula"]
OCULTAS = {"VSE"}  # válvulas que o sinótico atravessa
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
    tubos = _atravessar(tubos, {k for k, (cam, r) in elem.items()
                                if cam == "valvula" and str(r.get("tipo") or "").upper() in OCULTAS})
    for k in [k for k, (cam, r) in elem.items() if cam == "valvula" and str(r.get("tipo") or "").upper() in OCULTAS]:
        del elem[k]

    # ---- redes: componentes de nós comuns ligados por tubos (equipamentos cortam a rede)
    eh_eq = lambda nid: elem[nid][0] in EQUIP
    viz = defaultdict(list)
    for t in tubos:
        a, b = str(t["no_inicial"]), str(t["no_final"])
        # o tubo que atravessa uma válvula oculta continua separando a rede (vira a ligação entre os blocos)
        if not eh_eq(a) and not eh_eq(b) and not t.get("_oculta"):
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

    # ---- setores: o campo setor junta os nós do mesmo setor e separa setores diferentes da mesma rede
    def _setor(r):
        v = r.get("setor")
        return None if v is None or str(v).strip() in ("", "NULL", "None", "nan") else str(v).strip()
    grupo_de = {}  # nó -> chave do bloco: ("s", setor) ou ("c", índice da rede sem setor)
    for z, membros in enumerate(zonas):
        fila = deque()
        for m in membros:
            st = _setor(elem[m][1])
            if st:
                grupo_de[m] = ("s", st)
                fila.append(m)
        if not fila:
            for m in membros:
                grupo_de[m] = ("c", z)
            continue
        while fila:  # nós sem setor: o setor do vizinho mais perto (pelos tubos)
            x = fila.popleft()
            for y in viz[x]:
                if y not in grupo_de:
                    grupo_de[y] = grupo_de[x]
                    fila.append(y)
    grupos = defaultdict(list)
    for nid, (camada, _) in elem.items():
        if camada == "no_juncao":
            grupos[grupo_de[nid]].append(nid)

    # ---- arestas: equipamento <-> bloco (pelos tubos de fronteira), equipamento <-> equipamento e setor <-> setor
    fronteira = defaultdict(list)  # (equip, grupo) -> [(tubo, sinal: +1 = tubo vai do equip para a rede)]
    diretas = defaultdict(list)    # (equip_a, equip_b) ordenado -> [(tubo, sinal: +1 = de a para b)]
    entre = defaultdict(list)      # (grupo_a, grupo_b) ordenado -> [(tubo, sinal)]: tubos entre setores
    for t in tubos:
        a, b = str(t["no_inicial"]), str(t["no_final"])
        if eh_eq(a) and eh_eq(b):
            k = tuple(sorted((a, b)))
            diretas[k].append((str(t["id"]), 1 if a == k[0] else -1))
        elif eh_eq(a):
            fronteira[(a, grupo_de[b])].append((str(t["id"]), 1))
        elif eh_eq(b):
            fronteira[(b, grupo_de[a])].append((str(t["id"]), -1))
        elif grupo_de[a] != grupo_de[b]:
            k = tuple(sorted((grupo_de[a], grupo_de[b])))
            entre[k].append((str(t["id"]), 1 if grupo_de[a] == k[0] else -1))
    adj_grupo = defaultdict(set)
    for (e, g) in fronteira:
        adj_grupo[g].add(e)
    com_vizinho = {g for k in entre for g in k}
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

    # demanda dos consumidores (casas): vai para o nó ligado, ou metade para cada ponta da tubulação ligada
    extra = defaultdict(float)
    if "consumidor" in c:
        pontas = {str(t["id"]): (str(t["no_inicial"]), str(t["no_final"])) for t in tubos if not t.get("_oculta")}
        for r in c["consumidor"].to_dict("records"):
            q, alvo = _num(r.get("demanda_base")), str(r.get("ligado_a") or "")
            if not ativo(r) or q <= 0:
                continue
            if alvo in elem and elem[alvo][0] == "no_juncao":
                extra[alvo] += q
            elif alvo in pontas:
                nos_ = [n for n in pontas[alvo] if n in elem and elem[n][0] == "no_juncao"]
                for n in nos_:
                    extra[n] += q / len(nos_)
    zid_de = {g: (f"setor:{g[1]}" if g[0] == "s" else f"rede:{g[1]}") for g in grupos}
    for g, membros in sorted(grupos.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        eqs = sorted(adj_grupo[g])
        recs = [elem[m][1] for m in membros]
        dem = sum(_num(r.get("demanda_base")) + extra[m] for m, r in zip(membros, recs))
        consumo = [m for m, r in zip(membros, recs)
                   if _num(r.get("demanda_base")) + extra[m] > 0 or r.get("tipo") in CONSUMO]
        if g[0] == "c" and dem <= 0 and not consumo and len(eqs) == 2 and g not in com_vizinho:
            # ligação sem consumo entre dois equipamentos: vira linha direta
            a, b = eqs
            tubs = fronteira[(a, g)]
            arestas.append({"de": a, "para": b, "tubos": [[t, s] for t, s in tubs],
                            "dn": max(dn.get(t, 0) for t, _ in tubs + fronteira[(b, g)])})
            continue
        if not eqs and not consumo and g not in com_vizinho:
            continue  # pedaço solto, sem nada para mostrar
        zid = zid_de[g]
        if g[0] == "s":  # setor: sempre um bloco com o nome dele
            tipo, rot = "zona", f"Setor {g[1]}"
        else:
            tipo = "zona" if consumo or dem > 0 else "derivacao"
            rot = "Rede" if tipo == "zona" else "Derivação"
        blocos[zid] = {"id": zid, "tipo": tipo, "rotulo": rot, "nos": membros,
                       "consumo": consumo or membros, "n_nos": len(membros), "demanda_base": round(dem, 3)}
        for e in eqs:
            tubs = fronteira[(e, g)]
            arestas.append({"de": e, "para": zid, "tubos": [[t, s] for t, s in tubs],
                            "dn": max(dn.get(t, 0) for t, _ in tubs)})
    for (ga, gb), tubs in entre.items():  # tubulações que ligam um setor a outro
        if zid_de[ga] in blocos and zid_de[gb] in blocos:
            arestas.append({"de": zid_de[ga], "para": zid_de[gb], "tubos": [[t, s] for t, s in tubs],
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


def _atravessar(tubos, ocultas):
    """Tira do caminho cada válvula oculta: os dois tubos dela viram um só, com o id e o sentido do primeiro (a
    vazão é a mesma). Uma de cada vez, para valerem também válvulas ocultas seguidas. Válvula oculta com outro
    número de tubos some com eles."""
    tubos = list(tubos)
    for v in ocultas:
        dela = [t for t in tubos if v in (str(t["no_inicial"]), str(t["no_final"]))]
        tubos = [t for t in tubos if v not in (str(t["no_inicial"]), str(t["no_final"]))]
        if len(dela) != 2:
            continue
        t1, t2 = dela
        o1 = str(t1["no_final"]) if str(t1["no_inicial"]) == v else str(t1["no_inicial"])
        o2 = str(t2["no_final"]) if str(t2["no_inicial"]) == v else str(t2["no_inicial"])
        a, b = (o1, o2) if str(t1["no_final"]) == v else (o2, o1)  # o sentido de t1 vale para o caminho todo
        tubos.append(dict(t1, no_inicial=a, no_final=b, _oculta=True, diametro_nominal=max(
            _num(t1.get("diametro_nominal")), _num(t2.get("diametro_nominal")))))
    return tubos


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
