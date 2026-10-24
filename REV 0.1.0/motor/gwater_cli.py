"""Ponte entre o QGIS e o motor: valida e simula um cadastro, gravando o resultado em JSON.

Uso:
  python gwater_cli.py validar <cadastro.gpkg> <saida.json> [--com-projetados]
  python gwater_cli.py simular <cadastro.gpkg> <saida.json> [--com-projetados]

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
    from simular import rodar
    out, inp = validar(gpkg, com_projetados, alteracoes)
    if not out["ok"]:
        return out
    arq_inp = os.path.splitext(gpkg)[0] + (f"_{nome_inp}" if nome_inp else "") + ".inp"
    with open(arq_inp, "w", encoding="utf-8") as f:
        f.write(inp)
    try:
        res, dt = rodar(inp)
    except Exception as e:  # o EPANET não fecha a solução: devolve como erro da rede, não do programa
        out["ok"] = False
        out["itens"].insert(0, {"nivel": "ERRO", "camada": None, "id": None,
                                "msg": f"o EPANET não conseguiu resolver a rede ({type(e).__name__}). "
                                       f"Verifique trechos fechados, bombas e válvulas: {e}"[:400]})
        return out
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


if __name__ == "__main__":
    acao, gpkg, saida = sys.argv[1:4]
    com_proj = "--com-projetados" in sys.argv
    try:
        out = validar(gpkg, com_proj)[0] if acao == "validar" else simular(gpkg, com_proj)
    except Exception as e:  # qualquer falha do motor volta legível para o QGIS
        out = {"ok": False, "itens": [{"nivel": "ERRO", "msg": f"falha no motor: {e}", "camada": None, "id": None}],
               "traceback": traceback.format_exc()}
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print("ok" if out.get("ok") else "com erros")
