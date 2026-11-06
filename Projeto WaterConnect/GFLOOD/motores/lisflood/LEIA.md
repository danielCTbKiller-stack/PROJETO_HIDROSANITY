# LISFLOOD-FP (motor macro do GFLOOD)

O GFLOOD chama o LISFLOOD-FP como **executável externo** (`bin\lisflood.exe`), sem copiar código dele para o
GFLOOD (`hub_inundacao/macro.py` gera os arquivos, roda e lê os resultados). Outro executável pode ser usado pela
variável de ambiente `GFLOOD_LISFLOOD`.

## Código-fonte

- Zenodo, registro 4073011 (LISFLOOD-FP 8.0, outubro de 2020; o registro avisa que há versão mais nova em
  `https://zenodo.org/records/4073011/latest`):
  `https://zenodo.org/records/4073011/files/LISFLOOD-FP-8.zip` (53 MB, md5 `00602cbba617a50a34478495d2688add`).
- Não há executável oficial para Windows: é preciso compilar.

## Licença: conferir antes de usar comercialmente

As fontes não batem: o Zenodo diz **GPL-2.0 only**; o site seamlesswave.com diz **GPL-3.0 "for any non-commercial
use"**; a Universidade de Bristol chama de **"non-commercial, research code"**. Confira o arquivo de licença que vem
no `.zip` e, para uso comercial, a autorização dos autores.

## Compilar com GPU (Windows)

Precisa de Visual Studio Build Tools 2022 (C++ e CMake) e do CUDA Toolkit da NVIDIA. Extraia o `.zip` em `fonte\`
e rode `compilar.bat`: ele chama o `corrigir_cuda13.py`, compila e põe o `lisflood.exe` e as DLLs em `bin\`.

O código é de 2020 e o CUDA 13 mudou coisas; o GFLOOD ajusta sem mexer no modelo:
- `gflood.config.cmake` (no lugar do `config.default.cmake`): compila para a placa desta máquina (`sm_89`, RTX
  40xx; troque para outra placa), C++17 e o pré-processador moderno do MSVC no CUDA, e `_HAS_STD_BYTE=0`;
- `corrigir_cuda13.py`: no `helper_cuda.h` da NVIDIA (escolha da placa) troca dois campos que o CUDA 13 tirou;
  tira do caminho a cópia antiga da biblioteca CUB (`cuda\cub`); e tira de `lisflood.h` as macros de `cbrt`
  (remendo para Visual Studio antigo, que o CUDA 13 recusa).

Na versão 8, só os solvers **FV1** e **DG2** rodam na GPU (palavra `cuda` no `.par`); o inercial (ACC) roda na CPU.
O GFLOOD usa FV1 + `cuda` quando o cenário pede GPU, e ACC sem GPU. Conferido no canal sintético
(`testes\test_canal.py`): o log mostra "Using CUDA device: 0" e os dois solvers dão a mesma mancha.
