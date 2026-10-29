"""The pdm build hook (B2): `pdm_build.py` re-exports these two functions.

```python
from texpkg_build.hook import pdm_build_initialize, pdm_build_update_files
```

`[tool.texpkg] distribution = "module:attribute"` names the declaration (B3). The wheel holds the generated module and
the declaration copied into it; the sdist holds the author's sources and builds the same wheel (B6).
"""

import importlib
import importlib.metadata
import pathlib

from pdm.backend.hooks import Context

from texpkg._internal import classify
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from ._internal import assemble, checks, generate, generated
from ._internal.isolate import author_source
from .testing import load_declaration

PYDANTIC = "pydantic>=2,<3"


def _installed(name: str) -> str:
    """`X.Y.Z` of the installed distribution `name`, without dev or local parts: the release the build runs against."""
    try:
        found = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        raise DeclarationError(
            f"{name} is not installed in the build environment",
            code="TP-B015",
            path=name,
            hint=f"add {name} to [build-system] requires, so the wheel can depend on the release it was built with",
        ) from None
    return found if (match := classify.RELEASE.match(found)) is None else match[0]


def _base_requirement(name: str) -> str:
    """`name>=X.Y.Z,<N`: from the release the build runs against up to the next breaking one (V13): the next major, or
    the next minor before 1.0."""
    version = _installed(name)
    major, minor, _ = classify.parse_version(version)
    return f"{name}>={version},<{major + 1 if major else f'0.{minor + 1}'}"


def requirements(dist: Distribution) -> list[str]:
    """What the wheel depends on (B7): everything its code imports, named here whether or not texpkg brings it along.
    texpkg and texmodel of the release it was built with, up to the next minor (`~=X.Y.Z` is `>=X.Y.Z, ==X.Y.*`),
    pydantic, and the base's wheel from the release it was built on to its next breaking one."""
    base = [_base_requirement(dist.base.name)] if dist.base else []
    return [f"texpkg~={_installed('texpkg')}", f"texmodel~={_installed('texmodel')}", PYDANTIC, *base]


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
    """A wheel depends on texpkg and the base (B7); `pdm_build_update_files` pins them, once the declaration says which
    base. Until then, and for an sdist or an editable install, which link or hold the sources, it is texpkg itself."""
    metadata = context.config.metadata
    metadata["dependencies"] = ["texpkg"]
    if "dynamic" in metadata and "dependencies" in metadata["dynamic"]:
        metadata["dynamic"].remove("dependencies")


def pdm_build_update_files(context: Context, files: dict[str, pathlib.Path]) -> None:
    if context.target != "wheel":
        return  # the sdist holds the sources, an editable install links them: the module is made for a wheel (B6)
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
        module_files = generate.sources(dist, f"{module}:{attr}", version, contracts)
        files.clear()  # a wheel holds the generated module, not the author's sources
        assemble.assemble(
            context.build_dir / dist.module, dist, declaration, module_files, held
        )  # not ensure_build_dir(): its .gitignore
        context.config.metadata["dependencies"] = requirements(dist)
