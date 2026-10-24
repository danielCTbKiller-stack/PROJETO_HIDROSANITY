"""Teste: propostas mudam o resultado do jeito esperado e ficam gravadas no cadastro.

Uso:  python testar_cenarios.py      (trabalha numa cópia do cadastro de exemplo)
"""
import os
import shutil
import tempfile

import cenarios
import gwater_cli
from cadastro_para_inp import GPKG_PADRAO

tmp = os.path.join(tempfile.mkdtemp(), "cadastro.gpkg")
shutil.copyfile(GPKG_PADRAO, tmp)
falhas = []


def checar(cond, msg):
    print(("  OK    " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


def sim(alts=None, proj=False):
    d = gwater_cli.simular(tmp, proj, alts, nome_inp="teste")
    assert d["ok"], d["itens"]
    return d


base = sim()
pmax = lambda d, n: max(d["nos"][n]["p"])
qmax = lambda d, l: max(abs(x) for x in d["links"][l]["q"])

# 1) setpoint da VRP 2: 18 -> 25 mca sobe a pressão em S1 ~7 mca
d = sim([{"camada": "valvula", "id": "VRP2", "campo": "ajuste", "valor": 25}])
checar(abs((pmax(d, "S1") - pmax(base, "S1")) - 7) < 0.3,
       f"VRP2 18→25 mca: S1 máx {pmax(base, 'S1'):.1f} → {pmax(d, 'S1'):.1f} mca")

# 2) manobra: fechar o único trecho do setor S2 -> aviso apontando S2, simula, S2 recebe zero
d = sim([{"camada": "trecho", "id": "T_S2_A", "campo": "status", "valor": "FECHADO"}])
checar(any("SEM ABASTECIMENTO" in i["msg"] and i["id"] == "S2" for i in d["itens"]) and max(d["nos"]["S2"]["d"]) < 0.01
       and max(d["nos"]["S2"]["de"]) > 1, "T_S2_A fechado → aviso 'S2 SEM ABASTECIMENTO', entregue 0 de "
       f"{max(d['nos']['S2']['de']):.1f} L/s solicitados")
d = sim([{"camada": "valvula", "id": "VRP3", "campo": "status", "valor": "FECHADA"}])
checar(max(d["nos"]["S2"]["d"]) < 0.01, "VRP3 fechada → S2 sem abastecimento")
# 2b) entrada do R1 fechada: o reservatório esvazia e o atendimento cai (antes o EPANET travava)
d = sim([{"camada": "trecho", "id": "T_ENT_R1", "campo": "status", "valor": "FECHADO"}])
vazio = next((i for i, v in enumerate(d["nos"]["R1"]["p"]) if v < 0.01), None)
falta = sum(a - b for a, b in zip(d["nos"]["S1"]["de"], d["nos"]["S1"]["d"]))
checar(vazio is not None and falta > 1, f"T_ENT_R1 fechado → R1 esvazia às {d['horas'][vazio]:.2f} h e S1 fica sem água")
checar(all(abs(a - b) < 1e-6 for a, b in zip(base["nos"]["S1"]["de"], base["nos"]["S1"]["d"])),
       "rede atual: 100% da demanda atendida (PDA não altera a operação normal)")

# 3) diâmetro maior reduz a velocidade
d = sim([{"camada": "trecho", "id": "T_S1_C", "campo": "diametro_nominal", "valor": 250}])
vmax = lambda d, l: max(abs(x) for x in d["links"][l]["v"])
checar(vmax(d, "T_S1_C") < vmax(base, "T_S1_C") * 0.5,
       f"T_S1_C DN150→250: v máx {vmax(base, 'T_S1_C'):.2f} → {vmax(d, 'T_S1_C'):.2f} m/s")

# 4) fator de demanda 1,5 aumenta o consumo em 50%
d = sim(cenarios.alteracoes_completas({"fator_demanda": 1.5}))
checar(abs(qmax(d, "T_SAI_R1") / qmax(base, "T_SAI_R1") - 1.5) < 0.01, "fator de demanda 1,5 → saída do R1 ×1,50")

# 5) bomba forçada desligada: controles ignorados, vazão zero o dia todo
d = sim([{"camada": "bomba", "id": "B1", "campo": "status_inicial", "valor": "FECHADA"}])
checar(qmax(d, "B1") < 0.01 and any("controles" in i["msg"] for i in d["itens"]),
       "B1 forçada desligada: vazão 0 e aviso de controles desconsiderados")

# 6) alteração inválida vira erro legível
d = gwater_cli.simular(tmp, False, [{"camada": "trecho", "id": "NAO_EXISTE", "campo": "diametro_nominal", "valor": 100}])
checar(not d["ok"] and "não existe" in d["itens"][0]["msg"], "elemento inexistente na proposta → erro claro")

# 7) gravar, listar, atualizar e excluir no GeoPackage
cid = cenarios.salvar(tmp, {"nome": "Reforço Setor S1", "descricao": "teste", "com_projetados": False,
                            "fator_demanda": 1.2, "alteracoes": [{"camada": "valvula", "id": "VRP2",
                                                                 "campo": "ajuste", "valor": "25"}]})
lst = cenarios.listar(tmp)
checar(len(lst) == 1 and lst[0]["id"] == "REFORCO_SETOR_S1" and lst[0]["alteracoes"][0]["valor"] == "25",
       f"cenário gravado no cadastro como {cid}")
cenarios.salvar(tmp, {**lst[0], "fator_demanda": 1.3})
cenarios.salvar(tmp, {"nome": "Reforço Setor S1", "alteracoes": []})
lst = cenarios.listar(tmp)
checar(len(lst) == 2 and lst[0]["fator_demanda"] == 1.3 and lst[1]["id"] == "REFORCO_SETOR_S1_2",
       "atualizar mantém o id; nome repetido gera id novo")
cenarios.excluir(tmp, "REFORCO_SETOR_S1_2")
checar([x["id"] for x in cenarios.listar(tmp)] == ["REFORCO_SETOR_S1"], "excluir remove só o cenário pedido")
d = gwater_cli.simular(tmp, False)
checar(d["ok"], "cadastro continua válido com as tabelas de cenário")

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
raise SystemExit(1 if falhas else 0)
