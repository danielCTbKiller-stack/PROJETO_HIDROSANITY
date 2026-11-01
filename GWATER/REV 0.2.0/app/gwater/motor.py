"""Chama o motor GWATER (Python do projeto, com WNTR) fora do Python do QGIS.

Cópia do plugin adaptada ao programa GWATER.exe: o Python (.venv) e o motor são os da própria pasta
REV 0.2.0, e o painel usa a porta 8775 (o plugin do QGIS continua na 8765, os dois podem rodar juntos)."""
import json
import os
import socket
import subprocess
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA_PAINEL = 8775
RAIZ = os.path.dirname(os.path.dirname(AQUI))  # REV 0.2.0
VERSAO_PAINEL = 4  # versão mínima do servidor do painel (motor/servidor.py, VERSAO) que este plugin espera


def config():
    """Python do projeto e pasta do motor (config.json, se existir, manda; senão, os da pasta REV 0.2.0)."""
    arq = os.path.join(AQUI, "config.json")
    if os.path.exists(arq):
        with open(arq, encoding="utf-8") as f:
            return json.load(f)
    portatil = os.path.join(RAIZ, "runtime", "python", "python.exe")  # versão portátil (pen drive)
    py = portatil if os.path.exists(portatil) else os.path.join(RAIZ, ".venv", "Scripts", "python.exe")
    return {"python": py, "motor": os.path.join(RAIZ, "motor")}


def _ambiente():
    # O QGIS define variáveis do Python, GDAL e PROJ dele; o motor usa as próprias versões.
    # (PYTHONEXECUTABLE, em especial, faz o .venv perder as bibliotecas instaladas.)
    fora = ("GDAL_DATA", "GDAL_DRIVER_PATH", "PROJ_LIB", "PROJ_DATA", "QT_PLUGIN_PATH")
    env = {k: v for k, v in os.environ.items() if k.upper() not in fora and not k.upper().startswith("PYTHON")}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def rodar(acao, alvo, com_projetados=False, extras=()):
    """acao: validar, simular, exportar, novo, importar ou analise (ver gwater_cli.py).
    alvo: o cadastro (.gpkg), ou o config.json da importação. Retorna o dicionário gravado pelo motor."""
    cfg = config()
    fd, saida = tempfile.mkstemp(suffix=".json", prefix="gwater_")
    os.close(fd)
    cmd = [cfg["python"], "-W", "ignore", os.path.join(cfg["motor"], "gwater_cli.py"), acao, alvo, saida, *extras]
    if com_projetados:
        cmd.append("--com-projetados")
    log = saida + ".log"
    try:
        with open(log, "w+", encoding="utf-8", errors="replace") as out:
            p = subprocess.Popen(cmd, cwd=cfg["motor"], env=_ambiente(), stdout=out, stderr=subprocess.STDOUT,
                                 creationflags=_flags())
            _esperar(p, 900)
            out.seek(0)
            texto = out.read()
        if os.path.getsize(saida) == 0:
            raise RuntimeError((texto or "o motor não respondeu")[-3000:])
        with open(saida, encoding="utf-8") as f:
            return json.load(f)
    finally:
        for arq in (saida, log):
            try:
                os.remove(arq)
            except OSError:
                pass


def _esperar(p, limite):
    """Espera o motor sem congelar a janela: a tela continua se redesenhando (cliques ficam de fora, para
    ninguém editar o cadastro no meio do cálculo)."""
    import time
    try:
        from qgis.PyQt.QtCore import QEventLoop
        from qgis.PyQt.QtWidgets import QApplication
        app = QApplication.instance()
    except ImportError:
        app = None
    fim = time.monotonic() + limite
    while True:
        try:
            p.wait(timeout=0.05)
            return
        except subprocess.TimeoutExpired:
            if time.monotonic() > fim:
                p.kill()
                raise RuntimeError("o motor passou de 15 minutos e foi interrompido")
            if app is not None:
                app.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)


def painel_no_ar():
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", PORTA_PAINEL)) == 0


def iniciar_painel(gpkg):
    """Sobe o servidor do Centro de Operações; devolve o processo (ou None se já estava no ar)."""
    if painel_no_ar():
        return None
    cfg = config()
    return subprocess.Popen([cfg["python"], "-W", "ignore", os.path.join(cfg["motor"], "servidor.py"), gpkg,
                             f"--porta={PORTA_PAINEL}"],
                            cwd=cfg["motor"], env=_ambiente(), creationflags=_flags(),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _api(rota, corpo=None, timeout=3):
    import urllib.request
    url = f"http://127.0.0.1:{PORTA_PAINEL}{rota}"
    req = urllib.request.Request(url, method="POST" if corpo is not None else "GET",
                                 data=None if corpo is None else json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def versao_painel():
    """Versão do servidor no ar (0 = servidor de uma versão antiga, sem a rota /api/versao)."""
    try:
        return int(_api("/api/versao").get("versao", 0))
    except Exception:
        return 0


def encerrar_painel():
    """Pede para um servidor (versão 3 ou mais nova) sair; True se a porta ficou livre."""
    import time
    try:
        _api("/api/encerrar", {})
    except Exception:
        return False
    for _ in range(30):
        if not painel_no_ar():
            return True
        time.sleep(0.1)
    return False


def trocar_cadastro(gpkg):
    """Painel já no ar (de outra sessão ou outro cadastro): passa a usar o cadastro aberto no QGIS."""
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{PORTA_PAINEL}/api/cadastro", method="POST",
                                 data=json.dumps({"gpkg": gpkg}).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r).get("gpkg")
    except Exception:  # servidor antigo, sem essa rota: o plugin reinicia o painel
        return None


def analise(nome, gpkg, com_projetados=False, **parametros):
    """Ferramenta de análise do motor (motor/analises.py): incendio, descarga, criticidade, zonas_pressao,
    energia, renovacao, dimensionar, qualidade, comparar, esqueletizar."""
    fd, arq = tempfile.mkstemp(suffix=".json", prefix="gwater_par_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"nome": nome, **parametros}, f, ensure_ascii=False)
    try:
        return rodar("analise", gpkg, com_projetados, [f"--params={arq}"])
    finally:
        os.remove(arq)
