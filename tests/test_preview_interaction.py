"""Colocación interactiva: sello fantasma, clic instantáneo, flechas y migración."""
import pytest

pytest.importorskip("PySide6")


@pytest.fixture()
def view(tmp_path):
    from PySide6.QtWidgets import QApplication

    from helpers import make_pdf
    app = QApplication.instance() or QApplication([])
    from kipufirma.gui.preview import PreviewView
    v = PreviewView()
    v.resize(600, 800)
    v.show()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(make_pdf([(595, 842, [(72, 300, 11, "Firma")]), (612, 792, [])]))
    v.set_document(pdf, 0)
    app.processEvents()
    yield v, app
    v.close()


def test_ghost_follows_mouse_and_click_places_exactly_there(view):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    v, app = view
    got = []
    v.rectChosen.connect(lambda page, rect: got.append((page, rect)))
    target_scene = v.mapFromScene(300 * v._scale, (842 - 200) * v._scale)    # punto (300, 200) en pt
    QTest.mouseMove(v.viewport(), target_scene)
    app.processEvents()
    assert v._ghost is not None and v._ghost.isVisible()
    ghost = v._ghost.rect()
    QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, target_scene)
    app.processEvents()
    assert len(got) == 1
    page, rect = got[0]
    assert page == 0
    assert rect.width == pytest.approx(110) and rect.height == pytest.approx(36)
    assert (rect.x0 + rect.x1) / 2 == pytest.approx(300, abs=2)               # centrado en el puntero
    assert (rect.y0 + rect.y1) / 2 == pytest.approx(200, abs=2)
    placed = v._to_scene(rect)
    assert placed.center().x() == pytest.approx(ghost.center().x(), abs=1)   # coincide con el fantasma
    assert [b for b in v._boxes if b[0] == 0]                                # dibujado al instante
    QTest.mouseMove(v.viewport(), QPoint(2, 2))


def test_ghost_stays_inside_page(view):
    from PySide6.QtCore import QPointF
    v, _ = view
    r = v.stamp_rect_at(QPointF(0, 0))                     # esquina superior izquierda
    assert r.x0 >= 2 and r.y1 <= 842 - 2


def test_arrow_keys_nudge(view):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from kipufirma.core.geometry import Rect
    v, app = view
    got = []
    v.rectChosen.connect(lambda page, rect: got.append(rect))
    v.show_placed(0, Rect(100, 100, 210, 136))
    QTest.keyClick(v, Qt.Key_Right)
    QTest.keyClick(v, Qt.Key_Up, Qt.ShiftModifier)
    assert got[0].x0 == pytest.approx(101) and got[1].y0 == pytest.approx(110)


def test_same_document_is_not_reopened(view):
    v, _ = view
    doc = v._doc
    v.set_document(v.path, 1)
    assert v._doc is doc and v.page_index == 1


def test_old_config_migrates_to_firmaec_size():
    from kipufirma.core.config import Settings
    s = Settings.from_dict({"schema": 1, "placement": {"size": {"width": 170, "height": 55}},
                            "signing": {"show_date_in_stamp": True}})
    assert (s.placement.size.width, s.placement.size.height) == (110, 36)
    assert s.signing.show_date_in_stamp is False
    s2 = Settings.from_dict({"schema": 2, "placement": {"size": {"width": 200, "height": 60}}})
    assert s2.placement.size.width == 200


def test_preview_cache_avoids_reanalysis(tmp_path, settings, monkeypatch):
    from helpers import make_pdf
    from kipufirma.core import batch
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(make_pdf([(595, 842, [])]))
    calls = []
    real = batch.inspect_pdf
    monkeypatch.setattr(batch, "inspect_pdf", lambda *a, **k: calls.append(1) or real(*a, **k))
    batch.preview_document(pdf, settings)
    batch.preview_document(pdf, settings)
    assert len(calls) == 1
