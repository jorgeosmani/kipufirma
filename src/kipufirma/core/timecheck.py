"""Verificación del reloj del equipo.

La fecha que aparece en la firma la pone el equipo. Si el reloj está mal,
la firma queda con una fecha incorrecta (FirmaEC lo evita pidiendo la hora
a su servidor). Aquí comparamos el reloj local con la cabecera HTTP
``Date`` de un servidor público confiable y avisamos si hay desfase.
Para una fecha con valor probatorio fuerte, configure un sello de tiempo
(TSA) en Ajustes.
"""
from __future__ import annotations

import email.utils
import urllib.request
from datetime import datetime, timezone

DEFAULT_TIME_URL = "https://www.firmadigital.gob.ec/"
MAX_SKEW_SECONDS = 120


def clock_skew_seconds(url: str = DEFAULT_TIME_URL, timeout: float = 6.0) -> float | None:
    """Segundos (local - servidor). ``None`` si no hay red o no hay cabecera."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "KipuFirma/1.0"})  # noqa: S310 (URL fija HTTPS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            header = resp.headers.get("Date")
    except Exception:
        return None
    if not header:
        return None
    server = email.utils.parsedate_to_datetime(header)
    return (datetime.now(timezone.utc) - server).total_seconds()
