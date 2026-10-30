"""Manejo de la contraseña del certificado con el menor rastro posible.

Python no garantiza el borrado de memoria (los ``str`` son inmutables y el
recolector puede haber copiado datos). Lo que sí hacemos:

* la contraseña viaja como ``bytearray`` mutable desde la interfaz hasta la
  librería criptográfica y se sobrescribe con ceros apenas se usa;
* nunca se guarda en disco, ni en la configuración ni en los registros;
* el objeto se niega a imprimirse (``repr``/``str`` no revelan el contenido).

Ver docs/SEGURIDAD.md para el análisis completo de esta limitación.
"""
from __future__ import annotations

import ctypes


class SecretBuffer:
    __slots__ = ("_buf",)

    def __init__(self, data: bytes | bytearray | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._buf = bytearray(data)

    @classmethod
    def from_chars(cls, chars: str) -> "SecretBuffer":
        return cls(chars)

    def bytes_view(self) -> bytes:
        """Copia inmutable de corta vida para APIs que exigen ``bytes``."""
        return bytes(self._buf)

    def __len__(self) -> int:
        return len(self._buf)

    def wipe(self) -> None:
        n = len(self._buf)
        if n:
            addr = (ctypes.c_char * n).from_buffer(self._buf)
            ctypes.memset(ctypes.addressof(addr), 0, n)
            del addr
        self._buf = bytearray()

    def __enter__(self) -> "SecretBuffer":
        return self

    def __exit__(self, *exc) -> None:
        self.wipe()

    def __del__(self) -> None:
        try:
            self.wipe()
        except Exception:  # noqa: S110 (destructor: nunca debe lanzar)
            pass

    def __repr__(self) -> str:
        return "SecretBuffer(<oculto>)"

    __str__ = __repr__
