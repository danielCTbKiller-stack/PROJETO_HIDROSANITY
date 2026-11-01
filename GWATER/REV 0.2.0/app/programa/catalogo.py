"""Catálogo da faixa de menus do GWATER.exe (as abas do WaterGEMS, em português).

Cada botão: (chave, texto, ícone, tamanho, explicação[, submenu]).
  tamanho "G" = botão grande (ícone em cima, texto embaixo); "P" = pequeno (ícone e texto ao lado).
  submenu: lista de (chave, texto, ícone, explicação) que abre ao clicar na setinha do botão.
A chave chama o método acao_<chave> do núcleo (programa/nucleo.py). Os botões que já existiam no plugin
(tubulacao, simular, cotas...) usam o mesmo código do plugin.
"""

SELECIONAR = [
    ("selecionar", "Selecionar (clique ou janela)", "selecionar", "Clique num elemento ou arraste uma janela. Shift soma à seleção, Ctrl tira."),
    ("sel_poligono", "Por polígono", "sel_poligono", "Desenhe um polígono: seleciona tudo o que estiver dentro (clique direito fecha)."),
    ("sel_tipo", "Por tipo de elemento", "sel_tipo", "Seleciona todos os elementos de um ou mais tipos (tubulações, nós, válvulas...)."),
    ("sel_atributo", "Por atributo", "sel_atributo", "Seleciona por uma condição nos dados, por exemplo DN < 100 ou material = 'Cimento-amianto'."),
    ("sel_inverter", "Inverter seleção", "sel_inverter", "Seleciona o que não estava selecionado (nos tipos que já tinham seleção)."),
    ("sel_limpar", "Limpar seleção", "sel_limpar", "Tira a seleção de todos os elementos (tecla Esc)."),
]
MEDIR = [
    ("medir_comprimento", "Comprimento", "medir_comprimento", "Mede uma distância no mapa (clique os pontos, clique direito termina)."),
    ("medir_area", "Área", "medir_area", "Mede uma área no mapa (clique os vértices, clique direito termina)."),
]
CALCULO = ("Cálculo", [
    ("cenarios", "Cenários", "cenarios", "G", "Cria, abre e roda cenários: a rede atual ou uma proposta (alterações de DN, status, demanda...). O cenário ativo é o que o Calcular usa."),
    ("alternativas", "Alternativas", "alternativas", "P", "Edita as alterações do cenário ativo, elemento por elemento (o que muda em relação à rede atual)."),
    ("opcoes", "Opções", "opcoes", "P", "Opções de cálculo (Calculation Options): período estendido ou regime permanente, hora de início, passos, multiplicador de demanda, convergência, PDD e limites dos alertas."),
    ("simular", "Calcular", "calcular", "G", "Valida e roda a simulação de 24 h no EPANET. O mapa se colore com pressão e velocidade, e a linha do tempo fica em Tempos."),
    ("validar", "Validar", "validar", "P", "Confere a rede sem calcular: ligações, códigos, diâmetros, curvas, cotas. Os problemas aparecem em Notificações."),
    ("tempos", "Tempos", "tempos", "P", "Linha do tempo da simulação: escolha a hora, reproduza as 24 h ou vá ao pior momento."),
    ("resumo", "Resumo", "resumo", "P", "Resumo do cálculo: balanço de vazões, pressões extremas, bombas, válvulas e reservatórios."),
    ("notificacoes", "Notificações", "notificacoes", "P", "Lista de erros e avisos da validação e do EPANET. Clique duplo leva até o elemento."),
    ("alertas", "Alertas", "alertas", "P", "Elementos fora dos limites (Opções > Limites; padrão NBR 12218: 10 a 50 mca): pressão, velocidade e perda de carga, reservatório vazio ou cheio."),
])

FAIXA = [
    ("inicio", "Início", [
        CALCULO,
        ("Desenho", [
            ("disposicao", "Desenhar", "tubulacao", "G", "Desenha tubulações e elementos (abre a aba Desenho).", [
                ("tubulacao", "Tubulação", "tubulacao", "Desenha uma tubulação (clique os vértices, clique direito termina)."),
                ("no", "Nó", "no", "Coloca um nó de consumo ou junção."),
                ("reservatorio", "Reservatório", "reservatorio", "Coloca um reservatório de nível variável."),
                ("captacao", "Captação", "captacao", "Coloca uma captação (nível fixo)."),
                ("bomba", "Bomba", "bomba", "Coloca uma bomba."),
                ("valvula_prv", "Válvula redutora (PRV)", "prv", "Coloca uma válvula redutora de pressão."),
            ]),
            ("medir", "Medir", "medir", "G", "Mede distâncias e áreas no mapa.", MEDIR),
            ("selecionar", "Selecionar", "selecionar", "G", "Seleciona elementos no mapa (clique ou janela). A setinha tem as outras formas.", SELECIONAR),
            ("sel_poligono", "Por polígono", "sel_poligono", "P", "Seleciona o que estiver dentro de um polígono desenhado."),
            ("sel_tipo", "Por elemento", "sel_tipo", "P", "Seleciona todos os elementos de um tipo."),
            ("sel_atributo", "Por atributo", "sel_atributo", "P", "Seleciona por uma condição nos dados."),
            ("excluir", "Excluir", "excluir", "P", "Apaga os elementos selecionados (e as tubulações ligadas a um nó apagado)."),
            ("localizar", "Localizar", "localizar", "P", "Procura um elemento pelo código e vai até ele."),
        ]),
        ("Componentes comuns", [
            ("central_demanda", "Central de demanda", "demanda", "G", "Tabela de todos os nós com demanda e padrão: edite, multiplique, distribua e confira o total."),
            ("padroes", "Padrões", "padroes", "P", "Padrões de consumo (multiplicadores ao longo do dia), com gráfico."),
            ("curvas", "Curvas de bomba", "curvas", "P", "Curvas das bombas (vazão × altura), como as Pump Definitions do WaterGEMS."),
            ("controles", "Controles", "controles", "P", "Controles simples e lógicos: liga/desliga bomba, abre/fecha válvula ou muda o ajuste por nível, pressão ou hora.", [
                ("controles", "Controles simples", "controles", "Uma condição e uma ação: nível, pressão ou hora."),
                ("controles_logicos", "Controles lógicos", "controles", "SE / E / OU … ENTÃO … SENÃO, com prioridade (Logical Controls)."),
            ]),
        ]),
        ("Vistas", [
            ("graficos", "Gráficos", "graficos", "G", "Gráfico ao longo do dia dos elementos selecionados (pressão, vazão, velocidade, nível...)."),
            ("tabelas", "Tabelas", "tabelas", "G", "Tabelas editáveis de cada tipo de elemento (FlexTables), com os resultados do cálculo."),
            ("conjuntos", "Conjuntos de seleção", "conjuntos", "P", "Guarda a seleção atual com um nome e a recupera depois."),
            ("propriedades", "Propriedades", "propriedades", "P", "Mostra o painel de propriedades do elemento selecionado (dados e resultados)."),
            ("atualizar", "Atualizar", "atualizar", "P", "Redesenha o mapa e recarrega os resultados."),
        ]),
        ("Ferramentas", [
            ("topologia_ativa", "Topologia ativa", "topologia", "G", "Ativa ou desativa elementos: os desativados ficam no cadastro mas saem do cálculo."),
            ("modelbuilder", "ModelBuilder", "modelbuilder", "G", "Importa elementos de qualquer arquivo (shapefile, GeoPackage...) com de-para de colunas."),
        ]),
        ("Assistente", [
            ("assistente", "Assistente de IA", "ajuda", "G", "Claude, GPT ou Gemini dentro do programa: pela sua conta (site oficial, assinatura Pro) ou pela API, com a escolha do modelo e os dados da rede como contexto."),
        ]),
    ]),
    ("desenho", "Desenho", [
        ("Desenho", [
            ("selecionar", "Selecionar", "selecionar", "G", "Seleciona elementos (clique ou janela).", SELECIONAR),
            ("excluir", "Excluir", "excluir", "P", "Apaga os elementos selecionados."),
            ("localizar", "Localizar", "localizar", "P", "Procura um elemento pelo código."),
            ("mover", "Mover", "mover", "P", "Arrasta um elemento ou vértice; as tubulações ligadas acompanham."),
            ("converter", "Converter em…", "propriedades", "P", "Troca o tipo dos elementos selecionados no mesmo lugar (nó → hidrante, nó → PRV…), como o Morph do WaterGEMS."),
        ]),
        ("Ligação", [
            ("tubulacao", "Tubulação", "tubulacao", "G", "Desenha uma tubulação: clique os vértices e clique direito para terminar. As pontas viram nós ou ligam nos elementos sob o cursor."),
            ("dividir", "Dividir", "dividir", "P", "Corrige ligações com uma tolerância: encaixa pontas soltas e divide tubulações onde outra encosta."),
            ("inverter_sentido", "Inverter sentido", "tubulacao", "P", "A tubulação selecionada passa a ir do nó final para o inicial (Reverse)."),
            ("unir_nos", "Unir nós próximos", "no", "P", "Nós a menos da tolerância viram um só, com as demandas somadas (Merge Nodes in Close Proximity)."),
        ]),
        ("Nó", [
            ("no", "Nó", "no", "G", "Coloca um nó (junção ou ponto de consumo). Sobre uma tubulação, ela é dividida."),
            ("reservatorio", "Reservatório", "reservatorio", "P", "Reservatório de nível variável (tank)."),
            ("captacao", "Captação", "captacao", "P", "Captação ou manancial: nível fixo (reservoir)."),
            ("hidrante", "Hidrante", "hidrante", "P", "Nó do tipo hidrante (usado na análise de incêndio)."),
            ("ponto_consumo", "Consumidor", "ponto_consumo", "P", "Consumidor (casa) sem tubulação própria: liga sozinho no nó ou no meio da tubulação mais perto, e a demanda vai para lá (Customer Meter)."),
            ("ligar_consumidores", "Religar consumidores", "ponto_consumo", "P", "Liga os consumidores selecionados (ou todos) ao nó ou ao meio de tubulação mais perto."),
        ]),
        ("Bomba", [
            ("bomba", "Bomba", "bomba", "G", "Coloca uma bomba. Escolha a curva no formulário (Curvas de bomba)."),
            ("estacao", "Estação elevatória", "estacao", "P", "Agrupa as bombas selecionadas numa estação elevatória (campo elevatória)."),
            ("bomba_variavel", "Rotação variável", "bomba_variavel", "P", "Define a rotação relativa das bombas selecionadas (inversor de frequência)."),
        ]),
        ("Válvula", [
            ("valvula_prv", "PRV", "prv", "P", "Válvula redutora de pressão: mantém a pressão de saída."),
            ("valvula_psv", "PSV", "psv", "P", "Válvula sustentadora de pressão: mantém a pressão de entrada."),
            ("valvula_pbv", "PBV", "pbv", "P", "Válvula quebra-pressão: reduz a pressão num valor fixo."),
            ("valvula_fcv", "FCV", "fcv", "P", "Válvula controladora de vazão: limita a vazão."),
            ("valvula_tcv", "TCV", "tcv", "P", "Válvula de estrangulamento (perda de carga ajustável)."),
            ("valvula_gpv", "GPV", "gpv", "P", "Válvula de perda genérica (curva perda × vazão)."),
        ]),
        ("Outros", [
            ("registro", "Registro", "registro", "G", "Registro de manobra (abre e fecha trechos). Fechado, isola a rede como no WaterGEMS."),
            ("ponto_cotado", "Ponto cotado", "ponto_cotado", "P", "Ponto com a cota do terreno (vira fonte para o TRex)."),
        ]),
        ("Anotação", [
            ("borda", "Borda", "borda", "P", "Desenha um retângulo de anotação no mapa."),
            ("texto", "Texto", "texto", "P", "Escreve um texto no mapa."),
            ("linha", "Linha", "linha", "P", "Desenha uma linha de anotação no mapa."),
        ]),
        ("Medição", [
            ("medir_comprimento", "Comprimento", "medir_comprimento", "P", "Mede uma distância."),
            ("medir_area", "Área", "medir_area", "P", "Mede uma área."),
        ]),
        ("Propriedades", [
            ("propriedades", "Propriedades", "propriedades", "G", "Painel de propriedades do elemento selecionado."),
            ("prototipos", "Protótipos", "prototipos", "G", "Valores usados em tudo o que for desenhado: DN, material, situação, cota, demanda, tipo..."),
        ]),
    ]),
    ("analise", "Análise", [
        CALCULO,
        ("Ferramentas de análise", [
            ("incendio", "Incêndio", "incendio", "G", "Vazão disponível em cada hidrante mantendo a pressão residual (Fire Flow)."),
            ("descarga", "Descarga", "descarga", "G", "Que tubulações cada descarga de rede limpa (velocidade de arraste), como o Flushing."),
            ("renovacao", "Renovação de redes", "renovacao", "G", "Ordena as tubulações por prioridade de troca: idade, material, desempenho e criticidade."),
            ("darwin", "Otimização", "darwin", "G", "Dimensionamento automático de diâmetros (Designer) e calibração automática (Calibrator).", [
                ("dimensionar", "Dimensionar diâmetros", "dimensionar", "Menor custo para as tubulações selecionadas atenderem pressão e velocidade."),
                ("calibracao_darwin", "Calibrar (Darwin Calibrator)", "calibracao", "Calibração com os momentos medidos em campo: rugosidade por grupo, demanda e status, pelo método genético ou gradiente."),
            ]),
            ("calibracao_darwin", "Calibração", "calibracao", "G", "Darwin Calibrator: momentos medidos em campo, grupos de rugosidade e demanda, status desconhecido; as melhores soluções viram cenário ou vão ao cadastro."),
            ("energia", "Custo de energia", "energia", "G", "Energia e custo das bombas com tarifa por hora (ponta e fora de ponta)."),
            ("zonas_pressao", "Zonas de pressão", "zonas_pressao", "P", "Divide a rede em zonas separadas por bombas, válvulas reguladoras e registros fechados."),
            ("criticidade", "Criticidade", "criticidade", "P", "O que deixa de ser entregue quando cada tubulação sai de operação."),
            ("mais_analises", "Mais", "mais", "P", "Outras análises.", [
                ("idade_agua", "Idade da água", "qualidade", "Tempo que a água leva da fonte até cada ponto (horas)."),
                ("cloro", "Cloro residual", "cloro", "Decaimento do cloro na rede (mg/L)."),
                ("rastreamento", "Rastrear a origem da água", "qualidade", "Que parte da água de cada nó vem de cada captação ou reservatório (Trace)."),
                ("dados", "Balanço hídrico (dados recebidos)", "dados", "Dados de campo e balanço hídrico do sistema."),
            ]),
        ]),
        ("Vistas de análise", [
            ("graficos", "Gráficos", "graficos", "G", "Gráficos dos elementos selecionados ao longo do dia."),
            ("tabelas", "Tabelas", "tabelas", "G", "Tabelas de elementos com dados e resultados."),
            ("propriedades", "Propriedades", "propriedades", "G", "Painel de propriedades."),
            ("conjuntos", "Conjuntos de seleção", "conjuntos", "P", "Seleções guardadas com nome."),
            ("consultas", "Consultas", "consultas", "P", "Consultas prontas: revisão da rede, rastreamento e resultados."),
            ("navegador", "Navegador", "navegador", "P", "Percorre, um a um, os elementos de uma consulta ou seleção."),
            ("contornos", "Contornos", "contornos", "P", "Curvas de mesma pressão, carga ou cota sobre o mapa."),
            ("atualizar", "Atualizar", "atualizar", "P", "Redesenha o mapa."),
        ]),
        ("SCADA", [
            ("aovivo", "Simulador SCADA", "aovivo", "G", "Telemetria e gêmeo digital, com simulador de SCADA (Ao vivo)."),
        ]),
    ]),
    ("componentes", "Componentes", [
        ("Comuns", [
            ("central_demanda", "Central de demanda", "demanda", "G", "Demandas e padrões de todos os nós."),
            ("demandas_unitarias", "Demandas unitárias", "demanda", "P", "Consumo por unidade (habitante, m², leito…) aplicado aos nós selecionados (Unit Demands)."),
            ("padroes", "Padrões", "padroes", "P", "Padrões de consumo."),
            ("curvas", "Curvas de bomba", "curvas", "P", "Curvas das bombas."),
            ("controles", "Controles", "controles", "P", "Regras de operação.", [
                ("controles", "Controles simples", "controles", "Uma condição e uma ação."),
                ("controles_logicos", "Controles lógicos", "controles", "SE / E / OU … ENTÃO … SENÃO, com prioridade."),
            ]),
        ]),
        ("Zonas", [
            ("zonas", "Zonas", "zonas", "G", "Setores da rede (campo setor): crie, renomeie e atribua aos elementos selecionados."),
        ]),
        ("Biblioteca", [
            ("bibliotecas", "Bibliotecas de engenharia", "bibliotecas", "G", "Materiais (C de Hazen-Williams, vida útil), diâmetros comerciais e custos."),
            ("prototipos", "Protótipos", "prototipos", "G", "Valores padrão dos elementos desenhados."),
        ]),
        ("Outros", [
            ("qualidade_opcoes", "Qualidade da água", "qualidade", "P", "Idade da água, cloro residual e origem da água (Trace)."),
            ("curvas_valvula", "Curvas de válvula (GPV)", "gpv", "P", "Perda de carga × vazão de cada válvula GPV (Valve Characteristics)."),
            ("tarifas", "Tarifas de energia", "energia", "P", "Preço da energia por hora do dia, usado no Custo de energia (Energy Pricing)."),
            ("perdas", "Perdas localizadas", "perdas", "P", "Biblioteca de coeficientes K (curvas, registros, tês) para as tubulações selecionadas."),
            ("extensoes", "Extensões de dados", "extensoes", "P", "Cria campos novos nos elementos (dados do usuário)."),
        ]),
        ("Dados de campo", [
            ("dados", "Séries de campo", "dados", "G", "Dados recebidos (SABESP, SCADA, loggers): 24 h digitadas ou planilha, e balanço hídrico."),
            ("calibracao_darwin", "Calibração", "calibracao", "P", "Dados de campo e calibração (Darwin Calibrator)."),
            ("calibrador_watergems", "Calibrador WaterGEMS", "calibracao", "P", "Calibrador WaterGEMS (página web): leituras de campo × modelo do WaterGEMS, gráficos e planilhas."),
        ]),
    ]),
    ("revisao", "Revisão", [
        ("Revisão", [
            ("comparar_cenarios", "Comparação de cenários", "comparar", "G", "Roda dois cenários e mostra os indicadores e as diferenças elemento por elemento."),
        ]),
        ("Histórico de alterações", [
            ("rastreio", "Histórico de alterações", "rastreio", "G", "Registra cada elemento criado, alterado ou apagado (quem, quando, o quê).", [
                ("rastreio_ligar", "Ligar / desligar o registro", "rastreio", "Liga ou desliga o registro das alterações."),
                ("rastreio_ver", "Ver histórico", "rastreio_ver", "Abre a lista de alterações registradas."),
            ]),
            ("arquivar", "Arquivo compactado", "arquivar", "G", "Guarda uma cópia compactada (.zip) do cadastro e do projeto, com data e hora."),
        ]),
    ]),
    ("exibir", "Exibir", [
        ("Zoom e vista", [
            ("zoom_total", "Zoom total", "zoom_total", "G", "Mostra a rede inteira."),
            ("zoom_mais", "Aproximar", "zoom_mais", "P", "Ferramenta de aproximar (clique ou janela)."),
            ("zoom_menos", "Afastar", "zoom_menos", "P", "Ferramenta de afastar."),
            ("pan", "Mover mapa", "pan", "P", "Arrasta o mapa (também com o botão do meio do mouse)."),
            ("zoom_anterior", "Vista anterior", "zoom_anterior", "P", "Volta para a vista anterior."),
            ("zoom_proximo", "Vista seguinte", "zoom_proximo", "P", "Avança para a vista seguinte."),
            ("zoom_selecao", "Zoom na seleção", "zoom_selecao", "P", "Enquadra os elementos selecionados."),
            ("vistas_nomeadas", "Vistas com nome", "vistas", "P", "Guarda e recupera enquadramentos do mapa."),
            ("vista_aerea", "Vista aérea", "vista_aerea", "P", "Janela pequena com a rede inteira e o retângulo da vista atual."),
        ]),
        ("Desenho", [
            ("simbologia", "Simbologia", "simbologia", "P", "Cores e símbolos da camada escolhida no painel Simbologia dos elementos."),
            ("fundos", "Mapa de fundo", "fundos", "P", "OpenStreetMap, imagem de satélite ou um arquivo (raster, shapefile) como fundo."),
            ("rotulos", "Rótulos", "rotulos", "P", "Mostra ou esconde os códigos dos elementos no mapa."),
            ("rotulos_resultados", "Rótulos de resultados", "rotulos", "P", "Escreve no mapa a pressão, vazão ou velocidade de cada elemento na hora escolhida (Annotation)."),
            ("atualizar", "Atualizar", "atualizar", "P", "Redesenha o mapa."),
        ]),
        ("Elemento", [
            ("graficos", "Gráficos", "graficos", "G", "Gráficos dos elementos selecionados."),
            ("perfis", "Perfis", "perfis", "G", "Perfil entre dois nós: terreno e linha piezométrica ao longo do caminho."),
            ("tabelas", "Tabelas", "tabelas", "G", "Tabelas de elementos."),
            ("propriedades", "Propriedades", "propriedades", "G", "Painel de propriedades."),
            ("grafico_rapido", "Gráfico rápido", "grafico_rapido", "P", "Clique num elemento e veja o gráfico dele na hora."),
            ("prototipos", "Protótipos", "prototipos", "P", "Valores padrão do desenho."),
        ]),
        ("Seleção e consulta", [
            ("conjuntos", "Conjuntos de seleção", "conjuntos", "G", "Seleções guardadas."),
            ("consultas", "Consultas", "consultas", "P", "Consultas prontas."),
            ("navegador", "Navegador", "navegador", "P", "Percorre os elementos de uma consulta."),
        ]),
        ("Superfície", [
            ("contornos", "Contornos", "contornos", "G", "Curvas de mesma pressão, carga ou cota."),
        ]),
        ("Painéis", [
            ("painel_simbologia", "Simbologia dos elementos", "camadas", "P", "Mostra ou esconde o painel de camadas."),
            ("painel_propriedades", "Propriedades", "propriedades", "P", "Mostra ou esconde o painel de propriedades."),
            ("painel_consultas", "Consultas", "consultas", "P", "Mostra ou esconde o painel de consultas."),
            ("painel_calculo", "Cálculo", "tempos", "P", "Mostra ou esconde o painel de cálculo (notificações e tempos)."),
        ]),
    ]),
    ("ferramentas", "Ferramentas", [
        ("Topologia", [
            ("topologia_ativa", "Topologia ativa", "topologia", "G", "Ativa ou desativa elementos no cálculo."),
        ]),
        ("Criação do modelo", [
            ("modelbuilder", "ModelBuilder", "modelbuilder", "G", "Importa elementos de arquivos com de-para."),
            ("cotas", "TRex", "cotas", "G", "Cota do terreno de raster, curvas de nível ou pontos, em todos os elementos."),
            ("loadbuilder", "LoadBuilder", "loadbuilder", "P", "Distribui consumos de hidrômetros (pontos) ou de setores (polígonos) para os nós."),
            ("thiessen", "Polígonos de Thiessen", "thiessen", "P", "Área de influência de cada nó (polígonos de Voronoi)."),
            ("demanda", "Distribuir demanda", "demanda", "P", "Distribui uma vazão total pelos nós, proporcional ao comprimento das tubulações."),
            ("importar", "Novo de shapefile", "importar", "P", "Cria um cadastro novo a partir de um shapefile de rede."),
        ]),
        ("Ferramentas", [
            ("ids", "Centro de códigos", "ids", "G", "Confere códigos repetidos ou vazios e renumera elementos."),
            ("externas", "Ferramentas externas", "externas", "G", "Abre o cadastro no QGIS, o modelo no EPANET ou a pasta do cadastro.", [
                ("abrir_qgis", "Abrir no QGIS", "qgis", "Abre o projeto do cadastro no QGIS (com o plugin GWATER)."),
                ("abrir_epanet", "Abrir .inp no EPANET", "epanet", "Gera o .inp e abre no EPANET 2.2 (se estiver instalado)."),
                ("abrir_pasta", "Abrir a pasta do cadastro", "pasta", "Abre a pasta do cadastro no Explorador do Windows."),
            ]),
            ("esqueletizar", "Esqueletizador", "esqueletizar", "P", "Cria uma cópia simplificada da rede: corta ramais finos e une tubulações em série."),
            ("extensoes", "Extensões de dados", "extensoes", "P", "Campos novos nos elementos."),
            ("mais_ferramentas", "Mais", "mais", "P", "Outras ferramentas.", [
                ("cores", "Faixas e cores", "cores", "Faixas e cores dos resultados no mapa."),
                ("limpar", "Limpar resultados", "limpar", "Tira as camadas de resultado do mapa."),
                ("exportar", "Exportar .inp", "exportar", "Grava o modelo para o EPANET 2.2."),
                ("guia", "Guia dos botões", "ajuda", "Explicação de todos os botões."),
            ]),
        ]),
    ]),
    ("relatorio", "Relatório", [
        ("Relatório", [
            ("relatorio_personalizado", "Relatório personalizado", "relatorio", "G", "Monta um relatório com as seções escolhidas e salva em PDF ou HTML."),
        ]),
        ("Tabelas de elementos", [
            ("tabela_trecho", "Tubulações", "tubulacao", "G", "Tabela das tubulações com resultados."),
            ("tabela_no_juncao", "Nós", "no", "G", "Tabela dos nós com resultados."),
            ("tabela_bomba", "Bombas", "bomba", "G", "Tabela das bombas."),
            ("tabela_valvula", "Válvulas", "valvula", "G", "Tabela das válvulas."),
            ("tabela_reservatorio", "Reservatórios", "reservatorio", "G", "Tabela dos reservatórios."),
        ]),
        ("Tabelas", [
            ("tabelas", "Tabelas", "tabelas", "G", "Todas as tabelas."),
        ]),
        ("Relatórios", [
            ("detalhes_elemento", "Detalhes do elemento", "propriedades", "P", "Relatório dos elementos selecionados: todos os dados, resultados hora a hora, gráfico e leituras de campo (Element Details)."),
            ("resumo_cenario", "Resumo do cenário", "resumo", "P", "Opções, totais e resultados do cenário calculado."),
            ("inventario", "Inventário do modelo", "inventario", "P", "Quantidade de cada elemento e comprimento total da rede."),
            ("inventario_tubos", "Inventário de tubulações", "inventario_tubos", "P", "Comprimento por diâmetro e por material."),
        ]),
    ]),
    ("operacoes", "Centro de Operações", [
        ("Telas", [
            ("sinotico", "Sinótico", "painel", "G", "Esquema do sistema montado a partir do cadastro aberto."),
            ("dados", "Dados recebidos", "dados", "G", "Dados de campo e balanço hídrico."),
            ("mapa", "Mapa e propostas", "mapa", "G", "Mapa web com propostas e comparação Atual × Proposta."),
            ("calibracao", "Calibração", "calibracao", "G", "Medições de campo e calibração automática."),
            ("calibrador_watergems", "Calibrador WaterGEMS", "calibracao", "G", "Calibrador WaterGEMS (página web) numa aba do programa."),
            ("aovivo", "Ao vivo", "aovivo", "G", "Telemetria, gêmeo digital e alarmes."),
        ]),
    ]),
]

ARQUIVO = [
    ("novo", "Novo cadastro…", "novo", "Cadastro vazio, em qualquer pasta e sistema UTM."),
    ("importar", "Novo de shapefile…", "importar", "Cadastro novo a partir de um shapefile de rede."),
    ("abrir", "Abrir…", "abrir", "Abre um cadastro GWATER (.qgz)."),
    ("recentes", "Abrir recente", "abrir", ""),
    None,
    ("salvar", "Salvar edições", "salvar", "Grava no cadastro tudo o que foi desenhado ou alterado (Ctrl+S)."),
    ("salvar_projeto", "Salvar projeto", "salvar", "Grava o projeto (vistas, estilos, mapa de fundo, conjuntos de seleção)."),
    ("salvar_como", "Salvar cadastro como…", "salvar", "Copia o cadastro e o projeto com outro nome."),
    None,
    ("exportar", "Exportar .inp (EPANET)…", "exportar", "Grava o modelo para o EPANET 2.2."),
    ("arquivar", "Arquivo compactado (.zip)…", "arquivar", "Cópia de segurança do cadastro."),
    ("abrir_qgis", "Abrir no QGIS", "qgis", "Abre o cadastro no QGIS."),
    None,
    ("guia", "Guia dos botões", "ajuda", "Explicação de todos os botões."),
    ("sobre", "Sobre o GWATER", "gwater", ""),
    ("sair", "Sair", "sair", "Fecha o programa."),
]
ACESSO_RAPIDO = [("novo", "novo", "Novo cadastro"), ("abrir", "abrir", "Abrir cadastro"),
                 ("salvar", "salvar", "Salvar edições (Ctrl+S)"), ("desfazer", "desfazer", "Desfazer (Ctrl+Z)"),
                 ("refazer", "refazer", "Refazer (Ctrl+Y)"), ("simular", "calcular", "Calcular (F5)")]


def todos():
    """{chave: (texto, ícone, explicação)} de todos os botões e itens de submenu."""
    out = {}
    for _, _, grupos in FAIXA:
        for _, botoes in grupos:
            for b in botoes:
                out.setdefault(b[0], (b[1], b[2], b[4]))
                for s in (b[5] if len(b) > 5 else []):
                    out.setdefault(s[0], (s[1], s[2], s[3]))
    for item in ARQUIVO:
        if item:
            out.setdefault(item[0], (item[1], item[2], item[3]))
    return out
