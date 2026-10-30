"""Reglas de ubicación de la firma visible y su resolución por documento.

Modos:

* ``fija``: misma posición en todos los documentos, expresada como esquina
  de anclaje + desplazamiento (así se adapta a A4, carta, oficio o páginas
  apaisadas, a diferencia de FirmaEC que exige A4).
* ``palabra``: busca palabras clave y coloca la firma relativa a ellas
  (debajo, encima, a la derecha, a la izquierda o sobre el texto). Si no se
  encuentran, aplica un plan alternativo: omitir, posición fija o invisible.
* ``invisible``: firma sin sello visual (válida igual que la visible).
* Además, cada documento puede tener una ubicación **manual** que el usuario
  dibuja en la vista previa y que prevalece sobre la regla general.

Todas las medidas están en puntos tipográficos (1 pt = 1/72 pulgada =
0,3528 mm) y en espacio *visual* (ver geometry.py).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from kipufirma.core.errors import KeywordNotFoundError, PlacementError
from kipufirma.core.geometry import PageGeom, Rect
from kipufirma.core.locator import KeywordMatch

PAGE_MODES = ("ultima", "primera", "numero", "todas")
ANCHORS = ("inf-der", "inf-izq", "sup-der", "sup-izq")
POSITIONS = ("debajo", "encima", "derecha", "izquierda", "sobre")
ALIGNS = ("izquierda", "centro", "derecha")
OCCURRENCES = ("ultima", "primera", "todas")
FALLBACKS = ("omitir", "fija", "invisible")


@dataclass
class StampSize:
    # Tamaño por defecto igual al de FirmaEC (RectanguloUtil: 110 × 36 pt).
    width: float = 110.0
    height: float = 36.0


@dataclass
class FixedRule:
    page_mode: str = "ultima"
    page_number: int = 1                 # 1-based, para page_mode == "numero"
    anchor: str = "inf-der"
    dx: float = 56.0                      # distancia horizontal al borde (pt)
    dy: float = 72.0                      # distancia vertical al borde (pt)

    @staticmethod
    def from_visual_rect(rect: Rect, page_w: float, page_h: float,
                         page_mode: str = "ultima", page_number: int = 1) -> "FixedRule":
        """Convierte un recuadro dibujado en la vista previa a ancla+offset,
        eligiendo la esquina más cercana al centro del recuadro."""
        cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        right = cx > page_w / 2
        top = cy > page_h / 2
        anchor = ("sup-" if top else "inf-") + ("der" if right else "izq")
        dx = page_w - rect.x1 if right else rect.x0
        dy = page_h - rect.y1 if top else rect.y0
        return FixedRule(page_mode, page_number, anchor, round(dx, 1), round(dy, 1))

    def visual_rect(self, page_w: float, page_h: float, size: StampSize) -> Rect:
        w, h = size.width, size.height
        x0 = page_w - self.dx - w if self.anchor.endswith("der") else self.dx
        y0 = page_h - self.dy - h if self.anchor.startswith("sup") else self.dy
        return Rect(x0, y0, x0 + w, y0 + h)


@dataclass
class KeywordRule:
    keywords: list[str] = field(default_factory=lambda: ["Firma"])
    position: str = "debajo"
    align: str = "izquierda"
    gap: float = 4.0                      # separación entre texto y sello (pt)
    dx: float = 0.0
    dy: float = 0.0
    occurrence: str = "ultima"
    fallback: str = "fija"


@dataclass
class PlacementRule:
    mode: str = "fija"                     # "fija" | "palabra" | "invisible"
    size: StampSize = field(default_factory=StampSize)
    fixed: FixedRule = field(default_factory=FixedRule)
    keyword: KeywordRule = field(default_factory=KeywordRule)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict | None) -> "PlacementRule":
        d = d or {}
        def pick(cls, data):
            names = cls.__dataclass_fields__.keys()
            return cls(**{k: v for k, v in (data or {}).items() if k in names})
        rule = PlacementRule(
            mode=d.get("mode", "fija"),
            size=pick(StampSize, d.get("size")),
            fixed=pick(FixedRule, d.get("fixed")),
            keyword=pick(KeywordRule, d.get("keyword")),
        )
        rule.validate()
        return rule

    def validate(self) -> None:
        if self.mode not in ("fija", "palabra", "invisible"):
            raise PlacementError(f"Modo de ubicación desconocido: {self.mode}")
        if not (20 <= self.size.width <= 600 and 10 <= self.size.height <= 400):
            raise PlacementError("El tamaño del sello está fuera de rango (20–600 × 10–400 pt).")
        f, k = self.fixed, self.keyword
        if f.page_mode not in PAGE_MODES or f.anchor not in ANCHORS:
            raise PlacementError("Parámetros de posición fija inválidos.")
        if f.page_mode == "numero" and int(f.page_number) < 1:
            raise PlacementError("El número de página debe ser 1 o mayor.")
        if (k.position not in POSITIONS or k.align not in ALIGNS
                or k.occurrence not in OCCURRENCES or k.fallback not in FALLBACKS):
            raise PlacementError("Parámetros de búsqueda por palabra clave inválidos.")
        if self.mode == "palabra" and not any(x.strip() for x in k.keywords):
            raise PlacementError("Escriba al menos una palabra clave.")


@dataclass
class ManualBox:
    """Ubicación dibujada a mano para un documento concreto."""
    page_index: int
    rect: Rect                              # espacio visual


@dataclass
class SigBox:
    page_index: int
    user_rect: Rect
    visual_rect: Rect
    rotation: int = 0


@dataclass
class Resolution:
    boxes: list[SigBox] = field(default_factory=list)
    invisible: bool = False
    skipped: bool = False
    source: str = ""                        # "fija" | "palabra" | "manual" | "invisible" | "alternativa"
    note: str = ""

    @property
    def summary(self) -> str:
        if self.skipped:
            return "Se omitirá: " + self.note
        if self.invisible:
            return "Firma invisible" + (f" ({self.note})" if self.note else "")
        pages = ", ".join(str(b.page_index + 1) for b in self.boxes)
        label = {"fija": "Posición fija", "palabra": "Palabra clave", "manual": "Manual",
                 "alternativa": "Posición fija (alternativa)"}.get(self.source, self.source)
        return f"{label} · pág. {pages}" + (f" · {self.note}" if self.note else "")


def _pages_for(rule: FixedRule, count: int) -> list[int]:
    if rule.page_mode == "primera":
        return [0]
    if rule.page_mode == "todas":
        return list(range(count))
    if rule.page_mode == "numero":
        return [min(int(rule.page_number), count) - 1]
    return [count - 1]


def _box(geom: PageGeom, page_index: int, visual: Rect) -> SigBox:
    visual = geom.clamp_visual(visual)
    return SigBox(page_index, geom.rect_to_user(visual), visual, geom.rotation)


def resolve_fixed(rule: PlacementRule, pages: list[PageGeom]) -> Resolution:
    res = Resolution(source="fija")
    for i in _pages_for(rule.fixed, len(pages)):
        w, h = pages[i].visual_size
        res.boxes.append(_box(pages[i], i, rule.fixed.visual_rect(w, h, rule.size)))
    return res


def stamp_rect_for_match(match_visual: list[Rect], k: KeywordRule, size: StampSize) -> Rect:
    w, h = size.width, size.height
    first, last = match_visual[0], match_visual[-1]
    full = first
    for r in match_visual[1:]:
        full = full.union(r)

    def halign(ref: Rect) -> float:
        if k.align == "centro":
            return (ref.x0 + ref.x1) / 2 - w / 2
        if k.align == "derecha":
            return ref.x1 - w
        return ref.x0

    if k.position == "debajo":
        x0, y0 = halign(last), last.y0 - k.gap - h
    elif k.position == "encima":
        x0, y0 = halign(first), first.y1 + k.gap
    elif k.position == "derecha":
        x0, y0 = last.x1 + k.gap, (last.y0 + last.y1) / 2 - h / 2
    elif k.position == "izquierda":
        x0, y0 = first.x0 - k.gap - w, (first.y0 + first.y1) / 2 - h / 2
    else:  # sobre: centrado sobre el texto
        x0, y0 = (full.x0 + full.x1) / 2 - w / 2, (full.y0 + full.y1) / 2 - h / 2
    return Rect(x0 + k.dx, y0 + k.dy, x0 + k.dx + w, y0 + k.dy + h)


def resolve_keyword(rule: PlacementRule, pages: list[PageGeom],
                    finder: Callable[[list[str]], list[KeywordMatch]]) -> Resolution:
    k = rule.keyword
    matches = finder(k.keywords)
    if not matches:
        err = KeywordNotFoundError(k.keywords)
        if k.fallback == "omitir":
            return Resolution(skipped=True, source="palabra", note=str(err))
        if k.fallback == "invisible":
            return Resolution(invisible=True, source="alternativa", note="palabra clave no encontrada")
        res = resolve_fixed(rule, pages)
        res.source, res.note = "alternativa", "palabra clave no encontrada"
        return res
    ordered = sorted(matches, key=lambda m: (m.page_index, -m.bbox.y1, m.bbox.x0))
    if k.occurrence == "primera":
        chosen = ordered[:1]
    elif k.occurrence == "ultima":
        chosen = ordered[-1:]
    else:
        chosen = ordered
    res = Resolution(source="palabra", note=f"«{chosen[0].keyword}»"
                     + (f" ×{len(chosen)}" if len(chosen) > 1 else ""))
    for m in chosen:
        g = pages[m.page_index]
        vis_lines = [g.rect_to_visual(r) for r in m.lines]
        # En espacio visual el orden de lectura es de arriba hacia abajo.
        vis_lines.sort(key=lambda r: (-r.y1, r.x0))
        res.boxes.append(_box(g, m.page_index, stamp_rect_for_match(vis_lines, k, rule.size)))
    return res


def resolve_manual(boxes: list[ManualBox], pages: list[PageGeom]) -> Resolution:
    res = Resolution(source="manual")
    for b in boxes:
        if not 0 <= b.page_index < len(pages):
            raise PlacementError("La ubicación manual apunta a una página que no existe.")
        res.boxes.append(_box(pages[b.page_index], b.page_index, b.rect))
    return res


def resolve(rule: PlacementRule, pages: list[PageGeom],
            finder: Callable[[list[str]], list[KeywordMatch]] | None = None,
            manual: list[ManualBox] | None = None) -> Resolution:
    if not pages:
        raise PlacementError("El documento no tiene páginas.")
    if manual:
        return resolve_manual(manual, pages)
    if rule.mode == "invisible":
        return Resolution(invisible=True, source="invisible")
    if rule.mode == "palabra":
        if finder is None:
            raise PlacementError("No hay motor de búsqueda de texto disponible.")
        return resolve_keyword(rule, pages, finder)
    return resolve_fixed(rule, pages)
