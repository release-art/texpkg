"""Helpers for an author's tests: the declaration loaded in memory, the L3 law, the isolated compile (1.4, L7, A7)."""

import importlib
import importlib.util
import pathlib
import pkgutil
import sys
import tempfile
from types import ModuleType

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
    contain, made from the same generated source (1.4): no wheel, no embedding. The files are written to a temporary
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
    for path, text in generate.sources(dist, attr, version, contracts or Contracts()).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text, encoding="utf-8")
    for loaded in [n for n in sys.modules if _is_under(n, dist.module)]:
        del sys.modules[loaded]
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
