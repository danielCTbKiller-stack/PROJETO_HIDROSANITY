"""Gera os ícones SVG da faixa de menus do GWATER.exe (24×24).

Os de traço usam as cores do Centro de Operações (C, W, M, D, B…): ao carregar, tema.icone troca essas cores pelas
do tema em uso. Os ilustrados (_ilustrados.py) têm cores próprias e valem em qualquer tema.

Uso:  python _gerar.py      (grava os .svg nesta pasta; a marca e o logo vêm de ../../gwater/icones)
"""
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
C, W, B, G, A, R, V, M, D = "#35d0ff", "#e8f2ff", "#1d8fd6", "#3ddc97", "#ffb547", "#ff6b7a", "#a78bfa", "#86a3c9", "#0b2a58"


def s(d, cor=C, w=1.8, fill="none", extra=""):
    return f'<path d="{d}" fill="{fill}" stroke="{cor}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" {extra}/>'


def f(d, cor=C):
    return f'<path d="{d}" fill="{cor}"/>'


def c(x, y, r, cor=C, fill="none", w=1.8):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{cor}" stroke-width="{w}"/>'


def r(x, y, w_, h, cor=C, fill="none", w=1.8, rx=1.5, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w_}" height="{h}" rx="{rx}" fill="{fill}" stroke="{cor}" stroke-width="{w}" {extra}/>'


def t(x, y, txt, cor=W, tam=7):
    return (f'<text x="{x}" y="{y}" font-family="Segoe UI, Arial" font-size="{tam}" font-weight="700" fill="{cor}" '
            f'text-anchor="middle">{txt}</text>')


def valvula(letras, cor=A):
    return s("M4 6 L12 11 L4 16 Z M20 6 L12 11 L20 16 Z", cor, 1.6, fill=cor + "33") + t(12, 23, letras, W, 6.5)


GOTA = "M12 3c3.5 4.6 5.5 7.6 5.5 10.2a5.5 5.5 0 0 1-11 0C6.5 10.6 8.5 7.6 12 3z"
LUPA = c(10, 10, 5.5) + s("M14.2 14.2 L20 20", C, 2.2)

ICONES = {
    # ---- cálculo
    "calcular": c(12, 12, 9.5, G, G + "33") + f("M10 7.5 L16.5 12 L10 16.5 Z", G),
    "validar": s("M12 3 L19 6 V11.5 C19 16 16 19.5 12 21 C8 19.5 5 16 5 11.5 V6 Z", G) + s("M8.6 12 L11 14.4 L15.6 9.6", W, 2),
    "cenarios": s("M12 4 L21 8.5 L12 13 L3 8.5 Z", C) + s("M3 12.5 L12 17 L21 12.5", B) + s("M3 16.5 L12 21 L21 16.5", M),
    "alternativas": c(6, 5.5, 2) + c(6, 18.5, 2) + c(18, 9, 2, A) + s("M6 7.5 V16.5 M6 13 C6 10 12 9 16 9", C),
    "opcoes": c(12, 12, 3.2) + s("M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1", W),
    "tempos": c(12, 12, 9) + s("M12 6.5 V12 L16 14", W, 2),
    "resumo": r(5, 3.5, 14, 17.5) + s("M9 3.5 V5.5 H15 V3.5", W) + s("M8 10h8M8 13.5h8M8 17h5", W, 1.5),
    "notificacoes": s("M6 16 V11 A6 6 0 0 1 18 11 V16 L19.5 18 H4.5 Z", A) + s("M10 20.5 A2 2 0 0 0 14 20.5", A),
    "alertas": s("M12 3.5 L21.5 20 H2.5 Z", R, fill=R + "22") + s("M12 9.5 V14", W, 2) + c(12, 17, 0.6, W, W),
    # ---- desenho
    "tubulacao": s("M3.5 18 L10 9.5 L15 13.5 L20.5 5", C, 2.6) + c(3.5, 18, 2.2, C, D) + c(20.5, 5, 2.2, C, D),
    "no": c(12, 12, 5.5, C, B, 2) + c(12, 12, 1.8, W, W),
    "reservatorio": r(4, 5, 16, 15, C, rx=2) + f("M5 12.5 H19 V18.5 A0.5 0.5 0 0 1 18.5 19 H5.5 A0.5 0.5 0 0 1 5 18.5 Z", B) + s("M5 12.5 q2.3 -1.6 4.6 0 t4.6 0 t4.8 0", W, 1.2),
    "captacao": s("M2.5 9 L6 19 H18 L21.5 9", C) + f("M4.4 13 H19.6 L18 19 H6 Z", B) + s("M3.5 12 q2.1-1.6 4.2 0 t4.2 0 t4.2 0 t4.2 0", W, 1.2),
    "hidrante": r(8.5, 7, 7, 13, R, R + "33", 1.6, 1) + s("M7.5 7 A4.5 3 0 0 1 16.5 7", R, 1.6) + s("M5.5 12.5 H8.5 M15.5 12.5 H18.5", R, 2.2) + s("M7 20.5 H17", W, 1.6),
    "ponto_consumo": s("M4 11 L12 4 L20 11 V20 H4 Z", C) + f("M12 10.5c1.6 2.2 2.6 3.5 2.6 4.7a2.6 2.6 0 0 1-5.2 0c0-1.2 1-2.5 2.6-4.7z", B),
    "bomba": c(12, 12, 8.5, R, R + "22") + f("M9 7.5 L17 12 L9 16.5 Z", R),
    "estacao": r(3, 5, 18, 15, M, rx=2) + c(8.5, 13.5, 3.6, R, R + "22", 1.5) + c(15.5, 13.5, 3.6, R, R + "22", 1.5) + s("M3 9 H21", M),
    "bomba_variavel": c(10, 12, 7, R, R + "22") + f("M8 9 L14 12 L8 15 Z", R) + s("M17.5 5 q1.5 2 0 4 t0 4 t0 4", A, 1.5),
    "valvula": valvula("", A),
    "prv": valvula("PRV"), "psv": valvula("PSV"), "pbv": valvula("PBV"), "fcv": valvula("FCV", G), "tcv": valvula("TCV", M), "vre": valvula("VRE", C), "vse": valvula("VSE", G),
    "gpv": valvula("GPV", V),
    "registro": s("M4 9 L12 14 L4 19 Z M20 9 L12 14 L20 19 Z", W, 1.6, fill=W + "22") + s("M12 14 V5 M8.5 5 H15.5", A, 2),
    "ponto_cotado": s("M12 4 L20 19 H4 Z", "#c49a5a", fill="#c49a5a33") + t(12, 17.5, "Z", W, 7.5),
    "borda": r(3.5, 5, 17, 14, W, rx=0.5, extra='stroke-dasharray="3 2"'),
    "texto": s("M5 5.5 H19 M12 5.5 V19.5 M9 19.5 H15", W, 2.2),
    "linha": s("M4 19 L20 5", W, 2) + c(4, 19, 1.6, C, C) + c(20, 5, 1.6, C, C),
    "medir": r(2.5, 8, 19, 8, A, A + "22", 1.6, 1) + s("M6 8v3.5M9.5 8v2M13 8v3.5M16.5 8v2M20 8v3.5", A, 1.3),
    "medir_comprimento": s("M3 12 H21 M3 12 l3-3 M3 12 l3 3 M21 12 l-3-3 M21 12 l-3 3", A, 1.8) + s("M3 6v12M21 6v12", W, 1.2),
    "medir_area": s("M4 18 L7 5 L19 8 L20 19 Z", A, fill=A + "22") + s("M7 9l9 9M5.5 13l6 6M10 6l9 9", A, 0.8),
    "selecionar": f("M6 3 L6 19 L10 15 L13 21 L15.5 20 L12.5 14 L18 14 Z", W),
    "sel_poligono": s("M4 8 L10 4 L19 7 L17 17 L8 20 Z", C, extra='stroke-dasharray="2.5 2"') + f("M11 10 V19 L13 17 L14.6 20.4 L16 19.8 L14.4 16.4 H17 Z", W),
    "sel_tipo": f("M4 3 V15 L7 12 L9.3 16.5 L11 15.8 L8.8 11.3 H13 Z", W) + s("M14 10h7M14 14h7M14 18h7", C, 1.6),
    "sel_atributo": s("M3.5 4.5 H20.5 L14 12.5 V19 L10 21 V12.5 Z", C, fill=C + "22"),
    "sel_inverter": s("M5 8 H17 L14 5 M19 16 H7 L10 19", C, 2),
    "sel_limpar": f("M4 3 V15 L7 12 L9.3 16.5 L11 15.8 L8.8 11.3 H13 Z", W) + s("M15 14 L21 20 M21 14 L15 20", R, 2),
    "excluir": s("M5 5 L19 19 M19 5 L5 19", R, 2.6),
    "localizar": LUPA,
    "mover": s("M12 3 V21 M3 12 H21 M12 3 l-3 3 M12 3 l3 3 M12 21 l-3-3 M12 21 l3-3 M3 12 l3-3 M3 12 l3 3 M21 12 l-3-3 M21 12 l-3 3", W, 1.7),
    "dividir": s("M3 12 H9 M15 12 H21", C, 2.6) + c(12, 12, 2.2, A, A) + s("M8 5 L16 19 M16 5 L8 19", W, 1.2),
    "propriedades": r(4, 3.5, 16, 17) + s("M7.5 8h3M12.5 8h4M7.5 12h3M12.5 12h4M7.5 16h3M12.5 16h4", W, 1.5),
    "prototipos": r(6, 3, 12, 7, A, A + "33", 1.6) + s("M12 10 V14 M5 14 H19 V18 H5 Z", A, 1.6) + s("M4 21 H20", W, 1.4),
    # ---- componentes
    "demanda": s("M4 7 H13 A3 3 0 0 1 16 10 V11 M4 4.5 V9.5", C, 2) + f("M16 13.5c1.4 1.9 2.2 3 2.2 4a2.2 2.2 0 0 1-4.4 0c0-1 .8-2.1 2.2-4z", B),
    "padroes": s("M3 20 V4 M3 20 H21", M, 1.4) + s("M4 15 H7 V10 H10 V6 H13 V12 H16 V8 H19 V14 H21", C, 1.8),
    "curvas": s("M3 20 V4 M3 20 H21", M, 1.4) + s("M4 6 C10 6.5 15 9 20 17", R, 2) + c(13, 9.5, 1.5, A, A),
    "controles": r(3, 8, 18, 8, C, rx=4) + c(16.5, 12, 2.6, G, G),
    "graficos": s("M3 20 V4 M3 20 H21", M, 1.4) + s("M5 16 L9 10 L13 13 L19 6", C, 2) + s("M5 18 L10 15 L14 17 L19 12", A, 1.6),
    "tabelas": r(3, 4, 18, 16) + s("M3 9 H21 M3 14 H21 M9 4 V20 M15 4 V20", C, 1.2),
    "conjuntos": r(3, 6, 13, 12, C, extra='stroke-dasharray="2.5 2"') + r(8, 3, 13, 12, W),
    "atualizar": s("M19 8 A8 8 0 1 0 20 13", C, 2) + s("M19.5 3.5 V8.5 H14.5", C, 2),
    "topologia": c(5, 6, 2) + c(19, 6, 2) + c(12, 18, 2) + s("M7 6 H17 M6 8 L11 16.5", C) + s("M18 8 L13 16.5", M, 1.6, extra='stroke-dasharray="2 2"') + c(19, 6, 2, R),
    "modelbuilder": r(10, 10, 11, 10, C) + s("M10 13.5 H21 M10 17 H21 M14.5 10 V20", C, 1) + s("M3 4 H9 V10 M9 10 L4.5 5.5 M9 10 H5", A, 1.8),
    # ---- análises
    "incendio": f("M12 2.5c1 3.5 5 5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2.5-5.5.3 1.8 1 2.6 2 3 0-3 .3-5 .5-7.5z", R) + f("M12 12c.6 1.7 2.3 2.4 2.3 4.3a2.3 2.3 0 0 1-4.6 0c0-1.1.7-1.8 1.2-2.6.3.8.7 1 1.1 1.2z", A),
    "descarga": r(4, 9, 6, 12, R, R + "33", 1.5, 1) + s("M10 13 H13", R, 2.4) + s("M14.5 10 q3 1 5 -1 M14.5 13 H20.5 M14.5 16 q3 -1 5 1", C, 1.6),
    "renovacao": s("M3 9 H21 M3 15 H21", M, 1.4) + s("M17 6 A6 6 0 1 0 18 12", G, 2) + s("M17.5 3 V6.5 H14", G, 2),
    "darwin": c(12, 12, 9) + c(12, 12, 5, A) + c(12, 12, 1.4, A, A) + s("M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4", W, 1.4),
    "dimensionar": s("M3 12 H21", C, 6) + s("M8 4 V8 M8 16 V20 M6.5 5.5 L8 4 L9.5 5.5 M6.5 18.5 L8 20 L9.5 18.5", A, 1.5),
    "energia": f("M13.5 2 L5 13.5 H11 L9.5 22 L19 9.5 H13 Z", A),
    "zonas_pressao": s("M3 4 H11 V11 H3 Z", B, fill=B + "44") + s("M13 4 H21 V11 H13 Z", G, fill=G + "44") + s("M3 13 H21 V20 H3 Z", A, fill=A + "44"),
    "criticidade": s("M3 12 H9.5 L11 9 L13 15 L14.5 12 H21", C, 2.4) + s("M9.5 12 L11 9", R, 2.4),
    "mais": c(5, 12, 1.6, W, W) + c(12, 12, 1.6, W, W) + c(19, 12, 1.6, W, W),
    "qualidade": f(GOTA, B) + s("M12 9.5 V13.5 L14.5 15", W, 1.6),
    "cloro": f(GOTA, G) + t(12, 16.5, "Cl", D, 7.5),
    "dados": s("M5 6 C5 3.5 19 3.5 19 6 V18 C19 20.5 5 20.5 5 18 Z", C) + s("M5 6 C5 8.5 19 8.5 19 6 M5 12 C5 14.5 19 14.5 19 12", C, 1.4),
    "consultas": s("M4 5h8M4 9h6M4 13h5", W, 1.6) + c(14.5, 14, 4.5) + s("M17.8 17.3 L21 20.5", C, 2.2),
    "navegador": c(12, 12, 9) + f("M12 5 L14.5 12 L12 19 L9.5 12 Z", A) + c(12, 12, 1.3, D, D),
    "contornos": s("M3 17 C7 12 10 18 14 13 S20 9 21 10", C, 1.6) + s("M3 12 C6 7 10 13 13 8 S19 4 21 5", B, 1.6) + s("M3 21 C8 17 13 22 21 16", M, 1.4),
    "aovivo": c(12, 13, 2.2, G, G) + s("M8 9 A5.6 5.6 0 0 0 8 17 M16 9 A5.6 5.6 0 0 1 16 17 M5 6 A10 10 0 0 0 5 20 M19 6 A10 10 0 0 1 19 20", G, 1.6),
    "zonas": s("M3 6 L9 3 L15 6 L21 3 V18 L15 21 L9 18 L3 21 Z", C) + s("M9 3 V18 M15 6 V21", C, 1.2),
    "bibliotecas": r(3.5, 4, 4, 16, C, rx=0.6) + r(8.5, 4, 4, 16, A, rx=0.6) + s("M14 5.5 L17.8 4.5 L21 19.5 L17.2 20.5 Z", G),
    "perdas": s("M4 20 V12 A6 6 0 0 1 10 6 H20", C, 4) + s("M4 20 V12 A6 6 0 0 1 10 6 H20", D, 1.2),
    "extensoes": r(3, 4, 13, 16) + s("M3 9 H16 M3 14 H16", C, 1.2) + s("M19 13 V21 M15 17 H23", G, 2),
    "comparar": r(3, 4, 8, 16, C) + r(13, 4, 8, 16, A) + s("M5.5 15h3M5.5 11h3M15.5 9h3M15.5 13h3", W, 1.4),
    "rastreio": s("M4.5 12 A7.5 7.5 0 1 0 7 6.4", C, 2) + s("M3.5 4 V8.5 H8", C, 2) + s("M12 8 V12.5 L15 14.5", W, 1.8),
    "rastreio_ver": r(4, 3.5, 16, 17) + c(9, 9, 3, A, w=1.5) + s("M9 7.6 V9 L10 9.8", A, 1.2) + s("M8 15h8M8 18h6", W, 1.4),
    "arquivar": r(3, 4, 18, 5, A, A + "33") + s("M4.5 9 V20 H19.5 V9", A) + s("M9.5 12.5 H14.5", W, 2),
    # ---- exibir
    "zoom_total": s("M4 9 V4 H9 M15 4 H20 V9 M20 15 V20 H15 M9 20 H4 V15", W, 2) + r(8, 8, 8, 8, C),
    "zoom_mais": LUPA + s("M7.5 10 H12.5 M10 7.5 V12.5", W, 1.6),
    "zoom_menos": LUPA + s("M7.5 10 H12.5", W, 1.6),
    "pan": s("M8 13 V6.5 a1.4 1.4 0 0 1 2.8 0 V11 M10.8 11 V4.8 a1.4 1.4 0 0 1 2.8 0 V11 M13.6 11 V6 a1.4 1.4 0 0 1 2.8 0 V12 M16.4 11 V8.5 a1.4 1.4 0 0 1 2.8 0 V15 C19.2 19 16.5 21.5 13 21.5 C10 21.5 8.5 20 7 17.5 L4.6 13.4 a1.4 1.4 0 0 1 2.4 -1.4 L8 13.5", W, 1.4),
    "zoom_anterior": s("M10 6 L4 12 L10 18 M4 12 H20", C, 2.2),
    "zoom_proximo": s("M14 6 L20 12 L14 18 M20 12 H4", C, 2.2),
    "zoom_selecao": r(4, 4, 16, 16, A, extra='stroke-dasharray="2.5 2"') + c(12, 12, 3, C) + s("M12 6 V9 M12 15 V18 M6 12 H9 M15 12 H18", C, 1.4),
    "vistas": s("M6 3.5 H18 V21 L12 16.5 L6 21 Z", A, fill=A + "33"),
    "vista_aerea": r(3, 4, 18, 16) + r(10, 9, 7, 6, A, A + "33", 1.5) + s("M5 17 L9 12 L12 14 L16 7", C, 1.2),
    "simbologia": s("M12 3 A9 9 0 1 0 12 21 C13.5 21 14 19.5 13 18.3 C12 17 13 15.5 14.5 15.5 H17 A4 4 0 0 0 21 11.5 C21 6.8 17 3 12 3 Z", W, 1.6) + c(7.5, 11, 1.4, R, R) + c(10, 7, 1.4, A, A) + c(15, 7.5, 1.4, G, G) + c(17, 11, 1.4, C, C),
    "fundos": c(12, 12, 9) + s("M3 12 H21 M12 3 C8.5 7 8.5 17 12 21 C15.5 17 15.5 7 12 3", C, 1.3),
    "rotulos": s("M3.5 4 H12 L20.5 12.5 L12.5 20.5 L3.5 11.5 Z", A, fill=A + "22") + c(8, 8.5, 1.5, A, A),
    "perfis": f("M3 20 L3 14 L8 11 L13 15 L18 10 L21 12 V20 Z", "#6b4f2a") + s("M3 7 L21 9", C, 2) + s("M3 14 L8 11 L13 15 L18 10 L21 12", "#c49a5a", 1.4),
    "grafico_rapido": s("M3 20 V4 M3 20 H21", M, 1.4) + s("M5 15 L9 9 L13 12 L19 5", C, 2) + f("M14 12 V22 L16.5 19.5 L18.5 23.3 L20 22.6 L18.1 18.8 H21.5 Z", W),
    "camadas": s("M12 4 L21 8.5 L12 13 L3 8.5 Z", C, fill=C + "22") + s("M3 12.5 L12 17 L21 12.5 M3 16.5 L12 21 L21 16.5", C),
    # ---- ferramentas
    "cotas": f("M2 20 L8.5 9 L12 14 L15.5 7 L22 20 Z", "#6b4f2a") + s("M2 20 L8.5 9 L12 14 L15.5 7 L22 20", "#c49a5a", 1.4) + t(18.5, 8, "Z", A, 7),
    "loadbuilder": s("M3 10 L7 6.5 L11 10 V15 H3 Z", W, 1.4) + c(18, 16, 3, C, B) + s("M11 12.5 L15 15", A, 1.8, extra='stroke-dasharray="2 1.6"'),
    "thiessen": s("M3 3 H21 V21 H3 Z", M, 1.2) + s("M3 11 L9 9 L12 3 M9 9 L11 15 L3 18 M11 15 L17 14 L21 9 M17 14 L19 21 M12 3 L17 6 L21 9", C, 1.5),
    "ids": s("M9 3.5 L7 20.5 M17 3.5 L15 20.5 M4 8.5 H20.5 M3.5 15.5 H20", C, 2),
    "externas": r(3.5, 6.5, 14, 14, W) + s("M13 3.5 H20.5 V11 M20.5 3.5 L11 13", C, 2),
    "qgis": c(11, 11, 7.5, G) + s("M15.5 15.5 L21 21", G, 2.6) + c(11, 11, 3, G, G),
    "epanet": s("M3 12 H21", B, 5) + t(12, 15.5, "E", W, 9.5),
    "pasta": s("M3 7 V19 H21 V9 H11.5 L9.5 7 Z", A, fill=A + "22"),
    "esqueletizar": c(4, 12, 1.8) + c(20, 12, 1.8) + c(12, 5, 1.8, M) + c(12, 19, 1.8, M) + s("M5.8 12 H18.2", C, 2) + s("M5.6 11 L10.4 6 M5.6 13 L10.4 18", M, 1.3, extra='stroke-dasharray="2 2"'),
    "cores": r(3, 4, 18, 4, R, R) + r(3, 10, 18, 4, A, A) + r(3, 16, 18, 4, G, G),
    "limpar": s("M14 4 L20.5 10.5 L11 20 H6 L3.5 17.5 Z", R, fill=R + "22") + s("M9 9 L15.5 15.5 M11 20 H20.5", W, 1.4),
    "exportar": s("M12 15 V3 M7.5 7.5 L12 3 L16.5 7.5", C, 2) + s("M4 13 V20 H20 V13", W, 1.8),
    "importar": s("M12 3 V15 M7.5 10.5 L12 15 L16.5 10.5", C, 2) + s("M4 13 V20 H20 V13", W, 1.8),
    "ajuda": c(12, 12, 9) + s("M9.2 9.3 A2.8 2.8 0 1 1 12 12.3 V14", W, 2) + c(12, 17.2, 0.7, W, W),
    "relatorio": s("M6 3 H14.5 L19 7.5 V21 H6 Z", W) + s("M14.5 3 V7.5 H19", W) + s("M9 12h7M9 15h7M9 18h4", C, 1.5),
    "inventario": r(3, 12, 8, 8, A) + r(13, 12, 8, 8, A) + r(8, 4, 8, 8, C),
    "inventario_tubos": s("M3 7 H21", C, 4) + s("M3 13 H16", B, 4) + s("M3 19 H11", M, 4),
    # ---- arquivo e telas
    "novo": s("M6 3 H14.5 L19 7.5 V21 H6 Z", W) + s("M14.5 3 V7.5 H19", W) + s("M12.5 11 V18 M9 14.5 H16", G, 2),
    "abrir": s("M3 7 V19 H18 L21 11 H7.5 L5 19", A) + s("M3 7 H9 L11 9 H17 V11", A),
    "salvar": s("M4 4 H17 L20 7 V20 H4 Z", C) + r(8, 4, 8, 5, C, w=1.4, rx=0.5) + r(7, 13, 10, 7, W, w=1.4, rx=0.5),
    "desfazer": s("M9 5 L4 10 L9 15 M4 10 H14 A6 6 0 0 1 14 22", C, 2),
    "refazer": s("M15 5 L20 10 L15 15 M20 10 H10 A6 6 0 0 0 10 22", C, 2),
    "sair": s("M14 4 H20 V20 H14", W) + s("M10 8 L6 12 L10 16 M6 12 H16", R, 2),
    "painel": r(2.5, 4, 19, 13, C) + s("M8 21 H16 M12 17 V21", C) + s("M5.5 13 L9 9.5 L12 11.5 L16 7.5 L18.5 9", G, 1.6),
    "mapa": s("M12 21 C7 15 5 12 5 9 A7 7 0 0 1 19 9 C19 12 17 15 12 21 Z", R, fill=R + "22") + c(12, 9, 2.5, W),
    "calibracao": s("M4 17 A8.5 8.5 0 1 1 20 17", C, 2) + s("M12 14.5 L16.5 8.5", A, 2.2) + c(12, 14.5, 1.6, A, A),
    "atributos": r(4, 3.5, 16, 17) + s("M7.5 8h3M12.5 8h4M7.5 12h3M12.5 12h4M7.5 16h3M12.5 16h4", W, 1.5),
    "simular": c(12, 12, 9.5, G, G + "33") + f("M10 7.5 L16.5 12 L10 16.5 Z", G),
}


# ---- símbolos dos elementos (mapa claro e painel escuro): contorno escuro, cor por tipo
K = "#0b1f3a"


def _valv(cor):
    return s("M3.5 6 L12 12 L3.5 18 Z M20.5 6 L12 12 L20.5 18 Z", K, 1.3, fill=cor)


ELEMENTOS = {
    "elem_tubulacao": s("M3 12 H21", K, 6) + s("M3 12 H21", "#1c7ed6", 3.6),
    "elem_tubulacao_fechada": s("M3 12 H21", "#868e96", 3, extra='stroke-dasharray="3 2.5"'),
    "elem_tubulacao_cv": s("M3 12 H21", "#ae3ec9", 3.4) + f("M10 7 L16 12 L10 17 Z", "#ae3ec9"),
    "elem_no": c(12, 12, 5, K, "#1c4f8a", 1.4),
    "elem_consumo": c(12, 12, 6, K, "#1c7ed6", 1.4) + c(12, 12, 2.2, "#ffffff", "#ffffff", 0.5),
    "elem_hidrante": r(8, 7, 8, 13, K, "#e5484d", 1.3, 1) + s("M7 7 A5 3.5 0 0 1 17 7", K, 1.3, fill="#e5484d") +
                     s("M5 13 H8 M16 13 H19", K, 2.4),
    "elem_ponta": r(7, 7, 10, 10, K, "#9aa5b1", 1.3, 1),
    "elem_reservatorio": r(4, 4, 16, 16, K, "#ffffff", 1.4, 2) + f("M5 11.5 H19 V18.5 A0.5 0.5 0 0 1 18.5 19 H5.5 A0.5 0.5 0 0 1 5 18.5 Z", "#1d8fd6"),
    "elem_captacao": s("M2.5 6 L6.5 19 H17.5 L21.5 6 Z", K, 1.4, fill="#0ca678") + s("M5 11 q1.8-1.4 3.5 0 t3.5 0 t3.5 0 t3.5 0", "#ffffff", 1.2),
    "elem_bomba": c(12, 12, 8.5, K, "#e5484d", 1.4) + f("M9.3 7.6 L16.8 12 L9.3 16.4 Z", "#ffffff"),
    "elem_prv": _valv("#2fb36f"), "elem_psv": _valv("#1c7ed6"), "elem_pbv": _valv("#ae3ec9"),
    "elem_fcv": _valv("#f59f00"), "elem_tcv": _valv("#adb5bd"),
    "elem_vre": _valv("#15aabf"), "elem_vse": _valv("#74b816"), "elem_gpv": _valv("#a0522d"),
    "elem_valvula": _valv("#ffd43b"),
    "elem_registro": s("M3.5 9 L12 14 L3.5 19 Z M20.5 9 L12 14 L20.5 19 Z", K, 1.3, fill="#ffffff") + s("M12 14 V4 M8 4 H16", K, 2.2),
    "elem_ponto_cotado": s("M12 4 L20.5 19.5 H3.5 Z", K, 1.3, fill="#c49a5a"),
}
ICONES.update(ELEMENTOS)
# os ilustrados (equipamentos e ações principais, com cores próprias) substituem os de traço
from _ilustrados import ILUSTRADOS  # noqa: E402
ICONES.update(ILUSTRADOS)


def gravar():
    n = 0
    for nome, corpo in ICONES.items():
        if not corpo:
            continue
        with open(os.path.join(AQUI, nome + ".svg"), "w", encoding="utf-8") as fh:
            fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{corpo}</svg>')
        n += 1
    return n


if __name__ == "__main__":
    print(gravar(), "ícones gravados")
