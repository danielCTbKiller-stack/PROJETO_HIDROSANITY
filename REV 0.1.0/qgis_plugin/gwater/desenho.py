"""Desenho como no WaterGEMS: o usuário desenha no QGIS e o GWATER mantém a rede ligada.

- Tubulação nova: cada ponta liga no elemento que estiver ali; ponta solta ganha um nó novo;
  ponta no meio de outra tubulação divide essa tubulação. Vértice da tubulação sobre um
  elemento existente divide a tubulação nova ali.
- Nó, válvula, bomba... sobre uma tubulação: a tubulação é dividida e o elemento fica no meio.
  Válvula/bomba/reservatório sobre um nó existente: o nó é substituído pelo elemento.
- Elemento movido: as pontas das tubulações ligadas a ele acompanham.
- Códigos, comprimento, nó inicial/final, rugosidade e (se houver MDT) cota são preenchidos.

Tudo acontece no buffer de edição: nada vai para o GeoPackage até "Salvar edições".
"""
import re
from functools import partial

from qgis.core import (
    QgsDefaultValue, QgsExpression, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY,
    QgsProject, QgsRectangle,
)
from qgis.PyQt.QtCore import QTimer

PONTOS = ["captacao", "reservatorio", "bomba", "valvula", "no_juncao"]
REDE = PONTOS + ["trecho"]
PREFIXO = {"captacao": "C", "reservatorio": "R", "bomba": "B", "valvula": "V", "no_juncao": "N", "trecho": "T"}
# "cota" é a cota do terreno em todo elemento pontual (cadastros antigos podem não ter o campo em reservatório
# e captação: ele é criado na primeira aplicação do TRex)
CAMPO_COTA = {"no_juncao": "cota", "valvula": "cota", "bomba": "cota", "reservatorio": "cota", "captacao": "cota"}
TOL = 0.05  # m: igual à tolerância do conversor (cadastro_para_inp.TOL_PONTA)
NOME = {"captacao": "captação", "reservatorio": "reservatório", "bomba": "bomba", "valvula": "válvula",
        "no_juncao": "nó", "trecho": "tubulação"}


def _vazio(v):
    return v is None or str(v) in ("", "NULL")


def _linha(g):
    if g.isMultipart():
        partes = g.asMultiPolyline()
        return [QgsPointXY(p) for p in partes[0]] if partes else []
    return [QgsPointXY(p) for p in g.asPolyline()]


def _ponto(g):
    return QgsPointXY(g.asMultiPoint()[0]) if g.isMultipart() else QgsPointXY(g.asPoint())


def _caixa(p, tol=TOL):
    return QgsRectangle(p.x() - tol, p.y() - tol, p.x() + tol, p.y() + tol)


def _sem_repetidos(pts):
    out = []
    for p in pts:
        if not out or out[-1].distance(p) > 1e-6:
            out.append(p)
    return out


class Topologia:
    def __init__(self, plugin):
        self.plugin = plugin
        self.ativo = True          # caixa "Ligar automaticamente" do painel
        self.ocupado = False       # nossas próprias edições não disparam o tratamento de novo
        self.salvando = False      # ao salvar, o QGIS reemite featureAdded das feições gravadas
        self.camadas = {}
        self.pos = {}              # (id da camada, fid) -> posição antes de mover
        self.fila = []
        self.ligacoes = []
        self.mdt = None            # fonte de cota automática dos nós novos (cotas.Fonte ou raster)
        self.log = []              # o que foi feito sozinho (mostrado na barra de mensagens e usado nos testes)
        self.contador = None       # {camada: último número} durante operações em lote
        self.n_nos = self.n_divisoes = 0

    # ------------------------------------------------ ligar às camadas do cadastro aberto
    def conectar(self):
        self.desconectar()
        for nome in REDE:
            try:
                lyr = self.plugin.camada(nome)
            except LookupError:
                continue
            self.camadas[nome] = lyr
            for sinal, slot in ((lyr.featureAdded, partial(self._adicionado, nome)),
                                (lyr.geometryChanged, partial(self._geometria, nome)),
                                (lyr.editingStarted, partial(self._memorizar, nome)),
                                (lyr.beforeCommitChanges, self._salvando),
                                (lyr.afterCommitChanges, partial(self._memorizar, nome))):
                sinal.connect(slot)
                self.ligacoes.append((lyr.id(), sinal, slot))
            self._memorizar(nome)
        return len(self.camadas) == len(REDE)

    def desconectar(self):
        prj = QgsProject.instance()
        for lid, sinal, slot in self.ligacoes:
            # camada que já saiu do projeto pode estar apagada: tocar no sinal dela derruba o QGIS
            # (o Qt desfaz sozinho as ligações de um objeto apagado)
            if prj.mapLayer(lid) is None:
                continue
            try:
                sinal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self.ligacoes, self.camadas, self.pos, self.fila = [], {}, {}, []

    def _salvando(self, *_):
        self.salvando = True
        QTimer.singleShot(0, self._salvou)  # a gravação é síncrona: o timer roda depois dela

    def _salvou(self):
        self.salvando = False

    def camadas_saindo(self, ids):
        """QgsProject.layersWillBeRemoved: desliga enquanto as camadas ainda existem."""
        if any(lyr.id() in ids for lyr in self.camadas.values()):
            self.desconectar()

    def _memorizar(self, nome):
        if nome == "trecho" or nome not in self.camadas:
            return
        lyr = self.camadas[nome]
        for f in lyr.getFeatures():
            if f.hasGeometry():
                self.pos[(lyr.id(), f.id())] = _ponto(f.geometry())

    # ------------------------------------------------ sinais do QGIS (adiados: a ferramenta do QGIS termina antes)
    def _adicionado(self, nome, fid):
        if nome not in self.camadas:
            return
        if nome != "trecho":  # posição de partida, para as tubulações acompanharem se o elemento for movido
            f = self.camadas[nome].getFeature(fid)
            if f.hasGeometry():
                self.pos[(self.camadas[nome].id(), fid)] = _ponto(f.geometry())
        if not self.ocupado and not self.salvando and self.ativo:
            self._adiar(self._trecho_novo if nome == "trecho" else self._ponto_novo, *((fid,) if nome == "trecho"
                                                                                     else (nome, fid)))

    def _geometria(self, nome, fid, geom):
        if self.ocupado or self.salvando or not self.ativo or nome not in self.camadas:
            return
        if nome == "trecho":
            self._adiar(self._ligar_pontas, fid)
            return
        lyr = self.camadas[nome]
        antes, depois = self.pos.get((lyr.id(), fid)), _ponto(geom)
        self.pos[(lyr.id(), fid)] = depois
        if antes and antes.distance(depois) > 1e-6:
            self._adiar(self._arrastar, antes, depois)

    def _adiar(self, func, *args):
        self.fila.append((func, args))
        if len(self.fila) == 1:
            QTimer.singleShot(0, self.processar)

    def processar(self):
        fila, self.fila = self.fila, []
        if not fila:
            return
        self.ocupado = True
        n0 = len(self.log)
        try:
            for func, args in fila:
                try:
                    func(*args)
                except Exception as e:  # nunca derrubar a edição do usuário
                    self.plugin.aviso(f"ligação automática: {e}")
        finally:
            self.ocupado = False
        novos = self.log[n0:]
        if novos:
            self.plugin.informar(" · ".join(novos[:4]) + (f" (+{len(novos) - 4})" if len(novos) > 4 else ""))
            self.plugin.iface.mapCanvas().refresh()

    # ------------------------------------------------ consultas
    def _editar(self, lyr):
        if not lyr.isEditable():
            lyr.startEditing()

    def elemento_em(self, p, ignorar=None, tol=TOL):
        """(camada, feição) do elemento pontual mais próximo de p, a até tol metros."""
        melhor = None
        for nome in PONTOS:
            lyr = self.camadas.get(nome)
            if not lyr:
                continue
            for f in lyr.getFeatures(QgsFeatureRequest().setFilterRect(_caixa(p, tol))):
                if ignorar != (nome, f.id()) and f.hasGeometry():
                    d = _ponto(f.geometry()).distance(p)
                    if d <= tol and (melhor is None or d < melhor[0]):
                        melhor = (d, nome, f)
        return melhor[1:] if melhor else None

    def trechos_cruzando(self, p, ignorar=(), tol=TOL):
        """Tubulações que passam a até tol de p, fora das pontas: [(feição, índice do vértice seguinte)]."""
        out = []
        for f in self.camadas["trecho"].getFeatures(QgsFeatureRequest().setFilterRect(_caixa(p, tol))):
            if f.id() in ignorar or not f.hasGeometry():
                continue
            pts = _linha(f.geometry())
            if len(pts) < 2 or pts[0].distance(p) <= tol or pts[-1].distance(p) <= tol:
                continue
            d2, _, depois, _ = f.geometry().closestSegmentWithContext(p)
            if d2 <= tol * tol:
                out.append((f, depois))
        return out

    def proximo_id(self, nome):
        if self.contador is not None and nome in self.contador:  # em lote: sem varrer a camada a cada código
            self.contador[nome] += 1
            return f"{PREFIXO[nome]}-{self.contador[nome]:04d}"
        lyr, pre = self.camadas[nome], PREFIXO[nome]
        rx = re.compile(rf"^{pre}-(\d+)$")
        n = 0
        for f in lyr.getFeatures():
            m = rx.match(str(f["id"] or ""))
            if m:
                n = max(n, int(m.group(1)))
        if self.contador is not None:
            self.contador[nome] = n + 1
        return f"{pre}-{n + 1:04d}"

    def _id_unico(self, nome, fid):
        """O código da feição está preenchido e não se repete? (o código sugerido pelo formulário pode
        coincidir com um criado aqui e ainda não salvo; os códigos valem para todas as camadas de pontos)"""
        cod = self.camadas[nome].getFeature(fid)["id"]
        if _vazio(cod):
            return False
        filtro = f'"id" = {QgsExpression.quotedValue(cod)}'
        for outro, lyr in self.camadas.items():
            if (outro == "trecho") != (nome == "trecho"):
                continue
            for f in lyr.getFeatures(QgsFeatureRequest().setFilterExpression(filtro)):
                if (outro, f.id()) != (nome, fid):
                    return False
        return True

    def cota_mdt(self, p):
        """Cota do terreno pela fonte escolhida em Cotas do terreno (raster, curvas de nível ou pontos)."""
        if not self.mdt:
            return None
        from .cotas import Fonte
        if not isinstance(self.mdt, Fonte):  # raster direto (versões antigas do projeto)
            self.mdt = Fonte("raster", self.mdt, self.camadas["trecho"].crs())
        try:
            if not self.mdt.valida():
                raise RuntimeError
            return self.mdt.cota(p)
        except RuntimeError:  # camada removida do projeto
            self.mdt = None
            return None

    def rugosidade(self, material):
        try:
            dom = self.plugin.camada("dominio_material")
        except LookupError:
            return None
        for f in dom.getFeatures():
            if f["material"] == material:
                return f["rugosidade_hw"]
        return None

    # ------------------------------------------------ edições
    def _mudar(self, lyr, fid, campo, valor):
        i = lyr.fields().indexOf(campo)
        if i >= 0:
            # skipDefaultValues: nós mesmos preenchemos os campos calculados, sem depender das expressões
            lyr.changeAttributeValue(fid, i, valor, None, True)

    def _geometria_trecho(self, fid, pts):
        tr = self.camadas["trecho"]
        g = QgsGeometry.fromPolylineXY(pts)
        tr.changeGeometry(fid, g, True)
        self._mudar(tr, fid, "comprimento", round(g.length(), 2))

    def criar_no(self, p, obs="criado ao desenhar"):
        lyr = self.camadas["no_juncao"]
        self._editar(lyr)
        f = QgsFeature(lyr.fields())
        f.setGeometry(QgsGeometry.fromPointXY(p))
        nid = self.proximo_id("no_juncao")
        for campo, valor in {"id": nid, "tipo": "JUNCAO", "demanda_base": 0.0, "cota": self.cota_mdt(p),
                             "situacao": self.plugin.prototipo("situacao"),
                             "observacao": obs}.items():
            f[campo] = valor
        lyr.addFeature(f)  # featureAdded guarda a posição (ver _adicionado)
        self.log.append(f"nó {nid} criado")
        self.n_nos += 1
        return nid

    def dividir(self, f, depois, p, nid):
        """Divide a tubulação f em p; o pedaço de jusante vira uma tubulação nova. Os dois ligam em nid."""
        tr = self.camadas["trecho"]
        self._editar(tr)
        pts = _linha(f.geometry())
        a, b = _sem_repetidos(pts[:depois] + [p]), _sem_repetidos([p] + pts[depois:])
        if len(a) < 2 or len(b) < 2:
            return None
        no_final = f["no_final"]
        self._geometria_trecho(f.id(), a)
        self._mudar(tr, f.id(), "no_final", nid)
        nova = QgsFeature(tr.fields())
        nova.setAttributes(list(f.attributes()))
        if tr.fields().indexOf("fid") >= 0:
            nova["fid"] = None  # chave do GeoPackage: gerada ao salvar
        g = QgsGeometry.fromPolylineXY(b)
        nova.setGeometry(g)
        novo_id = self.proximo_id("trecho")
        nova["id"], nova["no_inicial"], nova["no_final"] = novo_id, nid, no_final
        nova["comprimento"] = round(g.length(), 2)
        tr.addFeature(nova)
        self.log.append(f"tubulação {f['id']} dividida em {nid} (nova: {novo_id})")
        self.n_divisoes += 1
        return nova.id()

    def religar(self, antigo, novo):
        """Tubulações que apontavam para o código antigo passam a apontar para o novo."""
        tr = self.camadas["trecho"]
        for campo in ("no_inicial", "no_final"):
            filtro = f'"{campo}" = {QgsExpression.quotedValue(antigo)}'
            for f in tr.getFeatures(QgsFeatureRequest().setFilterExpression(filtro)):
                self._editar(tr)
                self._mudar(tr, f.id(), campo, novo)

    def no_na_ponta(self, p, fid_trecho):
        """Código do elemento na ponta p da tubulação (cria/divide o que for preciso)."""
        achado = self.elemento_em(p)
        if achado:
            return achado[1]["id"]
        cruzando = self.trechos_cruzando(p, ignorar=(fid_trecho,))
        nid = self.criar_no(p)
        for f, depois in cruzando:
            self.dividir(f, depois, p, nid)
        if not cruzando:  # outra tubulação terminando no mesmo ponto, sem nó (cadastro antigo): liga também
            tr = self.camadas["trecho"]
            for f in tr.getFeatures(QgsFeatureRequest().setFilterRect(_caixa(p))):
                if f.id() == fid_trecho or not f.hasGeometry():
                    continue
                pts = _linha(f.geometry())
                for campo, q in (("no_inicial", pts[0]), ("no_final", pts[-1])):
                    if q.distance(p) <= TOL:
                        self._mudar(tr, f.id(), campo, nid)
        return nid

    # ------------------------------------------------ tratamentos
    def _trecho_novo(self, fid):
        tr = self.camadas["trecho"]
        f = tr.getFeature(fid)
        if not f.isValid() or not f.hasGeometry():
            return
        pts = _sem_repetidos(_linha(f.geometry()))
        if len(pts) < 2:
            return
        # vértices intermediários sobre elementos existentes: a tubulação é dividida ali
        cortes = [k for k in range(1, len(pts) - 1) if self.elemento_em(pts[k])]
        pedacos = [pts[i:j + 1] for i, j in zip([0] + cortes, cortes + [len(pts) - 1])]
        fids = [fid]
        if len(pedacos) > 1:
            self._geometria_trecho(fid, pedacos[0])
            for pedaco in pedacos[1:]:
                nova = QgsFeature(tr.fields())
                nova.setAttributes(list(f.attributes()))
                if tr.fields().indexOf("fid") >= 0:
                    nova["fid"] = None
                nova.setGeometry(QgsGeometry.fromPolylineXY(pedaco))
                nova["id"] = self.proximo_id("trecho")
                tr.addFeature(nova)
                fids.append(nova.id())
            self.log.append(f"tubulação dividida em {len(pedacos)} nos elementos por onde passa")
        for k in fids:
            if not self._id_unico("trecho", k):
                self._mudar(tr, k, "id", self.proximo_id("trecho"))
            self._ligar_pontas(k, nova=True)

    def _ligar_pontas(self, fid, nova=False):
        tr = self.camadas["trecho"]
        f = tr.getFeature(fid)
        if not f.isValid() or not f.hasGeometry():
            return
        pts = _linha(f.geometry())
        if len(pts) < 2:
            return
        ini = self.no_na_ponta(pts[0], fid)
        fim = self.no_na_ponta(pts[-1], fid)
        f = tr.getFeature(fid)  # pode ter mudado
        self._mudar(tr, fid, "no_inicial", ini)
        self._mudar(tr, fid, "no_final", fim)
        self._mudar(tr, fid, "comprimento", round(f.geometry().length(), 2))
        if _vazio(f["rugosidade_hw"]) and not _vazio(f["material"]):
            self._mudar(tr, fid, "rugosidade_hw", self.rugosidade(f["material"]))
        if nova:
            self.log.append(f"tubulação {f['id']}: {ini} → {fim}, {f.geometry().length():.1f} m")

    def _ponto_novo(self, nome, fid):
        lyr = self.camadas[nome]
        f = lyr.getFeature(fid)
        if not f.isValid() or not f.hasGeometry():
            return
        p = _ponto(f.geometry())
        self.pos[(lyr.id(), fid)] = p
        if not self._id_unico(nome, fid):
            self._mudar(lyr, fid, "id", self.proximo_id(nome))
            f = lyr.getFeature(fid)
        campo = CAMPO_COTA.get(nome)
        if campo and lyr.fields().indexOf(campo) >= 0 and _vazio(f[campo]):
            cota = self.cota_mdt(p)
            if cota is not None:
                self._mudar(lyr, fid, campo, cota)
        outro = self.elemento_em(p, ignorar=(nome, fid))
        if outro:
            onome, of = outro
            if onome == "no_juncao" and nome != "no_juncao":
                # como no WaterGEMS: o nó vira o elemento novo (as tubulações passam a ligar nele)
                self.religar(of["id"], f["id"])
                self.camadas["no_juncao"].deleteFeature(of.id())
                self.log.append(f"nó {of['id']} substituído por {NOME[nome]} {f['id']}")
            else:
                self.plugin.aviso(f"já existe {NOME[onome]} {of['id']} neste ponto; {NOME[nome]} {f['id']} "
                                  "ficou sobreposto. Apague um dos dois.")
            return
        for t, depois in self.trechos_cruzando(p):
            self.dividir(t, depois, p, f["id"])

    def _arrastar(self, antes, depois):
        tr = self.camadas["trecho"]
        for f in tr.getFeatures(QgsFeatureRequest().setFilterRect(_caixa(antes))):
            pts = _linha(f.geometry())
            mudou = False
            if pts and pts[0].distance(antes) <= TOL:
                pts[0], mudou = depois, True
            if pts and pts[-1].distance(antes) <= TOL:
                pts[-1], mudou = depois, True
            if mudou:
                self._editar(tr)
                self._geometria_trecho(f.id(), pts)
                self.log.append(f"tubulação {f['id']} acompanhou ({f.geometry().length():.1f} → "
                                f"{QgsGeometry.fromPolylineXY(pts).length():.1f} m)")


    # ------------------------------------------------ ferramenta Dividir tubulações (em lote)
    def dividir_rede(self, tol, fids=None, nos=True, em_t=True, encaixar=True):
        """Corrige a ligação da rede com uma tolerância (m), como o "Split" do WaterGEMS.

        fids: tubulações a tratar (None = todas).
        encaixar: ponta de tubulação a até tol de um elemento vai para cima dele;
        em_t: ponta a até tol do meio de outra tubulação divide essa tubulação (ligação em T);
        nos: elemento (nó, válvula, bomba...) a até tol do meio de uma tubulação divide a tubulação ali.
        Devolve {"encaixadas", "divididas", "nos_criados"}. Fica no buffer de edição.
        """
        tr = self.camadas["trecho"]
        for lyr in self.camadas.values():
            self._editar(lyr)
        alvo = set(fids) if fids is not None else {f.id() for f in tr.getFeatures()}
        self.ocupado, self.contador = True, {}
        self.n_nos = self.n_divisoes = 0
        encaixadas = 0
        try:
            if encaixar:
                for fid in list(alvo):
                    f = tr.getFeature(fid)
                    pts = _linha(f.geometry()) if f.hasGeometry() else []
                    mudou = False
                    for k in (0, -1):
                        if pts and not self.elemento_em(pts[k]):
                            perto = self.elemento_em(pts[k], tol=tol)
                            if perto:
                                pts[k], mudou = _ponto(perto[1].geometry()), True
                                encaixadas += 1
                    if mudou and len(_sem_repetidos(pts)) >= 2:
                        self._geometria_trecho(fid, _sem_repetidos(pts))
            if em_t:
                for fid in list(alvo):
                    f = tr.getFeature(fid)
                    if not f.hasGeometry():
                        continue
                    pts = _linha(f.geometry())
                    for p in (pts[0], pts[-1]):
                        if self.elemento_em(p):
                            continue
                        hospedeiras = self.trechos_cruzando(p, ignorar=(fid,), tol=tol)
                        if hospedeiras:
                            nid = self.criar_no(p)
                            for h, depois in hospedeiras:
                                nova = self.dividir(tr.getFeature(h.id()), depois, p, nid)
                                if nova is not None and h.id() in alvo:
                                    alvo.add(nova)
            if nos:
                for nome in PONTOS:
                    lyr = self.camadas.get(nome)
                    for e in (list(lyr.getFeatures()) if lyr else []):
                        if not e.hasGeometry():
                            continue
                        p = _ponto(e.geometry())
                        for h, depois in self.trechos_cruzando(p, tol=tol):
                            if h.id() not in alvo:
                                continue
                            nova = self.dividir(tr.getFeature(h.id()), depois, p, e["id"])
                            if nova is not None:
                                alvo.add(nova)
            for fid in alvo:  # nós inicial/final e comprimento de tudo o que foi tocado
                f = tr.getFeature(fid)
                if not f.isValid() or not f.hasGeometry():
                    continue
                pts = _linha(f.geometry())
                for campo, p in (("no_inicial", pts[0]), ("no_final", pts[-1])):
                    achado = self.elemento_em(p)
                    if achado and f[campo] != achado[1]["id"]:
                        self._mudar(tr, fid, campo, achado[1]["id"])
                self._mudar(tr, fid, "comprimento", round(f.geometry().length(), 2))
        finally:
            self.ocupado, self.contador = False, None
        return {"encaixadas": encaixadas, "divididas": self.n_divisoes, "nos_criados": self.n_nos}


# ------------------------------------------------ protótipo (valores usados em tudo o que for desenhado)
def aplicar_prototipo(camadas, dn, material, situacao, formulario):
    """Ajusta os valores padrão das camadas e se o formulário abre a cada elemento desenhado."""
    from qgis.core import Qgis, QgsEditFormConfig
    for nome, lyr in camadas.items():
        idx = lyr.fields().indexOf
        if idx("situacao") >= 0:
            lyr.setDefaultValueDefinition(idx("situacao"), QgsDefaultValue(f"'{situacao}'"))
        if nome == "trecho":
            lyr.setDefaultValueDefinition(idx("diametro_nominal"), QgsDefaultValue(str(dn) if dn else ""))
            lyr.setDefaultValueDefinition(idx("material"), QgsDefaultValue(f"'{material}'" if material else ""))
        cfg = lyr.editFormConfig()
        try:
            cfg.setSuppress(Qgis.AttributeFormSuppression.Default if formulario else Qgis.AttributeFormSuppression.On)
        except AttributeError:  # QGIS < 3.32
            cfg.setSuppress(QgsEditFormConfig.SuppressDefault if formulario else QgsEditFormConfig.SuppressOn)
        lyr.setEditFormConfig(cfg)
