"""The build imports the author's declaration into the process it runs in, and leaves no trace of it (B2).

While it is imported, the author's source is on `sys.path` and the modules of the declaration and of the generated
module are the build's own copies (a copy that is already loaded is put aside and restored).
"""

import contextlib
import pathlib
import sys
from collections.abc import Generator
from types import ModuleType


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
    """`source` on `sys.path` for the block, and the modules that were forgotten and imported put right afterwards."""
    where = str(source)
    sys.path.insert(0, where)
    isolation = Isolation()
    try:
        yield isolation
    finally:
        sys.path.remove(where)
        isolation.restore()
