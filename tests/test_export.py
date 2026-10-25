"""Export (phase 6: E1): the payload flat, a template and a README per kind, the provenance file."""

import datetime
import pathlib
import sys

import pytest

from texpkg.errors import PayloadError
from texpkg_build.testing import load_declaration

from .helpers import FIXTURES, golden

NOW = datetime.datetime(2026, 10, 25, 12, 30, 5, tzinfo=datetime.UTC)
EXPORT = [
    "NOTICE.txt",
    "README-expert.md",
    "README-vocab.md",
    "acme-brand-provenance.sty",
    "acme-brand.sty",
    "expert-template.tex",
    "lmroman10-regular.otf",
    "lockup.pdf",
    "vocab-template.tex",
]


def listing(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_the_export_is_the_whole_payload_flat_with_a_template_and_a_readme_per_kind(acme_brand_tex, tmp_path):
    written = acme_brand_tex.export(tmp_path / "out", now=NOW, stamp="1.2.0-abc")
    assert listing(tmp_path / "out") == EXPORT
    assert sorted(p.relative_to(tmp_path / "out").as_posix() for p in written) == EXPORT
    assert "materialised 2026-10-25T12:30:05Z" in (tmp_path / "out/acme-brand-provenance.sty").read_text()


def test_the_template_is_the_kinds_example_with_its_settings_and_no_search_path_lines(acme_brand_tex, tmp_path):
    acme_brand_tex.export(tmp_path, now=NOW)
    template = (tmp_path / "expert-template.tex").read_text()
    assert (
        "\\setlength{\\abFactGap}{3mm}" in template and "input@path" not in template and "graphicspath" not in template
    )
    golden(FIXTURES / "acme_brand" / "generated" / "expert-template.tex", template)


def test_the_readme_is_made_from_the_kinds_classes(acme_brand_tex, tmp_path):
    acme_brand_tex.export(tmp_path, now=NOW)
    text = (tmp_path / "README-expert.md").read_text()
    golden(FIXTURES / "acme_brand" / "generated" / "README-expert.md", text)
    assert "latexmk -lualatex expert-template.tex" in text and "`\\abFact[accent]{text}`" in text
    assert "`\\begin{abCard} ... \\end{abCard}`" in text and "`compact`, `wide`" in text


def test_an_export_into_a_directory_that_holds_it_writes_only_what_differs(acme_brand_tex, tmp_path):
    acme_brand_tex.export(tmp_path, now=NOW)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()}
    acme_brand_tex.export(tmp_path, now=NOW)
    assert {p: p.stat().st_mtime_ns for p in tmp_path.iterdir()} == before


def test_an_export_of_a_package_with_a_missing_file_writes_nothing(tmp_path):
    module = load_declaration("acme_brand:broken", version="1.2.0")
    with pytest.raises(PayloadError):
        module.export(tmp_path / "out")
    assert not (tmp_path / "out").exists()
    for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
        del sys.modules[name]


def test_a_profile_kind_is_exported_as_the_base_kind_it_expands_to(acme_brand_tex, tmp_path):
    module = load_declaration("acme_deck:dist", version="2.0.0")
    try:
        module.export(tmp_path, now=NOW)
        template = (tmp_path / "brief-template.tex").read_text()
        assert "\\setlength{\\abFactGap}{4mm}" in template and "\\begin{abDeck}" in template
        assert "`\\abFact[accent]{text}`" in (tmp_path / "README-brief.md").read_text()
        assert (tmp_path / "acme-brand.sty").is_file() and (tmp_path / "acme-deck.sty").is_file()
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] in ("acme_deck_tex", "acme_deck")]:
            del sys.modules[name]
