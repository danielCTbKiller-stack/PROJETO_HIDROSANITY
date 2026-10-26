"""Assistente de IA dentro do GWATER: Claude, GPT ou Gemini.

Dois modos:
  Conta (site oficial)  o site do fornecedor (claude.ai, chatgpt.com, gemini.google.com) abre num navegador embutido,
                        com login próprio que fica guardado: usa a assinatura (Pro, Plus, Advanced) da pessoa, com os
                        modelos do plano. Os fornecedores não deixam outro programa usar a assinatura pela API, então
                        este é o caminho para o plano pago.
  API (chave)           chat do próprio GWATER pela API do fornecedor, com a escolha do modelo (lista que vem do próprio
                        fornecedor) e, se marcado, os dados do cadastro e do último cálculo como contexto. Precisa de
                        uma chave de API (cobrança por uso, separada da assinatura), guardada criptografada no usuário
                        do Windows (DPAPI).
"""
import base64
import ctypes
import json
import os
import re
from html import escape

from qgis.PyQt.QtCore import QByteArray, QSettings, Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                                 QPlainTextEdit, QPushButton, QSplitter, QStackedWidget, QTextBrowser, QVBoxLayout,
                                 QWidget)

from gwater.estilo import COR

CHAVE = ("GWATER", "GWATER")
FORNECEDORES = {
    "claude": {"nome": "Claude (Anthropic)", "site": "https://claude.ai/new",
               "modelos": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
               "pagina_chave": "https://console.anthropic.com/settings/keys"},
    "gpt": {"nome": "GPT (OpenAI)", "site": "https://chatgpt.com/",
            "modelos": [], "pagina_chave": "https://platform.openai.com/api-keys"},
    "gemini": {"nome": "Gemini (Google)", "site": "https://gemini.google.com/app",
               "modelos": [], "pagina_chave": "https://aistudio.google.com/app/apikey"},
}
SISTEMA = ("Você é o assistente do GWATER, um programa de cadastro e modelagem hidráulica de redes de água (EPANET 2.2, "
           "no estilo do WaterGEMS). Responda em português do Brasil, de forma direta e técnica, como um engenheiro "
           "de saneamento experiente. Use as normas brasileiras quando couber (NBR 12218, 12211, 12217, Portaria GM/MS "
           "888). Quando receber dados do cadastro ou do cálculo, baseie a resposta neles e diga quando faltar dado.")


# ---------------------------------------------------------------- chave de API guardada com o DPAPI do Windows
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(dados, proteger):
    try:
        crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    except AttributeError:  # fora do Windows: base64 simples (não criptografa)
        return base64.b64encode(dados) if proteger else base64.b64decode(dados)
    buf = ctypes.create_string_buffer(dados, len(dados))
    entrada, saida = _Blob(len(dados), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    f = crypt32.CryptProtectData if proteger else crypt32.CryptUnprotectData
    if not f(ctypes.byref(entrada), None, None, None, None, 0, ctypes.byref(saida)):
        raise OSError("o Windows não conseguiu proteger/ler a chave")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        kernel32.LocalFree(saida.pbData)


def gravar_chave(fornecedor, chave):
    s = QSettings(*CHAVE)
    if not chave:
        s.remove(f"ia/chave_{fornecedor}")
        return
    s.setValue(f"ia/chave_{fornecedor}", base64.b64encode(_dpapi(chave.strip().encode(), True)).decode())


def ler_chave(fornecedor):
    v = QSettings(*CHAVE).value(f"ia/chave_{fornecedor}", "")
    if not v:
        return ""
    try:
        return _dpapi(base64.b64decode(v), False).decode()
    except (OSError, ValueError):
        return ""


# ---------------------------------------------------------------- pedidos às APIs
def pedido(fornecedor, chave, modelo, mensagens, sistema):
    """(url, cabeçalhos, corpo) da chamada de chat de cada fornecedor. mensagens: [{"papel", "texto"}]."""
    if fornecedor == "claude":
        return ("https://api.anthropic.com/v1/messages",
                {"x-api-key": chave, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                {"model": modelo, "max_tokens": 4096, "system": sistema,
                 "messages": [{"role": "assistant" if m["papel"] == "ia" else "user", "content": m["texto"]}
                              for m in mensagens]})
    if fornecedor == "gpt":
        return ("https://api.openai.com/v1/chat/completions",
                {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
                {"model": modelo, "messages": [{"role": "system", "content": sistema}] +
                 [{"role": "assistant" if m["papel"] == "ia" else "user", "content": m["texto"]} for m in mensagens]})
    return (f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
            {"x-goog-api-key": chave, "Content-Type": "application/json"},
            {"systemInstruction": {"parts": [{"text": sistema}]},
             "contents": [{"role": "model" if m["papel"] == "ia" else "user", "parts": [{"text": m["texto"]}]}
                          for m in mensagens]})


def texto_da_resposta(fornecedor, dados):
    if "error" in dados:
        e = dados["error"]
        raise ValueError(e.get("message") if isinstance(e, dict) else str(e))
    if fornecedor == "claude":
        return "".join(b.get("text", "") for b in dados.get("content", []) if b.get("type") == "text")
    if fornecedor == "gpt":
        return dados["choices"][0]["message"]["content"] or ""
    cand = (dados.get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))


def pedido_modelos(fornecedor, chave):
    if fornecedor == "claude":
        return ("https://api.anthropic.com/v1/models?limit=100",
                {"x-api-key": chave, "anthropic-version": "2023-06-01"})
    if fornecedor == "gpt":
        return "https://api.openai.com/v1/models", {"Authorization": f"Bearer {chave}"}
    return "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", {"x-goog-api-key": chave}


def modelos_da_resposta(fornecedor, dados):
    if fornecedor == "gemini":
        return sorted(m["name"].split("/", 1)[-1] for m in dados.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))
    ids = [m["id"] for m in dados.get("data", [])]
    if fornecedor == "gpt":  # só os de conversa (tira embeddings, áudio, imagem, moderação…)
        ids = [i for i in ids if re.match(r"^(gpt|o\d|chatgpt)", i)
               and not re.search(r"(audio|realtime|tts|transcribe|image|embedding|search|moderation)", i)]
    return sorted(set(ids), reverse=True)


# ---------------------------------------------------------------- contexto do cadastro
def contexto(nucleo):
    """Resumo do cadastro aberto e do último cálculo, em texto, para a IA responder sobre a rede."""
    linhas = []
    gpkg = nucleo.cadastro()
    if not gpkg:
        return "Nenhum cadastro aberto."
    linhas.append(f"Cadastro: {os.path.basename(gpkg)}"
                  + (f" · cenário ativo: {nucleo.cenario['nome']}" if nucleo.cenario else " · rede atual"))
    for c in ("trecho", "no_juncao", "reservatorio", "captacao", "bomba", "valvula"):
        try:
            lyr = nucleo.camada(c)
        except LookupError:
            continue
        linhas.append(f"{lyr.name()}: {lyr.featureCount()} elemento(s)")
    try:
        tr = nucleo.camada("trecho")
        comp, por_mat, por_dn = 0.0, {}, {}
        for f in tr.getFeatures():
            L = float(f["comprimento"] or 0) if str(f["comprimento"]) != "NULL" else f.geometry().length()
            comp += L
            por_mat[str(f["material"])] = por_mat.get(str(f["material"]), 0) + L
            por_dn[str(f["diametro_nominal"])] = por_dn.get(str(f["diametro_nominal"]), 0) + L
        linhas.append(f"Comprimento total de rede: {comp / 1000:.2f} km")
        linhas.append("Por material (m): " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(por_mat.items(),
                                                                                       key=lambda x: -x[1])[:8]))
        linhas.append("Por DN (m): " + ", ".join(f"DN{k} {v:.0f}" for k, v in sorted(por_dn.items(),
                                                                                  key=lambda x: -x[1])[:10]))
        nos = nucleo.camada("no_juncao")
        dem = sum(float(f["demanda_base"] or 0) for f in nos.getFeatures() if str(f["demanda_base"]) != "NULL")
        linhas.append(f"Demanda base total: {dem:.3f} L/s")
    except LookupError:
        pass
    try:
        from .componentes import limites
        lim = limites(nucleo)
        linhas.append(f"Limites (Opções): pressão {lim['limite_pressao_min']:g} a {lim['limite_pressao_max']:g} mca, "
                      f"velocidade até {lim['limite_velocidade']:g} m/s")
    except Exception:
        pass
    res = nucleo.res
    if res:
        d = res.d
        pres = [(nid, min(d["nos"][nid]["p"]), max(d["nos"][nid]["p"])) for nid in res.rid_consumo]
        if pres:
            pmin, pmax = min(pres, key=lambda x: x[1]), max(pres, key=lambda x: x[2])
            linhas.append(f"Último cálculo (24 h): pressão mínima {pmin[1]:.1f} mca no nó {pmin[0]}, máxima "
                          f"{pmax[2]:.1f} mca no nó {pmax[0]}")
            baixos = sorted(pres, key=lambda x: x[1])[:10]
            linhas.append("Nós com menor pressão: " + ", ".join(f"{n} {p:.1f}" for n, p, _ in baixos))
        vel = sorted(((t, max(abs(x) for x in d["links"][t]["v"])) for t in res.rid_tr), key=lambda x: -x[1])[:10]
        if vel:
            linhas.append("Maiores velocidades (m/s): " + ", ".join(f"{t} {v:.2f}" for t, v in vel))
        try:
            k = nucleo.janela.passo()
            linhas.append("Resumo na hora atual: " + re.sub(r"<[^>]+>", " ", res.resumo(k))[:1500])
        except Exception:
            pass
    else:
        linhas.append("A rede ainda não foi calculada nesta sessão.")
    sel = []
    for lyr, fids in nucleo.janela.selecionados()[:3]:
        for f in lyr.getFeatures(fids[:5]):
            attrs = {c.name(): f[c.name()] for c in f.fields() if c.name() != "fid" and str(f[c.name()]) != "NULL"}
            sel.append(f"{lyr.name()} {attrs}")
    if sel:
        linhas.append("Elementos selecionados no mapa: " + " | ".join(sel))
    return "\n".join(linhas)


# ---------------------------------------------------------------- tela
class Assistente(QWidget):
    def __init__(self, nucleo):
        super().__init__()
        self.nucleo = nucleo
        self.historico = []  # [{"papel": "voce"|"ia", "texto"}]
        self.nam = None
        self.webs = {}
        s = QSettings(*CHAVE)
        v = QVBoxLayout(self)
        topo = QHBoxLayout()
        self.forn = QComboBox()
        for k, f in FORNECEDORES.items():
            self.forn.addItem(f["nome"], k)
        self.forn.setCurrentIndex(max(0, self.forn.findData(s.value("ia/fornecedor", "claude"))))
        self.modo = QComboBox()
        self.modo.addItem("Conta (site oficial, assinatura Pro)", "site")
        self.modo.addItem("API (chave, escolha do modelo)", "api")
        self.modo.setCurrentIndex(max(0, self.modo.findData(s.value("ia/modo", "site"))))
        self.modelo = QComboBox()
        self.modelo.setEditable(True)
        self.modelo.setMinimumWidth(220)
        self.modelo.setToolTip("Modelo que responde (lista do próprio fornecedor; dá para digitar outro)")
        self.b_modelos = QPushButton("Atualizar modelos")
        self.b_chave = QPushButton("Chave de API…")
        self.b_externo = QPushButton("Abrir no navegador")
        self.b_externo.setToolTip("Se o login não funcionar aqui dentro (o Google às vezes bloqueia navegadores "
                                  "embutidos), use o seu navegador")
        for w in (QLabel("IA:"), self.forn, QLabel("Modo:"), self.modo, QLabel("Modelo:"), self.modelo,
                  self.b_modelos, self.b_chave, self.b_externo):
            topo.addWidget(w)
        topo.addStretch(1)
        v.addLayout(topo)
        self.pilha = QStackedWidget()
        v.addWidget(self.pilha, 1)
        # ---- modo API: o chat do GWATER
        chat = QWidget()
        vc = QVBoxLayout(chat)
        vc.setContentsMargins(0, 0, 0, 0)
        self.conversa = QTextBrowser()
        self.conversa.setOpenExternalLinks(True)
        vc.addWidget(self.conversa, 1)
        self.ctx = QCheckBox("Enviar os dados do cadastro e do último cálculo junto com a pergunta")
        self.ctx.setChecked(str(s.value("ia/contexto", "true")).lower() in ("true", "1"))
        vc.addWidget(self.ctx)
        h = QHBoxLayout()
        self.entrada = QPlainTextEdit()
        self.entrada.setPlaceholderText("Pergunte sobre a rede, o cálculo, normas… (Ctrl+Enter envia)")
        self.entrada.setMaximumHeight(90)
        self.b_enviar = QPushButton("Enviar")
        self.b_enviar.setStyleSheet(f"font-weight:600; background:{COR['btn_on']}")
        b_limpar = QPushButton("Nova conversa")
        h.addWidget(self.entrada, 1)
        vb = QVBoxLayout()
        vb.addWidget(self.b_enviar)
        vb.addWidget(b_limpar)
        h.addLayout(vb)
        vc.addLayout(h)
        self.pilha.addWidget(chat)
        self.site = QStackedWidget()  # um navegador por fornecedor (cada um com o seu login)
        self.pilha.addWidget(self.site)
        self.forn.currentIndexChanged.connect(lambda _: self._trocar())
        self.modo.currentIndexChanged.connect(lambda _: self._trocar())
        self.modelo.currentTextChanged.connect(lambda t: QSettings(*CHAVE).setValue(f"ia/modelo_{self.f()}", t))
        self.ctx.toggled.connect(lambda v_: QSettings(*CHAVE).setValue("ia/contexto", v_))
        self.b_modelos.clicked.connect(self.atualizar_modelos)
        self.b_chave.clicked.connect(self.pedir_chave)
        self.b_externo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(FORNECEDORES[self.f()]["site"])))
        self.b_enviar.clicked.connect(self.enviar)
        b_limpar.clicked.connect(self.limpar)
        self.entrada.keyPressEvent = self._tecla
        self._trocar()
        self._mostrar()

    def f(self):
        return self.forn.currentData()

    # ------------------------------------------------ troca de fornecedor e modo
    def _trocar(self):
        s = QSettings(*CHAVE)
        s.setValue("ia/fornecedor", self.f())
        s.setValue("ia/modo", self.modo.currentData())
        api = self.modo.currentData() == "api"
        for w in (self.modelo, self.b_modelos, self.b_chave):
            w.setVisible(api)
        self.b_externo.setVisible(not api)
        if api:
            self.pilha.setCurrentIndex(0)
            salvos = s.value(f"ia/modelos_{self.f()}", "") or ""
            lista = [m for m in salvos.split("|") if m] or FORNECEDORES[self.f()]["modelos"]
            self.modelo.blockSignals(True)
            self.modelo.clear()
            self.modelo.addItems(lista)
            self.modelo.setCurrentText(s.value(f"ia/modelo_{self.f()}", lista[0] if lista else ""))
            self.modelo.blockSignals(False)
            if not ler_chave(self.f()):
                self._linha("sistema", f"Para usar o {FORNECEDORES[self.f()]['nome']} pela API, clique em "
                            f"<b>Chave de API…</b> (crie a chave em {FORNECEDORES[self.f()]['pagina_chave']}). "
                            "A cobrança é por uso, separada da assinatura. Para usar a assinatura Pro, troque o modo "
                            "para <b>Conta (site oficial)</b>.")
        else:
            self.pilha.setCurrentIndex(1)
            self._abrir_site()

    def _abrir_site(self):
        k = self.f()
        if k not in self.webs and (os.environ.get("GWATER_TESTE") or os.environ.get("QT_QPA_PLATFORM") == "offscreen"):
            self.webs[k] = QLabel(f"(teste: aqui abre {FORNECEDORES[k]['site']})")  # o Chromium não sobe sem tela
            self.site.addWidget(self.webs[k])
        if k not in self.webs:
            try:
                from qgis.PyQt.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
                from qgis.PyQt.QtWebEngineWidgets import QWebEngineView
            except ImportError:
                lb = QLabel("O navegador embutido não está disponível nesta instalação. Use <b>Abrir no navegador</b>.")
                self.webs[k] = lb
                self.site.addWidget(lb)
                self.site.setCurrentWidget(lb)
                return
            pasta = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "GWATER", "ia", k)
            os.makedirs(pasta, exist_ok=True)
            perfil = QWebEngineProfile(f"gwater_ia_{k}", self)  # login guardado entre as sessões
            perfil.setPersistentStoragePath(pasta)
            perfil.setCachePath(os.path.join(pasta, "cache"))
            try:
                perfil.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
            except AttributeError:
                pass
            # agente de navegador comum: alguns logins recusam navegadores que se identificam como embutidos
            perfil.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/124.0.0.0 Safari/537.36")
            view = QWebEngineView()
            pagina = QWebEnginePage(perfil, view)
            view.setPage(pagina)
            view.load(QUrl(FORNECEDORES[k]["site"]))
            self.webs[k] = view
            self.site.addWidget(view)
        self.site.setCurrentWidget(self.webs[k])

    # ------------------------------------------------ chave e modelos
    def pedir_chave(self):
        atual = ler_chave(self.f())
        txt, ok = QInputDialog.getText(self, "Chave de API",
                                       f"Chave da API do {FORNECEDORES[self.f()]['nome']} (fica criptografada no seu "
                                       f"usuário do Windows; vazio apaga).\nCrie em: "
                                       f"{FORNECEDORES[self.f()]['pagina_chave']}",
                                       QLineEdit.EchoMode.Password, "•" * 8 if atual else "")
        if not ok or txt == "•" * 8:
            return
        gravar_chave(self.f(), txt.strip())
        self._linha("sistema", "Chave gravada." if txt.strip() else "Chave apagada.")
        if txt.strip():
            self.atualizar_modelos()

    def _rede(self, url, cab, corpo, ao_terminar):
        from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
        if self.nam is None:
            self.nam = QNetworkAccessManager(self)
        req = QNetworkRequest(QUrl(url))
        for k, v_ in cab.items():
            req.setRawHeader(k.encode(), v_.encode())
        req.setTransferTimeout(180_000)
        rep = self.nam.post(req, QByteArray(json.dumps(corpo).encode())) if corpo is not None else self.nam.get(req)

        def fim():
            bruto = bytes(rep.readAll()).decode("utf-8", "replace")
            erro = rep.error() != QNetworkReply.NetworkError.NoError
            rep.deleteLater()
            try:
                dados = json.loads(bruto) if bruto else {}
            except ValueError:
                dados = {"error": {"message": bruto[:300] or rep.errorString()}}
            if erro and "error" not in dados:
                dados = {"error": {"message": rep.errorString()}}
            ao_terminar(dados)
        rep.finished.connect(fim)

    def atualizar_modelos(self):
        chave = ler_chave(self.f())
        if not chave:
            return self.pedir_chave()
        k = self.f()
        url, cab = pedido_modelos(k, chave)
        self.b_modelos.setEnabled(False)

        def pronto(dados):
            self.b_modelos.setEnabled(True)
            if "error" in dados:
                e = dados["error"]
                return self._linha("erro", f"Não consegui ler os modelos: {escape(str(e.get('message') if isinstance(e, dict) else e))}")
            lista = modelos_da_resposta(k, dados)
            if not lista:
                return self._linha("erro", "O fornecedor não devolveu nenhum modelo de conversa.")
            QSettings(*CHAVE).setValue(f"ia/modelos_{k}", "|".join(lista))
            if k == self.f():
                atual = self.modelo.currentText()
                self.modelo.blockSignals(True)
                self.modelo.clear()
                self.modelo.addItems(lista)
                self.modelo.setCurrentText(atual if atual in lista else lista[0])
                self.modelo.blockSignals(False)
                QSettings(*CHAVE).setValue(f"ia/modelo_{k}", self.modelo.currentText())
            self._linha("sistema", f"{len(lista)} modelo(s) disponíveis no {FORNECEDORES[k]['nome']}.")
        self._rede(url, cab, None, pronto)

    # ------------------------------------------------ conversa
    def _tecla(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.enviar()
        else:
            QPlainTextEdit.keyPressEvent(self.entrada, e)

    def _linha(self, papel, html):
        self.historico_tela = getattr(self, "historico_tela", [])
        self.historico_tela.append((papel, html))
        self._mostrar()

    def _mostrar(self):
        cores = {"voce": COR["cyan"], "ia": COR["ok"], "sistema": COR["muted"], "erro": COR["crit"]}
        nomes = {"voce": "Você", "ia": FORNECEDORES[self.f()]["nome"].split(" (")[0], "sistema": "GWATER",
                 "erro": "Erro"}
        partes = []
        for papel, html in getattr(self, "historico_tela", []):
            partes.append(f"<p><b style='color:{cores[papel]}'>{nomes[papel]}</b><br>{html}</p>")
        self.conversa.setHtml(f"<div style='font-size:10pt'>{''.join(partes)}</div>")
        self.conversa.verticalScrollBar().setValue(self.conversa.verticalScrollBar().maximum())

    def limpar(self):
        self.historico, self.historico_tela = [], []
        self._mostrar()

    def enviar(self):
        texto = self.entrada.toPlainText().strip()
        if not texto:
            return
        chave = ler_chave(self.f())
        if not chave:
            return self.pedir_chave()
        modelo = self.modelo.currentText().strip()
        if not modelo:
            return self._linha("erro", "Escolha o modelo (Atualizar modelos traz a lista do fornecedor).")
        self.entrada.clear()
        self._linha("voce", escape(texto).replace("\n", "<br>"))
        self.historico.append({"papel": "voce", "texto": texto})
        sistema = SISTEMA
        if self.ctx.isChecked():
            sistema += "\n\nDados atuais do GWATER:\n" + contexto(self.nucleo)
        k = self.f()
        url, cab, corpo = pedido(k, chave, modelo, self.historico, sistema)
        self.b_enviar.setEnabled(False)
        self.b_enviar.setText("Pensando…")

        def pronto(dados):
            self.b_enviar.setEnabled(True)
            self.b_enviar.setText("Enviar")
            try:
                resposta = texto_da_resposta(k, dados)
            except (ValueError, KeyError, IndexError) as e:
                self.historico.pop()
                return self._linha("erro", escape(str(e)))
            self.historico.append({"papel": "ia", "texto": resposta})
            self._linha("ia", markdown_html(resposta))
        self._rede(url, cab, corpo, pronto)


def markdown_html(txt):
    """Markdown simples da resposta → HTML (títulos, negrito, código, listas)."""
    try:
        from qgis.PyQt.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setMarkdown(txt)
        corpo = doc.toHtml()
        m = re.search(r"<body[^>]*>(.*)</body>", corpo, re.S)
        return m.group(1) if m else corpo
    except Exception:
        return escape(txt).replace("\n", "<br>")


def assistente(nucleo):
    janela = nucleo.janela
    w = getattr(janela, "_assistente", None)
    try:
        if w is not None and janela.centro.indexOf(w) >= 0:
            janela.centro.setCurrentWidget(w)
            return w
    except RuntimeError:
        pass
    w = Assistente(nucleo)
    janela._assistente = w
    janela.abrir_aba(w, "Assistente de IA", "ajuda")
    return w


ACOES = {"assistente": assistente}
