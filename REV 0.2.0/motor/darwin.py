"""Calibração como o Darwin Calibrator do WaterGEMS.

Estudo de calibração:
  momentos     dados de campo de um instante (Field Data Snapshot): hora do dia, fator de demanda do momento,
               condições de contorno (nível de reservatório, status e ajuste de bomba/válvula) e as leituras
               observadas (pressão, carga, vazão ou nível) com peso
  grupos_c     grupos de rugosidade (Roughness Groups): tubulações, faixa (mín, máx) e modo
               (valor: C novo para todas; multiplicador: C de cada uma × fator)
  grupos_d     grupos de demanda (Demand Groups): nós e faixa do multiplicador
  status       elementos de status desconhecido (Status Groups): ABERTA ou FECHADA
  objetivo     soma dos quadrados, soma dos absolutos ou maior diferença (Fitness Type), com
               "mca por ponto de aptidão" e "L/s por ponto de aptidão"
  metodo       genetico (evolução diferencial, busca global como o algoritmo genético do Darwin) ou
               gradiente (mínimos quadrados, rápido; só para soma dos quadrados e sem status)

Cada momento é o modelo congelado naquela hora (demandas, níveis e bombas da simulação de 24 h, com as
condições de contorno informadas por cima) e resolvido direto na biblioteca do EPANET: milhares de
avaliações em segundos.
"""
import math
import os

import numpy as np
from wntr.epanet.util import EN

from analises import ErroModelo, Modelo, Rapido, _r  # noqa: F401  (ErroModelo: a ponte do cli trata)

GRANDEZAS = {"pressao": "mca", "carga": "m", "vazao": "L/s", "nivel": "m"}
OBJETIVOS = ("quadrados", "absoluto", "maximo")


class Estudo:
    """Momentos prontos para avaliar: um Rapido por momento, com os valores de base guardados."""

    def __init__(self, m, momentos, grupos_c, grupos_d, status, nomes=None):
        """m: o Modelo (no processo principal); nos processos de cálculo em paralelo vem None, com os momentos já
        congelados (mo["arq"]) e `nomes` = (tubos, nós de consumo)."""
        self.m = m
        self.momentos, self.grupos_c, self.grupos_d, self.status = momentos, grupos_c, grupos_d, status
        tubos, juncs = (set(nomes[0]), set(nomes[1])) if nomes else (set(m.wn.pipe_name_list), set(m.consumo))
        self.nomes = (sorted(tubos), sorted(juncs))
        if m is not None and len(momentos) > 1:
            m.res  # vários momentos: o dia inteiro uma vez só, em vez de uma simulação até cada hora
        for g in grupos_c:
            g["ids"] = [i for i in g["ids"] if i in tubos]
        for g in grupos_d:
            g["ids"] = [i for i in g["ids"] if i in juncs]
        self.R, self.base_c, self.base_d, self.obs = [], {}, [], []
        for k, mo in enumerate(momentos):
            if mo.get("arq"):
                arq, t = mo["arq"], mo["t"]
            else:
                arq, t = m.instante(float(mo["hora"]) * 3600 if mo.get("hora") not in (None, "") else None, dda=False)
                mo["arq"], mo["t"] = arq, t
            R = Rapido(arq)
            self.R.append(R)
            fd = float(mo.get("fator_demanda") or 1)
            self.base_d.append({n: R.no_valor(n, EN.BASEDEMAND) * fd for n in juncs})
            for c in mo.get("contorno", []):  # condições de contorno do momento, por cima do modelo
                self._contorno(R, c, mo["nome"])
            for o in mo.get("observacoes", []):
                gr, el = o["grandeza"], str(o["elemento"])
                alvo = el + "__J" if gr in ("pressao", "carga") and el + "__J" in R.no else el
                ok = (alvo in R.link) if gr == "vazao" else (alvo in R.no)
                self.obs.append({"momento": mo["nome"], "k": k, "elemento": el, "alvo": alvo, "grandeza": gr,
                                 "valor": float(o["valor"]), "peso": float(o.get("peso") or 1), "ok": ok})
        if not self.R:
            raise ValueError("nenhum momento de medição")
        R0 = self.R[0]
        for g in grupos_c:
            for i in g["ids"]:
                self.base_c[i] = R0.link_valor(i, EN.ROUGHNESS)
        sem = [o["elemento"] for o in self.obs if not o["ok"]]
        if sem:
            raise ValueError(f"elementos medidos que não estão no modelo: {', '.join(sorted(set(sem))[:8])}")
        if not self.obs:
            raise ValueError("nenhuma leitura de campo nos momentos")

    @staticmethod
    def _contorno(R, c, nome):
        el, at, v = str(c["elemento"]), str(c["atributo"]).upper(), c["valor"]
        try:
            if at == "NIVEL":
                R.mudar_no(el, EN.TANKLEVEL, float(v))
            elif at == "STATUS":
                R.mudar_link(el, EN.INITSTATUS, 0 if str(v).upper().startswith("FECH") else 1)
            elif at == "AJUSTE":
                R.mudar_link(el, EN.INITSETTING, float(str(v).replace(",", ".")))
            elif at == "CARGA":
                R.mudar_no(el, EN.ELEVATION, float(v))
        except KeyError:
            raise ValueError(f"momento {nome}: condição de contorno em '{el}', que não está no modelo")

    def n_var(self):
        return len(self.grupos_c) + len(self.grupos_d) + len(self.status)

    def limites(self):
        lo = [g["min"] for g in self.grupos_c] + [g["min"] for g in self.grupos_d] + [0.0] * len(self.status)
        hi = [g["max"] for g in self.grupos_c] + [g["max"] for g in self.grupos_d] + [1.999] * len(self.status)
        return np.array(lo, float), np.array(hi, float)

    def inicial(self):
        x = []
        for g in self.grupos_c:
            if g.get("modo") == "multiplicador":
                x.append(1.0)
            else:
                cs = [self.base_c[i] for i in g["ids"]] or [100.0]
                x.append(float(np.mean(cs)))
        x += [1.0] * len(self.grupos_d)
        x += [1.0] * len(self.status)
        lo, hi = self.limites()
        return np.clip(np.array(x, float), lo, hi)

    def aplicar(self, x):
        nc, nd = len(self.grupos_c), len(self.grupos_d)
        for R, base_d in zip(self.R, self.base_d):
            for g, v in zip(self.grupos_c, x[:nc]):
                for i in g["ids"]:
                    R.mudar_link(i, EN.ROUGHNESS, v * self.base_c[i] if g.get("modo") == "multiplicador" else v)
            mult = {}
            for g, v in zip(self.grupos_d, x[nc:nc + nd]):
                for n in g["ids"]:
                    mult[n] = v
            for n, b in base_d.items():
                R.mudar_no(n, EN.BASEDEMAND, b * mult.get(n, 1.0))
            for s, v in zip(self.status, x[nc + nd:]):
                aberto = 1 if s["opcoes"][min(int(v), len(s["opcoes"]) - 1)] == "ABERTA" else 0
                R.mudar_link(s["elemento"], EN.INITSTATUS, aberto)

    def simulados(self, x):
        """Valor simulado de cada leitura (None se o EPANET não resolveu o momento)."""
        self.aplicar(x)
        ok = [R.resolver() for R in self.R]
        out = []
        for o in self.obs:
            R = self.R[o["k"]]
            if not ok[o["k"]]:
                out.append(None)
            elif o["grandeza"] == "vazao":
                out.append(abs(R.link_valor(o["alvo"], EN.FLOW)))
            elif o["grandeza"] == "carga":
                out.append(R.no_valor(o["alvo"], EN.HEAD))
            elif o["grandeza"] == "nivel":
                out.append(R.no_valor(o["alvo"], EN.PRESSURE))
            else:
                out.append(R.no_valor(o["alvo"], EN.PRESSURE))
        return out

    def residuos(self, x, mca, lps):
        """Diferença de cada leitura em pontos de aptidão (Darwin: mca ou L/s por ponto), já com o peso."""
        sim = self.simulados(x)
        r = []
        for o, s in zip(self.obs, sim):
            esc = lps if o["grandeza"] == "vazao" else mca
            r.append(1e3 if s is None else (s - o["valor"]) / esc * o["peso"])
        return np.array(r)

    def fechar(self):
        for R in self.R:
            R.fechar()


class Avaliador:
    """Aptidão de uma solução, para os processos de cálculo em paralelo: cada processo monta o seu Estudo (o EPANET
    aberto em cada momento) na primeira chamada e reaproveita nas seguintes."""

    def __init__(self, momentos, grupos_c, grupos_d, status, nomes, mca, lps, objetivo):
        self.args = (momentos, grupos_c, grupos_d, status, nomes)
        self.mca, self.lps, self.objetivo = mca, lps, objetivo
        self.e = None

    def __getstate__(self):
        return {**self.__dict__, "e": None}

    def __call__(self, x):
        if self.e is None:
            mo, gc, gd, st, nomes = self.args
            self.e = Estudo(None, [dict(m) for m in mo], [dict(g) for g in gc], [dict(g) for g in gd],
                            [dict(s) for s in st], nomes)
        return aptidao(self.e.residuos(np.asarray(x, float), self.mca, self.lps), self.objetivo)


def aptidao(r, objetivo):
    if objetivo == "absoluto":
        return float(np.sum(np.abs(r)))
    if objetivo == "maximo":
        return float(np.max(np.abs(r))) if len(r) else 0.0
    return float(np.sum(r ** 2))


def calibrar(gpkg, momentos, grupos_c=(), grupos_d=(), status=(), objetivo="quadrados", mca_por_ponto=1.0,
             lps_por_ponto=1.0, metodo="genetico", max_avaliacoes=2000, solucoes=3, com_projetados=False,
             alteracoes=None, semente=1):
    """Roda o estudo de calibração; devolve as melhores soluções e a comparação antes × depois."""
    from scipy.optimize import differential_evolution, least_squares
    grupos_c, grupos_d, status = [dict(g) for g in grupos_c], [dict(g) for g in grupos_d], [dict(s) for s in status]
    if not grupos_c and not grupos_d and not status:
        raise ValueError("escolha ao menos um grupo de ajuste (rugosidade, demanda ou status)")
    m = Modelo(gpkg, com_projetados, alteracoes)
    try:
        e = Estudo(m, [dict(mo) for mo in momentos], grupos_c, grupos_d, status)
        try:
            lo, hi = e.limites()
            x0 = e.inicial()
            r0 = e.residuos(x0, mca_por_ponto, lps_por_ponto)
            visto = []  # (aptidão, x) de cada avaliação, para as N melhores soluções diferentes

            def f(x):
                r = e.residuos(np.asarray(x, float), mca_por_ponto, lps_por_ponto)
                a = aptidao(r, objetivo)
                visto.append((a, np.array(x, float)))
                return a
            if metodo == "gradiente" and objetivo == "quadrados" and not status:
                def fr(x):
                    r = e.residuos(np.asarray(x, float), mca_por_ponto, lps_por_ponto)
                    visto.append((aptidao(r, objetivo), np.array(x, float)))
                    return r
                least_squares(fr, x0, bounds=(lo, hi), diff_step=0.01, x_scale="jac",
                              max_nfev=max(20, int(max_avaliacoes) // max(1, len(x0))))
                usado = "gradiente"
            else:
                n = len(x0)
                pop = 15
                geracoes = max(5, int(max_avaliacoes) // (pop * n) - 1)
                from analises import nucleos
                nuc = nucleos()
                pesado = len(e.nomes[0]) * len(e.momentos) > int(os.environ.get("GWATER_PESADO", "3000"))  # rede grande
                if nuc > 1 and pesado:
                    av = Avaliador(e.momentos, e.grupos_c, e.grupos_d, e.status, e.nomes, mca_por_ponto,
                                   lps_por_ponto, objetivo)
                    sol = differential_evolution(av, list(zip(lo, hi)), x0=x0, popsize=pop, maxiter=geracoes,
                                                 seed=semente, tol=1e-7, polish=False, init="sobol",
                                                 updating="deferred", workers=nuc)
                    visto += [(float(a), np.array(x, float)) for a, x in zip(sol.population_energies, sol.population)]
                    visto.append((float(sol.fun), np.array(sol.x, float)))
                    visto.append((f(x0), np.array(x0, float)))
                    for _ in range(int(sol.nfev)):  # conta as avaliações feitas nos outros processos
                        visto.append((math.inf, x0))
                    usado = f"genetico ({nuc} núcleos)"
                else:
                    differential_evolution(f, list(zip(lo, hi)), x0=x0, popsize=pop, maxiter=geracoes, seed=semente,
                                           tol=1e-7, polish=False, init="sobol", updating="immediate")
                    usado = "genetico"
            visto.sort(key=lambda t: t[0])
            melhores = []
            escala = np.maximum(hi - lo, 1e-9)
            for a, x in visto:  # soluções diferentes entre si (> 2% da faixa em algum parâmetro)
                if not math.isfinite(a):
                    continue
                if all(np.max(np.abs(x - y) / escala) > 0.02 for _, y in melhores):
                    melhores.append((a, x))
                if len(melhores) >= max(1, int(solucoes)):
                    break
            sim0 = e.simulados(x0)
            sols = []
            for a, x in melhores:
                sim = e.simulados(x)
                sols.append({"aptidao": _r(a, 4), "parametros": _parametros(e, x0, x),
                             "leituras": _leituras(e, sim0, sim), "alteracoes": _alteracoes(e, x),
                             "indicadores": _indicadores(e, sim)})
            return {"ok": True, "metodo": usado, "avaliacoes": len(visto), "objetivo": objetivo,
                    "aptidao_inicial": _r(aptidao(r0, objetivo), 4), "indicadores_inicial": _indicadores(e, sim0),
                    "solucoes": sols}
        finally:
            e.fechar()
    finally:
        m.fechar()


def _parametros(e, x0, x):
    out = []
    nc, nd = len(e.grupos_c), len(e.grupos_d)
    for g, a, b in zip(e.grupos_c, x0[:nc], x[:nc]):
        out.append({"tipo": "rugosidade", "grupo": g["nome"], "n": len(g["ids"]), "modo": g.get("modo", "valor"),
                    "inicial": _r(a, 3), "calibrado": _r(b, 3 if g.get("modo") == "multiplicador" else 1),
                    "no_limite": bool(min(abs(b - g["min"]), abs(b - g["max"])) < 0.005 * (g["max"] - g["min"]))})
    for g, b in zip(e.grupos_d, x[nc:nc + nd]):
        out.append({"tipo": "demanda", "grupo": g["nome"], "n": len(g["ids"]), "modo": "multiplicador",
                    "inicial": 1.0, "calibrado": _r(b, 3),
                    "no_limite": bool(min(abs(b - g["min"]), abs(b - g["max"])) < 0.005 * (g["max"] - g["min"]))})
    for s, v in zip(e.status, x[nc + nd:]):
        out.append({"tipo": "status", "grupo": s["elemento"], "n": 1, "modo": "status", "inicial": None,
                    "calibrado": s["opcoes"][min(int(v), len(s["opcoes"]) - 1)], "no_limite": False})
    return out


def _leituras(e, antes, depois):
    out = []
    for o, a, b in zip(e.obs, antes, depois):
        out.append({"momento": o["momento"], "elemento": o["elemento"], "grandeza": o["grandeza"],
                    "un": GRANDEZAS[o["grandeza"]], "observado": _r(o["valor"], 3), "antes": _r(a, 3),
                    "depois": _r(b, 3), "dif_antes": _r(None if a is None else a - o["valor"], 3),
                    "dif_depois": _r(None if b is None else b - o["valor"], 3)})
    return out


def _indicadores(e, sim):
    """Erro médio absoluto e maior diferença por grandeza, e o ajuste (R²) observado × simulado."""
    out = {}
    for gr in GRANDEZAS:
        pares = [(o["valor"], s) for o, s in zip(e.obs, sim) if o["grandeza"] == gr and s is not None]
        if not pares:
            continue
        ob, si = np.array([p[0] for p in pares]), np.array([p[1] for p in pares])
        dif = si - ob
        r2 = 1 - np.sum(dif ** 2) / np.sum((ob - ob.mean()) ** 2) if len(ob) > 1 and np.ptp(ob) > 0 else None
        out[gr] = {"n": len(pares), "erro_medio": _r(float(np.mean(np.abs(dif))), 3),
                   "maior": _r(float(np.max(np.abs(dif))), 3), "r2": _r(r2, 3)}
    return out


def _alteracoes(e, x):
    """Solução → alterações de cenário (rugosidade de cada tubulação, demanda de cada nó, status)."""
    alts = []
    nc, nd = len(e.grupos_c), len(e.grupos_d)
    for g, v in zip(e.grupos_c, x[:nc]):
        for i in g["ids"]:
            c = v * e.base_c[i] if g.get("modo") == "multiplicador" else v
            alts.append({"camada": "trecho", "id": i, "campo": "rugosidade_hw", "valor": round(float(c), 1)})
    base = {}
    for col in e.m.c["no_juncao"][["id", "demanda_base"]].itertuples(index=False):
        base[str(col[0])] = float(col[1] or 0)
    for g, v in zip(e.grupos_d, x[nc:nc + nd]):
        for n in g["ids"]:
            if base.get(n):
                alts.append({"camada": "no_juncao", "id": n, "campo": "demanda_base",
                             "valor": round(base[n] * float(v), 5)})
    for s, v in zip(e.status, x[nc + nd:]):
        op = s["opcoes"][min(int(v), len(s["opcoes"]) - 1)]
        cam = "bomba" if s["elemento"] in set(e.m.c["bomba"]["id"]) else \
            ("valvula" if s["elemento"] in set(e.m.c["valvula"]["id"]) else "trecho")
        campo = {"bomba": "status_inicial", "valvula": "status", "trecho": "status"}[cam]
        valor = op if cam != "trecho" else ("ABERTO" if op == "ABERTA" else "FECHADO")
        alts.append({"camada": cam, "id": s["elemento"], "campo": campo, "valor": valor})
    return alts


if __name__ == "__main__":  # rede de exemplo: C "verdadeiro" diferente, medido e recuperado
    import sys
    from cadastro_para_inp import GPKG_PADRAO
    print(math.pi, sys.argv[1:] or GPKG_PADRAO)
