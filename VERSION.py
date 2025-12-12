"""
Version information pro TooZ Hub 2
Centralizované řízení verzí pro snadnou aktualizaci
Čte verzi ze souboru VERSION v kořenovém adresáři
"""
from pathlib import Path
from datetime import datetime

# Cesta ke kořenovému adresáři projektu
_project_root = Path(__file__).parent
_version_file = _project_root / "VERSION"

# Načtení verze ze souboru VERSION
def _read_version():
    """Načte verzi ze souboru VERSION"""
    try:
        if _version_file.exists():
            version = _version_file.read_text(encoding="utf-8").strip()
            return version
        else:
            # Fallback pokud soubor neexistuje
            return "2.1.0"
    except Exception as e:
        print(f"[VERSION] Warning: Nepodařilo se načíst verzi ze souboru VERSION: {e}")
        return "2.1.0"

# Načtení verze
__version__ = _read_version()

# Ostatní informace o verzi
__version_name__ = f"TOOZHUB{__version__.replace('.', '')}"
__build_date__ = datetime.now().strftime("%Y-%m-%d")
__update_info__ = "Kompletní redesign UI + zavedení verzování"

# Pro import
VERSION = __version__
VERSION_NAME = __version_name__
BUILD_DATE = __build_date__
UPDATE_INFO = __update_info__

