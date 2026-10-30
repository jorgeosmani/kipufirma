"""Ubicaciones de configuración, registros y recursos.

En Windows se usan las carpetas por usuario (``%APPDATA%`` para la
configuración, ``%LOCALAPPDATA%`` para registros), que ya están protegidas
por las ACL del perfil del usuario. Nunca se escribe junto al ejecutable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from kipufirma import APP_NAME


def _windows_dir(env: str, fallback: str) -> Path:
    base = os.environ.get(env)
    return Path(base) if base else Path.home() / fallback


def config_dir() -> Path:
    override = os.environ.get("KIPUFIRMA_CONFIG_DIR")
    if override:
        d = Path(override)
    elif sys.platform == "win32":
        d = _windows_dir("APPDATA", "AppData/Roaming") / APP_NAME
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_dir() -> Path:
    if sys.platform == "win32":
        d = _windows_dir("LOCALAPPDATA", "AppData/Local") / APP_NAME / "logs"
    else:
        d = config_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(*parts: str) -> Path:
    """Ruta a un recurso empaquetado (funciona también dentro de PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base, "kipufirma", "resources", *parts)
    return Path(__file__).resolve().parent.joinpath("resources", *parts)
