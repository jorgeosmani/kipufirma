"""Revocación OCSP/CRL con respuestas simuladas (sin red)."""
import datetime as dt

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp

from kipufirma.core import revocation
from kipufirma.core.batch import prepare_session
from kipufirma.core.errors import CertificateNotUsableError


def _with_urls(pki, ocsp_url=True, crl_url=True):
    """Re-emite el certificado del firmante con AIA/CDP."""
    b = (x509.CertificateBuilder().subject_name(pki.cert.subject).issuer_name(pki.cert.issuer)
         .public_key(pki.cert.public_key()).serial_number(pki.cert.serial_number)
         .not_valid_before(pki.cert.not_valid_before_utc).not_valid_after(pki.cert.not_valid_after_utc))
    if ocsp_url:
        b = b.add_extension(x509.AuthorityInformationAccess([x509.AccessDescription(
            x509.oid.AuthorityInformationAccessOID.OCSP, x509.UniformResourceIdentifier("http://ocsp.prueba/"))]), False)
    if crl_url:
        b = b.add_extension(x509.CRLDistributionPoints([x509.DistributionPoint(
            [x509.UniformResourceIdentifier("http://crl.prueba/sub.crl")], None, None, None)]), False)
    return b.sign(pki.sub_key, hashes.SHA256())


def _ocsp_response(pki, cert, status):
    now = dt.datetime.now(dt.timezone.utc)
    b = ocsp.OCSPResponseBuilder().add_response(
        cert=cert, issuer=pki.sub, algorithm=hashes.SHA1(), cert_status=status, this_update=now,
        next_update=now + dt.timedelta(hours=1),
        revocation_time=now if status == ocsp.OCSPCertStatus.REVOKED else None,
        revocation_reason=None).responder_id(ocsp.OCSPResponderEncoding.HASH, pki.sub)
    return b.sign(pki.sub_key, hashes.SHA256()).public_bytes(serialization.Encoding.DER)


def _crl(pki, revoked_serials, signer_key=None):
    now = dt.datetime.now(dt.timezone.utc)
    b = x509.CertificateRevocationListBuilder().issuer_name(pki.sub.subject).last_update(now).next_update(now + dt.timedelta(days=1))
    for s in revoked_serials:
        b = b.add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(s).revocation_date(now).build())
    return b.sign(signer_key or pki.sub_key, hashes.SHA256()).public_bytes(serialization.Encoding.DER)


@pytest.mark.parametrize("status,expected", [(ocsp.OCSPCertStatus.GOOD, "good"), (ocsp.OCSPCertStatus.REVOKED, "revoked")])
def test_ocsp(pki, monkeypatch, status, expected):
    cert = _with_urls(pki)
    monkeypatch.setattr(revocation, "_http", lambda url, *a, **k: _ocsp_response(pki, cert, status))
    res = revocation.check_revocation(cert, pki.sub)
    assert res.status == expected and res.source == "OCSP"


def test_ocsp_forged_signature_is_rejected(pki, monkeypatch):
    from helpers import FakeEcPKI
    cert = _with_urls(pki, crl_url=False)
    evil = FakeEcPKI()
    now = dt.datetime.now(dt.timezone.utc)
    forged = ocsp.OCSPResponseBuilder().add_response(
        cert=cert, issuer=pki.sub, algorithm=hashes.SHA1(), cert_status=ocsp.OCSPCertStatus.GOOD,
        this_update=now, next_update=None, revocation_time=None, revocation_reason=None
    ).responder_id(ocsp.OCSPResponderEncoding.HASH, evil.sub).sign(evil.sub_key, hashes.SHA256())
    monkeypatch.setattr(revocation, "_http", lambda *a, **k: forged.public_bytes(serialization.Encoding.DER))
    assert revocation.check_revocation(cert, pki.sub).status == "unknown"


def test_crl_fallback_and_signature_check(pki, monkeypatch):
    cert = _with_urls(pki, ocsp_url=False)
    monkeypatch.setattr(revocation, "_http", lambda *a, **k: _crl(pki, [cert.serial_number]))
    assert revocation.check_revocation(cert, pki.sub).status == "revoked"
    monkeypatch.setattr(revocation, "_http", lambda *a, **k: _crl(pki, []))
    assert revocation.check_revocation(cert, pki.sub).status == "good"
    monkeypatch.setattr(revocation, "_http", lambda *a, **k: _crl(pki, [], signer_key=pki.root_key))
    assert revocation.check_revocation(cert, pki.sub).status == "unknown"


def test_network_down_policies(credential, settings, monkeypatch):
    import kipufirma.core.batch as batch
    monkeypatch.setattr(batch, "check_revocation",
                        lambda *a: revocation.RevocationResult("unknown", "", "sin red"))
    settings.security.revocation_policy = "advertir"
    assert any("revocado" in w for w in prepare_session(credential, settings))
    settings.security.revocation_policy = "estricta"
    with pytest.raises(CertificateNotUsableError):
        prepare_session(credential, settings)
    monkeypatch.setattr(batch, "check_revocation",
                        lambda *a: revocation.RevocationResult("revoked", "OCSP", "x", dt.datetime.now(dt.timezone.utc)))
    settings.security.revocation_policy = "advertir"
    with pytest.raises(CertificateNotUsableError, match="REVOCADO"):
        prepare_session(credential, settings)


def test_clock_skew_warning(credential, settings, monkeypatch):
    import kipufirma.core.batch as batch
    settings.security.check_clock = True
    monkeypatch.setattr(batch, "clock_skew_seconds", lambda: 600.0)
    assert any("reloj" in w for w in prepare_session(credential, settings))
