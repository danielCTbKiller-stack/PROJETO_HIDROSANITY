"""Ponte entre o QGIS e o motor: cada botão do plugin chama uma ação daqui e lê o resultado em JSON.

Uso:
  python gwater_cli.py validar  <cadastro.gpkg> <saida.json> [--com-projetados]
  python gwater_cli.py simular  <cadastro.gpkg> <saida.json> [--com-projetados]
  python gwater_cli.py exportar <cadastro.gpkg> <saida.json> --inp=<modelo.inp> [--com-projetados]
  python gwater_cli.py novo     <destino.gpkg>  <saida.json> [--crs=EPSG:31983]
  python gwater_cli.py importar <config.json>   <saida.json>      (ver importar_shp.py)

O plugin do QGIS roda este script com o Python do projeto (.venv), que tem o WNTR.
A simulação também grava <cadastro>.inp ao lado do GeoPackage (abre no EPANET 2.2).
"""
import json
import os
import sys
import tempfile
import traceback


def validar(gpkg, com_projetados, alteracoes=None):
    from cadastro_para_inp import converter
    inp, rel = converter(gpkg, com_projetados, alteracoes)
    return {"ok": rel.ok, "itens": rel.itens()}, inp


def simular(gpkg, com_projetados, alteracoes=None, nome_inp=None):
    """nome_inp: sufixo do .inp gravado (a proposta não sobrescreve o modelo da rede atual)."""
    from simular import FalhaEpanet, rodar
    out, inp = validar(gpkg, com_projetados, alteracoes)
    if not out["ok"]:
        return out
    arq_inp = os.path.splitext(gpkg)[0] + (f"_{nome_inp}" if nome_inp else "") + ".inp"
    with open(arq_inp, "w", encoding="utf-8") as f:
        f.write(inp)
    avisos = []
    try:
        res, dt = rodar(inp, avisos)
    except FalhaEpanet as e:  # o EPANET não fecha a solução: devolve o motivo dele, ligado aos elementos
        out["ok"] = False
        itens = _itens_epanet(gpkg, e.avisos)
        if not any(i["nivel"] == "ERRO" for i in itens):
            itens.insert(0, {"nivel": "ERRO", "camada": None, "id": None, "msg": str(e)[:400]})
        out["itens"] = itens + out["itens"]
        return out
    out["itens"] += _itens_epanet(gpkg, avisos)
    n, l = res.node, res.link
    r2 = lambda s: [round(float(v), 3) for v in s]
    # demanda solicitada (base × padrão): com PDA a entregue pode ser menor -> % de atendimento
    import wntr
    with tempfile.NamedTemporaryFile("w", suffix=".inp", delete=False, encoding="utf-8") as f:
        f.write(inp)
    try:
        esperada = wntr.metrics.expected_demand(wntr.network.WaterNetworkModel(f.name))
    finally:
        os.remove(f.name)
    out.update({
        "inp": arq_inp,
        "tempo_calculo_s": round(dt, 3),
        "horas": [round(t / 3600, 4) for t in n["pressure"].index],
        # nós: pressão (mca), carga (m), demanda (L/s)
        "nos": {nid: {"p": r2(n["pressure"][nid]), "h": r2(n["head"][nid]), "d": r2(n["demand"][nid] * 1000),
                      **({"de": r2(esperada[nid].reindex(n["pressure"].index, method="ffill") * 1000)}
                         if nid in esperada and esperada[nid].abs().sum() > 0 else {})}
                for nid in n["pressure"].columns},
        # links: vazão (L/s), velocidade (m/s), status (0 fechado, 1 aberto, 2 ativo), perda (m/km)
        "links": {lid: {"q": r2(l["flowrate"][lid] * 1000), "v": r2(l["velocity"][lid]),
                        "s": [int(x) for x in l["status"][lid]], "hl": r2(l["headloss"][lid] * 1000)}
                  for lid in l["flowrate"].columns},
    })
    return out


def _itens_epanet(gpkg, avisos):
    """Avisos do relatório do EPANET viram itens da aba Problemas, ligados à camada do elemento."""
    import pyogrio
    camada_de = {}
    for camada in ("trecho", "captacao", "reservatorio", "bomba", "valvula", "no_juncao"):
        try:
            for i in pyogrio.read_dataframe(gpkg, layer=camada, columns=["id"], read_geometry=False)["id"]:
                camada_de[str(i)] = camada
        except Exception:
            pass
    nomes = {"bomba": "bomba", "valvula": "válvula", "trecho": "tubulação", "no_juncao": "nó",
             "reservatorio": "reservatório", "captacao": "captação"}
    itens = []
    for nivel, el, msg in avisos:
        cam = camada_de.get(str(el)) if el else None
        if cam and msg.startswith(str(el)):  # "{e}: fechou..." -> "válvula V-0009: fechou..."
            msg = f"{nomes[cam]} {msg}"
        itens.append({"nivel": nivel, "camada": cam, "id": el if cam else None, "msg": "EPANET: " + msg})
    return itens


def exportar(gpkg, com_projetados, arq_inp):
    """Valida e grava o .inp onde o usuário escolher (abre no EPANET 2.2 oficial)."""
    out, inp = validar(gpkg, com_projetados)
    if out["ok"]:
        with open(arq_inp, "w", encoding="utf-8") as f:
            f.write(inp)
        out["inp"] = arq_inp
    return out


def novo(destino, crs=None):
    from importar_shp import novo_cadastro
    gpkg, qgz = novo_cadastro(destino, crs)
    return {"ok": True, "itens": [], "gpkg": gpkg, "qgz": qgz}


def importar(arq_config):
    from importar_shp import gravar, importar as ler_shp
    with open(arq_config, encoding="utf-8") as f:
        cfg = json.load(f)
    trechos, nos, avisos = ler_shp(cfg)
    gpkg, qgz = gravar(trechos, nos, cfg.get("destino", "importado"), cfg.get("crs"))
    return {"ok": True, "gpkg": gpkg, "qgz": qgz, "n_trechos": len(trechos), "n_nos": len(nos),
            "itens": [{"nivel": "AVISO", "camada": None, "id": None, "msg": a} for a in avisos]}


def _opcao(nome):
    return next((a.split("=", 1)[1] for a in sys.argv if a.startswith(f"--{nome}=")), None)


if __name__ == "__main__":
    acao, alvo, saida = sys.argv[1:4]
    com_proj = "--com-projetados" in sys.argv
    try:
        if acao == "validar":
            out = validar(alvo, com_proj)[0]
        elif acao == "simular":
            out = simular(alvo, com_proj)
        elif acao == "exportar":
            out = exportar(alvo, com_proj, _opcao("inp"))
        elif acao == "novo":
            out = novo(alvo, _opcao("crs"))
        elif acao == "importar":
            out = importar(alvo)
        else:
            raise ValueError(f"ação desconhecida: {acao}")
    except SystemExit as e:  # importar_shp avisa problemas do shapefile com SystemExit(mensagem)
        out = {"ok": False, "itens": [{"nivel": "ERRO", "msg": str(e), "camada": None, "id": None}]}
    except Exception as e:  # qualquer falha do motor volta legível para o QGIS
        out = {"ok": False, "itens": [{"nivel": "ERRO", "msg": f"falha no motor: {e}", "camada": None, "id": None}],
               "traceback": traceback.format_exc()}
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("ok" if out.get("ok") else "com erros")
