"""Utilidades de prueba: PKI ecuatoriana simulada y generador de PDF.

NUNCA use certificados reales en las pruebas ni los suba al repositorio."""
from __future__ import annotations

import datetime as dt

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

PASSWORD = b"Clave-Prueba-123"


def der_utf8(s: str) -> bytes:
    b = s.encode("utf-8")
    return bytes([0x0C, len(b)]) + b


class FakeEcPKI:
    """PKI simulada (el nombre no empieza por Test para que pytest no la recolecte)."""

    def __init__(self, org="SECURITY DATA SEGURIDAD EN DATOS Y FIRMA DIGITAL S.A.",
                 ext_arc="1.3.6.1.4.1.37746", scheme="EXT", days=365, start_days=-1,
                 key_usage=(True, True), name="MARÍA JOSÉ PEÑAFIEL ÁLVAREZ"):
        now = dt.datetime.now(dt.timezone.utc)
        self.root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        root_name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
                               x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
                               x509.NameAttribute(NameOID.COMMON_NAME, "AC RAIZ PRUEBAS")])
        self.root = self._ca(root_name, root_name, self.root_key, self.root_key, now)
        self.sub_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        sub_name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
                              x509.NameAttribute(NameOID.ORGANIZATION_NAME, org),
                              x509.NameAttribute(NameOID.COMMON_NAME, "AC SUBORDINADA PRUEBAS")])
        self.sub = self._ca(sub_name, root_name, self.sub_key, self.root_key, now)
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        attrs = [x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"), x509.NameAttribute(NameOID.COMMON_NAME, name)]
        if scheme == "SUBJ":
            attrs += [x509.NameAttribute(NameOID.SERIAL_NUMBER, "IDCEC-1712345678"),
                      x509.NameAttribute(NameOID.GIVEN_NAME, "MARÍA JOSÉ"),
                      x509.NameAttribute(NameOID.SURNAME, "PEÑAFIEL ÁLVAREZ")]
        b = (x509.CertificateBuilder().subject_name(x509.Name(attrs)).issuer_name(sub_name)
             .public_key(self.key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now + dt.timedelta(days=start_days))
             .not_valid_after(now + dt.timedelta(days=days))
             .add_extension(x509.KeyUsage(key_usage[0], key_usage[1], False, False, False, False, False, False, False), critical=True))
        if scheme == "EXT":
            for k, v in {1: "1712345678", 2: "MARÍA JOSÉ", 3: "PEÑAFIEL", 4: "ÁLVAREZ"}.items():
                b = b.add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(f"{ext_arc}.3.{k}"), der_utf8(v)), critical=False)
        self.cert = b.sign(self.sub_key, hashes.SHA256())

    @staticmethod
    def _ca(subject, issuer, key, signer_key, now):
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - dt.timedelta(days=10)).not_valid_after(now + dt.timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
                .sign(signer_key, hashes.SHA256()))

    def p12(self, password: bytes = PASSWORD, include_chain: bool = True) -> bytes:
        cas = [self.sub, self.root] if include_chain else None
        return pkcs12.serialize_key_and_certificates(b"firma", self.key, self.cert, cas,
                                                     serialization.BestAvailableEncryption(password))


def make_pdf(pages, catalog_extra: bytes = b"") -> bytes:
    """pages: [(ancho, alto, [(x, y, tamaño, texto)], rotacion)] -> PDF mínimo."""
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    pages_id = len(objs) + 1 + 2 * len(pages)
    kids = []
    for spec in pages:
        w, h, items = spec[0], spec[1], spec[2]
        rot = spec[3] if len(spec) > 3 else 0
        stream = b"".join(
            b"BT /F1 %d Tf %.2f %.2f Td (%s) Tj ET\n" % (s, x, y, t.encode("cp1252").replace(b"(", b"\\(").replace(b")", b"\\)"))
            for x, y, s, t in items)
        c = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Rotate %d "
                        b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>" % (pages_id, w, h, rot, font, c)))
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))) == pages_id
    cat = add(b"<< /Type /Catalog %s /Pages %d 0 R >>" % (catalog_extra, pages_id))
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, xref)
    return bytes(out)


def make_pdf_with_js() -> bytes:
    return make_pdf([(595, 842, [(72, 700, 12, "Hola")])],
                    catalog_extra=b"/OpenAction << /S /JavaScript /JS (app.alert\\(1\\)) >>")


TestPKI = FakeEcPKI  # alias histórico
