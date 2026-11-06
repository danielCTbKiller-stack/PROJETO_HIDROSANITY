"""Etapas 1 e 2 do GFLOOD num caso sintético: canal reto num vale inclinado.

Vale de 2 km × 400 m com declividade de 0,1 %, canal de 20 m no meio (2 m mais fundo), hidrograma triangular de
50 m³/s entrando a montante e nível fixo a jusante. Confere o cenário em JSON, o preparo dos rasters, a chuva de
projeto e os arquivos do LISFLOOD-FP; a simulação roda quando o lisflood.exe existe (senão o teste é pulado).

Uso:  ..\\runtime\\envs\\gflood\\python.exe -m pytest -q testes
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hub_inundacao import macro, preparo  # noqa: E402
from hub_inundacao.modelo import Cenario, Forcante, Hidrograma, Rugosidade, Terreno  # noqa: E402

CRS = "EPSG:31983"
X0, Y0 = 330000.0, 7394000.0


def _vale(pasta, res=5.0):
    nx, ny = int(2000 / res), int(400 / res)
    x = np.arange(nx) * res
    y = np.arange(ny) * res
    z = 100.0 - 0.001 * x[None, :] + 0.02 * np.abs(y[:, None] - 200.0)   # vale em V suave
    z[np.abs(y - 200.0) <= 10.0, :] -= 2.0                                # canal de 20 m
    return preparo.criar_raster(z.astype("float32"), X0, Y0 + 400.0, res, CRS, pasta / "mdt.tif")


@pytest.fixture
def cenario(tmp_path):
    mdt = _vale(tmp_path)
    hid = Hidrograma("entrada", (X0 + 10.0, Y0 + 200.0), [(0, 0.0), (1800, 50.0), (3600, 0.0)])
    return Cenario(nome="canal sintético", crs=CRS, terreno=Terreno(mdt=mdt, resolucao_macro=10.0),
                   rugosidade=Rugosidade(n_padrao=0.035),
                   forcante=Forcante(hidrogramas=[hid], nivel_jusante=96.5, borda_jusante="E"),
                   duracao=3600.0, passo_saida=600.0, gpu=True, pasta_trabalho=str(tmp_path / "trabalho"))


def test_cenario_json(cenario, tmp_path):
    arq = tmp_path / "cenario.json"
    cenario.salvar(arq)
    c2 = Cenario.abrir(arq)
    assert c2 == cenario


def test_preparo_grade_e_manning(cenario, tmp_path):
    tif = preparo.grade(cenario.terreno.mdt, tmp_path / "g.tif", CRS, 10.0)
    z, gt, _ = preparo.ler(tif)
    assert gt[1] == 10.0 and z.shape == (40, 200)
    assert abs(z[20, 0] - 98.0) < 0.2 and z[20, 0] > z[20, -1]   # fundo do canal descendo para leste
    n = preparo.manning(Rugosidade(n_padrao=0.04), tif, tmp_path / "n.tif")
    nn, _, _ = preparo.ler(n)
    assert nn.shape == z.shape and np.allclose(nn, 0.04)


def test_chuva_de_projeto():
    serie = preparo.hietograma(K=1747.9, a=0.181, b=15.0, c=0.89, tr_anos=25, duracao_min=60, passo_min=5)
    assert len(serie) == 12
    pico = max(range(12), key=lambda i: serie[i][1])
    assert pico in (5, 6)                                         # blocos alternados: pico no meio
    total = preparo.volume_chuva_mm(serie)
    esperado = preparo.idf(1747.9, 0.181, 15.0, 0.89, 25, 60)     # mm/h em 1 h = mm
    assert abs(total - esperado) < 0.01 * esperado


def test_arquivos_lisflood(cenario):
    par = macro.gerar(cenario)
    texto = par.read_text(encoding="utf-8")
    for chave in ("DEMfile", "manningfile", "bcifile", "bdyfile", "sim_time", "saveint", "acceleration", "cuda"):
        assert chave in texto, chave
    bci = (par.parent / "entrada.bci").read_text(encoding="utf-8").splitlines()
    assert bci[0].startswith("P ") and "QVAR entrada" in bci[0]
    assert bci[1].startswith("E ") and bci[1].endswith("HFIX 96.5")
    bdy = (par.parent / "entrada.bdy").read_text(encoding="utf-8").splitlines()
    assert bdy[1:4] == ["entrada", "3 seconds", "0 0"] and bdy[5] == "0 3600"
    cab = (par.parent / "dem.asc").read_text().splitlines()[:6]
    assert cab[0].split()[1] == "200" and cab[1].split()[1] == "40"   # ncols, nrows na resolução do macro


@pytest.mark.skipif(macro.executavel() is None, reason="lisflood.exe ainda não compilado")
def test_simulacao_lisflood(cenario):
    r = macro.simular(cenario)
    assert r.maximos.get("profundidade")
    d, _, nd = preparo.ler(r.maximos["profundidade"])
    d = np.where(d == nd, 0, d)
    assert d[20, 100] > 0.1           # o canal molhou no meio do vale
    assert d[0, 100] < d[20, 100]     # a encosta molha menos que o canal
