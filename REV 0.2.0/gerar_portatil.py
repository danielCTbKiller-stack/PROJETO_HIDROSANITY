"""Monta a versão portátil do GWATER (para pen drive): o programa, o QGIS e o Python do motor numa pasta só.

    PORTATIL\\GWATER\\
      GWATER.exe              abre direto, sem instalar nada (o lançador acha o QGIS e o Python da pasta)
      app\\ motor\\ painel\\ modelo\\ cadastro\\ (só o exemplo)
      runtime\\qgis\\           cópia do QGIS instalado (sem GRASS, documentação e cabeçalhos de programação)
      runtime\\python\\         Python 3.12 com o motor (WNTR/EPANET, pandas, geopandas, scipy…)
      dados\\                  criado no primeiro uso: configurações, perfil do QGIS e logins (vão junto)

Uso:  .venv\\Scripts\\python.exe gerar_portatil.py [pasta de destino]
      (padrão: a pasta PORTATIL\\GWATER do projeto; pode ser direto o pen drive, ex.: E:\\GWATER)
"""
import glob
import os
import shutil
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))


def robocopy(origem, destino, excluir_pastas=(), excluir_arquivos=()):
    """Cópia rápida (várias threads) com o robocopy do Windows. Códigos 0 a 7 = sucesso."""
    cmd = ["robocopy", origem, destino, "/E", "/MT:16", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"]
    if excluir_pastas:
        cmd += ["/XD", *excluir_pastas]
    if excluir_arquivos:
        cmd += ["/XF", *excluir_arquivos]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode >= 8:
        raise RuntimeError(f"robocopy falhou ({r.returncode}) copiando {origem}:\n{r.stdout[-2000:]}{r.stderr[-1000:]}")


def tamanho(pasta):
    total = 0
    for r, _, fs in os.walk(pasta):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total / 2 ** 30


def achar_qgis():
    cands = sorted(glob.glob(r"C:\Program Files\QGIS 4*"), reverse=True) or \
        sorted(glob.glob(r"C:\Program Files\QGIS 3*"), reverse=True)
    for c in cands:
        if os.path.exists(os.path.join(c, "bin", "python-qgis.bat")) or \
                os.path.exists(os.path.join(c, "bin", "python-qgis-ltr.bat")):
            return c
    raise SystemExit("Não achei o QGIS instalado em C:\\Program Files.")


def python_base():
    """Python de onde o .venv do motor foi criado (pyvenv.cfg, linha home)."""
    cfg = os.path.join(AQUI, ".venv", "pyvenv.cfg")
    if not os.path.exists(cfg):
        raise SystemExit("Falta o .venv do motor: rode preparar_ambiente.bat antes.")
    for linha in open(cfg, encoding="utf-8"):
        if linha.strip().startswith("home"):
            return linha.split("=", 1)[1].strip()
    raise SystemExit("pyvenv.cfg sem a linha home.")


def main(destino):
    t0 = time.time()
    destino = os.path.abspath(destino)
    print(f"Montando o GWATER portátil em {destino}")
    os.makedirs(destino, exist_ok=True)

    # 1 · o programa (sem o .venv, sem os cadastros pessoais, sem os testes)
    print("1/4 programa…", flush=True)
    robocopy(AQUI, destino,
             excluir_pastas=[os.path.join(AQUI, d) for d in (".venv", "runtime", "dados", "testes", "cadastro")]
             + ["__pycache__"],
             excluir_arquivos=["gwater_erros.log", "*.pyc", "gerar_portatil.py", "gerar_portatil.bat"])
    os.makedirs(os.path.join(destino, "cadastro"), exist_ok=True)
    for arq in ("gwater_cadastro.gpkg", "GWATER_cadastro.qgz", "criar_cadastro.py"):
        if os.path.exists(os.path.join(AQUI, "cadastro", arq)):
            shutil.copy2(os.path.join(AQUI, "cadastro", arq), os.path.join(destino, "cadastro", arq))

    # 2 · Python do motor: o Python base + as bibliotecas do .venv, numa pasta só (anda junto)
    print("2/4 Python do motor…", flush=True)
    base = python_base()
    py = os.path.join(destino, "runtime", "python")
    robocopy(base, py, excluir_pastas=[os.path.join(base, "Lib", "site-packages"), os.path.join(base, "Lib", "test"),
                                       os.path.join(base, "Doc"), "__pycache__"])
    robocopy(os.path.join(AQUI, ".venv", "Lib", "site-packages"), os.path.join(py, "Lib", "site-packages"),
             excluir_pastas=["__pycache__"])

    # 3 · QGIS (o mapa e a edição): cópia da instalação, sem o que o GWATER não usa
    print("3/4 QGIS (o maior: alguns minutos)…", flush=True)
    qgis = achar_qgis()
    robocopy(qgis, os.path.join(destino, "runtime", "qgis"),
             excluir_pastas=[os.path.join(qgis, p) for p in ("include", "doc", r"apps\grass", r"apps\saga",
                                                             r"apps\Python312\Lib\test", r"var\log")]
             + glob.glob(os.path.join(qgis, "apps", "grass*")) + ["__pycache__"],
             excluir_arquivos=["grass*.bat", "python-grass*.bat", "saga_gui.bat"])

    # 4 · conferência: o Python portátil importa o motor e calcula o exemplo
    print("4/4 conferindo…", flush=True)
    r = subprocess.run([os.path.join(py, "python.exe"), "-c",
                        "import wntr, pyogrio, geopandas, scipy, networkx; print('motor ok')"],
                       capture_output=True, text=True, cwd=os.path.join(destino, "motor"))
    print("   ", (r.stdout or r.stderr).strip()[-300:])
    with open(os.path.join(destino, "LEIA-ME.txt"), "w", encoding="utf-8") as f:
        f.write("GWATER portátil\n\n"
                "Clique duas vezes em GWATER.exe. Não precisa instalar nada: o QGIS e o Python do motor estão na pasta "
                "runtime.\nAs suas configurações, o perfil do QGIS e os logins do Assistente de IA ficam na pasta "
                "dados (vão junto com o pen drive).\nAs chaves de API do Assistente são criptografadas pelo usuário do "
                "Windows: em outro computador, digite de novo.\nRodar do pen drive é mais lento para abrir do que de um "
                "SSD; para trabalhar muito tempo num computador, copie a pasta para o disco.\n")
    print(f"Pronto em {(time.time() - t0) / 60:.1f} min: {tamanho(destino):.2f} GB em {destino}")
    return 0 if "motor ok" in (r.stdout or "") else 1


if __name__ == "__main__":
    padrao = os.path.join(os.path.dirname(AQUI), "PORTATIL", "GWATER")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else padrao))
