@echo off
rem Prepara o motor de calculo do GWATER (uma vez so): Python 3.12 + WNTR (EPANET 2.2), na pasta .venv
cd /d "%~dp0"
echo GWATER - preparando o motor de calculo...
where py >nul 2>nul && (py -3.12 -m venv .venv) || (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" (
  echo Nao achei o Python 3.12. Instale de https://www.python.org e rode este arquivo de novo.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
echo Pronto. Pode fechar esta janela e abrir o GWATER.exe.
pause
