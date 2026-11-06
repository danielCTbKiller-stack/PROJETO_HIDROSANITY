"""Calibração da rede predial, como o Darwin Calibrator do WaterGEMS (e o calibrador do GWATER, em
GWATER/REV 0.2.0/motor/darwin.py), adaptada ao cálculo da NBR 5626.

Estudo de calibração:
  momentos     dados de campo de um instante (Field Data Snapshot): fator de demanda do momento (vazão
               provável × fator), pressão na saída do reservatório (condição de contorno) e as leituras
               observadas (pressão em nó, vazão em trecho) com peso
  grupos_c     grupos de rugosidade (Roughness Groups): trechos e faixa (mín, máx) do multiplicador da
               perda de carga (1 = tubo novo; tubo velho/incrustado > 1)
  grupos_d     grupos de demanda (Demand Groups): nós e faixa do multiplicador dos pesos dos aparelhos
  objetivo     soma dos quadrados, soma dos absolutos ou maior diferença (Fitness Type), com
               "mca por ponto de aptidão" e "L/s por ponto de aptidão"
  metodo       genetico (evolução diferencial do SciPy, busca global da família do algoritmo genético do
               Darwin) ou gradiente (mínimos quadrados, rápido; só para soma dos quadrados)

Cada avaliação é um cálculo completo da rede (árvore), sem alterar o projeto; `aplicar` grava a solução.
"""
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import numpy as np

from services.network_analyzer import NetworkAnalyzer
from services.project_manager import ProjectManager

GRANDEZAS = {"pressao": "mca", "vazao": "L/s"}
OBJETIVOS = ("quadrados", "absoluto", "maximo")


@dataclass
class Leitura:
    elemento: str          # id do nó (pressão) ou do trecho (vazão)
    grandeza: str          # "pressao" | "vazao"
    valor: float
    peso: float = 1.0


@dataclass
class Momento:
    nome: str
    fator_demanda: float = 1.0
    pressao_fonte_mca: Optional[float] = None   # None = a do projeto
    leituras: List[Leitura] = field(default_factory=list)


@dataclass
class Grupo:
    nome: str
    ids: List[str]
    min: float = 0.5
    max: float = 3.0


@dataclass
class Estudo:
    momentos: List[Momento]
    grupos_c: List[Grupo] = field(default_factory=list)
    grupos_d: List[Grupo] = field(default_factory=list)
    objetivo: str = "quadrados"
    mca_por_ponto: float = 1.0
    lps_por_ponto: float = 0.1
    metodo: str = "genetico"
    geracoes: int = 60
    populacao: int = 15
    semente: Optional[int] = 1
    n_solucoes: int = 5


# ----------------------------------------------------------------------------- grupos sugeridos
def grupos_por_material(project: ProjectManager) -> List[Grupo]:
    por: Dict[str, List[str]] = {}
    for p in project.pipes.values():
        por.setdefault(p.material, []).append(p.id)
    return [Grupo(f"Rugosidade · {m}", ids) for m, ids in sorted(por.items())]


def _andar(project, nid):
    return project.floor_index(project.nodes[nid].elevation_m)


def grupos_por_pavimento(project: ProjectManager, demanda=False) -> List[Grupo]:
    """Rugosidade: trechos cujo nó de jusante está no pavimento. Demanda: nós com aparelhos."""
    por: Dict[int, List[str]] = {}
    if demanda:
        for n in project.nodes.values():
            if n.fixtures:
                por.setdefault(_andar(project, n.id), []).append(n.id)
    else:
        for p in project.pipes.values():
            por.setdefault(min(_andar(project, p.start_node_id), _andar(project, p.end_node_id)), []).append(p.id)
    nome = lambda i: project.floors[i].name if i < len(project.floors) else f"Pav. {i}"
    rot = "Demanda" if demanda else "Rugosidade"
    lo, hi = (0.3, 2.0) if demanda else (0.5, 3.0)
    return [Grupo(f"{rot} · {nome(i)}", ids, lo, hi) for i, ids in sorted(por.items())]


# ----------------------------------------------------------------------------- avaliação
class Calibrador:
    def __init__(self, project: ProjectManager, source_id: str, source_pressure_mca: float,
                 estudo: Estudo, auto_fittings: bool = True):
        self.project, self.source, self.p0, self.e = project, source_id, source_pressure_mca, estudo
        self.auto_fittings = auto_fittings
        if estudo.objetivo not in OBJETIVOS:
            raise ValueError(f"objetivo desconhecido: {estudo.objetivo}")
        if not estudo.momentos:
            raise ValueError("nenhum momento de medição")
        obs = [(k, l) for k, m in enumerate(estudo.momentos) for l in m.leituras]
        if not obs:
            raise ValueError("nenhuma leitura de campo nos momentos")
        sem = sorted({l.elemento for _, l in obs
                      if l.elemento not in (project.nodes if l.grandeza == "pressao" else project.pipes)})
        if sem:
            raise ValueError(f"elementos medidos que não estão no modelo: {', '.join(sem[:8])}")
        for g in estudo.grupos_c:
            g.ids = [i for i in g.ids if i in project.pipes]
        for g in estudo.grupos_d:
            g.ids = [i for i in g.ids if i in project.nodes]
        if not estudo.grupos_c and not estudo.grupos_d:
            raise ValueError("escolha ao menos um grupo de rugosidade ou de demanda")
        self.obs = obs
        self.base_c = {pid: p.roughness_factor for pid, p in project.pipes.items()}
        self.avaliacoes = 0

    def n_var(self):
        return len(self.e.grupos_c) + len(self.e.grupos_d)

    def limites(self):
        gs = self.e.grupos_c + self.e.grupos_d
        return np.array([g.min for g in gs], float), np.array([g.max for g in gs], float)

    def inicial(self):
        lo, hi = self.limites()
        return np.clip(np.ones(self.n_var()), lo, hi)

    def simular(self, x):
        """Resultados de cada momento com a solução x (sem alterar o projeto ao final)."""
        nc = len(self.e.grupos_c)
        fator = {}
        for g, v in zip(self.e.grupos_c, x[:nc]):
            for i in g.ids:
                fator[i] = v
        wf = {}
        for g, v in zip(self.e.grupos_d, x[nc:]):
            for i in g.ids:
                wf[i] = float(v)
        pipes = self.project.pipes
        try:
            for pid, p in pipes.items():
                p.roughness_factor = self.base_c[pid] * fator.get(pid, 1.0)
            an = NetworkAnalyzer(self.project)
            out = []
            for m in self.e.momentos:
                p0 = self.p0 if m.pressao_fonte_mca is None else m.pressao_fonte_mca
                out.append(an.analyze(self.source, p0, auto_fittings=self.auto_fittings,
                                      flow_factor=m.fator_demanda, weight_factor=wf))
        finally:
            for pid, p in pipes.items():
                p.roughness_factor = self.base_c[pid]
        self.avaliacoes += 1
        return out

    def residuos(self, x, res=None):
        """Diferença simulado − observado, em pontos de aptidão, já com o peso."""
        res = res or self.simular(x)
        r = []
        for k, l in self.obs:
            if l.grandeza == "pressao":
                sim, esc = res[k]["nodes"][l.elemento]["pressure_mca"], self.e.mca_por_ponto
            else:
                sim, esc = res[k]["pipes"][l.elemento]["flow_lps"], self.e.lps_por_ponto
            r.append((sim - l.valor) / esc * l.peso)
        return np.array(r, float)

    def aptidao(self, x):
        r = self.residuos(x)
        if self.e.objetivo == "quadrados":
            return float(np.sum(r * r))
        if self.e.objetivo == "absoluto":
            return float(np.sum(np.abs(r)))
        return float(np.max(np.abs(r)))

    def tabela(self, x):
        """Uma linha por leitura: observado, simulado, diferença."""
        res = self.simular(x)
        linhas = []
        for k, l in self.obs:
            if l.grandeza == "pressao":
                sim = res[k]["nodes"][l.elemento]["pressure_mca"]
            else:
                sim = res[k]["pipes"][l.elemento]["flow_lps"]
            linhas.append({"momento": self.e.momentos[k].nome, "elemento": l.elemento, "grandeza": l.grandeza,
                           "unidade": GRANDEZAS[l.grandeza], "observado": l.valor, "simulado": sim,
                           "diferenca": sim - l.valor})
        return linhas

    # ------------------------------------------------------------------------- otimização
    def rodar(self, progresso=None):
        """Devolve {"solucoes": [{"x", "aptidao", "grupos"}...] (melhor primeiro), "inicial", "avaliacoes"}."""
        from scipy.optimize import differential_evolution, least_squares

        lo, hi = self.limites()
        x0 = self.inicial()
        apt0 = self.aptidao(x0)
        vistos = []  # (aptidão, x) de todas as avaliações, para as melhores soluções distintas

        def f(x):
            a = self.aptidao(x)
            vistos.append((a, np.array(x, float)))
            return a

        if self.e.metodo == "gradiente":
            if self.e.objetivo != "quadrados":
                raise ValueError("o método gradiente só trabalha com soma dos quadrados")
            r = least_squares(lambda x: self.residuos(x), x0, bounds=(lo, hi))
            vistos.append((self.aptidao(r.x), r.x))
        else:
            def cb(xk, convergence=None):
                if progresso:
                    return bool(progresso(len(vistos), min(a for a, _ in vistos)))
                return False
            differential_evolution(f, list(zip(lo, hi)), maxiter=self.e.geracoes, popsize=self.e.populacao,
                                   seed=self.e.semente, tol=1e-7, polish=True, callback=cb, updating="immediate")

        vistos.sort(key=lambda t: t[0])
        sols = []
        for a, x in vistos:
            if all(np.max(np.abs(x - s["x"]) / np.maximum(hi - lo, 1e-9)) > 0.02 for s in sols):
                sols.append({"x": x, "aptidao": a})
            if len(sols) >= self.e.n_solucoes:
                break
        nomes = [g.nome for g in self.e.grupos_c + self.e.grupos_d]
        for s in sols:
            s["grupos"] = dict(zip(nomes, (float(v) for v in s["x"])))
        return {"solucoes": sols, "inicial": apt0, "avaliacoes": self.avaliacoes}

    def aplicar(self, x):
        """Grava a solução no projeto: rugosidade nos trechos e multiplicador de peso nos aparelhos."""
        nc = len(self.e.grupos_c)
        for g, v in zip(self.e.grupos_c, x[:nc]):
            for i in g.ids:
                p = self.project.pipes[i]
                p.roughness_factor = self.base_c[i] * float(v)
        for g, v in zip(self.e.grupos_d, x[nc:]):
            for i in g.ids:
                n = self.project.nodes[i]  # cópias: o mesmo aparelho pode estar em vários nós
                n.fixtures = [replace(fx, weight=fx.weight * float(v)) for fx in n.fixtures]
        self.base_c = {pid: p.roughness_factor for pid, p in self.project.pipes.items()}
