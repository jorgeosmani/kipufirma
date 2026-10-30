"""Firma por lotes: prepara la sesión (certificado + controles), resuelve la
ubicación de cada documento, firma, verifica y escribe el resultado.

Un error en un documento NO detiene el lote (a diferencia de FirmaEC, que
muestra una ventana modal por cada error): se registra y se continúa.
"""
from __future__ import annotations

import csv
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pypdfium2 as pdfium

from kipufirma.core.certificate import Credential, check_usable
from kipufirma.core.config import Settings
from kipufirma.core.errors import (
    CancelledError,
    CertificateNotUsableError,
    DocumentError,
    EncryptedDocumentError,
    KipuError,
    LockedDocumentError,
    SuspiciousDocumentError,
)
from kipufirma.core.locator import find_keywords
from kipufirma.core.naming import atomic_write, output_path
from kipufirma.core.pdf_inspect import PdfReport, inspect_pdf
from kipufirma.core.placement import ManualBox, Resolution, resolve
from kipufirma.core.revocation import check_revocation
from kipufirma.core.signer import sign_pdf_bytes
from kipufirma.core.timecheck import MAX_SKEW_SECONDS, clock_skew_seconds
from kipufirma.core.trust import TrustStore
from kipufirma.core.verify import verify_pdf_bytes

log = logging.getLogger(__name__)

STATUS_OK, STATUS_WARN, STATUS_SKIP, STATUS_ERROR = "Firmado", "Firmado con avisos", "Omitido", "Error"


@dataclass
class DocResult:
    source: Path
    status: str = ""
    output: Path | None = None
    placement: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class Preview:
    report: PdfReport
    resolution: Resolution | None
    error: str = ""


def resolve_for_document(data: bytes, report: PdfReport, settings: Settings,
                         manual: list[ManualBox] | None = None) -> Resolution:
    doc = pdfium.PdfDocument(data)
    try:
        def finder(keywords: list[str]):
            return find_keywords(doc, keywords)
        return resolve(settings.placement, report.pages, finder, manual)
    finally:
        doc.close()


_REPORT_CACHE: dict[tuple, PdfReport] = {}
_REPORT_CACHE_MAX = 200
_cache_lock = threading.Lock()


def _cached_report(path: Path) -> tuple[PdfReport, bytes | None]:
    """El análisis del PDF (lo más lento) se hace una vez por versión del archivo."""
    st = path.stat()
    key = (str(path.resolve()), st.st_mtime_ns, st.st_size)
    with _cache_lock:
        rep = _REPORT_CACHE.get(key)
    if rep is not None:
        return rep, None
    data = path.read_bytes()
    rep = inspect_pdf(path, data)
    with _cache_lock:
        if len(_REPORT_CACHE) >= _REPORT_CACHE_MAX:
            _REPORT_CACHE.pop(next(iter(_REPORT_CACHE)))
        _REPORT_CACHE[key] = rep
    return rep, data


def preview_document(path: Path, settings: Settings, manual: list[ManualBox] | None = None) -> Preview:
    """Para la vista previa: qué páginas tiene y dónde iría la firma."""
    try:
        path = Path(path)
        rep, data = _cached_report(path)
        if rep.encrypted and not rep.opens_without_password:
            return Preview(rep, None, str(EncryptedDocumentError()))
        if settings.placement.mode == "palabra" and not manual:
            data = data if data is not None else path.read_bytes()
            return Preview(rep, resolve_for_document(data, rep, settings, manual))
        return Preview(rep, resolve(settings.placement, rep.pages, None, manual))
    except KipuError as e:
        return Preview(PdfReport(Path(path)), None, str(e))
    except Exception as e:
        log.exception("Vista previa fallida")
        return Preview(PdfReport(Path(path)), None, f"No se pudo analizar: {e}")


def prepare_session(cred: Credential, settings: Settings) -> list[str]:
    """Controles una vez por lote. Lanza si no se debe firmar."""
    warnings = check_usable(cred, require_trusted_chain=settings.security.require_trusted_ca)
    if settings.security.check_clock:
        skew = clock_skew_seconds()
        if skew is not None and abs(skew) > MAX_SKEW_SECONDS:
            warnings.append(f"El reloj del equipo difiere {int(skew)} s de la hora real; "
                            "la fecha de la firma quedará desfasada. Sincronice la hora de Windows.")
    policy = settings.security.revocation_policy
    if policy != "desactivada":
        issuer = cred.chain.issuer if cred.chain else None
        res = check_revocation(cred.certificate, issuer)
        if res.status == "revoked":
            when = res.revoked_at.astimezone().strftime("%d/%m/%Y") if res.revoked_at else ""
            raise CertificateNotUsableError(f"El certificado está REVOCADO {when} ({res.source}). No se puede firmar.")
        if res.status == "unknown":
            msg = "No se pudo confirmar que el certificado no esté revocado (sin conexión o servicio no disponible)."
            if policy == "estricta":
                raise CertificateNotUsableError(msg + " La política estricta impide continuar.")
            warnings.append(msg)
    return warnings


def output_dir_for(src: Path, settings: Settings) -> Path:
    o = settings.output
    if o.mode == "carpeta" and o.folder:
        return Path(o.folder)
    if o.mode == "subcarpeta":
        return src.parent / (o.subfolder or "firmados")
    return src.parent


def sign_one(src: Path, cred: Credential, settings: Settings, trust: TrustStore,
             manual: list[ManualBox] | None = None) -> DocResult:
    res = DocResult(src)
    data = src.read_bytes()
    rep = inspect_pdf(src, data)
    if rep.encrypted and not rep.opens_without_password:
        raise EncryptedDocumentError()
    if rep.certified_no_changes:
        raise LockedDocumentError()
    if rep.threats:
        text = "; ".join(rep.threats)
        if settings.security.pdf_threat_policy == "bloquear":
            raise SuspiciousDocumentError(f"Documento potencialmente peligroso: {text}.")
        res.warnings.append(f"Contenido activo detectado: {text}.")
    resolution = resolve_for_document(data, rep, settings, manual)
    res.placement = resolution.summary
    if resolution.skipped:
        res.status, res.message = STATUS_SKIP, resolution.note
        return res
    if resolution.source == "alternativa":
        res.warnings.append("No se encontró la palabra clave; se aplicó la ubicación alternativa.")
    signed = sign_pdf_bytes(data, cred, resolution, settings.signing,
                            owner_restricted=rep.encrypted)
    # Verificación inmediata de TODAS las firmas añadidas (las últimas N).
    added = 1 if resolution.invisible or not resolution.boxes else len(resolution.boxes)
    reports = verify_pdf_bytes(signed, trust)
    for r in reports[-added:]:
        if not r.ok:
            raise DocumentError("La verificación posterior de la firma falló: "
                                + ("; ".join(r.errors) or "firma no íntegra"))
    if rep.signature_count:
        res.warnings.append(f"El documento ya tenía {rep.signature_count} firma(s); se conservaron.")
    out = output_path(src, output_dir_for(src, settings), settings.output.suffix)
    atomic_write(out, signed)
    res.output = out
    res.status = STATUS_WARN if res.warnings else STATUS_OK
    res.message = "Firma verificada correctamente."
    return res


ProgressCb = Callable[[int, int, Path, DocResult | None], None]


def run_batch(files: list[Path], cred: Credential, settings: Settings, trust: TrustStore,
              manual: dict[Path, list[ManualBox]] | None = None,
              progress: ProgressCb | None = None,
              cancel: threading.Event | None = None) -> list[DocResult]:
    manual = manual or {}
    results: list[DocResult] = []
    total = len(files)
    for i, f in enumerate(files):
        if cancel is not None and cancel.is_set():
            for rest in files[i:]:
                results.append(DocResult(rest, STATUS_SKIP, message=str(CancelledError())))
            break
        if progress:
            progress(i, total, f, None)
        try:
            r = sign_one(Path(f), cred, settings, trust, manual.get(Path(f)))
        except KipuError as e:
            r = DocResult(Path(f), STATUS_ERROR, message=str(e))
        except Exception as e:  # inesperado: se registra con traza, el lote sigue
            log.exception("Error inesperado con %s", Path(f).name)
            r = DocResult(Path(f), STATUS_ERROR, message=f"Error inesperado: {e}")
        log.info("%s -> %s %s", Path(f).name, r.status, r.message)
        results.append(r)
        if progress:
            progress(i + 1, total, f, r)
    return results


def export_report(results: list[DocResult], path: Path, signer: str = "") -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # BOM: Excel lo abre bien
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Fecha", "Firmante", "Documento", "Estado", "Ubicación", "Archivo firmado", "Detalle", "Avisos"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            w.writerow([now, signer, str(r.source), r.status, r.placement,
                        str(r.output or ""), r.message, " | ".join(r.warnings)])
