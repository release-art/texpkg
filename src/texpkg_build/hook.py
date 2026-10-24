"""The pdm build hook (B2): `pdm_build.py` re-exports these two functions.

```python
from texpkg_build.hook import pdm_build_initialize, pdm_build_update_files
```

`[tool.texpkg] distribution = "module:attribute"` names the declaration (B3). The wheel holds the generated module and
the declaration copied into it; the sdist holds the author's sources and builds the same wheel (B6).
"""

import contextlib
import importlib
import importlib.metadata
import pathlib
import shutil
import sys
from collections.abc import Generator
from types import ModuleType

from pdm.backend.hooks import Context

from texpkg.contracts import Contracts
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from ._internal import checks, generate
from .testing import load_declaration

PYDANTIC = "pydantic>=2,<3"  # the one thing a wheel cannot embed: it is compiled (B7)


def _pointer(context: Context) -> tuple[str, str]:
    given = context.config.data.get("tool", {}).get("texpkg", {}).get("distribution")
    module, _, attr = str(given).partition(":")
    if not (module and attr):
        raise DeclarationError(
            f"{context.root / 'pyproject.toml'}: [tool.texpkg] distribution is {given!r}",
            code="TP-B007",
            hint='write distribution = "module:attribute", the Distribution the build generates the module from',
        )
    return module, attr


class _Isolation:
    """The modules of the author's declaration and of the module generated from it, imported for the build and forgotten
    after: the build runs in the author's environment, which need not install the project, and a build must not see (or
    leave behind) another copy of them already imported in the process."""

    def __init__(self) -> None:
        self._tops: set[str] = set()
        self._stashed: dict[str, ModuleType] = {}

    def forget(self, top: str) -> None:
        """Take the modules of the package `top` out of the way until the build is over."""
        self._tops.add(top)
        self._stashed |= {n: sys.modules.pop(n) for n in list(sys.modules) if n.split(".")[0] == top}

    def restore(self) -> None:
        for name in [n for n in sys.modules if n.split(".")[0] in self._tops]:
            del sys.modules[name]
        sys.modules.update(self._stashed)


@contextlib.contextmanager
def _author_source(context: Context) -> Generator[_Isolation]:
    source = str(context.root / (context.config.build_config.package_dir or "."))
    sys.path.insert(0, source)
    isolation = _Isolation()
    try:
        yield isolation
    finally:
        sys.path.remove(source)
        isolation.restore()


def pdm_build_initialize(context: Context) -> None:
    """The wheel needs pydantic, and (until the run time is embedded) the texpkg and texmodel it was built with."""
    metadata = context.config.metadata
    metadata["dependencies"] = [
        PYDANTIC,
        f"texmodel=={importlib.metadata.version('texmodel')}",
        f"texpkg=={importlib.metadata.version('texpkg')}",
    ]
    if "dynamic" in metadata and "dependencies" in metadata["dynamic"]:
        metadata["dynamic"].remove("dependencies")


def pdm_build_update_files(context: Context, files: dict[str, pathlib.Path]) -> None:
    if context.target == "sdist":
        return
    if context.target != "wheel":
        raise DeclarationError(
            f"a {context.target} build of a texpkg package",
            code="TP-B008",
            hint="the module is generated from the declaration: test it with texpkg_build.testing.load_declaration",
        )
    module, attr = _pointer(context)
    with _author_source(context) as isolation:
        isolation.forget(module.split(".")[0])
        dist = getattr(importlib.import_module(module), attr, None)
        if not isinstance(dist, Distribution):
            raise DeclarationError(f"{module}:{attr} is not a Distribution", code="TP-B003", path=f"{module}:{attr}")
        isolation.forget(dist.module)
        declaration = checks.declaration_directory(dist)
        checks.assets_are_there(dist)
        version = str(context.config.metadata["version"])
        checks.module_satisfies_the_protocols(load_declaration(f"{module}:{attr}", version=version))
        generated = generate.sources(dist, attr, version, Contracts())
        files.clear()  # a wheel holds the generated module, not the author's sources
        out = context.build_dir / dist.module  # not ensure_build_dir(): its .gitignore would go into the wheel
        for rel, text in generated.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(text, encoding="utf-8")
        shutil.copytree(
            declaration,
            out / "_declaration",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            dirs_exist_ok=True,
        )
