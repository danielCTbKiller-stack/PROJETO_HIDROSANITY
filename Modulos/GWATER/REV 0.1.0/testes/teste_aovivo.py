"""Teste da operação ao vivo: o gêmeo digital detecta um vazamento sem dar falso alarme?

Roda o simulador de telemetria sem esperar o relógio (passo a passo):
  - rede "real" = cadastro + vazamento de 4 L/s no nó S1 a partir das 10:00;
  - 05:00-10:00: não pode haver alarme de vazamento (nem desvio);
  - depois das 10:00: alarme VAZAMENTO no setor S1 em até 30 min, nenhum no S2;
  - sensor que para de transmitir gera alarme de COMUNICACAO; voltando, normaliza;
  - reconhecer alarme.
Uso:  python teste_aovivo.py   (trabalha numa cópia do cadastro de exemplo)
"""
import os
import shutil
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
import aovivo  # noqa: E402
from cadastro_para_inp import GPKG_PADRAO  # noqa: E402

tmp = os.path.join(tempfile.mkdtemp(), "cadastro.gpkg")
shutil.copyfile(GPKG_PADRAO, tmp)
falhas = []


def checar(cond, msg):
    print(("  OK    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


g = aovivo.Gemeo(tmp)
sim = aovivo.Simulador(g, inicio_h=5.0, vazamento={"no": "S1", "hora": 10.0, "lps": 4.0}, semente=3)
print("  sensores:", ", ".join(f"{e}/{gr}" for e, gr in sim.sensores))
hora = lambda: (sim.t / 3600)
t0 = time.perf_counter()

# ---- 05:00 -> 10:00 sem vazamento
tipos_antes = set()
while hora() < 9.75:
    sim.avancar(5)
    tipos_antes |= {a["tipo"] for a in g.alarmes.values()}
e = g.estado()   # 09:45, antes do vazamento
s1 = next(s for s in e["sensores"] if s["elemento"] == "T_S1_C" and s["grandeza"] == "vazao")
checar(abs(s1["desvio"]) < 0.6, f"gêmeo acompanha o campo às 09:45: T_S1_C medido {s1['valor']:.2f} × esperado {s1['esperado']:.2f} L/s")
while hora() < 10.0:
    sim.avancar(5)
    tipos_antes |= {a["tipo"] for a in g.alarmes.values()}
checar(not ({"VAZAMENTO", "DESVIO"} & tipos_antes), f"sem vazamento: nenhum alarme de vazamento/desvio (tipos vistos: {sorted(tipos_antes) or 'nenhum'})")

# ---- vazamento às 10:00
detectado = None
while hora() < 11.0 and not detectado:
    sim.avancar(1)
    a = g.alarmes.get("VAZAMENTO|S1")
    if a:
        detectado = (hora(), a)
checar(detectado is not None and detectado[0] <= 10.5,
       f"vazamento detectado às {aovivo.txt_hora(sim.base + detectado[0] * 3600) if detectado else '—'} "
       f"(início real 10:00)")
if detectado:
    print("    →", detectado[1]["severidade"].upper(), "·", detectado[1]["mensagem"])
checar("VAZAMENTO|S2" not in g.alarmes, "setor S2 sem alarme de vazamento (o vazamento é no S1)")

# ---- reconhecer
aid = g.alarmes["VAZAMENTO|S1"]["id"] if "VAZAMENTO|S1" in g.alarmes else -1
checar(g.reconhecer(aid) and g.alarmes["VAZAMENTO|S1"]["reconhecido"] is not None, "operador reconhece o alarme")

# ---- sensor mudo
sim.falha.add(("S2", "pressao"))
sim.avancar(12)
checar("COMUNICACAO|S2|pressao" in g.alarmes, "S2 parou de transmitir → alarme de comunicação em 10 min")
sim.falha.clear()
sim.avancar(2)
checar("COMUNICACAO|S2|pressao" not in g.alarmes and any(h["evento"] == "normalizado" and h["tipo"] == "COMUNICACAO"
                                                         for h in g.historico), "S2 voltou → alarme normalizado no histórico")

# ---- o resto do dia: o vazamento continua sendo apontado, previsão do reservatório
while hora() < 20.0:
    sim.avancar(15)
checar("VAZAMENTO|S1" in g.alarmes, "às 20:00 o vazamento no S1 continua sinalizado")
e = g.estado()
r1 = next(s for s in e["sensores"] if s["elemento"] == "R1")
checar(len(r1["previsao"]) > 10 and len(r1["medido"]) > 100, f"estado para a tela: R1 com {len(r1['medido'])} leituras "
       f"e {len(r1['previsao'])} pontos de previsão")
n = g.db.execute("SELECT COUNT(*) FROM leitura").fetchone()[0]
checar(n > 5000, f"{n} leituras gravadas no banco de telemetria")
print(f"  {(sim.t / 3600 - 5):.0f} h simuladas em {time.perf_counter() - t0:.1f} s · alarmes ativos: "
      f"{[a['chave'] for a in g.alarmes.values()]}")
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
raise SystemExit(1 if falhas else 0)
