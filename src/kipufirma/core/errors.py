"""Jerarquía de errores con mensajes pensados para el usuario final."""
from __future__ import annotations


class KipuError(Exception):
    """Error base. ``str(e)`` siempre es un mensaje en español apto para mostrar."""


class CertificateError(KipuError):
    pass


class WrongPasswordError(CertificateError):
    def __init__(self) -> None:
        super().__init__("La contraseña del certificado es incorrecta.")


class CertificateFileError(CertificateError):
    pass


class CertificateNotUsableError(CertificateError):
    """Caducado, aún no vigente, revocado, sin uso de firma, etc."""


class TooManyAttemptsError(CertificateError):
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        super().__init__(
            f"Demasiados intentos fallidos. Espere {seconds} segundos antes de volver a intentar."
        )


class DocumentError(KipuError):
    pass


class EncryptedDocumentError(DocumentError):
    def __init__(self) -> None:
        super().__init__("El documento está protegido con contraseña; quite la protección antes de firmar.")


class SuspiciousDocumentError(DocumentError):
    pass


class LockedDocumentError(DocumentError):
    def __init__(self) -> None:
        super().__init__(
            "El documento tiene una firma de certificación que no permite más cambios ni firmas."
        )


class PlacementError(DocumentError):
    pass


class KeywordNotFoundError(PlacementError):
    def __init__(self, keywords: list[str]) -> None:
        joined = ", ".join(f"«{k}»" for k in keywords)
        super().__init__(f"No se encontró ninguna de las palabras clave: {joined}.")


class SigningError(KipuError):
    pass


class CancelledError(KipuError):
    def __init__(self) -> None:
        super().__init__("Operación cancelada por el usuario.")
