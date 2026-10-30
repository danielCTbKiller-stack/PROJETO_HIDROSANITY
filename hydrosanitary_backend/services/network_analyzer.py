from collections import deque
from typing import Dict, Iterable, List, Optional

from core.entities import Pipe
from dataclasses import replace

from engine.hydraulic_calculator import HydraulicCalculator
from engine.sizing import select_diameter
from core.standards import GEOMETRIC_FITTINGS
from engine.validator import HydraulicValidator
from services.fittings import detect_fittings, fittings_equivalent_length
from services.project_manager import ProjectManager


class NetworkAnalyzer:
    """Analisa uma rede ramificada de água fria: vazões, dimensionamento e pressões."""

    def __init__(self, project: ProjectManager):
        self.project = project

    def _build_tree(self, source_id: str):
        """Orienta os trechos a partir da fonte. Retorna (filhos por nó, trecho que chega em cada nó)."""
        if source_id not in self.project.nodes:
            raise ValueError(f"Nó de origem '{source_id}' não existe no projeto.")

        adjacency: Dict[str, List[Pipe]] = {}
        for pipe in self.project.pipes.values():
            for nid in (pipe.start_node_id, pipe.end_node_id):
                if nid not in self.project.nodes:
                    raise ValueError(f"Trecho {pipe.id} referencia nó inexistente '{nid}'.")
            adjacency.setdefault(pipe.start_node_id, []).append(pipe)
            adjacency.setdefault(pipe.end_node_id, []).append(pipe)

        children: Dict[str, List[str]] = {source_id: []}
        parent_pipe: Dict[str, Pipe] = {}
        visited = {source_id}
        queue = deque([source_id])
        while queue:
            current = queue.popleft()
            for pipe in adjacency.get(current, []):
                other = pipe.end_node_id if pipe.start_node_id == current else pipe.start_node_id
                if other in visited:
                    if parent_pipe.get(current) is not pipe:
                        raise ValueError(f"Rede em malha não suportada (ciclo no trecho {pipe.id}).")
                    continue
                visited.add(other)
                parent_pipe[other] = pipe
                children.setdefault(current, []).append(other)
                children.setdefault(other, [])
                queue.append(other)

        unreachable = set(self.project.nodes) - visited
        if unreachable:
            raise ValueError(f"Nós desconectados da fonte: {sorted(unreachable)}")
        return children, parent_pipe

    def analyze(
        self,
        source_id: str,
        source_pressure_mca: float,
        auto_size: bool = False,
        max_velocity: float = 3.0,
        active_rooms: Optional[Iterable[str]] = None,
        auto_fittings: bool = False,
        flow_factor: float = 1.0,
    ) -> dict:
        """
        Calcula vazão por trecho (pesos acumulados a jusante), opcionalmente
        dimensiona os diâmetros (alterando os trechos) e verifica a pressão em cada nó.

        `active_rooms` simula uso simultâneo: só os aparelhos desses cômodos consomem
        (None = todos). `auto_fittings` soma ao trecho o comprimento equivalente das conexões
        (joelhos e tês detectados pela geometria + registros informados no nó de chegada),
        sem alterar `equivalent_length_m` do trecho. Trechos sem consumo a jusante ficam com vazão zero e sem alertas.
        `flow_factor` escala as vazões prováveis (1 = hora de pico); usado na simulação em período estendido.
        """
        active = None if active_rooms is None else set(active_rooms)

        def used(nid):
            return [f for f in self.project.nodes[nid].fixtures
                    if active is None or self.project.nodes[nid].room in active]

        children, parent_pipe = self._build_tree(source_id)
        nodes = self.project.nodes

        # Pesos acumulados a jusante (pós-ordem)
        order = [source_id]
        for nid in order:
            order.extend(children[nid])
        downstream_weight = {nid: sum(f.weight for f in used(nid)) for nid in order}
        for nid in reversed(order):
            if nid in parent_pipe:
                p = parent_pipe[nid]
                parent_id = p.start_node_id if p.end_node_id == nid else p.end_node_id
                downstream_weight[parent_id] += downstream_weight[nid]

        pipe_results, alerts = {}, []
        pressures = {source_id: source_pressure_mca}
        source_elev = nodes[source_id].elevation_m
        head_loss_to = {source_id: 0.0}
        prv_reduction: Dict[str, float] = {}

        for nid in order[1:]:
            pipe = parent_pipe[nid]
            parent_id = pipe.start_node_id if pipe.end_node_id == nid else pipe.end_node_id
            flow = HydraulicCalculator.calculate_probable_flow(downstream_weight[nid]) * flow_factor

            if auto_size and flow > 0:
                chosen = select_diameter(flow, max_velocity)
                if chosen is None:
                    alerts.append({
                        "level": "ALERTA", "code": "NO_DIAMETER",
                        "message": f"Trecho {pipe.id}: nenhum diâmetro comercial atende {flow:.2f} L/s.",
                    })
                else:
                    pipe.diameter_mm = chosen

            velocity = HydraulicCalculator.calculate_velocity(flow, pipe.diameter_mm)
            fit_leq, fit_detail = 0.0, []
            if auto_fittings:
                # conexão de mudança de direção informada no nó substitui a detectada pela geometria
                informed = any(f in GEOMETRIC_FITTINGS for f in nodes[parent_id].fittings)
                detected = [] if informed else detect_fittings(nodes, children, parent_pipe, parent_id, nid)
                names = detected + list(nodes[nid].fittings)
                fit_leq, fit_detail = fittings_equivalent_length(names, pipe.diameter_mm)
            total_eq = pipe.equivalent_length_m + fit_leq
            hf = HydraulicCalculator.calculate_head_loss(replace(pipe, equivalent_length_m=total_eq), flow)
            check = HydraulicValidator.validate_pipe_limits(pipe.id, velocity, max_velocity)
            if flow > 0 and check["level"] != "OK":
                alerts.append(check)

            head_loss_to[nid] = head_loss_to[parent_id] + hf
            pressures[nid] = source_pressure_mca + (source_elev - nodes[nid].elevation_m) - head_loss_to[nid]
            setpoint = nodes[nid].prv_setpoint_mca
            if setpoint > 0 and pressures[nid] > setpoint:
                # VRP: a pressão a jusante fica no valor regulado; o excesso entra como perda
                prv_reduction[nid] = pressures[nid] - setpoint
                head_loss_to[nid] += prv_reduction[nid]
                pressures[nid] = setpoint
            pipe_results[pipe.id] = {
                "weight": downstream_weight[nid], "flow_lps": flow, "diameter_mm": pipe.diameter_mm,
                "velocity_ms": velocity, "head_loss_mca": hf,
                "equivalent_length_m": total_eq, "fittings": fit_detail,
            }

        node_results = {}
        for nid, pressure in pressures.items():
            required = max((f.min_pressure_mca for f in used(nid)), default=0.0)
            ok = pressure >= required
            node_results[nid] = {"pressure_mca": pressure, "required_mca": required, "ok": ok,
                                 "prv_reduction_mca": prv_reduction.get(nid, 0.0)}
            if not ok:
                alerts.append({
                    "level": "ALERTA", "code": "LOW_PRESSURE",
                    "message": f"Nó {nid}: pressão de {pressure:.2f} mca abaixo do mínimo de {required:.2f} mca.",
                })

        return {"pipes": pipe_results, "nodes": node_results, "alerts": alerts}
