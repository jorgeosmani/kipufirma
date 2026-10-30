"""Prueba de humo de la interfaz (sin pantalla: QT_QPA_PLATFORM=offscreen)."""
import pytest

pytest.importorskip("PySide6")


def test_main_window_builds_and_resolves(tmp_path, settings):
    from PySide6.QtWidgets import QApplication

    from helpers import make_pdf
    app = QApplication.instance() or QApplication([])
    from kipufirma.gui.main_window import MainWindow
    from kipufirma.gui.theme import apply_theme
    apply_theme(app, "claro")
    w = MainWindow(settings)
    w.show()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(make_pdf([(595, 842, [(72, 300, 11, "Firma del docente")])]))
    w.sign_page.add_paths([pdf])
    w.sign_page._resolver.wait(5000)
    app.processEvents()
    assert w.sign_page.docs[0]["preview"] is not None
    assert "Posición fija" in w.sign_page.table.item(0, 2).text()
    # Cambiar a palabra clave y comprobar que se recalcula
    w.sign_page.rb_keyword.setChecked(True)
    w.sign_page.k_words.setPlainText("firma del docente")
    w.sign_page._resolve_timer.stop()
    w.sign_page._resolve_all()
    w.sign_page._resolver.wait(5000)
    app.processEvents()
    assert "Palabra clave" in w.sign_page.table.item(0, 2).text()
    for i in range(5):
        w.nav.setCurrentRow(i)
        app.processEvents()
    w.close()
