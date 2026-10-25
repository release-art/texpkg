import importlib
import os
import pathlib
import sys
import zipfile
from collections.abc import Iterator
from types import ModuleType

import pytest
from texmodel_build.compiler import Compiler
from texmodel_build.errors import ToolchainError

from texpkg_build.testing import load_declaration

from . import projects


@pytest.fixture
def acme_brand_tex() -> Iterator[ModuleType]:
    """The acme brand's module, as a wheel built from the declaration would be (loaded in memory, 1.4)."""
    module = load_declaration("acme_brand:dist", version="1.2.0")
    yield module
    for name in [n for n in sys.modules if n == "acme_brand_tex" or n.startswith("acme_brand_tex.")]:
        del sys.modules[name]


@pytest.fixture(scope="session")
def fonts(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    return tmp_path_factory.mktemp("fonts")


@pytest.fixture
def compiler(fonts: pathlib.Path) -> Compiler:
    """The reference image, or a skip (TEXPKG_REQUIRE_TEX=1 makes the skip a failure)."""
    comp = Compiler(image=os.environ.get("TEXPKG_TEST_IMAGE", "texmodel-test"), font_cache=fonts, epoch=1700000000)
    try:
        comp.check_ready()
    except ToolchainError as exc:
        if os.environ.get("TEXPKG_REQUIRE_TEX"):
            pytest.fail(f"reference image unusable: {exc}")
        pytest.skip(f"no usable reference image: {exc}")
    return comp


@pytest.fixture
def expert(acme_brand_tex: ModuleType) -> ModuleType:
    return importlib.import_module("acme_brand_tex.kinds.expert")


@pytest.fixture
def vocab(acme_brand_tex: ModuleType) -> ModuleType:
    return importlib.import_module("acme_brand_tex.kinds.vocab")


@pytest.fixture
def brand_site(tmp_path, monkeypatch):
    """The brand's wheel built and installed where the deck's build finds it, as `[build-system] requires` does."""
    built = projects.wheel(projects.author_project(tmp_path / "brand"), tmp_path / "brand-dist")
    site = tmp_path / "brand-site"
    zipfile.ZipFile(built).extractall(site)
    monkeypatch.syspath_prepend(str(site))
    yield built
    for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
        del sys.modules[name]
    importlib.invalidate_caches()
