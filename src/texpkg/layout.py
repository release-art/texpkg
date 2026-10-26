"""The layout (A2): where a payload file goes under a document directory, and the preamble lines that find it (A5).

Policy over `texmodel.bundle`, which decides nothing about placement. There is one layout, `LAYOUT`, for every
distribution: a package built on another writes into the same directory, which the one set of preamble lines finds.
"""

import dataclasses
import pathlib

from texmodel.package import PreambleSlots
from texmodel.preamble import GraphicsPath, InputPath

from .assets import Role
from .errors import DeclarationError


@dataclasses.dataclass(frozen=True)
class Project:
    """`.sty`, graphics and notes in `dir`; fonts at the root, since luaotfload reads no document-side search path;
    `BY_PATH` at its own path."""

    dir: pathlib.PurePosixPath

    def __post_init__(self) -> None:
        if not self.dir.parts or self.dir.is_absolute() or ".." in self.dir.parts or "." in self.dir.parts:
            raise DeclarationError(
                f"layout directory {str(self.dir)!r}: not a relative directory inside the document",
                code="TP-A003",
                hint="e.g. Project(PurePosixPath('res/acme'))",
            )

    def place(self, role: Role, path: pathlib.PurePosixPath) -> pathlib.PurePosixPath:
        match role:
            case Role.BY_PATH:
                return path
            case Role.FONT:
                return pathlib.PurePosixPath(path.name)
            case Role.PACKAGE | Role.GRAPHIC | Role.NOTE:
                return self.dir / path.name

    def preamble(self) -> PreambleSlots:
        return PreambleSlots(before_package=(InputPath(f"{self.dir}/"),), after_package=(GraphicsPath(f"{self.dir}/"),))

    def owned(self) -> tuple[str, ...]:
        return (f"{self.dir}/**/*",)


LAYOUT = Project(pathlib.PurePosixPath("res/texpkg"))
