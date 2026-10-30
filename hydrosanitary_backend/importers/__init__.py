import os

from importers.config import ImportConfig
from importers.network_builder import ImportResult


def import_project(path: str, config: ImportConfig = None) -> ImportResult:
    """Importa um projeto pela extensão do arquivo (.dxf, .ifc)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".dxf":
        from importers.dxf_importer import import_dxf
        return import_dxf(path, config)
    if ext == ".ifc":
        from importers.ifc_importer import import_ifc
        return import_ifc(path, config)
    if ext == ".dwg":
        raise NotImplementedError("DWG ainda não é suportado: converta para DXF (ex.: ODA File Converter).")
    raise ValueError(f"Formato '{ext}' não suportado. Use .dxf ou .ifc.")
