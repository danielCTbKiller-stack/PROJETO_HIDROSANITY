# GWATER · Projeto Piloto

Plataforma open source de **cadastro, modelagem hidráulica e operação** de redes de água: o cadastro georreferenciado fica no **QGIS**, os cálculos são do **EPANET 2.2**, e a decisão acontece num **Centro de Operações** no navegador.

O objetivo é juntar, sem licença comercial, o que hoje exige três produtos:

| Papel | Produto comercial | No GWATER |
|---|---|---|
| Cadastro georreferenciado | ArcGIS Pro | QGIS + GeoPackage ([cadastro](REV%200.1.0/cadastro)) |
| Modelagem, cenários e calibração | WaterGEMS | Motor Python + EPANET/WNTR ([motor](REV%200.1.0/motor)) e plugin QGIS ([qgis_plugin](REV%200.1.0/qgis_plugin)) |
| Operação, alarmes e gêmeo digital | Elipse Water | Painel web ([painel](REV%200.1.0/painel)) |

O fluxograma do projeto está em [fluxo/GWATER - Fluxo de Trabalho.drawio](fluxo) (abrir com o draw.io desktop). Ele tem uma página com o fluxo de trabalho (fases 0 a 12 e próximos passos) e outra com a arquitetura.

---

## Início rápido

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

---

## Histórico (REV 0.1.0)

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

## Limitações conhecidas e próximos passos
- **Dados reais:** ainda não foram testados com cadastro, shapefile ou medições reais. Até agora só com o exemplo e com dados sintéticos.
- **SCADA:** nenhum conectado. O gêmeo digital foi testado só com o simulador.
- **Propostas e calibração:** ficam no navegador (o plugin abre a página certa), não em janelas do QGIS.
- **Dados recebidos → modelo:** os dados conferidos ainda não vão direto para a Calibração; é preciso ligar cada série a um elemento do cadastro (próximo passo).
- **Cota por curvas longe da rede:** sem raio de busca, um elemento muito além da última curva recebe um valor interpolado entre as duas curvas mais próximas, que é só aproximado.
- **Apagar elementos:** apagar um nó não apaga as tubulações ligadas; a validação aponta as pontas soltas.
- **Alarmes:** aparecem só na tela, sem e-mail, WhatsApp ou SMS.
- **Localização de vazamento:** é feita por setor, a partir dos macromedidores. Achar o trecho exato exige mais sensores de pressão.
- **Banco de telemetria:** SQLite. Para muitos sensores e anos de histórico, o caminho é TimescaleDB ou InfluxDB.
- **Energia:** estimada com rendimento de bomba de 70%, porque o cadastro ainda não tem curva de rendimento.
- **Internet:** o painel carrega a biblioteca MapLibre, as fontes e o mapa de fundo da internet.
