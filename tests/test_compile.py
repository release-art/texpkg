"""The compile suite (phase 2): a document is accepted by TeX with only its payload beside it.

Skipped without the reference image; TEXPKG_REQUIRE_TEX=1 (CI) makes that a failure. The image is
TEXPKG_TEST_IMAGE, else `texmodel-test` (texmodel's `bin/test-image.sh`).
"""

import dataclasses
import pathlib
from types import ModuleType

import pytest
from texmodel_build.compiler import Compiler

from texpkg import Flat
from texpkg._internal import payload

pytestmark = [pytest.mark.tex, pytest.mark.timeout(300)]

CASES = [("expert", None), ("expert", "compact"), ("expert", "wide"), ("vocab", None)]


def build(module: ModuleType, kind: str, variant: str | None, root: pathlib.Path, layout=None) -> pathlib.Path:  # noqa: ANN001
    """A document directory holding the kind's payload and the `.tex`, nothing else (A6)."""
    release = module._bound.RELEASE
    dist = release.dist if layout is None else dataclasses.replace(release.dist, layout=layout)
    api = module.kinds.modules()[kind]._api
    payload.build(release.sty, tuple(dist.resolved_assets()), dist.layout, kind).write(root)
    source = root / "document.tex"
    source.write_text(release.plan(api.kind, api.example(), variant).text, encoding="utf-8")
    return source


@pytest.mark.parametrize(("kind", "variant"), CASES)
def test_a_kind_compiles_with_only_its_payload(acme_brand_tex, compiler: Compiler, tmp_path, kind, variant):
    source = build(acme_brand_tex, kind, variant, tmp_path / "doc")
    result = compiler.compile(source, tmp_path / "out")
    result.raise_for_status()
    assert result.pages == 1


def test_a_flat_layout_compiles_too(acme_brand_tex, compiler: Compiler, tmp_path):
    source = build(acme_brand_tex, "expert", None, tmp_path / "doc", Flat())
    assert (tmp_path / "doc" / "acme-brand.sty").is_file()
    compiler.compile(source, tmp_path / "out").raise_for_status()


def test_a_missing_lockup_is_a_compile_error_not_a_silent_fallback(acme_brand_tex, compiler: Compiler, tmp_path):
    source = build(acme_brand_tex, "expert", None, tmp_path / "doc")
    (tmp_path / "doc" / "res" / "acme" / "lockup.pdf").unlink()
    assert not compiler.compile(source, tmp_path / "out").ok
