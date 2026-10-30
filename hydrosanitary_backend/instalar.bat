@echo off
rem Instala o Hidrossanitario (ambiente virtual + dependencias). Rode uma vez.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 ou superior nao encontrado. Instale em python.org e marque "Add python.exe to PATH".
  pause
  exit /b 1
)
python -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Instalacao concluida. Abra o programa com iniciar.bat
pause
