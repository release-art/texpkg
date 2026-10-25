"""The pdm build hook (B2): `pdm_build.py` re-exports these two functions.

```python
from texpkg_build.hook import pdm_build_initialize, pdm_build_update_files
```

`[tool.texpkg] distribution = "module:attribute"` names the declaration (B3). The wheel holds the generated module and
the declaration copied into it; the sdist holds the author's sources and builds the same wheel (B6).
"""

import contextlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import pathlib
import sys
from collections.abc import Generator
from types import ModuleType

from pdm.backend.hooks import Context

from texpkg.contracts import Contracts
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from ._internal import checks, embed, generate
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


class _LinkRunTime(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Static linking at build time: an installed base carries its own private texmodel and texpkg, but the declaration
    being built must use classes of one texmodel. While it is imported, `<base>._embedded.texmodel` and `.texpkg` are
    the
    modules this build runs on, as the wheel's single copy will be."""

    def find_spec(
        self, fullname: str, path: object = None, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        parts = fullname.split(".")
        if len(parts) > 2 and parts[1] == embed.EMBEDDED and parts[2] in embed.RUN_TIME:
            return importlib.util.spec_from_loader(fullname, self)
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        return importlib.import_module(spec.name.split(f".{embed.EMBEDDED}.", 1)[1])

    def exec_module(self, module: ModuleType) -> None:
        """The module is the build's own and already runs."""


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

    def drop(self, top: str) -> None:
        """Forget what is imported under `top` from now on, keeping what is imported now."""
        self._tops.add(top)

    def restore(self) -> None:
        for name in [n for n in sys.modules if n.split(".")[0] in self._tops]:
            del sys.modules[name]
        sys.modules.update(self._stashed)


@contextlib.contextmanager
def _author_source(context: Context) -> Generator[_Isolation]:
    source = str(context.root / (context.config.build_config.package_dir or "."))
    sys.path.insert(0, source)
    linker = _LinkRunTime()
    sys.meta_path.insert(0, linker)
    isolation = _Isolation()
    try:
        yield isolation
    finally:
        sys.meta_path.remove(linker)
        sys.path.remove(source)
        isolation.restore()


def pdm_build_initialize(context: Context) -> None:
    """A wheel needs pydantic and nothing else: texmodel, texpkg and the bases are embedded in it (B7)."""
    metadata = context.config.metadata
    metadata["dependencies"] = [PYDANTIC]
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
        for base in dist.chain()[1:]:
            isolation.drop(base.module)
        declaration = checks.declaration_directory(dist)
        checks.assets_are_there(dist)
        checks.tex_names_are_unique(dist)
        checks.design_is_valid(dist)
        version = str(context.config.metadata["version"])
        checks.module_satisfies_the_protocols(load_declaration(f"{module}:{attr}", version=version))
        generated = generate.sources(dist, attr, version, Contracts())
        files.clear()  # a wheel holds the generated module, not the author's sources
        embed.embed(
            context.build_dir / dist.module, dist, declaration, generated
        )  # not ensure_build_dir(): its .gitignore
