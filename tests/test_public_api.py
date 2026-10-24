"""The public/private line: top-level modules are public API, everything else lives in `_internal`."""

import importlib
import pathlib
import pkgutil
import shutil

import pytest

import texpkg
import texpkg_build

from . import spawn

ROOT = pathlib.Path(__file__).parents[1]

PUBLIC = {
    "assets",
    "contracts",
    "declaration",
    "document",
    "errors",
    "layout",
    "migration",
    "protocol",
    "provenance",
}
PUBLIC_BUILD = {"cli", "hook", "testing"}


def test_only_the_public_modules_sit_at_the_top_level():
    top = {m.name for m in pkgutil.iter_modules(texpkg.__path__)}
    assert top - {"_internal"} == PUBLIC, "a new module is either public (add it here) or goes in _internal"
    top = {m.name for m in pkgutil.iter_modules(texpkg_build.__path__)}
    assert top - {"_internal"} == PUBLIC_BUILD


@pytest.mark.parametrize("package", [texpkg, texpkg_build])
def test_every_module_imports(package):
    for info in pkgutil.walk_packages(package.__path__, f"{package.__name__}."):
        importlib.import_module(info.name)


def test_the_import_contracts_hold_and_a_violation_breaks_one(tmp_path):
    shutil.copy(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copytree(ROOT / "src", tmp_path, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    clean = spawn.lint_imports(tmp_path)
    assert clean.returncode == 0, clean.stdout
    (tmp_path / "texpkg" / "x.py").write_text("import texpkg_build\n")
    broken = spawn.lint_imports(tmp_path)
    assert broken.returncode != 0 and "the run time does not know the build" in broken.stdout
