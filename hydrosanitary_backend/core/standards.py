# Diâmetros comerciais internos comuns para tubos de PVC predial (mm)
COMMERCIAL_DIAMETERS = [15, 20, 25, 32, 40, 50, 60, 75, 85, 110]

# Tabela padrão de aparelhos sanitários e pesos (NBR 5626)
FIXTURE_DATABASE = {
    "chuveiro_eletrico": {"weight": 0.4, "min_pressure": 1.0},
    "bacia_sanitaria_cx_acoplada": {"weight": 0.3, "min_pressure": 0.5},
    "lavatorio": {"weight": 0.1, "min_pressure": 0.5},
    "pia_cozinha": {"weight": 0.7, "min_pressure": 0.5},
    "maquina_lavar": {"weight": 1.0, "min_pressure": 1.0},
    "bacia_valvula_descarga": {"weight": 32.0, "min_pressure": 1.5},
    "ducha_higienica": {"weight": 0.4, "min_pressure": 1.0},
    "tanque": {"weight": 0.7, "min_pressure": 0.5},
    "bide": {"weight": 0.1, "min_pressure": 0.5},
    "torneira_jardim": {"weight": 0.4, "min_pressure": 0.5},
    "maquina_lavar_loucas": {"weight": 1.0, "min_pressure": 1.0},
}

# Rótulo, sigla (para os símbolos) e altura típica do ponto de utilização acima do piso (m)
FIXTURE_INFO = {
    "chuveiro_eletrico": ("Chuveiro elétrico", "CH", 2.10),
    "bacia_sanitaria_cx_acoplada": ("Bacia c/ caixa acoplada", "BS", 0.30),
    "bacia_valvula_descarga": ("Bacia c/ válvula de descarga", "VD", 1.10),
    "lavatorio": ("Lavatório", "LV", 0.60),
    "pia_cozinha": ("Pia de cozinha", "PIA", 1.00),
    "maquina_lavar": ("Máquina de lavar roupa", "MLR", 0.75),
    "maquina_lavar_loucas": ("Máquina de lavar louça", "MLL", 0.60),
    "ducha_higienica": ("Ducha higiênica", "DH", 0.50),
    "tanque": ("Tanque", "TQ", 0.90),
    "bide": ("Bidê", "BD", 0.30),
    "torneira_jardim": ("Torneira de jardim", "TJ", 0.60),
}

# Comprimentos equivalentes de conexões em tubo de PVC soldável (m), por diâmetro nominal (mm).
# Valores típicos de tabelas de fabricante (NBR 5626, anexo). Confira com a tabela do fabricante
# adotado no projeto; para diâmetros fora da faixa usa-se o valor da extremidade mais próxima e,
# entre dois diâmetros, interpola-se linearmente.
EQUIVALENT_LENGTH_DIAMETERS = [20, 25, 32, 40, 50, 60, 75, 85, 110]
EQUIVALENT_LENGTH_TABLE = {
    "joelho_90":          [1.1, 1.2, 2.0, 3.2, 3.4, 3.7, 3.9, 4.3, 4.9],
    "joelho_45":          [0.4, 0.5, 0.7, 1.0, 1.3, 1.5, 1.7, 1.8, 1.9],
    "te_passagem_direta": [0.7, 0.8, 0.9, 1.5, 2.2, 2.3, 2.4, 2.5, 2.6],
    "te_saida_lateral":   [2.3, 2.4, 3.1, 4.6, 7.3, 7.6, 7.8, 8.0, 8.3],
    "te_saida_bilateral": [2.3, 2.4, 3.1, 4.6, 7.3, 7.6, 7.8, 8.0, 8.3],
    "registro_gaveta":    [0.1, 0.2, 0.2, 0.3, 0.4, 0.4, 0.5, 0.5, 0.7],
    "registro_globo":     [11.4, 15.0, 22.0, 35.8, 37.9, 38.0, 40.0, 42.3, 50.9],
    "registro_pressao":   [11.4, 15.0, 22.0, 35.8, 37.9, 38.0, 40.0, 42.3, 50.9],
    "curva_90":           [0.4, 0.5, 0.6, 0.7, 1.2, 1.3, 1.4, 1.5, 1.6],
    "curva_45":           [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    "valvula_retencao":   [2.5, 2.7, 3.8, 4.9, 6.8, 7.1, 8.2, 9.3, 10.4],
    # corpo da VRP (perda localizada); a redução de pressão em si vem do ajuste (Node.prv_setpoint_mca)
    "valvula_redutora_pressao": [2.5, 2.7, 3.8, 4.9, 6.8, 7.1, 8.2, 9.3, 10.4],
    "hidrometro":         [2.0, 2.4, 3.2, 4.0, 5.0, 5.5, 6.0, 6.5, 7.5],
    "luva":               [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "bucha_reducao":      [0.3, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
}
# Conexões que mudam a direção do escoamento: quando o usuário informa uma delas num nó,
# ela substitui a detecção automática pela geometria nesse nó.
GEOMETRIC_FITTINGS = {"joelho_90", "joelho_45", "curva_90", "curva_45",
                      "te_passagem_direta", "te_saida_lateral", "te_saida_bilateral"}
FITTING_LABELS = {
    "joelho_90": "joelho 90°", "joelho_45": "joelho 45°", "te_passagem_direta": "tê, passagem direta",
    "te_saida_lateral": "tê, saída lateral", "te_saida_bilateral": "tê, saída bilateral",
    "registro_gaveta": "registro de gaveta", "registro_globo": "registro de globo",
    "registro_pressao": "registro de pressão", "curva_90": "curva 90°", "curva_45": "curva 45°",
    "valvula_retencao": "válvula de retenção", "valvula_redutora_pressao": "válvula redutora de pressão (VRP)",
    "hidrometro": "hidrômetro", "luva": "luva", "bucha_reducao": "bucha de redução",
}
FITTING_SHORT = {
    "joelho_90": "J90", "joelho_45": "J45", "te_passagem_direta": "TÊ", "te_saida_lateral": "TÊ",
    "te_saida_bilateral": "TÊ", "registro_gaveta": "RG", "registro_globo": "RGL", "registro_pressao": "RP",
    "curva_90": "C90", "curva_45": "C45", "valvula_retencao": "VR", "valvula_redutora_pressao": "VRP",
    "hidrometro": "HD", "luva": "LV", "bucha_reducao": "BR",
}
MATERIALS = ["PVC Soldável", "PPR", "CPVC", "PEX", "Cobre", "Aço galvanizado"]
# Pressão estática máxima nos pontos de utilização (NBR 5626: 400 kPa)
MAX_STATIC_PRESSURE_MCA = 40.0
