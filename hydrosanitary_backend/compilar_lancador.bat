@echo off
rem Gera os lancadores a partir de lancador\Hidrossanitario.cs: HIDROSANITY.exe (raiz do repositorio) e
rem Hidrossanitario.exe (nesta pasta). Os dois abrem o menu inicial (GWATER ou GPREDIAL).
rem So precisa rodar de novo se o lancador mudar; mudancas no programa nao exigem recompilar.
cd /d "%~dp0lancador"
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
"%CSC%" /nologo /target:winexe /out:..\Hidrossanitario.exe /win32icon:hidrossanitario.ico /reference:System.Windows.Forms.dll Hidrossanitario.cs
if errorlevel 1 (pause & exit /b 1)
"%CSC%" /nologo /target:winexe /out:..\..\HIDROSANITY.exe /win32icon:hidrossanitario.ico /reference:System.Windows.Forms.dll Hidrossanitario.cs
if errorlevel 1 (pause & exit /b 1)
echo Pronto: HIDROSANITY.exe e Hidrossanitario.exe
