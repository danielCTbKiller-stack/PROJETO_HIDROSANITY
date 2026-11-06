"""Adaptador do LISFLOOD-FP (motor macro): gera os arquivos dele, roda o executável e lê os resultados.

O LISFLOOD-FP roda como executável externo (motores/lisflood/bin/lisflood.exe), sem código dele no GFLOOD (licença).
Solver inercial (ACC, palavra `acceleration`); com `cenario.gpu`, a palavra `cuda` faz ele rodar na placa de vídeo
(precisa do executável compilado com CUDA).

Arquivos na pasta de trabalho do macro:
  dem.asc, n.asc        terreno e Manning (grade ASCII ESRI, na resolução do macro)
  entrada.bci / .bdy    hidrogramas pontuais (P x y QVAR) e nível de jusante (borda HFIX ou livre)
  chuva.rain            chuva uniforme (mm/h no tempo), se houver
  simulacao.par         o arquivo de controle
Saídas do LISFLOOD-FP em resultados/: res-NNNN.wd (profundidade), res-NNNN.elev (nível), res.max (máxima).
"""
import os
import subprocess
import time
from pathlib import Path

from osgeo import gdal

from . import preparo
from .modelo import Resultado

AQUI = Path(__file__).resolve().parent
EXE_PADRAO = AQUI.parent / "motores" / "lisflood" / "bin" / "lisflood.exe"


def executavel():
    """O lisflood.exe do GFLOOD (variável GFLOOD_LISFLOOD para usar outro)."""
    exe = Path(os.environ.get("GFLOOD_LISFLOOD", EXE_PADRAO))
    return exe if exe.exists() else None


def _asc(tif, asc):
    gdal.Translate(str(asc), str(tif), format="AAIGrid", outputType=gdal.GDT_Float32,
                   creationOptions=["DECIMAL_PRECISION=4"])
    Path(str(asc).replace(".asc", ".prj")).unlink(missing_ok=True)
    return Path(asc).name


def _serie_bdy(nome, serie):
    return [nome, f"{len(serie)} seconds"] + [f"{v:.6g} {t:.6g}" for t, v in serie]


def gerar(cenario, pasta=None):
    """Escreve os arquivos do LISFLOOD-FP. Devolve o caminho do .par."""
    pasta = Path(pasta or Path(cenario.pasta_trabalho) / "macro")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "resultados").mkdir(exist_ok=True)
    t = cenario.terreno
    dem_tif = preparo.grade(t.mdt, pasta / "dem.tif", cenario.crs, t.resolucao_macro)
    if t.edificacoes:
        dem_tif = preparo.edificacoes(dem_tif, t.edificacoes, t.altura_edificacoes, pasta / "dem_edif.tif")
    n_tif = preparo.manning(cenario.rugosidade, dem_tif, pasta / "n.tif")
    par = {"DEMfile": _asc(dem_tif, pasta / "dem.asc"), "resroot": "res", "dirroot": "resultados",
           "sim_time": f"{cenario.duracao:g}", "initial_tstep": "1.0", "massint": f"{min(60.0, cenario.passo_saida):g}",
           "saveint": f"{cenario.passo_saida:g}", "manningfile": _asc(n_tif, pasta / "n.asc")}
    f = cenario.forcante
    bci, bdy = [], ["GFLOOD - séries de contorno"]
    for h in f.hidrogramas:
        bci.append(f"P {h.ponto[0]:.3f} {h.ponto[1]:.3f} QVAR {h.nome}")
        bdy += _serie_bdy(h.nome, h.serie)
    if f.nivel_jusante is not None:
        xmin, ymin, xmax, ymax = preparo.limites(dem_tif)
        lado = f.borda_jusante.upper()
        a, b = (ymin, ymax) if lado in ("E", "W") else (xmin, xmax)
        bci.append(f"{lado} {a:.3f} {b:.3f} HFIX {f.nivel_jusante:g}")
    if bci:
        (pasta / "entrada.bci").write_text("\n".join(bci) + "\n", encoding="utf-8")
        par["bcifile"] = "entrada.bci"
    if len(bdy) > 1:
        (pasta / "entrada.bdy").write_text("\n".join(bdy) + "\n", encoding="utf-8")
        par["bdyfile"] = "entrada.bdy"
    if f.chuva:
        (pasta / "chuva.rain").write_text("\n".join(["GFLOOD - chuva (mm/h)", f"{len(f.chuva)} seconds"] +
                                                  [f"{v:.6g} {t_:.6g}" for t_, v in f.chuva]) + "\n", encoding="utf-8")
        par["rainfall"] = "chuva.rain"
    linhas = [f"{k:<15} {v}" for k, v in par.items()] + ["acceleration"]  # solver inercial (ACC)
    if cenario.gpu:
        linhas.append("cuda")  # o mesmo solver, na placa de vídeo
    arq = pasta / "simulacao.par"
    arq.write_text("# GFLOOD - " + cenario.nome + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return arq


def rodar(par, exe=None, progresso=None):
    """Roda o LISFLOOD-FP; devolve (código de saída, log). `progresso(linha)` recebe o log ao vivo."""
    exe = Path(exe) if exe else executavel()
    if exe is None:
        raise FileNotFoundError("lisflood.exe não encontrado em motores/lisflood/bin (veja motores/lisflood/LEIA.md)")
    p = subprocess.Popen([str(exe), "-v", Path(par).name], cwd=str(Path(par).parent), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log = []
    for linha in p.stdout:
        log.append(linha)
        if progresso:
            progresso(linha.rstrip())
    return p.wait(), "".join(log)


def ler(pasta, crs, passo_saida):
    """Converte as saídas do LISFLOOD-FP em GeoTIFF: profundidade por instante e as máximas."""
    pasta = Path(pasta)
    res = pasta / "resultados"
    out = pasta / "geotiff"
    out.mkdir(exist_ok=True)
    r = Resultado(motor="LISFLOOD-FP", pasta=str(out))
    for wd in sorted(res.glob("res-*.wd")):
        k = int(wd.stem.split("-")[-1])
        tif = out / f"profundidade_{k:04d}.tif"
        gdal.Translate(str(tif), str(wd), outputSRS=crs, format="GTiff", creationOptions=["COMPRESS=DEFLATE"])
        r.instantes.append((k * passo_saida, str(tif)))
    for ext, nome in ((".max", "profundidade"), (".mxe", "nivel"), (".maxtm", "tempo_maximo")):
        arq = res / f"res{ext}"
        if arq.exists():
            tif = out / f"max_{nome}.tif"
            gdal.Translate(str(tif), str(arq), outputSRS=crs, format="GTiff", creationOptions=["COMPRESS=DEFLATE"])
            r.maximos[nome] = str(tif)
    return r


def simular(cenario, exe=None, progresso=None):
    """Gera, roda e lê: o motor macro de ponta a ponta. Devolve o Resultado (log incluído)."""
    t0 = time.perf_counter()
    par = gerar(cenario)
    codigo, log = rodar(par, exe, progresso)
    r = ler(par.parent, cenario.crs, cenario.passo_saida)
    r.log = log + f"\n[GFLOOD] código {codigo}, {time.perf_counter() - t0:.1f} s"
    if codigo != 0:
        raise RuntimeError(f"LISFLOOD-FP terminou com código {codigo}. Log:\n{log[-2000:]}")
    return r
