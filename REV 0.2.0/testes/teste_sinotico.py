"""Teste do sinótico automático (motor/sinotico.py) com o cadastro de exemplo.

Confere se o esquema montado a partir do cadastro é o do sistema da tela original
(captação -> bomba -> R1 -> derivação -> VRPs -> setores) e se as vazões das ligações,
calculadas pelos tubos de fronteira, batem com as vazões dos equipamentos no EPANET.

Uso:  python teste_sinotico.py
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
import gwater_cli  # noqa: E402
import sinotico  # noqa: E402
from cadastro_para_inp import GPKG_PADRAO  # noqa: E402

falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


s = sinotico.montar(GPKG_PADRAO)
B = {b["id"]: b for b in s["blocos"]}
tipos = sorted(b["tipo"] for b in s["blocos"])
checar(tipos == ["bomba", "captacao", "derivacao", "reservatorio", "valvula", "valvula", "valvula", "zona", "zona"],
       f"blocos: {tipos}")
ligacoes = {(a["de"], a["para"]) for a in s["arestas"]}
for par in [("CAP", "B1"), ("B1", "R1"), ("VRP1", "VRP2")]:
    checar(par in ligacoes, f"ligação {par[0]} -> {par[1]}")
checar(B["CAP"]["col"] < B["B1"]["col"] < B["R1"]["col"] < B["VRP1"]["col"] < B["VRP2"]["col"],
       "colunas seguem o caminho da água: CAP, B1, R1, VRP1, VRP2")
zonas = {b["rotulo"]: b for b in s["blocos"] if b["tipo"] == "zona"}
checar(set(zonas) == {"Setor S1", "Setor S2"}, f"redes com nome do setor: {sorted(zonas)}")

d = gwater_cli.simular(GPKG_PADRAO, False)
checar(d["ok"], "simulação do exemplo")


def q_aresta(a, i):
    return sum(sinal * d["links"][t]["q"][i] for t, sinal in a["tubos"])


n = len(d["horas"])
pior = 0.0
for a in s["arestas"]:
    for eq in (a["de"], a["para"]):
        if B[eq]["tipo"] in ("bomba", "valvula"):
            # a vazão que passa no equipamento é a que chega/sai pela ligação
            pior = max(pior, max(abs(abs(q_aresta(a, i)) - abs(d["links"][eq]["q"][i])) for i in range(n)))
# tolerância: com VRP ativa o EPANET fecha o balanço só dentro da precisão de convergência (< 1%)
checar(pior < 0.1, f"vazão das ligações = vazão de bombas e válvulas no EPANET (diferença máx {pior:.3f} L/s)")
sai_r1 = [a for a in s["arestas"] if a["de"] == "R1"][0]
checar(all(q_aresta(sai_r1, i) >= -1e-6 for i in range(n)), "saída de R1 sempre no sentido do desenho (positiva)")
dem = sum(max(0, d["nos"][nid]["d"][40]) for z in zonas.values() for nid in z["nos"])
checar(abs(dem - q_aresta(sai_r1, 40)) < 0.05, f"10h: o que sai de R1 ({q_aresta(sai_r1, 40):.2f}) = consumo dos setores "
                                               f"({dem:.2f} L/s)")

print("\n== agrupamento pelo setor")
import pandas as pd  # noqa: E402
from cadastro_para_inp import ler_cadastro  # noqa: E402
c = ler_cadastro(GPKG_PADRAO)
orig = sinotico.ler_cadastro
sinotico.ler_cadastro = lambda _g: {k: v.copy() for k, v in c.items()}
# a derivação na saída de R1 marcada como S1: o mesmo setor em dois pedaços da rede vira um bloco só
c["no_juncao"].loc[c["no_juncao"]["id"] == "J_SAI", "setor"] = "S1"
s2 = sinotico.montar(GPKG_PADRAO)
s1 = [b for b in s2["blocos"] if b["rotulo"].startswith("Setor S1")]
checar(len(s1) == 1 and s1[0]["n_nos"] == 2, f"setor S1 em dois pedaços = 1 bloco com os 2 nós: {[(b['rotulo'], b.get('n_nos')) for b in s1]}")
lig = {(a["de"], a["para"]) for a in s2["arestas"]}
checar({"R1", "setor:S1"} in [set(x) for x in lig] and {"VRP2", "setor:S1"} in [set(x) for x in lig], f"R1 e VRP2 ligam no mesmo bloco S1: {sorted(lig)}")
# uma tubulação ligando S1 a S2: a rede vira uma só, mas cada setor continua no seu bloco, ligados entre si
c["no_juncao"].loc[c["no_juncao"]["id"] == "J_SAI", "setor"] = None
novo = c["trecho"].iloc[[0]].copy()
novo["id"], novo["no_inicial"], novo["no_final"] = "T_S1_S2", "S1", "S2"
c["trecho"] = pd.concat([c["trecho"], novo], ignore_index=True)
s3 = sinotico.montar(GPKG_PADRAO)
rot = sorted(b["rotulo"] for b in s3["blocos"] if b["tipo"] == "zona")
lig = {(a["de"], a["para"]) for a in s3["arestas"]}
checar(rot == ["Setor S1", "Setor S2"] and (("setor:S1", "setor:S2") in lig or ("setor:S2", "setor:S1") in lig),
       f"rede com dois setores = dois blocos ligados entre si: {rot}")
sinotico.ler_cadastro = orig

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
