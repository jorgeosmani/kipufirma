"""Inspección del PDF antes de firmar: geometría de páginas, cifrado, firmas
existentes, certificación (DocMDP) y contenido potencialmente peligroso.

FirmaEC rechaza documentos con JavaScript en /OpenAction o en anotaciones
("El documento es potencialmente sospechoso"). Aquí ampliamos la revisión
(acciones /Launch, /AA, árbol de nombres JavaScript, archivos incrustados,
formularios XFA) y dejamos que la política decida: bloquear o advertir.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.reader import PdfFileReader

from kipufirma.core.errors import DocumentError
from kipufirma.core.geometry import PageGeom

log = logging.getLogger(__name__)

MAX_PDF_BYTES = 300 * 1024 * 1024


@dataclass
class PdfReport:
    path: Path
    page_count: int = 0
    pages: list[PageGeom] = field(default_factory=list)
    encrypted: bool = False
    opens_without_password: bool = True
    signature_count: int = 0
    certified_no_changes: bool = False
    threats: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def page_geometry(doc: pdfium.PdfDocument) -> list[PageGeom]:
    geoms = []
    for i in range(len(doc)):
        page = doc[i]
        x0, y0, x1, y1 = page.get_cropbox()
        geoms.append(PageGeom(x0, y0, x1, y1, page.get_rotation() % 360))
        page.close()
    return geoms


def _resolve(obj):
    while isinstance(obj, generic.IndirectObject):
        obj = obj.get_object()
    return obj


def _action_threats(action, where: str, out: list[str], depth: int = 0) -> None:
    action = _resolve(action)
    if depth > 8 or not isinstance(action, generic.DictionaryObject):
        return
    kind = _resolve(action.get("/S"))
    if kind in ("/JavaScript",) or "/JS" in action:
        out.append(f"JavaScript en {where}")
    elif kind == "/Launch":
        out.append(f"Acción que ejecuta programas (/Launch) en {where}")
    elif kind in ("/ImportData", "/SubmitForm"):
        out.append(f"Acción {kind} en {where}")
    nxt = action.get("/Next")
    if nxt is not None:
        nxt = _resolve(nxt)
        for a in (nxt if isinstance(nxt, generic.ArrayObject) else [nxt]):
            _action_threats(a, where, out, depth + 1)


def _scan_threats(reader: PdfFileReader) -> list[str]:
    out: list[str] = []
    root = reader.root
    if "/OpenAction" in root:
        _action_threats(root["/OpenAction"], "la apertura del documento", out)
    aa = _resolve(root.get("/AA"))
    if isinstance(aa, generic.DictionaryObject):
        for k in aa:
            _action_threats(aa[k], f"acciones automáticas del documento ({k})", out)
    names = _resolve(root.get("/Names"))
    if isinstance(names, generic.DictionaryObject):
        if "/JavaScript" in names:
            out.append("JavaScript a nivel de documento")
        if "/EmbeddedFiles" in names:
            out.append("Archivos incrustados (adjuntos)")
    acro = _resolve(root.get("/AcroForm"))
    if isinstance(acro, generic.DictionaryObject) and "/XFA" in acro:
        out.append("Formulario XFA (contenido dinámico)")
    try:
        pages_root = _resolve(root["/Pages"])
        stack, seen = [pages_root], 0
        while stack and seen < 5000:
            node = _resolve(stack.pop())
            seen += 1
            if _resolve(node.get("/Type")) == "/Pages":
                stack.extend(_resolve(node.get("/Kids", generic.ArrayObject())))
                continue
            paa = _resolve(node.get("/AA"))
            if isinstance(paa, generic.DictionaryObject):
                for k in paa:
                    _action_threats(paa[k], "acciones automáticas de página", out)
            for annot in _resolve(node.get("/Annots", generic.ArrayObject())) or []:
                annot = _resolve(annot)
                if isinstance(annot, generic.DictionaryObject):
                    if "/A" in annot:
                        _action_threats(annot["/A"], "un enlace o anotación", out)
                    aaa = _resolve(annot.get("/AA"))
                    if isinstance(aaa, generic.DictionaryObject):
                        for k in aaa:
                            _action_threats(aaa[k], "acciones de un campo", out)
    except Exception as e:  # estructura dañada: lo notificamos sin abortar
        log.debug("No se pudo recorrer el árbol de páginas: %s", e)
    return sorted(set(out))


def inspect_pdf(path: Path, data: bytes | None = None) -> PdfReport:
    path = Path(path)
    if data is None:
        if path.stat().st_size > MAX_PDF_BYTES:
            raise DocumentError("El PDF supera el tamaño máximo admitido (300 MB).")
        data = path.read_bytes()
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise DocumentError("El archivo no es un PDF válido.")
    rep = PdfReport(path)
    try:
        reader = PdfFileReader(io.BytesIO(data), strict=False)
    except Exception as e:
        raise DocumentError(f"No se pudo leer el PDF (¿dañado?): {e}") from None
    if reader.encrypted:
        rep.encrypted = True
        try:
            res = reader.decrypt("")
            rep.opens_without_password = bool(res and res.status.name in ("USER", "OWNER"))
        except Exception:
            rep.opens_without_password = False
        if not rep.opens_without_password:
            return rep
        rep.notes.append("El documento tiene restricciones de seguridad (contraseña de propietario).")
    rep.threats = _scan_threats(reader)
    try:
        rep.signature_count = len(reader.embedded_signatures)
    except Exception:
        rep.signature_count = 0
    try:
        from pyhanko.sign.validation import read_certification_data
        cert_data = read_certification_data(reader)
        if cert_data is not None and cert_data.permission.value == 1:
            rep.certified_no_changes = True
    except Exception as e:
        log.debug("Sin datos de certificación legibles: %s", e)
    try:
        doc = pdfium.PdfDocument(data)
        rep.pages = page_geometry(doc)
        rep.page_count = len(rep.pages)
        doc.close()
    except Exception as e:
        raise DocumentError(f"No se pudo interpretar las páginas del PDF: {e}") from None
    return rep
