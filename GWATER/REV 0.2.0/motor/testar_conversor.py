"""Teste: o modelo gerado a partir do cadastro reproduz a Fase 0?

Uso:  python testar_conversor.py
"""
from simular import simular, simular_cadastro

TOL = 0.05  # mca ou L/s ou % de nível

ref, _ = simular()
# a Fase 0 usa demanda fixa (DDA); o cadastro usa PDA por padrão -> compara no mesmo modo
cad, _ = simular_cadastro(alteracoes=[{"camada": "global", "campo": "modelo_demanda", "valor": "DDA"}])
assert len(ref["rows"]) == len(cad["rows"]), "número de passos diferente"

pior = {}
for a, b in zip(ref["rows"], cad["rows"]):
    for k, v in a.items():
        pior[k] = max(pior.get(k, 0), abs(v - b[k]))

falhas = {k: d for k, d in pior.items() if d > TOL}
for k, d in sorted(pior.items(), key=lambda x: -x[1]):
    print(f"  {k:7s} diferença máxima {d:.4f}")
print("\nRESULTADO:", "IGUAL à Fase 0" if not falhas else f"DIFERENTE em {list(falhas)}")
raise SystemExit(1 if falhas else 0)
