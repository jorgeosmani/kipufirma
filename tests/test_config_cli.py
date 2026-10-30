import io
import json
import logging

from helpers import PASSWORD, make_pdf
from kipufirma.core.config import Settings, config_file, load_settings, save_settings
from kipufirma.core.logging_setup import RedactingFilter


def test_config_round_trip_never_stores_secrets(tmp_path):
    s = Settings()
    s.certificate.path = r"C:\Firma\mi.p12"
    s.signing.tsa_password = "secreto-tsa"
    s.placement.mode = "palabra"
    save_settings(s)
    raw = config_file().read_text(encoding="utf-8")
    assert "secreto-tsa" not in raw
    assert json.loads(raw)["signing"]["tsa_password"] == ""
    s2 = load_settings()
    assert s2.certificate.path == s.certificate.path and s2.placement.mode == "palabra"


def test_corrupt_config_is_backed_up():
    config_file().write_text("{no json", encoding="utf-8")
    s = load_settings()
    assert s.output.mode == "subcarpeta"
    assert config_file().with_suffix(".json.corrupto").exists()


def test_invalid_values_normalized():
    s = Settings.from_dict({"security": {"revocation_policy": "x"}, "signing": {"md_algorithm": "md5"}})
    assert s.security.revocation_policy == "advertir" and s.signing.md_algorithm == "sha512"


def test_log_redaction():
    rec = logging.LogRecord("x", logging.INFO, "", 0, "cedula 1712345678 password=abc123 ruc 1790012345001", None, None)
    RedactingFilter().filter(rec)
    assert "1712345678" not in rec.msg and "abc123" not in rec.msg and "1790012345001" not in rec.msg


def test_cli_certificate_and_sign(tmp_path, pki, monkeypatch, capsys):
    from kipufirma import cli
    from kipufirma.core import trust as trust_mod
    monkeypatch.setattr(trust_mod.TrustStore, "default", classmethod(lambda cls, include_user=True: cls([pki.root])))
    p12 = tmp_path / "f.p12"
    p12.write_bytes(pki.p12())
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD.decode() + "\n"))
    assert cli.main(["certificado", "--p12", str(p12), "--clave-stdin"]) == 0
    assert "PEÑAFIEL" in capsys.readouterr().out
    s = Settings()
    s.security.revocation_policy = "desactivada"
    s.security.check_clock = False
    save_settings(s)
    doc = tmp_path / "d.pdf"
    doc.write_bytes(make_pdf([(595, 842, [(72, 300, 11, "Firma del docente")])]))
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD.decode() + "\n"))
    rc = cli.main(["firmar", str(doc), "--p12", str(p12), "--clave-stdin", "--palabra", "firma del docente",
                   "--informe", str(tmp_path / "i.csv")])
    assert rc == 0
    assert (tmp_path / "firmados" / "d-firmado.pdf").exists()
    assert cli.main(["verificar", str(tmp_path / "firmados")]) == 0
