"""Búsqueda de palabras clave en el texto del PDF con coordenadas.

* Insensible a mayúsculas, tildes y diéresis («FIRMA DEL DECANO» encuentra
  «Firma del decano» y «firma del décano»).
* Tolera espacios múltiples y saltos de línea dentro de la frase.
* Devuelve los rectángulos en espacio de usuario, por línea, para poder
  ubicar la firma debajo de la última línea o encima de la primera.

Nota: solo funciona con PDF que tienen texto. Un documento escaneado sin OCR
no contiene texto: use la ubicación fija o manual, o aplíquele OCR antes.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from kipufirma.core.geometry import Rect

_SPACES = {"\r", "\n", "\t", "\u00a0", "\u2007", "\u202f", "\ufffe", "\x02"}


def normalize_char(c: str) -> str:
    if c in _SPACES or c.isspace():
        return " "
    decomposed = unicodedata.normalize("NFD", c)
    base = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return base.casefold()


def normalize_text(s: str) -> str:
    out: list[str] = []
    for c in s:
        n = normalize_char(c)
        if n == " " and (not out or out[-1] == " "):
            continue
        out.append(n)
    return "".join(out).strip()


@dataclass
class KeywordMatch:
    page_index: int
    keyword: str
    lines: list[Rect]            # un rectángulo por línea, en espacio de usuario

    @property
    def bbox(self) -> Rect:
        r = self.lines[0]
        for x in self.lines[1:]:
            r = r.union(x)
        return r


class PageText:
    """Texto normalizado de una página con mapa a índices de caracteres PDFium."""

    def __init__(self, page: pdfium.PdfPage) -> None:
        self.page = page
        self.textpage = page.get_textpage()
        n = self.textpage.count_chars()
        chars = [chr(pdfium_c.FPDFText_GetUnicode(self.textpage.raw, i) or 32) for i in range(n)]
        self.norm_chars: list[str] = []
        self.index_map: list[int] = []
        for i, c in enumerate(chars):
            for nc in normalize_char(c):
                if nc == " " and (not self.norm_chars or self.norm_chars[-1] == " "):
                    continue
                self.norm_chars.append(nc)
                self.index_map.append(i)
        self.text = "".join(self.norm_chars)

    def close(self) -> None:
        self.textpage.close()
        self.page.close()

    def find_all(self, keyword: str) -> list[list[Rect]]:
        needle = normalize_text(keyword)
        if not needle:
            return []
        results = []
        start = 0
        while True:
            pos = self.text.find(needle, start)
            if pos < 0:
                break
            first = self.index_map[pos]
            last = self.index_map[pos + len(needle) - 1]
            count = last - first + 1
            n_rects = self.textpage.count_rects(first, count)
            rects = []
            for k in range(n_rects):
                x0, y0, x1, y1 = self.textpage.get_rect(k)
                if x1 - x0 > 0.1 and y1 - y0 > 0.1:
                    rects.append(Rect(x0, y0, x1, y1))
            if rects:
                results.append(rects)
            start = pos + max(len(needle), 1)
        return results


def find_keywords(doc: pdfium.PdfDocument, keywords: list[str],
                  pages: list[int] | None = None) -> list[KeywordMatch]:
    """Busca, en orden de prioridad, cada palabra clave. Devuelve las
    coincidencias de la PRIMERA palabra clave que aparezca en el documento
    (así se pueden listar alternativas: «Firma del docente», «Firma:»)."""
    keywords = [k for k in (kw.strip() for kw in keywords) if k]
    page_ids = pages if pages is not None else list(range(len(doc)))
    texts: dict[int, PageText] = {}
    try:
        for kw in keywords:
            found: list[KeywordMatch] = []
            for i in page_ids:
                if i not in texts:
                    page = doc[i]
                    texts[i] = PageText(page)
                for lines in texts[i].find_all(kw):
                    found.append(KeywordMatch(i, kw, lines))
            if found:
                return found
        return []
    finally:
        for t in texts.values():
            t.close()


def page_has_text(doc: pdfium.PdfDocument, index: int) -> bool:
    page = doc[index]
    tp = page.get_textpage()
    try:
        return tp.count_chars() > 0
    finally:
        tp.close()
        page.close()
