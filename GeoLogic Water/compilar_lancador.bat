@echo off
rem Gera o "GeoLogic Water.exe" (nesta pasta) a partir de lancador\GeoLogicWater.cs.
rem So precisa rodar de novo se o lancador mudar; mudancas no hub.py nao exigem recompilar.
cd /d "%~dp0lancador"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
"%CSC%" /nologo /target:winexe /out:"..\GeoLogic Water.exe" /win32icon:geologic.ico /reference:System.Windows.Forms.dll GeoLogicWater.cs
if errorlevel 1 (pause & exit /b 1)
echo Pronto: GeoLogic Water.exe
