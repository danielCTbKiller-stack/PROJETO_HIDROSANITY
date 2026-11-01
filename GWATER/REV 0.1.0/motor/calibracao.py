"""Calibração do modelo com medições de campo.

Medições: CSV com uma leitura por linha (separador , ou ; e decimal . ou ,):
    elemento;grandeza;hora;valor
    S1;pressao;07:15;19,4
    T_S1_C;vazao;7.25;11,8
    R1;nivel;07:15;3,61
  grandeza: pressao (mca, em nó; em válvula/bomba vale o lado de jusante, ou use VRP1__M),
            vazao (L/s, em trecho, bomba ou válvula), nivel (m, em reservatório).
  hora: HH:MM, HH:MM:SS, horas decimais ou data/hora (usa a hora do dia).

Calibração automática: ajusta a rugosidade C (por material, setor ou única) e um
fator de demanda (por setor ou global) para aproximar o modelo das medições,
minimizando o erro normalizado (mínimos quadrados, scipy).
"""
import io
import math
import re
import shutil
from datetime import datetime

import numpy as np
import pandas as pd
import pyogrio

from cadastro_para_inp import ler_cadastro, converter
from simular import rodar

T_MED = "medicao"
# tolerância de cada grandeza: leitura "ajustada" se |modelo - campo| <= tolerância
TOL = {"pressao": 1.0, "nivel": 0.10, "vazao": 0.05}   # mca, m, fração da vazão medida
TOL_VAZAO_MIN = 0.2                                     # L/s
META = 0.85                                             # 85% das leituras dentro da tolerância
SIGMA = {"pressao": 0.5, "nivel": 0.05, "vazao": None}  # peso do resíduo (vazão: 5% da média medida)
UN = {"pressao": "mca", "vazao": "L/s", "nivel": "m"}
LIM_C, LIM_F = (40.0, 150.0), (0.3, 3.0)


# ------------------------------------------------------------------ medições
def _hora(v):
    s = str(v).strip()
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", s)
    if m:
        return int(m[1]) + int(m[2]) / 60 + int(m[3] or 0) / 3600
    return float(s.replace(",", "."))


def ler_csv(texto):
    texto = texto.lstrip("﻿")
    sep = ";" if texto.split("\n", 1)[0].count(";") >= texto.split("\n", 1)[0].count(",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    faltam = {"elemento", "grandeza", "hora", "valor"} - set(df.columns)
    if faltam:
        raise ValueError(f"faltam as colunas {sorted(faltam)} (esperado: elemento, grandeza, hora, valor)")
    df = df.dropna(subset=["elemento", "valor"])
    df["elemento"] = df["elemento"].str.strip()
    df["grandeza"] = df["grandeza"].str.strip().str.lower().str.replace("ã", "a").str.replace("í", "i")
    ruins = set(df["grandeza"]) - set(UN)
    if ruins:
        raise ValueError(f"grandeza desconhecida: {sorted(ruins)} (use pressao, vazao ou nivel)")
    df["hora"] = df["hora"].map(_hora)
    df["valor"] = df["valor"].str.replace(",", ".").astype(float)
    return df[["elemento", "grandeza", "hora", "valor"]].reset_index(drop=True)


def salvar_medicoes(gpkg, df, campanha):
    df = df.assign(campanha=campanha)[["campanha", "elemento", "grandeza", "hora", "valor"]]
    pyogrio.write_dataframe(df, gpkg, layer=T_MED, driver="GPKG")


def ler_medicoes(gpkg):
    if T_MED not in {n for n, _ in pyogrio.list_layers(gpkg)}:
        return pd.DataFrame(columns=["campanha", "elemento", "grandeza", "hora", "valor"])
    return pyogrio.read_dataframe(gpkg, layer=T_MED)


# ------------------------------------------------------------------ modelo x campo
def _serie(res, elemento, grandeza, camada_de):
    """Série simulada (np.array) para o sensor, ou None se o elemento não está no modelo."""
    n, l = res.node, res.link
    if grandeza == "vazao":
        return (l["flowrate"][elemento].abs() * 1000).to_numpy() if elemento in l["flowrate"] else None
    alvo = elemento
    if camada_de.get(elemento) in ("valvula", "bomba"):
        alvo = elemento + "__J"
    return n["pressure"][alvo].to_numpy() if alvo in n["pressure"] else None


def avaliar(res, med, camada_de):
    """Compara modelo x campo; devolve (sensores, residuos_normalizados)."""
    horas = res.node["pressure"].index.to_numpy() / 3600
    sensores, resid = [], []
    for (el, gr), g in med.groupby(["elemento", "grandeza"], sort=False):
        sim = _serie(res, el, gr, camada_de)
        obs_h, obs = g["hora"].to_numpy(float), g["valor"].to_numpy(float)
        s = {"elemento": el, "grandeza": gr, "un": UN[gr], "n": len(g),
             "obs_h": [round(x, 4) for x in obs_h], "obs": [round(x, 3) for x in obs]}
        if sim is None:
            s["erro"] = f"{el} não existe no modelo (ou está desativado)"
            sensores.append(s)
            continue
        mod = np.interp(obs_h, horas, sim)
        err = mod - obs
        tol = np.maximum(TOL["vazao"] * np.abs(obs), TOL_VAZAO_MIN) if gr == "vazao" else np.full(len(obs), TOL[gr])
        dentro = float(np.mean(np.abs(err) <= tol))
        sig = SIGMA[gr] or max(0.05 * float(np.mean(np.abs(obs))), TOL_VAZAO_MIN)
        resid.append(err / sig)
        s.update({"sim_h": [round(x, 4) for x in horas], "sim": [round(float(x), 3) for x in sim],
                  "vies": float(np.mean(err)), "rmse": float(np.sqrt(np.mean(err ** 2))),
                  "max": float(np.max(np.abs(err))), "dentro": dentro, "ok": dentro >= META})
        sensores.append(s)
    return sensores, (np.concatenate(resid) if resid else np.array([]))


def resumo(sensores):
    v = [s for s in sensores if "dentro" in s]
    return {"sensores": len(v), "ajustados": sum(s["ok"] for s in v),
            "dentro_medio": float(np.mean([s["dentro"] for s in v])) if v else None}


# ------------------------------------------------------------------ parâmetros de calibração
def _grupo(valor):
    return valor if isinstance(valor, str) and valor.strip() else "(sem setor)"


def montar_grupos(c, por_c="material", por_d="setor"):
    """Grupos de rugosidade e de demanda a partir do cadastro."""
    tr = c["trecho"]
    tr = tr[tr["situacao"].isin(["EXISTENTE"]) | tr["situacao"].isna()]
    dom = dict(zip(c["dominio_material"]["material"], c["dominio_material"]["rugosidade_hw"]))
    gc = {}
    for _, t in tr.iterrows():
        chave = "todos" if por_c == "unico" else _grupo(t[por_c])
        C = t["rugosidade_hw"] if t["rugosidade_hw"] is not None else dom.get(t["material"], 130)
        gc.setdefault(chave, {"ids": [], "C": []})
        gc[chave]["ids"].append(t["id"])
        gc[chave]["C"].append(float(C))
    gd = {}
    for _, n in c["no_juncao"].iterrows():
        if (n["demanda_base"] or 0) > 0:
            chave = "todos" if por_d == "unico" else _grupo(n["setor"])
            gd.setdefault(chave, {"ids": [], "base": []})
            gd[chave]["ids"].append(n["id"])
            gd[chave]["base"].append(float(n["demanda_base"]))
    return ([{"grupo": k, "ids": v["ids"], "inicial": round(float(np.mean(v["C"])), 1)} for k, v in gc.items()],
            [{"grupo": k, "ids": v["ids"], "base": v["base"], "inicial": 1.0} for k, v in gd.items()])


def alteracoes_de(gc, gd, xc, xd):
    """Parâmetros -> alterações (formato de proposta/cenário)."""
    alts = []
    for g, C in zip(gc, xc):
        alts += [{"camada": "trecho", "id": i, "campo": "rugosidade_hw", "valor": round(float(C), 1)} for i in g["ids"]]
    for g, f in zip(gd, xd):
        alts += [{"camada": "no_juncao", "id": i, "campo": "demanda_base", "valor": round(b * float(f), 4)}
                 for i, b in zip(g["ids"], g["base"])]
    return alts


def _aplicar_direto(c, gc, gd, xc, xd):
    """Mesmo efeito de alteracoes_de, direto nas tabelas (rápido, usado a cada rodada)."""
    c = {k: v.copy() for k, v in c.items()}
    tr, nj = c["trecho"], c["no_juncao"]
    for g, C in zip(gc, xc):
        tr.loc[tr["id"].isin(g["ids"]), "rugosidade_hw"] = float(C)
    for g, f in zip(gd, xd):
        base = dict(zip(g["ids"], g["base"]))
        m = nj["id"].isin(g["ids"])
        nj.loc[m, "demanda_base"] = nj.loc[m, "id"].map(lambda i: base[i] * float(f))
    return c


def _simular(c, com_projetados=False):
    inp, rel = converter(camadas=c, com_projetados=com_projetados)
    if not rel.ok:
        raise ValueError("cadastro com erros: " + "; ".join(rel.erros[:3]))
    return rodar(inp)[0]


# ------------------------------------------------------------------ API do módulo
def comparar(gpkg, med=None, alteracoes=None):
    med = ler_medicoes(gpkg) if med is None else med
    if med.empty:
        raise ValueError("nenhuma medição carregada")
    c = ler_cadastro(gpkg)
    inp, rel = converter(camadas=c, alteracoes=alteracoes)
    if not rel.ok:
        raise ValueError("cadastro com erros: " + "; ".join(rel.erros[:3]))
    camada_de = _camada_de(c)
    sens, _ = avaliar(rodar(inp)[0], med, camada_de)
    return {"sensores": sens, "resumo": resumo(sens)}


def _camada_de(c):
    return {i: cam for cam in ("captacao", "reservatorio", "bomba", "valvula", "no_juncao") for i in c[cam]["id"]}


def calibrar(gpkg, por_c="material", por_d="setor", ajustar_c=True, ajustar_d=True, med=None, progresso=None):
    from scipy.optimize import least_squares

    med = ler_medicoes(gpkg) if med is None else med
    if med.empty:
        raise ValueError("nenhuma medição carregada")
    c0 = ler_cadastro(gpkg)
    camada_de = _camada_de(c0)
    gc, gd = montar_grupos(c0, por_c, por_d)
    if not ajustar_c:
        gc = []
    if not ajustar_d:
        gd = []
    if not gc and not gd:
        raise ValueError("escolha ao menos rugosidade ou demanda para calibrar")
    x0c, x0d = [g["inicial"] for g in gc], [g["inicial"] for g in gd]
    # variáveis normalizadas: C/100 e fator de demanda, para o otimizador ter escalas parecidas
    x0 = np.array([v / 100 for v in x0c] + x0d)
    lo = np.array([LIM_C[0] / 100] * len(gc) + [LIM_F[0]] * len(gd))
    hi = np.array([LIM_C[1] / 100] * len(gc) + [LIM_F[1]] * len(gd))
    x0 = np.clip(x0, lo + 1e-6, hi - 1e-6)
    rodadas = [0]

    def separar(x):
        return x[:len(gc)] * 100, x[len(gc):]

    def residuos(x):
        rodadas[0] += 1
        xc, xd = separar(x)
        try:
            res = _simular(_aplicar_direto(c0, gc, gd, xc, xd))
        except Exception:
            return np.full(n_res, 1e3)  # combinação que o EPANET não resolve: penaliza
        r = avaliar(res, med, camada_de)[1]
        if progresso:
            progresso(rodadas[0], float(np.sum(r ** 2)))
        return r

    antes_sens, r0 = avaliar(_simular(c0), med, camada_de)
    n_res = len(r0)
    if n_res == 0:
        raise ValueError("nenhuma medição corresponde a elementos do modelo")
    sol = least_squares(residuos, x0, bounds=(lo, hi), diff_step=0.01, x_scale="jac", max_nfev=120)
    xc, xd = separar(sol.x)
    depois_sens, r1 = avaliar(_simular(_aplicar_direto(c0, gc, gd, xc, xd)), med, camada_de)

    # sensibilidade: parâmetro que quase não muda o erro é pouco confiável (faltam medições)
    J = sol.jac
    sens_col = np.sqrt((J ** 2).sum(axis=0)) if J is not None else np.zeros(len(sol.x))
    params = []
    for i, (g, ini, fim) in enumerate([(g, g["inicial"], v) for g, v in zip(gc, xc)]):
        params.append({"tipo": "rugosidade", "grupo": g["grupo"], "n": len(g["ids"]), "inicial": ini,
                       "calibrado": round(float(fim), 1), "sensibilidade": float(sens_col[i]),
                       "no_limite": bool(abs(fim - LIM_C[0]) < 0.5 or abs(fim - LIM_C[1]) < 0.5)})
    for j, (g, fim) in enumerate(zip(gd, xd)):
        params.append({"tipo": "demanda", "grupo": g["grupo"], "n": len(g["ids"]), "inicial": 1.0,
                       "calibrado": round(float(fim), 3), "sensibilidade": float(sens_col[len(gc) + j]),
                       "no_limite": bool(abs(fim - LIM_F[0]) < 0.01 or abs(fim - LIM_F[1]) < 0.01)})
    smax = max([p["sensibilidade"] for p in params] + [1e-9])
    for p in params:
        p["identificavel"] = p["sensibilidade"] > 0.02 * smax
    return {
        "parametros": params,
        "antes": {"sensores": antes_sens, "resumo": resumo(antes_sens), "erro": float(np.sum(r0 ** 2))},
        "depois": {"sensores": depois_sens, "resumo": resumo(depois_sens), "erro": float(np.sum(r1 ** 2))},
        "rodadas": rodadas[0],
        "alteracoes": alteracoes_de(gc, gd, xc, xd),
    }


def aplicar_ao_cadastro(gpkg, alteracoes):
    """Grava rugosidade/demanda calibradas no cadastro. Faz cópia de segurança antes."""
    import geopandas as gpd
    backup = gpkg[:-5] + f"_antes_calibracao_{datetime.now():%Y%m%d_%H%M%S}.gpkg"
    shutil.copyfile(gpkg, backup)
    por_camada = {}
    for a in alteracoes:
        if (a["camada"], a["campo"]) not in (("trecho", "rugosidade_hw"), ("no_juncao", "demanda_base")):
            raise ValueError(f"aplicar ao cadastro aceita só rugosidade e demanda (recebido {a['camada']}.{a['campo']})")
        por_camada.setdefault(a["camada"], {}).setdefault(a["campo"], {})[a["id"]] = float(a["valor"])
    for camada, campos in por_camada.items():
        g = gpd.read_file(gpkg, layer=camada)
        for campo, valores in campos.items():
            m = g["id"].isin(valores)
            g.loc[m, campo] = g.loc[m, "id"].map(valores)
        g.to_file(gpkg, layer=camada, driver="GPKG")
    return backup


if __name__ == "__main__":
    import sys
    from cadastro_para_inp import GPKG_PADRAO
    r = comparar(sys.argv[1] if len(sys.argv) > 1 else GPKG_PADRAO)
    for s in r["sensores"]:
        print(s["elemento"], s["grandeza"], s.get("erro") or f"rmse {s['rmse']:.2f} {s['un']} · {s['dentro']:.0%} dentro")
