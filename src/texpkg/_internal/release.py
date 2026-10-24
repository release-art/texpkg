"""A distribution bound to a release: what a built module's functions call (P7).

texpkg adds no document logic of its own: rendering is texmodel's `Package.plan`, given the kind's settings and the
layout's preamble lines.
"""

import dataclasses
import pathlib
from collections.abc import Mapping
from typing import Any, cast

from texmodel.components import Command, Environment, Node
from texmodel.plan import Plan

from ..contracts import Changes, Contracts
from ..declaration import Distribution, Kind
from ..document import Document
from ..errors import DeclarationError
from . import state


@dataclasses.dataclass(frozen=True)
class Release:
    """A distribution at the release it was built as. `sty` holds the `.sty` of every package in the chain, as the build
    rendered them (P4): what is shipped is what `save` writes."""

    dist: Distribution
    version: str
    contracts: Contracts
    sty: Mapping[str, str]

    def plan(self, kind: Kind, tree: Node, variant: str | None) -> Plan:
        """The `.tex` of `tree` as lines with provenance: the kind's presets, then the variant's settings (L8)."""
        return self.dist.package.plan(tree, settings=kind.settings(variant), preamble=self.dist.layout.preamble())

    def kind[T: Command | Environment](self, name: str, model: type[T]) -> "KindApi[T]":
        return KindApi(self, self.dist.kind(name), model)


class KindApi[T: Command | Environment]:
    """What a kind module's functions call."""

    def __init__(self, release: Release, kind: Kind, model: type[T]) -> None:
        if kind.model is not model:
            raise DeclarationError(
                f"kind {kind.name}: the module was generated for {model.__name__}, "
                f"the declaration has {kind.model.__name__}",
                code="TP-B001",
                path=kind.name,
                hint="build the package again",
            )
        self.release, self.kind = release, kind

    def document(self, tree: T, path: pathlib.Path) -> Document[T]:
        return Document(tree, path, self.release, self.kind)

    def schema(self, mode: state.Mode) -> dict[str, Any]:
        return state.schema(self.kind.model, mode)

    def example(self) -> T:
        return cast("T", self.kind.example())

    def variants(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.kind.variants)

    def changes(self, old: int, new: int) -> Changes:
        return Changes()
