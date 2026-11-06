"""Gera o modelo EPANET (.inp) do sistema do Centro de Operações.

Sistema: captação -> estação elevatória -> reservatório R1 ->
  ramal S1 com VRP 1 e VRP 2 em série
  ramal S2 com VRP 3 independente

Todos os parâmetros ajustáveis pelo painel estão em PADRAO.
"""
import math

PADRAO = {
    "cap_r1": 520.0,       # capacidade útil do R1 (m³)
    "nivel_ini": 58.0,     # nível inicial do R1 (%)
    "bomba_liga": 42.0,    # liga a bomba abaixo deste nível (%)
    "bomba_desliga": 88.0, # desliga a bomba acima deste nível (%)
    "vrp1": 30.0,          # setpoint de jusante (mca)
    "vrp2": 18.0,
    "vrp3": 22.0,
    "fator_demanda": 1.0,  # multiplicador sobre a demanda base
    "rugosidade": 130.0,   # Hazen-Williams C das redes
}

ALTURA_R1 = 6.0  # altura útil do reservatório (m)


def padrao_consumo():
    """96 multiplicadores (15 min) com picos manhã, almoço e noite."""
    g = lambda h, m, s: math.exp(-0.5 * ((h - m) / s) ** 2)
    q = [8.5 + 11 * g(i / 4, 7.2, 1.6) + 7 * g(i / 4, 12.6, 1.8) + 12 * g(i / 4, 19.4, 2.2)
         for i in range(96)]
    media = sum(q) / len(q)
    return [v / media for v in q], media


def gerar_inp(params=None):
    p = {**PADRAO, **(params or {})}
    mult, media = padrao_consumo()
    dem = media * p["fator_demanda"]
    C = p["rugosidade"]
    diam_r1 = math.sqrt(4 * p["cap_r1"] / ALTURA_R1 / math.pi)
    nv = lambda pct: ALTURA_R1 * pct / 100

    pat = "\n".join(
        "PAD_CONS " + " ".join(f"{m:.4f}" for m in mult[i:i + 8]) for i in range(0, 96, 8))

    return f"""[TITLE]
GWATER - Sistema do Centro de Operacoes (REV 0.1.0)

[JUNCTIONS]
;ID      Elev   Demand  Pattern
J_SUC    98     0
J_REC    98     0
R1_ENT   129    0
J_SAI    104    0
V1M      92     0
V1J      92     0
V2M      85     0
V2J      85     0
S1       82     {dem * 0.62:.3f}  PAD_CONS
V3M      90     0
V3J      90     0
S2       87     {dem * 0.38:.3f}  PAD_CONS

[RESERVOIRS]
;ID   Head
CAP   100

[TANKS]
;ID  Elev  InitLvl  MinLvl  MaxLvl  Diam  MinVol
R1   130   {nv(p['nivel_ini']):.3f}  0  {ALTURA_R1}  {diam_r1:.3f}  0

[PIPES]
;ID         N1      N2      Len   Diam  Rough  Minor Status
T_SUCCAO    CAP     J_SUC   20    250   {C}    0     Open
T_RECALQUE  J_REC   R1_ENT  1500  200   {C}    0     CV
T_ENT_R1    R1_ENT  R1      10    200   {C}    0     Open
T_SAI_R1    R1      J_SAI   30    250   {C}    0     Open
T_S1_A      J_SAI   V1M     800   200   {C}    0     Open
T_S1_B      V1J     V2M     600   150   {C}    0     Open
T_S1_C      V2J     S1      500   150   {C}    0     Open
T_S2_A      J_SAI   V3M     700   150   {C}    0     Open
T_S2_B      V3J     S2      400   150   {C}    0     Open

[PUMPS]
;ID  N1     N2     Params
B1   J_SUC  J_REC  HEAD CURVA_B1

[VALVES]
;ID    N1   N2   Diam  Type  Setting  Minor
VRP1   V1M  V1J  150   PRV   {p['vrp1']}  0
VRP2   V2M  V2J  150   PRV   {p['vrp2']}  0
VRP3   V3M  V3J  150   PRV   {p['vrp3']}  0

[CURVES]
;ID        Q(L/s)  H(m)
CURVA_B1   0       55
CURVA_B1   26      42
CURVA_B1   40      30

[PATTERNS]
{pat}

[CONTROLS]
LINK B1 OPEN IF NODE R1 BELOW {nv(p['bomba_liga']):.3f}
LINK B1 CLOSED IF NODE R1 ABOVE {nv(p['bomba_desliga']):.3f}

[TIMES]
Duration            24:00
Hydraulic Timestep  0:15
Pattern Timestep    0:15
Report Timestep     0:15
Report Start        0:00

[OPTIONS]
Units      LPS
Headloss   H-W
Trials     100
Accuracy   0.001

[COORDINATES]
;Node    X     Y   (layout do esquemático do painel)
CAP      69    210
J_SUC    230   225
J_REC    330   225
R1_ENT   460   225
R1       515   165
J_SAI    600   150
V1M      690   150
V1J      730   150
V2M      815   150
V2J      855   150
S1       912   150
V3M      730   320
V3J      770   320
S2       912   320

[END]
"""
