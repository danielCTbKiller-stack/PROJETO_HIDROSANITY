@echo off
rem Compila o LISFLOOD-FP (fonte\LISFLOOD-FP-trunk) com GPU e copia o lisflood.exe e as DLLs para bin\.
rem Precisa do Visual Studio Build Tools 2022 (C++ e CMake) e do CUDA Toolkit. A placa e escolhida em
rem gflood.config.cmake. Rode de novo so se o codigo ou a configuracao mudarem.
setlocal
cd /d "%~dp0"
set VS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat
if not exist "%VS%" (echo Visual Studio Build Tools 2022 nao encontrado. & exit /b 1)
call "%VS%" >nul
rem CUDA Toolkit: o mais novo instalado (vale tambem num terminal aberto antes da instalacao)
for /d %%c in ("%ProgramFiles%\NVIDIA GPU Computing Toolkit\CUDA\v*") do set "CUDA_PATH=%%~c"
if not defined CUDA_PATH (echo CUDA Toolkit nao encontrado: compila sem GPU.) else (set "PATH=%CUDA_PATH%\bin;%PATH%" & echo CUDA: %CUDA_PATH%)
set SRC=%~dp0fonte\LISFLOOD-FP-trunk
set OBJ=%~dp0fonte\build
rem o LISFLOOD-FP 8.0 usa campos que o CUDA 13 tirou: ajusta o arquivo de apoio da NVIDIA (corrigir_cuda13.py)
set PY=%~dp0..\..\runtime\envs\gflood\python.exe
"%PY%" "%~dp0corrigir_cuda13.py" "%SRC%" || exit /b 1
cmake -S "%SRC%" -B "%OBJ%" -G Ninja -DCMAKE_BUILD_TYPE=Release -D_CONFIG="%~dp0gflood.config.cmake" || exit /b 1
cmake --build "%OBJ%" --config Release || exit /b 1
if not exist bin mkdir bin
copy /y "%OBJ%\lisflood.exe" bin\ >nul
for %%d in ("%SRC%\windep\netCDF4-64\bin\*.dll" "%SRC%\DLL's\*.dll") do copy /y "%%~d" bin\ >nul 2>nul
echo Pronto: bin\lisflood.exe
