"""Servidor local do painel: entrega as telas e simula sob demanda.

Uso:  python servidor.py [cadastro.gpkg] [--porta=8765]   ->  http://localhost:8765
  GET  /api/rede                 rede do cadastro em GeoJSON (WGS84)
  POST /api/simular-rede         {"com_projetados": true} -> validação + séries por nó e trecho
  POST /api/simular              {"vrp1": 28, ...} -> sinótico do sistema de exemplo (Fase 0)
  POST /api/simular-cadastro     sinótico alimentado pelo cadastro de exemplo
  GET  /api/sinotico?projetados=1 esquema do sistema montado a partir do cadastro (sinotico.py)
  GET  /api/cadastro             cadastro em uso; POST {"gpkg": caminho} troca (o QGIS avisa ao abrir o painel)
  GET  /api/dados                dados recebidos (séries de campo) + análise; POST /api/dados/ler (prévia da planilha),
       /api/dados/importar, /api/dados/digitar (24 leituras de um dia), /api/dados/excluir (ver dados_recebidos.py)
"""
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from cadastro_para_inp import GPKG_PADRAO
from modelo import PADRAO
from simular import RAIZ, simular, simular_cadastro

PORTA = 8765
# sobe a cada rota nova: o plugin do QGIS compara e reinicia um servidor antigo que tenha ficado no ar
VERSAO = 4
SERVIDOR = None
CADASTRO = None
GEMEO = SIMULADOR = None  # operação ao vivo (criados sob demanda)


def cadastro():
    return CADASTRO or GPKG_PADRAO


def gemeo(novo=False):
    global GEMEO
    if GEMEO is None or novo:
        import aovivo
        GEMEO = aovivo.Gemeo(cadastro())
    return GEMEO


class Handler(SimpleHTTPRequestHandler):
    def _json(self, dados, code=200):
        out = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota == "/":  # a tela inicial é o sinótico do cadastro aberto
            self.send_response(302)
            self.send_header("Location", "/sinotico.html")
            self.end_headers()
            return
        if rota == "/api/versao":
            return self._json({"versao": VERSAO, "cadastro": os.path.basename(cadastro())})
        if rota == "/api/cadastro":
            return self._json({"gpkg": cadastro(), "arquivo": os.path.basename(cadastro())})
        if rota == "/api/dados":
            import dados_recebidos as dr
            try:
                tudo = dr.carregar(dr.arquivo_de(cadastro()))
                return self._json({"elementos_padrao": {k: {"nome": n, "grandezas": g} for k, (n, g) in dr.ELEMENTOS.items()},
                                   "unidades": {k: list(v) for k, v in dr.UNIDADES.items()},
                                   "series": tudo, "analise": dr.analisar(tudo), "arquivo": os.path.basename(cadastro())})
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        if rota == "/api/sinotico":
            import sinotico
            try:
                proj = "projetados=1" in self.path
                return self._json({**sinotico.montar(cadastro(), proj), "arquivo": os.path.basename(cadastro())})
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        if rota in ("/api/aovivo/estado", "/api/aovivo/simulador"):
            try:
                if rota == "/api/aovivo/estado":
                    return self._json(gemeo().estado() if GEMEO or SIMULADOR else {"agora": None})
                g = gemeo()
                return self._json({"simulador": SIMULADOR.status() if SIMULADOR else None,
                                   "nos_consumo": sorted(g.consumo)})
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        if self.path.split("?")[0] == "/api/medicoes":
            import calibracao
            try:
                m = calibracao.ler_medicoes(cadastro())
                return self._json({"campanha": m["campanha"].iloc[0] if len(m) else None, "leituras": len(m),
                                   "sensores": [{"elemento": e, "grandeza": g, "n": len(x),
                                                 "de": float(x["hora"].min()), "ate": float(x["hora"].max())}
                                                for (e, g), x in m.groupby(["elemento", "grandeza"], sort=False)]})
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        if self.path.split("?")[0] == "/api/cenarios":
            import cenarios
            try:
                return self._json(cenarios.listar(cadastro()))
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        if self.path.split("?")[0] == "/api/rede":
            from rede_geojson import rede
            try:
                return self._json({**rede(cadastro()), "arquivo": os.path.basename(cadastro())})
            except Exception as e:
                return self._json({"erro": str(e)}, 400)
        return super().do_GET()

    def do_POST(self):
        rotas = ("/api/simular", "/api/simular-cadastro", "/api/simular-rede", "/api/cenarios",
                 "/api/cenarios/excluir", "/api/medicoes", "/api/calibracao/comparar",
                 "/api/calibracao/calibrar", "/api/calibracao/aplicar", "/api/telemetria",
                 "/api/aovivo/reconhecer", "/api/aovivo/simulador", "/api/cadastro",
                 "/api/dados/ler", "/api/dados/importar", "/api/dados/digitar", "/api/dados/excluir", "/api/encerrar")
        if self.path not in rotas:
            return self.send_error(404)
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/encerrar":  # o plugin troca um servidor antigo por um novo
                import threading
                self._json({"ok": True})
                threading.Thread(target=SERVIDOR.shutdown, daemon=True).start()
                return
            if self.path.startswith("/api/dados/"):  # dados recebidos: {elemento, nome, conteudo (base64), aba, mapa, unidades}
                import dados_recebidos as dr
                arq = dr.arquivo_de(cadastro())
                if self.path == "/api/dados/ler":
                    p = dr.ler_planilha(corpo["nome"], corpo["conteudo"], corpo.get("aba"))
                    dados = {**{k: p[k] for k in ("abas", "aba", "colunas", "n")}, "linhas": p["linhas"][:8],
                             "sugestao": dr.sugerir(corpo["elemento"], p["colunas"])}
                elif self.path == "/api/dados/importar":
                    dados = dr.importar(arq, corpo["elemento"], corpo["nome"], corpo["conteudo"], corpo["mapa"],
                                        corpo.get("unidades"), corpo.get("aba"))
                elif self.path == "/api/dados/digitar":  # {elemento, data: aaaa-mm-dd, valores: {grandeza: [24]}, unidades}
                    dados = dr.digitar(arq, corpo["elemento"], corpo["data"], corpo["valores"], corpo.get("unidades")) or {}
                else:
                    dr.excluir(arq, corpo["elemento"])
                    dados = {"ok": True}
            elif self.path == "/api/cadastro":  # o QGIS abriu outro cadastro
                global CADASTRO, GEMEO
                if not os.path.exists(corpo["gpkg"]):
                    raise FileNotFoundError(corpo["gpkg"])
                if os.path.abspath(corpo["gpkg"]) != os.path.abspath(cadastro()):
                    CADASTRO, GEMEO = corpo["gpkg"], None
                dados = {"gpkg": cadastro(), "arquivo": os.path.basename(cadastro())}
            elif self.path == "/api/simular-rede":
                # corpo: {com_projetados, alteracoes, fator_demanda, proposta: bool}
                import cenarios
                import gwater_cli
                dados = gwater_cli.simular(cadastro(), bool(corpo.get("com_projetados")),
                                           cenarios.alteracoes_completas(corpo),
                                           nome_inp="proposta" if corpo.get("proposta") else None)
            elif self.path == "/api/cenarios":
                import cenarios
                cid = cenarios.salvar(cadastro(), corpo)
                dados = {"id": cid, "cenarios": cenarios.listar(cadastro())}
            elif self.path == "/api/telemetria":  # [{elemento, grandeza, valor, ts}] ou {leituras: [...]}
                leituras = corpo["leituras"] if isinstance(corpo, dict) else corpo
                dados = {"recebidas": gemeo().receber(leituras)}
            elif self.path == "/api/aovivo/reconhecer":  # {id}
                dados = {"ok": gemeo().reconhecer(int(corpo["id"]))}
            elif self.path == "/api/aovivo/simulador":  # {acao: iniciar|parar, velocidade, inicio_h, vazamento}
                global SIMULADOR
                if SIMULADOR:
                    SIMULADOR.parar.set()
                    SIMULADOR = None
                if corpo.get("acao") == "iniciar":
                    import aovivo
                    SIMULADOR = aovivo.Simulador(gemeo(novo=True), corpo.get("velocidade", 2),
                                                 corpo.get("inicio_h", 5), corpo.get("vazamento"))
                    SIMULADOR.start()
                dados = {"simulador": SIMULADOR.status() if SIMULADOR else None}
            elif self.path == "/api/medicoes":  # {csv: texto, campanha}
                import calibracao
                med = calibracao.ler_csv(corpo["csv"])
                calibracao.salvar_medicoes(cadastro(), med, corpo.get("campanha") or "campanha")
                dados = {"leituras": len(med), "sensores": med.groupby(["elemento", "grandeza"]).ngroups}
            elif self.path == "/api/calibracao/comparar":  # {alteracoes?}
                import calibracao
                dados = calibracao.comparar(cadastro(), alteracoes=corpo.get("alteracoes"))
            elif self.path == "/api/calibracao/calibrar":  # {por_c, por_d, ajustar_c, ajustar_d}
                import calibracao
                dados = calibracao.calibrar(cadastro(), corpo.get("por_c", "material"), corpo.get("por_d", "setor"),
                                            corpo.get("ajustar_c", True), corpo.get("ajustar_d", True))
            elif self.path == "/api/calibracao/aplicar":  # {alteracoes}
                import calibracao
                dados = {"backup": os.path.basename(calibracao.aplicar_ao_cadastro(cadastro(), corpo["alteracoes"]))}
            elif self.path == "/api/cenarios/excluir":
                import cenarios
                cenarios.excluir(cadastro(), corpo["id"])
                dados = {"cenarios": cenarios.listar(cadastro())}
            elif self.path == "/api/simular-cadastro":
                dados, _ = simular_cadastro(cadastro())  # lê o GeoPackage salvo pelo QGIS
            else:
                # campo vazio no formulário = mantém o valor padrão
                params = {k: float(v) for k, v in corpo.items() if k in PADRAO and str(v).strip() != ""}
                p = {**PADRAO, **params}
                if p["bomba_liga"] >= p["bomba_desliga"]:
                    raise ValueError("o nível de 'liga' da bomba precisa ser menor que o de 'desliga'")
                dados, _ = simular(params)
            self._json(dados)
        except Exception as e:  # erro do motor volta para a tela
            self._json({"erro": str(e)}, 400)

    def log_message(self, fmt, *args):
        print(fmt % args)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--porta=")]
    CADASTRO = args[0] if args else None  # o plugin do QGIS passa o cadastro aberto
    PORTA = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--porta=")), PORTA)
    h = partial(Handler, directory=os.path.join(RAIZ, "painel"))
    print(f"Painel GWATER em http://localhost:{PORTA} · cadastro: {cadastro()}")
    SERVIDOR = ThreadingHTTPServer(("127.0.0.1", PORTA), h)
    SERVIDOR.serve_forever()
