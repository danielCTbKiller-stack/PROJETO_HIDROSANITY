"""Chama o motor GWATER (Python do projeto, com WNTR) fora do Python do QGIS."""
import json
import os
import socket
import subprocess
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA_PAINEL = 8765


def config():
    """config.json é escrito pelo instalador: {"python": ..., "motor": ...}"""
    with open(os.path.join(AQUI, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _ambiente():
    # O QGIS define variáveis do Python, GDAL e PROJ dele; o motor usa as próprias versões.
    # (PYTHONEXECUTABLE, em especial, faz o .venv perder as bibliotecas instaladas.)
    fora = ("GDAL_DATA", "GDAL_DRIVER_PATH", "PROJ_LIB", "PROJ_DATA", "QT_PLUGIN_PATH")
    env = {k: v for k, v in os.environ.items() if k.upper() not in fora and not k.upper().startswith("PYTHON")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def rodar(acao, gpkg, com_projetados=False):
    """acao = 'validar' ou 'simular'. Retorna o dicionário gravado pelo gwater_cli.py."""
    cfg = config()
    fd, saida = tempfile.mkstemp(suffix=".json", prefix="gwater_")
    os.close(fd)
    cmd = [cfg["python"], "-W", "ignore", os.path.join(cfg["motor"], "gwater_cli.py"), acao, gpkg, saida]
    if com_projetados:
        cmd.append("--com-projetados")
    try:
        p = subprocess.run(cmd, cwd=cfg["motor"], env=_ambiente(), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=_flags(), timeout=900)
        if os.path.getsize(saida) == 0:
            raise RuntimeError((p.stderr or p.stdout or "o motor não respondeu")[-3000:])
        with open(saida, encoding="utf-8") as f:
            return json.load(f)
    finally:
        os.remove(saida)


def painel_no_ar():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORTA_PAINEL)) == 0


def iniciar_painel(gpkg):
    """Sobe o servidor do Centro de Operações; devolve o processo (ou None se já estava no ar)."""
    if painel_no_ar():
        return None
    cfg = config()
    return subprocess.Popen([cfg["python"], "-W", "ignore", os.path.join(cfg["motor"], "servidor.py"), gpkg],
                            cwd=cfg["motor"], env=_ambiente(), creationflags=_flags(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
