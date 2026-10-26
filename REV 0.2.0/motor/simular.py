"""Roda o modelo no motor EPANET (via WNTR) e exporta os resultados para o painel.

Uso:  python simular.py
Gera: ../modelo/sistema_cos.inp  e  ../painel/resultados.js
"""
import json
import os
import re
import tempfile
import time
from collections import OrderedDict

import wntr

from modelo import ALTURA_R1, PADRAO, gerar_inp

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# chave usada pelo painel -> (tipo, elemento, grandeza)
MAPA = {
    "qIn":   ("link", "B1", "flowrate"),
    "qOut":  ("link", "T_SAI_R1", "flowrate"),
    "qS1":   ("link", "T_S1_C", "flowrate"),
    "qS2":   ("link", "T_S2_B", "flowrate"),
    "pMont": ("node", "J_SUC", "pressure"),
    "pJus":  ("node", "J_REC", "pressure"),
    "pEnt":  ("node", "R1_ENT", "pressure"),
    "pRes":  ("node", "J_SAI", "pressure"),
    "v1m":   ("node", "V1M", "pressure"),
    "v1j":   ("node", "V1J", "pressure"),
    "v2m":   ("node", "V2M", "pressure"),
    "v2j":   ("node", "V2J", "pressure"),
    "v3m":   ("node", "V3M", "pressure"),
    "v3j":   ("node", "V3J", "pressure"),
    "pRede": ("node", "S1", "pressure"),
    "pS2":   ("node", "S2", "pressure"),
    "velRec": ("link", "T_RECALQUE", "velocity"),
    "velS1": ("link", "T_S1_C", "velocity"),
    "velS2": ("link", "T_S2_B", "velocity"),
}


# no modelo gerado do cadastro, bombas e válvulas têm nós internos <id>__M / <id>__J
NOS_CADASTRO = {"J_SUC": "B1__M", "J_REC": "B1__J", "V1M": "VRP1__M", "V1J": "VRP1__J",
                "V2M": "VRP2__M", "V2J": "VRP2__J", "V3M": "VRP3__M", "V3J": "VRP3__J"}
MAPA_CADASTRO = {k: (t, NOS_CADASTRO.get(el, el), g) for k, (t, el, g) in MAPA.items()}


class FalhaEpanet(Exception):
    """O EPANET parou. `avisos`: o relatório dele traduzido ([(nivel, elemento, mensagem)])."""

    def __init__(self, msg, avisos):
        super().__init__(msg)
        self.avisos = avisos


# avisos do relatório (.rpt) do EPANET 2.2 -> mensagem em português; {e} = elemento, {h} = hora
AVISOS_RPT = [
    (r"System unbalanced at ([\d:]+) hrs", "ERRO", None,
     "o EPANET parou às {h}: a rede ficou desequilibrada (o cálculo não converge). As causas mais comuns estão nos "
     "avisos abaixo: bomba fora da curva, válvula isolando trechos, níveis ou cargas digitados errado"),
    (r"Pump (\S+) .*exceeds maximum flow", "AVISO", 1,
     "bomba {e}: trabalha além da vazão máxima da curva (a demanda é maior do que a bomba entrega, ou falta altura "
     "de recalque). Confira a curva em Curvas de bomba"),
    (r"Pump (\S+) .*cannot deliver head", "AVISO", 1,
     "bomba {e}: desligou porque não vence a altura pedida (a altura máxima da curva, no shutoff, é menor que o "
     "desnível até onde ela recalca). Confira a curva e a cota/nível do destino"),
    (r"Pump (\S+) .*exceeds", "AVISO", 1, "bomba {e}: fora da faixa da curva"),
    (r"Valve (\S+) caused ill-conditioning", "AVISO", 1,
     "válvula {e}: deixou o cálculo instável (ajuste muito baixo ou válvulas em série brigando)"),
    (r"System disconnected because of Link (\S+)", "AVISO", 1,
     "{e}: fechou e isolou parte da rede"),
    (r"Node (\S+) disconnected", "AVISO", 1, "nó {e}: ficou sem ligação com nenhuma fonte de água"),
    (r"Negative pressures at ([\d:]+) hrs", "AVISO", None, "pressões negativas na rede às {h}"),
    (r"(?:Error|Erro) (\d+):?\s*(.*)", "ERRO", None, "erro {e} do EPANET: {t}"),
]


def ler_relatorio(texto):
    """Traduz os avisos do relatório do EPANET, agrupando repetições: [(nivel, elemento, mensagem)]."""
    grupos = OrderedDict()
    hora = None
    for linha in texto.splitlines():
        m_h = re.search(r"at ([\d:]+) hrs", linha)
        if m_h:
            hora = m_h.group(1)
        for padrao, nivel, grupo_el, modelo in AVISOS_RPT:
            m = re.search(padrao, linha)
            if not m:
                continue
            el = m.group(1) if grupo_el else None
            if el:
                el = el.split("__")[0]  # nós internos de bomba/válvula -> o próprio equipamento
            chave = (modelo, el)
            if chave not in grupos:
                txt = m.group(2) if modelo.startswith("erro") and m.lastindex and m.lastindex >= 2 else ""
                grupos[chave] = [nivel, el or (m.group(1) if modelo.startswith("erro") else None),
                                 modelo.format(e=el or (m.group(1) if m.groups() else ""), h=hora or "?", t=txt), 0, hora]
            grupos[chave][3] += 1
            break
    out = []
    for nivel, el, msg, n, primeira in grupos.values():
        if n > 1 and "{h}" not in msg:
            msg += f" ({n} vezes; a primeira às {primeira})" if primeira else f" ({n} vezes)"
        out.append((nivel, el, msg))
    return sorted(out, key=lambda x: x[0] != "ERRO")


def _limpar_sobras(horas=6):
    """Pastas temporárias de cálculos antigos que o Windows não deixou apagar na hora (arquivo preso pelo
    antivírus ou pelo EPANET): apaga as que já passaram de algumas horas, sem nunca interromper o cálculo."""
    import glob
    import shutil
    limite = time.time() - horas * 3600
    for d in glob.glob(os.path.join(tempfile.gettempdir(), "gwater_sim_*")):
        try:
            if os.path.getmtime(d) < limite:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def rodar(inp, avisos=None):
    """Roda um texto .inp no EPANET e devolve (resultados WNTR, segundos).

    avisos: lista que recebe o relatório do EPANET traduzido (bomba fora da curva, nó isolado...).
    Se o EPANET parar, levanta FalhaEpanet com o motivo, em vez do erro sem sentido da leitura do arquivo."""
    t0 = time.perf_counter()
    _limpar_sobras()
    with tempfile.TemporaryDirectory(prefix="gwater_sim_", ignore_cleanup_errors=True) as tmp:
        arq = os.path.join(tmp, "modelo.inp")
        with open(arq, "w", encoding="utf-8") as f:
            f.write(inp)
        wn = wntr.network.WaterNetworkModel(arq)

        def relatorio():
            try:
                with open(os.path.join(tmp, "run.rpt"), encoding="latin-1") as f:
                    return ler_relatorio(f.read())
            except OSError:
                return []
        try:
            res = wntr.sim.EpanetSimulator(wn).run_sim(file_prefix=os.path.join(tmp, "run"))
        except Exception as e:
            rel = relatorio()
            motivo = next((m for n, _, m in rel if n == "ERRO"), None)
            raise FalhaEpanet(motivo or f"o EPANET não conseguiu resolver a rede ({type(e).__name__}: {e})", rel) \
                from e
        if avisos is not None:
            avisos.extend(relatorio())
    return res, time.perf_counter() - t0


def extrair(res, mapa=MAPA, altura_r1=ALTURA_R1):
    nos, trechos = res.node, res.link
    nivel = nos["pressure"]["R1"] / altura_r1 * 100  # pressão no tanque = lâmina d'água
    status_b1 = trechos["status"]["B1"]
    rows = []
    for i, t in enumerate(nivel.index):
        r = {"hora": t / 3600, "level": float(nivel.iloc[i]), "bomba": int(status_b1.iloc[i] > 0)}
        for k, (tipo, el, g) in mapa.items():
            v = float((nos if tipo == "node" else trechos)[g][el].iloc[i])
            r[k] = v * 1000 if g == "flowrate" else v  # m³/s -> L/s
        rows.append(r)
    return rows


PRESSOES = ("pMont", "pJus", "pEnt", "pRes", "v1m", "v1j", "v2m", "v2j", "v3m", "v3j", "pRede", "pS2")


def pacote(rows, dt, params, fonte):
    avisos = []
    pmin = min(r[k] for r in rows for k in PRESSOES)
    if pmin < 0:
        avisos.append(f"pressão negativa ({pmin:.0f} mca): a rede não consegue atender a demanda "
                      f"nessas condições; os valores perto e abaixo de zero não têm sentido físico")
    return {"motor": f"EPANET 2.2 via WNTR {wntr.__version__}", "fonte": fonte,
            "tempo_calculo_s": round(dt, 3), "params": params, "rows": rows, "avisos": avisos}


def simular(params=None):
    p = {**PADRAO, **(params or {})}
    inp = gerar_inp(p)
    res, dt = rodar(inp)
    return pacote(extrair(res), dt, p, "modelo fixo (Fase 0)"), inp


def simular_cadastro(gpkg=None, alteracoes=None):
    from cadastro_para_inp import GPKG_PADRAO, converter
    inp, rel = converter(gpkg or GPKG_PADRAO, alteracoes=alteracoes)
    if not rel.ok:
        raise ValueError("cadastro com erros:\n" + rel.texto())
    res, dt = rodar(inp)
    # parâmetros reais do cadastro que o painel exibe
    import pyogrio
    r1 = pyogrio.read_dataframe(gpkg or GPKG_PADRAO, layer="reservatorio").set_index("id").loc["R1"]
    p = {**PADRAO, "cap_r1": float(r1["volume_util"])}
    return pacote(extrair(res, MAPA_CADASTRO, float(r1["nivel_max"])), dt, p, "cadastro QGIS"), inp


def exportar(params=None):
    dados, inp = simular(params)
    with open(os.path.join(RAIZ, "modelo", "sistema_cos.inp"), "w", encoding="utf-8") as f:
        f.write(inp)
    with open(os.path.join(RAIZ, "painel", "resultados.js"), "w", encoding="utf-8") as f:
        f.write("window.GWATER_RESULTS=" + json.dumps(dados, ensure_ascii=False) + ";\n")
    return dados


if __name__ == "__main__":
    d = exportar()
    r = d["rows"]
    print(f"{d['motor']} | {len(r)} passos | {d['tempo_calculo_s']} s")
    for k in ("qIn", "qOut", "level", "pJus", "v1j", "v2j", "v3j", "pRede", "pS2", "velRec"):
        vs = [x[k] for x in r]
        print(f"  {k:7s} min {min(vs):7.2f}  max {max(vs):7.2f}")
