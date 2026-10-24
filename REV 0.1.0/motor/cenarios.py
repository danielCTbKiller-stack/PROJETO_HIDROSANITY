"""Cenários (propostas) gravados no próprio GeoPackage do cadastro.

Tabelas (criadas na primeira gravação):
  cenario            id, nome, descricao, com_projetados, fator_demanda, atualizado_em
  cenario_alteracao  cenario, camada, elemento, campo, valor
"""
import re
import unicodedata
from datetime import datetime

import pandas as pd
import pyogrio

T_CEN, T_ALT = "cenario", "cenario_alteracao"
COLS_CEN = ["id", "nome", "descricao", "com_projetados", "fator_demanda", "atualizado_em"]
COLS_ALT = ["cenario", "camada", "elemento", "campo", "valor"]


def _ler(gpkg, camada, cols):
    if camada not in {n for n, _ in pyogrio.list_layers(gpkg)}:
        return pd.DataFrame(columns=cols)
    df = pyogrio.read_dataframe(gpkg, layer=camada)
    return df.astype(object).where(df.notna(), None)[cols]


def listar(gpkg):
    cen, alt = _ler(gpkg, T_CEN, COLS_CEN), _ler(gpkg, T_ALT, COLS_ALT)
    out = []
    for _, c in cen.iterrows():
        alts = alt[alt["cenario"] == c["id"]]
        out.append({"id": c["id"], "nome": c["nome"], "descricao": c["descricao"] or "",
                    "com_projetados": bool(c["com_projetados"]), "fator_demanda": float(c["fator_demanda"] or 1),
                    "atualizado_em": c["atualizado_em"],
                    "alteracoes": [{"camada": a["camada"], "id": a["elemento"], "campo": a["campo"], "valor": a["valor"]}
                                   for _, a in alts.iterrows()]})
    return out


def _gravar(gpkg, cen, alt):
    cen = pd.DataFrame(cen, columns=COLS_CEN).astype({"com_projetados": "int32", "fator_demanda": "float64"})
    alt = pd.DataFrame(alt, columns=COLS_ALT).astype(str)
    pyogrio.write_dataframe(cen.astype({c: str for c in ("id", "nome", "descricao", "atualizado_em")}),
                            gpkg, layer=T_CEN, driver="GPKG")
    pyogrio.write_dataframe(alt, gpkg, layer=T_ALT, driver="GPKG")


def _novo_id(nome, existentes):
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()[:30] or "CENARIO"
    cid, n = base, 2
    while cid in existentes:
        cid, n = f"{base}_{n}", n + 1
    return cid


def salvar(gpkg, c):
    """Cria ou atualiza o cenário c (sem 'id' = novo). Devolve o id."""
    todos = listar(gpkg)
    if not (c.get("nome") or "").strip():
        raise ValueError("dê um nome à proposta antes de salvar")
    cid = c.get("id") or _novo_id(c["nome"], {x["id"] for x in todos})
    c = {**c, "id": cid, "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M")}
    todos = [x for x in todos if x["id"] != cid] + [c]
    _gravar(gpkg,
            [[x["id"], x["nome"], x.get("descricao", ""), int(bool(x.get("com_projetados"))),
              float(x.get("fator_demanda") or 1), x.get("atualizado_em", "")] for x in todos],
            [[x["id"], a["camada"], a["id"], a["campo"], a["valor"]] for x in todos for a in x.get("alteracoes", [])])
    return cid


def excluir(gpkg, cid):
    todos = [x for x in listar(gpkg) if x["id"] != cid]
    _gravar(gpkg,
            [[x["id"], x["nome"], x["descricao"], int(x["com_projetados"]), x["fator_demanda"], x["atualizado_em"]]
             for x in todos],
            [[x["id"], a["camada"], a["id"], a["campo"], a["valor"]] for x in todos for a in x["alteracoes"]])


def alteracoes_completas(c):
    """Alterações do cenário + fator de demanda global, no formato do conversor."""
    alts = list(c.get("alteracoes", []))
    f = float(c.get("fator_demanda") or 1)
    if abs(f - 1) > 1e-9:
        alts.append({"camada": "global", "id": "", "campo": "fator_demanda", "valor": f})
    return alts
