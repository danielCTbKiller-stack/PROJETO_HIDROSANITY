# GWATER · Projeto Piloto

Plataforma open source de **cadastro, modelagem hidráulica e operação** de redes de água: o cadastro georreferenciado fica no **QGIS**, os cálculos são do **EPANET 2.2**, e a decisão acontece num **Centro de Operações** no navegador.

O objetivo é juntar, sem licença comercial, o que hoje exige três produtos:

| Papel | Produto comercial | No GWATER |
|---|---|---|
| Cadastro georreferenciado | ArcGIS Pro | QGIS + GeoPackage ([cadastro](REV%200.1.0/cadastro)) |
| Modelagem, cenários e calibração | WaterGEMS | Motor Python + EPANET/WNTR ([motor](REV%200.1.0/motor)) e plugin QGIS ([qgis_plugin](REV%200.1.0/qgis_plugin)) |
| Operação, alarmes e gêmeo digital | Elipse Water | Painel web ([painel](REV%200.1.0/painel)) |

O fluxograma do projeto está em [fluxo/GWATER - Fluxo de Trabalho.drawio](fluxo) (abrir com o draw.io desktop). Ele tem uma página com o fluxo de trabalho e outra com a arquitetura.

---

## Início rápido

Requisitos: Windows, **Python 3.12** e **QGIS 3.44 LTR** (o plugin também declara compatibilidade com o QGIS 4).

```bash
cd "REV 0.1.0"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**1. Abrir o painel (Centro de Operações):**

```bash
.venv\Scripts\python.exe motor\servidor.py
```

Depois abra <http://localhost:8765>. Para usar outro cadastro, passe o caminho: `motor\servidor.py C:\caminho\cadastro.gpkg`.

**2. Instalar o plugin no QGIS** (com o QGIS fechado):

```bash
.venv\Scripts\python.exe qgis_plugin\instalar_plugin.py
```

Abra o QGIS, ative **GWATER** em *Complementos → Gerenciar* se ele não aparecer, e abra `cadastro\GWATER_cadastro.qgz`.

---

## O que o sistema faz

### Cadastro no QGIS
- **Arquivos:** `gwater_cadastro.gpkg` (dados) e `GWATER_cadastro.qgz` (projeto com estilos, formulários e snapping).
- **Camadas:** captação, reservatórios, bombas, válvulas, nós e trechos. Tabelas de padrões de consumo, curvas, controles, opções e materiais.
- **Regra de desenho (como no WaterGEMS):** bombas e válvulas são pontos. O trecho que chega no ponto é o lado de montante, e o que sai é o de jusante.
- **Preenchimento automático:** código, comprimento, nó inicial e final (pelo encaixe), rugosidade pelo material e volume útil.
- Os detalhes estão em [MODELO_DE_DADOS.md](REV%200.1.0/cadastro/MODELO_DE_DADOS.md).

### Importação de shapefile
`motor\importar_shp.py config.json` transforma um shapefile de rede num cadastro novo:
- reprojeta e separa multipartes
- cria os nós nas pontas, unindo folgas pela tolerância
- divide "T" não segmentados
- lê as cotas de um shapefile de pontos
- distribui a demanda pelos nós

O modelo de `config.json` está em [testes/shp_teste](REV%200.1.0/testes/shp_teste).

### Conversão cadastro → EPANET
[cadastro_para_inp.py](REV%200.1.0/motor/cadastro_para_inp.py) valida a rede e gera o `.inp`, que abre no EPANET 2.2 oficial.
- **O que a validação confere:** topologia, códigos repetidos, atributos desatualizados, diâmetro, rugosidade, conectividade e setores isolados por registros fechados.
- **Modo de demanda:** PDA (demanda dependente da pressão) por padrão, configurável em `opcoes_simulacao`. Assim é possível simular manobras: quem fica sem água se um registro for fechado.

### Plugin QGIS
- **Barra GWATER:** Validar, Simular e Painel web.
- **Validação:** lista os problemas, e o clique duplo leva até o elemento.
- **Simulação:** pressão e velocidade coloridas no mapa, linha do tempo de 24 h, botão "pior momento" e resumo de bombas, válvulas e reservatórios.

### Painel web (http://localhost:8765)

| Tela | Para quê |
|---|---|
| **Sinótico** | Diagrama do sistema de exemplo (tela original do COS) alimentado pelo EPANET |
| **Mapa da rede** | Qualquer cadastro no mapa: cores por velocidade, vazão, perda de carga e pressão (NBR 12218), setas de fluxo, mostradores ao vivo, KPIs e gráfico de 24 h por elemento |
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
   ├─ painel/                 telas web (sinótico, mapa, calibração, ao vivo)
   ├─ qgis_plugin/            plugin GWATER e instalador
   └─ testes/                 testes de ponta a ponta e dados de exemplo
```

| Módulo do motor | Função |
|---|---|
| `modelo.py`, `simular.py` | Sistema de exemplo da Fase 0 e execução do EPANET |
| `cadastro_para_inp.py` | Validação e conversão do cadastro; alterações de proposta |
| `importar_shp.py` | Shapefile → cadastro |
| `gwater_cli.py` | Ponte com o plugin do QGIS (validar/simular → JSON) |
| `rede_geojson.py` | Rede em GeoJSON para o mapa |
| `cenarios.py` | Propostas gravadas no GeoPackage |
| `calibracao.py` | Medições, métricas de ajuste e calibração automática |
| `aovivo.py` | Gêmeo digital, alarmes e simulador de telemetria |
| `servidor.py` | Servidor HTTP do painel e API |

---

## Testes

Todos usam **cópias** do cadastro, e nenhum altera os seus dados.

```bash
cd "REV 0.1.0\motor"
..\.venv\Scripts\python.exe testar_conversor.py      # cadastro reproduz a Fase 0
..\.venv\Scripts\python.exe testar_cenarios.py       # propostas, manobras, PDA, gravação
cd ..\testes
..\.venv\Scripts\python.exe teste_importacao.py      # shapefile → cadastro → EPANET
..\.venv\Scripts\python.exe teste_calibracao.py      # recupera C e demanda "verdadeiros"
..\.venv\Scripts\python.exe teste_aovivo.py          # detecta vazamento sem falso alarme
"C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat" teste_plugin.py   # plugin sem abrir o QGIS
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

## Limitações conhecidas e próximos passos
- **Dados reais:** ainda não foram testados com cadastro, shapefile ou medições reais. Até agora só com o exemplo e com dados sintéticos.
- **SCADA:** nenhum conectado. O gêmeo digital foi testado só com o simulador.
- **Plugin QGIS:** ainda não lista propostas nem faz calibração.
- **Alarmes:** aparecem só na tela, sem e-mail, WhatsApp ou SMS.
- **Localização de vazamento:** é feita por setor, a partir dos macromedidores. Achar o trecho exato exige mais sensores de pressão.
- **Banco de telemetria:** SQLite. Para muitos sensores e anos de histórico, o caminho é TimescaleDB ou InfluxDB.
- **Energia:** estimada com rendimento de bomba de 70%, porque o cadastro ainda não tem curva de rendimento.
- **Internet:** o painel carrega a biblioteca MapLibre e o mapa de fundo da internet.
