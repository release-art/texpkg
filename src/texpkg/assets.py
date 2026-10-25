"""Assets and their roles (A1): the files the TeX needs that texmodel does not render."""

import dataclasses
import enum
import importlib.resources.abc
import pathlib
from collections.abc import Collection
from typing import NamedTuple

from .errors import DeclarationError


@enum.unique
class Role(enum.StrEnum):
    """What a file is, which decides where a layout puts it (A1): never inferred from a suffix. A `StrEnum`, so one
    package's value equals another's (B11)."""

    PACKAGE = "package"  # a `.sty`
    GRAPHIC = "graphic"
    FONT = "font"  # luaotfload reads no search path, so a layout puts it at the document's root
    BY_PATH = "by-path"  # named by path in a preamble: it keeps that path
    NOTE = "note"  # notes, licences


@dataclasses.dataclass(frozen=True)
class Asset:
    """A file the package ships. `path` is relative to the declaring package's root (`Distribution.root`); `kinds`
    names the kinds that need it, none meaning every kind (A6)."""

    path: str
    role: Role
    why: str
    kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        parts = pathlib.PurePosixPath(self.path).parts
        if not self.path or "\\" in self.path or pathlib.PurePosixPath(self.path).is_absolute() or ".." in parts:
            raise DeclarationError(
                f"asset path {self.path!r}: not a relative path inside the package",
                code="TP-A001",
                path=self.path,
                hint="a posix path under the declaring package, without '..'",
            )
        object.__setattr__(self, "kinds", tuple(self.kinds))

    def needed_by(self, kinds: Collection[str] | None) -> bool:
        """Whether a document that is one of `kinds` (a profile kind and the base kind it expands to) needs this asset;
        `None` is every kind (an export, E1)."""
        return kinds is None or not self.kinds or bool(set(self.kinds) & set(kinds))


class Resolved(NamedTuple):
    """An asset with the file it stands for, read with `importlib.resources` (P5)."""

    asset: Asset
    source: importlib.resources.abc.Traversable
