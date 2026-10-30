"""Sello visual de la firma (apariencia del campo de firma).

Diseño equivalente al estampado "QR" de FirmaEC: código QR a la izquierda
con los datos de la firma y, a la derecha, «Firmado electrónicamente por:»
y el nombre del titular en negrita. Mejoras respecto al original:

* el QR se dibuja con vectores (nítido a cualquier zoom e impresión);
* el tamaño de letra del nombre se ajusta automáticamente y el nombre se
  reparte en hasta 3 líneas en lugar de truncarse a 57 caracteres;
* el sello se adapta al tamaño elegido por el usuario (no solo 110×36 pt).

Se usan las fuentes estándar Courier/Courier-Bold con WinAnsiEncoding
(soporta tildes y eñes del español) igual que FirmaEC usa Courier.
"""
from __future__ import annotations

from dataclasses import dataclass

import qrcode
from pyhanko.pdf_utils import content, generic
from pyhanko.pdf_utils.content import ResourceType
from pyhanko.pdf_utils.layout import BoxConstraints

COURIER_ADVANCE = 0.6  # ancho de glifo de Courier, en em


@dataclass
class StampText:
    signer_name: str
    header: str = "Firmado electrónicamente por:"
    footer_lines: tuple[str, ...] = ()
    qr_payload: str = ""
    show_qr: bool = True


def build_qr_payload(name: str, reason: str, location: str, sign_time_iso: str,
                     app_label: str, validate_url: str = "https://www.firmadigital.gob.ec") -> str:
    """Mismo contenido y orden que el QR de FirmaEC."""
    return (f"FIRMADO POR: {name.strip()}\n"
            f"RAZON: {reason}\n"
            f"LOCALIZACION: {location}\n"
            f"FECHA: {sign_time_iso}\n"
            f"VALIDAR CON: {validate_url}\n"
            f"Firmado digitalmente con {app_label}")


def _font(base: str) -> generic.DictionaryObject:
    return generic.DictionaryObject({
        generic.NameObject("/Type"): generic.NameObject("/Font"),
        generic.NameObject("/Subtype"): generic.NameObject("/Type1"),
        generic.NameObject("/BaseFont"): generic.NameObject("/" + base),
        generic.NameObject("/Encoding"): generic.NameObject("/WinAnsiEncoding"),
    })


def pdf_literal(text: str) -> bytes:
    raw = text.encode("cp1252", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def wrap_words(text: str, max_chars: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        while len(w) > max_chars:                 # palabra más larga que la línea
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:max_chars])
            w = w[max_chars:]
        cand = f"{cur} {w}".strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


@dataclass
class TextLayout:
    name_size: float
    small_size: float
    name_lines: list[str]


def fit_text(text_w: float, text_h: float, st: StampText, max_name_lines: int = 3) -> TextLayout:
    """Busca el mayor tamaño de letra que hace caber todo el texto."""
    size = 11.0
    while size >= 3.0:
        small = max(3.0, min(size * 0.62, 6.5))
        max_chars = max(int(text_w / (COURIER_ADVANCE * size)), 4)
        lines = wrap_words(st.signer_name, max_chars)
        small_chars = max(int(text_w / (COURIER_ADVANCE * small)), 4)
        small_ok = all(len(s) <= small_chars for s in (st.header, *st.footer_lines))
        total = small * 1.2 * (1 + len(st.footer_lines)) + size * 1.12 * len(lines)
        if len(lines) <= max_name_lines and total <= text_h - 1 and small_ok:
            return TextLayout(size, small, lines)
        size -= 0.25
    small = 3.0
    max_chars = max(int(text_w / (COURIER_ADVANCE * 3.0)), 4)
    return TextLayout(3.0, small, wrap_words(st.signer_name, max_chars)[:max_name_lines])


class StampAppearance(content.PdfContent):
    """``width``/``height`` son las medidas VISUALES del sello. ``rotation`` es
    el /Rotate de la página: el contenido se contrarrota para que el sello se
    lea derecho y la caja en espacio de usuario tenga las medidas correctas."""

    def __init__(self, width: float, height: float, text: StampText, rotation: int = 0) -> None:
        self.rotation = rotation % 360
        uw, uh = (height, width) if self.rotation in (90, 270) else (width, height)
        super().__init__(box=BoxConstraints(width=uw, height=uh))
        self.user_w, self.user_h = float(uw), float(uh)
        self.w, self.h, self.st = float(width), float(height), text
        self.set_resource(ResourceType.FONT, generic.NameObject("/KfR"), _font("Courier"))
        self.set_resource(ResourceType.FONT, generic.NameObject("/KfB"), _font("Courier-Bold"))

    def _qr_ops(self, side: float, y_off: float) -> list[bytes]:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        qr.add_data(self.st.qr_payload.encode("utf-8"))
        qr.make(fit=True)
        matrix = qr.get_matrix()
        n = len(matrix)
        cell = side / n
        ops = [b"q 0 0 0 rg"]
        for r, row in enumerate(matrix):
            c = 0
            while c < n:                        # fusiona módulos contiguos: PDF más liviano
                if row[c]:
                    start = c
                    while c < n and row[c]:
                        c += 1
                    ops.append(b"%.3f %.3f %.3f %.3f re" % (
                        start * cell, y_off + side - (r + 1) * cell, (c - start) * cell, cell))
                else:
                    c += 1
        ops.append(b"f Q")
        return ops

    def render(self) -> bytes:
        pad = 1.0
        ops: list[bytes] = []
        x_text = pad
        if self.st.show_qr and self.st.qr_payload:
            side = min(self.h - 2 * pad, self.w * 0.40)
            ops += self._qr_ops(side, (self.h - side) / 2)
            x_text = side + max(4.0, self.h * 0.09)
        text_w = self.w - x_text - pad
        lay = fit_text(text_w, self.h - 2 * pad, self.st)
        n_small_after = len(self.st.footer_lines)
        block = lay.small_size * 1.2 * (1 + n_small_after) + lay.name_size * 1.12 * len(lay.name_lines)
        y = (self.h + block) / 2                # centrado vertical
        ops.append(b"0 0 0 rg")

        def line(font: bytes, size: float, txt: str, leading: float) -> None:
            nonlocal y
            y -= leading
            ops.append(b"BT /%s %.2f Tf %.2f %.2f Td (%s) Tj ET" % (
                font, size, x_text, y + size * 0.22, pdf_literal(txt)))

        line(b"KfR", lay.small_size, self.st.header, lay.small_size * 1.2)
        for t in lay.name_lines:
            line(b"KfB", lay.name_size, t, lay.name_size * 1.12)
        for t in self.st.footer_lines:
            line(b"KfR", lay.small_size, t, lay.small_size * 1.2)
        matrix = {
            0: None,
            90: (0, 1, -1, 0, self.user_w, 0),
            180: (-1, 0, 0, -1, self.user_w, self.user_h),
            270: (0, -1, 1, 0, 0, self.user_h),
        }[self.rotation]
        if matrix:
            ops = [b"q %g %g %g %g %.3f %.3f cm" % matrix] + ops + [b"Q"]
        return b"\n".join(ops)
