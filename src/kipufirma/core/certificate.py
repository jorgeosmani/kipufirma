"""Carga del archivo PKCS#12 (.p12/.pfx), inspección y validación previa a
la firma. La contraseña llega como :class:`SecretBuffer` y se borra en
cuanto la librería criptográfica terminó de usarla."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12

from kipufirma.core.ec_certs import SignerData, extract_signer_data, identify_ca
from kipufirma.core.errors import (
    CertificateFileError,
    CertificateNotUsableError,
    TooManyAttemptsError,
    WrongPasswordError,
)
from kipufirma.core.secrets import SecretBuffer
from kipufirma.core.trust import ChainResult, TrustStore, fingerprint

log = logging.getLogger(__name__)

EXPIRY_WARNING_DAYS = 30
MAX_P12_SIZE = 1024 * 1024  # 1 MiB: un .p12 real pesa unos pocos KB
CLOUD_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "icloud", "box sync", "mega")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_in_cloud_folder(path: Path) -> bool:
    """Advierte si el .p12 vive en una carpeta sincronizada con la nube:
    una copia del certificado fuera del equipo amplía la superficie de ataque."""
    low = str(path).lower()
    return any(m in low for m in CLOUD_MARKERS)


@dataclass
class CertificateInfo:
    signer: SignerData
    ca_name: str
    ca_recognized: bool
    serial_hex: str
    not_before: datetime
    not_after: datetime
    thumbprint: str
    key_usage_ok: bool
    key_usage_text: str
    subject: str
    issuer: str

    def days_left(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        return (self.not_after - now).days

    def summary(self) -> str:
        return (f"{self.signer.display_name} · {self.ca_name} · vence "
                f"{self.not_after.astimezone().strftime('%d/%m/%Y')}")


@dataclass
class Credential:
    """Clave privada + certificado, vivos solo durante un lote de firma."""
    private_key: object
    certificate: x509.Certificate
    extra_certs: list[x509.Certificate]
    info: CertificateInfo
    chain: ChainResult | None = None
    warnings: list[str] = field(default_factory=list)

    def destroy(self) -> None:
        self.private_key = None


def describe(cert: x509.Certificate) -> CertificateInfo:
    ca_name, recognized = identify_ca(cert)
    try:
        ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
        ok = bool(ku.digital_signature or ku.content_commitment)
        parts = [n for n, v in (("firma digital", ku.digital_signature),
                                ("no repudio", ku.content_commitment),
                                ("cifrado de clave", ku.key_encipherment)) if v]
        ku_text = ", ".join(parts) or "ninguno"
    except x509.ExtensionNotFound:
        ok, ku_text = True, "no especificado"
    return CertificateInfo(
        signer=extract_signer_data(cert),
        ca_name=ca_name,
        ca_recognized=recognized,
        serial_hex=format(cert.serial_number, "X"),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        thumbprint=fingerprint(cert),
        key_usage_ok=ok,
        key_usage_text=ku_text,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
    )


def _read_p12(path: Path) -> bytes:
    path = Path(path)
    if not path.is_file():
        raise CertificateFileError(f"No se encontró el archivo del certificado: {path}")
    if path.stat().st_size > MAX_P12_SIZE:
        raise CertificateFileError("El archivo seleccionado es demasiado grande para ser un certificado .p12/.pfx.")
    return path.read_bytes()


def load_credential(path: Path, password: SecretBuffer, trust: TrustStore | None = None) -> Credential:
    """Abre el .p12. Siempre borra la contraseña, haya éxito o error."""
    data = _read_p12(path)
    try:
        pw = password.bytes_view()
        try:
            bundle = pkcs12.load_pkcs12(data, pw or None)
        except ValueError as e:
            if "Invalid password" in str(e):
                raise WrongPasswordError() from None
            raise CertificateFileError(
                "El archivo no es un certificado PKCS#12 válido o está dañado.") from None
        finally:
            del pw
    finally:
        password.wipe()

    if bundle.key is None or bundle.cert is None:
        raise CertificateFileError("El archivo no contiene una clave privada con su certificado.")
    cert = bundle.cert.certificate
    extra = [c.certificate for c in bundle.additional_certs]
    info = describe(cert)
    cred = Credential(bundle.key, cert, extra, info)
    if trust is not None:
        cred.chain = trust.build_chain(cert, extra)
    return cred


def check_usable(cred: Credential, now: datetime | None = None,
                 require_trusted_chain: bool = True) -> list[str]:
    """Lanza :class:`CertificateNotUsableError` si no se debe firmar; devuelve
    advertencias no bloqueantes."""
    now = now or datetime.now(timezone.utc)
    info = cred.info
    fmt = "%d/%m/%Y %H:%M"
    if now < info.not_before:
        raise CertificateNotUsableError(
            f"El certificado aún no está vigente (válido desde {info.not_before.astimezone().strftime(fmt)}).")
    if now > info.not_after:
        raise CertificateNotUsableError(
            f"El certificado caducó el {info.not_after.astimezone().strftime(fmt)}.")
    if not info.key_usage_ok:
        raise CertificateNotUsableError(
            f"El certificado no está autorizado para firmar (uso de clave: {info.key_usage_text}).")
    warnings: list[str] = []
    if cred.chain is not None and not cred.chain.trusted:
        msg = ("El certificado no pertenece a una Entidad de Certificación reconocida en Ecuador. "
               + cred.chain.detail)
        if require_trusted_chain:
            raise CertificateNotUsableError(msg)
        warnings.append(msg)
    elif not info.ca_recognized:
        warnings.append(f"Entidad emisora no listada: {info.ca_name}.")
    days = info.days_left(now)
    if days <= EXPIRY_WARNING_DAYS:
        warnings.append(f"Su certificado vence en {days} día(s). Gestione la renovación con su entidad.")
    cred.warnings.extend(warnings)
    return warnings


class AttemptLimiter:
    """Retardo exponencial tras contraseñas incorrectas (3 intentos libres,
    luego 30 s, 60 s, 120 s... hasta 15 min). Frena el uso por terceros
    del equipo desbloqueado; no sustituye a una contraseña robusta."""

    FREE_ATTEMPTS = 3
    BASE = 30
    MAX = 15 * 60

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._failures = 0
        self._locked_until = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            remaining = int(self._locked_until - self._clock() + 0.999)
            if remaining > 0:
                raise TooManyAttemptsError(remaining)

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            extra = self._failures - self.FREE_ATTEMPTS
            if extra >= 0:
                self._locked_until = self._clock() + min(self.BASE * (2 ** extra), self.MAX)

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._locked_until = 0.0

    @property
    def failures(self) -> int:
        return self._failures
