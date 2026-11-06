import base64
from datetime import date
from html import escape
from typing import Iterable, Optional

from core.standards import FITTING_LABELS
from services.budget_calculator import BudgetCalculator
from services.project_manager import ProjectManager

STYLE = """
body { font-family: sans-serif; font-size: 10pt; color: #222; }
h1 { font-size: 18pt; margin-bottom: 0; } h2 { font-size: 13pt; margin-top: 18px; border-bottom: 1px solid #999; }
table { border-collapse: collapse; width: 100%; } th, td { border: 1px solid #bbb; padding: 3px 6px; text-align: right; }
th { background: #e8eaf0; } td.l, th.l { text-align: left; } .bad { color: #b00020; font-weight: bold; }
.small { font-size: 8.5pt; color: #555; }
"""


def _row(cells, left_first=True):
    out = []
    for i, c in enumerate(cells):
        cls = ' class="l"' if (i == 0 and left_first) else ""
        out.append(f"<td{cls}>{c}</td>")
    return "<tr>" + "".join(out) + "</tr>"


def _table(headers, rows):
    head = "".join(f'<th class="l">{h}</th>' if i == 0 else f"<th>{h}</th>" for i, h in enumerate(headers))
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>"


def generate_memorial(
    project: ProjectManager,
    result: dict,
    *,
    source_id: str,
    source_pressure_mca: float,
    max_velocity: float = 3.0,
    auto_size: bool = False,
    active_rooms: Optional[Iterable[str]] = None,
    project_name: str = "Projeto",
    image_png: Optional[bytes] = None,
) -> str:
    """Memorial de cálculo de água fria em HTML (autocontido; imprimível ou conversível em PDF)."""
    e = escape
    active = None if active_rooms is None else list(active_rooms)
    all_rooms = sorted({n.room for n in project.nodes.values() if n.fixtures and n.room})
    parts = [f"<html><head><meta charset='utf-8'><style>{STYLE}</style></head><body>",
             f"<h1>Memorial de cálculo – Instalação predial de água fria</h1>",
             f"<p>{e(project_name)} &nbsp;·&nbsp; {date.today():%d/%m/%Y}</p>"]

    parts.append("<h2>1. Dados de entrada</h2>")
    scenario = "todos os aparelhos em uso simultâneo" if active is None or set(active) >= set(all_rooms) \
        else "uso simultâneo apenas nos cômodos: " + (", ".join(e(r) for r in active) or "nenhum")
    parts.append(
        "<ul>"
        f"<li>Nó de origem (fonte): <b>{e(source_id)}</b> — cota {project.nodes[source_id].elevation_m:.2f} m, "
        f"pressão disponível {source_pressure_mca:.2f} mca</li>"
        f"<li>Velocidade máxima admitida: {max_velocity:.2f} m/s</li>"
        f"<li>Diâmetros: {'dimensionados automaticamente (menor diâmetro comercial que atende)' if auto_size else 'conforme projeto'}</li>"
        f"<li>Cenário: {scenario}</li>"
        f"<li>Trechos: {len(project.pipes)} · Nós: {len(project.nodes)} · Cômodos: {len(project.rooms)}</li></ul>")
    if image_png:
        parts.append(f"<p><img src='data:image/png;base64,{base64.b64encode(image_png).decode()}' width='620'></p>")

    parts.append("<h2>2. Método de cálculo</h2><ul>"
                 "<li>Vazão provável (método dos pesos, NBR 5626): Q = 0,3·√ΣP [L/s], com ΣP a soma dos pesos dos aparelhos a jusante do trecho.</li>"
                 "<li>Velocidade: v = Q / A, com A a área da seção circular do diâmetro interno.</li>"
                 "<li>Perda de carga (Fair-Whipple-Hsiao, PVC, água fria): J = 0,0008695·Q<sup>1,75</sup> / D<sup>4,75</sup> "
                 "[m/m, Q em m³/s, D em m]; hf = J·(L + Leq), com Leq o comprimento equivalente das conexões (tabela de PVC soldável por diâmetro).</li>"
                 "<li>Pressão no nó = pressão na fonte + (cota da fonte − cota do nó) − Σhf do caminho.</li></ul>")

    parts.append("<h2>3. Aparelhos atendidos</h2>")
    rows = []
    for n in project.nodes.values():
        for f in n.fixtures:
            rows.append(_row([e(n.id), e(n.room or "–"), e(f.name.replace("_", " ")), f"{f.weight:.2f}", f"{f.min_pressure_mca:.2f}"]))
    parts.append(_table(["Nó", "Cômodo", "Aparelho", "Peso", "Pressão mín. (mca)"], rows))

    parts.append("<h2>4. Dimensionamento dos trechos</h2>")
    rows = []
    for pid, r in result["pipes"].items():
        pipe = project.pipes[pid]
        if r["flow_lps"] <= 0:
            status = "sem consumo"
        elif r["velocity_ms"] > max_velocity:
            status = "<span class='bad'>velocidade alta</span>"
        elif r["velocity_ms"] < 0.3:
            status = "velocidade baixa"
        else:
            status = "OK"
        rows.append(_row([e(pid), f"{e(pipe.start_node_id)} → {e(pipe.end_node_id)}", f"{pipe.length_m:.2f}",
                          f"{r.get('equivalent_length_m', pipe.equivalent_length_m):.2f}", f"{r['diameter_mm']:g}", f"{r.get('weight', 0):.2f}",
                          f"{r['flow_lps']:.3f}", f"{r['velocity_ms']:.2f}", f"{r['head_loss_mca']:.3f}", status]))
    parts.append(_table(["Trecho", "De → Para", "L (m)", "Leq (m)", "DN (mm)", "ΣP", "Q (L/s)", "v (m/s)", "hf (mca)", "Situação"], rows))

    detail_rows = []
    for pid, r in result["pipes"].items():
        if r.get("fittings"):
            counts = {}
            for name, leq in r["fittings"]:
                counts.setdefault(name, [0, leq])[0] += 1
            text = "; ".join(f"{v[0]}× {FITTING_LABELS.get(k, k)} ({v[1]:.2f} m cada)" for k, v in counts.items())
            detail_rows.append(_row([e(pid), f"<span style='text-align:left'>{text}</span>", f"{sum(l for _, l in r['fittings']):.2f}"]))
    if detail_rows:
        parts.append("<h3>Conexões consideradas (comprimento equivalente)</h3>")
        parts.append(_table(["Trecho", "Conexões", "Leq (m)"], detail_rows))

    parts.append("<h2>5. Verificação de pressões</h2>")
    rows = []
    for nid, r in result["nodes"].items():
        node = project.nodes[nid]
        status = "OK" if r["ok"] else "<span class='bad'>PRESSÃO INSUFICIENTE</span>"
        rows.append(_row([e(nid), e(node.room or "–"), f"{node.elevation_m:.2f}", f"{r['pressure_mca']:.2f}",
                          f"{r['required_mca']:.2f}", status]))
    parts.append(_table(["Nó", "Cômodo", "Cota (m)", "Pressão (mca)", "Mínima (mca)", "Situação"], rows))

    parts.append("<h2>6. Alertas</h2>")
    if result["alerts"]:
        parts.append("<ul>" + "".join(f"<li>[{e(a['level'])}] {e(a['message'])}</li>" for a in result["alerts"]) + "</ul>")
    else:
        parts.append("<p>Nenhum alerta: todos os trechos e pontos de consumo atendem aos critérios verificados.</p>")

    parts.append("<h2>7. Quantitativo de tubulação</h2>")
    items = BudgetCalculator.calculate_materials_cost(list(project.pipes.values()))
    rows = [_row([e(i["material"]), f"{i['quantity']:.2f}", f"R$ {i['unit_price']:.2f}", f"R$ {i['total_price']:.2f}"]) for i in items]
    rows.append(_row(["<b>Total</b>", "", "", f"<b>R$ {sum(i['total_price'] for i in items):.2f}</b>"]))
    parts.append(_table(["Material", "Qtd (m)", "Preço un.", "Total"], rows))

    parts.append("<p class='small'>Memorial gerado automaticamente. Escopo: rede ramificada de água fria; os resultados "
                 "devem ser conferidos e assinados pelo engenheiro responsável. Conexões: joelhos e tês detectados pela "
                 "geometria; registros somente quando indicados no projeto.</p></body></html>")
    return "".join(parts)
