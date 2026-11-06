@echo off
rem Gera o GPREDIAL.exe (nesta pasta) a partir de lancador\GPREDIAL.cs. O hub (GeoLogic Water.exe) tem o seu,
rem na pasta GeoLogic Water. So precisa rodar de novo se o lancador mudar; mudancas no programa nao exigem recompilar.
cd /d "%~dp0lancador"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
"%CSC%" /nologo /target:winexe /out:..\GPREDIAL.exe /win32icon:gpredial.ico /reference:System.Windows.Forms.dll GPREDIAL.cs
if errorlevel 1 (pause & exit /b 1)
echo Pronto: GPREDIAL.exe
