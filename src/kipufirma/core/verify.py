"""Verificación local de firmas en PDF (integridad + confianza en las ECEP).

Se ejecuta automáticamente después de firmar cada documento: si la firma
recién creada no verifica, el archivo de salida se elimina y se reporta el
error. También se usa en la pestaña «Verificar».

La verificación OFICIAL con valor legal es la del validador de FirmaEC
(https://www.firmadigital.gob.ec); ver docs/PRUEBAS_ACEPTACION.md.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import datetime

from asn1crypto import x509 as ax509
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from kipufirma.core.ec_certs import extract_signer_data, identify_ca
from kipufirma.core.trust import TrustStore

log = logging.getLogger(__name__)


@dataclass
class SignatureReport:
    field_name: str
    signer_name: str = ""
    ca_name: str = ""
    signing_time: datetime | None = None
    intact: bool = False
    valid: bool = False
    trusted: bool = False
    covers_whole_document: bool = False
    modification_level: str = ""
    md_algorithm: str = ""
    subfilter: str = ""
    has_timestamp: bool = False
    reason: str = ""
    location: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.intact and self.valid


def _context(trust: TrustStore, allow_fetching: bool) -> ValidationContext:
    roots = [ax509.Certificate.load(c.public_bytes(Encoding.DER)) for c in trust.anchors.values()]
    return ValidationContext(trust_roots=roots, allow_fetching=allow_fetching,
                             revocation_mode="soft-fail")


def verify_pdf_bytes(data: bytes, trust: TrustStore, allow_fetching: bool = False) -> list[SignatureReport]:
    reader = PdfFileReader(io.BytesIO(data), strict=False)
    reports: list[SignatureReport] = []
    ctx = _context(trust, allow_fetching)
    for emb in reader.embedded_signatures:
        rep = SignatureReport(field_name=emb.field_name)
        try:
            crypto_cert = x509.load_der_x509_certificate(emb.signer_cert.dump())
            rep.signer_name = extract_signer_data(crypto_cert).display_name
            rep.ca_name = identify_ca(crypto_cert)[0]
        except Exception as e:
            rep.errors.append(f"Certificado ilegible: {e}")
        try:
            rep.md_algorithm = emb.md_algorithm
            rep.subfilter = str(emb.sig_object.get("/SubFilter", ""))
            rep.reason = str(emb.sig_object.get("/Reason", "") or "")
            rep.location = str(emb.sig_object.get("/Location", "") or "")
            rep.signing_time = emb.self_reported_timestamp
            status = validate_pdf_signature(emb, ctx)
            rep.intact = bool(status.intact)
            rep.valid = bool(status.valid)
            rep.trusted = bool(status.trusted)
            rep.covers_whole_document = status.coverage.name == "ENTIRE_FILE"
            rep.modification_level = getattr(status.modification_level, "name", "")
            rep.has_timestamp = status.timestamp_validity is not None
        except Exception as e:
            rep.errors.append(str(e))
        reports.append(rep)
    return reports
