"""Cotas do terreno, como o TRex do WaterGEMS: de raster, curvas de nível ou pontos cotados.

- Raster (MDT/MDE): valor da célula sob o elemento.
- Curvas de nível (linhas, shp/gpkg): interpolação linear entre a curva mais próxima e a curva
  mais próxima com outra cota: z = z1 + (z2 − z1) · d1 / (d1 + d2).
- Pontos cotados: o ponto que coincide, ou média ponderada pelo inverso do quadrado da distância
  dos pontos mais próximos (até 6).
Não há raio de busca: todo elemento recebe a cota da curva (ou dos pontos) mais próxima, a qualquer distância.

Arquivos grandes (curvas de um estado inteiro) não são carregados por inteiro: só entram as
feições da região da rede, lidas pelo índice espacial do próprio arquivo, e as distâncias são
medidas em metros, no sistema do cadastro, mesmo que o arquivo esteja em graus.
"""
import re
import unicodedata

from qgis.core import (
    QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, QgsPointXY, QgsProject,
    QgsRasterLayer, QgsRectangle, QgsSpatialIndex, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

CAMPO = "cota"  # cota do terreno: o mesmo campo em todo elemento pontual do cadastro
ELEMENTOS = [("no_juncao", "Nós / junções"), ("valvula", "Válvulas"), ("bomba", "Bombas"),
             ("reservatorio", "Reservatórios"), ("captacao", "Captações")]
TIPOS = {"raster": "Raster (MDT / MDE)", "curvas": "Curvas de nível (linhas)", "pontos": "Pontos cotados"}
NOMES_COTA = ["cota", "cotas", "elev", "elevacao", "elevation", "z", "altitude", "alt", "contour", "curva",
              "curva_nivel", "cote", "height", "altura", "cota_m", "elev_m", "nivel", "valor", "quota"]


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def campo_cota(camada):
    """Campo numérico com cara de cota (ou None)."""
    numericos = [f.name() for f in camada.fields() if f.isNumeric()]
    por_nome = {_norm(n): n for n in numericos}
    for cand in NOMES_COTA:
        if cand in por_nome:
            return por_nome[cand]
    for n in numericos:
        if any(c in _norm(n) for c in ("cota", "elev", "alt", "contour", "curva")):
            return n
    return None


def tem_z(camada):
    from qgis.core import QgsWkbTypes
    return QgsWkbTypes.hasZ(camada.wkbType())


def _numero(v):
    if v is None or str(v) in ("", "NULL"):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


class Fonte:
    """Uma fonte de cota. `cota(p)` recebe um ponto no sistema do cadastro e devolve metros (ou None).

    Sem raio de busca: vale sempre a curva (ou os pontos) mais próxima, a qualquer distância. Para não ler o
    arquivo inteiro, só a região da rede entra no índice; se o mais próximo pode estar fora dela, a região cresce.
    """

    def __init__(self, tipo, camada, crs_cadastro, campo=None, usar_z=False):
        self.tipo, self.camada, self.campo = tipo, camada, campo
        self.usar_z = usar_z
        self.crs = crs_cadastro
        self.area = None  # região já carregada no índice (sistema do cadastro)
        self.completo = False  # a região já cobre o arquivo inteiro
        self.indice, self.geoms, self.valores = None, {}, {}
        prj = QgsProject.instance()
        self.para_fonte = QgsCoordinateTransform(crs_cadastro, camada.crs(), prj)
        self.da_fonte = QgsCoordinateTransform(camada.crs(), crs_cadastro, prj)

    def nome(self):
        extra = "" if self.tipo == "raster" else (" · Z da geometria" if self.usar_z else f" · campo {self.campo}")
        return f"{self.camada.name()} ({TIPOS[self.tipo].split(' (')[0].lower()}{extra})"

    def valida(self):
        try:
            return self.camada is not None and self.camada.isValid()
        except RuntimeError:  # camada removida
            return False

    # ------------------------------------------------ índice da região
    def preparar(self, area):
        """Carrega as feições da área (sistema do cadastro), com folga."""
        if self.tipo == "raster":
            return
        a = QgsRectangle(area)
        a.grow(max(500.0, 0.1 * max(a.width(), a.height())))
        if self.area is not None:
            if self.area.contains(a):
                return
            a.combineExtentWith(self.area)
        self._carregar(a)

    def _carregar(self, a):
        self.area = a
        try:
            self.completo = a.contains(self.da_fonte.transformBoundingBox(self.camada.extent()))
        except Exception:  # extensão que não se transforma: lê o arquivo todo de uma vez
            self.completo = True
        self.indice = QgsSpatialIndex(QgsSpatialIndex.Flag.FlagStoreFeatureGeometries)
        self.geoms, self.valores = {}, {}
        req = QgsFeatureRequest()
        if not self.completo:
            req.setFilterRect(self.para_fonte.transformBoundingBox(a))
        if not self.usar_z and self.campo:
            req.setSubsetOfAttributes([self.campo], self.camada.fields())
        for f in self.camada.getFeatures(req):
            if not f.hasGeometry():
                continue
            v = self._valor(f)
            if v is None:
                continue
            g = QgsGeometry(f.geometry())
            g.transform(self.da_fonte)
            nf = QgsFeature(f.id())
            nf.setGeometry(g)
            self.indice.addFeature(nf)
            self.geoms[f.id()], self.valores[f.id()] = g, v

    def _ampliar(self):
        a = QgsRectangle(self.area)
        a.grow(max(a.width(), a.height(), 1000.0))
        self._carregar(a)

    def _valor(self, f):
        if self.usar_z:
            try:
                return float(next(f.geometry().vertices()).z())
            except (StopIteration, ValueError):
                return None
        return _numero(f[self.campo])

    def _vizinhos(self, p, n):
        """[(distância, valor)] dos n mais próximos, ordenados."""
        gp = QgsGeometry.fromPointXY(p)
        return sorted((self.geoms[fid].distance(gp), self.valores[fid]) for fid in self.indice.nearestNeighbor(p, n))

    def _busca(self, p, n, basta):
        """Vizinhos garantidamente mais próximos: a distância que `basta` devolve tem de ser menor que a da borda
        da região carregada (senão algo fora dela poderia estar mais perto); se não for, amplia a região."""
        if self.area is None or not self.area.contains(p):
            self.preparar(QgsRectangle(p.x(), p.y(), p.x(), p.y()))
        while True:
            viz = self._vizinhos(p, n)
            borda = min(p.x() - self.area.xMinimum(), self.area.xMaximum() - p.x(),
                        p.y() - self.area.yMinimum(), self.area.yMaximum() - p.y())
            d = basta(viz)
            if self.completo or (d is not None and d <= borda):
                return viz
            self._ampliar()

    # ------------------------------------------------ cota
    def cota(self, p):
        p = QgsPointXY(p)
        if self.tipo == "raster":
            v, ok = self.camada.dataProvider().sample(self.para_fonte.transform(p), 1)
            return round(float(v), 2) if ok else None
        if self.tipo == "curvas":
            def outra_curva(viz):  # distância da curva mais próxima com outra cota (a 2ª da interpolação)
                return next((d for d, z in viz[1:] if abs(z - viz[0][1]) > 1e-6), None) if viz else None
            viz = []
            for n in (16, 64, 256):  # uma curva pode vir partida em muitas feições com a mesma cota
                # basta: a 2ª curva achada; ou, se as n mais próximas têm todas a mesma cota, a n-ésima (e aí
                # o laço pede mais vizinhos); com menos de n na região, falta área: amplia
                viz = self._busca(p, n, lambda v: outra_curva(v) if outra_curva(v) is not None else
                                  (v[-1][0] if len(v) == n else None))
                if outra_curva(viz) is not None or len(viz) < n:
                    break
            if not viz:
                return None
            d1, z1 = viz[0]
            outra = next(((d, z) for d, z in viz[1:] if abs(z - z1) > 1e-6), None)
            if d1 < 1e-6 or outra is None:
                return round(z1, 2)
            d2, z2 = outra
            return round(z1 + (z2 - z1) * d1 / (d1 + d2), 2)
        viz = self._busca(p, 6, lambda v: v[-1][0] if len(v) == 6 else None)  # pontos cotados
        if not viz:
            return None
        if viz[0][0] < 0.01:
            return round(viz[0][1], 2)
        pesos = [(1 / d ** 2, z) for d, z in viz]
        return round(sum(w * z for w, z in pesos) / sum(w for w, _ in pesos), 2)


def _xy(g):
    """Ponto de um elemento (Point ou MultiPoint)."""
    return QgsPointXY(g.vertexAt(0))


def abrir_arquivo(caminho, subcamada=None):
    """Camada (vetorial ou raster) de um arquivo, sem pôr no projeto (arquivos grandes deixariam o mapa lento)."""
    if caminho.lower().endswith((".tif", ".tiff", ".asc", ".img", ".vrt", ".dem", ".adf", ".jp2")):
        lyr = QgsRasterLayer(caminho, caminho.replace("\\", "/").split("/")[-1])
    else:
        uri = caminho + (f"|layername={subcamada}" if subcamada else "")
        lyr = QgsVectorLayer(uri, subcamada or caminho.replace("\\", "/").split("/")[-1], "ogr")
    return lyr if lyr.isValid() else None


def subcamadas(caminho):
    """Nomes das camadas dentro de um GeoPackage (ou [] para arquivo de uma camada só)."""
    if not caminho.lower().endswith((".gpkg", ".sqlite")):
        return []
    try:
        from qgis.core import QgsProviderRegistry
        return [s.name() for s in QgsProviderRegistry.instance().querySublayers(caminho)]
    except AttributeError:  # QGIS < 3.22
        lyr = QgsVectorLayer(caminho, "x", "ogr")
        return [s.split("!!::!!")[1] for s in lyr.dataProvider().subLayers()] if lyr.isValid() else []


def garantir_campo(lyr):
    """Cria o campo `cota` (cota do terreno) na camada, se ainda não existir (cadastros antigos). Fica no buffer."""
    if lyr.fields().indexOf(CAMPO) >= 0:
        return False
    if not lyr.isEditable():
        lyr.startEditing()
    lyr.addAttribute(QgsField(CAMPO, QVariant.Double))
    return True


def preencher(plugin, fonte, todas, camadas=None, so_selecionados=False):
    """Preenche o campo `cota` (cota do terreno) pela fonte.

    camadas: nomes das camadas (padrão: todos os elementos pontuais do cadastro abertos no projeto);
    so_selecionados: só as feições selecionadas. Devolve (preenchidos, sem cota: códigos). Fica no buffer de edição."""
    lyrs = []
    for n in camadas or [c for c, _ in ELEMENTOS]:
        try:
            lyrs.append(plugin.camada(n))
        except LookupError:  # cadastro sem essa camada no projeto
            continue
    pts = []
    for lyr in lyrs:
        feats = lyr.getSelectedFeatures() if so_selecionados else lyr.getFeatures()
        pts += [(lyr, f) for f in feats if f.hasGeometry() and not f.geometry().isEmpty()]
    if not pts:
        return 0, []
    xs = [_xy(f.geometry()).x() for _, f in pts]
    ys = [_xy(f.geometry()).y() for _, f in pts]
    fonte.preparar(QgsRectangle(min(xs), min(ys), max(xs), max(ys)))
    feitos, fora = 0, []
    for lyr in lyrs:
        garantir_campo(lyr)
    for lyr, f in pts:
        idx = lyr.fields().indexOf(CAMPO)
        atual = lyr.getFeature(f.id())[CAMPO] if idx >= 0 else None
        if not todas and _numero(atual) is not None:
            continue
        v = fonte.cota(_xy(f.geometry()))
        if v is None:
            fora.append(str(f["id"]) if lyr.fields().indexOf("id") >= 0 else str(f.id()))
            continue
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.changeAttributeValue(f.id(), idx, v)
        feitos += 1
    return feitos, fora
