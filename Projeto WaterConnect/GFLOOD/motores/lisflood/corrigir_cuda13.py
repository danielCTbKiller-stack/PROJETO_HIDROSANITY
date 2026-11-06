"""Ajusta o LISFLOOD-FP 8.0 (de 2020) ao CUDA 12.x/13: o helper_cuda.h dos exemplos da NVIDIA, que ele inclui,
lê campos de cudaDeviceProp que o CUDA 13 tirou (computeMode e clockRate). Troca pela leitura com
cudaDeviceGetAttribute, que existe em todas as versões. Só mexe nesse arquivo de apoio (a escolha da placa), não no
modelo; pode rodar de novo (não repete a troca). O compilar.bat chama antes de compilar.

Uso:  python corrigir_cuda13.py <pasta LISFLOOD-FP-trunk>
"""
import sys
from pathlib import Path

MARCA = "// GFLOOD: CUDA 13"
FUNCAO = MARCA + """
inline int gfloodAtributo(cudaDeviceAttr atributo, int dispositivo) {
  int valor = 0;
  cudaDeviceGetAttribute(&valor, atributo, dispositivo);
  return valor;
}
"""
TROCAS = [  # (linha original, nova) - o dispositivo de cada trecho é o da linha cudaGetDeviceProperties acima dele
    ("if (deviceProp.computeMode == cudaComputeModeProhibited) {",
     "if (gfloodAtributo(cudaDevAttrComputeMode, devID) == cudaComputeModeProhibited) {"),
    ("if (deviceProp.computeMode != cudaComputeModeProhibited) {",
     "if (gfloodAtributo(cudaDevAttrComputeMode, current_device) != cudaComputeModeProhibited) {"),
    ("sm_per_multiproc * deviceProp.clockRate;",
     "sm_per_multiproc * gfloodAtributo(cudaDevAttrClockRate, current_device);"),
    ("(deviceProp.computeMode != cudaComputeModeProhibited)) {",
     "(gfloodAtributo(cudaDevAttrComputeMode, current_device) != cudaComputeModeProhibited)) {"),
]


def cub_antigo(trunk):
    """O LISFLOOD-FP traz uma cópia antiga da biblioteca CUB em cuda/cub, que fica na frente da do CUDA (que já
    traz a sua, compatível com o Thrust dele). Renomeia a cópia para o compilador achar a do CUDA."""
    velha, nova = Path(trunk) / "cuda" / "cub", Path(trunk) / "cuda" / "cub_antigo"
    if velha.is_dir():
        velha.rename(nova)
        return "cuda/cub renomeado para cub_antigo"
    return "cub antigo já fora do caminho"


def cbrt_macro(trunk):
    """lisflood.h define cbrt e cbrtf como macros (remendo para Visual Studio antigo, sem a função). O VS 2022 tem a
    função, e o CUDA 13 recusa compilar com uma função matemática virando macro. Tira as duas macros."""
    arq = Path(trunk) / "lisflood.h"
    s = arq.read_text(encoding="utf-8", errors="replace")
    velho = ("#ifndef cbrt\n\t#define cbrt(x) pow(x,1/3.0);\n#endif\n"
             "#ifndef cbrtf\n\t#define cbrtf(x) powf(x,1/3.0f);\n#endif\n")
    s2 = s.replace("\r\n", "\n")
    if velho not in s2:
        return "macros de cbrt já fora"
    arq.write_text(s2.replace(velho, "// GFLOOD: as macros de cbrt/cbrtf (Visual Studio antigo) saíram: o VS 2022 tem a "
                                     "função e o CUDA 13 não aceita a macro\n"), encoding="utf-8")
    return "macros de cbrt tiradas"


def corrigir(trunk):
    arq = Path(trunk) / "cuda" / "common" / "helper_cuda.h"
    s = arq.read_text(encoding="utf-8", errors="replace")
    if MARCA in s:
        return "já corrigido"
    for a, b in TROCAS:
        if a not in s:
            raise SystemExit(f"trecho não encontrado em {arq}: {a}")
        s = s.replace(a, b)
    # logo depois do "#ifdef __CUDA_RUNTIME_H__" das funções que escolhem a placa (só ali há o runtime do CUDA)
    i = s.index("\n", s.index("#ifdef __CUDA_RUNTIME_H__")) + 1
    s = s[:i] + FUNCAO + "\n" + s[i:]
    arq.write_text(s, encoding="utf-8")
    return "corrigido"


if __name__ == "__main__":
    print("helper_cuda.h:", corrigir(sys.argv[1]))
    print(cub_antigo(sys.argv[1]))
    print(cbrt_macro(sys.argv[1]))
