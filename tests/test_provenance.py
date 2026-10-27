"""Provenance (V2-V4, V34): the command, the file, the PDF entry."""

import datetime

import pytest

from texpkg import provenance
from texpkg._internal import provenance_tex as tex
from texpkg.document import FileState
from texpkg.errors import DeclarationError
from texpkg_build._internal import generate

from .helpers import FIXTURES, golden

NOW = datetime.datetime(2026, 10, 25, 12, 30, 5, tzinfo=datetime.UTC)
LATER = NOW + datetime.timedelta(days=1)
FILE = "res/texpkg/acme-brand-provenance.sty"


def test_the_text_is_composed_of_the_parts_that_are_there():
    assert tex.info("acme", "1.2.0", "", "") == "acme 1.2.0"
    assert tex.info("acme", "1.2.0", "1.2.0-abc", "") == "acme 1.2.0, stamp 1.2.0-abc"
    assert (
        tex.info("acme", "1.2.0", "s", "2026-10-25T12:30:05Z")
        == "acme 1.2.0, stamp s, materialised 2026-10-25T12:30:05Z"
    )


def test_the_file_is_golden_and_reads_back():
    text = tex.companion("ab", "acme-brand", "1.2.0", "1.2.0-abc", "2026-10-25T12:30:05Z")
    golden(FIXTURES / "acme_brand" / "generated" / "acme-brand-provenance.sty", text)
    assert tex.read(text, "ab") == ("1.2.0-abc", "2026-10-25T12:30:05Z")
    assert tex.read("nothing", "ab") == ("", "")


def test_a_time_is_utc_text_and_the_clock_is_read_only_without_one():
    assert provenance.time_of(NOW) == "2026-10-25T12:30:05Z"
    zoned = NOW.astimezone(datetime.timezone(datetime.timedelta(hours=2)))
    assert provenance.time_of(zoned) == "2026-10-25T12:30:05Z"
    assert provenance.time_of(NOW.replace(tzinfo=None)) == "2026-10-25T12:30:05Z"
    assert tex.TIME.fullmatch(provenance.time_of(None))


def test_a_stamp_is_text_that_is_the_same_in_tex_and_in_a_pdf(acme_brand_tex):
    release = acme_brand_tex._bound.RELEASE
    assert provenance.stamp_of(None, release) == "1.2.0"
    assert provenance.stamp_of("1.2.0-3f9c2ab-dirty", release) == "1.2.0-3f9c2ab-dirty"
    for bad in ["a{b", "50%", "a\\b", "a_b", "é"]:
        with pytest.raises(DeclarationError) as raised:
            provenance.stamp_of(bad, release)
        assert raised.value.code == "TP-D006"


def test_a_package_without_a_prefix_cannot_declare_provenance():
    import dataclasses

    from acme_brand import dist
    from texmodel.package import Package

    bare = dataclasses.replace(dist, package=Package("bare", prefix="", builtin=False), kinds=(), assets=())
    with pytest.raises(DeclarationError) as raised:
        generate.render_sty(bare, "1.0.0")
    assert raised.value.code == "TP-B011"


def test_the_block_is_in_the_sty_and_not_in_the_authors_package(acme_brand_tex):
    from acme_brand import pkg

    sty = acme_brand_tex._bound.RELEASE.sty["acme-brand.sty"]
    assert "\\def\\abProvenanceStamp{}" in sty and "ProvenanceInfo" not in pkg.render()


@pytest.fixture
def doc(expert, tmp_path):
    return expert.create(tmp_path / "doc", expert.example())


def test_save_writes_a_provenance_file_for_each_package_with_the_stamp_and_the_pinned_time(doc):
    doc.save(now=NOW, stamp="1.2.0-3f9c2ab")
    text = (doc.path / FILE).read_text()
    assert "\\def\\abProvenanceStamp{1.2.0-3f9c2ab}" in text and "\\def\\abProvenanceTime{2026-10-25T12:30:05Z}" in text
    assert "(\\detokenize{acme-brand 1.2.0, stamp 1.2.0-3f9c2ab, materialised 2026-10-25T12:30:05Z})" in text
    assert "AbProvenance" in text


def test_a_second_save_keeps_the_time_while_nothing_else_is_written(doc):
    doc.save(now=NOW)
    first = (doc.path / FILE).read_text()
    doc.save(now=LATER)
    assert (doc.path / FILE).read_text() == first and "2026-10-25T12:30:05Z" in first


def test_a_new_stamp_or_a_changed_payload_materialises_again(doc):
    doc.save(now=NOW)
    doc.save(now=LATER, stamp="other")
    assert "2026-10-26T12:30:05Z" in (doc.path / FILE).read_text()
    (doc.path / "res/texpkg/acme-brand.sty").write_text("edited")
    doc.save(now=NOW + datetime.timedelta(days=2), stamp="other")
    assert "2026-10-27T12:30:05Z" in (doc.path / FILE).read_text()


def test_check_compares_the_provenance_by_stamp_not_by_time(doc):
    doc.save(now=NOW, stamp="s1")
    assert doc.check(stamp="s1").current
    report = doc.check()  # the release's version is not the stamp it was saved with
    assert report.files[doc.path / FILE] is FileState.CHANGED and not report.current
    (doc.path / FILE).unlink()
    assert doc.check(stamp="s1").files[doc.path / FILE] is FileState.MISSING


def test_check_of_an_unsaved_directory_reports_the_provenance_missing(doc):
    assert doc.check().files[doc.path / FILE] is FileState.MISSING


def test_a_dependent_writes_one_file_per_package_of_its_stack(tmp_path, acme_brand_tex):
    from texpkg_build.testing import load_declaration

    module = load_declaration("acme_deck:dist", version="2.0.0")
    slide = module.kinds.modules()["slide"]
    document = slide.create(tmp_path, slide.example())
    document.save(now=NOW)
    brand = (tmp_path / "res/texpkg/acme-brand-provenance.sty").read_text()
    assert (tmp_path / "res/texpkg/acme-deck-provenance.sty").is_file()
    assert "acme-brand 1.0.0, stamp 2.0.0, materialised 2026-10-25T12:30:05Z" in brand
    assert document.check().current and not document.check(stamp="other").current
