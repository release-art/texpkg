"""`Document[T]`: a kind's tree and the directory it lives in (P27, P28)."""

import dataclasses
import enum
import json
import pathlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from texmodel import drift
from texmodel.components import Command, Environment

from ._internal import directory, handedits, state
from .contracts import Pair
from .declaration import Kind
from .errors import HandEditError, NotADocumentError

if TYPE_CHECKING:
    from ._internal.release import Release


@enum.unique
class FileState(enum.StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    MISSING = "missing"
    EXTRA = "extra"  # in a place the payload writes to, and not written by it: a retired `.sty` (A4)


@enum.unique
class HandEditKind(enum.StrEnum):
    ADDED = "added"  # in the file, not in the plan
    REMOVED = "removed"  # in the plan, not in the file
    CHANGED = "changed"


@dataclasses.dataclass(frozen=True)
class HandEdit:
    """One line of a `.tex` that is not what `save` wrote (D8). `path` is the node's data path (`/content/1/content/0`),
    or the plan's own for a line no node wrote; `value` is the typed value when texmodel can read the edit back (D9),
    else `None`: it is never guessed."""

    file: pathlib.Path
    path: str
    expected: str
    found: str
    kind: HandEditKind
    value: object = None


@dataclasses.dataclass(frozen=True)
class TemplateChange:
    """One thing a new release changes for a saved document (D4): a setting a `.tex` is written with
    (`setting deck.tex FactGap`), a default (`default Fact.accent`) or a `.sty` (`sty acme-brand.sty`, by hash).
    `old` and `new` are the recorded and the current value; `None` is absent."""

    setting: str
    old: object
    new: object


@dataclasses.dataclass(frozen=True)
class Check:
    """What a `save` would change, and nothing changed to find out (P29, A4). A file that is `EXTRA` is reported, but a
    save removes nothing, so it does not make the document not current."""

    files: Mapping[pathlib.Path, FileState]
    edits: tuple[HandEdit, ...] = ()

    @property
    def current(self) -> bool:
        return not self.edits and all(s in (FileState.UNCHANGED, FileState.EXTRA) for s in self.files.values())


@dataclasses.dataclass(frozen=True)
class StackEntry:
    package: str
    release: str
    output: Pair  # what the package rendered with, `current:revision` (V18)


@dataclasses.dataclass(frozen=True)
class Stack:
    """The packages a document was rendered through, the top one first: its lockfile (V18)."""

    entries: tuple[StackEntry, ...]


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

    @property
    def defaults(self) -> tuple[str, ...]:
        """The data paths of the values that are still the package's defaults (V21)."""
        return state.default_paths(self.tree)

    @property
    def stack(self) -> Stack:
        """The packages the document was last saved through; the release's own when nothing is saved yet."""
        saved = directory.read(self.path, directory.TEMPLATE)
        template = json.loads(saved) if saved else self._release.template(self._kind)
        return Stack(tuple(StackEntry(e["package"], e["release"], Pair(*e["output"])) for e in template["stack"]))

    def render(self, variant: str | None = None) -> str:
        """The `.tex` of the document, complete: pure, nothing is written. Raises an `ExceptionGroup` of texmodel
        `ValidationError` when the tree breaks a rule."""
        return self._release.plan(self._kind, self.tree, variant).text

    def replace(self, tree: T) -> "Document[T]":
        """The same document, in the same directory, with another tree."""
        return Document(tree, self.path, self._release, self._kind)

    def _expected(self) -> dict[str, str | bytes]:
        """Every file a save writes, by path in the directory."""
        payload = self._release.payload(self._kind)
        return (
            payload.expected()
            | self._release.rendered(self._kind, self.tree)
            | self._release.states(self._kind, self.tree)
        )

    def _data_path(self, plan_path: str) -> str:
        """A profile's tree is expanded before it is written, so a plan path names a node of the base's tree and not a
        path in this document's data: it is given as it is."""
        return plan_path if self._kind.expand else handedits.data_path(plan_path)

    def hand_edits(self) -> tuple[HandEdit, ...]:
        """The lines of the `.tex` files that differ from the plan `save` kept of them (D8)."""
        return tuple(
            HandEdit(
                self.path / name,
                self._data_path(edit.path),
                edit.expected,
                edit.found,
                HandEditKind(edit.kind.value),
            )
            for name, edit in handedits.edits(self.path, self._kind.documents())
        )

    def save(self, *, force: bool = False) -> None:
        """Write the states, the `.tex` of every variant with its plan, and the payload of the kind: only what changed,
        and a history entry only when the states did (P29). Raises `HandEditError`, writing nothing, when a `.tex` was
        edited by hand, unless `force`. Nothing is written if the tree or the payload is not whole."""
        rendered = self._release.rendered(self._kind, self.tree)
        states = self._release.states(self._kind, self.tree)
        payload = self._release.payload(self._kind)
        payload.complete()
        if not force and (edits := self.hand_edits()):
            files = ", ".join(sorted({e.file.name for e in edits}))
            raise HandEditError(
                f"{len(edits)} hand-edited line(s) in {files}: not overwritten",
                edits=edits,
                hint="doc.hand_edits() lists them; save(force=True) overwrites them",
            )
        payload.write(self.path)
        directory.write(self.path, directory.differing(self.path, rendered))
        if changed := directory.differing(self.path, states):
            directory.rotate_history(self.path)
            directory.write(self.path, changed)

    def check(self) -> Check:
        """What a save would change; writes nothing. A hand-edited `.tex` is reported as changed and in `edits`."""
        report = drift.check_drift(self._expected(), self.path, self._release.dist.layout.owned())
        files: dict[pathlib.Path, FileState] = {}
        for rel in self._expected():
            files[self.path / rel] = (
                FileState.MISSING
                if rel in report.missing
                else FileState.CHANGED
                if rel in report.stale
                else FileState.UNCHANGED
            )
        files |= {self.path / rel: FileState.EXTRA for rel in report.orphaned}
        return Check(files, self.hand_edits())

    def template_changes(self) -> tuple[TemplateChange, ...]:
        """What the installed release changes for this document against the template state it was saved with (D4)."""
        saved = directory.read(self.path, directory.TEMPLATE)
        if saved is None:
            raise NotADocumentError(
                f"{self.path}: no {directory.TEMPLATE}", code="TP-D001", path=str(self.path), hint="save the document"
            )
        old, new = _flat(json.loads(saved)), _flat(self._release.template(self._kind))
        return tuple(
            TemplateChange(key, old.get(key), new.get(key)) for key in sorted(old | new) if old.get(key) != new.get(key)
        )


def _flat(template: dict[str, Any]) -> dict[str, object]:
    """The parts of a template state a release can change for a document, one entry each."""
    return (
        {
            f"setting {file} {value}": line
            for file, lines in template["settings"].items()
            for value, line in lines.items()
        }
        | {f"default {name}": value for name, value in template["defaults"].items()}
        | {f"sty {name}": digest for name, digest in template["sty"].items()}
    )
