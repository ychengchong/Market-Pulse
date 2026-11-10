"""Local database settings shared by the app and command-line tools."""
import os
from pathlib import Path
import tomllib

_dll_handle = None


def local_settings():
    path = Path(".streamlit/secrets.toml")
    if not path.exists():
        return {}
    try:
        settings = tomllib.loads(path.read_text(encoding="utf-8"))
        database = settings.get("database", {})
        if not isinstance(database, dict):
            raise ValueError("Invalid database settings")
        return database
    except (OSError, ValueError):
        raise ValueError("Unable to read local database settings") from None


def connection_string():
    value = os.environ.get("DATABASE_URL") or local_settings().get("url")
    if value is not None and not isinstance(value, str):
        raise ValueError("Database connection must be a string")
    return value


def prepare_driver():
    global _dll_handle
    if _dll_handle is not None:
        return
    folder = os.environ.get("PG_LIBPQ_DIR")
    if not folder:
        folder = local_settings().get("libpq_dir")
    # The supported Windows installation also supplies a trusted libpq for
    # machines whose policy blocks the optional wheel extension.
    if not folder and os.name == "nt":
        standard = Path("C:/Program Files/PostgreSQL/18/bin")
        if (standard / "libpq.dll").exists():
            folder = str(standard)
    if folder:
        folder = str(Path(folder).resolve(strict=True))
        os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("PSYCOPG_IMPL", "python")
        if os.name == "nt":
            _dll_handle = os.add_dll_directory(folder)
