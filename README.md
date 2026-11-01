# Hidrossanitário – água fria predial

Software de modelagem hidráulica predial (NBR 5626) em Python + PySide6, com a identidade visual do GWATER:
desenho em planta/isométrica 2.5D, vista 2D da parede de trabalho, aparelhos e peças (VRP, registros, tês,
curvas…), paredes externas/internas por pavimento, sinótico animado do prédio e simulação em período estendido.

O repositório junta dois programas:

| Pasta | Programa |
|---|---|
| [`hydrosanitary_backend/`](hydrosanitary_backend/) | **Hidrossanitário** (este README e o [README de lá](hydrosanitary_backend/README.md)) |
| [`GWATER/`](GWATER/) | **GWATER**, redes de distribuição de água (EPANET/WNTR + QGIS), com o histórico do Git dele; veja o [README do GWATER](GWATER/README.md) |

**Calibração (Darwin Calibrator do WaterGEMS):** o GWATER calibra redes de distribuição
(`GWATER/REV 0.2.0/motor/darwin.py`); o Hidrossanitário ganhou o mesmo calibrador para a rede predial, na aba
**CALIBRAÇÃO** (Análise → Calibrar). Você informa momentos de medição (fator de demanda e pressão na saída do
reservatório), as leituras de campo (pressão em nós, vazão em trechos), grupos de rugosidade (por material ou
pavimento) e de demanda (por pavimento), a aptidão (soma dos quadrados, dos absolutos ou maior diferença) e o
método (genético ou gradiente). As melhores soluções aparecem com a comparação observado × simulado, e a
escolhida é gravada no projeto (fator de rugosidade de cada trecho e pesos dos aparelhos; Ctrl+Z desfaz).

O botão **Análise → Abrir GWATER** abre o GWATER.exe. O ambiente portátil dele (QGIS + Python, ~2,5 GB) fica
fora do Git: gere com `GWATER\REV 0.2.0\gerar_portatil.bat` ou copie a pasta `PORTATIL\GWATER` para
`GWATER\PORTATIL\GWATER`.

## Rodar numa máquina nova (Windows)

1. Instale o Python 3.10+ (python.org, marque "Add python.exe to PATH").
2. Clique duas vezes em `hydrosanitary_backend\Hidrossanitario.exe`. Na primeira vez ele oferece instalar o
   ambiente (`instalar.bat`: cria `.venv` e instala `requirements.txt`).
   Alternativa: rode `instalar.bat` e depois `iniciar.bat`.
3. Para ver um exemplo: Início → Edifício.

Testes: `hydrosanitary_backend\.venv\Scripts\python.exe -m pytest -q` (dentro de `hydrosanitary_backend`).

## Mapa do código

| Pasta | Conteúdo |
|---|---|
| `core/` | entidades (Node, Pipe, Wall, Room, Floor) e tabelas da norma (aparelhos, Leq das peças) |
| `engine/`, `services/network_analyzer.py` | cálculo: vazão provável, perda de carga (Fair-Whipple-Hsiao), VRP |
| `services/extended_period.py` | simulação em período estendido (curva horária, reservatório, falta d'água) |
| `services/project_io.py` | arquivo de projeto `.hsp` (JSON) |
| `importers/` | importação DXF / IFC |
| `gui/canvas.py` | área de desenho (planta, isométrica, vista da parede, seleção, snap) |
| `gui/synoptic.py`, `gui/extended.py` | sinótico do prédio e tela de período estendido |
| `gui/main_window.py`, `gui/ribbon.py`, `gui/theme.py`, `gui/symbols.py` | janela, faixa de menus, tema GWATER, ícones |
| `lancador/` | lançador `Hidrossanitario.exe` (C#; `compilar_lancador.bat` recompila) |
| `examples/` | edifício de exemplo e casa em DXF |
| `tests/` | testes (pytest) |
