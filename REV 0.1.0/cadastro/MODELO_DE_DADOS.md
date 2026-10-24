# GWATER · Modelo de dados do cadastro (REV 0.1.0)

Arquivo: `gwater_cadastro.gpkg` · Projeto: `GWATER_cadastro.qgz`
Sistema de referência: **SIRGAS 2000 / UTM 23S (EPSG:31983)**. Para outra zona, altere `CRS` em `criar_cadastro.py`.

Para recriar tudo do zero (isso **apaga** o GeoPackage atual):

```
"C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat" criar_cadastro.py
```

## Regra de topologia (como no WaterGEMS)

- Todos os elementos pontuais (captação, reservatório, bomba, válvula, nó) são **nós**.
- O **trecho** liga dois nós e precisa começar e terminar exatamente sobre eles. O snapping já está ligado no projeto.
- Bomba e válvula: o trecho que **chega** no ponto é o lado de montante, e o que **sai** é o de jusante. Desenhe sempre no sentido do escoamento.
- Os códigos `id` precisam ser únicos em **todas** as camadas de pontos.

## Camadas

| Camada | Equivale no EPANET | Campos principais |
|---|---|---|
| Captação | Reservoir | carga_hidraulica (m) |
| Reservatórios | Tank | cota_fundo, nivel_ini/min/max (m), diametro (m), volume_util (calculado) |
| Bombas | Pump | cota, curva, status_inicial, rotacao_relativa |
| Válvulas | Valve | tipo (PRV, PSV, FCV, TCV...), ajuste (mca ou L/s), diametro (mm), status |
| Nós / junções | Junction | cota (m), demanda_base (L/s), padrao |
| Trechos | Pipe | no_inicial/no_final (automáticos), comprimento (automático), diametro_nominal (mm), material, rugosidade_hw, status (ABERTO, FECHADO, CV) |

Todas as camadas têm também os campos `situacao` (EXISTENTE / PROJETADO / DESATIVADO), `setor` e `observacao`.

## Preenchimento automático no formulário

- `id`: próximo código livre (N-0001, T-0001, V-0001...)
- `comprimento`: comprimento real da geometria
- `no_inicial` / `no_final`: código do nó em que cada ponta do trecho está encaixada
- `rugosidade_hw`: se ficar vazio, usa o C sugerido para o material (tabela `dominio_material`)
- `volume_util` do reservatório: π·D²/4 · (nível máx − nível mín)

## Tabelas do modelo

- `padrao_consumo`: multiplicadores por passo de 15 min
- `curva`: curvas de bomba (vazão em L/s × altura em m)
- `controle`: regras simples, por exemplo "B1 ABERTA se o nível de R1 ficar abaixo de 2,52 m"
- `opcoes_simulacao`: unidades, fórmula de perda de carga, duração e passos de tempo
- `dominio_material`: materiais e seu C de Hazen-Williams
