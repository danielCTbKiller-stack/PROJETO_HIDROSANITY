# Hidrossanitário – água fria predial

Software de modelagem hidráulica predial (NBR 5626) em Python + PySide6, com a identidade visual do GWATER:
desenho em planta/isométrica 2.5D, vista 2D da parede de trabalho, aparelhos e peças (VRP, registros, tês,
curvas…), paredes externas/internas por pavimento, sinótico animado do prédio e simulação em período estendido.

O código fica em [`hydrosanitary_backend/`](hydrosanitary_backend/); a documentação detalhada está no
[README de lá](hydrosanitary_backend/README.md).

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
