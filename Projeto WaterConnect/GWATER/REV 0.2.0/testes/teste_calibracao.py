"""Teste da calibração: a "rede verdadeira" difere do cadastro; a calibração descobre a diferença?

1. simula a rede com tubos do S1 envelhecidos (C 95), consumo S1 x0,90 e S2 x1,15;
2. amostra 5 sensores a cada 15 min com ruído -> CSV de campo (formato do painel);
3. calibra partindo do cadastro original e confere se recupera os valores verdadeiros;
4. aplica no cadastro (numa cópia) e confere a cópia de segurança.

Uso:  python teste_calibracao.py   (gera testes/medicoes_campo_teste.csv, útil para testar o painel)
"""
import os
import shutil
import sys
import tempfile
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
import calibracao as cal  # noqa: E402
from cadastro_para_inp import GPKG_PADRAO, converter, ler_cadastro  # noqa: E402
from simular import rodar  # noqa: E402

VERDADE = {"C_S1": 95.0, "f_S1": 0.90, "f_S2": 1.15}
SENSORES = [("S1", "pressao"), ("S2", "pressao"), ("T_S1_C", "vazao"), ("T_S2_B", "vazao"), ("R1", "nivel")]
RUIDO = {"pressao": 0.15, "nivel": 0.02, "vazao": 0.02}  # mca, m, fração
falhas = []


def checar(cond, msg):
    print(("  OK    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# ---- 1) rede verdadeira
c = ler_cadastro(GPKG_PADRAO)
dem = dict(zip(c["no_juncao"]["id"], c["no_juncao"]["demanda_base"]))
verdade = [{"camada": "trecho", "id": t, "campo": "rugosidade_hw", "valor": VERDADE["C_S1"]}
           for t in ("T_S1_A", "T_S1_B", "T_S1_C")]
verdade += [{"camada": "no_juncao", "id": "S1", "campo": "demanda_base", "valor": dem["S1"] * VERDADE["f_S1"]},
            {"camada": "no_juncao", "id": "S2", "campo": "demanda_base", "valor": dem["S2"] * VERDADE["f_S2"]}]
inp, rel = converter(GPKG_PADRAO, alteracoes=verdade)
res = rodar(inp)[0]

# ---- 2) leituras de campo com ruído
rng = np.random.default_rng(7)
horas = res.node["pressure"].index.to_numpy() / 3600
linhas = ["elemento;grandeza;hora;valor"]
for el, gr in SENSORES:
    serie = cal._serie(res, el, gr, {"R1": "reservatorio"})
    for h, v in zip(horas[:-1], serie[:-1]):
        v = v * (1 + rng.normal(0, RUIDO[gr])) if gr == "vazao" else v + rng.normal(0, RUIDO[gr])
        # formato brasileiro: ; como separador, vírgula decimal, hora HH:MM
        linhas.append(f"{el};{gr};{int(h):02d}:{int(round(h % 1 * 60)):02d};{f'{v:.3f}'.replace('.', ',')}")
csv = "\n".join(linhas)
arq_csv = os.path.join(AQUI, "medicoes_campo_teste.csv")
with open(arq_csv, "w", encoding="utf-8") as f:
    f.write(csv)
med = cal.ler_csv(csv)
checar(len(med) == 5 * 96, f"CSV de campo lido: {len(med)} leituras de {med['elemento'].nunique()} sensores")

# ---- 3) calibrar numa cópia do cadastro
tmp = os.path.join(tempfile.mkdtemp(), "cadastro.gpkg")
shutil.copyfile(GPKG_PADRAO, tmp)
cal.salvar_medicoes(tmp, med, "teste")
checar(len(cal.ler_medicoes(tmp)) == len(med), "medições gravadas no cadastro (tabela 'medicao')")

antes = cal.comparar(tmp)
print("  antes:", antes["resumo"], {f"{s['elemento']}/{s['grandeza']}": f"{s['dentro']:.0%}" for s in antes["sensores"]})
t0 = time.perf_counter()
r = cal.calibrar(tmp, por_c="setor", por_d="setor")
dt = time.perf_counter() - t0
p = {(x["tipo"], x["grupo"]): x for x in r["parametros"]}
for x in r["parametros"]:
    print(f"    {x['tipo']:10s} {x['grupo']:12s} {x['inicial']:>7} -> {x['calibrado']:>7}  "
          f"{'identificável' if x['identificavel'] else 'POUCO SENSÍVEL'}{'  (no limite)' if x['no_limite'] else ''}")
print(f"  {r['rodadas']} rodadas do EPANET em {dt:.1f} s · erro {r['antes']['erro']:.0f} -> {r['depois']['erro']:.0f}")
print("  depois:", r["depois"]["resumo"])

checar(abs(p[("rugosidade", "S1")]["calibrado"] - VERDADE["C_S1"]) <= 8,
       f"C do setor S1 recuperado: {p[('rugosidade', 'S1')]['calibrado']} (verdade {VERDADE['C_S1']})")
checar(abs(p[("demanda", "S1")]["calibrado"] - VERDADE["f_S1"]) <= 0.04,
       f"demanda S1 recuperada: ×{p[('demanda', 'S1')]['calibrado']} (verdade ×{VERDADE['f_S1']})")
checar(abs(p[("demanda", "S2")]["calibrado"] - VERDADE["f_S2"]) <= 0.04,
       f"demanda S2 recuperada: ×{p[('demanda', 'S2')]['calibrado']} (verdade ×{VERDADE['f_S2']})")
checar(antes["resumo"]["ajustados"] < antes["resumo"]["sensores"], "antes: modelo NÃO atende a meta em todos os sensores")
checar(r["depois"]["resumo"]["ajustados"] == r["depois"]["resumo"]["sensores"],
       f"depois: {r['depois']['resumo']['ajustados']}/{r['depois']['resumo']['sensores']} sensores dentro da meta (85% das leituras)")

# ---- 4) aplicar no cadastro (cópia) com backup
backup = cal.aplicar_ao_cadastro(tmp, r["alteracoes"])
c2 = ler_cadastro(tmp)
C_S1 = c2["trecho"].set_index("id").loc["T_S1_C", "rugosidade_hw"]
checar(os.path.exists(backup) and abs(C_S1 - p[("rugosidade", "S1")]["calibrado"]) < 0.1,
       f"aplicado ao cadastro (T_S1_C C={C_S1}) e cópia de segurança criada")
depois_aplicar = cal.comparar(tmp)
checar(depois_aplicar["resumo"]["ajustados"] == depois_aplicar["resumo"]["sensores"],
       "cadastro calibrado reproduz o campo sem precisar de proposta")

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
raise SystemExit(1 if falhas else 0)
