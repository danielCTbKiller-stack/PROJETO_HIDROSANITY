"""Programas integrados do HIDROSANITY (lista em programas.json, na raiz do repositório).

A gota no canto da faixa abre `escolher()`: o seletor (gui/seletor.py), com um cartão por programa; clicar abre o
programa. O GWATER tem o mesmo seletor (GWATER/REV 0.2.0/app/programa/seletor.py), lendo o mesmo arquivo.
"""
import json
import subprocess
from pathlib import Path

from gui import theme
from gui.theme import COR

RAIZ = Path(__file__).resolve().parents[2]


def programas():
    try:
        return json.loads((RAIZ / "programas.json").read_text(encoding="utf-8"))["programas"]
    except (OSError, ValueError, KeyError):
        return []


def abrir(prog):
    """Abre o programa pelo primeiro comando que existir. Devolve o erro, ou None."""
    for cmd in prog.get("comandos", []):
        exe = RAIZ / cmd[0]
        if exe.exists():
            try:
                subprocess.Popen([str(exe)] + list(cmd[1:]), cwd=str(RAIZ / prog.get("pasta", "")))
                return None
            except OSError as e:
                return str(e)
    return f"não encontrei {prog['comandos'][0][0]} em {RAIZ}"


def escolher(parent, atual):
    """Janela com os programas integrados (gui/seletor.py); `atual` é o id do programa que chamou."""
    from gui import seletor
    seletor.mostrar(parent, atual, programas(), abrir, COR, theme.ESTILO)
