# Roteiro de conferência da faixa de menus (GWATER × WaterGEMS)

Marque cada item: [x] funciona como no WaterGEMS, ou anote o problema ao lado.

## Aba Início

**Cálculo**
- [ ] **Cenários** — Cria, abre e roda cenários: a rede atual ou uma proposta (alterações de DN, status, demanda...). O cenário ativo é o que o Calcular usa.
- [ ] **Alternativas** — Edita as alterações do cenário ativo, elemento por elemento (o que muda em relação à rede atual).
- [ ] **Opções** — Opções de cálculo: duração, passos de tempo, fórmula de perda de carga, demanda dependente da pressão, pressões mínima e requerida.
- [ ] **Calcular** — Valida e roda a simulação de 24 h no EPANET. O mapa se colore com pressão e velocidade, e a linha do tempo fica em Tempos.
- [ ] **Validar** — Confere a rede sem calcular: ligações, códigos, diâmetros, curvas, cotas. Os problemas aparecem em Notificações.
- [ ] **Tempos** — Linha do tempo da simulação: escolha a hora, reproduza as 24 h ou vá ao pior momento.
- [ ] **Resumo** — Resumo do cálculo: balanço de vazões, pressões extremas, bombas, válvulas e reservatórios.
- [ ] **Notificações** — Lista de erros e avisos da validação e do EPANET. Clique duplo leva até o elemento.
- [ ] **Alertas** — Elementos fora dos limites: pressão abaixo de 10 ou acima de 50 mca, velocidade e perda de carga altas, reservatório vazio ou cheio.

**Desenho**
- [ ] **Desenhar** — Desenha tubulações e elementos (abre a aba Desenho).
    - [ ] Tubulação — Desenha uma tubulação (clique os vértices, clique direito termina).
    - [ ] Nó — Coloca um nó de consumo ou junção.
    - [ ] Reservatório — Coloca um reservatório de nível variável.
    - [ ] Captação — Coloca uma captação (nível fixo).
    - [ ] Bomba — Coloca uma bomba.
    - [ ] Válvula redutora (PRV) — Coloca uma válvula redutora de pressão.
- [ ] **Medir** — Mede distâncias e áreas no mapa.
    - [ ] Comprimento — Mede uma distância no mapa (clique os pontos, clique direito termina).
    - [ ] Área — Mede uma área no mapa (clique os vértices, clique direito termina).
- [ ] **Selecionar** — Seleciona elementos no mapa (clique ou janela). A setinha tem as outras formas.
    - [ ] Selecionar (clique ou janela) — Clique num elemento ou arraste uma janela. Shift soma à seleção, Ctrl tira.
    - [ ] Por polígono — Desenhe um polígono: seleciona tudo o que estiver dentro (clique direito fecha).
    - [ ] Por tipo de elemento — Seleciona todos os elementos de um ou mais tipos (tubulações, nós, válvulas...).
    - [ ] Por atributo — Seleciona por uma condição nos dados, por exemplo DN < 100 ou material = 'Cimento-amianto'.
    - [ ] Inverter seleção — Seleciona o que não estava selecionado (nos tipos que já tinham seleção).
    - [ ] Limpar seleção — Tira a seleção de todos os elementos (tecla Esc).
- [ ] **Por polígono** — Seleciona o que estiver dentro de um polígono desenhado.
- [ ] **Por elemento** — Seleciona todos os elementos de um tipo.
- [ ] **Por atributo** — Seleciona por uma condição nos dados.
- [ ] **Excluir** — Apaga os elementos selecionados (e as tubulações ligadas a um nó apagado).
- [ ] **Localizar** — Procura um elemento pelo código e vai até ele.

**Componentes comuns**
- [ ] **Central de demanda** — Tabela de todos os nós com demanda e padrão: edite, multiplique, distribua e confira o total.
- [ ] **Padrões** — Padrões de consumo (multiplicadores ao longo do dia), com gráfico.
- [ ] **Curvas de bomba** — Curvas das bombas (vazão × altura), como as Pump Definitions do WaterGEMS.
- [ ] **Controles** — Regras de operação: liga/desliga bomba ou abre/fecha válvula por nível, pressão ou hora.

**Vistas**
- [ ] **Gráficos** — Gráfico ao longo do dia dos elementos selecionados (pressão, vazão, velocidade, nível...).
- [ ] **Tabelas** — Tabelas editáveis de cada tipo de elemento (FlexTables), com os resultados do cálculo.
- [ ] **Conjuntos de seleção** — Guarda a seleção atual com um nome e a recupera depois.
- [ ] **Propriedades** — Mostra o painel de propriedades do elemento selecionado (dados e resultados).
- [ ] **Atualizar** — Redesenha o mapa e recarrega os resultados.

**Ferramentas**
- [ ] **Topologia ativa** — Ativa ou desativa elementos: os desativados ficam no cadastro mas saem do cálculo.
- [ ] **ModelBuilder** — Importa elementos de qualquer arquivo (shapefile, GeoPackage...) com de-para de colunas.

## Aba Desenho

**Desenho**
- [ ] **Selecionar** _(repetido, já conferido)_ — Seleciona elementos (clique ou janela).
    - [ ] Selecionar (clique ou janela) — Clique num elemento ou arraste uma janela. Shift soma à seleção, Ctrl tira.
    - [ ] Por polígono — Desenhe um polígono: seleciona tudo o que estiver dentro (clique direito fecha).
    - [ ] Por tipo de elemento — Seleciona todos os elementos de um ou mais tipos (tubulações, nós, válvulas...).
    - [ ] Por atributo — Seleciona por uma condição nos dados, por exemplo DN < 100 ou material = 'Cimento-amianto'.
    - [ ] Inverter seleção — Seleciona o que não estava selecionado (nos tipos que já tinham seleção).
    - [ ] Limpar seleção — Tira a seleção de todos os elementos (tecla Esc).
- [ ] **Excluir** _(repetido, já conferido)_ — Apaga os elementos selecionados.
- [ ] **Localizar** _(repetido, já conferido)_ — Procura um elemento pelo código.
- [ ] **Mover** — Arrasta um elemento ou vértice; as tubulações ligadas acompanham.

**Ligação**
- [ ] **Tubulação** — Desenha uma tubulação: clique os vértices e clique direito para terminar. As pontas viram nós ou ligam nos elementos sob o cursor.
- [ ] **Dividir** — Corrige ligações com uma tolerância: encaixa pontas soltas e divide tubulações onde outra encosta.

**Nó**
- [ ] **Nó** — Coloca um nó (junção ou ponto de consumo). Sobre uma tubulação, ela é dividida.
- [ ] **Reservatório** — Reservatório de nível variável (tank).
- [ ] **Captação** — Captação ou manancial: nível fixo (reservoir).
- [ ] **Hidrante** — Nó do tipo hidrante (usado na análise de incêndio).
- [ ] **Ponto de consumo** — Nó do tipo consumo (avaliado pela NBR 12218).

**Bomba**
- [ ] **Bomba** — Coloca uma bomba. Escolha a curva no formulário (Curvas de bomba).
- [ ] **Estação elevatória** — Agrupa as bombas selecionadas numa estação elevatória (campo elevatória).
- [ ] **Rotação variável** — Define a rotação relativa das bombas selecionadas (inversor de frequência).

**Válvula**
- [ ] **PRV** — Válvula redutora de pressão: mantém a pressão de saída.
- [ ] **PSV** — Válvula sustentadora de pressão: mantém a pressão de entrada.
- [ ] **PBV** — Válvula quebra-pressão: reduz a pressão num valor fixo.
- [ ] **FCV** — Válvula controladora de vazão: limita a vazão.
- [ ] **TCV** — Válvula de estrangulamento (perda de carga ajustável).
- [ ] **GPV** — Válvula de perda genérica (curva perda × vazão).

**Outros**
- [ ] **Registro** — Registro de manobra (abre e fecha trechos). Fechado, isola a rede como no WaterGEMS.
- [ ] **Ponto cotado** — Ponto com a cota do terreno (vira fonte para o TRex).

**Anotação**
- [ ] **Borda** — Desenha um retângulo de anotação no mapa.
- [ ] **Texto** — Escreve um texto no mapa.
- [ ] **Linha** — Desenha uma linha de anotação no mapa.

**Medição**
- [ ] **Comprimento** — Mede uma distância.
- [ ] **Área** — Mede uma área.

**Propriedades**
- [ ] **Propriedades** _(repetido, já conferido)_ — Painel de propriedades do elemento selecionado.
- [ ] **Protótipos** — Valores usados em tudo o que for desenhado: DN, material, situação, cota, demanda, tipo...

## Aba Análise

**Cálculo**
- [ ] **Cenários** _(repetido, já conferido)_ — Cria, abre e roda cenários: a rede atual ou uma proposta (alterações de DN, status, demanda...). O cenário ativo é o que o Calcular usa.
- [ ] **Alternativas** _(repetido, já conferido)_ — Edita as alterações do cenário ativo, elemento por elemento (o que muda em relação à rede atual).
- [ ] **Opções** _(repetido, já conferido)_ — Opções de cálculo: duração, passos de tempo, fórmula de perda de carga, demanda dependente da pressão, pressões mínima e requerida.
- [ ] **Calcular** _(repetido, já conferido)_ — Valida e roda a simulação de 24 h no EPANET. O mapa se colore com pressão e velocidade, e a linha do tempo fica em Tempos.
- [ ] **Validar** _(repetido, já conferido)_ — Confere a rede sem calcular: ligações, códigos, diâmetros, curvas, cotas. Os problemas aparecem em Notificações.
- [ ] **Tempos** _(repetido, já conferido)_ — Linha do tempo da simulação: escolha a hora, reproduza as 24 h ou vá ao pior momento.
- [ ] **Resumo** _(repetido, já conferido)_ — Resumo do cálculo: balanço de vazões, pressões extremas, bombas, válvulas e reservatórios.
- [ ] **Notificações** _(repetido, já conferido)_ — Lista de erros e avisos da validação e do EPANET. Clique duplo leva até o elemento.
- [ ] **Alertas** _(repetido, já conferido)_ — Elementos fora dos limites: pressão abaixo de 10 ou acima de 50 mca, velocidade e perda de carga altas, reservatório vazio ou cheio.

**Ferramentas de análise**
- [ ] **Incêndio** — Vazão disponível em cada hidrante mantendo a pressão residual (Fire Flow).
- [ ] **Descarga** — Que tubulações cada descarga de rede limpa (velocidade de arraste), como o Flushing.
- [ ] **Renovação de redes** — Ordena as tubulações por prioridade de troca: idade, material, desempenho e criticidade.
- [ ] **Otimização** — Dimensionamento automático de diâmetros (Designer) e calibração automática (Calibrator).
    - [ ] Dimensionar diâmetros — Menor custo para as tubulações selecionadas atenderem pressão e velocidade.
    - [ ] Calibrar (C e demanda) — Calibração automática com medições de campo (abre no Centro de Operações).
- [ ] **Custo de energia** — Energia e custo das bombas com tarifa por hora (ponta e fora de ponta).
- [ ] **Zonas de pressão** — Divide a rede em zonas separadas por bombas, válvulas reguladoras e registros fechados.
- [ ] **Criticidade** — O que deixa de ser entregue quando cada tubulação sai de operação.
- [ ] **Mais** — Outras análises.
    - [ ] Idade da água — Tempo que a água leva da fonte até cada ponto (horas).
    - [ ] Cloro residual — Decaimento do cloro na rede (mg/L).
    - [ ] Balanço hídrico (dados recebidos) — Dados de campo e balanço hídrico do sistema.

**Vistas de análise**
- [ ] **Gráficos** _(repetido, já conferido)_ — Gráficos dos elementos selecionados ao longo do dia.
- [ ] **Tabelas** _(repetido, já conferido)_ — Tabelas de elementos com dados e resultados.
- [ ] **Propriedades** _(repetido, já conferido)_ — Painel de propriedades.
- [ ] **Conjuntos de seleção** _(repetido, já conferido)_ — Seleções guardadas com nome.
- [ ] **Consultas** — Consultas prontas: revisão da rede, rastreamento e resultados.
- [ ] **Navegador** — Percorre, um a um, os elementos de uma consulta ou seleção.
- [ ] **Contornos** — Curvas de mesma pressão, carga ou cota sobre o mapa.
- [ ] **Atualizar** _(repetido, já conferido)_ — Redesenha o mapa.

**SCADA**
- [ ] **Simulador SCADA** — Telemetria e gêmeo digital, com simulador de SCADA (Ao vivo).

## Aba Componentes

**Comuns**
- [ ] **Central de demanda** _(repetido, já conferido)_ — Demandas e padrões de todos os nós.
- [ ] **Padrões** _(repetido, já conferido)_ — Padrões de consumo.
- [ ] **Curvas de bomba** _(repetido, já conferido)_ — Curvas das bombas.
- [ ] **Controles** _(repetido, já conferido)_ — Regras de operação.

**Zonas**
- [ ] **Zonas** — Setores da rede (campo setor): crie, renomeie e atribua aos elementos selecionados.

**Biblioteca**
- [ ] **Bibliotecas de engenharia** — Materiais (C de Hazen-Williams, vida útil), diâmetros comerciais e custos.
- [ ] **Protótipos** _(repetido, já conferido)_ — Valores padrão dos elementos desenhados.

**Outros**
- [ ] **Qualidade da água** — Idade da água e cloro residual.
- [ ] **Perdas localizadas** — Biblioteca de coeficientes K (curvas, registros, tês) para as tubulações selecionadas.
- [ ] **Extensões de dados** — Cria campos novos nos elementos (dados do usuário).

**Dados de campo**
- [ ] **Séries de campo** — Dados recebidos (SABESP, SCADA, loggers): 24 h digitadas ou planilha, e balanço hídrico.
- [ ] **Medições** — Medições de campo para a calibração.

## Aba Revisão

**Revisão**
- [ ] **Comparação de cenários** — Roda dois cenários e mostra os indicadores e as diferenças elemento por elemento.

**Histórico de alterações**
- [ ] **Histórico de alterações** — Registra cada elemento criado, alterado ou apagado (quem, quando, o quê).
    - [ ] Ligar / desligar o registro — Liga ou desliga o registro das alterações.
    - [ ] Ver histórico — Abre a lista de alterações registradas.
- [ ] **Arquivo compactado** — Guarda uma cópia compactada (.zip) do cadastro e do projeto, com data e hora.

## Aba Exibir

**Zoom e vista**
- [ ] **Zoom total** — Mostra a rede inteira.
- [ ] **Aproximar** — Ferramenta de aproximar (clique ou janela).
- [ ] **Afastar** — Ferramenta de afastar.
- [ ] **Mover mapa** — Arrasta o mapa (também com o botão do meio do mouse).
- [ ] **Vista anterior** — Volta para a vista anterior.
- [ ] **Vista seguinte** — Avança para a vista seguinte.
- [ ] **Zoom na seleção** — Enquadra os elementos selecionados.
- [ ] **Vistas com nome** — Guarda e recupera enquadramentos do mapa.
- [ ] **Vista aérea** — Janela pequena com a rede inteira e o retângulo da vista atual.

**Desenho**
- [ ] **Simbologia** — Cores e símbolos da camada escolhida no painel Simbologia dos elementos.
- [ ] **Mapa de fundo** — OpenStreetMap, imagem de satélite ou um arquivo (raster, shapefile) como fundo.
- [ ] **Rótulos** — Mostra ou esconde os códigos dos elementos no mapa.
- [ ] **Atualizar** _(repetido, já conferido)_ — Redesenha o mapa.

**Elemento**
- [ ] **Gráficos** _(repetido, já conferido)_ — Gráficos dos elementos selecionados.
- [ ] **Perfis** — Perfil entre dois nós: terreno e linha piezométrica ao longo do caminho.
- [ ] **Tabelas** _(repetido, já conferido)_ — Tabelas de elementos.
- [ ] **Propriedades** _(repetido, já conferido)_ — Painel de propriedades.
- [ ] **Gráfico rápido** — Clique num elemento e veja o gráfico dele na hora.
- [ ] **Protótipos** _(repetido, já conferido)_ — Valores padrão do desenho.

**Seleção e consulta**
- [ ] **Conjuntos de seleção** _(repetido, já conferido)_ — Seleções guardadas.
- [ ] **Consultas** _(repetido, já conferido)_ — Consultas prontas.
- [ ] **Navegador** _(repetido, já conferido)_ — Percorre os elementos de uma consulta.

**Superfície**
- [ ] **Contornos** _(repetido, já conferido)_ — Curvas de mesma pressão, carga ou cota.

**Painéis**
- [ ] **Simbologia dos elementos** — Mostra ou esconde o painel de camadas.
- [ ] **Propriedades** — Mostra ou esconde o painel de propriedades.
- [ ] **Consultas** — Mostra ou esconde o painel de consultas.
- [ ] **Cálculo** — Mostra ou esconde o painel de cálculo (notificações e tempos).

## Aba Ferramentas

**Topologia**
- [ ] **Topologia ativa** _(repetido, já conferido)_ — Ativa ou desativa elementos no cálculo.

**Criação do modelo**
- [ ] **ModelBuilder** _(repetido, já conferido)_ — Importa elementos de arquivos com de-para.
- [ ] **TRex** — Cota do terreno de raster, curvas de nível ou pontos, em todos os elementos.
- [ ] **LoadBuilder** — Distribui consumos de hidrômetros (pontos) ou de setores (polígonos) para os nós.
- [ ] **Polígonos de Thiessen** — Área de influência de cada nó (polígonos de Voronoi).
- [ ] **Distribuir demanda** — Distribui uma vazão total pelos nós, proporcional ao comprimento das tubulações.
- [ ] **Novo de shapefile** — Cria um cadastro novo a partir de um shapefile de rede.

**Ferramentas**
- [ ] **Centro de códigos** — Confere códigos repetidos ou vazios e renumera elementos.
- [ ] **Ferramentas externas** — Abre o cadastro no QGIS, o modelo no EPANET ou a pasta do cadastro.
    - [ ] Abrir no QGIS — Abre o projeto do cadastro no QGIS (com o plugin GWATER).
    - [ ] Abrir .inp no EPANET — Gera o .inp e abre no EPANET 2.2 (se estiver instalado).
    - [ ] Abrir a pasta do cadastro — Abre a pasta do cadastro no Explorador do Windows.
- [ ] **Esqueletizador** — Cria uma cópia simplificada da rede: corta ramais finos e une tubulações em série.
- [ ] **Extensões de dados** _(repetido, já conferido)_ — Campos novos nos elementos.
- [ ] **Mais** — Outras ferramentas.
    - [ ] Faixas e cores — Faixas e cores dos resultados no mapa.
    - [ ] Limpar resultados — Tira as camadas de resultado do mapa.
    - [ ] Exportar .inp — Grava o modelo para o EPANET 2.2.
    - [ ] Guia dos botões — Explicação de todos os botões.

## Aba Relatório

**Relatório**
- [ ] **Relatório personalizado** — Monta um relatório com as seções escolhidas e salva em PDF ou HTML.

**Tabelas de elementos**
- [ ] **Tubulações** — Tabela das tubulações com resultados.
- [ ] **Nós** — Tabela dos nós com resultados.
- [ ] **Bombas** — Tabela das bombas.
- [ ] **Válvulas** — Tabela das válvulas.
- [ ] **Reservatórios** — Tabela dos reservatórios.

**Tabelas**
- [ ] **Tabelas** _(repetido, já conferido)_ — Todas as tabelas.

**Relatórios**
- [ ] **Resumo do cenário** — Opções, totais e resultados do cenário calculado.
- [ ] **Inventário do modelo** — Quantidade de cada elemento e comprimento total da rede.
- [ ] **Inventário de tubulações** — Comprimento por diâmetro e por material.

## Aba Centro de Operações

**Telas**
- [ ] **Sinótico** — Esquema do sistema montado a partir do cadastro aberto.
- [ ] **Dados recebidos** _(repetido, já conferido)_ — Dados de campo e balanço hídrico.
- [ ] **Mapa e propostas** — Mapa web com propostas e comparação Atual × Proposta.
- [ ] **Calibração** _(repetido, já conferido)_ — Medições de campo e calibração automática.
- [ ] **Ao vivo** _(repetido, já conferido)_ — Telemetria, gêmeo digital e alarmes.

## Menu Arquivo

- [ ] **Novo cadastro…** — Cadastro vazio, em qualquer pasta e sistema UTM.
- [ ] **Novo de shapefile…** — Cadastro novo a partir de um shapefile de rede.
- [ ] **Abrir…** — Abre um cadastro GWATER (.qgz).
- [ ] **Abrir recente** — 
- [ ] **Salvar edições** — Grava no cadastro tudo o que foi desenhado ou alterado (Ctrl+S).
- [ ] **Salvar projeto** — Grava o projeto (vistas, estilos, mapa de fundo, conjuntos de seleção).
- [ ] **Salvar cadastro como…** — Copia o cadastro e o projeto com outro nome.
- [ ] **Exportar .inp (EPANET)…** — Grava o modelo para o EPANET 2.2.
- [ ] **Arquivo compactado (.zip)…** — Cópia de segurança do cadastro.
- [ ] **Abrir no QGIS** — Abre o cadastro no QGIS.
- [ ] **Guia dos botões** — Explicação de todos os botões.
- [ ] **Sobre o GWATER** — 
- [ ] **Sair** — Fecha o programa.