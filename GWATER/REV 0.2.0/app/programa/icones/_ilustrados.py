"""Ícones ilustrados do GWATER (24×24): o equipamento como ele é de verdade, com cores próprias (água azul, metal,
bomba vermelha, válvula verde) e contorno escuro, para ficarem legíveis em qualquer tema, claro ou escuro.

_gerar.py junta estes aos ícones de traço (que levam as cores do tema, trocadas ao carregar: tema.icone).
"""
K = "#1d3447"        # contorno
AG, AG2, AG3 = "#2f9be0", "#8fd3ff", "#1c6fae"   # água: média, clara, funda
MT, MT2 = "#b4c4d1", "#7b8fa1"                   # metal claro e escuro
VM, VD, AM, BR = "#e0524f", "#2fae74", "#f2a33a", "#ffffff"
TERRA, GRAMA, CONC = "#b98a5a", "#5fb76b", "#cfc8b9"


def P(d, fill="none", st=K, w=1.2, extra=""):
    return (f'<path d="{d}" fill="{fill}" stroke="{st}" stroke-width="{w}" stroke-linejoin="round" '
            f'stroke-linecap="round" {extra}/>')


def R(x, y, w, h, fill, rx=1, st=K, sw=1.2):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'


def C(x, y, r, fill, st=K, sw=1.2):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'


def T(x, y, txt, cor=K, tam=5.6):
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI, Arial" font-size="{tam}" font-weight="800" fill="{cor}" '
            f'text-anchor="middle">{txt}</text>')


def grad(gid, c1, c2, vertical=True):
    xy = 'x1="0" y1="0" x2="0" y2="1"' if vertical else 'x1="0" y1="0" x2="1" y2="0"'
    return (f'<defs><linearGradient id="{gid}" {xy}><stop offset="0" stop-color="{c1}"/>'
            f'<stop offset="1" stop-color="{c2}"/></linearGradient></defs>')


# ---------------------------------------------------------------- peças que se repetem
def tanque(nivel=0.55):
    """Reservatório elevado: cuba cilíndrica com água pelo nível, tampa e pilares."""
    y = 4 + (1 - nivel) * 10
    return (grad("ag", AG2, AG3) + P("M7 18 L5.5 22 M17 18 L18.5 22 M12 18 V22", st=MT2, w=1.4) +
            P("M4.5 5 Q12 2.2 19.5 5 V16.5 Q12 19.3 4.5 16.5 Z", fill=BR) +
            f'<path d="M4.5 {y} Q12 {y + 1.6} 19.5 {y} V16.5 Q12 19.3 4.5 16.5 Z" fill="url(#ag)"/>' +
            P(f"M4.5 {y} Q12 {y + 1.6} 19.5 {y}", st=BR, w=0.9) +
            P("M4.5 5 Q12 2.2 19.5 5 V16.5 Q12 19.3 4.5 16.5 Z") + P("M4.5 5 Q12 7.6 19.5 5", w=0.9))


def bomba_corpo():
    """Bomba centrífuga: voluta vermelha, bocal de saída, motor cinza e base."""
    return (grad("mt", MT, MT2) + R(2, 19.5, 20, 2.5, CONC, 0.6) +
            R(12.5, 9.5, 9, 7, "url(#mt)", 1.5) + P("M14.5 9.5 V16.5 M17 9.5 V16.5 M19.5 9.5 V16.5", w=0.7) +
            C(8, 13, 6, VM) + C(8, 13, 2.2, "#ffd0cf") + P("M8 7 H12.5 V3.5 H7.5 V7", fill=VM) +
            P("M8 19 V19.5 M5 18 L4.5 19.5 M11 18 L11.5 19.5", w=1))


def valvula_corpo(cor=VD, letras=None, volante=True):
    """Corpo de válvula com flanges e volante em cima; letras (PRV, VSE…) embaixo."""
    out = (R(1.5, 8.5, 2.2, 7, MT2, 0.5) + R(20.3, 8.5, 2.2, 7, MT2, 0.5) +
           P("M3.7 9.5 L12 12 L3.7 14.5 Z M20.3 9.5 L12 12 L20.3 14.5 Z", fill=cor) + C(12, 12, 1.6, BR))
    if volante:
        out += P("M12 10.4 V5.2", w=1.3) + f'<ellipse cx="12" cy="4.4" rx="4.2" ry="1.4" fill="{MT}" stroke="{K}" stroke-width="1.1"/>'
    if letras:  # numa etiqueta branca: legível também nos temas escuros
        out += R(4.6, 17.6, 14.8, 5.8, BR, 1.6, sw=0.9) + T(12, 22.2, letras, K, 5.4)
    return out


def casa():
    return (P("M3 11.5 L12 4 L21 11.5", fill="none", w=1.4) + P("M5.5 10 V20.5 H18.5 V10 L12 5 Z", fill="#fff4e0") +
            P("M2.5 12 L12 3.6 L21.5 12", st=VM, w=1.8) + R(10, 14, 4, 6.5, AG3, 0.4) + R(6.8, 11.5, 2.6, 2.6, AG2, 0.3, sw=0.8))


# ---------------------------------------------------------------- os ícones
ILUSTRADOS = {
    # ---- equipamentos e elementos
    "reservatorio": tanque(),
    "captacao": (grad("rio", AG2, AG3) + P("M1 21 Q6 18 12 19 T23 18 V23 H1 Z", fill="url(#rio)", st=AG3, w=0.8) +
                 P("M1 17 Q6 15 12 16 T23 15", st=AG, w=1) + R(9, 6, 6, 10, CONC, 0.5) +
                 P("M12 6 V2.5 H19 V5", w=1.3, st=MT2) + R(10.5, 9, 3, 3, AG2, 0.3, sw=0.8) +
                 P("M3 15 L6 12 L9 15", st=GRAMA, w=1.4) + P("M16 15 L19 11.5 L22 15", st=GRAMA, w=1.4)),
    "bomba": bomba_corpo(),
    "bomba_variavel": bomba_corpo() + C(19.5, 4.5, 3.6, AM) + P("M17.6 5.6 Q19.5 2 21.4 5.6", w=0.9) + P("M19.5 4.6 L20.6 3.2", w=0.9),
    "estacao": (R(2, 8, 20, 13.5, CONC, 0.8) + P("M1 8.5 L12 2.5 L23 8.5", fill=VM, w=1.2) +
                C(8, 15.5, 3.2, VM) + C(16, 15.5, 3.2, VM) + C(8, 15.5, 1, BR, sw=0.8) + C(16, 15.5, 1, BR, sw=0.8)),
    "no": C(12, 12, 4.5, AG, sw=1.4) + C(12, 12, 1.6, BR, sw=0.8) + P("M2 12 H7.5 M16.5 12 H22", st=AG3, w=2.2),
    "tubulacao": (grad("tb", MT, MT2) + P("M3 17 L17 3", st=K, w=6.2) + P("M3 17 L17 3", st=AG, w=4.2) +
                  P("M4.5 15.5 L15.5 4.5", st=AG2, w=1.2) + R(1, 15.5, 6, 6, "url(#tb)", 1, sw=1.1) +
                  R(15, 1.5, 6, 6, "url(#tb)", 1, sw=1.1) + C(19.5, 19.5, 2.4, VD, sw=1)),
    "hidrante": (R(8, 6.5, 8, 14, VM, 1.2) + P("M7 6.8 Q12 1.5 17 6.8 Z", fill=VM) + R(10.5, 1.8, 3, 2, MT2, 0.4, sw=0.9) +
                 R(4, 10, 4, 3.5, MT, 0.6) + R(16, 10, 4, 3.5, MT, 0.6) + R(6.5, 20.5, 11, 2, MT2, 0.5) +
                 C(12, 13.5, 1.8, "#ffd0cf", sw=0.9)),
    "ponto_consumo": casa() + C(18.5, 18.5, 3.4, AG, sw=1) + T(18.5, 20.3, "m³", BR, 3.6),
    "valvula": valvula_corpo(),
    "registro": valvula_corpo(MT2, "REG"),
    "prv": valvula_corpo(VD, "PRV"),
    "psv": valvula_corpo(AG, "PSV"),
    "pbv": valvula_corpo("#a066d3", "PBV"),
    "fcv": valvula_corpo(AM, "FCV"),
    "tcv": valvula_corpo(MT2, "TCV"),
    "gpv": valvula_corpo("#a0522d", "GPV"),
    "vre": valvula_corpo("#15aabf", "VRE"),
    "vse": valvula_corpo("#74b816", "VSE"),
    # ---- cálculo e análises
    "calcular": (grad("cl", "#4fd18f", "#1f8f5a") + C(12, 12, 10, "url(#cl)", sw=1.3) +
                 P("M9.5 7 L17.5 12 L9.5 17 Z", fill=BR, w=1)),
    "simular": (grad("sm", "#4fd18f", "#1f8f5a") + C(12, 12, 10, "url(#sm)", sw=1.3) +
                P("M9.5 7 L17.5 12 L9.5 17 Z", fill=BR, w=1)),
    "validar": (grad("vl", "#6fd3a0", "#1f8f5a") + P("M12 2.5 L20 5.5 V11.5 C20 16.5 16.5 20 12 21.5 C7.5 20 4 16.5 4 11.5 V5.5 Z", fill="url(#vl)") +
                P("M8.2 12 L11 14.8 L16 9.2", st=BR, w=2)),
    "curvas": (R(2.5, 2.5, 19, 19, BR, 2) + P("M5 6 V19 H20", w=1) + P("M5.5 8 Q12 9 19 17", st=VM, w=1.8) +
               P("M5.5 17 Q11 7 19 10", st=AG, w=1.8)),
    "padroes": (R(2.5, 3, 19, 18, BR, 2) + "".join(R(4.5 + i * 3.1, 19 - h, 2.3, h, AG if i not in (2, 3) else AM, 0.3, sw=0.7)
                                                   for i, h in enumerate((5, 7, 12, 14, 9, 6)))),
    "qualidade": (P("M12 2.5 C16.5 8 18.5 11 18.5 14.5 A6.5 6.5 0 0 1 5.5 14.5 C5.5 11 7.5 8 12 2.5 Z", fill=AG) +
                  P("M8.5 14.5 A3.5 3.5 0 0 0 12 18", st=BR, w=1.4) + C(18.5, 18.5, 3.6, VD, sw=1) +
                  P("M16.9 18.5 L18 19.7 L20.2 17.3", st=BR, w=1.1)),
    "cloro": (R(6, 5, 12, 16, "#e9f6ea", 2) + R(9, 2.5, 6, 3, MT2, 0.6) + R(6, 10, 12, 6, VD, 0) +
              P("M6 5 H18 V21 H6 Z", w=1.2) + T(12, 14.8, "Cl", BR, 5.5)),
    "incendio": (P("M12 2 C15 6 19 9 19 14.5 A7 7 0 0 1 5 14.5 C5 11 7 9 8.5 7 C9 10 10 11 11 11.5 C10.5 8 11 5 12 2 Z", fill=AM) +
                 P("M12 21.5 A3.6 3.6 0 0 1 8.4 18 C8.4 15.5 10.5 14 12 12 C13.5 14 15.6 15.5 15.6 18 A3.6 3.6 0 0 1 12 21.5 Z", fill=VM, w=1)),
    "descarga": (valvula_corpo(VM, volante=True) + P("M12 15.5 V19", st=AG3, w=1.3) +
                 P("M10 19.5 Q12 23 14 19.5", st=AG, w=1.4) + P("M7.5 21 Q8.5 23 9.5 21 M14.5 21 Q15.5 23 16.5 21", st=AG, w=1)),
    "energia": P("M13.5 1.8 L5 13.5 H11.2 L9.8 22.2 L19 9.8 H12.6 Z", fill=AM, w=1.3),
    "perdas": (P("M2 9 H22 M2 15 H22", w=1.2) + R(2, 9, 20, 6, AG2, 0, sw=0) + P("M2 9 H22 M2 15 H22", w=1.3) +
               P("M11 15 L12 13 L13 15", st=K, w=1) + P("M12 15.5 V17.5", st=AG3, w=1.2) +
               P("M12 18 C13.5 20 13.5 21.5 12 21.8 C10.5 21.5 10.5 20 12 18 Z", fill=AG, w=0.9)),
    "calibracao": (C(12, 12, 9.5, BR, sw=1.2) + C(12, 12, 6, VM, sw=1) + C(12, 12, 3, BR, sw=1) + C(12, 12, 1, VM, sw=0.8) +
                   P("M21.5 2.5 L13.5 10.5", w=1.5) + P("M21.5 2.5 L21.8 6.2 M21.5 2.5 L17.8 2.2", w=1.4)),
    "darwin": (P("M7 3 C7 9 17 9 17 15 C17 21 7 21 7 21 M17 3 C17 9 7 9 7 15 C7 21 17 21 17 21", st=VD, w=1.6) +
               P("M8.5 6 H15.5 M9.5 12 H14.5 M8.5 18 H15.5", st=AG, w=1.2)),
    "criticidade": (P("M12 2.5 L22 20.5 H2 Z", fill=AM, w=1.3) + P("M12 8.5 V14", w=2) + C(12, 17.3, 1.2, K, sw=0.4)),
    # ---- telas, dados e arquivos
    "mapa": (P("M2 5.5 L8 3.5 L16 5.5 L22 3.5 V18.5 L16 20.5 L8 18.5 L2 20.5 Z", fill="#e6f0d8") +
             P("M8 3.5 V18.5 M16 5.5 V20.5", w=0.9) + P("M3 14 Q9 9 13 12 T21 8", st=AG, w=1.8) +
             C(17, 13.5, 2.4, VM, sw=1) + C(17, 13.5, 0.8, BR, sw=0.5)),
    "painel": (R(2, 3, 20, 15, "#16324f", 1.5) + P("M8 21.5 H16 M12 18 V21.5", w=1.4) +
               P("M4.5 14 L8.5 9.5 L11.5 12 L16 6.5 L19.5 9", st=AG2, w=1.4) + C(16, 6.5, 1.2, AM, st=AM, sw=0.4)),
    "aovivo": (C(12, 12, 3, VM, sw=1) + P("M7.5 7.5 A6.4 6.4 0 0 0 7.5 16.5 M16.5 7.5 A6.4 6.4 0 0 1 16.5 16.5", st=VM, w=1.6) +
               P("M4.5 4.5 A10.6 10.6 0 0 0 4.5 19.5 M19.5 4.5 A10.6 10.6 0 0 1 19.5 19.5", st=VM, w=1.4)),
    "dados": (f'<ellipse cx="12" cy="5.5" rx="8" ry="3" fill="{AG2}" stroke="{K}" stroke-width="1.2"/>' +
              P("M4 5.5 V18.5 A8 3 0 0 0 20 18.5 V5.5", fill=AG2) + P("M4 12 A8 3 0 0 0 20 12", w=1.1) +
              f'<ellipse cx="12" cy="5.5" rx="8" ry="3" fill="{AG2}" stroke="{K}" stroke-width="1.2"/>'),
    "relatorio": (P("M5 2.5 H15 L19.5 7 V21.5 H5 Z", fill=BR) + P("M15 2.5 V7 H19.5", w=1.1) +
                  P("M8 11 H16 M8 14 H16 M8 17 H13", st=MT2, w=1.2) + R(14, 15.5, 6.5, 6.5, VD, 1, sw=1) +
                  P("M15.6 18.8 L16.9 20.1 L19 17.6", st=BR, w=1.1)),
    "graficos": (R(2.5, 2.5, 19, 19, BR, 2) + R(5.5, 13, 3, 6, AG, 0.4, sw=0.9) + R(10.5, 8, 3, 11, VD, 0.4, sw=0.9) +
                 R(15.5, 5, 3, 14, AM, 0.4, sw=0.9)),
    "tabelas": (R(2.5, 3.5, 19, 17, BR, 1.5) + R(2.5, 3.5, 19, 4.5, AG, 1.5) +
                P("M2.5 12.5 H21.5 M2.5 16.5 H21.5 M9 8 V20.5 M15 8 V20.5", w=0.9)),
    "cotas": (P("M1.5 20.5 L8 9 L12 14 L16.5 6 L22.5 20.5 Z", fill="#c7a77a") + P("M14.5 9.5 L16.5 6 L18.4 10.6 Z", fill=BR, w=0.8) +
              P("M2 20.5 H22", w=1.3) + T(6, 7, "z", K, 6.5)),
    "zonas": (P("M2.5 3 L12 2.5 L11 12 L2.5 13 Z", fill="#9ed9f5") + P("M12 2.5 L21.5 3.5 L21 11.5 L11 12 Z", fill="#b9e6c4") +
              P("M2.5 13 L11 12 L12 21.5 L3 21 Z", fill="#ffe0a8") + P("M11 12 L21 11.5 L21.5 21 L12 21.5 Z", fill="#f6c3c2")),
    "opcoes": (P("M12 1.8 L14 4.2 L17.1 3.6 L17.6 6.7 L20.4 8.1 L19.4 11.1 L21.3 13.6 L18.9 15.6 L19.2 18.8 L16 19 "
                 "L14.4 21.7 L12 19.8 L9.6 21.7 L8 19 L4.8 18.8 L5.1 15.6 L2.7 13.6 L4.6 11.1 L3.6 8.1 L6.4 6.7 L6.9 3.6 L10 4.2 Z",
                 fill=MT) + C(12, 12, 3.4, BR, sw=1.2)),
    "novo": (P("M5 2.5 H14.5 L19 7 V21.5 H5 Z", fill=BR) + P("M14.5 2.5 V7 H19", w=1.1) + C(17.5, 17.5, 4.3, VD, sw=1) +
             P("M17.5 15.2 V19.8 M15.2 17.5 H19.8", st=BR, w=1.4)),
    "abrir": (P("M2 6 H9 L11 8 H20 V19.5 H2 Z", fill="#f5c45a") + P("M2 19.5 L5 11 H22.5 L20 19.5 Z", fill="#ffd97d")),
    "salvar": (P("M3 3 H17.5 L21 6.5 V21 H3 Z", fill=AG) + R(6.5, 3, 9, 6, BR, 0.4, sw=1) + R(6, 13, 12, 8, BR, 0.4, sw=1) +
               P("M12.5 4.5 V7.5", w=1.4)),
    "importar": (P("M5 2.5 H15 L19.5 7 V21.5 H5 Z", fill=BR) + P("M12 7.5 V16.5 M8.5 13 L12 16.5 L15.5 13", st=VD, w=1.8)),
    "exportar": (P("M5 2.5 H15 L19.5 7 V21.5 H5 Z", fill=BR) + P("M12 16.5 V7.5 M8.5 11 L12 7.5 L15.5 11", st=AG3, w=1.8)),
    "modelbuilder": (R(2, 3, 9, 7, "#f5c45a", 1) + P("M11 6.5 H15 V12.5", st=AG3, w=1.5) + P("M13 10.5 L15 12.5 L17 10.5", st=AG3, w=1.5) +
                     P("M9 20.5 L14 15 L20 19 L23 14", st=AG, w=1.8) + C(9, 20.5, 1.6, BR, sw=1) + C(14, 15, 1.6, BR, sw=1) +
                     C(20, 19, 1.6, BR, sw=1)),
}
ILUSTRADOS["demanda"] = (casa() + R(14.5, 15.5, 8, 7, AG, 1.2, sw=1) + T(18.5, 21, "L/s", BR, 3.6))
ILUSTRADOS["loadbuilder"] = (R(1.5, 13, 8.5, 8.5, "#fff4e0", 0.8) + P("M1 13.5 L5.75 9 L10.5 13.5", st=VM, w=1.4) +
                             R(13.5, 13, 8.5, 8.5, "#fff4e0", 0.8) + P("M13 13.5 L17.75 9 L22.5 13.5", st=VM, w=1.4) +
                             P("M12 2 V8 M8.5 5 L12 8 L15.5 5", st=AG3, w=1.6) + P("M5.75 17 V18.5 M17.75 17 V18.5", st=AG, w=1.8))
