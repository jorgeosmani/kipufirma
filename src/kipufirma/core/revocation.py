"""Comprobación de revocación del certificado del firmante por OCSP y, si no
hay respuesta, por CRL. Usa solo las URL publicadas en el propio certificado
(AIA y CRL Distribution Points), sin intermediarios.

Política configurable: ``desactivada`` | ``advertir`` (por defecto, como
FirmaEC: si no hay red se continúa avisando) | ``estricta`` (sin
confirmación de "no revocado" no se firma).
"""
from __future__ import annotations

import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import ocsp
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

log = logging.getLogger(__name__)

TIMEOUT = 10
MAX_CRL_BYTES = 30 * 1024 * 1024
USER_AGENT = "KipuFirma/1.0 (+revocation-check)"


@dataclass
class RevocationResult:
    status: str                 # "good" | "revoked" | "unknown"
    source: str = ""            # "OCSP" | "CRL" | ""
    detail: str = ""
    revoked_at: datetime | None = None


def _http(url: str, data: bytes | None = None, ctype: str | None = None, limit: int = 2_000_000) -> bytes:
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError("URL no soportada")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})  # noqa: S310 (esquema validado arriba)
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 (URL del certificado)
        body = resp.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Respuesta demasiado grande")
    return body


def _verify_sig(public_key, signature: bytes, data: bytes, hash_alg) -> bool:
    try:
        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(signature, data, padding.PKCS1v15(), hash_alg)
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, data, ec.ECDSA(hash_alg))
        else:
            return False
        return True
    except Exception:
        return False


def ocsp_urls(cert: x509.Certificate) -> list[str]:
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return []
    return [d.access_location.value for d in aia
            if d.access_method == AuthorityInformationAccessOID.OCSP]


def crl_urls(cert: x509.Certificate) -> list[str]:
    try:
        cdp = cert.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS).value
    except x509.ExtensionNotFound:
        return []
    urls = []
    for dp in cdp:
        for name in dp.full_name or []:
            if isinstance(name, x509.UniformResourceIdentifier):
                urls.append(name.value)
    return urls


def check_ocsp(cert: x509.Certificate, issuer: x509.Certificate) -> RevocationResult:
    urls = ocsp_urls(cert)
    if not urls:
        return RevocationResult("unknown", "OCSP", "El certificado no publica un servicio OCSP.")
    req = ocsp.OCSPRequestBuilder().add_certificate(cert, issuer, hashes.SHA1()).build()  # noqa: S303 (CertID OCSP, RFC 6960; no es una firma)
    body = req.public_bytes(serialization.Encoding.DER)
    last = ""
    for url in urls:
        try:
            resp = ocsp.load_der_ocsp_response(_http(url, body, "application/ocsp-request"))
        except Exception as e:  # red, formato
            last = f"{url}: {e}"
            continue
        if resp.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
            last = f"{url}: estado {resp.response_status.name}"
            continue
        # Verificar la firma de la respuesta (emisor o respondedor delegado).
        responder = issuer
        for c in resp.certificates:
            if c.issuer == issuer.subject:
                try:
                    c.verify_directly_issued_by(issuer)
                    responder = c
                except Exception as e:
                    log.debug("Certificado de respondedor OCSP no emitido por el emisor: %s", e)
        if not _verify_sig(responder.public_key(), resp.signature,
                           resp.tbs_response_bytes, resp.signature_hash_algorithm):
            last = f"{url}: la respuesta OCSP no tiene una firma válida"
            continue
        if resp.serial_number != cert.serial_number:
            last = f"{url}: la respuesta no corresponde al certificado"
            continue
        if resp.certificate_status == ocsp.OCSPCertStatus.GOOD:
            return RevocationResult("good", "OCSP", url)
        if resp.certificate_status == ocsp.OCSPCertStatus.REVOKED:
            return RevocationResult("revoked", "OCSP", url, resp.revocation_time_utc)
        last = f"{url}: estado desconocido"
    return RevocationResult("unknown", "OCSP", last)


def check_crl(cert: x509.Certificate, issuer: x509.Certificate) -> RevocationResult:
    last = "El certificado no publica una CRL."
    for url in crl_urls(cert):
        try:
            raw = _http(url, limit=MAX_CRL_BYTES)
            crl = (x509.load_pem_x509_crl(raw) if raw.lstrip().startswith(b"-----")
                   else x509.load_der_x509_crl(raw))
        except Exception as e:
            last = f"{url}: {e}"
            continue
        if not crl.is_signature_valid(issuer.public_key()):
            last = f"{url}: la CRL no está firmada por el emisor"
            continue
        entry = crl.get_revoked_certificate_by_serial_number(cert.serial_number)
        if entry is not None:
            return RevocationResult("revoked", "CRL", url, entry.revocation_date_utc)
        return RevocationResult("good", "CRL", url)
    return RevocationResult("unknown", "CRL", last)


def check_revocation(cert: x509.Certificate, issuer: x509.Certificate | None) -> RevocationResult:
    if issuer is None:
        return RevocationResult("unknown", "", "No se conoce el emisor para consultar la revocación.")
    res = check_ocsp(cert, issuer)
    if res.status != "unknown":
        return res
    res2 = check_crl(cert, issuer)
    if res2.status != "unknown":
        return res2
    return RevocationResult("unknown", "", f"OCSP: {res.detail} | CRL: {res2.detail}")
