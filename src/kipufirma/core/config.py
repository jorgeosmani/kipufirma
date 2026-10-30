"""Configuración persistente en ``%APPDATA%\\KipuFirma\\config.json``.

Qué SÍ se guarda: ruta del .p12, su huella SHA-256 (para detectar si el
archivo fue reemplazado), huella y datos públicos del certificado, y las
preferencias de firma/ubicación/salida.

Qué NUNCA se guarda: la contraseña del certificado, la clave privada, el
contenido de los documentos, ni la cédula/RUC del titular.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from kipufirma.core import dpapi
from kipufirma.core.placement import PlacementRule
from kipufirma.core.signer import SignOptions
from kipufirma.paths import config_dir

log = logging.getLogger(__name__)
SCHEMA_VERSION = 2


@dataclass
class CertificateSettings:
    path: str = ""
    file_sha256: str = ""
    thumbprint: str = ""
    holder: str = ""
    ca_name: str = ""
    not_after: str = ""


@dataclass
class OutputSettings:
    mode: str = "subcarpeta"          # "junto" | "subcarpeta" | "carpeta"
    subfolder: str = "firmados"
    folder: str = ""
    suffix: str = "-firmado"
    open_folder_when_done: bool = True


@dataclass
class SecuritySettings:
    revocation_policy: str = "advertir"   # "desactivada" | "advertir" | "estricta"
    pdf_threat_policy: str = "advertir"   # "advertir" | "bloquear"
    require_trusted_ca: bool = True
    check_clock: bool = True
    warn_cloud_folder: bool = True


@dataclass
class UiSettings:
    theme: str = "sistema"                # "sistema" | "claro" | "oscuro"
    last_documents_dir: str = ""
    recursive_folders: bool = False


@dataclass
class Settings:
    schema: int = SCHEMA_VERSION
    certificate: CertificateSettings = field(default_factory=CertificateSettings)
    signing: SignOptions = field(default_factory=SignOptions)
    placement: PlacementRule = field(default_factory=PlacementRule)
    output: OutputSettings = field(default_factory=OutputSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    ui: UiSettings = field(default_factory=UiSettings)
    tsa_password_protected: str = ""

    # --- serialización -------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["signing"]["tsa_password"] = ""          # jamás en claro
        return d

    @staticmethod
    def _pick(cls, data: dict | None):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})

    @classmethod
    def from_dict(cls, d: dict) -> "Settings":
        s = cls()
        s.certificate = cls._pick(CertificateSettings, d.get("certificate"))
        s.signing = cls._pick(SignOptions, d.get("signing"))
        s.output = cls._pick(OutputSettings, d.get("output"))
        s.security = cls._pick(SecuritySettings, d.get("security"))
        s.ui = cls._pick(UiSettings, d.get("ui"))
        try:
            s.placement = PlacementRule.from_dict(d.get("placement"))
        except Exception as e:
            log.warning("Regla de ubicación inválida en la configuración, se usa la predeterminada: %s", e)
        s.tsa_password_protected = str(d.get("tsa_password_protected", ""))
        if int(d.get("schema", 1)) < 2:
            # v1 -> v2: el tamaño por defecto del sello pasó de 170×55 a 110×36 pt (como FirmaEC).
            size = s.placement.size
            if abs(size.width - 170) < 0.5 and abs(size.height - 55) < 0.5:
                size.width, size.height = 110.0, 36.0
            s.signing.show_date_in_stamp = False
        if s.tsa_password_protected:
            try:
                s.signing.tsa_password = dpapi.unprotect(s.tsa_password_protected)
            except Exception:
                s.signing.tsa_password = ""
        s.normalize()
        return s

    def normalize(self) -> None:
        sec = self.security
        if sec.revocation_policy not in ("desactivada", "advertir", "estricta"):
            sec.revocation_policy = "advertir"
        if sec.pdf_threat_policy not in ("advertir", "bloquear"):
            sec.pdf_threat_policy = "advertir"
        if self.output.mode not in ("junto", "subcarpeta", "carpeta"):
            self.output.mode = "subcarpeta"
        if not self.output.suffix.strip() and self.output.mode == "junto":
            self.output.suffix = "-firmado"     # evita pisar el nombre del original
        if self.signing.md_algorithm not in ("sha256", "sha384", "sha512"):
            self.signing.md_algorithm = "sha512"
        if self.signing.subfilter not in ("adbe", "pades"):
            self.signing.subfilter = "adbe"

    def set_tsa_password(self, password: str) -> None:
        self.signing.tsa_password = password
        self.tsa_password_protected = dpapi.protect(password) if password and dpapi.AVAILABLE else ""


def config_file() -> Path:
    return config_dir() / "config.json"


def load_settings(path: Path | None = None) -> Settings:
    path = path or config_file()
    if not path.exists():
        return Settings()
    try:
        return Settings.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        backup = path.with_suffix(".json.corrupto")
        log.error("Configuración ilegible (%s); se respalda en %s y se usan valores por defecto.", e, backup)
        try:
            os.replace(path, backup)
        except OSError:
            pass
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    path = path or config_file()
    settings.normalize()
    payload = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
