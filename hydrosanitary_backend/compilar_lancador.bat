@echo off
rem Gera Hidrossanitario.exe (o lancador) a partir de lancador\Hidrossanitario.cs.
rem So precisa rodar de novo se o lancador mudar; mudancas no programa nao exigem recompilar.
cd /d "%~dp0lancador"
"%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /target:winexe /out:..\Hidrossanitario.exe /win32icon:hidrossanitario.ico /reference:System.Windows.Forms.dll Hidrossanitario.cs
if errorlevel 1 (pause & exit /b 1)
echo Pronto: Hidrossanitario.exe
