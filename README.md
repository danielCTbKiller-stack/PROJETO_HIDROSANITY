# GWATER · Projeto Piloto

Plataforma open source de **cadastro, modelagem hidráulica e operação** de redes de água: o cadastro georreferenciado fica num GeoPackage, os cálculos são do **EPANET 2.2**, e a decisão acontece num **Centro de Operações**.

O GWATER existe em duas formas, que usam o mesmo cadastro e o mesmo motor:

| Revisão | Forma | Para quem |
|---|---|---|
| [REV 0.1.0](REV%200.1.0) | **Plugin do QGIS** (menu GWATER e Central GWATER) e Centro de Operações no navegador | quem já trabalha no QGIS |
| [REV 0.2.0](REV%200.2.0) | **GWATER.exe**, um programa à parte, com faixa de menus e ferramentas de análise como o WaterGEMS; o Centro de Operações abre dentro dele | quem quer um programa só, sem precisar saber QGIS |

O objetivo é juntar, sem licença comercial, o que hoje exige três produtos:

| Papel | Produto comercial | No GWATER |
|---|---|---|
| Cadastro georreferenciado | ArcGIS Pro | QGIS + GeoPackage ([cadastro](REV%200.1.0/cadastro)) |
| Modelagem, cenários e calibração | WaterGEMS | Motor Python + EPANET/WNTR ([motor](REV%200.1.0/motor)) e plugin QGIS ([qgis_plugin](REV%200.1.0/qgis_plugin)) |
| Operação, alarmes e gêmeo digital | Elipse Water | Painel web ([painel](REV%200.1.0/painel)) |

O fluxograma do projeto está em [fluxo/GWATER - Fluxo de Trabalho.drawio](fluxo) (abrir com o draw.io desktop). Ele tem uma página com o fluxo de trabalho (fases 0 a 13 e próximos passos) e outra com a arquitetura. O diagrama do programa (GWATER.exe) está em [fluxo/GWATER.exe - Programa.drawio](fluxo): como ele abre, a janela, as abas da faixa, os dados e o motor, e as melhorias da fase 14.

---

## GWATER.exe (REV 0.2.0) · programa à parte

**Para abrir:** clique duas vezes em [`REV 0.2.0\GWATER.exe`](REV%200.2.0). Na primeira vez, se faltar o motor de cálculo, ele oferece rodar `preparar_ambiente.bat` (cria o Python da pasta com o WNTR; precisa de internet, uma vez só). Também dá para arrastar um `.qgz` ou `.gpkg` sobre o `GWATER.exe` para abrir direto.

Requisitos: Windows e o **QGIS 4.2** (ou 3.44 LTR) instalado. O GWATER usa as bibliotecas do QGIS para o mapa e a edição, mas a janela, os menus e as ferramentas são dele: o QGIS não aparece. Se o QGIS estiver numa pasta fora do comum, crie `GWATER.ini` ao lado do `.exe` com a linha `qgis=C:\caminho\do\QGIS`.

**A janela** segue o WaterGEMS:
- **Faixa de menus** no alto, com o botão **Arquivo** (novo, abrir, recentes, salvar, exportar .inp, arquivo compactado) e o acesso rápido (novo, abrir, salvar, desfazer, refazer, calcular).
- **Mapa** no centro, com a caixa do **cenário ativo**, as ferramentas de zoom e a **hora do resultado**. As telas do Centro de Operações abrem em abas ao lado do mapa.
- **Painéis:** *Simbologia dos elementos* (como no WaterGEMS: um item por tipo, com caixinha que liga e desliga o tipo no mapa, ícone próprio e a quantidade; embaixo, as camadas de resultado, análises e mapa de fundo), *Propriedades* (dados e resultados do elemento selecionado; com vários selecionados, muda um campo em todos), *Consultas* com o *Navegador*, e *Cálculo* (notificações e linha do tempo).
- **Barra de status:** coordenadas, escala, sistema, seleção e edições pendentes.
- Tela **Início** com novo cadastro, abrir, novo de shapefile, o exemplo e os recentes.
- **Abertura animada:** a cada vez que o programa abre, sorteia um de 4 logos animados (gota e ondas, nome enchendo de água, rede de tubos se desenhando, nível de água subindo), enquanto a janela carrega. As opções estão em `REV 0.2.0\splash_opcoes.html`.
- **Configurações** (botão de engrenagem ao lado de *Fundo*): tema do programa. São 6 temas escuros (Grafite Ciano, o padrão; Abissal Neon; Meia-noite Violeta; Esmeralda Noturno; Âmbar Industrial; Original) e 1 claro. A escolha fica salva. Prévia em `REV 0.2.0\temas_opcoes.html`.
- **Mapa de fundo** na barra do mapa: claro, escuro e terreno (Esri, sem chave de acesso), OpenStreetMap, satélite ou nenhum.

| Aba | Ferramentas (nome no WaterGEMS) |
|---|---|
| **Início** | Cenários (Scenarios), Alternativas, Opções, Calcular (Compute), Validar, Tempos, Resumo, Notificações, Alertas · Desenhar, Medir, Selecionar (clique, janela, polígono, por elemento, por atributo), Excluir, Localizar · Central de demanda (Demand Center), Padrões, Curvas de bomba (Pump Definitions), Controles · Gráficos, Tabelas (FlexTables), Conjuntos de seleção, Propriedades · Topologia ativa, ModelBuilder |
| **Desenho** | Tubulação, Nó, Reservatório (Tank), Captação (Reservoir), Hidrante, Ponto de consumo, Bomba, Estação elevatória, Rotação variável (VSP), PRV, PSV, PBV, FCV, TCV, GPV, Registro (Isolation Valve), Ponto cotado (Spot Elevation), Borda, Texto, Linha, Comprimento, Área, Mover, Dividir, Propriedades, Protótipos |
| **Análise** | Incêndio (Fire Flow), Descarga (Flushing), Renovação de redes (Pipe Renewal Planner), Otimização: dimensionar diâmetros e calibrar (Darwin), Custo de energia (Energy Cost), Zonas de pressão, Criticidade, Idade da água e cloro · Gráficos, Tabelas, Consultas, Navegador, Contornos · Simulador SCADA |
| **Componentes** | Central de demanda, Padrões, Curvas, Controles, Zonas, Bibliotecas de engenharia (materiais, C, vida útil, diâmetros e custos), Protótipos, Qualidade da água, Perdas localizadas (biblioteca de K), Extensões de dados, Séries de campo |
| **Revisão** | Comparação de cenários, Histórico de alterações (Change Tracking), Arquivo compactado (Bulk Archive) |
| **Exibir** | Zoom total, aproximar, afastar, mover, vista anterior e seguinte, zoom na seleção, Vistas com nome, Vista aérea, Simbologia, Mapa de fundo (OpenStreetMap, satélite, arquivo), Rótulos, Perfis, Gráfico rápido, painéis |
| **Ferramentas** | Topologia ativa, ModelBuilder, TRex, LoadBuilder, Polígonos de Thiessen, Distribuir demanda, Centro de códigos (GIS-ID), Ferramentas externas (QGIS, EPANET, pasta), Esqueletizador (Skelebrator), Faixas e cores |
| **Relatório** | Relatório personalizado (PDF, HTML, impressora), tabelas de tubulações, nós, bombas, válvulas e reservatórios, Resumo do cenário, Inventário do modelo, Inventário de tubulações |
| **Centro de Operações** | Sinótico, Dados recebidos, Mapa e propostas, Calibração, Ao vivo (dentro do programa) |

**Tipos de elemento:** tubulação (aberta, fechada, com retenção), nó/junção, ponto de consumo, hidrante, ponta de rede, reservatório, captação, bomba e cada tipo de válvula (PRV, PSV, PBV, FCV, TCV, GPV e **registro de manobra**), cada um com símbolo próprio no mapa e na lista. O registro entra no EPANET como TCV totalmente aberta (ou fechada, pelo status), com o diâmetro da tubulação ligada se faltar o dele.

**Válvulas:**
- **Status:** ATIVA (regulando), **INATIVA** (100% aberta, sem regular: vai ao EPANET como *Open*, e o ajuste pode ficar vazio), ABERTA ou FECHADA.
- **TCV:** é aberta (sem perda) ou fechada, sem ajuste.
- **PRV, PSV, PBV e FCV ativas:** o ajuste é obrigatório. A validação lembra que, para deixar a válvula aberta, o status é INATIVA.

**Simbologia dos elementos:** um clique duplo no tipo abre o editor dele:
- tamanho do símbolo (ou espessura da linha), com prévia;
- rótulos: campo, texto antes e depois, tamanho e cor;
- **color coding**: cores por faixas de valor ou por categoria, com as classes geradas pelos dados.

Tudo fica salvo no projeto.

**Tabelas (FlexTables):**
- **Seleção por célula:** a seleção é por célula, como no Excel. *Selecionar coluna* (ou clicar no título) pega a coluna inteira.
- **Ctrl+V:** um valor colado vai para todas as células selecionadas, ou seja, para a coluna inteira se ela estiver selecionada. Várias linhas copiadas do Excel colam a partir da célula atual.
- **Ctrl+C:** copia as células selecionadas.
- **Edição global** (Global Edit): opera numa coluna inteira, ou só nas linhas selecionadas.
  - Para números: definir, somar, subtrair, multiplicar, dividir, arredondar e limpar.
  - Para texto: definir, acrescentar no início ou no fim, substituir e limpar.
- **Desfazer:** Colar e Edição global se desfazem com um único Ctrl+Z.
- **Rugosidade:** a rugosidade vem do material só quando a tubulação é criada. Depois disso, o valor digitado é mantido.

**Notificações** (painel *Cálculo*): agrupadas por tipo de problema, como o User Notifications do WaterGEMS, por exemplo "ERRO · Sem ligação com nenhuma fonte (12)".
- Ordem: erros primeiro, do grupo maior para o menor.
- Filtro: erros, avisos ou os dois.
- Busca: por texto ou código.
- Clique duplo leva até o elemento.

**ModelBuilder** (importar shapefiles): adicione vários arquivos de uma vez e diga o que cada um é. Arquivo de linhas vira tubulações; arquivo de pontos pode ser qualquer tipo de nó, reservatório, captação, bomba ou cada tipo de válvula (ou válvula com o tipo numa coluna). O nome do arquivo já sugere o tipo (vrp, registro, hidrante, reservatório...). Depois, o de-para de colunas e a tradução de valores, arquivo por arquivo.

A importação é feita em lote: os elementos pontuais entram primeiro, e as tubulações ligam neles; pontas a menos da tolerância viram o mesmo nó; ponta no meio de outra tubulação a divide (T); válvula, bomba ou hidrante no meio de uma tubulação a divide e fica entre os pedaços. Válvula com as duas tubulações no mesmo sentido tem uma invertida, com aviso para conferir. Tudo vai para a edição num único passo de desfazer. No teste, cerca de 10 mil linhas viram 20 mil tubulações e 10 mil nós em 5 segundos.

O que cada análise faz:

| Análise | Como funciona |
|---|---|
| **Incêndio** | Para cada hidrante (ou nó escolhido), a maior vazão mantendo a pressão residual no próprio nó e, se pedido, a pressão mínima nos outros nós. Mostra se atende a vazão exigida. |
| **Descarga** | Abre cada ponto com a vazão escolhida e lista as tubulações que passam da velocidade de limpeza. |
| **Criticidade** | Fecha cada tubulação, uma de cada vez, e mede a água que deixa de chegar aos consumidores e os nós que ficam abaixo da pressão mínima. |
| **Zonas de pressão** | Separa a rede pelas bombas, válvulas reguladoras e registros fechados; mostra demanda, cotas, pressões e por onde a água entra e sai. |
| **Custo de energia** | kWh e R$ de cada bomba com tarifa de ponta e fora de ponta, kWh/m³ e a parte do custo que cai na ponta. |
| **Renovação de redes** | Nota de 0 a 100 por tubulação (idade frente à vida útil, material, perda de carga e velocidade, criticidade) e custo acumulado para planejar por orçamento. |
| **Dimensionar** | Menores diâmetros das tubulações selecionadas que atendem pressão mínima e velocidade máxima no pico, com o custo. Vira cenário ou é aplicado no cadastro. |
| **Qualidade** | Idade da água ou cloro residual (decaimento no volume e na parede), no último dia de uma simulação longa. |

**Desempenho** (rede de 20 mil tubulações e 10 mil nós, medido em `teste_desempenho.py`):

| Operação | Tempo |
|---|---|
| Importar no ModelBuilder | ~5 s |
| Salvar edições | ~2 s |
| TRex com curvas de nível em todos os nós | ~9 s, com barra de progresso e Cancelar |
| Abrir a tabela de tubulações | ~2,5 s |
| Abrir o projeto | ~1 s |

No ModelBuilder, as cotas do TRex são calculadas em lote, depois dos nós. Enquanto o EPANET calcula, a janela continua se redesenhando e os cliques ficam bloqueados.

As análises instantâneas usam a rede congelada num instante (por padrão o de maior consumo): demandas, níveis e bombas daquele momento da simulação de 24 h, resolvida milhares de vezes direto na biblioteca do EPANET. Cada análise abre uma aba com a tabela (clique duplo vai ao elemento, exporta para CSV) e pinta uma camada no grupo *Análises GWATER*.

**Consultas** prontas: revisão da rede (nós muito próximos, tubulações que se cruzam, nós órfãos, pontas, candidatos a divisão, tubulações sem nós ou duplicadas, isolados), rastreamento (conectados, adjacentes, desconectados, caminho mais curto, a montante e a jusante pelo sentido do fluxo, **isolar** uma tubulação mostrando os registros a fechar e quem fica sem água), dados de entrada e resultados (pressões fora da faixa, bombas fora da curva, válvulas que não regulam, reservatórios vazios ou cheios, velocidade e perda altas, sem autolimpeza). Dá para criar consultas próprias.

**Cenários:** cada cenário guarda as alterações em relação à rede atual, o fator de demanda e a escolha de incluir os PROJETADOS. Ficam nas mesmas tabelas do cadastro que as propostas do Centro de Operações web. O cenário ativo é o que Calcular e as análises usam.

**Histórico de alterações:** a cada Salvar edições, o que entrou, saiu ou mudou (campo, antes e depois, quem e quando) vai para `<cadastro>_historico.sqlite`, ao lado do cadastro.

O plugin do QGIS (REV 0.1.0) continua funcionando como antes. O GWATER.exe tem as suas próprias cópias do motor, do painel e do código do plugin: mudanças numa revisão não afetam a outra. O painel do programa usa a porta 8775, e o do plugin, a 8765, então os dois rodam ao mesmo tempo.

---

## Início rápido (plugin do QGIS, REV 0.1.0)

Requisitos: Windows, **Python 3.12** e **QGIS 3.44 LTR** ou **QGIS 4.2** (o plugin foi testado nos dois).

```bash
cd "REV 0.1.0"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**1. Abrir o painel (Centro de Operações):**

```bash
.venv\Scripts\python.exe motor\servidor.py
```

Depois abra <http://localhost:8765>. Para usar outro cadastro, passe o caminho: `motor\servidor.py C:\caminho\cadastro.gpkg` (e `--porta=8766` para outra porta).

Pelo QGIS não é preciso fazer isso: os botões do Centro de Operações sobem o servidor com o cadastro aberto. Se houver um servidor de versão anterior no ar, o plugin percebe (`/api/versao`) e o reinicia sozinho.

**2. Instalar o plugin no QGIS** (com o QGIS fechado; ele é copiado para o QGIS 3 e o QGIS 4 que houver no computador):

```bash
.venv\Scripts\python.exe qgis_plugin\instalar_plugin.py
```

Abra o QGIS, ative **GWATER** em *Complementos → Gerenciar* se ele não aparecer, e use o menu **GWATER** (ao lado de Ajuda). Nele você cria um cadastro novo, importa um shapefile ou abre `cadastro\GWATER_cadastro.qgz`. Depois disso, tudo se faz por esse menu e pela **Central GWATER**, sem terminal.

---

## O que o sistema faz

### Cadastro no QGIS
- **Arquivos:** `gwater_cadastro.gpkg` (dados) e `GWATER_cadastro.qgz` (projeto com estilos, formulários e snapping).
- **Camadas:** captação, reservatórios, bombas, válvulas, nós e trechos. Tabelas de padrões de consumo, curvas, controles, opções e materiais.
- **Regra de desenho (como no WaterGEMS):** bombas e válvulas são pontos. O trecho que chega no ponto é o lado de montante, e o que sai é o de jusante.
- **Preenchimento automático:** código, comprimento, nó inicial e final (pelo encaixe), rugosidade pelo material e volume útil.
- Os detalhes estão em [MODELO_DE_DADOS.md](REV%200.1.0/cadastro/MODELO_DE_DADOS.md).

### Importação de shapefile
O botão **Novo cadastro de shapefile** do plugin (ou `motor\importar_shp.py config.json`) transforma um shapefile de rede num cadastro novo:
- reprojeta e separa multipartes
- aceita linhas 3D (PolylineZ, comum em arquivo vindo do CAD): a rede fica em 2D e o Z das pontas vira a cota dos nós
- cria os nós nas pontas, unindo folgas pela tolerância
- divide "T" não segmentados
- lê as cotas de um shapefile de pontos (que tem prioridade sobre o Z)
- distribui a demanda pelos nós

Para trazer elementos para um cadastro que já existe, use o **ModelBuilder** (abaixo).

O modelo de `config.json` está em [testes/shp_teste](REV%200.1.0/testes/shp_teste).

### Conversão cadastro → EPANET
[cadastro_para_inp.py](REV%200.1.0/motor/cadastro_para_inp.py) valida a rede e gera o `.inp`, que abre no EPANET 2.2 oficial.
- **O que a validação confere:** topologia, códigos repetidos, atributos desatualizados, diâmetro, rugosidade, conectividade e setores isolados por registros fechados.
- **Modo de demanda:** PDA (demanda dependente da pressão) por padrão, configurável em `opcoes_simulacao`. Assim é possível simular manobras: quem fica sem água se um registro for fechado.

### Plugin QGIS: menu GWATER e Central GWATER
Todas as funções do motor estão no QGIS, em três lugares com os mesmos botões:
- o menu **GWATER**;
- as barras **GWATER · Desenho** e **GWATER · Modelo**;
- o painel lateral **Central GWATER**, que mostra a explicação de cada botão ao lado dele.

Passe o mouse sobre um botão para ver o que ele faz. O botão *Guia dos botões* reúne todas as explicações e o passo a passo. A Central tem a mesma identidade visual do painel web e se ajusta ao lugar onde fica: em faixa horizontal embaixo do mapa (grupos lado a lado, com a ajuda à direita) ou em coluna na lateral. Ela tem três abas: *Central*, *Problemas* e *Resultados*.

| Grupo | Botões |
|---|---|
| 1 · Cadastro | Novo cadastro (vazio, em qualquer pasta e sistema UTM), Novo cadastro de shapefile, **ModelBuilder**, Abrir cadastro, Salvar edições |
| 2 · Desenhar a rede | Tubulação, Nó, Válvula, Bomba, Reservatório, Captação, Mover, **Dividir tubulações**, Ver/editar dados, e os padrões de desenho (DN, material, situação) |
| 3 · Preparar o modelo | **Curvas de bomba**, **Cotas do terreno (TRex)**, Distribuir demanda, Validar rede |
| 4 · Simular | Simular 24 h (mapa colorido + linha do tempo), **Faixas e cores**, Limpar resultados, Exportar .inp |
| 5 · Centro de Operações | Sinótico, Dados recebidos, Mapa e propostas, Calibração, Ao vivo (no navegador) |

**Desenho como no WaterGEMS** ([desenho.py](REV%200.1.0/qgis_plugin/gwater/desenho.py)): você desenha e a rede se mantém ligada sozinha.
- **Tubulação nova:**
  - a ponta solta ganha um nó;
  - a ponta sobre um elemento liga nele;
  - a ponta no meio de outra tubulação divide essa tubulação.
- **Válvula, bomba ou nó clicado sobre uma tubulação:** a tubulação é dividida e o elemento fica no meio.
- **Válvula, bomba ou reservatório sobre um nó:** o nó vira esse elemento.
- **Elemento arrastado:** as tubulações ligadas acompanham.
- **Preenchidos sozinhos:** códigos, comprimento, nós inicial e final, rugosidade e, se houver MDT escolhido, a cota.
- Nada vai para o arquivo até **Salvar edições**.

**Curvas de bomba** ([curvas.py](REV%200.1.0/qgis_plugin/gwater/curvas.py)), como as *Pump Definitions* do WaterGEMS:
- a janela lista as curvas cadastradas e permite criar, duplicar, renomear e excluir;
- cada curva tem uma tabela vazão (L/s) × altura (m) e um gráfico que mostra a curva exatamente como o EPANET vai usá-la;
- três formas de definir: 1 ponto (ponto de projeto), 3 pontos (shutoff, projeto, máxima) ou vários pontos;
- a janela recusa o que o EPANET não aceita (2 pontos, vazão que não cresce, altura que sobe);
- no formulário da bomba, o campo *curva* vira uma lista com as curvas cadastradas;
- o botão *Usar nas bombas selecionadas* aplica a curva às bombas escolhidas no mapa.

**ModelBuilder** ([modelbuilder.py](REV%200.1.0/qgis_plugin/gwater/modelbuilder.py)) importa elementos de qualquer arquivo para o cadastro aberto, num assistente de 4 passos:
1. **Origem:** o tipo de elemento (tubulações, nós, válvulas, bombas, reservatórios ou captações) e o arquivo ou camada de onde vêm. O sistema de coordenadas é convertido sozinho.
2. **De → para:** para cada campo do cadastro, a coluna do arquivo, com um exemplo do valor. Colunas de nome parecido já vêm ligadas (DN → diâmetro, MAT → material, COD → código…), e há um *valor fixo* para quando a coluna vier vazia.
3. **Valores:** a tradução dos valores de lista. Por exemplo, FOFO → Ferro fundido dúctil, VRP → PRV.
4. **Opções:**
   - **Tubulações:** a tolerância (m) para criar os nós nas pontas, unindo as pontas próximas e ligando nos elementos que já existem; e a divisão das ligações em "T".
   - **Elementos pontuais:** dividir as tubulações sobre as quais caem e substituir o nó que estiver no mesmo lugar.

**Cotas do terreno (TRex)** ([cotas.py](REV%200.1.0/qgis_plugin/gwater/cotas.py)), como o TRex do WaterGEMS, lê a cota de três tipos de fonte:
- **raster** (MDT/MDE);
- **curvas de nível** em linhas (shp ou gpkg): interpola entre a curva mais próxima e a próxima curva de outra cota;
- **pontos cotados**: inverso da distância.

A fonte pode ser uma camada do projeto ou um arquivo, e no GeoPackage com várias camadas você escolhe qual usar. A cota pode vir de um campo ou do Z da geometria (curvas 3D).
- **Sem raio de busca:** todo elemento recebe a cota das curvas (ou pontos) mais próximas, a qualquer distância. Fora de um raster ele fica sem cota e aparece na mensagem.
- **Arquivos grandes**, como as curvas do estado inteiro, não entram no mapa: só a região da rede é lida, pelo índice espacial do arquivo. Se a curva mais próxima estiver fora dela, a região cresce sozinha até achar. As distâncias são medidas em metros mesmo com o arquivo em graus.
- **Onde aplica:** o resultado vai no campo **`cota`**, a cota do terreno, que existe em todos os elementos pontuais (nós, válvulas, bombas, reservatórios e captações; cadastros antigos ganham o campo). A janela já abre com *Tudo*, *Toda a rede* e *Todos (substitui as cotas existentes)*; dá para escolher só alguns tipos de elemento, só os selecionados no mapa ou só os elementos sem cota.
- A mesma fonte pode dar cota a cada nó novo desenhado.

**Dividir tubulações** corrige a ligação da rede com uma tolerância escolhida, como o *Split* do WaterGEMS. Vale para a rede toda ou para as tubulações selecionadas:
- encaixa pontas soltas no elemento mais próximo;
- divide a tubulação onde outra encosta no meio dela;
- divide a tubulação onde um nó, válvula ou bomba está sobre ela.

A validação lista os problemas na aba Problemas, e o clique duplo leva até o elemento. Quando o EPANET para (rede desequilibrada, bomba fora da curva, válvula isolando trechos), o relatório dele aparece traduzido na mesma aba, apontando cada elemento. A validação também pega erros comuns de digitação: carga da captação abaixo do terreno, níveis do reservatório digitados como cota e ajuste de VRP muito baixo. A simulação colore o mapa: os nós pela pressão e os tubos, à escolha, por velocidade, **perda de carga (m/km)** ou vazão. Em *Faixas e cores* você define o intervalo (de/até), a cor e a legenda de cada faixa, e a escolha fica salva no projeto. Ela colore pressão e velocidade no mapa, com linha do tempo de 24 h, botão "pior momento" e resumo de bombas, válvulas e reservatórios.

### Painel web (http://localhost:8765)
As abas ficam no cabeçalho de cada tela: **Sinótico · Dados recebidos · Mapa da rede · Calibração · Ao vivo**. Todas as telas ocupam a janela inteira sem rolar a página (inclusive em monitor ultrawide): mapa, diagramas e painéis laterais têm altura fixa pela tela, e só as colunas laterais rolam por dentro. Em janela pequena ou celular a página volta a rolar.


| Tela | Para quê |
|---|---|
| **Sinótico** | Esquema do sistema montado **a partir do cadastro aberto** ([sinotico.py](REV%200.1.0/motor/sinotico.py)): captações, bombas, reservatórios e válvulas viram blocos, e as tubulações entre eles viram redes. Mostra vazão animada, nível, pressões, bombas ligadas e indicadores; os gráficos de 24 h ficam na coluna lateral. A tela original do exemplo (index.html) continua na pasta, fora das abas |
| **Dados recebidos** | Análise dos dados que chegam (SABESP, SCADA, loggers) **antes** de ir para o modelo, num sistema padrão: captação → reservatório → ZB (gravidade) e reservatório → elevatória/booster → ZA. Em cada elemento, **Digitar 24 h** abre uma janela com as 24 horas do dia (00:00 a 23:00) para lançar as leituras, na unidade que vier (dá para colar uma coluna do Excel); cada dia lançado aparece num gráfico de perfil de 24 h para comparar com os outros dias. Séries longas ainda podem vir de planilha (CSV ou .xlsx, com de-para de colunas e unidades). A tela mostra gráficos, período, passo, lacunas, picos, sensor travado e o **balanço hídrico** (entrada − consumo − Δ volume). Os dados ficam em `<cadastro>_dados_recebidos.json` e não mexem no modelo. Há planilhas de exemplo em [testes/dados_exemplo](REV%200.1.0/testes/dados_exemplo) |
| **Mapa da rede** | Qualquer cadastro no mapa: cores por velocidade, vazão, perda de carga e pressão (NBR 12218), setas de fluxo, KPIs e gráfico de 24 h por elemento. Os elementos aparecem só como ícones, cada um preso ao seu ponto em qualquer zoom, e o mostrador abre no clique. **Limpar seleção** pelo ✕ no mapa, pelo botão do painel lateral, com Esc ou clicando no vazio. O mapa e o painel lateral têm altura fixa pela tela, e o painel rola por dentro |
| **Mapa → Proposta** | Alterar elementos (DN, status, setpoint, demanda, bomba) e comparar **Atual × Proposta** (vista Diferença e tabela de 14 indicadores, com energia). Propostas ficam salvas no cadastro |
| **Calibração** | Carregar medições de campo (CSV), comparar modelo × campo e calibrar automaticamente a rugosidade C e a demanda por grupo; salvar como proposta ou aplicar ao cadastro (com backup) |
| **Ao vivo** | Telemetria × **gêmeo digital**: alarmes de vazamento, limite, desvio, previsão de reservatório e comunicação. Inclui um simulador de SCADA com vazamento escondido |

### Integração com SCADA
O SCADA, ou um gateway OPC-UA, MQTT ou Node-RED, envia as leituras para o servidor:

```http
POST http://localhost:8765/api/telemetria
[{"elemento": "S1", "grandeza": "pressao", "valor": 19.6, "ts": "2026-10-24T07:15:00"}]
```

- `elemento`: código do cadastro.
- `grandeza`: `pressao` (mca; em válvula ou bomba vale o lado de jusante), `vazao` (L/s) ou `nivel` (m).
- `ts`: data/hora ISO ou segundos Unix.

Outras rotas da API usadas pelas telas: `GET /api/sinotico`, `GET /api/dados` e `POST /api/dados/ler · importar · digitar · excluir` (dados recebidos), `GET /api/versao` e `POST /api/encerrar` (o plugin usa para trocar um servidor antigo).

---

## Estrutura

```
0 - PROJETO PILOTO GWATER/
├─ README.md
├─ fluxo/                     fluxograma (draw.io): fluxo de trabalho + arquitetura
├─ REV 0.0.0/                 tela de referência original do Centro de Operações
├─ REV 0.2.0/                 GWATER.exe (programa à parte)
│  ├─ GWATER.exe              lançador (código em lancador/GWATER.cs)
│  ├─ preparar_ambiente.bat   cria o Python do motor (.venv), uma vez só
│  ├─ app/gwater_app.py       programa: abre a janela com as bibliotecas do QGIS
│  ├─ app/programa/           janela, faixa de menus, ferramentas, análises, consultas, relatórios
│  ├─ app/gwater/             núcleo do plugin (cópia): desenho, TRex, ModelBuilder, curvas, cálculo
│  ├─ motor/                  motor (cópia) + analises.py
│  ├─ painel/, cadastro/      Centro de Operações e cadastro de exemplo
│  ├─ app/programa/abertura.html  logos animados da abertura
│  ├─ ROTEIRO_FAIXA.md        roteiro de conferência da faixa × WaterGEMS
│  └─ testes/                 teste_programa, teste_analises, teste_modelbuilder, teste_desempenho, teste_tabela_valvulas
└─ REV 0.1.0/
   ├─ requirements.txt
   ├─ cadastro/               GeoPackage, projeto QGIS, gerador e modelo de dados
   ├─ modelo/                 .inp de referência (sistema da tela original)
   ├─ motor/                  Python: conversor, simulação, cenários, calibração, gêmeo digital, servidor
   ├─ painel/                 telas web (sinótico, dados recebidos, mapa, calibração, ao vivo)
   ├─ qgis_plugin/            plugin GWATER e instalador
   └─ testes/                 testes de ponta a ponta e dados de exemplo
```

| Módulo do motor | Função |
|---|---|
| `modelo.py`, `simular.py` | Sistema de exemplo da Fase 0 e execução do EPANET |
| `cadastro_para_inp.py` | Validação e conversão do cadastro; alterações de proposta |
| `importar_shp.py` | Shapefile → cadastro; cadastro novo vazio |
| `gwater_cli.py` | Ponte com o plugin do QGIS: validar, simular, exportar, novo, importar (→ JSON) |
| `rede_geojson.py` | Rede em GeoJSON para o mapa |
| `cenarios.py` | Propostas gravadas no GeoPackage |
| `calibracao.py` | Medições, métricas de ajuste e calibração automática |
| `aovivo.py` | Gêmeo digital, alarmes e simulador de telemetria |
| `dados_recebidos.py` | Dias digitados hora a hora e leitura de planilhas (CSV/XLSX), análise das séries e balanço hídrico dos dados recebidos |
| `sinotico.py` | Esquema do sinótico montado a partir da topologia do cadastro |
| `servidor.py` | Servidor HTTP do painel e API (troca de cadastro quando o QGIS abre outro; informa a versão) |
| `analises.py` (REV 0.2.0) | Incêndio, descarga, criticidade, zonas de pressão, energia, renovação, dimensionamento, qualidade, comparação de cenários e esqueletização |

| Módulo do plugin (`qgis_plugin/gwater`) | Função |
|---|---|
| `plugin.py` | Menu GWATER, barras de ferramentas e ações de cada botão |
| `acoes.py` | Catálogo dos botões: nome, ícone, explicação e grupos |
| `dock.py`, `estilo.py` | Central GWATER (abas Central, Problemas, Resultados) e o visual do painel web |
| `desenho.py` | Desenho como no WaterGEMS: nós automáticos, divisão, elemento sobre nó, Dividir tubulações |
| `ferramentas.py` | Janelas: novo cadastro, importar shapefile, TRex, distribuir demanda, dividir, guia |
| `cotas.py` | Fontes de cota do TRex (raster, curvas de nível, pontos cotados), sem raio de busca |
| `curvas.py` | Curvas de bomba (Pump Definitions) |
| `modelbuilder.py` | ModelBuilder: importação com de-para, valores e tolerância |
| `resultados.py`, `faixas.py` | Cores dos resultados (pressão, velocidade, perda de carga, vazão) e faixas editáveis |
| `motor.py` | Chama o motor (`gwater_cli.py`) e sobe ou reinicia o servidor do painel |

---

## Testes

Todos usam **cópias** do cadastro, e nenhum altera os seus dados.

```bash
cd "REV 0.1.0\motor"
..\.venv\Scripts\python.exe testar_conversor.py      # cadastro reproduz a Fase 0
..\.venv\Scripts\python.exe testar_cenarios.py       # propostas, manobras, PDA, gravação
cd ..\testes
..\.venv\Scripts\python.exe teste_importacao.py      # shapefile (2D e 3D) → cadastro → EPANET
..\.venv\Scripts\python.exe teste_calibracao.py      # recupera C e demanda "verdadeiros"
..\.venv\Scripts\python.exe teste_aovivo.py          # detecta vazamento sem falso alarme
..\.venv\Scripts\python.exe teste_sinotico.py        # sinótico do cadastro = sistema do exemplo
..\.venv\Scripts\python.exe teste_relatorio.py       # motivo do EPANET parar chega traduzido, no elemento
..\.venv\Scripts\python.exe teste_dados_recebidos.py # dias de 24 h digitados, planilhas CSV/XLSX, unidades, lacunas, picos e balanço
"C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat" teste_plugin.py   # menu, Central, rede desenhada do zero, TRex, ModelBuilder
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" teste_plugin.py          # o mesmo teste no QGIS 4
```

No GWATER.exe (REV 0.2.0):

```bash
cd "REV 0.2.0\testes"
..\.venv\Scripts\python.exe teste_analises.py       # cada análise roda e dá números com sentido físico
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" teste_modelbuilder.py  # importa uma rede em grade (GWATER_N=100: 20 mil tubos)
set QT_QPA_PLATFORM=offscreen
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" teste_programa.py   # clica nos 118 botões, desenha, calcula, analisa
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" teste_desempenho.py # rede de 20 mil tubos: importar, salvar, TRex, tabela, calcular (com limites de tempo)
"C:\Program Files\QGIS 4.2.2\bin\python-qgis.bat" teste_tabela_valvulas.py  # TCV sem ajuste, PRV INATIVA, notificações por tipo, colar e edição global
```

O roteiro para conferir, aba por aba, os 113 botões da faixa contra o WaterGEMS está em [`REV 0.2.0\ROTEIRO_FAIXA.md`](REV%200.2.0/ROTEIRO_FAIXA.md).

---

## Histórico

| Fase | Entrega |
|---|---|
| 0 | EPANET dentro da tela do Centro de Operações (sistema de exemplo) |
| 1 | Cadastro georreferenciado no QGIS |
| 2 | Conversor cadastro → EPANET e importador de shapefile |
| 3 | Plugin QGIS: Validar, Simular, linha do tempo |
| 4 | Mapa da rede no navegador |
| 5 | Propostas e comparação Atual × Proposta; manobras com demanda dependente da pressão |
| 6 | Calibração com medições de campo |
| 7 | Telemetria, gêmeo digital e alarmes |
| 8 | Plugin com menu único e desenho estilo WaterGEMS (nós automáticos, divisão de tubulações, MDT, demanda) |
| 9 | Curvas de bomba, ModelBuilder (importação com de-para e tolerância) e Dividir tubulações |
| 10 | Sinótico automático a partir do cadastro aberto; todas as telas em tela cheia; mapa só com ícones e Limpar seleção |
| 11 | Cotas do terreno (TRex) por raster, curvas de nível ou pontos, sem raio de busca; perda de carga e faixas de cores; motivo do EPANET parar, traduzido; shapefile 3D |
| 12 | Dados recebidos: sistema padrão, 24 h digitadas por dia, comparação entre dias e balanço hídrico |
| 13 | **GWATER.exe** (REV 0.2.0): programa à parte com faixa de menus como o WaterGEMS, propriedades, tabelas, consultas, cenários, ferramentas de análise (incêndio, descarga, criticidade, zonas, energia, renovação, dimensionamento, qualidade), relatórios e o Centro de Operações dentro do programa |
| 14 | GWATER.exe: abertura animada, temas claro e escuros nas Configurações, mapas de fundo claro/escuro/terreno, editor de simbologia (tamanho, rótulos, color coding), ModelBuilder um tipo por arquivo, otimização (salvar 4×, TRex 4×, tabelas 3× mais rápidos), notificações por tipo, TCV aberta/fechada, PRV INATIVA, edição global e Ctrl+V nas tabelas |

## Limitações conhecidas e próximos passos
- **GWATER.exe:** precisa do QGIS instalado no computador (usa as bibliotecas dele). Um instalador único, com QGIS e Python embutidos, é um próximo passo.
- **Dimensionamento:** é uma primeira rodada gulosa (aumenta, a cada passo, o diâmetro que dá mais ganho por real), não o algoritmo genético do Darwin; serve para propor e comparar.
- **Transientes, fire flow por hidrante de coluna com perdas do hidrante, PDD por curva de emissores e a análise de rompimento de redes por segmentos de registros** do WaterGEMS não estão no GWATER.
- **Dados reais:** ainda não foram testados com cadastro, shapefile ou medições reais. Até agora só com o exemplo e com dados sintéticos.
- **SCADA:** nenhum conectado. O gêmeo digital foi testado só com o simulador.
- **Propostas e calibração no plugin:** ficam no navegador (o plugin abre a página certa). No GWATER.exe, os cenários têm janela própria e as telas web abrem dentro do programa.
- **Dados recebidos → modelo:** os dados conferidos ainda não vão direto para a Calibração; é preciso ligar cada série a um elemento do cadastro (próximo passo).
- **Cota por curvas longe da rede:** sem raio de busca, um elemento muito além da última curva recebe um valor interpolado entre as duas curvas mais próximas, que é só aproximado.
- **Apagar elementos:** apagar um nó não apaga as tubulações ligadas; a validação aponta as pontas soltas.
- **Alarmes:** aparecem só na tela, sem e-mail, WhatsApp ou SMS.
- **Localização de vazamento:** é feita por setor, a partir dos macromedidores. Achar o trecho exato exige mais sensores de pressão.
- **Banco de telemetria:** SQLite. Para muitos sensores e anos de histórico, o caminho é TimescaleDB ou InfluxDB.
- **Energia:** estimada com rendimento de bomba de 70%, porque o cadastro ainda não tem curva de rendimento.
- **Internet:** o painel carrega a biblioteca MapLibre, as fontes e o mapa de fundo da internet.
