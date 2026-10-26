"""The per-kind payload proved by compiling, and the font check (phase 6a: A7, A8)."""

import pytest

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
