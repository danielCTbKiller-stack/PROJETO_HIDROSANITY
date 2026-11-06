"""Teste dos Dados recebidos (motor/dados_recebidos.py) com planilhas no formato que costuma chegar.

Gera em testes/dados_exemplo/ cinco planilhas de 3 dias (passo de 15 min) de um sistema com perda
conhecida de 5% (a entrada da captação é 5% maior do que consumo + variação do reservatório):
  captacao.csv      ';' e vírgula decimal, data dd/mm/aaaa hh:mm, vazão em m³/h, pressão de entrada
  reservatorio.xlsx datas do Excel (número de série com formato de data), nível e volume
  elevatoria.csv    data e hora em colunas separadas, pressões em kgf/cm², uma lacuna de 3 h
  za.csv            ',' e ponto decimal, data ISO, um pico absurdo
  zb.xlsx           texto de data dd/mm/aaaa, consumo em L/s
Depois importa como a tela faz e confere: conversões de unidade, lacuna, pico e balanço ≈ 5%.

Uso:  python teste_dados_recebidos.py
"""
import base64
import math
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "motor"))
import dados_recebidos as dr  # noqa: E402

PASTA = os.path.join(AQUI, "dados_exemplo")
os.makedirs(PASTA, exist_ok=True)
falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# ---------------------------------------------------------------- sistema sintético
t0 = datetime(2026, 10, 1, 0, 0)
N = 3 * 96
AREA = 200.0  # m² do reservatório
tempos, za, zb, ent, vol = [], [], [], [], []
v = 800.0
for i in range(N):
    h = (i % 96) / 4
    a = 8 + 4 * math.sin((h - 6) / 24 * 2 * math.pi)       # L/s
    b = 12 + 5 * math.sin((h - 7) / 24 * 2 * math.pi)
    e = 21.5 + 1.5 * math.sin(h / 24 * 2 * math.pi)
    tempos.append(t0 + timedelta(minutes=15 * i))
    za.append(a)
    zb.append(b)
    ent.append(e)
    vol.append(v)
    v += (0.95 * e - a - b) * 900 / 1000                       # 5% da entrada se perde


def br(x, d=2):
    return f"{x:.{d}f}".replace(".", ",")


with open(os.path.join(PASTA, "captacao.csv"), "w", encoding="utf-8") as f:
    f.write("Data/Hora;Vazão (m³/h);Pressão (mca)\n")
    for t, e in zip(tempos, ent):
        f.write(f"{t:%d/%m/%Y %H:%M};{br(e * 3.6)};{br(18 + 0.5 * math.sin(t.hour))}\n")
with open(os.path.join(PASTA, "elevatoria.csv"), "w", encoding="utf-8") as f:
    f.write("DATA;HORA;P_SUCCAO;P_RECALQUE;VAZAO\n")
    for i, (t, a) in enumerate(zip(tempos, za)):
        if 100 <= i < 112:  # 3 h sem comunicação
            continue
        f.write(f"{t:%d/%m/%Y};{t:%H:%M};{br(0.35, 3)};{br(4.6 + 0.02 * a, 3)};{br(a)}\n")
with open(os.path.join(PASTA, "za.csv"), "w", encoding="utf-8") as f:
    f.write("timestamp,consumo_ls\n")
    for i, (t, a) in enumerate(zip(tempos, za)):
        f.write(f"{t:%Y-%m-%dT%H:%M:%S},{(950.0 if i == 150 else a):.3f}\n")


def xlsx(caminho, cab, linhas, col_data_excel):
    """.xlsx mínimo (zip + XML), com a coluna de data como número de série do Excel quando pedido."""
    comp = list(dict.fromkeys(str(c) for c in cab))
    idx = {c: i for i, c in enumerate(comp)}

    def col(n):
        s = ""
        n += 1
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s
    rows = ['<row r="1">' + "".join(f'<c r="{col(j)}1" t="s"><v>{idx[str(c)]}</v></c>' for j, c in enumerate(cab)) + "</row>"]
    for i, lin in enumerate(linhas, start=2):
        cel = []
        for j, x in enumerate(lin):
            if isinstance(x, datetime) and col_data_excel:
                serial = (x - datetime(1899, 12, 30)).total_seconds() / 86400
                cel.append(f'<c r="{col(j)}{i}" s="1"><v>{serial}</v></c>')
            elif isinstance(x, (int, float)):
                cel.append(f'<c r="{col(j)}{i}"><v>{x}</v></c>')
            else:
                txt = x.strftime("%d/%m/%Y %H:%M") if isinstance(x, datetime) else str(x)
                cel.append(f'<c r="{col(j)}{i}" t="inlineStr"><is><t>{txt}</t></is></c>')
        rows.append(f'<row r="{i}">' + "".join(cel) + "</row>")
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Leituras" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
        z.writestr("xl/styles.xml", f'<?xml version="1.0"?><styleSheet {ns}><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy hh:mm"/></numFmts>'
                   '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164" applyNumberFormat="1"/></cellXfs></styleSheet>')
        z.writestr("xl/sharedStrings.xml", f'<?xml version="1.0"?><sst {ns} count="{len(comp)}">' +
                   "".join(f"<si><t>{c}</t></si>" for c in comp) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0"?><worksheet {ns}><sheetData>' + "".join(rows) +
                   "</sheetData></worksheet>")


xlsx(os.path.join(PASTA, "reservatorio.xlsx"), ["Data", "Nível (m)", "Volume (m³)"],
     [[t, round(vv / AREA, 3), round(vv, 2)] for t, vv in zip(tempos, vol)], col_data_excel=True)
xlsx(os.path.join(PASTA, "zb.xlsx"), ["Data", "Consumo ZB (L/s)"],
     [[t, round(b, 3)] for t, b in zip(tempos, zb)], col_data_excel=False)

# ---------------------------------------------------------------- importação como a tela faz
arq = os.path.join(tempfile.mkdtemp(), "teste_dados_recebidos.json")


def b64(nome):
    with open(os.path.join(PASTA, nome), "rb") as f:
        return base64.b64encode(f.read()).decode()


def importar(el, nome, unidades=None):
    p = dr.ler_planilha(nome, b64(nome))
    mapa = dr.sugerir(el, p["colunas"])
    print(f"    {el}: colunas {p['colunas']} -> {mapa}")
    return dr.importar(arq, el, nome, b64(nome), mapa, unidades), mapa


r, m = importar("captacao", "captacao.csv", {"vazao_entrada": "m³/h"})
checar(m.get("vazao_entrada") == "Vazão (m³/h)" and m.get("pressao_entrada") == "Pressão (mca)", "captação: de-para automático")
checar(abs(r["series"]["vazao_entrada"]["media"] - sum(ent) / N) < 0.01, f"m³/h convertido para L/s (média {r['series']['vazao_entrada']['media']} L/s)")
r, m = importar("reservatorio", "reservatorio.xlsx")
checar(r["series"]["volume"]["n"] == N and r["series"]["volume"]["passo_min"] == 15.0, f"xlsx com datas do Excel: {r['series']['volume']['n']} leituras de 15 min")
r, m = importar("elevatoria", "elevatoria.csv", {"pressao_montante": "kgf/cm²", "pressao_jusante": "kgf/cm²"})
checar(m.get("hora") == "HORA" and m.get("pressao_montante") == "P_SUCCAO" and m.get("pressao_jusante") == "P_RECALQUE",
       f"elevatória: data e hora separadas, sucção/recalque reconhecidos")
checar(abs(r["series"]["pressao_montante"]["media"] - 3.5) < 0.01, f"kgf/cm² convertido para mca ({r['series']['pressao_montante']['media']})")
checar(r["series"]["vazao"]["lacunas"] == 1 and abs(r["series"]["vazao"]["horas_sem_dado"] - 3.0) < 0.01,
       f"lacuna de 3 h encontrada: {r['series']['vazao']['alertas']}")
r, m = importar("za", "za.csv")
checar(r["series"]["consumo"]["fora_do_padrao"] == 1, f"pico absurdo encontrado: {r['series']['consumo']['alertas']}")
r, m = importar("zb", "zb.xlsx")
checar(r["series"]["consumo"]["n"] == N, "xlsx com data em texto dd/mm/aaaa")

an = dr.analisar(dr.carregar(arq))
b = an["balanco"]
print(f"    balanço: {{{', '.join(f'{k}: {v}' for k, v in b.items() if k != 'serie')}}}")
# o pico de 950 L/s na ZA distorce um passo; o resto fecha em ~5%
checar(b.get("com_volume") and 3.0 < b["residuo_pct"] < 7.0, f"balanço hídrico mostra a perda de ~5%: {b['residuo_pct']}%")
checar(abs(b.get("elevatoria_x_za_pct", 99)) < 3, f"elevatória × consumo ZA: {b.get('elevatoria_x_za_pct')}%")
dr.excluir(arq, "za")
checar("za" not in dr.carregar(arq), "excluir os dados de um elemento")

# ---------------------------------------------------------------- dias digitados hora a hora (janela de 24 h)
arq2 = os.path.join(tempfile.mkdtemp(), "teste_digitado.json")
hora = [i for i in range(N) if i % 4 == 0][:48]  # dois dias, uma leitura por hora
for dia, fatia in (("2026-10-01", hora[:24]), ("2026-10-02", hora[24:])):
    dr.digitar(arq2, "captacao", dia, {"vazao_entrada": [br(ent[i] * 3.6) for i in fatia]}, {"vazao_entrada": "m³/h"})
    dr.digitar(arq2, "za", dia, {"consumo": [round(za[i], 3) for i in fatia]})
    dr.digitar(arq2, "zb", dia, {"consumo": [round(zb[i], 3) for i in fatia]})
    dr.digitar(arq2, "reservatorio", dia, {"nivel": [None] * 24, "volume": [round(vol[i], 2) for i in fatia]})
tudo = dr.carregar(arq2)
checar(len(tudo["captacao"]["series"]["vazao_entrada"]["dados"]) == 48 and "nivel" not in tudo["reservatorio"]["series"],
       "dois dias de 24 leituras gravados (nível em branco não entra)")
checar(abs(tudo["captacao"]["series"]["vazao_entrada"]["dados"][0][1] - ent[0]) < 0.01, "m³/h digitado vira L/s")
b = dr.analisar(tudo)["balanco"]
print(f"    balanço digitado: {{{', '.join(f'{k}: {v}' for k, v in b.items() if k != 'serie')}}}")
checar(b.get("passo_min") == 60 and 3.0 < b["residuo_pct"] < 7.0, f"balanço com passo de 1 h mostra a perda de ~5%: {b.get('residuo_pct')}%")
esperado = sum(ent[i] for i in hora) * 3.6  # L/s × 3600 s / 1000
checar(abs(b["entrada_m3"] - esperado) < 1, f"volume de entrada em m³ com passo de 1 h ({b['entrada_m3']} × {esperado:.1f})")
# redigitar um dia substitui só aquele dia; tudo em branco apaga o dia
dr.digitar(arq2, "za", "2026-10-02", {"consumo": [5] * 24})
s = dr.carregar(arq2)["za"]["series"]["consumo"]["dados"]
checar(len(s) == 48 and s[0][1] != 5 and s[-1][1] == 5, "redigitar o 2º dia troca só o 2º dia")
dr.digitar(arq2, "za", "2026-10-02", {"consumo": [None] * 24})
checar(len(dr.carregar(arq2)["za"]["series"]["consumo"]["dados"]) == 24, "dia em branco sai dos dados")
try:
    dr.digitar(arq2, "za", "2026-10-03", {"consumo": [1] * 23})
    checar(False, "23 leituras deveriam dar erro")
except ValueError as e:
    checar("24" in str(e), f"pede as 24 leituras: {e}")

print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
