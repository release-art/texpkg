"""The pdm build hook (B2): `pdm_build.py` re-exports these two functions.

```python
from texpkg_build.hook import pdm_build_initialize, pdm_build_update_files
```

`[tool.texpkg] distribution = "module:attribute"` names the declaration (B3). The wheel holds the generated module and
the declaration copied into it; the sdist holds the author's sources and builds the same wheel (B6).
"""

import importlib
import pathlib

from pdm.backend.hooks import Context

from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from ._internal import checks, embed, generate, generated
from ._internal.isolate import author_source
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
    source = context.root / (context.config.build_config.package_dir or ".")
    with author_source(source) as isolation:
        if pointer := context.config.data.get("tool", {}).get("texpkg", {}).get("generate"):
            where = generated.package_directory(source, module)
            generated.refuse_if_stale(pointer, where, generated.produce(pointer, where, isolation))
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
        loaded = load_declaration(f"{module}:{attr}", version=version)
        checks.module_satisfies_the_protocols(loaded)
        contracts, held = checks.contract_gate(context.root, dist, loaded._bound.RELEASE, version)  # pyright: ignore[reportAttributeAccessIssue]
        module_files = generate.sources(dist, attr, version, contracts)
        files.clear()  # a wheel holds the generated module, not the author's sources
        embed.embed(
            context.build_dir / dist.module, dist, declaration, module_files, held
        )  # not ensure_build_dir(): its .gitignore
