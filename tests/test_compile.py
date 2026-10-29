"""The compile suite: a saved document directory is accepted by TeX with only its payload beside it.

Skipped without the reference image; TEXPKG_REQUIRE_TEX=1 (CI) makes that a failure. The image is
TEXPKG_TEST_IMAGE, else `texmodel-test` (texmodel's `bin/test-image.sh`).
"""

import os
import pathlib
from types import ModuleType

import pytest
from texmodel_build.compiler import Compiler

from texpkg_build.testing import load_declaration

from . import projects, venvs

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

CASES = [("expert", "deck.tex"), ("expert", "deck-compact.tex"), ("expert", "deck-wide.tex"), ("vocab", "glossary.tex")]


def saved(module: ModuleType, kind: str, root: pathlib.Path) -> pathlib.Path:
    """A document directory as `save` leaves it: the kind's payload, the `.tex` files, the states."""
    kind_module = module.kinds.modules()[kind]
    kind_module.create(root, kind_module.example()).save()
    return root


@pytest.mark.parametrize(("kind", "name"), CASES)
def test_a_saved_document_compiles_with_only_its_payload(acme_brand_tex, compiler: Compiler, tmp_path, kind, name):
    root = saved(acme_brand_tex, kind, tmp_path / "doc")
    result = compiler.compile(root / name, tmp_path / "out")
    result.raise_for_status()
    assert result.pages == 1


def test_a_missing_lockup_is_a_compile_error_not_a_silent_fallback(acme_brand_tex, compiler: Compiler, tmp_path):
    root = saved(acme_brand_tex, "expert", tmp_path / "doc")
    (root / "res" / "texpkg" / "lockup.pdf").unlink()
    assert not compiler.compile(root / "deck.tex", tmp_path / "out").ok


SAVE = """
import sys
from acme_deck_tex.kinds import slide, vocab
for kind, name in ((slide, "slide"), (vocab, "vocab")):
    kind.create(f"{sys.argv[1]}/{name}", kind.example()).save()
"""


def test_documents_saved_by_an_installed_dependent_compile_with_nothing_else(brand_site, compiler, tmp_path):
    built = projects.wheel(
        projects.author_project(tmp_path / "deck", declaration="acme_deck", project="acme-deck-tex"), tmp_path / "dist"
    )
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, brand_site)
    venvs.install(python, built)
    venvs.run(python, SAVE, tmp_path / "docs", cwd=tmp_path)
    for name in ("slide/slide.tex", "vocab/glossary.tex"):
        compiler.compile(tmp_path / "docs" / name, tmp_path / "out" / name.split("/")[0]).raise_for_status()


def test_a_profile_document_compiles_as_the_base_kind_it_expands_to(acme_brand_tex, compiler, tmp_path):
    module = load_declaration("acme_deck:dist", version="2.0.0")
    brief = module.kinds.modules()["brief"]
    brief.create(tmp_path / "doc", brief.example()).save()
    compiler.compile(tmp_path / "doc" / "brief.tex", tmp_path / "out").raise_for_status()


# -- provenance --------------------------------------------------------------------------------------------


def with_provenance(root: pathlib.Path, head: str, *, name: str = "prov") -> pathlib.Path:
    """The saved `deck.tex` with `head` before `\\documentclass` and the provenance printed to the log."""
    text = (root / "deck.tex").read_text()
    text = text.replace("\\begin{document}", "\\typeout{PROVENANCE: \\abProvenanceInfo}\n\\begin{document}", 1)
    (root / f"{name}.tex").write_text(head + text)
    return root / f"{name}.tex"


def test_the_provenance_is_printable_and_is_in_the_pdfs_info_dictionary(acme_brand_tex, compiler, tmp_path):
    import datetime

    import pikepdf

    root = saved(acme_brand_tex, "expert", tmp_path / "doc")
    (root / "res/texpkg/acme-brand-provenance.sty").unlink()
    module = acme_brand_tex.kinds.modules()["expert"]
    module.load(root).save(now=datetime.datetime(2026, 10, 25, 12, 30, 5, tzinfo=datetime.UTC), stamp="1.2.0-3f9c2ab")
    source = with_provenance(root, "\\DocumentMetadata{lang=en-GB}\n")
    result = compiler.compile(source, tmp_path / "out")
    result.raise_for_status()
    expected = "acme-brand 1.2.0, stamp 1.2.0-3f9c2ab, materialised 2026-10-25T12:30:05Z"
    assert f"PROVENANCE: {expected}" in result.log.read_text()
    with pikepdf.open(result.pdf) as pdf:
        assert str(pdf.docinfo["/AbProvenance"]) == expected


def test_without_a_provenance_file_the_command_says_what_the_package_is(acme_brand_tex, compiler, tmp_path):
    root = saved(acme_brand_tex, "expert", tmp_path / "doc")
    (root / "res/texpkg/acme-brand-provenance.sty").unlink()
    result = compiler.compile(with_provenance(root, ""), tmp_path / "out")
    result.raise_for_status()
    assert "PROVENANCE: acme-brand 1.2.0\n" in result.log.read_text()
    import pikepdf

    with pikepdf.open(result.pdf) as pdf:
        assert "/AbProvenance" not in pdf.docinfo


MINIMAL = """\\DocumentMetadata{{lang=en-GB, pdfstandard={standard}, pdfversion={version}}}
\\documentclass{{article}}
{declarations}
\\begin{{document}}
Printed from \\acProvenanceInfo.
\\end{{document}}
"""


@pytest.mark.parametrize(
    ("standard", "version", "options", "findings"),
    [
        ("A-2b", "1.7", {"flavour": "2b", "pdfa": True, "pdfx": False, "colour": False}, set()),
        # PDF/X-4 also wants a trim box and an output intent, which this minimal page does not carry: the Info entry
        # adds no finding of its own.
        (
            "{A-2b,X-4}",
            "1.6",
            {"flavour": "2b", "pdfa": True, "pdfx": True, "colour": False},
            {"trimbox", "pdfx-intent"},
        ),
    ],
)
def test_the_info_entry_passes_pdfa_and_adds_nothing_to_pdfx(compiler, tmp_path, standard, version, options, findings):
    import pikepdf
    from texmodel_build.verify import registered

    from texpkg._internal import provenance_tex as tex

    verifier = registered()["proof-pdf"]
    if reason := verifier.unavailable(options):
        if os.environ.get("TEXPKG_REQUIRE_TEX"):
            pytest.fail(reason)
        pytest.skip(reason)
    source = tmp_path / "src"
    source.mkdir()
    (source / "acme-provenance.sty").write_text(
        tex.companion("ac", "acme", "1.2.0", "1.2.0-abc", "2026-10-25T12:30:05Z")
    )
    text = MINIMAL.format(standard=standard, version=version, declarations=tex.declarations("ac", "acme", "1.2.0"))
    (source / "doc.tex").write_text(text)
    result = compiler.compile(source / "doc.tex", tmp_path / "out")
    result.raise_for_status()
    with pikepdf.open(result.pdf) as pdf:
        assert str(pdf.docinfo["/AcProvenance"]) == "acme 1.2.0, stamp 1.2.0-abc, materialised 2026-10-25T12:30:05Z"
    assert {f.check for f in verifier.verify(result.pdf, options)} == findings


def test_every_template_of_an_export_compiles_with_the_search_environment_unset(acme_brand_tex, compiler, tmp_path):
    acme_brand_tex.export(tmp_path / "export", now=None)
    for kind in acme_brand_tex.kinds.names():
        compiler.compile(tmp_path / "export" / f"{kind}-template.tex", tmp_path / "out" / kind).raise_for_status()
