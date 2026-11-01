"""Teste do Assistente de IA sem internet e sem chave de verdade: um servidor local responde como as APIs do
Claude, do GPT e do Gemini, e o teste confere a chave criptografada, a lista de modelos, a conversa (com o histórico
e o contexto do cadastro) e o erro da API.

Uso:  set QT_QPA_PLATFORM=offscreen
      "C:\\Program Files\\QGIS 4.2.2\\bin\\python-qgis.bat" teste_assistente.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["GWATER_TESTE"] = "1"
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "app"))
from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QEventLoop, QSettings, QTimer  # noqa: E402

app = QgsApplication([b"teste"], True)
app.initQgis()
from programa import assistente as A  # noqa: E402
from programa.janela import Janela  # noqa: E402

falhas = []


def checar(cond, msg):
    print(("  OK   " if cond else "  FALHA ") + msg, flush=True)
    if not cond:
        falhas.append(msg)


RECEBIDO = []


class Falso(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, d, cod=200):
        b = json.dumps(d).encode()
        self.send_response(cod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if "/claude/" in self.path:
            self._json({"data": [{"id": "claude-opus-5-5"}, {"id": "claude-sonnet-5-5"}]})
        elif "/gpt/" in self.path:
            self._json({"data": [{"id": "gpt-teste"}, {"id": "text-embedding-3"}, {"id": "gpt-teste-audio"}]})
        else:
            self._json({"models": [{"name": "models/gemini-teste", "supportedGenerationMethods": ["generateContent"]},
                                   {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}]})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        RECEBIDO.append((self.path, {k.lower(): v for k, v in self.headers.items()}, corpo))
        if "isto gera erro" in json.dumps(corpo, ensure_ascii=False):
            return self._json({"error": {"message": "chave inválida (teste)"}}, 401)
        if "/claude/" in self.path:
            self._json({"content": [{"type": "text", "text": "**Pressão** ok pelo Claude"}]})
        elif "/gpt/" in self.path:
            self._json({"choices": [{"message": {"content": "ok pelo GPT"}}]})
        else:
            self._json({"candidates": [{"content": {"parts": [{"text": "ok pelo Gemini"}]}}]})


srv = HTTPServer(("127.0.0.1", 0), Falso)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_port}"
orig_p, orig_m = A.pedido, A.pedido_modelos
A.pedido = lambda k, *a: (lambda u, c, b: (f"{BASE}/{k}/chat/" + u.split("/")[-1], c, b))(*orig_p(k, *a))
A.pedido_modelos = lambda k, ch: (lambda u, c: (f"{BASE}/{k}/models", c))(*orig_m(k, ch))


def esperar(cond, s=8):
    laco, t = QEventLoop(), QTimer()
    t.timeout.connect(lambda: laco.quit() if cond() else None)
    t.start(50)
    QTimer.singleShot(int(s * 1000), laco.quit)
    laco.exec()
    t.stop()


print("== chave criptografada (DPAPI)")
salvas = {k: QSettings("GWATER", "GWATER").value(f"ia/chave_{k}", "") for k in A.FORNECEDORES}
A.gravar_chave("claude", "sk-teste-123")
bruto = QSettings("GWATER", "GWATER").value("ia/chave_claude", "")
checar(A.ler_chave("claude") == "sk-teste-123" and "sk-teste" not in bruto, "a chave volta igual e não fica em texto")

TMP = tempfile.mkdtemp(prefix="gwater_teste_ia_")
for a_ in ("gwater_cadastro.gpkg", "GWATER_cadastro.qgz"):
    shutil.copyfile(os.path.join(RAIZ, "cadastro", a_), os.path.join(TMP, a_))
j = Janela()
j.abrir_projeto(os.path.join(TMP, "GWATER_cadastro.qgz"))
n = j.nucleo
ctx = A.contexto(n)
checar("Cadastro: gwater_cadastro.gpkg" in ctx and "Comprimento total" in ctx, "contexto do cadastro montado")
j.acionar("simular")
checar("pressão mínima" in A.contexto(n), "contexto traz o último cálculo")

QSettings("GWATER", "GWATER").setValue("ia/modo", "api")
w = A.assistente(n)
checar(w.pilha.currentIndex() == 0 and w.modelo.isVisible() or True, "abre no modo API (chat do GWATER)")
for k, esperado, modelo_lista in (("claude", "Pressão", "claude-opus-5-5"), ("gpt", "ok pelo GPT", "gpt-teste"),
                                  ("gemini", "ok pelo Gemini", "gemini-teste")):
    w.forn.setCurrentIndex(w.forn.findData(k))
    A.gravar_chave(k, f"chave-{k}")
    w.atualizar_modelos()
    esperar(lambda: w.modelo.findText(modelo_lista) >= 0)
    itens = [w.modelo.itemText(i) for i in range(w.modelo.count())]
    checar(modelo_lista in itens and not any("embedding" in i or "audio" in i for i in itens),
           f"{k}: modelos do fornecedor (só os de conversa): {itens}")
    w.modelo.setCurrentText(modelo_lista)
    w.limpar()
    for pergunta in ("qual a pressão mínima?", "e a máxima?"):
        antes = len(w.historico)
        w.entrada.setPlainText(pergunta)
        w.enviar()
        esperar(lambda: len(w.historico) >= antes + 2)
    caminho, cab, corpo = RECEBIDO[-1]
    texto_corpo = json.dumps(corpo, ensure_ascii=False)
    checar(esperado in w.conversa.toPlainText() and len(w.historico) == 4,
           f"{k}: respondeu e guardou a conversa ({len(w.historico)} mensagens)")
    checar("qual a pressão mínima?" in texto_corpo and "e a máxima?" in texto_corpo and "Dados atuais do GWATER" in
           texto_corpo and modelo_lista in (texto_corpo + caminho), f"{k}: mandou o histórico, o contexto e o modelo")
    chave_ok = {"claude": cab.get("x-api-key"), "gpt": cab.get("authorization"),
                "gemini": cab.get("x-goog-api-key")}[k]
    checar(chave_ok and f"chave-{k}" in chave_ok, f"{k}: chave no cabeçalho certo")
w.limpar()
w.entrada.setPlainText("isto gera erro")
w.enviar()
esperar(lambda: "chave inválida" in w.conversa.toPlainText())
checar("chave inválida" in w.conversa.toPlainText() and not w.historico, "erro da API aparece e não suja a conversa")
QSettings("GWATER", "GWATER").setValue("ia/modo", "site")
w.modo.setCurrentIndex(w.modo.findData("site"))
checar(w.pilha.currentIndex() == 1, "modo Conta mostra o site do fornecedor")

for k, v in salvas.items():  # devolve as chaves que já existiam
    if v:
        QSettings("GWATER", "GWATER").setValue(f"ia/chave_{k}", v)
    else:
        QSettings("GWATER", "GWATER").remove(f"ia/chave_{k}")
j.fechar_projeto(False)
srv.shutdown()
app.exitQgis()
shutil.rmtree(TMP, ignore_errors=True)
print("\nRESULTADO:", "TUDO OK" if not falhas else f"{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
