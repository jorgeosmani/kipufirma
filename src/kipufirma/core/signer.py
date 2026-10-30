"""Firma PAdES de documentos PDF con pyHanko.

Compatibilidad con FirmaEC (modo por defecto):
* actualización incremental (no altera firmas previas ni el contenido);
* SubFilter ``adbe.pkcs7.detached`` y resumen SHA-512, como
  ``PadesEnhancedSigner`` de FirmaEC 5.3.0;
* razón, localización, y cadena de certificados incluida en la firma.

Alternativa: SubFilter ``ETSI.CAdES.detached`` (PAdES baseline B-B, o B-T
con sello de tiempo).

La clave privada nunca se serializa: :class:`KeySigner` firma directamente
con el objeto de ``cryptography`` que vive solo durante el lote.
"""
from __future__ import annotations

import io
import logging
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from asn1crypto import tsp
from asn1crypto import x509 as ax509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.layout import AxisAlignment, InnerScaling, SimpleBoxLayoutRule
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.fields import VisibleSigSettings
from pyhanko.stamp import StaticStampStyle
from pyhanko_certvalidator.registry import SimpleCertificateStore

from kipufirma import APP_NAME, __version__
from kipufirma.core.certificate import Credential
from kipufirma.core.errors import SigningError
from kipufirma.core.placement import Resolution
from kipufirma.core.stamp import StampAppearance, StampText, build_qr_payload

log = logging.getLogger(__name__)

_HASHES = {"sha256": hashes.SHA256, "sha384": hashes.SHA384, "sha512": hashes.SHA512}


@dataclass
class SignOptions:
    reason: str = "Firmado electrónicamente"
    location: str = "Ecuador"
    md_algorithm: str = "sha512"
    subfilter: str = "adbe"              # "adbe" (FirmaEC) | "pades"
    show_qr: bool = True
    header_text: str = "Firmado electrónicamente por:"
    footer_text: str = "Validar únicamente en FirmaEC"
    show_date_in_stamp: bool = False      # como FirmaEC: la fecha va en la firma y en el QR
    tsa_url: str = ""
    tsa_user: str = ""
    tsa_password: str = ""
    extra_footer: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if self.md_algorithm not in _HASHES:
            raise SigningError("Algoritmo de resumen no soportado.")
        if self.subfilter not in ("adbe", "pades"):
            raise SigningError("Formato de firma no soportado.")
        if len(self.reason) > 120 or len(self.location) > 120:
            raise SigningError("La razón y la localización admiten hasta 120 caracteres.")


class KeySigner(signers.Signer):
    """Signer de pyHanko que usa la clave privada de ``cryptography`` en memoria."""

    def __init__(self, credential: Credential) -> None:
        cert = ax509.Certificate.load(credential.certificate.public_bytes(Encoding.DER))
        chain = [ax509.Certificate.load(c.public_bytes(Encoding.DER)) for c in credential.extra_certs]
        if credential.chain is not None:
            chain += [ax509.Certificate.load(c.public_bytes(Encoding.DER))
                      for c in credential.chain.chain[1:]]
        super().__init__(signing_cert=cert, cert_registry=SimpleCertificateStore.from_certs(chain),
                         prefer_pss=False)
        self._key = credential.private_key

    def sign_raw(self, data: bytes, digest_algorithm: str) -> bytes:
        h = _HASHES[digest_algorithm.lower()]()
        if isinstance(self._key, rsa.RSAPrivateKey):
            return self._key.sign(data, padding.PKCS1v15(), h)
        if isinstance(self._key, ec.EllipticCurvePrivateKey):
            return self._key.sign(data, ec.ECDSA(h))
        raise SigningError("Tipo de clave no soportado (se admite RSA y EC).")

    async def async_sign_raw(self, data: bytes, digest_algorithm: str, dry_run: bool = False) -> bytes:
        return self.sign_raw(data, digest_algorithm)


class UrllibTimeStamper(timestamps.TimeStamper):
    """Cliente RFC 3161 mínimo (sin dependencias asíncronas adicionales)."""

    def __init__(self, url: str, user: str = "", password: str = "", timeout: int = 15) -> None:
        super().__init__()
        if not url.lower().startswith(("http://", "https://")):
            raise SigningError("La URL del sello de tiempo debe empezar por http:// o https://")
        self.url, self.user, self.password, self.timeout = url, user, password, timeout

    async def async_request_tsa_response(self, req: tsp.TimeStampReq) -> tsp.TimeStampResp:
        request = urllib.request.Request(self.url, data=req.dump(),  # noqa: S310 (esquema validado)
                                         headers={"Content-Type": "application/timestamp-query",
                                                  "User-Agent": f"{APP_NAME}/{__version__}"})
        if self.user:
            import base64
            token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            request.add_header("Authorization", f"Basic {token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read(1_000_000)
        except Exception as e:
            raise SigningError(f"No se pudo obtener el sello de tiempo ({self.url}): {e}") from None
        return tsp.TimeStampResp.load(body)


def sign_time_iso(now: datetime | None = None) -> str:
    now = (now or datetime.now()).astimezone()
    return now.isoformat(timespec="seconds")


def build_stamp_text(credential: Credential, opts: SignOptions, when_iso: str) -> StampText:
    name = credential.info.signer.display_name
    footer: list[str] = []
    if opts.show_date_in_stamp:
        footer.append("Fecha: " + when_iso.replace("T", " ")[:19])
    if opts.footer_text.strip():
        footer.append(opts.footer_text.strip())
    footer += [x for x in opts.extra_footer if x.strip()]
    payload = build_qr_payload(name, opts.reason, opts.location, when_iso,
                               f"{APP_NAME} {__version__}")
    return StampText(signer_name=name, header=opts.header_text, footer_lines=tuple(footer),
                     qr_payload=payload, show_qr=opts.show_qr)


def _existing_field_names(writer: IncrementalPdfFileWriter) -> set[str]:
    try:
        return {name for name, _, _ in fields.enumerate_sig_fields(writer.prev)}
    except Exception:
        return set()


def sign_pdf_bytes(data: bytes, credential: Credential, resolution: Resolution,
                   opts: SignOptions, owner_restricted: bool = False) -> bytes:
    """Aplica una firma por cada recuadro resuelto (o una invisible) y
    devuelve el PDF firmado. Cada firma es una actualización incremental."""
    opts.validate()
    if resolution.skipped:
        raise SigningError(resolution.note)
    signer = KeySigner(credential)
    timestamper = UrllibTimeStamper(opts.tsa_url, opts.tsa_user, opts.tsa_password) if opts.tsa_url else None
    subfilter = (fields.SigSeedSubFilter.PADES if opts.subfilter == "pades"
                 else fields.SigSeedSubFilter.ADOBE_PKCS7_DETACHED)
    targets = [None] if resolution.invisible or not resolution.boxes else list(resolution.boxes)
    current = data
    for box in targets:
        w = IncrementalPdfFileWriter(io.BytesIO(current), strict=False)
        if owner_restricted:
            w.encrypt("")
        taken = _existing_field_names(w)
        name = f"Firma_{uuid.uuid4().hex[:10]}"
        while name in taken:
            name = f"Firma_{uuid.uuid4().hex[:10]}"
        when = sign_time_iso()
        meta = signers.PdfSignatureMetadata(
            field_name=name, md_algorithm=opts.md_algorithm, subfilter=subfilter,
            reason=opts.reason or None, location=opts.location or None,
            name=credential.info.signer.display_name or None,
            app_build_props=signers.pdf_byterange.BuildProps(name=APP_NAME, revision=__version__),
        )
        if box is None:
            spec = fields.SigFieldSpec(name, on_page=0, box=None)
            style = None
        else:
            r = box.user_rect
            spec = fields.SigFieldSpec(
                name, on_page=box.page_index, box=r.as_int_tuple(),
                visible_sig_settings=VisibleSigSettings(rotate_with_page=True, scale_with_page_zoom=True,
                                                        print_signature=True))
            appearance = StampAppearance(box.visual_rect.width, box.visual_rect.height,
                                         build_stamp_text(credential, opts, when),
                                         rotation=box.rotation)
            style = StaticStampStyle(
                background=appearance, border_width=0, background_opacity=1.0,
                background_layout=SimpleBoxLayoutRule(
                    x_align=AxisAlignment.ALIGN_MIN, y_align=AxisAlignment.ALIGN_MIN,
                    inner_content_scaling=InnerScaling.STRETCH_FILL))
        pdf_signer = signers.PdfSigner(meta, signer, timestamper=timestamper,
                                       stamp_style=style, new_field_spec=spec)
        try:
            out = pdf_signer.sign_pdf(w)
        except SigningError:
            raise
        except Exception as e:
            log.exception("Fallo de pyHanko al firmar")
            raise SigningError(f"No se pudo firmar el documento: {e}") from None
        current = out.getvalue()
    return current
