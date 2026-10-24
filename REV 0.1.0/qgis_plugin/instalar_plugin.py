"""Instala (ou atualiza) o plugin GWATER no QGIS 3 do usuário.

Uso:  .venv\\Scripts\\python.exe qgis_plugin\\instalar_plugin.py

- copia qgis_plugin/gwater para o perfil 'default' do QGIS 3;
- grava config.json com o Python do projeto (.venv) e a pasta do motor;
- ativa o plugin no QGIS3.ini (só se o QGIS estiver fechado; aberto, ele
  sobrescreveria o arquivo ao sair - nesse caso ative em Complementos).
"""
import json
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
PERFIL = os.path.join(os.environ["APPDATA"], "QGIS", "QGIS3", "profiles", "default")
DESTINO = os.path.join(PERFIL, "python", "plugins", "gwater")
INI = os.path.join(PERFIL, "QGIS", "QGIS3.ini")


def qgis_aberto():
    out = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
    return "qgis" in out


def ativar_no_ini():
    texto = open(INI, encoding="utf-8").read() if os.path.exists(INI) else ""
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
    os.makedirs(os.path.dirname(INI), exist_ok=True)
    open(INI, "w", encoding="utf-8").write("\n".join(linhas) + "\n")


if __name__ == "__main__":
    if os.path.exists(DESTINO):
        shutil.rmtree(DESTINO)
    shutil.copytree(os.path.join(AQUI, "gwater"), DESTINO, ignore=shutil.ignore_patterns("__pycache__"))
    python = os.path.join(RAIZ, ".venv", "Scripts", "python.exe")
    with open(os.path.join(DESTINO, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"python": python, "motor": os.path.join(RAIZ, "motor")}, f, ensure_ascii=False, indent=2)
    print("Plugin copiado para", DESTINO)
    if qgis_aberto():
        print("QGIS está aberto: feche e abra de novo, depois ative em Complementos > Gerenciar > GWATER.")
    else:
        ativar_no_ini()
        print("Plugin ativado. Abra o QGIS 3.")
    sys.exit(0)
