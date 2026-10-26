"""The per-kind payload proved by compiling, and the font check (A7, A8)."""

import pathlib
from types import SimpleNamespace
from typing import Any, cast

import pytest
from texmodel_build.compiler import Compiler

from texpkg.errors import DeclarationError
from texpkg_build.testing import check_isolated, load_declaration


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_every_kind_of_a_whole_package_compiles_with_only_its_own_payload(acme_brand_tex, compiler, tmp_path):
    check_isolated(acme_brand_tex, compiler, tmp_path)


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_file_the_payload_of_a_kind_lacks_is_found(compiler, tmp_path):
    module = load_declaration("acme_brand:misdeclared", version="1.2.0")
    with pytest.raises(DeclarationError) as raised:
        check_isolated(module, compiler, tmp_path)
    assert raised.value.code == "TP-K011" and "expert/deck.tex" in str(raised.value)


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_system_font_is_found(compiler, tmp_path, monkeypatch):
    module = load_declaration("acme_brand:dist", version="1.2.0")
    original = compiler.compile

    def with_system_font(source, outdir, **kwargs):  # noqa: ANN001, ANN003, ANN202
        text = source.read_text().replace("\\begin{document}", "\\setmainfont{Latin Modern Roman}\n\\begin{document}")
        source.write_text(text)
        return original(source, outdir, **kwargs)

    monkeypatch.setattr(
        compiler.__class__, "compile", lambda self, source, outdir, **kw: with_system_font(source, outdir, **kw)
    )
    with pytest.raises(DeclarationError) as raised:
        check_isolated(module, compiler, tmp_path)
    assert "font read from outside" in str(raised.value)


class _Fake:
    """What `check_isolated` asks of a compiler, so its verdicts are proved without TeX: the errors and the log."""

    def __init__(self, tmp_path, *, errors=(), listing=""):  # noqa: ANN001, ANN002, ANN204
        self.errors, self.log = list(errors), None
        if listing:
            self.log = tmp_path / "doc.log"
            self.log.write_text(f"stack positions out of 5000i\n{listing}\nOutput written on doc.pdf (1 page).\n")

    def compile(self, source, outdir):  # noqa: ANN001, ANN201
        return SimpleNamespace(errors=self.errors, log=self.log)


def fake(tmp_path: pathlib.Path, **kwargs: Any) -> Compiler:
    return cast("Compiler", _Fake(tmp_path, **kwargs))


def test_a_payload_that_compiles_cleanly_with_its_own_fonts_is_whole(acme_brand_tex, tmp_path):
    check_isolated(acme_brand_tex, fake(tmp_path, listing="</work/src/lmroman10-regular.otf>"), tmp_path / "w")
    check_isolated(acme_brand_tex, fake(tmp_path), tmp_path / "w2")  # no log: nothing to read


def test_a_compile_error_makes_the_payload_not_whole(acme_brand_tex, tmp_path):
    error = SimpleNamespace(code="TM-C001", message="file 'lockup.pdf' not found")
    with pytest.raises(DeclarationError) as raised:
        check_isolated(acme_brand_tex, fake(tmp_path, errors=[error]), tmp_path / "w")
    assert raised.value.code == "TP-K011" and "expert/deck.tex: TM-C001 file 'lockup.pdf' not found" in str(
        raised.value
    )


def test_a_font_from_outside_the_document_directory_makes_the_payload_not_whole(acme_brand_tex, tmp_path):
    compiler = fake(tmp_path, listing="</usr/share/fonts/Other.otf>")
    with pytest.raises(DeclarationError) as raised:
        check_isolated(acme_brand_tex, compiler, tmp_path / "w")
    assert "font read from outside the document directory: /usr/share/fonts/Other.otf" in str(raised.value)
