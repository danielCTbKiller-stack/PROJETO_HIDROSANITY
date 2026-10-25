"""Ferramentas de análise (aba Análise): janelas de parâmetros, tabela de resultados e camada colorida.

O cálculo é do motor (motor/analises.py, no Python do projeto com o EPANET); aqui ficam as janelas.
Todas usam o cenário ativo e a escolha de incluir os PROJETADOS.
"""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from gwater import motor
from gwater.estilo import COR

from .util import (
    PONTOS, Dialogo, camada_resultado, cores_categorias, eixo, figura, ids_selecionados, janela_resultado, legenda,
    num, selecionar_ids,
)


def rodar(nucleo, nome, texto, **par):
    """Roda a análise no motor (com o cenário ativo); None se falhou (os problemas vão para Notificações)."""
    gpkg = nucleo._preparar()
    if not gpkg:
        return None
    if nome not in ("esqueletizar", "comparar"):
        alts = nucleo.alteracoes()
        if alts:
            par["alteracoes"] = alts
    nucleo.janela.ocupado(texto + (f" (cenário {nucleo.cenario['nome']})" if nucleo.cenario else ""))
    nucleo.dock.status.setText(texto)
    try:
        dados = motor.analise(nome, gpkg, nucleo.projetados(), **par)
    except Exception as e:
        nucleo.janela.livre()
        nucleo.aviso(f"Falha ao chamar o motor: {e}")
        return None
    nucleo.janela.livre()
    if not dados.get("ok"):
        n = nucleo.dock.mostrar_problemas(dados.get("itens", []))
        nucleo.mostrar_dock()
        nucleo.dock.status.setText(f"<b style='color:#e5484d'>A análise não rodou</b>: {dados.get('erro') or ''} "
                                   f"({n} erro(s) em Notificações).")
        return None
    nucleo.dock.status.setText(f"{texto.rstrip('…')}: pronto.")
    return dados


def _hora_campo(d):
    h = QComboBox()
    h.addItem("Hora de maior consumo", None)
    for i in range(24):
        h.addItem(f"{i:02d}:00", i)
    d.linha("Instante:", h, "A rede é analisada congelada neste instante: demandas, níveis e bombas desse momento")
    return h


def _alvo_nos(d, nucleo, rotulo="Nós analisados:"):
    alvo = QComboBox()
    sel = ids_selecionados(nucleo, "no_juncao")
    if sel:
        alvo.addItem(f"Os {len(sel)} nós selecionados no mapa", "sel")
    alvo.addItem("Hidrantes (ou os pontos de consumo, se não houver hidrante)", "hid")
    alvo.addItem("Todos os nós", "todos")
    d.linha(rotulo, alvo)
    return alvo, sel


def _nos_de(nucleo, escolha, sel):
    if escolha == "sel":
        return sel
    if escolha == "todos":
        return [str(f["id"]) for f in nucleo.camada("no_juncao").getFeatures()]
    return None


def _espin(minimo, maximo, valor, casas=1, sufixo=""):
    s = QDoubleSpinBox()
    s.setRange(minimo, maximo)
    s.setDecimals(casas)
    s.setValue(valor)
    if sufixo:
        s.setSuffix(" " + sufixo)
    return s


# ================================================================ incêndio
def incendio(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Incêndio (Fire Flow)",
                "Para cada nó: a maior vazão que dá para tirar dele mantendo a pressão residual, como o Fire Flow do "
                "WaterGEMS. Atende = a vazão disponível é maior ou igual à exigida.")
    alvo, sel = _alvo_nos(d, nucleo, "Hidrantes / nós:")
    q = d.linha("Vazão exigida:", _espin(0.5, 1000, 10, 1, "L/s"), "NBR 12218: hidrante de coluna urbano, 10 L/s")
    pr = d.linha("Pressão residual no hidrante:", _espin(0, 100, 10, 1, "mca"))
    zona = QCheckBox("Exigir também uma pressão mínima em todos os outros nós")
    d.lay.addWidget(zona)
    pz = d.linha("Pressão mínima nos outros nós:", _espin(0, 100, 10, 1, "mca"))
    hora = _hora_campo(d)
    d.botoes("Calcular")
    if not d.exec():
        return
    r = rodar(nucleo, "incendio", "Calculando a vazão de incêndio…", nos=_nos_de(nucleo, alvo.currentData(), sel),
              vazao=q.value(), p_residual=pr.value(), p_min_zona=pz.value() if zona.isChecked() else None,
              hora=hora.currentData())
    if not r:
        return
    linhas, cores = [], {}
    for i, x in enumerate(r["linhas"]):
        linhas.append([x["id"], x["q_necessaria"], x["q_disponivel"], "SIM" if x["atende"] else "NÃO", x["p_residual"],
                       x["p_min_zona"], x["no_p_min_zona"] or "", x["limitado_por"]])
        cores[i] = COR["ok"] if x["atende"] else COR["crit"]
    camada_resultado(nucleo, "Incêndio · vazão disponível (L/s)", {x["id"]: x["q_disponivel"] for x in r["linhas"]},
                     "q_disponivel", faixas=[(None, q.value(), "#e5484d", f"< {num(q.value(), 1)} L/s (não atende)"),
                                             (q.value(), 2 * q.value(), "#f59f00", "atende com folga pequena"),
                                             (2 * q.value(), None, "#2fb36f", f"≥ {num(2 * q.value(), 1)} L/s")])
    janela_resultado(nucleo, "Incêndio",
                     f"Instante {r['hora']}: <b>{r['atendem']} de {r['total']}</b> nós atendem {num(q.value(), 1)} L/s "
                     f"com {num(pr.value(), 1)} mca de pressão residual. Clique duplo leva até o nó. A camada "
                     "'Incêndio · vazão disponível' pinta os nós no mapa.",
                     ["Nó", "Vazão exigida (L/s)", "Vazão disponível (L/s)", "Atende", "Pressão residual (mca)",
                      "Pressão mín. outros nós", "Onde", "Limitado por"], linhas, "incendio", cores=cores)


# ================================================================ descarga
def descarga(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Descarga de rede (Flushing)",
                "Abre cada nó sozinho com a vazão escolhida e mostra que tubulações passam da velocidade de arraste "
                "(limpeza), como o Flushing do WaterGEMS. 0,76 m/s (2,5 pés/s) é a referência usual.")
    alvo, sel = _alvo_nos(d, nucleo, "Pontos de descarga:")
    q = d.linha("Vazão da descarga:", _espin(0.5, 1000, 20, 1, "L/s"))
    v = d.linha("Velocidade de limpeza:", _espin(0.1, 5, 0.76, 2, "m/s"))
    hora = _hora_campo(d)
    d.botoes("Calcular")
    if not d.exec():
        return
    r = rodar(nucleo, "descarga", "Simulando as descargas…", nos=_nos_de(nucleo, alvo.currentData(), sel),
              vazao=q.value(), v_alvo=v.value(), hora=hora.currentData())
    if not r:
        return
    melhor = {}
    for e in r["eventos"]:
        for t in e["tubos"]:
            melhor[t["id"]] = max(melhor.get(t["id"], 0), t["v"])
    camada_resultado(nucleo, "Descarga · velocidade máxima atingida (m/s)", melhor, "v", camadas=["trecho"],
                     faixas=[(v.value(), 1.5, "#74c0fc", "limpa"), (1.5, None, "#1c7ed6", "limpa (velocidade alta)")])
    eventos = {e["id"]: e for e in r["eventos"]}

    def mostrar_tubos(no):
        e = eventos.get(no)
        if e:
            selecionar_ids(nucleo, [no] + [t["id"] for t in e["tubos"]])
            nucleo.informar(f"Descarga em {no}: {e['n_tubos']} tubulação(ões) limpas ({num(e['comprimento_m'], 0)} m).")

    linhas = [[e["id"], e["vazao"], e["p_no"], e["n_tubos"], e["comprimento_m"], "sim" if e["convergiu"] else "NÃO"]
              for e in r["eventos"]]
    janela_resultado(nucleo, "Descarga",
                     f"Instante {r['hora']}. Clique duplo num ponto seleciona as tubulações que ele limpa. A camada "
                     f"'Descarga · velocidade máxima' mostra tudo o que alguma descarga limpa (≥ {num(v.value(), 2)} m/s).",
                     ["Ponto", "Vazão (L/s)", "Pressão no ponto (mca)", "Tubulações limpas", "Comprimento limpo (m)",
                      "Calculou"], linhas, "descarga", ao_clicar=mostrar_tubos)


# ================================================================ criticidade
def criticidade(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Criticidade",
                "Tira cada tubulação de operação, uma de cada vez, e mede a água que deixa de chegar aos consumidores "
                "(demanda dependente da pressão), como o Criticality do WaterGEMS. Mostra também os nós que ficam "
                "abaixo da pressão mínima.")
    alvo = QComboBox()
    sel = ids_selecionados(nucleo, "trecho")
    if sel:
        alvo.addItem(f"As {len(sel)} tubulações selecionadas", "sel")
    alvo.addItem("Todas as tubulações", "todas")
    d.linha("Tubulações:", alvo)
    pm = d.linha("Pressão mínima:", _espin(0, 100, 10, 1, "mca"))
    hora = _hora_campo(d)
    d.botoes("Calcular")
    if not d.exec():
        return
    r = rodar(nucleo, "criticidade", "Calculando a criticidade…", trechos=sel if alvo.currentData() == "sel" else None,
              p_min=pm.value(), hora=hora.currentData())
    if not r:
        return
    camada_resultado(nucleo, "Criticidade · água que falta (%)", {x["id"]: x["falta_pct"] for x in r["linhas"]},
                     "falta_pct", camadas=["trecho"],
                     faixas=[(None, 0.5, "#9aa5b1", "< 0,5% (pouco crítica)"), (0.5, 5, "#74c0fc", "0,5 a 5%"),
                             (5, 20, "#f59f00", "5 a 20%"), (20, None, "#e5484d", "> 20% (muito crítica)")])
    linhas = [[x["id"], x["falta_lps"], x["falta_pct"], x["nos_baixa_pressao"], x["nos_sem_agua"],
               ", ".join(x["exemplos"])] for x in r["linhas"]]
    cores = {i: COR["crit"] for i, x in enumerate(r["linhas"]) if (x["falta_pct"] or 0) >= 20}
    janela_resultado(nucleo, "Criticidade",
                     f"Instante {r['hora']}, consumo pedido {num(r['pedido_lps'], 2)} L/s. As mais críticas primeiro. "
                     "A camada 'Criticidade' pinta as tubulações.",
                     ["Tubulação", "Água que falta (L/s)", "Falta (%)", "Nós abaixo da mínima", "Nós sem água",
                      "Exemplos de nós afetados"], linhas, "criticidade", cores=cores)


# ================================================================ zonas de pressão
def zonas_pressao(nucleo):
    if not nucleo.cadastro():
        return
    r = rodar(nucleo, "zonas_pressao", "Identificando as zonas de pressão…")
    if not r:
        return
    cores = cores_categorias(len(r["zonas"]))
    cat = {z["zona"]: (cor, f"Zona {z['zona']} ({z['n_nos']} nós)") for z, cor in zip(r["zonas"], cores)}
    camada_resultado(nucleo, "Zonas de pressão · tubulações", {k: v for k, v in r["trechos"].items() if v},
                     "zona", categorias=cat, camadas=["trecho"])
    camada_resultado(nucleo, "Zonas de pressão · nós", r["nos"], "zona", categorias=cat,
                     camadas=[c for c in PONTOS if _tem(nucleo, c)])
    linhas = [[f"Zona {z['zona']}", z["n_nos"], z["demanda_lps"], z["cota_min"], z["cota_max"], z["p_min"], z["p_max"],
               ", ".join(z["fontes"]), ", ".join(z["entradas"]), ", ".join(z["saidas"])] for z in r["zonas"]]
    zonas = {f"Zona {z['zona']}": z for z in r["zonas"]}
    janela_resultado(nucleo, "Zonas de pressão",
                     f"{len(r['zonas'])} zonas separadas por {len(r['divisas'])} elemento(s) de divisa (bombas, válvulas "
                     "reguladoras e registros fechados). Clique duplo seleciona a zona.",
                     ["Zona", "Nós", "Demanda base (L/s)", "Cota mín (m)", "Cota máx (m)", "Pressão mín (mca)",
                      "Pressão máx (mca)", "Fontes", "Entra por", "Sai por"], linhas, "zonas_pressao",
                     ao_clicar=lambda z: selecionar_ids(nucleo, zonas[z]["elementos"]))


def _tem(nucleo, c):
    try:
        nucleo.camada(c)
        return True
    except LookupError:
        return False


# ================================================================ energia
def energia(nucleo):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Custo de energia",
                "Energia e custo das bombas na simulação de 24 h, com tarifa diferente no horário de ponta, como o "
                "Energy Cost do WaterGEMS.")
    eta = d.linha("Rendimento do conjunto motor-bomba:", _espin(10, 95, 70, 0, "%"))
    fora = d.linha("Tarifa fora de ponta:", _espin(0, 20, 0.55, 3, "R$/kWh"))
    ponta = d.linha("Tarifa na ponta:", _espin(0, 20, 2.10, 3, "R$/kWh"))
    ini = QSpinBox()
    ini.setRange(0, 23)
    ini.setValue(18)
    d.linha("Ponta começa às (h):", ini)
    dur = QSpinBox()
    dur.setRange(0, 12)
    dur.setValue(3)
    d.linha("Duração da ponta (h):", dur)
    dias = QSpinBox()
    dias.setRange(1, 31)
    dias.setValue(30)
    d.linha("Dias no mês:", dias)
    d.botoes("Calcular")
    if not d.exec():
        return
    tarifa = [ponta.value() if (h - ini.value()) % 24 < dur.value() else fora.value() for h in range(24)]
    r = rodar(nucleo, "energia", "Calculando a energia das bombas…", eficiencia=eta.value() / 100, tarifa=tarifa,
              dias_mes=dias.value())
    if not r:
        return
    if not r["bombas"]:
        return nucleo.informar("O cadastro não tem bombas.")
    gw, fig = figura(None, 2.6)
    ax = eixo(fig, titulo="Potência das bombas ao longo do dia", x="hora", y="kW")
    for i, b in enumerate(r["bombas"]):
        ax.plot(r["horas"], b["serie_kw"], label=b["id"], linewidth=1.6)
    for h in range(24):
        if tarifa[h] > min(tarifa):
            ax.axvspan(h, h + 1, color=COR["warn"], alpha=0.08)
    legenda(ax)
    gw.setMinimumHeight(240)
    linhas = [[b["id"], b["horas_ligada"], b["q_media_lps"], b["h_media_m"], b["potencia_max_kw"], b["kwh_dia"],
               b["kwh_por_m3"], b["custo_dia"], b["custo_mes"], b["custo_ponta_pct"]] for b in r["bombas"]]
    janela_resultado(nucleo, "Custo de energia",
                     f"Total: <b>{num(r['total_kwh_dia'], 1)} kWh/dia</b> · <b>R$ {num(r['total_custo_mes'], 2)}</b> por "
                     f"mês ({dias.value()} dias). Faixa amarela no gráfico = horário de ponta. Tirar bombeamento da ponta "
                     "(controle por hora ou mais reservação) reduz o custo.",
                     ["Bomba", "Horas ligada", "Vazão média (L/s)", "Altura média (m)", "Potência máx (kW)", "kWh/dia",
                      "kWh/m³", "R$/dia", "R$/mês", "% do custo na ponta"], linhas, "energia", topo=gw)


# ================================================================ renovação
def renovacao(nucleo):
    if not nucleo.cadastro():
        return
    from .componentes import biblioteca
    bib = biblioteca(nucleo)
    d = Dialogo(nucleo.janela, "Renovação de redes",
                "Nota de 0 a 100 para cada tubulação (mais alta = trocar antes), como o Pipe Renewal Planner do "
                "WaterGEMS: idade frente à vida útil do material, material, desempenho hidráulico (perda de carga e "
                "velocidade) e, se marcado, criticidade. Vida útil e custos vêm de Bibliotecas de engenharia.")
    pesos = {}
    for k, rot, v in (("idade", "Peso da idade", 35), ("material", "Peso do material", 25),
                      ("hidraulica", "Peso do desempenho hidráulico", 25), ("criticidade", "Peso da criticidade", 15)):
        s = QSpinBox()
        s.setRange(0, 100)
        s.setValue(v)
        s.setSuffix(" %")
        pesos[k] = d.linha(rot + ":", s)
    crit = QCheckBox("Calcular a criticidade de cada tubulação (mais demorado)")
    d.lay.addWidget(crit)
    d.botoes("Calcular")
    if not d.exec():
        return
    r = rodar(nucleo, "renovacao", "Calculando as prioridades de renovação…",
              pesos={k: s.value() for k, s in pesos.items()}, com_criticidade=crit.isChecked(),
              custo_m={str(k): v for k, v in bib["custos"].items()}, vida=bib["vida"])
    if not r:
        return
    camada_resultado(nucleo, "Renovação · nota de prioridade", {x["id"]: x["nota"] for x in r["linhas"]}, "nota",
                     camadas=["trecho"], faixas=[(None, 40, "#2fb36f", "baixa (< 40)"), (40, 60, "#f59f00", "média (40 a 60)"),
                                                 (60, None, "#e5484d", "alta (≥ 60)")])
    linhas = [[x["id"], x["nota"], x["prioridade"], x["idade"] if x["idade"] is not None else "", x["material"], x["dn"],
               x["comprimento"], x["perda_max_m_km"], x["v_max"], x["criticidade"], x["custo"], x["custo_acumulado"]]
              for x in r["linhas"]]
    cores = {i: COR["crit"] if x["prioridade"] == "ALTA" else COR["warn"] if x["prioridade"] == "MÉDIA" else COR["text"]
             for i, x in enumerate(r["linhas"])}
    altas = [x for x in r["linhas"] if x["prioridade"] == "ALTA"]
    janela_resultado(nucleo, "Renovação de redes",
                     f"<b>{len(altas)}</b> tubulação(ões) com prioridade alta, {num(sum(x['comprimento'] for x in altas), 0)} m, "
                     f"R$ {num(sum(x['custo'] for x in altas), 0)}. A coluna 'Custo acumulado' ajuda a montar o plano por "
                     "orçamento (troque de cima para baixo até o valor disponível).",
                     ["Tubulação", "Nota", "Prioridade", "Idade (anos)", "Material", "DN", "Comprimento (m)",
                      "Perda máx (m/km)", "Vel. máx (m/s)", "Criticidade", "Custo (R$)", "Custo acumulado (R$)"],
                     linhas, "renovacao", cores=cores)


# ================================================================ dimensionamento
def dimensionar(nucleo):
    if not nucleo.cadastro():
        return
    sel = ids_selecionados(nucleo, "trecho")
    if not sel:
        return nucleo.informar("Selecione no mapa as tubulações candidatas (as que podem mudar de diâmetro).")
    from .componentes import biblioteca
    bib = biblioteca(nucleo)
    d = Dialogo(nucleo.janela, "Dimensionamento de diâmetros",
                f"Escolhe os diâmetros das {len(sel)} tubulações selecionadas com o menor custo que atenda a pressão "
                "mínima nos pontos de consumo e a velocidade máxima, no instante de maior consumo (como uma primeira "
                "rodada do Darwin Designer). Diâmetros e custos vêm de Bibliotecas de engenharia.")
    pm = d.linha("Pressão mínima nos pontos de consumo:", _espin(0, 100, 10, 1, "mca"))
    vm = d.linha("Velocidade máxima nas candidatas:", _espin(0.3, 6, 3.0, 2, "m/s"))
    d.botoes("Dimensionar")
    if not d.exec():
        return
    r = rodar(nucleo, "dimensionar", "Dimensionando…", trechos=sel, p_min=pm.value(), v_max=vm.value(),
              dns=sorted(bib["custos"]), custo_m={str(k): v for k, v in bib["custos"].items()})
    if not r:
        return

    def como_cenario():
        from .cenarios_ui import gravar, listar, _novo_id, atualizar_combo
        from datetime import datetime
        gpkg = nucleo.cadastro()
        todos = listar(gpkg)
        nome = f"Dimensionamento {datetime.now():%d/%m %H:%M}"
        todos.append({"id": _novo_id(nome, {x["id"] for x in todos}), "nome": nome,
                      "descricao": f"pressão mín {pm.value():g} mca, velocidade máx {vm.value():g} m/s",
                      "com_projetados": nucleo.projetados(), "fator_demanda": 1.0,
                      "alteracoes": [{**a, "valor": str(a["valor"])} for a in r["alteracoes"]]})
        gravar(gpkg, todos)
        atualizar_combo(nucleo.janela)
        nucleo.informar(f"Cenário '{nome}' criado: ative-o em Cenário (no alto do mapa) para calcular.")

    def aplicar():
        if QMessageBox.question(nucleo.janela, "Aplicar no cadastro", "Trocar o diâmetro das tubulações no cadastro? "
                                "(fica na edição até Salvar edições; Ctrl+Z desfaz)") != QMessageBox.StandardButton.Yes:
            return
        tr = nucleo.camada("trecho")
        if not tr.isEditable():
            tr.startEditing()
        i = tr.fields().indexOf("diametro_nominal")
        novo = {x["id"]: x["dn_proposto"] for x in r["linhas"]}
        tr.beginEditCommand("Dimensionamento")
        for f in tr.getFeatures():
            if str(f["id"]) in novo:
                tr.changeAttributeValue(f.id(), i, float(novo[str(f["id"])]))
        tr.endEditCommand()
        nucleo.janela.canvas.refresh()

    linhas = [[x["id"], x["dn_atual"], x["dn_proposto"], x["comprimento"], x["custo"]] for x in r["linhas"]]
    ok = "atende" if r["atende"] else "NÃO atende (o limite está em outra parte da rede)"
    janela_resultado(nucleo, "Dimensionamento",
                     f"Instante {r['hora']}: pressão mínima {num(r['p_min_antes'], 1)} → <b>{num(r['p_min_depois'], 1)} mca</b>, "
                     f"velocidade máx {num(r['v_max_antes'], 2)} → <b>{num(r['v_max_depois'], 2)} m/s</b>: {ok}. "
                     f"Custo das candidatas: <b>R$ {num(r['custo_total'], 0)}</b>.",
                     ["Tubulação", "DN atual", "DN proposto", "Comprimento (m)", "Custo (R$)"], linhas, "dimensionamento",
                     extras=[("Salvar como cenário", como_cenario), ("Aplicar no cadastro", aplicar)])


# ================================================================ qualidade da água
def qualidade(nucleo, parametro="AGE"):
    if not nucleo.cadastro():
        return
    d = Dialogo(nucleo.janela, "Qualidade da água",
                "Idade da água (tempo desde a fonte) ou cloro residual com decaimento de 1ª ordem, como o Water Quality "
                "do WaterGEMS. A simulação roda vários dias para estabilizar e mostra o último dia.")
    tipo = QComboBox()
    tipo.addItem("Idade da água (h)", "AGE")
    tipo.addItem("Cloro residual (mg/L)", "CHEMICAL")
    tipo.setCurrentIndex(0 if parametro == "AGE" else 1)
    d.linha("Calcular:", tipo)
    dur = QSpinBox()
    dur.setRange(24, 720)
    dur.setValue(96)
    dur.setSuffix(" h")
    d.linha("Duração da simulação:", dur)
    c0 = d.linha("Cloro na saída da fonte:", _espin(0, 10, 1.5, 2, "mg/L"))
    kb = d.linha("Decaimento no volume (kb):", _espin(-20, 0, -0.5, 2, "1/dia"))
    kw = d.linha("Decaimento na parede (kw):", _espin(-20, 0, 0, 2, "m/dia"))
    d.botoes("Calcular")
    if not d.exec():
        return
    r = rodar(nucleo, "qualidade", "Simulando a qualidade da água…", parametro=tipo.currentData(),
              duracao_h=dur.value(), conc_fonte=c0.value(), kb_dia=kb.value(), kw=kw.value())
    if not r:
        return
    idade = tipo.currentData() == "AGE"
    if idade:
        faixas = [(None, 12, "#2fb36f", "< 12 h"), (12, 24, "#74c0fc", "12 a 24 h"), (24, 48, "#f59f00", "24 a 48 h"),
                  (48, None, "#e5484d", "> 48 h (água velha)")]
        campo, val = "idade_max", {k: v["max"] for k, v in r["nos"].items()}
        nome = "Idade da água máxima (h)"
    else:
        faixas = [(None, 0.2, "#e5484d", "< 0,2 mg/L (abaixo da Portaria GM/MS 888)"), (0.2, 0.5, "#f59f00", "0,2 a 0,5"),
                  (0.5, 2, "#2fb36f", "0,5 a 2"), (2, None, "#1c7ed6", "> 2 mg/L")]
        campo, val = "cloro_min", {k: v["min"] for k, v in r["nos"].items()}
        nome = "Cloro residual mínimo (mg/L)"
    camada_resultado(nucleo, nome, val, campo, faixas=faixas, camadas=[c for c in PONTOS if _tem(nucleo, c)])
    linhas = [[k, v["min"], v["media"], v["max"]] for k, v in sorted(r["nos"].items(), key=lambda x: -(x[1]["max"] or 0))]
    janela_resultado(nucleo, "Qualidade da água",
                     f"{r['parametro']} no último dia de {dur.value()} h simuladas. A camada '{nome}' pinta os nós.",
                     ["Nó", "Mínimo", "Média", "Máximo"], linhas, "qualidade")


# ================================================================ cálculo: tempos, resumo, notificações, alertas
def tempos(nucleo):
    nucleo.mostrar_dock()
    nucleo.dock.abas.setCurrentIndex(nucleo.dock.aba_resultados)
    if not nucleo.res:
        nucleo.informar("Calcule a rede (F5) para usar a linha do tempo.")


def notificacoes(nucleo):
    nucleo.mostrar_dock()
    nucleo.dock.abas.setCurrentIndex(nucleo.dock.aba_problemas)


def resumo(nucleo):
    res = nucleo.res
    if not res:
        return nucleo.aviso("Calcule a rede primeiro (F5).")
    d = res.d
    horas = res.horas
    dt = (horas[1] - horas[0]) * 3600 if len(horas) > 1 else 3600
    consumo = sum(sum(max(x, 0) for x in n["d"]) for nid, n in d["nos"].items() if "__" not in nid) * dt / 1000
    fontes = []
    for lyr_nome in ("captacao",):
        try:
            for f in nucleo.camada(lyr_nome).getFeatures():
                n = d["nos"].get(str(f["id"]))
                if n:
                    fontes.append((str(f["id"]), -sum(n["d"]) * dt / 1000))
        except LookupError:
            pass
    reserv = []
    try:
        for f in nucleo.camada("reservatorio").getFeatures():
            n = d["nos"].get(str(f["id"]))
            if n and f["diametro"]:
                area = 3.14159 * float(f["diametro"]) ** 2 / 4
                reserv.append((str(f["id"]), n["p"][0], n["p"][-1], min(n["p"]), max(n["p"]),
                               (n["p"][-1] - n["p"][0]) * area))
    except LookupError:
        pass
    pres = [(nid, min(n["p"]), max(n["p"])) for nid, n in d["nos"].items() if "__" not in nid and nid in res.rid_consumo]
    pmin = min(pres, key=lambda x: x[1]) if pres else None
    pmax = max(pres, key=lambda x: x[2]) if pres else None
    bombas = []
    try:
        for f in nucleo.camada("bomba").getFeatures():
            l = d["links"].get(str(f["id"]))
            if l:
                bombas.append((str(f["id"]), sum(1 for s in l["s"] if s) * dt / 3600,
                               sum(abs(q) for q, s in zip(l["q"], l["s"]) if s) * dt / 1000))
    except LookupError:
        pass
    from gwater.resultados import _hora
    html = [f"<h3>Resumo do cálculo{' · cenário ' + nucleo.cenario['nome'] if nucleo.cenario else ''}</h3>",
            f"<p>Simulação de {num(horas[-1], 0)} h, passo de {num(dt / 60, 0)} min, {len(d['nos'])} nós e "
            f"{len(d['links'])} ligações no modelo, EPANET {num(d.get('tempo_calculo_s', 0) * 1000, 0)} ms.</p>",
            "<h4>Balanço de volumes no período</h4><table cellpadding=4>",
            f"<tr><td>Consumo entregue</td><td align=right><b>{num(consumo, 1)} m³</b></td></tr>"]
    for fid, v in fontes:
        html.append(f"<tr><td>Fornecido pela captação {fid}</td><td align=right>{num(v, 1)} m³</td></tr>")
    for rid, n0, n1, mn, mx, dv in reserv:
        html.append(f"<tr><td>Reservatório {rid}: nível {num(n0, 2)} → {num(n1, 2)} m (faixa {num(mn, 2)} a {num(mx, 2)} m)"
                    f"</td><td align=right>Δ volume {num(dv, 1)} m³</td></tr>")
    html.append("</table><h4>Pressões nos pontos de consumo</h4>")
    if pmin:
        html.append(f"<p>Mínima <b>{num(pmin[1], 1)} mca</b> no nó {pmin[0]} · máxima <b>{num(pmax[2], 1)} mca</b> no nó "
                    f"{pmax[0]}. {sum(1 for p in pres if p[1] < 10)} nó(s) abaixo de 10 mca e "
                    f"{sum(1 for p in pres if p[2] > 50)} acima de 50 mca em algum momento.</p>")
    if bombas:
        html.append("<h4>Bombas</h4><table cellpadding=4>")
        for bid, hl, vol in bombas:
            html.append(f"<tr><td>{bid}</td><td>{num(hl, 1)} h ligada</td><td>{num(vol, 0)} m³ bombeados</td></tr>")
        html.append("</table>")
    html.append(f"<p>Pior momento (menor pressão): {_hora(horas[res.pior_momento()])}.</p>")
    from qgis.PyQt.QtWidgets import QTextBrowser
    dlg = Dialogo(nucleo.janela, "Resumo do cálculo", largura=640)
    t = QTextBrowser()
    from gwater.estilo import css_html
    t.setHtml(css_html() + "".join(html))
    t.setMinimumHeight(420)
    dlg.lay.addWidget(t)
    dlg.botoes(None, "Fechar")
    dlg.exec()


def alertas(nucleo):
    res = nucleo.res
    if not res:
        return nucleo.aviso("Calcule a rede primeiro (F5).")
    from gwater.resultados import _hora
    d, horas = res.d, res.horas
    linhas, cores = [], {}

    def add(eid, tipo, valor, quando, cor):
        cores[len(linhas)] = cor
        linhas.append([eid, tipo, valor, quando])

    for nid in res.rid_consumo:
        p = d["nos"][nid]["p"]
        if min(p) < 0:
            add(nid, "Pressão negativa", round(min(p), 1), _hora(horas[p.index(min(p))]), COR["crit"])
        elif min(p) < 10:
            add(nid, "Pressão abaixo de 10 mca (NBR 12218)", round(min(p), 1), _hora(horas[p.index(min(p))]), COR["crit"])
        if max(p) > 50:
            add(nid, "Pressão acima de 50 mca (NBR 12218)", round(max(p), 1), _hora(horas[p.index(max(p))]), COR["warn"])
    for lid in res.rid_tr:
        v = [abs(x) for x in d["links"][lid]["v"]]
        hl = [abs(x) for x in d["links"][lid]["hl"]]
        if max(v) > 2.5:
            add(lid, "Velocidade acima de 2,5 m/s", round(max(v), 2), _hora(horas[v.index(max(v))]), COR["warn"])
        if max(hl) > 10:
            add(lid, "Perda de carga acima de 10 m/km", round(max(hl), 1), _hora(horas[hl.index(max(hl))]), COR["warn"])
    try:
        for f in nucleo.camada("reservatorio").getFeatures():
            n = d["nos"].get(str(f["id"]))
            if not n:
                continue
            nmin, nmax = float(f["nivel_min"] or 0), float(f["nivel_max"] or 0)
            if min(n["p"]) <= nmin + 0.05:
                add(str(f["id"]), "Reservatório vazio (atingiu o nível mínimo)", round(min(n["p"]), 2),
                    _hora(horas[n["p"].index(min(n["p"]))]), COR["crit"])
            if nmax and max(n["p"]) >= nmax - 0.05:
                add(str(f["id"]), "Reservatório cheio (atingiu o nível máximo)", round(max(n["p"]), 2),
                    _hora(horas[n["p"].index(max(n["p"]))]), COR["warn"])
    except LookupError:
        pass
    try:
        for f in nucleo.camada("bomba").getFeatures():
            l = d["links"].get(str(f["id"]))
            if l and not any(l["s"]):
                add(str(f["id"]), "Bomba desligada o dia todo", 0, "—", COR["warn"])
    except LookupError:
        pass
    if not linhas:
        return nucleo.informar("Nenhum alerta: pressões, velocidades e reservatórios dentro dos limites.")
    janela_resultado(nucleo, "Alertas", f"<b>{len(linhas)}</b> alerta(s) na simulação. Clique duplo leva até o elemento.",
                     ["Elemento", "Alerta", "Valor", "Quando"], linhas, "alertas", cores=cores)


ACOES = {"incendio": incendio, "descarga": descarga, "criticidade": criticidade, "zonas_pressao": zonas_pressao,
         "energia": energia, "renovacao": renovacao, "dimensionar": dimensionar, "darwin": dimensionar,
         "idade_agua": lambda n: qualidade(n, "AGE"), "cloro": lambda n: qualidade(n, "CHEMICAL"),
         "qualidade_opcoes": lambda n: qualidade(n, "AGE"), "tempos": tempos, "resumo": resumo,
         "notificacoes": notificacoes, "alertas": alertas}
