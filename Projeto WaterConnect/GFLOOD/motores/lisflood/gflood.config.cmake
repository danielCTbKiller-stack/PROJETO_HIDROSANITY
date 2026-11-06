# Configuração de compilação do LISFLOOD-FP para o GFLOOD: a mesma do config.default.cmake dos autores, mas com o
# CUDA para as placas atuais. sm_89 = RTX 40xx (Ada); o PTX compute_89 deixa o driver adaptar a placas mais novas.
# Para outra placa, troque o 89 (ex.: 86 = RTX 30xx, 75 = RTX 20xx/GTX 16xx).
set(_NETCDF 1)
add_compile_definitions(_NUMERIC_MODE=0)
add_compile_definitions(_ONLY_RECT=0)
add_compile_definitions(_PROFILE_MODE=0)
add_compile_definitions(_DISABLE_WET_DRY=0)
add_compile_definitions(_CALCULATE_Q_MODE=1)
add_compile_definitions(_SGM_BY_BLOCKS=0)
add_compile_definitions(_BALANCE_TYPE=0)
set(CMAKE_CUDA_FLAGS "-gencode=arch=compute_89,code=sm_89 -gencode=arch=compute_89,code=compute_89")
# CUDA 12.x/13: a biblioteca padrão dele (CCCL) exige C++17 e o pré-processador moderno do MSVC
set(CMAKE_CUDA_STANDARD 17)
set(CMAKE_CUDA_STANDARD_REQUIRED True)
string(APPEND CMAKE_CUDA_FLAGS " -Xcompiler=/Zc:preprocessor")
# o tipo "byte" do Windows (rpcndr.h) briga com o std::byte do C++17 e derruba o compilador do CUDA
string(APPEND CMAKE_CUDA_FLAGS " -D_HAS_STD_BYTE=0")
