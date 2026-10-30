"""Almacén de anclas de confianza: certificados raíz e intermedios de las
ECEP ecuatorianas (extraídos de FirmaEC, ver tools/extraer_anclas_firmaec.py)
más anclas adicionales que el usuario coloque en
``<config>/anclas_adicionales/*.pem|*.crt|*.cer``.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from kipufirma.paths import config_dir, resource_path

log = logging.getLogger(__name__)


def fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()


def _load_any(path: Path) -> list[x509.Certificate]:
    raw = path.read_bytes()
    try:
        if b"-----BEGIN" in raw:
            return x509.load_pem_x509_certificates(raw)
        return [x509.load_der_x509_certificate(raw)]
    except ValueError:
        log.warning("Ancla ignorada (no es un certificado válido): %s", path.name)
        return []


@dataclass
class ChainResult:
    chain: list[x509.Certificate]      # hoja -> ... -> último encontrado
    trusted: bool                      # termina en un ancla del almacén
    anchor_subject: str = ""
    detail: str = ""

    @property
    def issuer(self) -> x509.Certificate | None:
        return self.chain[1] if len(self.chain) > 1 else None


class TrustStore:
    def __init__(self, certs: list[x509.Certificate]) -> None:
        self.anchors: dict[str, x509.Certificate] = {fingerprint(c): c for c in certs}
        self._by_subject: dict[bytes, list[x509.Certificate]] = {}
        for c in self.anchors.values():
            self._by_subject.setdefault(c.subject.public_bytes(), []).append(c)

    @classmethod
    def default(cls, include_user: bool = True) -> "TrustStore":
        certs: list[x509.Certificate] = []
        for p in sorted(resource_path("trust").glob("*.pem")):
            certs.extend(_load_any(p))
        if include_user:
            extra = config_dir() / "anclas_adicionales"
            if extra.is_dir():
                for p in sorted(extra.iterdir()):
                    if p.suffix.lower() in {".pem", ".crt", ".cer"}:
                        certs.extend(_load_any(p))
        return cls(certs)

    def __len__(self) -> int:
        return len(self.anchors)

    def is_anchor(self, cert: x509.Certificate) -> bool:
        return fingerprint(cert) in self.anchors

    @staticmethod
    def _issued_by(child: x509.Certificate, parent: x509.Certificate) -> bool:
        if child.issuer != parent.subject:
            return False
        try:
            child.verify_directly_issued_by(parent)
            return True
        except Exception:
            return False

    def build_chain(self, leaf: x509.Certificate,
                    extra: list[x509.Certificate] | None = None,
                    max_depth: int = 6) -> ChainResult:
        """Construye la cadena verificando criptográficamente cada eslabón.
        Los certificados ``extra`` (p. ej. los incluidos en el .p12) ayudan a
        construir la ruta, pero solo se confía si se llega a un ancla."""
        pool: list[x509.Certificate] = list(extra or [])
        chain = [leaf]
        current = leaf
        if self.is_anchor(leaf):
            return ChainResult(chain, True, leaf.subject.rfc4514_string())
        for _ in range(max_depth):
            if current.issuer == current.subject:
                break
            candidates = self._by_subject.get(current.issuer.public_bytes(), []) + [
                c for c in pool if c.subject == current.issuer
            ]
            parent = next((c for c in candidates if self._issued_by(current, c)), None)
            if parent is None:
                return ChainResult(chain, False, detail="No se encontró el emisor del certificado en las anclas de confianza.")
            chain.append(parent)
            if self.is_anchor(parent):
                return ChainResult(chain, True, parent.subject.rfc4514_string())
            current = parent
        return ChainResult(chain, False, detail="La cadena no termina en una entidad de certificación reconocida.")
