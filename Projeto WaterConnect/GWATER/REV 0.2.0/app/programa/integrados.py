"""Programas do GeoLogic Water: a gota no canto da faixa abre o seletor (seletor.py, o mesmo do hub e do GPREDIAL).

A lista fica em GeoLogic Water/programas.json, a pasta do hub, ao lado da pasta GWATER (duas pastas acima de
REV 0.2.0). Sem a lista (GWATER sozinho), mostra só o GWATER.
"""
import json
import os
import subprocess

from .tema import COR

REV = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # .../GWATER/REV 0.2.0


def _raiz():
    """A pasta do hub (Projeto WaterConnect): a primeira acima do GWATER com o programas.json."""
    d = REV
    for _ in range(6):
        d = os.path.dirname(d)
        if os.path.isfile(os.path.join(d, "programas.json")):
            return d
    return os.path.dirname(os.path.dirname(REV))


RAIZ = HUB = _raiz()  # os comandos do programas.json são relativos à pasta do hub


def programas():
    try:
        with open(os.path.join(HUB, "programas.json"), encoding="utf-8") as f:
            return json.load(f)["programas"]
    except (OSError, ValueError, KeyError):
        return [{"id": "gwater", "nome": "GWATER", "descricao": "Redes de distribuição de água", "icone": "rede"}]


def _ambiente():
    """O ambiente sem as variáveis do QGIS: o Python (PYTHONHOME, PYTHONPATH...), o Qt, o GDAL e o PROJ dele, e as
    pastas do runtime no PATH (com elas o outro programa carrega as DLLs do Qt do QGIS e fecha sem aviso)."""
    fora = ("GDAL_DATA", "GDAL_DRIVER_PATH", "PROJ_LIB", "PROJ_DATA", "OSGEO4W_ROOT", "QGIS_PREFIX_PATH")
    env = {k: v for k, v in os.environ.items() if k.upper() not in fora
           and not k.upper().startswith(("PYTHON", "QT_", "QTWEBENGINE", "QGIS"))}
    runtime = [os.path.normcase(os.path.realpath(os.path.join(REV, "runtime"))),
               os.path.normcase(os.path.join(REV, "runtime"))]
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep)
        if p and not any(os.path.normcase(os.path.realpath(p)).startswith(r) or os.path.normcase(p).startswith(r)
                         for r in runtime))
    return env


def abrir(prog):
    """Abre pelo primeiro comando que existir. Devolve o erro, ou None."""
    for cmd in prog.get("comandos", []):
        exe = os.path.join(RAIZ, *cmd[0].split("/"))
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe] + list(cmd[1:]), cwd=os.path.join(RAIZ, *prog.get("pasta", "").split("/")),
                                 env=_ambiente())
                return None
            except OSError as e:
                return str(e)
    return f"não encontrei o programa em {RAIZ}"


def escolher(janela, atual="gwater"):
    """Janela com os programas integrados (seletor.py, o mesmo do GPREDIAL)."""
    from . import seletor
    from .tema import ESTILO
    seletor.mostrar(janela, atual, programas(), abrir, COR, ESTILO)
