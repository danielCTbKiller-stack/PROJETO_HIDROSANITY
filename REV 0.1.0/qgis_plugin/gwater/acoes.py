"""Catálogo de todos os botões do GWATER.

Menu, barras de ferramentas, painel Central e Guia são montados a partir desta lista,
então o texto que explica cada botão é sempre o mesmo em todo lugar.
Cada ação: (chave, texto, ícone, o que faz). A chave vira o método `acao_<chave>` do plugin.
"""

GRUPOS = [
    ("cadastro", "1 · Cadastro", "Onde ficam os dados da rede: um GeoPackage e o projeto QGIS que o acompanha.", [
        ("novo", "Novo cadastro", "novo",
         "Cria um cadastro vazio numa pasta que você escolhe, com estilos, formulários e encaixe já configurados. "
         "Depois é só desenhar."),
        ("importar", "Novo cadastro de shapefile", "importar",
         "Cria um cadastro NOVO a partir de um shapefile de rede (linhas): cria os nós nas pontas, divide os “T”, "
         "lê as cotas de um shapefile de pontos e distribui a demanda."),
        ("modelbuilder", "ModelBuilder (importar elementos)", "modelbuilder",
         "Importa para o cadastro ABERTO tubulações, nós, válvulas, bombas, reservatórios ou captações de qualquer "
         "arquivo. Você liga cada coluna do arquivo a um campo do cadastro (de → para), traduz os valores "
         "(material, tipo...) e escolhe a tolerância para criar os nós nas pontas dos tubos."),
        ("abrir", "Abrir cadastro", "abrir",
         "Abre um projeto GWATER (.qgz) já existente."),
        ("salvar", "Salvar edições", "salvar",
         "Grava no GeoPackage tudo o que foi desenhado ou alterado em todas as camadas da rede. "
         "Validar e Simular sempre usam o que está salvo, e perguntam se houver algo pendente."),
    ]),
    ("desenho", "2 · Desenhar a rede (como no WaterGEMS)",
     "Escolha o elemento e clique no mapa. O GWATER cria os nós, divide as tubulações e preenche os códigos sozinho.", [
        ("tubulacao", "Tubulação", "tubulacao",
         "Clique os vértices e termine com o botão direito. Ponta solta ganha um nó novo; ponta sobre um elemento "
         "liga nele; ponta no meio de outra tubulação divide essa tubulação e liga as duas. Comprimento, nós "
         "inicial/final e rugosidade são preenchidos sozinhos. Desenhe no sentido do escoamento."),
        ("no", "Nó / consumo", "no",
         "Clique para inserir um nó. Sobre uma tubulação, ela é dividida em duas ligadas ao nó. "
         "Informe cota e demanda no formulário (ou use Cotas do MDT e Distribuir demanda)."),
        ("valvula", "Válvula", "valvula",
         "Clique sobre a tubulação no ponto da válvula: o tubo é dividido e a válvula fica entre os dois trechos "
         "(o de chegada é montante). Sobre um nó existente, o nó vira válvula. Informe tipo (PRV, FCV…) e ajuste."),
        ("bomba", "Bomba", "bomba",
         "Igual à válvula: clique sobre a tubulação (ou sobre um nó) no local da bomba. Informe a curva, cadastrada "
         "na tabela Curvas."),
        ("reservatorio", "Reservatório", "reservatorio",
         "Insere um reservatório de nível variável. Informe cota de fundo, níveis inicial, mínimo e máximo e "
         "diâmetro. O volume útil é calculado."),
        ("captacao", "Captação", "captacao",
         "Insere uma fonte de carga fixa: manancial, ETA ou ponto de entrega de uma adutora. Informe a carga "
         "hidráulica (m)."),
        ("mover", "Mover / editar vértices", "mover",
         "Arraste nós, válvulas ou vértices de tubulação. Ao mover um elemento, as tubulações ligadas a ele "
         "acompanham e o comprimento é recalculado."),
        ("dividir", "Dividir tubulações", "dividir",
         "Corrige a ligação da rede com uma tolerância que você escolhe: encaixa pontas soltas no elemento mais "
         "próximo, divide a tubulação onde outra encosta no meio dela (“T”) e onde um nó, válvula ou bomba está "
         "sobre ela. Vale para toda a rede ou só para as tubulações selecionadas."),
        ("atributos", "Ver / editar dados", "atributos",
         "Clique num elemento para ver e alterar os dados dele: DN, material, cota, demanda, ajuste da válvula…"),
    ]),
    ("modelo", "3 · Preparar o modelo", "Completa os dados que o EPANET precisa e confere a rede antes de calcular.", [
        ("curvas", "Curvas de bomba", "curvas",
         "Cadastra as curvas das bombas (vazão × altura), com gráfico, como as Pump Definitions do WaterGEMS. "
         "Depois a curva é escolhida numa lista no formulário de cada bomba."),
        ("cotas", "Cotas do terreno (TRex)", "cotas",
         "Como o TRex do WaterGEMS: preenche o campo cota (cota do terreno) de nós, válvulas, bombas, "
         "reservatórios e captações — tudo ou só o que você escolher — a partir de um raster (MDT/MDE), de curvas de nível "
         "(shp/gpkg, interpolando entre as duas curvas mais próximas) ou de pontos cotados, de uma camada do "
         "projeto ou direto do arquivo. Preenche só as vazias ou todas e pode dar cota a cada nó novo desenhado."),
        ("demanda", "Distribuir demanda", "demanda",
         "Reparte uma vazão total (L/s) entre os nós de toda a rede, de um setor ou dos selecionados, proporcional "
         "ao comprimento de tubulação ligado a cada nó (ou igual para todos)."),
        ("validar", "Validar rede", "validar",
         "Confere a rede sem calcular: pontas soltas, códigos repetidos, diâmetro ou rugosidade vazios, setores "
         "isolados por registro fechado. A lista aparece na aba Problemas; clique duplo leva até o elemento."),
    ]),
    ("simular", "4 · Simular no EPANET", "Calcula 24 h de operação e mostra o resultado no próprio mapa do QGIS.", [
        ("simular", "Simular 24 h", "simular",
         "Roda o EPANET 2.2 e pinta o mapa: pressão nos nós (faixas da NBR 12218) e velocidade nas tubulações. "
         "Na aba Resultados, a linha do tempo mostra cada hora e “Pior momento” vai ao instante crítico."),
        ("cores", "Faixas e cores", "cores",
         "Escolhe a variável que colore as tubulações (velocidade, perda de carga ou vazão) e define as faixas "
         "de cada cor (de, até, cor e texto da legenda), também para a pressão nos nós. Fica salvo no projeto."),
        ("limpar", "Limpar resultados", "limpar",
         "Tira do mapa as camadas de resultado da última simulação. O cadastro não é alterado."),
        ("exportar", "Exportar .inp", "exportar",
         "Gera o arquivo do modelo para abrir no EPANET 2.2 oficial ou em outro programa compatível."),
    ]),
    ("web", "5 · Centro de Operações (navegador)",
     "Abre o painel web já carregado com o cadastro deste projeto. Ele fica disponível enquanto o QGIS estiver aberto.", [
        ("mapa", "Mapa e propostas", "mapa",
         "Mapa da rede no navegador. Crie propostas (trocar DN, fechar registro, mudar setpoint ou demanda) e "
         "compare Atual × Proposta com 14 indicadores, inclusive energia."),
        ("calibracao", "Calibração", "calibracao",
         "Carregue medições de campo (CSV), compare com o modelo e ajuste a rugosidade e a demanda "
         "automaticamente. O resultado pode virar proposta ou ser aplicado ao cadastro (com cópia de segurança)."),
        ("aovivo", "Ao vivo", "aovivo",
         "Telemetria × gêmeo digital: alarmes de vazamento, pressão fora da faixa, desvio do modelo e previsão "
         "de nível de reservatório."),
        ("dados", "Dados recebidos", "importar",
         "Analisa os dados que chegaram (SABESP, SCADA, loggers) antes de usar no modelo: planilha por elemento do "
         "sistema padrão (captação, reservatório, elevatória, ZA, ZB), gráficos, lacunas, picos e balanço hídrico."),
        ("sinotico", "Sinótico", "painel",
         "Tela do Centro de Operações com o sistema de exemplo (captação, elevatória, R1 e VRPs) calculado pelo "
         "EPANET."),
    ]),
    ("ajuda", "Ajuda", "", [
        ("guia", "Guia dos botões", "ajuda",
         "Mostra o que cada botão faz e o passo a passo para montar uma rede do zero."),
    ]),
]

# rótulo curto (em até duas linhas) dos botões da Central; o texto completo fica no menu e na dica
CURTO = {
    "novo": "Novo\ncadastro", "importar": "Novo de\nshapefile", "modelbuilder": "Model\nBuilder",
    "dividir": "Dividir\ntubulações", "curvas": "Curvas de\nbomba", "abrir": "Abrir\ncadastro", "salvar": "Salvar\nedições",
    "no": "Nó /\nconsumo", "mover": "Mover", "atributos": "Ver / editar\ndados", "cotas": "Cotas do\nterreno",
    "demanda": "Distribuir\ndemanda", "validar": "Validar\nrede", "simular": "Simular\n24 h",
    "limpar": "Limpar\nresultados", "cores": "Faixas e\ncores", "exportar": "Exportar\n.inp", "mapa": "Mapa e\npropostas", "dados": "Dados\nrecebidos", "guia": "Guia dos\nbotões",
}

# botões que também ficam nas barras de ferramentas do QGIS
BARRA_DESENHO = ["tubulacao", "no", "valvula", "bomba", "reservatorio", "captacao", "mover", "dividir", "atributos",
                 "salvar"]
BARRA_MODELO = ["central", "validar", "simular", "limpar", "mapa"]

CENTRAL = ("central", "Central GWATER", "gwater",
           "Abre o painel lateral com todos os botões do GWATER explicados, a lista de problemas e os resultados.")

PASSO_A_PASSO = [
    ("Crie ou abra o cadastro", "Novo cadastro (rede do zero), Novo cadastro de shapefile ou Abrir cadastro. Para trazer "
                                "elementos de outros arquivos para o cadastro aberto, use o ModelBuilder."),
    ("Desenhe a fonte", "Insira a Captação ou o Reservatório de onde a água sai."),
    ("Desenhe as tubulações", "Use Tubulação. Comece na fonte e siga o sentido do escoamento. Os nós aparecem sozinhos "
                              "nas pontas e onde uma tubulação encosta em outra."),
    ("Coloque válvulas e bombas", "Clique sobre a tubulação no local exato; ela é dividida e o equipamento fica no meio. "
                                  "Cadastre as curvas em Curvas de bomba e escolha a curva no formulário da bomba."),
    ("Complete os dados", "Cotas do MDT para as cotas, Distribuir demanda para o consumo, e Ver / editar dados para "
                          "DN, material, curva da bomba e ajuste das válvulas."),
    ("Salve e valide", "Salvar edições e depois Validar rede. Corrija o que aparecer na aba Problemas."),
    ("Simule", "Simular 24 h. Veja pressões e velocidades no mapa e use a linha do tempo."),
    ("Decida", "Mapa e propostas, para comparar alternativas; Calibração, quando houver medições de campo; "
               "Ao vivo, para a operação com telemetria."),
]


def todas():
    """Todas as ações, na ordem do catálogo: {chave: (texto, ícone, descrição, grupo)}."""
    out = {CENTRAL[0]: (*CENTRAL[1:], None)}
    for gid, _, _, acoes in GRUPOS:
        for chave, texto, icone, desc in acoes:
            out[chave] = (texto, icone, desc, gid)
    return out
