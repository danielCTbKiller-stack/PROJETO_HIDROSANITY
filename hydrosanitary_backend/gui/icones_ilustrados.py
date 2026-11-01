"""Ícones ilustrados do GPREDIAL (24×24 SVG): os aparelhos e as peças como são de verdade, com cores próprias e
contorno escuro, legíveis em qualquer tema. Os botões que existem nos dois programas (novo, abrir, salvar,
calcular…) usam o mesmo desenho do GWATER (GWATER/REV 0.2.0/app/programa/icones/_ilustrados.py).

Só os botões e listas usam estes; na planta e no sinótico os aparelhos continuam como disco com a sigla, colorido
pelo resultado do cálculo.
"""
import importlib.util
from pathlib import Path

K = "#1d3447"
AG, AG2, AG3 = "#2f9be0", "#8fd3ff", "#1c6fae"
MT, MT2 = "#b4c4d1", "#7b8fa1"
VM, VD, AM, BR = "#e0524f", "#2fae74", "#f2a33a", "#ffffff"
LOUCA = "#f4f8fb"   # louça branca
CONC = "#cfc8b9"


def P(d, fill="none", st=K, w=1.2):
    return f'<path d="{d}" fill="{fill}" stroke="{st}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"/>'


def R(x, y, w, h, fill, rx=1, st=K, sw=1.2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'


def C(x, y, r, fill, st=K, sw=1.2):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'


def E(x, y, rx, ry, fill, st=K, sw=1.2):
    return f'<ellipse cx="{x}" cy="{y}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'


def gotas(*pts):
    return "".join(P(f"M{x} {y} q1 1.6 0 2.4 q-1 -0.8 0 -2.4 Z", fill=AG, st=AG3, w=0.6) for x, y in pts)


def torneira(x, y, esq=False):
    """Torneira de parede: corpo, bica para baixo e manopla."""
    s = -1 if esq else 1
    return (R(x - 1.2, y - 1.6, 2.4, 3.2, MT, 0.6, sw=1) + P(f"M{x} {y} H{x + s * 4} V{y + 2.2}", st=K, w=1.6) +
            P(f"M{x} {y} H{x + s * 4} V{y + 2.2}", st=MT, w=0.8) + P(f"M{x} {y - 1.6} V{y - 3.2} M{x - 1.6} {y - 3.4} H{x + 1.6}", w=1.1))


ILUSTRADOS = {
    # ---- aparelhos (NBR 5626)
    "chuveiro_eletrico": (P("M4 2.5 V6.5 H9.5", st=MT2, w=1.8) + R(8.5, 4, 8, 6.5, BR, 2) + P("M10.5 7.2 L12 5.6 L11.8 7 L13.4 7 L11.6 9.2 L12 7.8 Z", fill=AM, w=0.6) +
                          P("M9 10.5 H16 L17.5 12.8 H7.5 Z", fill=MT) + gotas((8.5, 15), (12.5, 15.5), (16.5, 15), (10.5, 19), (14.5, 19.5))),
    "bacia_sanitaria_cx_acoplada": (R(12.5, 2.5, 8, 10, LOUCA, 1.2) + R(14, 1.5, 5, 1.6, MT, 0.5, sw=0.9) +
                                    P("M3 11 H15 C15 16 13 18.5 10 19.5 L10.5 22 H5.5 L6 19 C4 17.5 3 15 3 11 Z", fill=LOUCA) +
                                    E(8.5, 11.2, 5.5, 1.5, "#dfe9f1", sw=1) + P("M12.5 11 H14", w=1)),
    "bacia_valvula_descarga": (P("M18.5 2 V9 M18.5 9 H14.5", st=MT2, w=1.8) + R(16.5, 4, 4, 3, MT, 0.8, sw=1) + C(18.5, 5.5, 0.8, VM, sw=0.6) +
                               P("M3 11 H15 C15 16 13 18.5 10 19.5 L10.5 22 H5.5 L6 19 C4 17.5 3 15 3 11 Z", fill=LOUCA) +
                               E(8.5, 11.2, 5.5, 1.5, "#dfe9f1", sw=1)),
    "lavatorio": (P("M2.5 11 H21.5 C21.5 16.5 17.5 19.5 12 19.5 C6.5 19.5 2.5 16.5 2.5 11 Z", fill=LOUCA) +
                  E(12, 11.4, 6.5, 1.6, "#cfe7f7", sw=1) + P("M10.5 19.5 L11 22.5 H13 L13.5 19.5", fill=LOUCA, w=1) +
                  P("M12 9.8 V5 H15.5 V7", st=K, w=1.8) + P("M12 9.8 V5 H15.5 V7", st=MT, w=0.9) + P("M10 5 H14", w=1.2) + gotas((15.5, 8))),
    "pia_cozinha": (R(1.5, 11, 21, 4, MT, 0.8) + P("M4 15 H20 V19 Q20 20.5 18.5 20.5 H5.5 Q4 20.5 4 19 Z", fill=MT2) +
                    P("M12 11 V4.5 Q12 2.5 14 2.5 H16 Q18 2.5 18 4.5 V7", st=K, w=1.8) +
                    P("M12 11 V4.5 Q12 2.5 14 2.5 H16 Q18 2.5 18 4.5 V7", st=MT, w=0.9) + gotas((18, 8.6))),
    "maquina_lavar": (R(3.5, 2, 17, 20, BR, 2) + P("M3.5 6.5 H20.5", w=1) + C(7, 4.3, 0.9, AG, sw=0.6) + R(11, 3.4, 7, 1.8, "#dfe9f1", 0.6, sw=0.7) +
                      C(12, 14, 5.5, MT, sw=1.2) + C(12, 14, 4, AG2, sw=0.9) + P("M8.5 15 Q12 13 15.5 15 V16.5 Q12 18.8 8.5 16.5 Z", fill=AG, st="none", w=0)),
    "maquina_lavar_loucas": (R(3.5, 2, 17, 20, BR, 2) + R(3.5, 2, 17, 4.5, MT, 2) + R(9, 3.2, 6, 1.6, BR, 0.5, sw=0.7) +
                             P("M5.5 9.5 H18.5 M5.5 18.5 H18.5", st=MT2, w=1) + C(9, 14, 3, LOUCA, sw=1) + C(15, 14, 3, LOUCA, sw=1) +
                             C(9, 14, 1.2, "#dfe9f1", sw=0.6) + C(15, 14, 1.2, "#dfe9f1", sw=0.6)),
    "ducha_higienica": (R(2, 7, 3.5, 5, MT, 0.8) + P("M5.5 9.5 C9 9.5 8 16 12 16.5", st=MT2, w=1.4) +
                        P("M11.5 15 L18.5 8.5 Q20.5 7 21.5 9 L15 16.5 Q13 18 11.5 15 Z", fill=BR) + P("M19 9 L20.6 10.6", w=0.9) +
                        gotas((20.5, 13), (17.5, 17), (21, 16.5))),
    "tanque": (P("M2.5 9 H21.5 L20 18.5 H4 Z", fill=CONC) + P("M5 11 H19 L18 16.5 H6 Z", fill="#e9e3d6", w=1) +
               P("M6 11.5 L18 16 M8 11 L18.5 15 M6.5 13.5 L16 16.5", st="#b9b19f", w=0.6) + P("M5 18.5 V22 M19 18.5 V22", w=1.4) +
               torneira(12, 5)),
    "bide": (P("M4 9.5 H20 C20 15 17 18.5 12 18.5 C7 18.5 4 15 4 9.5 Z", fill=LOUCA) + E(12, 9.9, 6.6, 1.5, "#cfe7f7", sw=1) +
             P("M9 18.5 L9.5 22 H14.5 L15 18.5", fill=LOUCA, w=1) + R(10.5, 5, 3, 3, MT, 0.6, sw=1) + P("M12 5 V3.2", w=1.2) +
             P("M12 8 Q12 6.5 13.5 6.2", st=AG, w=1)),
    "torneira_jardim": (R(1.5, 3, 4, 8, CONC, 0.5) + torneira(5.5, 7) + R(4.5, 2.2, 3, 1.4, VD, 0.5, sw=0.8) +
                        P("M9.5 9.2 C9.5 14 4 13.5 4 17.5 C4 21.5 12 22 16 19.5 C19 17.5 22 18.5 22.5 21", st=VD, w=2.4) +
                        P("M9.5 9.2 C9.5 14 4 13.5 4 17.5 C4 21.5 12 22 16 19.5 C19 17.5 22 18.5 22.5 21", st="#7fd6a6", w=0.8)),
    # ---- desenho do prédio
    "tubo": (R(1, 15.5, 6, 6, MT, 1, sw=1.1) + P("M4 18.5 L18.5 4", st=K, w=6) + P("M4 18.5 L18.5 4", st=AG, w=4) +
             P("M5.5 17 L17 5.5", st=AG2, w=1.1) + R(15.5, 1, 6, 6, MT, 1, sw=1.1)),
    "prumada": (R(9, 1.5, 6, 21, BR, 0.5, st="#00000000", sw=0) + P("M12 1.5 V22.5", st=K, w=6) + P("M12 1.5 V22.5", st=AG, w=4) +
                P("M11 2.5 V21.5", st=AG2, w=1) + P("M12 7.5 H20.5 M12 15.5 H20.5", st=K, w=4.2) + P("M12 7.5 H20.5 M12 15.5 H20.5", st=AG, w=2.4) +
                R(9.2, 6, 5.6, 3, MT, 0.6, sw=1) + R(9.2, 14, 5.6, 3, MT, 0.6, sw=1)),
    "pavimento": (P("M2 17.5 L12 22 L22 17.5 L12 13 Z", fill="#d9e3ec") + P("M2 12.5 L12 17 L22 12.5 L12 8 Z", fill="#e8eef3") +
                  P("M2 7.5 L12 12 L22 7.5 L12 3 Z", fill=AG2) + P("M2 7.5 V17.5 M22 7.5 V17.5 M12 12 V22", w=1)),
    "exemplo": (R(4, 4, 12, 18, "#e8eef3", 0.6) + R(16, 10, 5, 12, "#d9e3ec", 0.6) + R(7, 1.5, 3, 2.5, MT, 0.4, sw=0.9) +
                "".join(R(6 + (i % 2) * 5, 6.5 + (i // 2) * 4, 3, 2.4, AG2, 0.3, sw=0.7) for i in range(6)) +
                R(8.5, 18.5, 3, 3.5, AM, 0.3, sw=0.8) + P("M2 22 H22.5", w=1.3)),
    "relogio": (C(12, 12, 9.5, BR, sw=1.3) + C(12, 12, 8, "#eef6fb", sw=0.6) + P("M12 6.5 V12 L16 14.5", w=1.6) + C(12, 12, 1, K, sw=0.4) +
                P("M12 3.5 V4.8 M20.5 12 H19.2 M12 20.5 V19.2 M3.5 12 H4.8", w=1)),
    "excluir": (P("M5 6.5 H19 L17.5 21.5 H6.5 Z", fill=VM) + R(3.5, 4, 17, 2.5, VM, 0.6, sw=1.1) + R(9.5, 2, 5, 2, MT, 0.4, sw=0.9) +
                P("M9.5 10 V18 M12 10 V18 M14.5 10 V18", st=BR, w=1.2)),
}

# o mesmo desenho do GWATER nos botões que os dois programas têm
_DO_GWATER = {"novo": "novo", "abrir": "abrir", "salvar": "salvar", "calcular": "calcular", "calibracao": "calibracao",
              "opcoes": "opcoes", "memorial": "relatorio", "sinotico": "painel", "fonte": "reservatorio",
              "planta": "mapa"}


def _gwater():
    arq = Path(__file__).resolve().parents[2] / "GWATER" / "REV 0.2.0" / "app" / "programa" / "icones" / "_ilustrados.py"
    if not arq.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("_gwater_ilustrados", arq)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return {k: mod.ILUSTRADOS[v] for k, v in _DO_GWATER.items() if v in mod.ILUSTRADOS}
    except Exception:  # noqa: BLE001 - sem os do GWATER, ficam os desenhos próprios
        return {}


ILUSTRADOS.update(_gwater())


def svg(nome):
    corpo = ILUSTRADOS.get(nome)
    return None if corpo is None else f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{corpo}</svg>'
