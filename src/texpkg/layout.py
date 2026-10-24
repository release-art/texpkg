"""Layouts (A2): where a payload file goes under a document directory, and the preamble lines that find it (A5).

A layout is policy over `texmodel.bundle`, which decides nothing about placement.
"""

import dataclasses
import pathlib
from typing import Protocol

from texmodel.package import PreambleSlots
from texmodel.preamble import GraphicsPath, InputPath

from .assets import Role
from .errors import DeclarationError


class Layout(Protocol):
    def place(self, role: Role, path: pathlib.PurePosixPath) -> pathlib.PurePosixPath:
        """Where the file `path` (a declared asset's, or a generated `.sty`'s name) of `role` goes."""
        ...

    def preamble(self) -> PreambleSlots:
        """The lines a generated `.tex` needs to find what `place` put where (A5)."""
        ...

    def owned(self) -> tuple[str, ...]:
        """Globs under the document directory that only the payload writes to: a file there that the payload does not
        hold is `extra` (A4)."""
        ...


@dataclasses.dataclass(frozen=True)
class Flat:
    """Everything in the document's own directory, which kpathsea searches first. `BY_PATH` keeps its path."""

    def place(self, role: Role, path: pathlib.PurePosixPath) -> pathlib.PurePosixPath:
        return path if role is Role.BY_PATH else pathlib.PurePosixPath(path.name)

    def preamble(self) -> PreambleSlots:
        return PreambleSlots()

    def owned(self) -> tuple[str, ...]:
        return ("*.sty",)


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
