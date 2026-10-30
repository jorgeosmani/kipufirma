import pytest

from helpers import PASSWORD, FakeEcPKI
from kipufirma.core.certificate import AttemptLimiter, check_usable, file_sha256, is_in_cloud_folder, load_credential
from kipufirma.core.ec_certs import decode_der_string, extract_signer_data, identify_ca
from kipufirma.core.errors import (
    CertificateFileError,
    CertificateNotUsableError,
    TooManyAttemptsError,
    WrongPasswordError,
)
from kipufirma.core.secrets import SecretBuffer
from kipufirma.core.trust import TrustStore


def test_ext_scheme_extraction(pki):
    d = extract_signer_data(pki.cert)
    assert d.esquema == "EXT"
    assert d.cedula == "1712345678"
    assert d.display_name == "MARÍA JOSÉ PEÑAFIEL ÁLVAREZ"
    assert d.masked_id() == "17******78"


def test_subj_scheme_extraction():
    p = FakeEcPKI(scheme="SUBJ", org="UANATACA ECUADOR S.A.")
    d = extract_signer_data(p.cert)
    assert d.esquema == "SUBJ" and d.cedula == "1712345678"
    assert d.display_name == "MARÍA JOSÉ PEÑAFIEL ÁLVAREZ"
    assert identify_ca(p.cert) == ("Uanataca", True)


def test_unknown_ca():
    p = FakeEcPKI(org="EMPRESA DESCONOCIDA")
    name, ok = identify_ca(p.cert)
    assert not ok and "DESCONOCIDA" in name


@pytest.mark.parametrize("raw,expected", [
    (bytes([0x0C, 3]) + "ñá".encode()[:3], "ñ\ufffd"[:1]),
    (bytes([0x13, 4]) + b"ABCD", "ABCD"),
    (bytes([0x1E, 4]) + "ñA".encode("utf-16-be"), "ñA"),
])
def test_der_strings(raw, expected):
    assert decode_der_string(raw).startswith(expected)


def test_default_trust_store_has_ecuadorian_cas():
    store = TrustStore.default(include_user=False)
    assert len(store) >= 60
    subjects = " ".join(c.subject.rfc4514_string() for c in store.anchors.values()).upper()
    for org in ("BANCO CENTRAL DEL ECUADOR", "SECURITY DATA", "UANATACA", "CONSEJO DE LA JUDICATURA"):
        assert org in subjects


def test_chain_trusted_and_untrusted(pki):
    assert TrustStore([pki.root]).build_chain(pki.cert, [pki.sub]).trusted
    assert TrustStore([pki.sub]).build_chain(pki.cert).trusted   # ancla intermedia
    other = FakeEcPKI()
    assert not TrustStore([other.root]).build_chain(pki.cert, [pki.sub]).trusted


def test_load_ok(credential):
    assert credential.info.signer.cedula == "1712345678"
    assert credential.chain.trusted
    assert check_usable(credential) == []


def test_wrong_password_wipes_buffer(pki, tmp_path):
    p = tmp_path / "f.p12"
    p.write_bytes(pki.p12())
    buf = SecretBuffer(b"incorrecta")
    with pytest.raises(WrongPasswordError):
        load_credential(p, buf)
    assert len(buf) == 0 and "incorrecta" not in repr(buf)


def test_corrupt_and_missing_file(tmp_path):
    p = tmp_path / "x.p12"
    p.write_bytes(b"no es un p12" * 10)
    with pytest.raises(CertificateFileError):
        load_credential(p, SecretBuffer(b"x"))
    with pytest.raises(CertificateFileError):
        load_credential(tmp_path / "nada.p12", SecretBuffer(b"x"))


@pytest.mark.parametrize("kwargs,msg", [
    ({"days": -1, "start_days": -30}, "caducó"),
    ({"start_days": 5}, "aún no está vigente"),
    ({"key_usage": (False, False)}, "no está autorizado"),
])
def test_not_usable(tmp_path, kwargs, msg):
    p = FakeEcPKI(**kwargs)
    f = tmp_path / "f.p12"
    f.write_bytes(p.p12())
    cred = load_credential(f, SecretBuffer(PASSWORD), TrustStore([p.root]))
    with pytest.raises(CertificateNotUsableError, match=msg):
        check_usable(cred)


def test_untrusted_chain_policy(pki, tmp_path):
    f = tmp_path / "f.p12"
    f.write_bytes(pki.p12(include_chain=False))
    cred = load_credential(f, SecretBuffer(PASSWORD), TrustStore([FakeEcPKI().root]))
    with pytest.raises(CertificateNotUsableError, match="no pertenece"):
        check_usable(cred)
    assert any("no pertenece" in w for w in check_usable(cred, require_trusted_chain=False))


def test_expiry_warning(tmp_path):
    p = FakeEcPKI(days=10)
    f = tmp_path / "f.p12"
    f.write_bytes(p.p12())
    cred = load_credential(f, SecretBuffer(PASSWORD), TrustStore([p.root]))
    assert any("vence en" in w for w in check_usable(cred))


def test_attempt_limiter():
    t = [0.0]
    lim = AttemptLimiter(clock=lambda: t[0])
    for _ in range(3):
        lim.check()
        lim.failure()
    with pytest.raises(TooManyAttemptsError):
        lim.check()
    t[0] += 31
    lim.check()
    lim.success()
    assert lim.failures == 0


def test_cloud_and_hash(tmp_path):
    assert is_in_cloud_folder(tmp_path / "OneDrive - Uni" / "firma.p12")
    assert not is_in_cloud_folder(tmp_path / "Documentos" / "firma.p12")
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    assert file_sha256(f).startswith("ba7816bf")


def test_secret_buffer():
    with SecretBuffer("clave") as s:
        assert s.bytes_view() == b"clave"
    assert len(s) == 0
    assert str(s) == "SecretBuffer(<oculto>)"
