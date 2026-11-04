"""Local overrides (O1-O8): a file beside a document that changes a package's TeX, reported by `doc.sty`."""

import json
import sys

import pytest

from texpkg.document import OverrideKind
from texpkg.errors import StyEditError
from texpkg_build.testing import load_declaration

LOCAL = "acme-brand-local.sty"
PAYLOAD = "res/texpkg/acme-brand.sty"
DRAFT = "\\renewcommand{\\abTitle}[1]{#1}\n"


@pytest.fixture
def doc(expert, tmp_path):
    made = expert.create(tmp_path / "doc", expert.example())
    made.save()
    return made


def newer(expert, doc):
    """The document as the next release loads it; that release's `.sty` differs by its version."""
    return load_declaration("acme_brand:dist", version="1.3.0").kinds.modules()["expert"].load(doc.path)


def recorded(doc):
    return json.loads((doc.path / "_texpkg/template.json").read_text()).get("overrides")


def test_a_document_on_the_packages_own_tex_has_no_overrides(acme_brand_tex, doc):
    assert doc.sty == acme_brand_tex.STY and doc.sty.overrides == () and doc.check().overrides == ()
    doc.save()
    assert recorded(doc) is None  # the template state of a document without any is what it always was


def test_a_local_file_is_reported_on_its_packages_sty_and_by_check(doc):
    (doc.path / LOCAL).write_text(DRAFT)
    (found,) = doc.sty.overrides
    assert doc.sty.top.overrides == (found,)
    assert (found.path, found.kind, found.text) == (doc.path / LOCAL, OverrideKind.LOCAL, DRAFT)
    assert (found.against, found.stale) == (None, False)  # no save has seen it
    assert doc.check().overrides == (found,)


def test_an_override_names_what_it_redefines_and_what_no_package_declares(doc):
    (doc.path / LOCAL).write_text(
        "\\renewcommand{\\abTitle}[1]{#1}\n\\renewenvironment{abCard}{}{}\n\\renewcommand{\\abNope}{}\n"
        "\\renewcommand{\\maketitle}{}\n\\def\\abFactual{}\n"
    )
    (found,) = doc.sty.overrides
    assert found.names == ("abCard", "abNope", "abTitle", "maketitle")  # a `\\def` is not read
    assert found.unknown == ("abNope", "maketitle")


def test_a_local_file_in_the_payload_directory_is_found_as_tex_finds_it(doc):
    (doc.path / "res/texpkg" / LOCAL).write_text(DRAFT)
    assert [o.path for o in doc.sty.overrides] == [doc.path / "res/texpkg" / LOCAL]


def test_a_root_copy_of_the_sty_is_a_shadow_and_a_local_file_beside_it_is_not_hidden(doc):
    (doc.path / "acme-brand.sty").write_text("copy")
    (doc.path / LOCAL).write_text(DRAFT)
    assert [o.kind for o in doc.sty.overrides] == [OverrideKind.SHADOW, OverrideKind.LOCAL]


def test_save_keeps_a_local_file_and_records_the_release_it_saw(doc):
    (doc.path / LOCAL).write_text(DRAFT)
    assert not doc.check().current  # the template state a save writes now records it
    doc.save()
    assert (doc.path / LOCAL).read_text() == DRAFT
    assert doc.sty.top.overrides[0].against == "1.2.0"
    assert doc.check().current  # an override does not make the document out of date


def test_a_new_text_is_not_against_any_release_until_a_save_sees_it(doc):
    (doc.path / LOCAL).write_text(DRAFT)
    doc.save()
    (doc.path / LOCAL).write_text(DRAFT + "% more\n")
    assert doc.sty.top.overrides[0].against is None


def test_a_release_that_changes_the_sty_makes_an_override_stale_and_a_save_does_not_hide_it(expert, doc):
    (doc.path / LOCAL).write_text(DRAFT)
    doc.save()
    assert doc.template_changes() == ()
    loaded = newer(expert, doc)
    (found,) = loaded.sty.overrides
    assert (found.against, found.stale) == ("1.2.0", True)
    assert {c.setting: (c.old, c.new) for c in loaded.template_changes()}[f"override {LOCAL}"] == ("1.2.0", "1.3.0")
    loaded.save()
    assert loaded.sty.top.overrides[0].stale
    (doc.path / LOCAL).write_text(DRAFT + "% ported\n")
    loaded.save()
    assert (loaded.sty.top.overrides[0].against, loaded.sty.top.overrides[0].stale) == ("1.3.0", False)


def test_a_removed_override_leaves_no_record(doc):
    (doc.path / LOCAL).write_text(DRAFT)
    doc.save()
    (doc.path / LOCAL).unlink()
    doc.save()
    assert recorded(doc) is None


def test_save_refuses_an_edited_sty_of_the_payload_and_writes_nothing(doc):
    edited = doc.path / PAYLOAD
    edited.write_text(edited.read_text() + "% a draft\n")
    before = (doc.path / "_texpkg/template.json").read_text()
    with pytest.raises(StyEditError, match="acme-brand.sty") as refused:
        doc.save()
    assert refused.value.code == "TP-D009" and refused.value.files == (edited,)
    assert "% a draft" in edited.read_text() and (doc.path / "_texpkg/template.json").read_text() == before
    doc.save(force=True)
    assert "% a draft" not in edited.read_text()


def test_a_new_releases_sty_is_not_an_edit(expert, doc):
    loaded = newer(expert, doc)
    loaded.save()
    assert "v1.3.0" in (doc.path / PAYLOAD).read_text()


def test_a_dependents_stack_reports_each_packages_override_top_first(acme_brand_tex, tmp_path):
    module = load_declaration("acme_deck:dist", version="2.0.0")
    try:
        slide = module.kinds.modules()["slide"]
        made = slide.create(tmp_path / "doc", slide.example())
        (made.path / LOCAL).write_text(DRAFT)
        (made.path / "acme-deck-local.sty").write_text("% deck\n")
        assert [o.path.name for o in made.sty.overrides] == ["acme-deck-local.sty", LOCAL]
        assert [o.path.name for o in made.sty.bases[0].overrides] == [LOCAL]
        assert module.STY.overrides == ()  # the wheel knows no directory
        (made.path / "acme-deck-local.sty").write_text(DRAFT)
        assert made.sty.top.overrides[0].unknown == ()  # the base's names are the stack's
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] in ("acme_deck_tex", "acme_deck")]:
            del sys.modules[name]
