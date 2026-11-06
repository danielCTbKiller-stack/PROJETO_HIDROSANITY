"""Simulação em período estendido do consumo do prédio.

A cada passo de tempo:
  * consumo do prédio = população × consumo per capita × fator da curva horária (média 1);
  * o reservatório recebe a alimentação (rede pública / recalque) até encher (boia) e entrega o consumo;
    se esvaziar, o consumo não atendido vira déficit;
  * a rede é calculada com a pressão na saída igual à lâmina d'água no reservatório e as vazões
    prováveis escaladas pelo fator da hora em relação à hora de pico (pico = vazão provável da NBR 5626).

É um modelo de balanço de volume + verificação hidráulica por instante: serve para dimensionar a
reservação, ver a que horas o reservatório fica baixo e como a pressão nos pontos varia ao longo do dia.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from services.network_analyzer import NetworkAnalyzer
from services.project_manager import ProjectManager

# Curvas de consumo horário típicas (fator multiplicador da média, 0 h a 23 h)
PATTERNS = {
    "Residencial": [0.45, 0.35, 0.30, 0.30, 0.35, 0.60, 1.20, 1.75, 1.55, 1.20, 1.10, 1.20,
                    1.35, 1.15, 0.95, 0.90, 1.00, 1.20, 1.55, 1.70, 1.45, 1.10, 0.80, 0.55],
    "Comercial":   [0.10, 0.10, 0.10, 0.10, 0.10, 0.20, 0.60, 1.40, 2.00, 2.00, 1.90, 1.80,
                    1.60, 1.80, 1.90, 1.90, 1.80, 1.50, 1.00, 0.50, 0.30, 0.20, 0.15, 0.10],
    "Constante":   [1.0] * 24,
}


def normalized(pattern):
    m = sum(pattern) / len(pattern)
    return [v / m for v in pattern] if m > 0 else [1.0] * len(pattern)


@dataclass
class EPSConfig:
    population: int = 32
    per_capita_lpd: float = 200.0
    pattern: List[float] = field(default_factory=lambda: list(PATTERNS["Residencial"]))
    duration_h: float = 48.0
    step_min: float = 30.0
    reservoir_m3: float = 10.0
    reservoir_height_m: float = 1.5     # lâmina d'água com o reservatório cheio (pressão na saída)
    initial_level: float = 1.0          # 0..1
    inflow_m3h: float = 0.8             # alimentação máxima (rede pública ou recalque)
    cut_start_h: float = -1.0           # falta d'água na alimentação: das cut_start_h às cut_end_h (-1 = sem falta)
    cut_end_h: float = -1.0
    max_velocity: float = 3.0
    auto_fittings: bool = True

    @property
    def daily_m3(self):
        return self.population * self.per_capita_lpd / 1000.0


def supply_cut(cfg: EPSConfig, t_h: float) -> bool:
    if cfg.cut_start_h < 0 or cfg.cut_end_h < 0:
        return False
    h = t_h % 24
    a, b = cfg.cut_start_h % 24, cfg.cut_end_h % 24
    return a <= h < b if a <= b else (h >= a or h < b)


def default_config(project: ProjectManager) -> EPSConfig:
    """Valores iniciais a partir do modelo: 4 pessoas por pavimento com aparelhos."""
    floors = {project.floor_index(n.elevation_m) for n in project.nodes.values() if n.fixtures}
    cfg = EPSConfig(population=max(4, 4 * len(floors)))
    cfg.reservoir_m3 = round(max(1.0, cfg.daily_m3 * 1.0), 1)      # reserva de 1 dia (NBR 5626, mínimo)
    cfg.inflow_m3h = round(max(0.1, cfg.daily_m3 / 20.0), 2)       # repõe o dia em 20 h
    return cfg


def simulate(project: ProjectManager, source_id: str, cfg: EPSConfig) -> dict:
    pattern = normalized(cfg.pattern)
    peak = max(pattern)
    dt_h = cfg.step_min / 60.0
    n_steps = int(round(cfg.duration_h / dt_h)) + 1
    vol = cfg.reservoir_m3 * max(0.0, min(1.0, cfg.initial_level))
    analyzer = NetworkAnalyzer(project)
    steps = []
    for k in range(n_steps):
        t = k * dt_h
        f = pattern[int(t) % 24]
        demand = cfg.daily_m3 / 24.0 * f                      # m³/h
        # balanço do passo: alimentação até encher, consumo saindo
        room = cfg.reservoir_m3 - vol
        inflow = min(cfg.inflow_m3h, room / dt_h + demand) if k else 0.0
        if supply_cut(cfg, t):
            inflow = 0.0
        available = vol + inflow * dt_h
        supplied = min(demand, available / dt_h) if k else demand
        if k:
            vol = max(0.0, min(cfg.reservoir_m3, vol + (inflow - supplied) * dt_h))
        level = vol / cfg.reservoir_m3 if cfg.reservoir_m3 > 0 else 0.0
        empty = level <= 1e-6 and supplied < demand - 1e-9
        depth = level * cfg.reservoir_height_m
        factor = 0.0 if empty else f / peak
        result: Optional[dict] = None
        try:
            result = analyzer.analyze(source_id, depth, False, cfg.max_velocity, auto_fittings=cfg.auto_fittings,
                                      flow_factor=factor)
        except ValueError:
            result = None
        fx = [(nid, r) for nid, r in (result or {}).get("nodes", {}).items()
              if project.nodes[nid].fixtures]
        p_min = min(fx, key=lambda t: t[1]["pressure_mca"]) if fx else (None, None)
        p_max = max(fx, key=lambda t: t[1]["pressure_mca"]) if fx else (None, None)
        q_src = 0.0
        if result:
            for p in project.pipes.values():
                if source_id in (p.start_node_id, p.end_node_id) and p.id in result["pipes"]:
                    q_src += result["pipes"][p.id]["flow_lps"]
        steps.append({
            "t_h": t, "factor": factor, "demand_m3h": demand, "supplied_m3h": supplied, "inflow_m3h": inflow,
            "deficit_m3h": max(0.0, demand - supplied), "volume_m3": vol, "level": level, "empty": empty,
            "depth_m": depth, "q_source_lps": q_src,
            "p_min": p_min[1]["pressure_mca"] if p_min[1] else None, "p_min_node": p_min[0],
            "p_max": p_max[1]["pressure_mca"] if p_max[1] else None, "p_max_node": p_max[0],
            "n_low": sum(1 for _, r in fx if not r["ok"]) if not empty else len(fx),
            "result": result,
        })
    run = steps[1:] or steps
    lowest = min(steps, key=lambda s: s["level"])
    worst = min((s for s in steps if s["p_min"] is not None), key=lambda s: s["p_min"], default=None)
    peak_step = max(steps, key=lambda s: s["demand_m3h"])
    summary = {
        "daily_m3": cfg.daily_m3,
        "consumed_m3": sum(s["supplied_m3h"] for s in run) * dt_h,
        "deficit_m3": sum(s["deficit_m3h"] for s in run) * dt_h,
        "hours_empty": sum(dt_h for s in run if s["empty"]),
        "min_level": lowest["level"], "min_level_t": lowest["t_h"],
        "peak_demand_m3h": peak_step["demand_m3h"], "peak_t": peak_step["t_h"],
        "worst_p": worst["p_min"] if worst else None, "worst_p_t": worst["t_h"] if worst else None,
        "worst_p_node": worst["p_min_node"] if worst else None,
        "reserve_days": cfg.reservoir_m3 / cfg.daily_m3 if cfg.daily_m3 else 0.0,
    }
    return {"steps": steps, "summary": summary, "dt_h": dt_h}
