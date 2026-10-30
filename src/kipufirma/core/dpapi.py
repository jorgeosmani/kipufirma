"""Protección de datos con DPAPI de Windows (CryptProtectData), ligada a la
cuenta del usuario. Solo se usa para la contraseña OPCIONAL del servidor de
sello de tiempo. La contraseña del certificado .p12 JAMÁS se persiste.
En otros sistemas operativos no se guarda nada (se pedirá cada vez)."""
from __future__ import annotations

import base64
import sys

AVAILABLE = sys.platform == "win32"

if AVAILABLE:  # pragma: no cover - solo Windows
    import ctypes
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.windll.crypt32
    _kernel32 = ctypes.windll.kernel32
    _ENTROPY = b"KipuFirma-TSA-v1"

    def _blob(data: bytes) -> _BLOB:
        buf = ctypes.create_string_buffer(data, len(data))
        return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _call(fn, data: bytes) -> bytes:
        out = _BLOB()
        if not fn(ctypes.byref(_blob(data)), None, ctypes.byref(_blob(_ENTROPY)), None, None, 0x1,
                  ctypes.byref(out)):
            raise OSError("DPAPI falló")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(out.pbData)

    def protect(text: str) -> str:
        return base64.b64encode(_call(_crypt32.CryptProtectData, text.encode())).decode()

    def unprotect(token: str) -> str:
        return _call(_crypt32.CryptUnprotectData, base64.b64decode(token)).decode()
else:
    def protect(text: str) -> str:
        return ""

    def unprotect(token: str) -> str:
        return ""
