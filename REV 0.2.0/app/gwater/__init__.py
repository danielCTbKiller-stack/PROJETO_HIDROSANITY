def classFactory(iface):
    from .plugin import GwaterPlugin
    return GwaterPlugin(iface)
