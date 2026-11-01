"""Teste das ferramentas de análise do motor (motor/analises.py) no cadastro de exemplo.

Confere se cada análise roda e se os números fazem sentido físico:
  incêndio: mais vazão exigida -> menos nós atendem; a vazão disponível mantém a pressão residual
  descarga: vazão maior limpa mais tubos
  criticidade: fechar o tubo de saída do reservatório corta a água de quase toda a rede
  zonas: bomba e VRPs dividem a rede em zonas
  energia: bomba consome energia e a ponta custa mais
  renovação, dimensionamento, qualidade, comparação e esqueletização

Uso:  ..\\.venv\\Scripts\\python.exe teste_analises.py
"""
import os
import shutil
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "motor"))
import analises as an  # noqa: E402

PASTA = tempfile.mkdtemp(prefix="gwater_teste_analises_")
GPKG = os.path.join(PASTA, "exemplo.gpkg")
shutil.copyfile(os.path.join(RAIZ, "cadastro", "gwater_cadastro.gpkg"), GPKG)
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def medir(nome, f, *a, **k):
    t0 = time.perf_counter()
    r = f(*a, **k)
    print(f"\n== {nome} ({time.perf_counter() - t0:.1f} s)")
    if not r.get("ok", True):
        print("   ", r.get("erro"), r.get("itens", [])[:3])
    return r


r10 = medir("incêndio 10 L/s", an.incendio, GPKG, vazao=10, p_residual=10)
r40 = medir("incêndio 40 L/s", an.incendio, GPKG, vazao=40, p_residual=10)
checar(r10["ok"] and r10["total"] > 0, f"incêndio roda em {r10['total']} nós às {r10['hora']}")
checar(r40["atendem"] <= r10["atendem"], f"mais vazão, menos atendem: {r10['atendem']} (10 L/s) ≥ {r40['atendem']} (40 L/s)")
pior = r10["linhas"][0]
print("    pior:", pior)
checar(all((x["q_disponivel"] >= 10) == x["atende"] or x["limitado_por"] for x in r10["linhas"]),
       "atende ⇔ vazão disponível ≥ exigida")
rz = medir("incêndio com pressão mínima na zona", an.incendio, GPKG, vazao=10, p_residual=10, p_min_zona=10)
checar(all((a["q_disponivel"] or 0) >= (b["q_disponivel"] or 0) - 0.1 for a, b in
           zip(sorted(r10["linhas"], key=lambda x: x["id"]), sorted(rz["linhas"], key=lambda x: x["id"]))),
       "exigir pressão na zona nunca aumenta a vazão disponível")

d5 = medir("descarga 5 L/s", an.descarga, GPKG, vazao=5)
d30 = medir("descarga 30 L/s", an.descarga, GPKG, vazao=30)
s5, s30 = sum(e["n_tubos"] for e in d5["eventos"]), sum(e["n_tubos"] for e in d30["eventos"])
checar(s30 >= s5 and s30 > 0, f"descarga maior limpa mais tubos ({s5} → {s30})")

c = medir("criticidade", an.criticidade, GPKG)
top = c["linhas"][0]
print("    mais crítico:", top)
checar(c["ok"] and top["falta_pct"] > 0, f"o tubo mais crítico corta {top['falta_pct']}% da água ({top['id']})")

z = medir("zonas de pressão", an.zonas_pressao, GPKG)
print("    zonas:", [(x["zona"], x["n_nos"], x["entradas"], x["saidas"]) for x in z["zonas"]])
checar(len(z["zonas"]) >= 2 and z["divisas"], f"{len(z['zonas'])} zonas, divisas {z['divisas']}")

e = medir("energia", an.energia, GPKG)
print("    bombas:", [{k: v for k, v in b.items() if k != "serie_kw"} for b in e["bombas"]])
checar(e["bombas"] and e["total_kwh_dia"] > 0, f"bombas consomem {e['total_kwh_dia']} kWh/dia, R$ {e['total_custo_mes']}/mês")

rn = medir("renovação", an.renovacao, GPKG)
checar(rn["linhas"] and rn["linhas"][0]["nota"] >= rn["linhas"][-1]["nota"], f"ranking de {len(rn['linhas'])} tubos, "
       f"1º {rn['linhas'][0]['id']} nota {rn['linhas'][0]['nota']}")

cand = [x["id"] for x in c["linhas"][:4]]
dz = medir("dimensionamento", an.dimensionar, GPKG, trechos=cand, p_min=10)
print("    ", {k: v for k, v in dz.items() if k not in ("linhas", "alteracoes")})
checar(dz["ok"] and dz["linhas"], f"dimensiona {len(cand)} tubos: atende={dz['atende']}, R$ {dz['custo_total']}")

q = medir("idade da água", an.qualidade, GPKG, parametro="AGE", duracao_h=48)
mx = max(v["max"] for v in q["nos"].values())
checar(q["ok"] and mx > 0, f"idade máxima {mx} h")
cl = medir("cloro", an.qualidade, GPKG, parametro="CHEMICAL", duracao_h=48, conc_fonte=1.5, kb_dia=-1.0)
vals = [v["min"] for v in cl["nos"].values() if v["min"] is not None]
checar(cl["ok"] and vals and max(vals) <= 1.5 + 1e-6, f"cloro entre {min(vals)} e {max(vals)} mg/L (fonte 1,5)")

alt = [{"camada": "global", "id": "", "campo": "fator_demanda", "valor": 1.5}]
cp = medir("comparar atual × demanda +50%", an.comparar, GPKG, cenario_b=alt)
print("    A:", cp["a"], "\n    B:", cp["b"])
checar(cp["b"]["p_min"] <= cp["a"]["p_min"], "mais demanda, pressão mínima não sobe")

destino = os.path.join(PASTA, "exemplo_esqueleto.gpkg")
sk = medir("esqueletização", an.esqueletizar, GPKG, destino, dn_max=100)
print("    ", sk)
checar(sk["ok"] and os.path.exists(destino), f"esqueleto: {sk['tubos_final']} tubos, {sk['nos_final']} nós")
import geopandas as gpd  # noqa: E402
d_orig = gpd.read_file(GPKG, layer="no_juncao")["demanda_base"].fillna(0).sum()
checar(abs(sk["demanda_total"] - d_orig) < 0.01, f"demanda conservada ({d_orig:.3f} → {sk['demanda_total']} L/s)")
from cadastro_para_inp import converter  # noqa: E402
_, rel = converter(destino)
checar(rel.ok, "o esqueleto continua válido para o EPANET" + ("" if rel.ok else f": {rel.itens()[:3]}"))

shutil.rmtree(PASTA, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
