"""Registro en archivo rotativo con redacción de datos sensibles.

Ruta: ``%LOCALAPPDATA%\\KipuFirma\\logs\\kipufirma.log`` (5 × 1 MB).
Se enmascaran cédulas/RUC (10 o 13 dígitos) y cualquier valor asociado a
claves como password/contraseña/clave."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from kipufirma.paths import log_dir

_ID_RE = re.compile(r"(?<!\d)(\d{2})\d{6,9}(\d{2})(?!\d)")
_PW_RE = re.compile(r"(?i)(password|passphrase|contrase(?:ñ|n)a|clave|pin)(\s*[=:]\s*)(\S+)")


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        msg = _PW_RE.sub(r"\1\2***", msg)
        msg = _ID_RE.sub(lambda m: m.group(1) + "*" * (len(m.group(0)) - 4) + m.group(2), msg)
        record.msg, record.args = msg, ()
        return True


def setup_logging(level: int = logging.INFO, to_console: bool = False) -> None:
    root = logging.getLogger()
    if getattr(root, "_kipu_configured", False):
        return
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    fh = RotatingFileHandler(log_dir() / "kipufirma.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.addFilter(RedactingFilter())
    root.addHandler(fh)
    if to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(RedactingFilter())
        root.addHandler(ch)
    for noisy in ("pyhanko", "pyhanko_certvalidator", "fontTools", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._kipu_configured = True  # type: ignore[attr-defined]
