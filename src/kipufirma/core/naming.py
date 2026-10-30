"""Nombres de salida seguros y sin sobrescritura."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_stem(stem: str) -> str:
    stem = _INVALID.sub("_", stem).strip(" .") or "documento"
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    return stem[:180]


def output_path(src: Path, out_dir: Path | None, suffix: str = "-firmado") -> Path:
    """``informe.pdf`` -> ``informe-firmado.pdf`` (o ``informe-firmado (2).pdf``).
    Nunca devuelve una ruta existente ni la del original."""
    src = Path(src)
    folder = Path(out_dir) if out_dir else src.parent
    base = safe_stem(src.stem + suffix)
    candidate = folder / f"{base}.pdf"
    n = 2
    while candidate.exists() or candidate.resolve() == src.resolve():
        candidate = folder / f"{base} ({n}).pdf"
        n += 1
    return candidate


def atomic_write(path: Path, data: bytes) -> None:
    """Escribe en un temporal del mismo directorio y renombra: nunca deja un
    PDF a medio escribir si se corta la energía o falla el disco."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kipu-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            raise FileExistsError(path)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
