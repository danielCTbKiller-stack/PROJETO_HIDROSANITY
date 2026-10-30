@echo off
rem Abre o Hidrossanitario. Arraste um .dxf/.ifc sobre este arquivo para abri-lo direto.
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo Ambiente nao encontrado. Rode instalar.bat primeiro.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m gui.app %*
