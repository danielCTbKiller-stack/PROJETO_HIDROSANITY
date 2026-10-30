"""Gera um DXF de exemplo: casa de 10 x 6 m com banheiro, cozinha e área de serviço."""
import sys

import ezdxf

H = 2.7
Y = 2.9  # a tubulação corre rente à parede dos fundos dos cômodos molhados


def build(path: str) -> None:
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6  # metros
    msp = doc.modelspace()

    def pipe(dn, a, b):
        layer = f"AF_TUBO_{dn}"
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line(a, b, dxfattribs={"layer": layer})

    # Paredes externas e divisórias
    for a, b in [((0, 0), (10, 0)), ((10, 0), (10, 6)), ((10, 6), (0, 6)), ((0, 6), (0, 0)),
                 ((0, 3), (10, 3)), ((3, 0), (3, 3)), ((7, 0), (7, 3))]:
        msp.add_line(a, b, dxfattribs={"layer": "AF_PAREDE"})

    # Cômodos
    for name, (x0, y0, x1, y1) in {"Banheiro": (0, 0, 3, 3), "Cozinha": (3, 0, 7, 3),
                                   "Area_de_servico": (7, 0, 10, 3), "Quarto": (0, 3, 10, 6)}.items():
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                           dxfattribs={"layer": f"AF_COMODO_{name}"})

    # Tronco a partir da fonte (reservatório) e derivações
    S = (5, Y, 2.5)
    pipe(32, S, (4.5, Y, 2.5))                 # S -> K1
    pipe(32, (4.5, Y, 2.5), (3.5, Y, 2.5))     # K1 -> J1 (rumo ao banheiro)
    pipe(25, (3.5, Y, 2.5), (2.0, Y, 2.5))     # J1 -> J2
    pipe(20, (2.0, Y, 2.5), (2.0, Y, 2.1))     # J2 -> chuveiro
    pipe(25, (2.0, Y, 2.5), (1.0, Y, 2.5))     # J2 -> J3
    pipe(20, (1.0, Y, 2.5), (1.0, Y, 0.3))     # J3 -> bacia
    pipe(20, (1.0, Y, 2.5), (0.5, Y, 2.5))     # J3 -> L1
    pipe(20, (0.5, Y, 2.5), (0.5, Y, 0.9))     # L1 -> lavatório
    pipe(25, (4.5, Y, 2.5), (4.5, Y, 0.9))     # K1 -> pia da cozinha
    pipe(32, S, (7.5, Y, 2.5))                 # S -> J4 (rumo à área de serviço)
    pipe(25, (7.5, Y, 2.5), (7.5, Y, 0.9))     # J4 -> máquina de lavar
    pipe(25, (7.5, Y, 2.5), (9.0, Y, 2.5))     # J4 -> J5
    pipe(20, (9.0, Y, 2.5), (9.0, Y, 0.9))     # J5 -> tanque

    msp.add_blockref("FONTE", S, dxfattribs={"layer": "AF_FONTE"})
    for name, p in [("chuveiro_eletrico", (2.0, Y, 2.1)), ("bacia_sanitaria_cx_acoplada", (1.0, Y, 0.3)),
                    ("lavatorio", (0.5, Y, 0.9)), ("pia_cozinha", (4.5, Y, 0.9)),
                    ("maquina_lavar", (7.5, Y, 0.9)), ("pia_cozinha", (9.0, Y, 0.9))]:  # o último é o tanque
        msp.add_blockref(name, p, dxfattribs={"layer": "AF_APARELHO"})
    # Registros: geral da área de serviço (gaveta) e do banheiro (gaveta)
    msp.add_blockref("registro_gaveta", (7.5, Y, 2.5), dxfattribs={"layer": "AF_CONEXAO"})
    msp.add_blockref("registro_gaveta", (3.5, Y, 2.5), dxfattribs={"layer": "AF_CONEXAO"})
    doc.saveas(path)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "casa_exemplo.dxf")
