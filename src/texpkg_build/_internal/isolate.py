"""The build imports the author's declaration into the process it runs in, and leaves no trace of it (B2).

While it is imported, the author's source is on `sys.path`, the modules of the declaration and of the generated module
are the build's own copies (a copy that is already loaded is put aside and restored), and
`<base>._embedded.texmodel` and
`.texpkg` are the modules this process runs on, as the wheel's single copy will be.
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

from . import embed


class LinkRunTime(importlib.abc.MetaPathFinder, importlib.abc.Loader):
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


class Isolation:
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
def author_source(source: pathlib.Path) -> Generator[Isolation]:
    """`source` on `sys.path` for the block, and the modules that were forgotten and imported put right afterwards.

    Importing `<base>._embedded.texpkg.migration` through the finder binds `migration` on the real `texpkg` package,
    over the function of that name it exports; the packages' namespaces are put back too."""
    where = str(source)
    sys.path.insert(0, where)
    linker = LinkRunTime()
    sys.meta_path.insert(0, linker)
    linked = {name: dict(vars(sys.modules[name])) for name in embed.RUN_TIME if name in sys.modules}
    isolation = Isolation()
    try:
        yield isolation
    finally:
        sys.meta_path.remove(linker)
        sys.path.remove(where)
        isolation.restore()
        for name, namespace in linked.items():
            vars(sys.modules[name]).update(namespace)
