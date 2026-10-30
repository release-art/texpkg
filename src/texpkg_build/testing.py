"""Helpers for an author's tests: the declaration loaded in memory, the L3 law, the isolated compile (1.4, L7, A7)."""

import importlib
import importlib.util
import pathlib
import pkgutil
import sys
import tempfile
from collections.abc import Iterable
from types import ModuleType

from texmodel.components import Node
from texmodel.run import fonts
from texmodel.run.compiler import Compiler

from texpkg.contracts import Contracts
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from ._internal import generate


def _is_under(name: str, root: str) -> bool:
    return name == root or name.startswith(root + ".")


def _declared_modules(declared_in: str) -> dict[str, ModuleType]:
    """The declaration package and every module under it, imported."""
    package = importlib.import_module(declared_in)
    modules = {declared_in: package}
    for info in pkgutil.walk_packages(package.__path__, f"{declared_in}."):
        modules[info.name] = importlib.import_module(info.name)
    return modules


def load_declaration(pointer: str, *, version: str = "0.0.0", contracts: Contracts | None = None) -> ModuleType:
    """The module a wheel built from `pointer` (`"acme_decl:dist"`, as `[tool.texpkg] distribution` writes it) would
    contain, made from the same generated source (1.4): no wheel. The files are written to a temporary
    directory that lives as long as the module; the declaration is the one already imported, shown as
    `<module>._declaration`, so its classes are the ones the author's own tests use. Loading again replaces the
    module."""
    module_name, _, attr = pointer.partition(":")
    dist = getattr(importlib.import_module(module_name), attr, None)
    if not isinstance(dist, Distribution):
        raise DeclarationError(
            f"{pointer} is not a Distribution",
            code="TP-B003",
            path=pointer,
            hint='write [tool.texpkg] distribution = "module:attribute"',
        )
    scratch = tempfile.TemporaryDirectory(prefix="texpkg-")
    root = pathlib.Path(scratch.name) / dist.module
    for loaded in [n for n in sys.modules if _is_under(n, dist.module)]:
        del sys.modules[loaded]
    _write(dist, pointer, version, contracts or Contracts(), root)
    spec = importlib.util.spec_from_file_location(
        dist.module, root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None and spec.loader is not None  # a file we just wrote
    module = importlib.util.module_from_spec(spec)
    sys.modules[dist.module] = module
    for name, real in _declared_modules(dist.declared_in).items():
        sys.modules[f"{dist.module}._declaration{name.removeprefix(dist.declared_in)}"] = real
    module._scratch = scratch  # pyright: ignore[reportAttributeAccessIssue]  # the files go when the module does
    spec.loader.exec_module(module)
    return module


def _write(dist: Distribution, pointer: str, version: str, contracts: Contracts, root: pathlib.Path) -> None:
    """The generated module of `dist` in `root`: the declaration is the module already imported."""
    for path, text in generate.sources(dist, pointer, version, contracts).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")


def check_expansion(dist: Distribution, kind: str, examples: Iterable[Node] = ()) -> None:
    """The law of a profile kind (L3): every valid document of it expands to a valid document of the kind it expands to.
    Checked on the kind's own example and on `examples`: run it over trees a hypothesis strategy builds (L6, L7), where
    a profile that widens its base (a default or a value the base's type does not take) fails."""
    profile = dist.kind(kind)
    base = dist.base_kind(profile)
    if profile.expand is None or base is None:
        raise DeclarationError(f"kind {kind} is not a profile kind", code="TP-K009", path=kind)
    for tree in (profile.example(), *examples):
        if problems := tree.violations():
            raise DeclarationError(f"kind {kind}: {problems[0].message}", code="TP-K010", path=kind)
        if problem := dist.expansion_problem(profile, tree):
            raise DeclarationError(
                f"kind {kind}: {tree!r} expands to a tree that {problem}",
                code="TP-K010",
                path=kind,
                hint="a profile narrows its base and never widens it (L6)",
            )


async def check_isolated(module: ModuleType, compiler: Compiler, workdir: pathlib.Path) -> None:
    """Each kind's example, in each of its variants, saved into a fresh directory that holds only that kind's payload
    and compiled with no search path (no `TEXINPUTS`, no font directory): it fails on a file the payload lacks, and on a
    font embedded from outside the document directory (A7). It proves what the example uses, so an example uses the
    whole kind."""
    problems: list[str] = []
    for kind in module._bound.RELEASE.dist.kinds_offered():  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
        kind_module = module.kinds.modules()[kind.name]
        root = workdir / kind.name
        kind_module.create(root, kind_module.example()).save()
        for _, name in kind.documents():
            result = await compiler.compile(root / name, workdir / "out" / kind.name / name.removesuffix(".tex"))
            problems += [f"{kind.name}/{name}: {e.code} {e.message}" for e in result.errors]
            if result.log is not None:
                problems += [
                    f"{kind.name}/{name}: font read from outside the document directory: {path}"
                    for path in fonts.outside(
                        result.log.read_text(encoding="utf-8", errors="replace"),
                        [pathlib.Path("/work/src"), root.resolve()],
                        root.resolve(),
                    )
                ]
    if problems:
        raise DeclarationError(
            "a kind's payload is not whole:\n  " + "\n  ".join(problems),
            code="TP-K011",
            hint="an asset names every kind that needs it (Asset(kinds=)); fonts are assets, not system fonts",
        )
