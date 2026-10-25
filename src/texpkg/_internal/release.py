"""A distribution bound to a release: what a built module's functions call (P7).

texpkg adds no document logic of its own: rendering is texmodel's `Package.plan`, given the kind's settings and the
layout's preamble lines.
"""

import dataclasses
import pathlib
from collections.abc import Mapping
from typing import Any, cast

from texmodel.components import AnyValue, Command, Environment, Node
from texmodel.package import setting_line
from texmodel.plan import Plan

from ..contracts import Changes, Contracts
from ..declaration import Distribution, Kind
from ..document import Document
from ..errors import (
    DeclarationError,
    DocumentExistsError,
    KindMismatchError,
    MigrationError,
    NewerDataError,
    NotADocumentError,
)
from . import directory, payload, state
from .envelope import Envelope, dumps


@dataclasses.dataclass(frozen=True)
class Release:
    """A distribution at the release it was built as. `sty` holds the `.sty` of every package in the chain, as the build
    rendered them (P4): what is shipped is what `save` writes. `bases` are the releases embedded in it (P13)."""

    dist: Distribution
    version: str
    contracts: Contracts
    sty: Mapping[str, str]
    bases: tuple["Release", ...] = ()

    def stack(self) -> list[dict[str, Any]]:
        """The packages a document is rendered through, this one first (V18)."""
        out = [
            {
                "package": self.dist.name,
                "release": self.version,
                "output": list(dataclasses.astuple(self.contracts.output)),
            }
        ]
        return out + [entry for base in self.bases for entry in base.stack()]

    def settings(self, kind: Kind, variant: str | None) -> tuple[AnyValue, ...]:
        """What a document of `kind` is written with (L8): for a profile kind, the base kind's presets first, then
        its own locks, then the variant's."""
        base = self.dist.base_kind(kind)
        return (*(base.presets if base else ()), *kind.settings(variant))

    def plan(self, kind: Kind, tree: Node, variant: str | None) -> Plan:
        """The `.tex` of `tree` as lines with provenance: the kind's presets, then the variant's settings (L8).

        An exposed base kind is written by the base's package; the directory's layout is this distribution's."""
        body = tree if kind.expand is None else kind.expand(tree)
        package = self.dist.owner(kind.name).package
        return package.plan(body, settings=self.settings(kind, variant), preamble=self.dist.layout.preamble())

    def payload(self, kind: Kind) -> payload.Payload:
        kinds = (kind.name, *([kind.over] if kind.over else []))
        return payload.build(self.sty, tuple(self.dist.resolved_assets()), self.dist.layout, kinds)

    def rendered(self, kind: Kind, tree: Node) -> dict[str, str]:
        """Every `.tex` of the kind with the plan of it that `save` keeps (D7), by path in the directory."""
        files: dict[str, str] = {}
        for variant, name in kind.documents():
            plan = self.plan(kind, tree, variant)
            files |= {name: plan.text, directory.plan_file(variant): plan.to_json()}
        return files

    def template(self, kind: Kind) -> dict[str, Any]:
        """The package as a document of `kind` meets it (D6): the settings each `.tex` is written with, the defaults the
        kind's classes have, the `.sty` by hash, and the stack (V18). Not the design file."""
        c = self.contracts
        return {
            "package": self.dist.name,
            "release": self.version,
            "contracts": {
                "data": [c.data.current, c.data.revision, c.data.age],
                "interface": [c.interface.current, c.interface.revision, c.interface.age],
                "output": [c.output.current, c.output.revision],
            },
            "settings": {
                name: {type(v).__name__: setting_line(v) for v in self.settings(kind, variant)}
                for variant, name in kind.documents()
            },
            "defaults": state.defaults_table(kind.model),
            "sty": state.sty_hashes(self.sty),
            "stack": self.stack(),
        }

    def states(self, kind: Kind, tree: Node) -> dict[str, str]:
        """The pair of states `save` and `create` write (D1)."""
        envelope = Envelope(self.dist.name, kind.name, self.contracts.data.current, state.tree_state(tree))
        return {directory.STATE: envelope.to_text(), directory.TEMPLATE: dumps(self.template(kind))}

    def read(self, path: pathlib.Path) -> Envelope:
        """The envelope of the document in `path`, refused if it is another package's or not readable (K3)."""
        text = directory.read(path, directory.STATE)
        if text is None:
            raise NotADocumentError(
                f"{path}: no document here (no {directory.STATE})",
                code="TP-D001",
                path=str(path),
                hint="create one with a kind's create, or point at the directory that holds it",
            )
        envelope = Envelope.parse(text, str(path / directory.STATE))
        if envelope.package != self.dist.name:
            raise KindMismatchError(
                f"{path} holds a document of package {envelope.package!r}, not {self.dist.name!r}",
                found=f"{envelope.package}:{envelope.kind}",
                expected=self.dist.name,
                path=str(path),
            )
        current = self.contracts.data.current
        if envelope.data > current:
            raise NewerDataError(
                f"{path} was written for `data` version {envelope.data}, this release reads {current}",
                code="TP-D004",
                path=str(path),
                hint="install the release that wrote it, or a newer one",
            )
        if envelope.data < current:
            raise MigrationError(
                f"{path} was written for `data` version {envelope.data}, this release reads {current}",
                code="TP-M002",
                hint="migrating older data is not built yet",
            )
        return envelope

    def load(self, path: pathlib.Path | str) -> "Document[Any]":
        """The document in `path`, whatever its kind (the generic `load`, P26)."""
        envelope = self.read(pathlib.Path(path))
        return self.kind_of(envelope).load(path)

    def kind_of(self, envelope: Envelope) -> "KindApi[Any]":
        kind = self.dist.kind(envelope.kind)
        return KindApi(self, kind, kind.model)

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

    def create(self, path: pathlib.Path | str, tree: T) -> Document[T]:
        """A document in `path` (made if need be) with both states written; refuses a directory that holds one."""
        path = pathlib.Path(path)
        if (path / directory.STATE).exists():
            raise DocumentExistsError(
                f"{path} already holds a document",
                code="TP-D002",
                path=str(path),
                hint="load it, or choose another directory",
            )
        if problems := tree.violations():
            raise ExceptionGroup("invalid document", [v.error() for v in problems])
        directory.write(path, self.release.states(self.kind, tree))
        return Document(tree, path, self.release, self.kind)

    def load(self, path: pathlib.Path | str) -> Document[T]:
        """The document in `path`; writes nothing (D3). Refuses another kind's."""
        path = pathlib.Path(path)
        envelope = self.release.read(path)
        if envelope.kind != self.kind.name:
            raise KindMismatchError(
                f"{path} holds a {envelope.kind!r} document, not a {self.kind.name!r} one",
                found=envelope.kind,
                expected=self.kind.name,
                path=str(path),
            )
        tree = state.tree_from_state(self.kind.model, envelope.tree)
        return Document(cast("T", tree), path, self.release, self.kind)

    def schema(self, mode: state.Mode) -> dict[str, Any]:
        return state.schema(self.kind.model, mode)

    def example(self) -> T:
        return cast("T", self.kind.example())

    def variants(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.kind.variants)

    def changes(self, old: int, new: int) -> Changes:
        return Changes()
