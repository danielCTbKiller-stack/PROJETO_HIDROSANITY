"""Guia do GWATER.exe: todos os botões da faixa (lidos do catálogo), atalhos e o passo a passo."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from gwater.estilo import css_html

from . import catalogo

PASSO_A_PASSO = [
    ("Abrir ou criar o cadastro", "Arquivo › Novo cadastro (rede vazia), Novo de shapefile ou Abrir. O exemplo está na "
                                  "tela Início."),
    ("Desenhar", "Aba Desenho: Captação ou Reservatório, depois Tubulação (clique os vértices, clique direito termina). "
                 "As pontas viram nós sozinhas; bombas e válvulas sobre uma tubulação a dividem. Protótipos define os "
                 "valores que cada elemento já recebe."),
    ("Preparar", "Ferramentas › TRex (cotas do terreno), Componentes › Padrões, Curvas de bomba, Controles, Central de "
                 "demanda (ou LoadBuilder). Salvar edições (Ctrl+S) grava no cadastro."),
    ("Calcular", "Início › Calcular (F5). O mapa se colore; a linha do tempo fica no alto do mapa e em Tempos. "
                 "Propriedades mostra os resultados do elemento selecionado; Alertas e Resumo resumem o cálculo."),
    ("Analisar", "Aba Análise: Incêndio, Descarga, Criticidade, Zonas de pressão, Energia, Renovação, Dimensionamento, "
                 "Qualidade da água; Gráficos, Perfis, Contornos, Tabelas e Consultas."),
    ("Comparar alternativas", "Cenários: crie um cenário, mude o que quiser em Alternativas, ative e calcule. Revisão › "
                              "Comparação de cenários mostra a diferença."),
    ("Operar", "Aba Centro de Operações: sinótico, dados recebidos, mapa web, calibração e ao vivo, dentro do programa."),
]
ATALHOS = [("Ctrl+N / Ctrl+O", "novo / abrir cadastro"), ("Ctrl+S", "salvar edições"), ("Ctrl+Z / Ctrl+Y", "desfazer / refazer"),
           ("F5", "calcular"), ("F6", "validar"), ("Esc", "parar a ferramenta / limpar a seleção"),
           ("Del", "excluir os selecionados"), ("Ctrl+F", "localizar elemento"), ("Ctrl+T", "tabelas"),
           ("Ctrl+G", "gráficos"), ("Ctrl+Shift+F", "zoom total"), ("F1", "este guia"),
           ("Botão do meio do mouse", "arrasta o mapa"), ("Rodinha do mouse", "aproxima e afasta")]


def html_guia():
    h = ["<h2>GWATER · guia do programa</h2>", "<h3>Passo a passo</h3><ol>"]
    h += [f"<li><b>{t}</b>: {d}</li>" for t, d in PASSO_A_PASSO]
    h.append("</ol><h3>Atalhos</h3><table>")
    h += [f"<tr><td><b>{k}</b></td><td>{d}</td></tr>" for k, d in ATALHOS]
    h.append("</table>")
    for _, aba, grupos in catalogo.FAIXA:
        h.append(f"<h3>Aba {aba}</h3>")
        for grupo, botoes in grupos:
            h.append(f"<p><i>{grupo}</i></p><table>")
            for b in botoes:
                h.append(f"<tr><td width='170'><b>{b[1]}</b></td><td>{b[4]}</td></tr>")
                for s in (b[5] if len(b) > 5 else []):
                    h.append(f"<tr><td>&nbsp;&nbsp;› {s[1]}</td><td>{s[3]}</td></tr>")
            h.append("</table>")
    return "".join(h)


def guia(nucleo):
    j = QDialog(nucleo.janela)
    j.setWindowTitle("GWATER · Guia")
    j.resize(820, 720)
    v = QVBoxLayout(j)
    t = QTextBrowser()
    t.setHtml(css_html() + html_guia())
    v.addWidget(t)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    bb.button(QDialogButtonBox.StandardButton.Close).setText("Fechar")
    bb.rejected.connect(j.reject)
    v.addWidget(bb)
    j.setWindowModality(Qt.WindowModality.NonModal)
    j.show()
    nucleo.janelas.append(j)


ACOES = {"guia": guia}
