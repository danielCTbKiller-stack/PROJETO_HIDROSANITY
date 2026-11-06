@echo off
rem Gera dist\Hidrosanitario\Hidrosanitario.exe (precisa ter rodado instalar.bat antes).
cd /d "%~dp0"
call ".venv\Scripts\activate.bat"
pip install pyinstaller
pyinstaller --noconfirm --windowed --name Hidrosanitario --paths . ^
  --add-data "config;config" --collect-all ifcopenshell --collect-all ezdxf gui\app.py
echo.
echo Pronto: dist\Hidrosanitario\Hidrosanitario.exe
pause
