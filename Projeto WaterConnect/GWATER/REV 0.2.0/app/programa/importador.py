"""Importação rápida do ModelBuilder: vários arquivos de uma vez, cada um com o seu tipo de elemento.

Tudo é calculado em memória, com índices espaciais (grade e QgsSpatialIndex), e gravado no fim em lote
(addFeatures), num único comando de desfazer por camada. Assim, dezenas de milhares de tubulações entram
em segundos; antes, cada tubulação e cada nó novo fazia buscas que varriam toda a edição em andamento.

Ordem: primeiro os elementos pontuais (nós, válvulas, bombas...), depois as tubulações, para que elas
liguem neles. Nas tubulações:
  - pontas a menos da tolerância viram o mesmo nó; ponta perto de um elemento (existente ou importado)
    liga nele; ponta solta ganha nó novo;
  - ponta que encosta no meio de outra tubulação a divide (ligação em "T");
  - elemento pontual (válvula, bomba, hidrante...) sobre o meio de uma tubulação a divide e fica entre
    os dois pedaços, como no WaterGEMS.
Tudo fica no buffer de edição: Salvar edições grava; Ctrl+Z desfaz a importação inteira.
"""
import math
import re
from collections import defaultdict

from qgis.core import (
    QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle,
    QgsSpatialIndex, QgsWkbTypes,
)
from qgis.PyQt.QtWidgets import QApplication

from gwater.desenho import PONTOS, PREFIXO, TOL, _vazio
from gwater.modelbuilder import ano, campos_do, numero

PADROES = {"no_juncao": {"tipo": "JUNCAO", "demanda_base": 0.0},
           "valvula": {"status": "ATIVA", "perda_localizada": 0.0},
           "bomba": {"status_inicial": "ABERTA", "rotacao_relativa": 1.0},
           "trecho": {"status": "ABERTO", "perda_localizada": 0.0}}


class Cancelado(Exception):
    pass


class Grade:
    """Índice de pontos por grade: vizinho mais próximo a até `tol` em tempo constante."""

    def __init__(self, tol):
        self.cel = max(tol, 0.01)
        self.tol = tol
        self.g = defaultdict(list)

    def _c(self, x, y):
        return int(math.floor(x / self.cel)), int(math.floor(y / self.cel))

    def por(self, x, y, dado):
        self.g[self._c(x, y)].append((x, y, dado))

    def perto(self, x, y, tol=None):
        tol = self.tol if tol is None else tol
        n = int(math.ceil(tol / self.cel))
        cx, cy = self._c(x, y)
        melhor, dmin = None, tol
        for i in range(cx - n, cx + n + 1):
            for j in range(cy - n, cy + n + 1):
                for px, py, dado in self.g.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    if d <= dmin:
                        melhor, dmin = (px, py, dado), d
        return melhor


class Codigos:
    """Códigos novos sem varrer as camadas a cada elemento (N-0001, T-0001...)."""

    def __init__(self, usados_pontos, usados_tubos):
        self.usados = {"pontos": set(usados_pontos), "trecho": set(usados_tubos)}
        self.n = {}
        for camada, pre in PREFIXO.items():
            conj = self.usados["trecho" if camada == "trecho" else "pontos"]
            rx = re.compile(rf"^{pre}-(\d+)$")
            self.n[camada] = max([int(m.group(1)) for c in conj for m in [rx.match(c)] if m] or [0])

    def grupo(self, camada):
        return self.usados["trecho" if camada == "trecho" else "pontos"]

    def novo(self, camada):
        conj = self.grupo(camada)
        while True:
            self.n[camada] += 1
            cod = f"{PREFIXO[camada]}-{self.n[camada]:04d}"
            if cod not in conj:
                conj.add(cod)
                return cod

    def usar(self, camada, cod):
        """O código do arquivo, se estiver livre; senão um novo. -> (código, veio_repetido)."""
        conj = self.grupo(camada)
        if cod and cod not in conj:
            conj.add(cod)
            return cod, False
        return self.novo(camada), bool(cod)


def _atributos(campos, numericos, inteiros, fo, mapa, fixos, traducoes, fixos_tipo):
    vals = {}
    for campo in campos:
        valor, col = None, mapa.get(campo)
        if col:
            bruto = fo[col]
            if not _vazio(bruto):
                if campo in traducoes:
                    valor = traducoes[campo].get(str(bruto))
                elif campo == "ano_instalacao":  # aceita 1998, 15/03/1998, 1998-03-15 ou campo de data
                    valor = ano(bruto)
                elif campo in numericos:
                    valor = numero(bruto)
                else:
                    valor = str(bruto).strip()
        if valor is None and str(fixos.get(campo, "")).strip():
            valor = ano(fixos[campo]) if campo == "ano_instalacao" else \
                numero(fixos[campo]) if campo in numericos else str(fixos[campo]).strip()
        if valor is not None and campo in inteiros:
            valor = int(round(valor))
        if valor is not None:
            vals[campo] = valor
    for campo, valor in fixos_tipo.items():  # o tipo escolhido para o arquivo manda (PRV, HIDRANTE...)
        if campo == "tipo" or campo not in vals:
            vals[campo] = valor
    return vals


def _ponto_estacao(g, nos, tubos):
    """Polígono (estação de bomba, como a pump station do WaterGEMS) -> o ponto onde a bomba entra na rede:
    o nó do cadastro dentro do polígono mais perto do centro; senão o ponto da tubulação que cruza o polígono mais
    perto do centro; senão um ponto dentro do polígono."""
    centro = g.pointOnSurface().asPoint()
    dentro = [p for p in nos(g.boundingBox()) if g.contains(QgsGeometry.fromPointXY(p))]
    if dentro:
        return min(dentro, key=lambda p: p.distance(centro))
    perto = None
    for tg in tubos(g.boundingBox()):
        if tg.intersects(g):
            p = tg.intersection(g).nearestPoint(QgsGeometry.fromPointXY(centro)).asPoint()
            if perto is None or p.distance(centro) < perto.distance(centro):
                perto = QgsPointXY(p)
    return perto or QgsPointXY(centro)


def _partes(g, linha):
    if linha:
        partes = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
        out = []
        for p in partes:
            pts = []
            for v in p:
                q = QgsPointXY(v)
                if not pts or pts[-1].distance(q) > 1e-9:
                    pts.append(q)
            if len(pts) >= 2:
                out.append(pts)
        return out
    return [QgsPointXY(p) for p in g.asMultiPoint()] if g.isMultipart() else [QgsPointXY(g.asPoint())]


def _cortar(pts, cortes):
    """Corta a polilinha nos pontos [(distância ao longo, ponto, código)] -> [(pontos, código_ini, código_fim)]."""
    acum = [0.0]
    for a, b in zip(pts, pts[1:]):
        acum.append(acum[-1] + a.distance(b))
    pedacos, atual, i = [], [pts[0]], 1
    inicio = None
    for dist, p, cod in sorted(cortes, key=lambda c: c[0]):
        while i < len(pts) and acum[i] < dist - 1e-9:
            atual.append(pts[i])
            i += 1
        atual.append(p)
        pedacos.append((atual, inicio, cod))
        atual, inicio = [p], cod
        while i < len(pts) and acum[i] <= dist + 1e-9:
            i += 1
    atual += pts[i:]
    pedacos.append((atual, inicio, None))
    return [(([q for k, q in enumerate(pp) if k == 0 or q.distance(pp[k - 1]) > 1e-9]), a, b) for pp, a, b in pedacos]


def sincronizar(nucleo, trabalhos, mover=False):
    """Synchronize do ModelBuilder: elemento do arquivo com o mesmo código de um que já existe no cadastro tem os
    dados atualizados (só os campos ligados no de-para) e, com `mover`, a posição (pontos). Marca em cada trabalho
    os registros já tratados (job["pular"]), que a importação deixa de criar. Devolve {camada: quantos}."""
    from qgis.core import QgsCoordinateTransform
    camadas = nucleo.topologia.camadas or {}
    out = {}
    for job in trabalhos:
        col_id = job["mapa"].get("id")
        dest = camadas.get(job["camada"]) or nucleo.camada(job["camada"])
        job["pular"] = set()
        if not col_id or dest is None:
            continue
        existentes = {str(f["id"]): f for f in dest.getFeatures() if not _vazio(f["id"])}
        if not existentes:
            continue
        campos = [c for c, col in job["mapa"].items() if col and c != "id" and dest.fields().indexOf(c) >= 0]
        numericos = {f.name() for f in dest.fields() if f.isNumeric()}
        inteiros = {f.name() for f in dest.fields() if f.typeName().lower().startswith("int")}
        origem = job["origem"]
        ct = QgsCoordinateTransform(origem.crs(), dest.crs(), QgsProject.instance())
        if not dest.isEditable():
            dest.startEditing()
        dest.beginEditCommand(f"ModelBuilder: atualizar {job['nome']}")
        n = 0
        feats = origem.getSelectedFeatures() if job.get("so_sel") else origem.getFeatures()
        for fo in feats:
            cod = fo[col_id]
            if _vazio(cod) or str(cod).strip() not in existentes:
                continue
            alvo = existentes[str(cod).strip()]
            vals = _atributos(campos, numericos, inteiros, fo, job["mapa"], {}, job["traducoes"], {})
            for c, v in vals.items():
                if v != alvo[c]:
                    dest.changeAttributeValue(alvo.id(), dest.fields().indexOf(c), v)
            if mover and job["camada"] != "trecho" and fo.hasGeometry() and \
                    fo.geometry().type() == QgsWkbTypes.GeometryType.PointGeometry:
                g = QgsGeometry(fo.geometry())
                g.transform(ct)
                if g.asPoint().distance(alvo.geometry().asPoint()) > 1e-6:
                    dest.changeGeometry(alvo.id(), g)
            job["pular"].add(fo.id())
            n += 1
        dest.endEditCommand()
        if n:
            out[job["camada"]] = out.get(job["camada"], 0) + n
    return out


def importar_lote(nucleo, trabalhos, opcoes, progresso=None):
    """trabalhos: [{"camada", "fixos_tipo", "origem", "mapa", "fixos", "traducoes", "so_sel", "nome"}].
    opcoes: tolerancia, situacao, criar_nos, dividir_t, dividir_tubos, substituir_nos.
    Registros listados em job["pular"] (já atualizados por sincronizar) não são criados.
    Devolve o resumo {"importados", "por_tipo", "nos_criados", "divididas", "ligados_existentes", "avisos"}."""
    topo = nucleo.topologia
    if not topo.camadas:
        topo.conectar()
    camadas = topo.camadas
    tol = max(float(opcoes.get("tolerancia", 0.5)), TOL)
    situacao = opcoes.get("situacao", "EXISTENTE")
    avisos = []

    def passo(texto, k=None, total=None):
        if progresso is not None:
            if progresso.wasCanceled():
                raise Cancelado()
            progresso.setLabelText(texto)
            if total:
                progresso.setMaximum(total)
                progresso.setValue(k or 0)
        QApplication.processEvents()

    # ------------------------------------------------ o que já existe no cadastro
    passo("Lendo o cadastro aberto…")
    grade = Grade(tol)
    usados_pontos, usados_tubos = set(), set()
    pos_existente = {}
    for nome in PONTOS:
        lyr = camadas.get(nome)
        if lyr is None:
            continue
        for f in lyr.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(["id"], lyr.fields())):
            cod = None if _vazio(f["id"]) else str(f["id"])
            if cod:
                usados_pontos.add(cod)
            if f.hasGeometry() and cod:
                g = f.geometry()
                p = QgsPointXY(g.vertexAt(0))
                grade.por(p.x(), p.y(), (cod, nome, "existente", f.id()))
                pos_existente[cod] = (p, nome, f.id())
    tr = camadas["trecho"]
    idx_exist = QgsSpatialIndex()
    geo_exist = {}
    for f in tr.getFeatures(QgsFeatureRequest().setSubsetOfAttributes(["id"], tr.fields())):
        if not _vazio(f["id"]):
            usados_tubos.add(str(f["id"]))
        if f.hasGeometry():
            idx_exist.addFeature(f.id(), f.geometry().boundingBox())
            geo_exist[f.id()] = f.geometry()
    codigos = Codigos(usados_pontos, usados_tubos)

    def nos_em(ret):  # nós do cadastro numa área (para as estações de bomba em polígono)
        return [p for p, _n, _f in pos_existente.values() if ret.contains(p)]

    idx_vindo, geo_vindo = QgsSpatialIndex(), {}  # tubulações deste mesmo lote (entram depois dos pontos)
    if any(j["camada"] != "trecho" and j["origem"].geometryType() == QgsWkbTypes.GeometryType.PolygonGeometry
           for j in trabalhos):
        for j in [j for j in trabalhos if j["camada"] == "trecho"]:
            ct = QgsCoordinateTransform(j["origem"].crs(), tr.crs(), QgsProject.instance())
            for fo in (j["origem"].getSelectedFeatures() if j.get("so_sel") else j["origem"].getFeatures()):
                if fo.hasGeometry():
                    g = QgsGeometry(fo.geometry())
                    g.transform(ct)
                    k = len(geo_vindo)
                    geo_vindo[k] = g
                    idx_vindo.addFeature(k, g.boundingBox())

    def tubos_em(ret):
        return [geo_exist[i] for i in idx_exist.intersects(ret)] + [geo_vindo[i] for i in idx_vindo.intersects(ret)]
    rug = {}
    try:
        for f in nucleo.camada("dominio_material").getFeatures():
            rug[f["material"]] = f["rugosidade_hw"]
    except LookupError:
        pass

    novos_pontos = defaultdict(list)  # camada -> [QgsFeature]
    novos_nos = []                    # nós criados nas pontas
    substituidos = {}                 # código do nó existente -> código do elemento que ficou no lugar
    por_tipo = defaultdict(int)
    repetidos = sem_geom = 0

    def novo_no(p):
        cod = codigos.novo("no_juncao")
        f = QgsFeature(camadas["no_juncao"].fields())
        f.setGeometry(QgsGeometry.fromPointXY(p))
        for campo, valor in {"id": cod, "tipo": "JUNCAO", "demanda_base": 0.0, "situacao": situacao,
                             "observacao": "criado na importação"}.items():  # cota: em lote, no fim
            if f.fields().indexOf(campo) >= 0:
                f[campo] = valor
        novos_nos.append(f)
        grade.por(p.x(), p.y(), (cod, "no_juncao", "novo", None))
        return cod

    # ------------------------------------------------ 1 · elementos pontuais
    for job in [j for j in trabalhos if j["camada"] != "trecho"]:
        dest = camadas[job["camada"]]
        campos = campos_do(dest)
        numericos = {f.name() for f in dest.fields() if f.isNumeric()}
        inteiros = {f.name() for f in dest.fields() if f.typeName().lower().startswith("int")}
        origem = job["origem"]
        ct = QgsCoordinateTransform(origem.crs(), dest.crs(), QgsProject.instance())
        req = QgsFeatureRequest()
        cols = [c for c in set(job["mapa"].values()) if c]
        req.setSubsetOfAttributes(cols, origem.fields())
        feats = origem.getSelectedFeatures(req) if job.get("so_sel") else origem.getFeatures(req)
        total = origem.selectedFeatureCount() if job.get("so_sel") else origem.featureCount()
        for k, fo in enumerate(feats):
            if fo.id() in job.get("pular", ()):  # já atualizado (sincronizar)
                continue
            if k % 500 == 0:
                passo(f"Lendo {job['nome']} ({k} de {total})…", k, total)
            if not fo.hasGeometry() or fo.geometry().isEmpty():
                sem_geom += 1
                continue
            g = QgsGeometry(fo.geometry())
            g.transform(ct)
            vals = _atributos(campos, numericos, inteiros, fo, job["mapa"], job["fixos"], job["traducoes"],
                              job.get("fixos_tipo", {}))
            if g.type() == QgsWkbTypes.GeometryType.PolygonGeometry:
                partes = [_ponto_estacao(g, nos_em, tubos_em)]
            else:
                partes = _partes(g, False)
            for p in partes:
                f = QgsFeature(dest.fields())
                f.setGeometry(QgsGeometry.fromPointXY(p))
                for campo, valor in {**PADROES.get(job["camada"], {}), **vals}.items():
                    if f.fields().indexOf(campo) >= 0:
                        f[campo] = valor
                cod, rep = codigos.usar(job["camada"], None if _vazio(f["id"]) else str(f["id"]))
                repetidos += rep
                f["id"] = cod
                if _vazio(f["situacao"]):
                    f["situacao"] = situacao
                # elemento em cima de um nó existente: o nó sai e as tubulações ligam no elemento
                if job["camada"] != "no_juncao" and opcoes.get("substituir_nos", True):
                    achado = grade.perto(p.x(), p.y(), TOL)
                    if achado and achado[2][1] == "no_juncao" and achado[2][2] == "existente":
                        substituidos[achado[2][0]] = cod
                novos_pontos[job["camada"]].append(f)
                grade.por(p.x(), p.y(), (cod, job["camada"], "novo", None))
                por_tipo[job["nome"]] += 1

    # ------------------------------------------------ 2 · tubulações
    linhas = []  # [{"pts", "vals"}]
    for job in [j for j in trabalhos if j["camada"] == "trecho"]:
        dest = tr
        campos = campos_do(dest)
        numericos = {f.name() for f in dest.fields() if f.isNumeric()}
        inteiros = {f.name() for f in dest.fields() if f.typeName().lower().startswith("int")}
        origem = job["origem"]
        ct = QgsCoordinateTransform(origem.crs(), dest.crs(), QgsProject.instance())
        req = QgsFeatureRequest()
        req.setSubsetOfAttributes([c for c in set(job["mapa"].values()) if c], origem.fields())
        feats = origem.getSelectedFeatures(req) if job.get("so_sel") else origem.getFeatures(req)
        total = origem.selectedFeatureCount() if job.get("so_sel") else origem.featureCount()
        for k, fo in enumerate(feats):
            if fo.id() in job.get("pular", ()):  # já atualizado (sincronizar)
                continue
            if k % 500 == 0:
                passo(f"Lendo {job['nome']} ({k} de {total})…", k, total)
            if not fo.hasGeometry() or fo.geometry().isEmpty():
                sem_geom += 1
                continue
            g = QgsGeometry(fo.geometry())
            g.transform(ct)
            vals = _atributos(campos, numericos, inteiros, fo, job["mapa"], job["fixos"], job["traducoes"],
                              job.get("fixos_tipo", {}))
            for pts in _partes(g, True):
                linhas.append({"pts": pts, "vals": vals})
                por_tipo[job["nome"]] += 1

    nos_criados = ligados = divididas = 0
    pecas = []
    if linhas:
        # ---- 2a · pontas: agrupa as próximas (grade + união de conjuntos)
        passo(f"Ligando as pontas de {len(linhas)} tubulações…")
        pontas = []
        for i, l in enumerate(linhas):
            pontas += [(i, 0, l["pts"][0]), (i, -1, l["pts"][-1])]
        pai = list(range(len(pontas)))

        def raiz(k):
            while pai[k] != k:
                pai[k] = pai[pai[k]]
                k = pai[k]
            return k
        g_pontas = Grade(tol)
        for k, (_, _, p) in enumerate(pontas):
            if k % 5000 == 0:
                passo(f"Agrupando as pontas ({k} de {len(pontas)})…", k, len(pontas))
            n = int(math.ceil(tol / g_pontas.cel))
            cx, cy = g_pontas._c(p.x(), p.y())
            for a in range(cx - n, cx + n + 1):
                for b in range(cy - n, cy + n + 1):
                    for px, py, j in g_pontas.g.get((a, b), ()):
                        if math.hypot(px - p.x(), py - p.y()) <= tol:
                            pai[raiz(j)] = raiz(k)
            g_pontas.por(p.x(), p.y(), k)
        grupos = defaultdict(list)
        for k in range(len(pontas)):
            grupos[raiz(k)].append(k)
        codigo_ponta, pos_codigo = {}, {}
        nos_ponta = []  # (código, ponto, novo?)
        for n_g, membros in enumerate(grupos.values()):
            if n_g % 3000 == 0:
                passo(f"Criando os nós ({n_g} de {len(grupos)})…", n_g, len(grupos))
            xs = [pontas[k][2] for k in membros]
            centro = QgsPointXY(sum(p.x() for p in xs) / len(xs), sum(p.y() for p in xs) / len(xs))
            achado = grade.perto(centro.x(), centro.y())
            if achado:
                cod, alvo = achado[2][0], QgsPointXY(achado[0], achado[1])
                cod = substituidos.get(cod, cod)
                ligados += 1
                novo = False
            elif opcoes.get("criar_nos", True):
                alvo = xs[0] if len(xs) == 1 else centro
                cod = novo_no(alvo)
                nos_criados += 1
                novo = True
            else:
                continue
            pos_codigo[cod] = alvo
            nos_ponta.append((cod, alvo, novo))
            for k in membros:
                codigo_ponta[(pontas[k][0], pontas[k][1])] = cod

        # ---- 2b · cortes: ponta em "T" e elemento pontual no meio de uma tubulação
        passo("Procurando ligações em T e elementos sobre as tubulações…")
        idx = QgsSpatialIndex()
        for i, l in enumerate(linhas):
            xs = [p.x() for p in l["pts"]]
            ys = [p.y() for p in l["pts"]]
            idx.addFeature(i, QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
        geos = {}
        cortes = defaultdict(list)
        candidatos = []
        if opcoes.get("dividir_t", True):
            candidatos += [(c, p) for c, p, _ in nos_ponta]
        if opcoes.get("dividir_tubos", True):
            for camada, fs in novos_pontos.items():
                candidatos += [(str(f["id"]), f.geometry().asPoint()) for f in fs]
            candidatos += [(c, p) for c, (p, _, _) in pos_existente.items() if c not in substituidos]
        for n_c, (cod, p) in enumerate(candidatos):
            if n_c % 2000 == 0:
                passo(f"Procurando ligações ({n_c} de {len(candidatos)})…", n_c, len(candidatos))
            caixa = QgsRectangle(p.x() - tol, p.y() - tol, p.x() + tol, p.y() + tol)
            for i in idx.intersects(caixa):
                l = linhas[i]
                if codigo_ponta.get((i, 0)) == cod or codigo_ponta.get((i, -1)) == cod:
                    continue
                g = geos.get(i)
                if g is None:
                    g = geos[i] = QgsGeometry.fromPolylineXY(l["pts"])
                gp = QgsGeometry.fromPointXY(QgsPointXY(p))
                if g.distance(gp) > tol:
                    continue
                d = g.lineLocatePoint(gp)
                if tol < d < g.length() - tol:
                    cortes[i].append((d, QgsPointXY(p), cod))

        # ---- 2c · pedaços finais com nó inicial e final
        passo("Montando as tubulações…")
        for i, l in enumerate(linhas):
            ini, fim = codigo_ponta.get((i, 0)), codigo_ponta.get((i, -1))
            pts = list(l["pts"])
            if ini in pos_codigo:
                pts[0] = pos_codigo[ini]
            if fim in pos_codigo:
                pts[-1] = pos_codigo[fim]
            vistos = set()
            cs = []
            for d, p, cod in sorted(cortes.get(i, []), key=lambda c: c[0]):
                if cod not in vistos:
                    vistos.add(cod)
                    cs.append((d, p, cod))
            partes = _cortar(pts, cs) if cs else [(pts, None, None)]
            divididas += len(partes) - 1
            for k, (pp, a, b) in enumerate(partes):
                if len(pp) < 2:
                    continue
                a = a or (ini if k == 0 else None)
                b = b or (fim if k == len(partes) - 1 else None)
                pecas.append((pp, a, b, l["vals"], k))

        # ---- 2c' · válvula/bomba importada precisa de 1 tubulação chegando e 1 saindo: no shapefile as duas
        # linhas costumam vir desenhadas no mesmo sentido; inverte uma e avisa (o sentido define montante)
        dispositivos = {str(f["id"]) for c in ("valvula", "bomba") for f in novos_pontos.get(c, [])}
        inc = defaultdict(list)
        for n, (pp, a, b, vals, k) in enumerate(pecas):
            inc[a].append((n, "a"))
            inc[b].append((n, "b"))
        invertidos = []
        for cod in dispositivos:
            lst = inc.get(cod, [])
            if len(lst) == 2 and lst[0][1] == lst[1][1]:
                n = lst[0][0]
                pp, a, b, vals, k = pecas[n]
                pecas[n] = (pp[::-1], b, a, vals, k)
                invertidos.append(cod)
        if invertidos:
            avisos.append(f"{len(invertidos)} válvula(s)/bomba(s) tinham as duas tubulações no mesmo sentido: uma foi "
                          f"invertida para haver montante e jusante. Confira o sentido em: {', '.join(sorted(invertidos)[:10])}")

    # ---- 2d · pontas novas que caem no meio de tubulações que JÁ existiam: divide a existente
    a_dividir = []
    if opcoes.get("dividir_t", True) and linhas:
        for cod, p, novo in nos_ponta:
            if not novo:
                continue
            caixa = QgsRectangle(p.x() - tol, p.y() - tol, p.x() + tol, p.y() + tol)
            for fid in idx_exist.intersects(caixa):
                g = geo_exist[fid]
                gp = QgsGeometry.fromPointXY(p)
                if g.distance(gp) <= tol:
                    d = g.lineLocatePoint(gp)
                    if tol < d < g.length() - tol:
                        a_dividir.append((fid, p, cod))

    # ---- 2e · cota do terreno (fonte do TRex) dos elementos sem cota, em lote: a região da rede é lida uma vez
    # (pedir ponto a ponto recarregava as curvas de nível a cada nó e congelava o programa)
    sem_cota = [f for fs in list(novos_pontos.values()) + [novos_nos] for f in fs
                if f.fields().indexOf("cota") >= 0 and _vazio(f["cota"])]
    if sem_cota and topo.mdt is not None:
        fonte = topo.mdt
        try:
            from gwater.cotas import Fonte
            if isinstance(fonte, Fonte) and fonte.valida():
                xs = [f.geometry().asPoint().x() for f in sem_cota]
                ys = [f.geometry().asPoint().y() for f in sem_cota]
                passo("Lendo a fonte de cotas na região da rede…")
                fonte.preparar(QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
            for n_f, f in enumerate(sem_cota):
                if n_f % 200 == 0:
                    passo(f"Cota do terreno ({n_f} de {len(sem_cota)})…", n_f, len(sem_cota))
                f["cota"] = topo.cota_mdt(f.geometry().asPoint())
        except Cancelado:
            raise
        except Exception as e:  # sem cota não impede a importação; o TRex completa depois
            avisos.append(f"cota automática não aplicada ({e}); use Ferramentas › TRex")

    # ------------------------------------------------ 3 · gravação em lote
    passo("Gravando no cadastro…")
    canvas = nucleo.iface.mapCanvas()
    canvas.freeze(True)
    topo.ocupado = True
    resultado = 0
    try:
        for lyr in camadas.values():
            if not lyr.isEditable():
                lyr.startEditing()
        for camada, fs in list(novos_pontos.items()) + [("no_juncao", novos_nos)]:
            if not fs:
                continue
            lyr = camadas[camada]
            lyr.beginEditCommand("ModelBuilder")
            lyr.addFeatures(fs)
            lyr.endEditCommand()
            resultado += len(fs)
        if pecas:
            campos = campos_do(tr)
            fs = []
            for n, (pp, a, b, vals, k) in enumerate(pecas):
                if n % 2000 == 0:
                    passo(f"Gravando as tubulações ({n} de {len(pecas)})…", n, len(pecas))
                f = QgsFeature(tr.fields())
                g = QgsGeometry.fromPolylineXY(pp)
                f.setGeometry(g)
                for campo, valor in {**PADROES["trecho"], **vals}.items():
                    if campo in campos or campo in ("status",):
                        f[campo] = valor
                cod_arq = None if (_vazio(vals.get("id")) or k > 0) else str(vals["id"])
                cod, rep = codigos.usar("trecho", cod_arq)
                repetidos += rep and k == 0
                f["id"] = cod
                f["no_inicial"], f["no_final"] = a, b
                f["comprimento"] = round(g.length(), 2)
                if _vazio(f["situacao"]):
                    f["situacao"] = situacao
                if _vazio(f["rugosidade_hw"]) and not _vazio(f["material"]):
                    f["rugosidade_hw"] = rug.get(f["material"])
                fs.append(f)
            tr.beginEditCommand("ModelBuilder")
            tr.addFeatures(fs)
            tr.endEditCommand()
            resultado += len(fs)
        # nós existentes substituídos por elementos importados
        if substituidos:
            nos = camadas["no_juncao"]
            nos.beginEditCommand("ModelBuilder: substituir nós")
            for antigo, novo in substituidos.items():
                topo.religar(antigo, novo)
            nos.deleteFeatures([pos_existente[c][2] for c in substituidos if c in pos_existente])
            nos.endEditCommand()
            avisos.append(f"{len(substituidos)} nó(s) no mesmo lugar dos elementos importados foram substituídos por eles")
        # pontas novas no meio de tubulações existentes
        if a_dividir:
            tr.beginEditCommand("ModelBuilder: dividir existentes")
            for fid, p, cod in a_dividir:
                f = tr.getFeature(fid)
                if not f.isValid():
                    continue
                d2, _, depois, _ = f.geometry().closestSegmentWithContext(p)
                if topo.dividir(f, depois, p, cod) is not None:
                    divididas += 1
            tr.endEditCommand()
    finally:
        topo.ocupado = False
        canvas.freeze(False)
        canvas.refresh()
    if repetidos:
        avisos.append(f"{repetidos} código(s) do arquivo já existiam no cadastro: receberam código novo")
    if sem_geom:
        avisos.append(f"{sem_geom} feição(ões) sem geometria foram ignoradas")
    soltas = sum(1 for _, a, b, _, _ in pecas if not a or not b)
    if soltas:
        avisos.append(f"{soltas} tubulação(ões) ficaram com ponta sem nó (criar nós desligado)")
    return {"importados": sum(por_tipo.values()), "por_tipo": dict(por_tipo), "gravados": resultado,
            "nos_criados": nos_criados, "ligados_existentes": ligados, "divididas": divididas,
            "avisos": avisos}
