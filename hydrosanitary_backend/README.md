# Hydrosanitary backend

Motor de cálculo de água fria + importação de projetos.

## Importação (DXF e IFC)

```python
from importers import import_project
from importers.config import ImportConfig
from services.network_analyzer import NetworkAnalyzer

res = import_project("projeto.dxf", ImportConfig.from_json("config/import_config.json"))
out = NetworkAnalyzer(res.project).analyze(res.source_id, source_pressure_mca=5.0, auto_size=True)
print(res.warnings, out["alerts"])
```

### Padrão DXF (configurável em `config/import_config.json`)
| Elemento | Como desenhar |
|---|---|
| Tubo | LINE / LWPOLYLINE / POLYLINE na layer `AF_TUBO_<diâmetro mm>` (ex.: `AF_TUBO_25`); `AF_TUBO` = diâmetro padrão |
| Aparelho | bloco na layer `AF_APARELHO`, com nome = chave de `FIXTURE_DATABASE` (ex.: `chuveiro_eletrico`) ou apelido |
| Fonte de água | qualquer bloco na layer `AF_FONTE`, sobre uma ponta de tubo |
| Paredes | LINE / polilinha na layer `AF_PAREDE` (altura `wall_height_m`, padrão 2,7 m) |
| Cômodo | polilinha fechada na layer `AF_COMODO_<nome>`; aparelhos dentro do contorno pertencem ao cômodo |
| Cota | coordenada Z; unidade pelo `$INSUNITS` do arquivo (senão `default_unit`) |

Pontas a até `snap_tolerance_m` (5 cm) são unidas no mesmo nó. Aparelhos e fonte precisam estar sobre uma ponta de tubo.

### Padrão IFC
`IfcPipeSegment` = tubo (diâmetro de `NominalDiameter` ou da geometria); `IfcSanitaryTerminal` = aparelho
(`PredefinedType` SHOWER/TOILETPAN/WASHHANDBASIN/SINK, ou `ObjectType` = chave do aparelho);
fonte = elemento com "FONTE" no nome.

DWG: converta para DXF antes (ex.: ODA File Converter).

## Interface gráfica

```
pip install -r requirements.txt
python -m gui.app [projeto.dxf|projeto.ifc]
```
Abra o projeto (Ctrl+O), ajuste pressão da fonte / velocidade máxima, marque dimensionamento automático se quiser e calcule (F5).
A vista isométrica mostra pisos dos cômodos, paredes translúcidas e a tubulação por cima (há também a Planta e "Girar vista 90°"). Desmarque cômodos em "Cômodos consumindo" para simular uso simultâneo parcial. Os tubos aparecem em cinza quando não têm consumo. A planta mostra tubos coloridos pela velocidade (verde ok, azul baixa, vermelho acima do limite) e nós com a pressão; passe o mouse para ver detalhes. Roda do mouse = zoom.

Exemplo completo (casa com banheiro, cozinha e área de serviço): `python examples/make_sample_house.py casa.dxf`.

### Desenho, peças e sinótico (interface no estilo GWATER)

A janela usa a identidade visual do GWATER (tema escuro, faixa de menus por abas, cabeçalho com MODELO / SINÓTICO / RESULTADOS).

- **Desenho**: Tubo (clica os pontos; encaixa em nós e no meio de tubos, criando o tê), Prumada (tubo vertical até a cota informada), Reservatório. DN, material e altura do tubo acima do piso ficam na própria aba. Grade, Ortogonal (F8 ou Shift) e passo da grade.
- **Aparelhos** e **Peças**: clique num nó ou sobre um tubo. Peças: VRP (pede a pressão regulada), registros de gaveta/globo/pressão, retenção, hidrômetro, tê, joelhos, curvas, bucha e luva. Joelho/curva/tê informados num nó substituem a detecção automática nesse nó.
- **Arquitetura**: paredes externas e internas (com espessura), retângulo de paredes, cômodos e pavimentos. "Paredes p/ cima" empilha a arquitetura no pavimento de cima; "Replicar pavimento" copia o pavimento tipo (com a rede) para N pavimentos. Na isométrica as paredes são prismas 2.5D; os pavimentos acima do ativo ficam ocultos (corte), a não ser que se marque "Mostrar pavimentos acima".
- **Propriedades** (à direita): edita o elemento selecionado (DN, material, comprimento, Leq, cota, aparelhos, peças, VRP, tipo/espessura/altura de parede, nome do cômodo). Del apaga; Ctrl+Z / Ctrl+Y desfazem/refazem. Depois do primeiro cálculo, cada edição recalcula sozinha.
- **Sinótico**: corte esquemático do prédio com reservatório, prumadas, ramal de cada pavimento (VRP e registros), aparelhos agrupados por tipo com a pior pressão e o escoamento animado; clique num pavimento para editá-lo. Pressões acima de 40 mca (NBR 5626) aparecem em laranja.
- **Seleção**: clique numa face de parede para selecioná-la (fica em ciano; ao passar o mouse ela clareia). Clique e arraste no vazio para selecionar por janela: da esquerda para a direita pega só o que está inteiro dentro, da direita para a esquerda pega tudo o que a janela toca. Ctrl+clique soma ou retira. Com vários elementos, o painel permite trocar tipo/espessura/altura de paredes e DN/material de trechos em lote, e excluir todos (Del). A roda do mouse aproxima no ponto do cursor.
- **Vista da parede (2D)**: selecione uma parede e use Desenho → Vista da parede, o botão no painel Propriedades ou dê duplo clique nela. A parede aparece de pé (comprimento × altura) com grade de 10 cm, piso, teto, encontros com outras paredes e as alturas típicas dos pontos. Tubos, aparelhos e peças desenhados ali ficam no plano da parede, na altura clicada (Afastamento: 0 = embutido no eixo). "Outro lado" vira a vista; Esc volta ao 3D.
- **Rotação / profundidade**: paredes e tubos são desenhados em pedaços curtos, ordenados pela profundidade, então em qualquer rotação o que está na frente cobre o que está atrás. Exibir → "Tubulação sempre visível (raio-X)" coloca a rede por cima das paredes.
- **Período estendido**: simula o consumo do prédio ao longo de 1 a 14 dias (população, consumo per capita, curva horária editável, reservatório, alimentação e falta d'água programada). Mostra consumo × alimentação, nível do reservatório e pressões mínima/máxima, com reprodução no tempo; "Ver este instante no sinótico" leva o resultado da hora escolhida ao modelo e ao sinótico. As vazões de cada instante são as prováveis da NBR 5626 escaladas pela curva (a hora de pico vale 1).
- Projetos desenhados são salvos em `.hsp` (JSON). Exemplo pronto: Início → Edifício (ou `python examples/make_sample_building.py edificio.hsp`).

## Memorial de cálculo

Na interface: calcule e use Arquivo → Exportar memorial de cálculo (Ctrl+E), em PDF ou HTML. Contém dados de entrada, vista isométrica, método, aparelhos, dimensionamento dos trechos, verificação de pressões, alertas e quantitativo. Em código: `services.report_generator.generate_memorial(...)`. Exemplo: `examples/memorial_exemplo.pdf`.

## Conexões (comprimento equivalente)

`core/standards.py` traz a tabela de comprimentos equivalentes (PVC soldável) por diâmetro, com interpolação (`services/fittings.py`). Com `analyze(..., auto_fittings=True)` (caixa marcada na interface):
- joelhos 45°/90° e tês (passagem direta, saída lateral, saída bilateral) são detectados pela geometria dos nós;
- registros (`registro_gaveta`, `registro_globo`) são informados como blocos na layer `AF_CONEXAO`, sobre um ponto da rede, e contam no trecho que chega a ele;
- cada conexão é contada no trecho que sai do nó, usando o diâmetro desse trecho; o Leq já informado no trecho é mantido e somado.

Os valores da tabela são típicos de fabricante: confira com a tabela adotada no projeto.

## Instalação no Windows (ex.: `C:\01 - HIDROSANITARIO`)

1. Copie esta pasta para `C:\01 - HIDROSANITARIO`.
2. Instale o Python 3.10+ (python.org, marcando "Add python.exe to PATH").
3. Execute `instalar.bat` uma vez e depois `iniciar.bat` (ou arraste um .dxf/.ifc sobre ele).
4. Opcional: `build_exe.bat` gera `dist\Hidrosanitario\Hidrosanitario.exe` (PyInstaller).
