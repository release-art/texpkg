"""The compile suite: a saved document directory is accepted by TeX with only its payload beside it.

Skipped without the reference image; TEXPKG_REQUIRE_TEX=1 (CI) makes that a failure. The image is
TEXPKG_TEST_IMAGE, else `texmodel-test` (texmodel's `bin/test-image.sh`).
"""

import pathlib
from types import ModuleType

import pytest
from texmodel_build.compiler import Compiler

from texpkg_build.testing import load_declaration

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


def test_a_flat_layout_compiles_too(compiler: Compiler, tmp_path):
    module = load_declaration("acme_brand:flat", version="1.2.0")
    root = saved(module, "expert", tmp_path / "doc")
    assert (root / "acme-brand.sty").is_file() and not (root / "res").exists()
    compiler.compile(root / "deck.tex", tmp_path / "out").raise_for_status()


def test_a_missing_lockup_is_a_compile_error_not_a_silent_fallback(acme_brand_tex, compiler: Compiler, tmp_path):
    root = saved(acme_brand_tex, "expert", tmp_path / "doc")
    (root / "res" / "acme" / "lockup.pdf").unlink()
    assert not compiler.compile(root / "deck.tex", tmp_path / "out").ok
