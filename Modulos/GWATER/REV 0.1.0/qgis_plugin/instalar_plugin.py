"""Instala (ou atualiza) o plugin GWATER no QGIS do usuário: QGIS 3 e QGIS 4.

Uso:  .venv\\Scripts\\python.exe qgis_plugin\\instalar_plugin.py

- copia qgis_plugin/gwater para o perfil em uso de cada QGIS instalado
  (%APPDATA%\\QGIS\\QGIS3 e %APPDATA%\\QGIS\\QGIS4 - cada versão tem a própria pasta de plugins);
- grava config.json com o Python do projeto (.venv) e a pasta do motor;
- ativa o plugin no QGIS3.ini / QGIS4.ini (só se o QGIS estiver fechado; aberto, ele
  sobrescreveria o arquivo ao sair - nesse caso reabra o QGIS e ative em Complementos).
"""
import configparser
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
BASE = os.path.join(os.environ["APPDATA"], "QGIS")


def perfis():
    """[(versão, pasta do perfil em uso)] de cada QGIS que já foi aberto ao menos uma vez."""
    out = []
    for versao in ("QGIS3", "QGIS4"):
        raiz = os.path.join(BASE, versao, "profiles")
        if not os.path.isdir(raiz):
            continue
        perfil = "default"
        ini = os.path.join(raiz, "profiles.ini")
        if os.path.exists(ini):
            cp = configparser.ConfigParser()
            cp.read(ini, encoding="utf-8")
            perfil = cp.get("core", "lastProfile", fallback="default") or "default"
        out.append((versao, os.path.join(raiz, perfil)))
    if not out:  # QGIS nunca aberto: prepara o perfil padrão do QGIS 3
        out.append(("QGIS3", os.path.join(BASE, "QGIS3", "profiles", "default")))
    return out


def qgis_aberto():
    out = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    return "qgis" in out


def ativar_no_ini(ini):
    texto = open(ini, encoding="utf-8").read() if os.path.exists(ini) else ""
    linhas = texto.splitlines()
    if "[PythonPlugins]" not in linhas:
        linhas += ["", "[PythonPlugins]"]
    i = linhas.index("[PythonPlugins]")
    j = i + 1
    while j < len(linhas) and not linhas[j].startswith("["):
        if linhas[j].startswith("gwater="):
            linhas[j] = "gwater=true"
            break
        j += 1
    else:
        linhas.insert(i + 1, "gwater=true")
    os.makedirs(os.path.dirname(ini), exist_ok=True)
    open(ini, "w", encoding="utf-8").write("\n".join(linhas) + "\n")


if __name__ == "__main__":
    python = os.path.join(RAIZ, ".venv", "Scripts", "python.exe")
    aberto = qgis_aberto()
    for versao, perfil in perfis():
        destino = os.path.join(perfil, "python", "plugins", "gwater")
        if os.path.exists(destino):
            shutil.rmtree(destino)
        shutil.copytree(os.path.join(AQUI, "gwater"), destino, ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(destino, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"python": python, "motor": os.path.join(RAIZ, "motor")}, f, ensure_ascii=False, indent=2)
        print(f"{versao}: plugin copiado para {destino}")
        if not aberto:
            ativar_no_ini(os.path.join(perfil, "QGIS", f"{versao}.ini"))
            print(f"{versao}: plugin ativado.")
    if aberto:
        print("O QGIS está aberto: feche e abra de novo, depois ative em Complementos > Gerenciar > GWATER.")
    sys.exit(0)
