"""Desempenho: quantos núcleos do processador e quanta memória RAM o GWATER usa (Configurações).

  núcleos       o mapa desenha as camadas em paralelo (uma por núcleo), o QGIS usa esse tanto de threads e o motor
                divide as análises de muitos cálculos (incêndio, descarga, criticidade, calibração) entre eles
  memória       cache do GDAL (leitura de rasters e GeoPackage), do SQLite dos cadastros e das imagens dos mapas de
                fundo baixados da internet; mais memória = menos leitura de disco e de rede
"""
import ctypes
import os

from qgis.PyQt.QtCore import QSettings

CHAVE = ("GWATER", "GWATER")


def configuracoes():
    """As configurações do GWATER: no registro do Windows (instalado) ou na pasta dados/config (versão portátil, vão junto
    no pen drive). Todo o programa lê e grava por aqui (o QSettings com o nome do programa ignora o formato padrão)."""
    if os.environ.get("GWATER_DADOS"):
        return QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, *CHAVE)
    return QSettings(*CHAVE)


def nucleos_maquina():
    return os.cpu_count() or 1


def memoria_total_mb():
    """RAM física do computador (MB)."""
    try:
        class Estado(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        e = Estado()
        e.dwLength = ctypes.sizeof(Estado)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e))
        return int(e.ullTotalPhys / 2 ** 20)
    except Exception:  # fora do Windows
        try:
            return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 20)
        except (ValueError, OSError, AttributeError):
            return 8192


def padrao_cache_mb():
    """Padrão: 1/8 da RAM, entre 512 MB e 8 GB."""
    return int(min(8192, max(512, memoria_total_mb() // 8)))


def ler():
    s = configuracoes()
    n = int(s.value("desempenho/nucleos", 0) or 0)
    return {"nucleos": max(1, min(n or nucleos_maquina(), nucleos_maquina())),
            "cache_mb": int(s.value("desempenho/cache_mb", 0) or 0) or padrao_cache_mb(),
            "mapa_paralelo": str(s.value("desempenho/mapa_paralelo", "true")).lower() in ("true", "1"),
            "auto_min": int(s.value("salvar/auto_min", 5) or 0),
            "fluxo_fps": int(s.value("fluxo/fps", 15) or 15)}


def gravar(nucleos, cache_mb, mapa_paralelo, auto_min=None, fluxo_fps=None):
    s = configuracoes()
    if fluxo_fps is not None:
        s.setValue("fluxo/fps", int(fluxo_fps))
    if auto_min is not None:
        s.setValue("salvar/auto_min", int(auto_min))
    s.setValue("desempenho/nucleos", int(nucleos))
    s.setValue("desempenho/cache_mb", int(cache_mb))
    s.setValue("desempenho/mapa_paralelo", bool(mapa_paralelo))


def ambiente_antes_do_qgis():
    """Variáveis que o GDAL e as bibliotecas numéricas só leem ao iniciar (chamar antes do QgsApplication)."""
    cfg = ler()
    n, mb = str(cfg["nucleos"]), cfg["cache_mb"]
    os.environ["GWATER_NUCLEOS"] = n  # o motor (outro processo) herda e divide as análises por este tanto
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_MAX_THREADS"):
        os.environ[v] = n
    os.environ["GDAL_NUM_THREADS"] = "ALL_CPUS" if cfg["nucleos"] >= nucleos_maquina() else n
    os.environ["GDAL_CACHEMAX"] = str(int(mb * 0.5))         # metade do cache: blocos do GDAL
    os.environ["OGR_SQLITE_CACHE"] = str(int(mb * 0.25))     # um quarto: páginas do SQLite (GeoPackage)
    os.environ.setdefault("OGR_SQLITE_SYNCHRONOUS", "OFF")


def aplicar(janela=None):
    """Aplica as configurações no programa em execução (núcleos, cache e o mapa)."""
    cfg = ler()
    n, mb = cfg["nucleos"], cfg["cache_mb"]
    os.environ["GWATER_NUCLEOS"] = str(n)
    try:
        from qgis.core import QgsApplication
        QgsApplication.setMaxThreads(n)
    except Exception:
        pass
    try:
        from qgis.PyQt.QtCore import QThreadPool
        QThreadPool.globalInstance().setMaxThreadCount(n)
    except Exception:
        pass
    try:
        from osgeo import gdal
        gdal.SetCacheMax(int(mb * 0.5) * 2 ** 20)
        gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS" if n >= nucleos_maquina() else str(n))
        gdal.SetConfigOption("OGR_SQLITE_CACHE", str(int(mb * 0.25)))
    except Exception:
        pass
    try:  # cache em disco das imagens dos mapas de fundo (um quarto do valor, em disco)
        from qgis.core import QgsNetworkAccessManager
        cache = QgsNetworkAccessManager.instance().cache()
        if cache is not None and hasattr(cache, "setMaximumCacheSize"):
            cache.setMaximumCacheSize(int(mb * 0.25) * 2 ** 20)
    except Exception:
        pass
    try:
        from qgis.PyQt.QtGui import QPixmapCache
        QPixmapCache.setCacheLimit(min(int(mb * 0.05), 1024) * 1024)  # KB: ícones e símbolos já desenhados
    except Exception:
        pass
    if janela is not None and getattr(janela, "canvas", None) is not None:
        c = janela.canvas
        c.setParallelRenderingEnabled(cfg["mapa_paralelo"] and n > 1)  # cada camada num núcleo
        c.setCachingEnabled(True)  # camadas que não mudaram não são redesenhadas
        c.setMapUpdateInterval(250)  # mostra o desenho em andamento a cada 250 ms
    return cfg


def camadas(nucleo):
    """Camadas do cadastro mais leves de desenhar: geometria simplificada abaixo de 1 pixel (o cadastro não muda)."""
    try:
        from qgis.core import QgsVectorSimplifyMethod
    except ImportError:
        return
    for lyr in nucleo.camadas_rede():
        m = QgsVectorSimplifyMethod()
        m.setSimplifyHints(QgsVectorSimplifyMethod.SimplifyHint.GeometrySimplification)
        m.setSimplifyAlgorithm(QgsVectorSimplifyMethod.SimplifyAlgorithm.Distance)
        m.setThreshold(1.0)
        m.setForceLocalOptimization(True)
        lyr.setSimplifyMethod(m)
