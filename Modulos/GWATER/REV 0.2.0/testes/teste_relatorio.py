"""Teste da tradução do relatório do EPANET (simular.ler_relatorio) e das validações de digitação.

Usa linhas reais de um relatório em que o EPANET parou (bomba fora da curva, válvulas isolando trechos)
e confere que a mensagem que chega ao usuário diz o motivo e aponta o elemento.

Uso:  python teste_relatorio.py
"""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
from simular import FalhaEpanet, ler_relatorio, rodar  # noqa: E402

falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


RPT = """
  WARNING: Pump B-0001 open but exceeds maximum flow at 0:00:00 hrs.
  WARNING: Pump B-0002 open but exceeds maximum flow at 0:00:00 hrs.
  WARNING: Pump B-0001 open but exceeds maximum flow at 0:15:00 hrs.
  WARNING: Node N-0015 disconnected at 0:18:22 hrs
  WARNING: System disconnected because of Link V-0009
  WARNING: Pump B-0002 closed because cannot deliver head at 2:30:14 hrs.
  WARNING: System unbalanced at 2:30:14 hrs. EXECUTION HALTED.
  WARNING: Node V-0003__J disconnected at 2:30:14 hrs
"""
r = ler_relatorio(RPT)
print("\n".join(f"    {x}" for x in r))
checar(r[0][0] == "ERRO" and "2:30:14" in r[0][2] and "desequilibrada" in r[0][2], "parada do EPANET vem primeiro, com a hora")
b1 = [m for n, e, m in r if e == "B-0001"]
checar(len(b1) == 1 and "vazão máxima" in b1[0] and "2 vezes" in b1[0], "bomba além da curva, agrupada (2 vezes)")
checar(any(e == "B-0002" and "não vence a altura" in m for _, e, m in r), "bomba desligada por falta de altura")
checar(any(e == "V-0009" and "isolou" in m for _, e, m in r), "válvula que isolou parte da rede")
checar(any(e == "V-0003" for _, e, m in r), "nó interno V-0003__J vira o equipamento V-0003")

# um .inp que o EPANET não resolve: bomba recalcando para um reservatório 100 m acima do shutoff da curva
INP = """[TITLE]
teste
[JUNCTIONS]
J1  0  0
J2  0  0
[RESERVOIRS]
FONTE  10
[TANKS]
ALTO  200  2  0  5  10  0
[PIPES]
T1  FONTE  J1  100  200  130  0  Open
T2  J2  ALTO  100  200  130  0  Open
[PUMPS]
B1  J1  J2  HEAD C1
[CURVES]
C1  0  40
C1  20  30
C1  30  15
[OPTIONS]
Units  LPS
Headloss  H-W
[TIMES]
Duration  1:00
Hydraulic Timestep  0:15
[END]
"""
avisos = []
try:
    rodar(INP, avisos)
    erro = None
except FalhaEpanet as e:
    erro = e
txt = " | ".join(m for _, _, m in (erro.avisos if erro else avisos))
checar(any(e == "B1" and "altura" in m for _, e, m in (erro.avisos if erro else avisos)),
       f"bomba sem altura para chegar ao reservatório é apontada: {txt[:140]}")

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
