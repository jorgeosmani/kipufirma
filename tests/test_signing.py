import csv
import threading

import pytest

from helpers import make_pdf, make_pdf_with_js
from kipufirma.core.batch import (
    STATUS_ERROR,
    STATUS_OK,
    STATUS_SKIP,
    STATUS_WARN,
    export_report,
    preview_document,
    run_batch,
)
from kipufirma.core.naming import output_path, safe_stem
from kipufirma.core.pdf_inspect import inspect_pdf
from kipufirma.core.placement import KeywordRule, PlacementRule
from kipufirma.core.stamp import StampText, fit_text, wrap_words
from kipufirma.core.verify import verify_pdf_bytes


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def _simple(tmp_path, name="doc.pdf", text="Firma del docente"):
    return _write(tmp_path, name, make_pdf([(595, 842, [(72, 700, 12, "Informe"), (72, 200, 11, text)])]))


def test_sign_fixed_firmaec_compatible(tmp_path, credential, settings, trust):
    src = _simple(tmp_path)
    [r] = run_batch([src], credential, settings, trust)
    assert r.status == STATUS_OK, r.message
    assert r.output.name == "doc-firmado.pdf" and r.output.parent.name == "firmados"
    [rep] = verify_pdf_bytes(r.output.read_bytes(), trust)
    assert rep.ok and rep.trusted and rep.covers_whole_document
    assert rep.md_algorithm == "sha512" and rep.subfilter == "/adbe.pkcs7.detached"
    assert rep.signer_name == "MARÍA JOSÉ PEÑAFIEL ÁLVAREZ"
    assert rep.reason == settings.signing.reason
    assert src.read_bytes().startswith(b"%PDF")          # el original no se toca


def test_sign_pades_subfilter(tmp_path, credential, settings, trust):
    settings.signing.subfilter = "pades"
    [r] = run_batch([_simple(tmp_path)], credential, settings, trust)
    assert verify_pdf_bytes(r.output.read_bytes(), trust)[0].subfilter == "/ETSI.CAdES.detached"


def test_keyword_all_occurrences_produce_multiple_valid_signatures(tmp_path, credential, settings, trust):
    src = _write(tmp_path, "acta.pdf", make_pdf([
        (595, 842, [(72, 500, 11, "Firma:")]), (612, 792, [(300, 150, 11, "FIRMA:")])]))
    settings.placement = PlacementRule(mode="palabra", keyword=KeywordRule(keywords=["firma:"], occurrence="todas"))
    [r] = run_batch([src], credential, settings, trust)
    reps = verify_pdf_bytes(r.output.read_bytes(), trust)
    assert len(reps) == 2 and all(x.ok for x in reps)


def test_mixed_batch_keyword_per_document(tmp_path, credential, settings, trust):
    a = _write(tmp_path, "a.pdf", make_pdf([(595, 842, [(72, 600, 11, "Firma del Decano")])]))
    b = _write(tmp_path, "b.pdf", make_pdf([(595, 842, [(300, 100, 11, "Firma del Decano")]), (595, 842, [])]))
    c = _write(tmp_path, "c.pdf", make_pdf([(595, 842, [(72, 600, 11, "Sin palabra")])]))
    settings.placement = PlacementRule(mode="palabra", keyword=KeywordRule(keywords=["firma del decano"], fallback="omitir"))
    res = run_batch([a, b, c], credential, settings, trust)
    assert [r.status for r in res] == [STATUS_OK, STATUS_OK, STATUS_SKIP]
    assert "pág. 1" in res[1].placement


def test_invisible_and_resign_keeps_previous(tmp_path, credential, settings, trust):
    settings.placement = PlacementRule(mode="invisible")
    [r1] = run_batch([_simple(tmp_path)], credential, settings, trust)
    settings.placement = PlacementRule(mode="fija")
    [r2] = run_batch([r1.output], credential, settings, trust)
    assert r2.status == STATUS_WARN and "ya tenía 1 firma" in r2.warnings[0]
    reps = verify_pdf_bytes(r2.output.read_bytes(), trust)
    assert len(reps) == 2 and all(x.intact and x.valid for x in reps)


def test_suspicious_pdf_policy(tmp_path, credential, settings, trust):
    src = _write(tmp_path, "js.pdf", make_pdf_with_js())
    assert inspect_pdf(src).threats
    [r] = run_batch([src], credential, settings, trust)
    assert r.status == STATUS_WARN and "JavaScript" in r.warnings[0]
    settings.security.pdf_threat_policy = "bloquear"
    [r] = run_batch([src], credential, settings, trust)
    assert r.status == STATUS_ERROR and "peligroso" in r.message


def test_encrypted_pdf_rejected(tmp_path, credential, settings, trust):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter(clone_from=pypdf.PdfReader(_simple(tmp_path)))
    w.encrypt("secreta", algorithm="AES-128")
    out = tmp_path / "cifrado.pdf"
    with open(out, "wb") as f:
        w.write(f)
    [r] = run_batch([out], credential, settings, trust)
    assert r.status == STATUS_ERROR and "contraseña" in r.message


def test_bad_files_do_not_stop_batch(tmp_path, credential, settings, trust):
    bad = _write(tmp_path, "roto.pdf", b"esto no es un pdf")
    good = _simple(tmp_path)
    res = run_batch([bad, good], credential, settings, trust)
    assert [r.status for r in res] == [STATUS_ERROR, STATUS_OK]


def test_cancel(tmp_path, credential, settings, trust):
    ev = threading.Event()
    ev.set()
    res = run_batch([_simple(tmp_path)], credential, settings, trust, cancel=ev)
    assert res[0].status == STATUS_SKIP


def test_no_overwrite_and_report(tmp_path, credential, settings, trust):
    src = _simple(tmp_path)
    r1 = run_batch([src], credential, settings, trust)
    r2 = run_batch([src], credential, settings, trust)
    assert r1[0].output != r2[0].output and r2[0].output.name == "doc-firmado (2).pdf"
    rep = tmp_path / "informe.csv"
    export_report(r1 + r2, rep, "X")
    rows = list(csv.reader(open(rep, encoding="utf-8-sig"), delimiter=";"))
    assert len(rows) == 3 and rows[0][3] == "Estado"


def test_preview(tmp_path, settings):
    p = preview_document(_simple(tmp_path), settings)
    assert p.resolution and p.resolution.boxes and p.report.page_count == 1


def test_naming(tmp_path):
    assert safe_stem("CON") == "_CON"
    assert safe_stem('a<b>:c') == "a_b__c"
    src = tmp_path / "x.pdf"
    src.write_bytes(b"%PDF")
    assert output_path(src, None, "") != src


def test_stamp_text_fitting():
    assert wrap_words("JUAN CARLOS DE LA TORRE MONTESDEOCA", 12) == ["JUAN CARLOS", "DE LA TORRE", "MONTESDEOCA"]
    st = StampText("MARÍA JOSÉ PEÑAFIEL ÁLVAREZ DE LOS MONTEROS", footer_lines=("Fecha: 2026-10-29 10:00:00",))
    lay = fit_text(100, 50, st)
    assert 3 <= lay.name_size <= 11 and 1 <= len(lay.name_lines) <= 3
