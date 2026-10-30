import pypdfium2 as pdfium
import pytest

from helpers import make_pdf
from kipufirma.core.geometry import PageGeom, Rect
from kipufirma.core.locator import find_keywords, normalize_text
from kipufirma.core.pdf_inspect import inspect_pdf
from kipufirma.core.placement import FixedRule, KeywordRule, ManualBox, PlacementRule, StampSize, resolve

A4 = PageGeom(0, 0, 595, 842)


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_rotation_round_trip(rot):
    g = PageGeom(10, 20, 605, 862, rot)
    for x, y in [(10, 20), (300, 400), (605, 862)]:
        X, Y = g.to_visual(x, y)
        assert g.to_user(X, Y) == pytest.approx((x, y))
    W, H = g.visual_size
    assert (W, H) == ((842, 595) if rot in (90, 270) else (595, 842))


def test_clamp_keeps_inside():
    r = A4.clamp_visual(Rect(560, -20, 700, 30))
    assert r.x1 <= 595 and r.y0 >= 0 and r.width == 140


@pytest.mark.parametrize("page", [(595, 842), (612, 792), (842, 595), (612, 1008)])
def test_fixed_adapts_to_page_size(page):
    w, h = page
    rule = PlacementRule(mode="fija", size=StampSize(170, 55), fixed=FixedRule("ultima", 1, "inf-der", 50, 60))
    res = resolve(rule, [PageGeom(0, 0, w, h)] * 3)
    b = res.boxes[0]
    assert b.page_index == 2
    assert b.user_rect.x1 == pytest.approx(w - 50) and b.user_rect.y0 == pytest.approx(60)


def test_from_visual_rect_round_trip():
    r = Rect(400, 70, 570, 125)
    rule = FixedRule.from_visual_rect(r, 595, 842)
    assert rule.anchor == "inf-der"
    assert rule.visual_rect(595, 842, StampSize(170, 55)) == Rect(400, 70, 570, 125)
    top = FixedRule.from_visual_rect(Rect(40, 760, 210, 815), 595, 842)
    assert top.anchor == "sup-izq" and top.dx == 40 and top.dy == 27


@pytest.mark.parametrize("mode,expected", [("primera", [0]), ("ultima", [3]), ("todas", [0, 1, 2, 3])])
def test_page_modes(mode, expected):
    rule = PlacementRule(fixed=FixedRule(page_mode=mode))
    assert [b.page_index for b in resolve(rule, [A4] * 4).boxes] == expected
    rule.fixed.page_mode, rule.fixed.page_number = "numero", 9
    assert resolve(rule, [A4] * 4).boxes[0].page_index == 3          # se limita a la última


def test_normalize():
    assert normalize_text("  FIRMA   del\r\nDécano ") == "firma del decano"


def _doc(data):
    return pdfium.PdfDocument(data)


def test_keyword_search_accents_case():
    data = make_pdf([(595, 842, [(72, 700, 12, "Contrato"), (72, 200, 11, "Firma del Décano:")])])
    doc = _doc(data)
    m = find_keywords(doc, ["no existe", "firma del decano"])
    assert len(m) == 1 and m[0].keyword == "firma del decano"
    bb = m[0].bbox
    assert 70 < bb.x0 < 75 and 195 < bb.y0 < 205
    assert find_keywords(doc, ["zzz"]) == []


def _keyword_rule(**kw):
    return PlacementRule(mode="palabra", size=StampSize(170, 55), keyword=KeywordRule(**kw))


def test_keyword_below_left_aligned():
    data = make_pdf([(595, 842, [(100, 300, 11, "Firma del docente")])])
    doc = _doc(data)
    rule = _keyword_rule(keywords=["Firma del docente"], position="debajo", gap=4)
    res = resolve(rule, [A4], lambda k: find_keywords(doc, k))
    b = res.boxes[0].visual_rect
    assert res.source == "palabra"
    assert b.x0 == pytest.approx(100, abs=2)
    assert b.y1 == pytest.approx(300 - 4, abs=4)            # justo debajo del texto


def test_keyword_occurrences_and_fallbacks():
    data = make_pdf([(595, 842, [(72, 600, 11, "Firma"), (300, 200, 11, "Firma")]),
                     (595, 842, [(72, 400, 11, "Firma")])])
    doc = _doc(data)
    finder = lambda k: find_keywords(doc, k)  # noqa: E731
    pages = [A4, A4]
    assert [b.page_index for b in resolve(_keyword_rule(keywords=["Firma"], occurrence="todas"), pages, finder).boxes] == [0, 0, 1]
    last = resolve(_keyword_rule(keywords=["Firma"], occurrence="ultima"), pages, finder).boxes
    assert last[0].page_index == 1
    first = resolve(_keyword_rule(keywords=["Firma"], occurrence="primera"), pages, finder).boxes[0]
    assert first.page_index == 0 and first.visual_rect.y1 < 600
    for fb, check in [("omitir", lambda r: r.skipped), ("invisible", lambda r: r.invisible),
                      ("fija", lambda r: r.source == "alternativa" and r.boxes)]:
        assert check(resolve(_keyword_rule(keywords=["Inexistente"], fallback=fb), pages, finder))


def test_keyword_on_rotated_page_is_visually_below():
    # Página girada 90°: el texto en espacio de usuario aparece girado al verla.
    data = make_pdf([(595, 842, [(100, 300, 11, "Firma del docente")], 90)])
    doc = _doc(data)
    rep = inspect_pdf(__import__("pathlib").Path("x.pdf"), data)
    g = rep.pages[0]
    assert g.rotation == 90
    res = resolve(_keyword_rule(keywords=["Firma del docente"], position="debajo"), rep.pages,
                  lambda k: find_keywords(doc, k))
    box = res.boxes[0]
    kw_vis = g.rect_to_visual(find_keywords(doc, ["Firma del docente"])[0].bbox)
    assert box.visual_rect.y1 <= kw_vis.y0                    # debajo, tal como se ve
    vr = g.rect_to_visual(box.user_rect)
    assert (vr.x0, vr.y0, vr.x1, vr.y1) == pytest.approx((box.visual_rect.x0, box.visual_rect.y0, box.visual_rect.x1, box.visual_rect.y1), abs=0.01)
    assert box.rotation == 90 and box.user_rect.width == pytest.approx(box.visual_rect.height)


def test_manual_overrides_rule():
    rule = PlacementRule(mode="invisible")
    res = resolve(rule, [A4, A4], manual=[ManualBox(1, Rect(10, 10, 180, 65))])
    assert res.source == "manual" and res.boxes[0].page_index == 1


def test_rule_serialization_and_validation():
    r = PlacementRule(mode="palabra", keyword=KeywordRule(keywords=["Firma"]))
    assert PlacementRule.from_dict(r.to_dict()) == r
    with pytest.raises(Exception):
        PlacementRule.from_dict({"mode": "palabra", "keyword": {"keywords": [" "]}})
