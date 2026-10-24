"""`Document[T]`: a kind's tree and the directory it lives in (P27, P28)."""

import pathlib
from typing import TYPE_CHECKING

from texmodel.components import Command, Environment

from .declaration import Kind

if TYPE_CHECKING:
    from ._internal.release import Release


class Document[T: Command | Environment]:
    """A texmodel tree of a kind's classes (`doc.tree`) with texpkg's interface as methods (P28). Made by a kind's
    `load` and `create`, never by hand; a tree is frozen, so `replace` gives another document."""

    def __init__(self, tree: T, path: pathlib.Path, release: "Release", kind: Kind) -> None:
        self.tree = tree
        self.path = path
        self._release, self._kind = release, kind

    @property
    def kind(self) -> str:
        return self._kind.name

    def render(self, variant: str | None = None) -> str:
        """The `.tex` of the document, complete: pure, nothing is written. Raises an `ExceptionGroup` of texmodel
        `ValidationError` when the tree breaks a rule."""
        return self._release.plan(self._kind, self.tree, variant).text

    def replace(self, tree: T) -> "Document[T]":
        """The same document, in the same directory, with another tree."""
        return Document(tree, self.path, self._release, self._kind)
