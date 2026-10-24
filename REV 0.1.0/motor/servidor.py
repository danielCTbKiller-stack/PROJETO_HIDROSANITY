"""Servidor local do painel: entrega as telas e simula sob demanda.

Uso:  python servidor.py [cadastro.gpkg]   ->  http://localhost:8765
  GET  /api/rede                 rede do cadastro em GeoJSON (WGS84)
  POST /api/simular-rede         {"com_projetados": true} -> validação + séries por nó e trecho
  POST /api/simular              {"vrp1": 28, ...} -> sinótico do sistema de exemplo (Fase 0)
  POST /api/simular-cadastro     sinótico alimentado pelo cadastro de exemplo
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
                 "/api/aovivo/reconhecer", "/api/aovivo/simulador")
        if self.path not in rotas:
            return self.send_error(404)
        try:
            corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/simular-rede":
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
    CADASTRO = sys.argv[1] if len(sys.argv) > 1 else None  # o plugin do QGIS passa o cadastro aberto
    h = partial(Handler, directory=os.path.join(RAIZ, "painel"))
    print(f"Painel GWATER em http://localhost:{PORTA} · cadastro: {cadastro()}")
    ThreadingHTTPServer(("127.0.0.1", PORTA), h).serve_forever()
