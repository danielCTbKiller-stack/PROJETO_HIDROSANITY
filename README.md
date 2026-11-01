# GeoLogic Water – GWATER + GPREDIAL

Modelagem hidráulica: redes de distribuição (GWATER) e instalações prediais de água fria (GPREDIAL), reunidas
pelo hub **GeoLogic Water**.

| Pasta | O que é |
|---|---|
| [`GeoLogic Water/`](GeoLogic%20Water/) | **o hub**: `GeoLogic Water.exe` abre a tela para escolher o programa. Não tem programa próprio: lê a lista em `programas.json` e abre cada um na pasta dele. Aqui também ficam os temas (`temas.json`) |
| [`GWATER/`](GWATER/) | **GWATER**, redes de distribuição de água (EPANET/WNTR + QGIS), com o histórico do Git dele; veja o [README do GWATER](GWATER/README.md) |
| [`GPREDIAL/`](GPREDIAL/) | **GPREDIAL** (antigo Hidrossanitário), instalações prediais de água fria (NBR 5626); veja o [README do GPREDIAL](GPREDIAL/README.md) |

Cada programa também abre sozinho (`GWATER\REV 0.2.0\GWATER.exe`, `GPREDIAL\GPREDIAL.exe`), e a gota no canto
de cada um mostra a mesma tela do hub para trocar de programa.

**Integrar outro programa:** crie a pasta dele ao lado das outras e acrescente um item em
`GeoLogic Water/programas.json` (nome, descrição, ícone e o comando que abre, relativo a esta pasta). Ele aparece
no hub e na gota dos programas.

**Temas:** os 5 temas (Verde Saneamento é o padrão) ficam em `GeoLogic Water/temas.json`, lidos pelo hub e pelos
dois programas. A escolha é feita em Configurações e fica gravada; o hub segue a escolha do GPREDIAL.

**GWATER:**
- **Calibrador WaterGEMS** (`GWATER/REV 0.2.0/app/programa/calibrador_watergems.html`): abre numa aba do GWATER, em
  Análise → Dados de campo → Calibrador WaterGEMS, ou Centro de Operações → Calibrador WaterGEMS.
- **Consumidores:** um ponto com casa, ligado a um nó ou ao meio de uma tubulação.
- **Válvulas VRE e VSE:** de reservatório e de setor.

**Calibração (Darwin Calibrator do WaterGEMS):** o GWATER calibra redes de distribuição
(`GWATER/REV 0.2.0/motor/darwin.py`); o GPREDIAL ganhou o mesmo calibrador para a rede predial, na aba
**CALIBRAÇÃO** (Análise → Calibrar). Você informa:
- os momentos de medição: fator de demanda e pressão na saída do reservatório;
- as leituras de campo: pressão em nós e vazão em trechos;
- os grupos de rugosidade (por material ou pavimento) e de demanda (por pavimento);
- a aptidão: soma dos quadrados, dos absolutos ou maior diferença;
- o método: genético ou gradiente.

As melhores soluções aparecem com a comparação observado × simulado. A escolhida é gravada no projeto (fator de
rugosidade de cada trecho e pesos dos aparelhos), e o Ctrl+Z desfaz.

O GWATER usa o Python e as bibliotecas do QGIS, então roda em outro processo (o GPREDIAL e o hub usam o `.venv`
do PySide6, em `GPREDIAL\.venv`). O ambiente do GWATER (QGIS + Python, ~2,5 GB) fica fora do Git. Numa máquina
nova, use uma destas opções:
- instale o QGIS (o GWATER.exe acha o instalado), ou
- gere a versão portátil com `GWATER\REV 0.2.0\gerar_portatil.bat`, ou
- ligue a pasta `runtime` de uma versão portátil:
  `mklink /J "GWATER\REV 0.2.0\runtime" "<pasta portátil>\runtime"`.

## Rodar numa máquina nova (Windows)

1. Instale o Python 3.10+ (python.org, marque "Add python.exe to PATH").
2. Rode `GPREDIAL\instalar.bat` (cria o `.venv` do GPREDIAL, que o hub também usa). Ou abra o
   `GPREDIAL\GPREDIAL.exe`, que oferece instalar na primeira vez.
3. Abra o `GeoLogic Water\GeoLogic Water.exe` e escolha o programa.
4. Para ver um exemplo no GPREDIAL: Início → Edifício.

Testes do GPREDIAL: `GPREDIAL\.venv\Scripts\python.exe -m pytest -q` (dentro de `GPREDIAL`). Os do GWATER ficam em
`GWATER\REV 0.2.0\testes`.

Lançadores (C#, compilados pelo `csc.exe` que vem com o Windows): `GeoLogic Water\compilar_lancador.bat` e
`GPREDIAL\compilar_lancador.bat`. Só precisam ser recompilados se o lançador mudar.
