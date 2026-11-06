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

Precisa de Visual Studio (ou Build Tools) com "Desenvolvimento para desktop com C++" (traz o CMake) e do CUDA
Toolkit da NVIDIA (para os solvers na placa de vídeo). Pelo site dos autores: abrir a pasta `LISFLOOD-FP-trunk` no
Visual Studio, escolher `msvc-x64-Release` e compilar; sai `out\build\msvc-x64-Release\lisflood.exe`, que vai para
`bin\`. A palavra `cuda` no `.par` (o GFLOOD põe quando o cenário pede GPU) roda o solver escolhido na placa.
