@echo off
rem Monta o GWATER portatil (programa + QGIS + Python do motor) para copiar no pen drive.
rem Uso: gerar_portatil.bat [pasta de destino, ex.: E:\GWATER]
cd /d "%~dp0"
".venv\Scripts\python.exe" gerar_portatil.py %*
pause
