"""Dados recebidos: séries de campo (SABESP, SCADA, loggers) analisadas ANTES de entrar no modelo.

Sistema padrão: captação -> reservatório -> ZB (gravidade) e reservatório -> elevatória/booster -> ZA.
Cada elemento recebe os dados digitados hora a hora (24 leituras por dia, digitar()) ou uma planilha
(CSV ou XLSX, importar()), com uma coluna de data/hora e as colunas das grandezas:

  captacao     vazao_entrada (L/s), pressao_entrada (mca, opcional)
  reservatorio nivel (m), volume (m³)
  elevatoria   pressao_montante, pressao_jusante (mca), vazao (L/s)
  za, zb       consumo (L/s)

As séries ficam em <cadastro>_dados_recebidos.json, ao lado do cadastro (não mexem no modelo).
A análise mostra período, passo, lacunas, valores suspeitos e o balanço hídrico do sistema:
  entrada da captação − (consumo ZA + consumo ZB) − variação de volume do reservatório ≈ 0.
O .xlsx é lido direto do arquivo (zip + XML), sem depender de biblioteca de Excel.
"""
import base64
import csv
import io
import json
import math
import os
import re
import unicodedata
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

ELEMENTOS = {
    "captacao": ("Captação", [("vazao_entrada", "Vazão de entrada", "vazao"), ("pressao_entrada", "Pressão de entrada", "pressao")]),
    "reservatorio": ("Reservatório", [("nivel", "Nível", "nivel"), ("volume", "Volume", "volume")]),
    "elevatoria": ("Elevatória / booster", [("pressao_montante", "Pressão montante", "pressao"),
                                             ("pressao_jusante", "Pressão jusante", "pressao"), ("vazao", "Vazão", "vazao")]),
    "za": ("ZA · zona alta", [("consumo", "Consumo", "vazao")]),
    "zb": ("ZB · zona baixa", [("consumo", "Consumo", "vazao")]),
}
# unidade de leitura -> fator para a unidade do GWATER (L/s, mca, m, m³)
UNIDADES = {
    "vazao": {"L/s": 1.0, "m³/h": 1000 / 3600, "m³/s": 1000.0, "m³/dia": 1000 / 86400},
    "pressao": {"mca": 1.0, "kgf/cm²": 10.0, "bar": 10.197, "kPa": 0.10197},
    "nivel": {"m": 1.0, "cm": 0.01, "%": None},  # % fica em %
    "volume": {"m³": 1.0, "L": 0.001},
}
SINONIMOS = {
    "data": ["data", "datahora", "data_hora", "timestamp", "date", "datetime", "dt", "horario", "hora_data", "tempo"],
    "hora": ["hora", "time", "hh_mm"],
    "vazao_entrada": ["vazao_entrada", "vazao", "q_entrada", "qe", "q", "entrada", "vazao_l_s", "fluxo"],
    "pressao_entrada": ["pressao_entrada", "pressao", "p_entrada", "pe", "p"],
    "nivel": ["nivel", "nivel_m", "lamina", "altura", "level", "na", "nivel_reservatorio"],
    "volume": ["volume", "vol", "volume_m3", "v"],
    "pressao_montante": ["pressao_montante", "p_montante", "montante", "succao", "p_succao", "pm"],
    "pressao_jusante": ["pressao_jusante", "p_jusante", "jusante", "recalque", "p_recalque", "pj"],
    "vazao": ["vazao", "q", "vazao_recalque", "q_bombeada", "vazao_l_s"],
    "consumo": ["consumo", "vazao", "q", "demanda", "consumo_l_s", "vazao_distribuida"],
}


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


# ---------------------------------------------------------------- leitura de planilhas
def _xlsx(dados, aba=None):
    """Lê uma aba de .xlsx (zip + XML) -> (nomes das abas, linhas [[valor...]])."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    z = zipfile.ZipFile(io.BytesIO(dados))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    alvo = {r.get("Id"): r.get("Target") for r in rels}
    abas = [(s.get("name"), alvo[s.get("{%s}id" % ns["r"])]) for s in wb.find("m:sheets", ns)]
    nome, caminho = next(((n, c) for n, c in abas if n == aba), abas[0])
    caminho = caminho.lstrip("/")
    caminho = caminho if caminho.startswith("xl/") else "xl/" + caminho
    comp = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            comp.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    # estilos de data: números com formato de data viram data/hora
    datas = set()
    if "xl/styles.xml" in z.namelist():
        st = ET.fromstring(z.read("xl/styles.xml"))
        fmts = {int(f.get("numFmtId")): f.get("formatCode", "") for f in st.iter("{%s}numFmt" % ns["m"])}
        xfs = st.find("m:cellXfs", ns)
        for i, xf in enumerate(xfs if xfs is not None else []):
            fid = int(xf.get("numFmtId", 0))
            cod = fmts.get(fid, "")
            if 14 <= fid <= 22 or 45 <= fid <= 47 or re.search(r"(?<!\[)[dmyhs]{1,4}", cod.lower().replace("general", "")):
                datas.add(i)
    linhas = []
    for row in ET.fromstring(z.read(caminho)).iter("{%s}row" % ns["m"]):
        lin = {}
        for c in row.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r")).group(1)
            col = 0
            for ch in ref:
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", ns)
            if t == "s" and v is not None:
                val = comp[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            elif v is None:
                val = None
            elif t in ("str", "b", "e"):
                val = v.text
            else:
                val = float(v.text)
                if int(c.get("s", 0)) in datas:
                    val = (datetime(1899, 12, 30) + timedelta(days=val)).strftime("%Y-%m-%d %H:%M:%S")
            lin[col - 1] = val
        if lin:
            linhas.append([lin.get(i) for i in range(max(lin) + 1)])
    return [n for n, _ in abas], nome, linhas


def _csv(dados):
    for cod in ("utf-8-sig", "latin-1"):
        try:
            txt = dados.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    amostra = txt[:5000]
    sep = max([";", "\t", ","], key=amostra.count)
    return [l for l in csv.reader(io.StringIO(txt), delimiter=sep) if any(x.strip() for x in l)]


def ler_planilha(nome, conteudo_b64, aba=None):
    """-> {"abas", "aba", "colunas", "linhas" (prévia), "n"}: a 1ª linha não vazia é o cabeçalho."""
    dados = base64.b64decode(conteudo_b64)
    ext = os.path.splitext(nome.lower())[1]
    abas, aba_ok = [], None
    if ext in (".xlsx", ".xlsm"):
        abas, aba_ok, linhas = _xlsx(dados, aba)
    elif ext == ".xls":
        raise ValueError("arquivo .xls (Excel antigo): abra no Excel e salve como .xlsx ou .csv")
    else:
        linhas = _csv(dados)
    if not linhas:
        raise ValueError("a planilha está vazia")
    cab = [str(c).strip() if c not in (None, "") else f"coluna {i + 1}" for i, c in enumerate(linhas[0])]
    corpo = [l + [None] * (len(cab) - len(l)) for l in linhas[1:]]
    return {"abas": abas, "aba": aba_ok, "colunas": cab, "linhas": corpo, "n": len(corpo)}


def sugerir(elemento, colunas):
    """De-para automático: {"data": col, "hora": col|None, grandeza: col}."""
    nc = {_norm(c): c for c in colunas}
    out = {}
    usados = set()
    chaves = ["data", "hora"] + [g for g, _, _ in ELEMENTOS[elemento][1]]
    for chave in chaves:
        for cand in [chave] + SINONIMOS.get(chave, []):
            achou = next((c for n, c in nc.items() if (n == cand or n.startswith(cand + "_")) and c not in usados), None)
            if achou:
                out[chave] = achou
                usados.add(achou)
                break
    if "data" not in out and colunas:
        out["data"] = colunas[0]
    if out.get("hora") == out.get("data"):
        out.pop("hora")
    return out


def _numero(s):
    """'1.234,5' / '1,5' / '1234.5' / 12 -> float."""
    def um(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return np.nan
        if isinstance(v, (int, float)):
            return float(v)
        t = str(v).strip().replace(" ", "")
        if not t or t.lower() in ("nan", "-", "null", "none", "#n/d", "#n/a"):
            return np.nan
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
        else:
            t = t.replace(",", ".")
        try:
            return float(t)
        except ValueError:
            return np.nan
    return s.map(um)


def _tempo(data, hora=None):
    if hora is not None:
        data = data.astype(str).str.split(" ").str[0] + " " + hora.astype(str)
    num = pd.to_numeric(data, errors="coerce")
    if num.notna().mean() > 0.9 and num.dropna().between(20000, 80000).all():  # número de série do Excel
        return pd.to_datetime("1899-12-30") + pd.to_timedelta(num, unit="D")
    txt = data.astype(str).str.strip()
    iso = txt.str.match(r"^\d{4}-\d{2}-\d{2}").mean() > 0.5
    return pd.to_datetime(txt, errors="coerce", dayfirst=not iso, format="mixed")


def importar(arquivo_dados, elemento, nome, conteudo_b64, mapa, unidades=None, aba=None):
    """Lê a planilha com o de-para e guarda as séries do elemento. -> resumo da análise do elemento."""
    if elemento not in ELEMENTOS:
        raise ValueError(f"elemento desconhecido: {elemento}")
    p = ler_planilha(nome, conteudo_b64, aba)
    df = pd.DataFrame(p["linhas"], columns=p["colunas"])
    if not mapa.get("data"):
        raise ValueError("escolha a coluna de data/hora")
    ts = _tempo(df[mapa["data"]], df[mapa["hora"]] if mapa.get("hora") else None)
    series = {}
    unidades = unidades or {}
    for g, rot, tipo in ELEMENTOS[elemento][1]:
        col = mapa.get(g)
        if not col:
            continue
        v = _numero(df[col])
        un = unidades.get(g)
        fator = UNIDADES[tipo].get(un, 1.0) if un else 1.0
        if fator:
            v = v * fator
        s = pd.Series(v.values, index=ts).dropna()
        s = s[s.index.notna()].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if len(s):
            series[g] = {"unidade": "%" if (tipo == "nivel" and un == "%") else
                         {"vazao": "L/s", "pressao": "mca", "nivel": "m", "volume": "m³"}[tipo],
                         "dados": [[t.strftime("%Y-%m-%dT%H:%M:%S"), round(float(x), 4)] for t, x in s.items()]}
    if not series:
        raise ValueError("nenhuma coluna de dados com números válidos (confira o de-para e as datas)")
    tudo = carregar(arquivo_dados)
    tudo[elemento] = {"arquivo": nome, "aba": p["aba"], "importado_em": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                      "linhas_lidas": p["n"], "series": series}
    with open(arquivo_dados, "w", encoding="utf-8") as f:
        json.dump(tudo, f, ensure_ascii=False)
    return analisar(tudo)["elementos"][elemento]


def digitar(arquivo_dados, elemento, data, valores, unidades=None):
    """Grava um dia digitado à mão: valores = {grandeza: [24 leituras, de 00:00 a 23:00, None = sem leitura]}.

    O dia substitui o que havia nessas 24 h para cada grandeza digitada; os outros dias ficam, então dá para
    lançar vários dias e comparar o perfil de um com o outro. -> resumo da análise do elemento.
    """
    if elemento not in ELEMENTOS:
        raise ValueError(f"elemento desconhecido: {elemento}")
    dia = datetime.strptime(data, "%Y-%m-%d")
    fim = dia + timedelta(days=1)
    unidades = unidades or {}
    tudo = carregar(arquivo_dados)
    info = tudo.get(elemento) or {"series": {}}
    series = info["series"]
    for g, rot, tipo in ELEMENTOS[elemento][1]:
        lista = (valores or {}).get(g)
        if lista is None:
            continue
        if len(lista) != 24:
            raise ValueError(f"{rot}: são 24 leituras (00:00 a 23:00), vieram {len(lista)}")
        un = unidades.get(g)
        fator = UNIDADES[tipo].get(un, 1.0) if un else 1.0
        nums = _numero(pd.Series(lista, dtype=object))
        novos = [[(dia + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S"), round(float(x * (fator or 1.0)), 4)]
                 for h, x in enumerate(nums) if not math.isnan(x)]
        unidade = "%" if (tipo == "nivel" and un == "%") else {"vazao": "L/s", "pressao": "mca", "nivel": "m", "volume": "m³"}[tipo]
        velho = series.get(g)
        if velho and velho["unidade"] != unidade:  # só acontece com nível: % e metros não se convertem
            raise ValueError(f"{rot}: os outros dias estão em {velho['unidade']}; digite na mesma unidade")
        fora = [p for p in (velho["dados"] if velho else []) if not (dia <= datetime.fromisoformat(p[0]) < fim)]
        juntos = sorted(fora + novos)
        if juntos:  # a unidade digitada fica guardada para a janela já abrir nela da próxima vez
            series[g] = {"unidade": unidade, "unidade_digitada": un or unidade, "dados": juntos}
        else:
            series.pop(g, None)
    if not series:
        tudo.pop(elemento, None)
    else:
        dias = sorted({p[0][:10] for d in series.values() for p in d["dados"]})
        tudo[elemento] = {"arquivo": "digitado à mão · " + (f"{len(dias)} dias" if len(dias) > 1 else
                                                           datetime.strptime(dias[0], "%Y-%m-%d").strftime("%d/%m/%Y")),
                          "aba": None, "importado_em": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                          "linhas_lidas": sum(len(d["dados"]) for d in series.values()), "series": series, "digitado": True}
    with open(arquivo_dados, "w", encoding="utf-8") as f:
        json.dump(tudo, f, ensure_ascii=False)
    return analisar(tudo)["elementos"].get(elemento)


def carregar(arquivo_dados):
    if os.path.exists(arquivo_dados):
        with open(arquivo_dados, encoding="utf-8") as f:
            return json.load(f)
    return {}


def excluir(arquivo_dados, elemento):
    tudo = carregar(arquivo_dados)
    tudo.pop(elemento, None)
    with open(arquivo_dados, "w", encoding="utf-8") as f:
        json.dump(tudo, f, ensure_ascii=False)


# ---------------------------------------------------------------- análise
def _serie(d):
    return pd.Series([x[1] for x in d["dados"]], index=pd.to_datetime([x[0] for x in d["dados"]]))


def estatisticas(s):
    """Período, passo, lacunas e valores suspeitos de uma série."""
    out = {"n": int(len(s)), "inicio": s.index[0].strftime("%Y-%m-%dT%H:%M:%S"),
           "fim": s.index[-1].strftime("%Y-%m-%dT%H:%M:%S"),
           "min": round(float(s.min()), 3), "media": round(float(s.mean()), 3), "max": round(float(s.max()), 3)}
    dt = s.index.to_series().diff().dropna().dt.total_seconds()
    passo = float(dt.median()) if len(dt) else 0
    out["passo_min"] = round(passo / 60, 1)
    buracos = dt[dt > 2.5 * passo] if passo else dt.iloc[0:0]
    out["lacunas"] = int(len(buracos))
    out["horas_sem_dado"] = round(float((buracos - passo).sum() / 3600), 1) if len(buracos) else 0.0
    esperado = ((s.index[-1] - s.index[0]).total_seconds() / passo + 1) if passo else len(s)
    out["cobertura_pct"] = round(min(100.0, 100 * len(s) / esperado), 1) if esperado else 100.0
    out["negativos"] = int((s < 0).sum())
    mad = float((s - s.median()).abs().median())
    out["fora_do_padrao"] = int(((s - s.median()).abs() > 6 * 1.4826 * mad).sum()) if mad > 0 else 0
    # valor parado (sensor travado): 12 leituras iguais seguidas ou mais
    grupos = (s.diff() != 0).cumsum()
    tam = s.groupby(grupos).transform("size")
    out["travado"] = int((tam >= 12).sum())
    alertas = []
    if out["lacunas"]:
        alertas.append(f"{out['lacunas']} lacuna(s), {str(out['horas_sem_dado']).replace('.', ',')} h sem dado")
    if out["negativos"]:
        alertas.append(f"{out['negativos']} valor(es) negativo(s)")
    if out["fora_do_padrao"]:
        alertas.append(f"{out['fora_do_padrao']} valor(es) fora do padrão (picos)")
    if out["travado"]:
        alertas.append(f"{out['travado']} leitura(s) com valor parado (sensor travado?)")
    out["alertas"] = alertas
    return out


def analisar(tudo):
    """Estatísticas por elemento e balanço hídrico do sistema padrão."""
    elementos = {}
    for el, info in tudo.items():
        elementos[el] = {"arquivo": info["arquivo"], "importado_em": info["importado_em"],
                         "series": {g: {"unidade": d["unidade"], **estatisticas(_serie(d))}
                                    for g, d in info["series"].items()}}
    balanco = None
    try:
        balanco = _balanco(tudo)
    except Exception as e:  # dados insuficientes ou desalinhados: a tela mostra o motivo
        balanco = {"erro": str(e)}
    return {"elementos": elementos, "balanco": balanco}


def _fora_do_padrao(s):
    mad = float((s - s.median()).abs().median())
    return (s - s.median()).abs() > 6 * 1.4826 * mad if mad > 0 else s != s


def _balanco(tudo):
    descartados = {}

    def pega(el, g):
        d = tudo.get(el, {}).get("series", {}).get(g)
        if not d:
            return None
        s = _serie(d)
        ruim = _fora_do_padrao(s) | ((s < 0) if g != "volume" else False)
        if ruim.any():  # picos e vazões negativas não entram no balanço
            descartados[f"{el}.{g}"] = int(ruim.sum())
        return s[~ruim]
    entrada = pega("captacao", "vazao_entrada")
    za, zb = pega("za", "consumo"), pega("zb", "consumo")
    vol = pega("reservatorio", "volume")
    elev = pega("elevatoria", "vazao")
    if entrada is None or (za is None and zb is None):
        return {"erro": "para o balanço importe pelo menos a vazão de entrada da captação e o consumo de ZA ou ZB"}
    # passo do balanço: 15 min, ou o passo da série mais espaçada (dados digitados hora a hora -> 1 h)
    passos = [s.index.to_series().diff().dt.total_seconds().median() for s in (entrada, za, zb, vol, elev)
              if s is not None and len(s) > 1]
    seg = int(max([900] + [p for p in passos if p == p]))
    passo = f"{seg}s"
    junta = pd.DataFrame({"entrada": entrada.resample(passo).mean()})
    for nome, s in (("za", za), ("zb", zb), ("elevatoria", elev)):
        if s is not None:
            junta[nome] = s.resample(passo).mean()
    if vol is not None:
        v = vol.resample(passo).mean().interpolate(limit=4)
        junta["dvdt"] = v.diff() * 1000 / seg  # m³ no passo -> L/s
    junta = junta.dropna(subset=["entrada"])
    consumo = junta[[c for c in ("za", "zb") if c in junta]].sum(axis=1, min_count=1)
    junta["consumo"] = consumo
    junta["residuo"] = junta["entrada"] - consumo - (junta["dvdt"] if "dvdt" in junta else 0)
    ok = junta.dropna(subset=["consumo"])
    if not len(ok):
        return {"erro": "as datas da captação e das zonas não se cruzam: confira o período de cada planilha"}
    m3 = seg / 1000  # L/s × passo (s) / 1000 = m³
    ent_m3 = float(ok["entrada"].sum() * m3)
    res_m3 = float(ok["residuo"].dropna().sum() * m3)
    out = {"inicio": ok.index[0].strftime("%Y-%m-%dT%H:%M:%S"), "fim": ok.index[-1].strftime("%Y-%m-%dT%H:%M:%S"),
           "passos": int(len(ok)), "entrada_m3": round(ent_m3, 1), "consumo_m3": round(float(ok["consumo"].sum() * m3), 1),
           "residuo_m3": round(res_m3, 1), "residuo_pct": round(100 * res_m3 / ent_m3, 1) if ent_m3 else None,
           "com_volume": "dvdt" in junta, "passo_min": seg // 60, "descartados": descartados, "serie": []}
    if "elevatoria" in ok and "za" in ok:
        par = ok[["elevatoria", "za"]].dropna()
        if len(par):
            out["elevatoria_x_za_pct"] = round(100 * float((par["elevatoria"] - par["za"]).sum() / par["za"].sum()), 1) \
                if par["za"].sum() else None
    for t, r in ok.iterrows():
        out["serie"].append([t.strftime("%Y-%m-%dT%H:%M:%S"), _r(r["entrada"]), _r(r["consumo"]),
                             _r(r.get("dvdt")), _r(r["residuo"])])
    return out


def _r(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)


def arquivo_de(gpkg):
    return os.path.splitext(gpkg)[0] + "_dados_recebidos.json"


if __name__ == "__main__":
    import sys
    from cadastro_para_inp import GPKG_PADRAO
    r = analisar(carregar(arquivo_de(sys.argv[1] if len(sys.argv) > 1 else GPKG_PADRAO)))
    print(json.dumps({k: v for k, v in r.items() if k != "balanco"}, ensure_ascii=False, indent=1)[:2000])
    print("balanço:", {k: v for k, v in (r["balanco"] or {}).items() if k != "serie"})
