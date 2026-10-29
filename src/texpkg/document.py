"""`Document[T]`: a kind's tree and the directory it lives in (P27, P28)."""

import dataclasses
import datetime
import enum
import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from texmodel import drift
from texmodel.components import AnyValue, Command, Environment
from texmodel.plan import FieldEdit
from texmodel.preamble import PreambleSlots

from . import provenance
from ._internal import directory, handedits, state
from ._internal.state import Extras
from .contracts import Pair
from .declaration import Kind
from .errors import HandEditError, NotADocumentError
from .layout import LAYOUT

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
    """One line of a `.tex` that is not what `save` wrote (D8). `path` is the data path of the node that wrote it
    (`/content/1/content/0`: `.content[1].content[0]` of `Document.tree`, after `load`); a line of a setting or a
    preamble entry the document set has its place in the data (`/settings/0`), and one no node wrote, or any line of a
    profile kind, keeps the plan's own path (`header`, `settings[0]`, `Deck[0]/Card[1]`).

    `fields` are the arguments of the node a `CHANGED` line changes (texmodel's `FieldEdit`: `arg`, `found`, and the
    typed `value` when texmodel reads it back); empty when the change is not inside one argument's text (D9)."""

    file: pathlib.Path
    path: str
    expected: str
    found: str
    kind: HandEditKind
    fields: tuple[FieldEdit, ...] = ()


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

    def __init__(self, tree: T, path: pathlib.Path, release: "Release", kind: Kind, extras: Extras = Extras()) -> None:  # noqa: B008
        self.tree = tree
        self.path = path
        self._release, self._kind, self._extras = release, kind, extras

    @property
    def settings(self) -> tuple[AnyValue, ...]:
        """The values this document sets, within what its kind allows (D10); written after the kind's presets."""
        return self._extras.settings

    @property
    def options(self) -> tuple[str, ...]:
        """The class options of the document."""
        return self._extras.options

    @property
    def preamble(self) -> PreambleSlots:
        """The preamble entries of the document, which come after the lines that find the payload."""
        return self._extras.preamble

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
        return self._release.plan(self._kind, self.tree, variant, self._extras).text

    def replace(
        self,
        tree: T | None = None,
        *,
        settings: Sequence[AnyValue] | None = None,
        options: Sequence[str] | None = None,
        preamble: PreambleSlots | None = None,
    ) -> "Document[T]":
        """The same document, in the same directory, with another tree, and the settings, options or preamble given;
        what is not given stays. Refused whole if the kind does not allow what is given (D10)."""
        extras = self._release.kind(self._kind.name, self._kind.model).extras(
            self._extras.settings if settings is None else settings,
            self._extras.options if options is None else options,
            self._extras.preamble if preamble is None else preamble,
        )
        return Document(self.tree if tree is None else tree, self.path, self._release, self._kind, extras)

    def _expected(self, stamp: str, time: str) -> dict[str, str | bytes]:
        """Every file a save writes, by path in the directory."""
        files = provenance.files(self._release, stamp, time)
        payload = self._release.payload(self._kind, files)
        return (
            payload.expected()
            | self._release.rendered(self._kind, self.tree, self._extras)
            | self._release.states(self._kind, self.tree, self._extras)
        )

    def _data_path(self, plan_path: str, variant: str | None) -> str:
        """A line of a setting or a preamble entry the document set is at its place in the data (D10); one the kind
        writes keeps its plan path. A profile's tree is expanded before it is written, so a plan path names a node of
        the base's tree and not a path in this document's data: it is given as it is."""
        own = handedits.extra_path(
            plan_path,
            locked=len(self._release.settings(self._kind, variant)),
            leading=self._release.fixed_preamble(self._kind),
        )
        if own:
            return own
        return plan_path if self._kind.expand else handedits.data_path(plan_path)

    def hand_edits(self) -> tuple[HandEdit, ...]:
        """The lines of the `.tex` files that differ from the plan `save` kept of them (D8)."""
        variants = {name: variant for variant, name in self._kind.documents()}
        return tuple(
            HandEdit(
                self.path / name,
                self._data_path(edit.path, variants[name]),
                edit.expected,
                edit.found,
                HandEditKind(edit.kind.value),
                edit.fields,
            )
            for name, edit in handedits.edits(self.path, self._kind.documents())
        )

    def save(self, *, now: datetime.datetime | None = None, stamp: str | None = None, force: bool = False) -> None:
        """Write the states, the `.tex` of every variant with its plan, and the payload of the kind: only what changed,
        and a history entry only when the states did (P29). Raises `HandEditError`, writing nothing, when a `.tex` was
        edited by hand, unless `force`. Nothing is written if the tree or the payload is not whole.

        The provenance files carry `stamp` (default: the release's version, V4) and the time of `now` (default: the
        clock, N4). Their time is kept while the stamp and the rest of the payload are as they were."""
        rendered = self._release.rendered(self._kind, self.tree, self._extras)
        states = self._release.states(self._kind, self.tree, self._extras)
        wanted = provenance.stamp_of(stamp, self._release)
        bare = self._release.payload(self._kind)
        bare.complete()
        saved = provenance.saved(self.path, self._release)
        unchanged = saved is not None and saved.stamp == wanted and not bare.pending(self.path)
        time = saved.time if unchanged and saved else provenance.time_of(now)
        payload = self._release.payload(self._kind, provenance.files(self._release, wanted, time))
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

    def check(self, *, stamp: str | None = None) -> Check:
        """What a save would change; writes nothing. A hand-edited `.tex` is reported as changed and in `edits`. The
        provenance files are compared by stamp (A4): `stamp` is the one the document was saved with (default: the
        release's version), and the time they hold is not a difference."""
        wanted = provenance.stamp_of(stamp, self._release)
        saved = provenance.saved(self.path, self._release)
        expected = self._expected(wanted, saved.time if saved else provenance.time_of(None))
        report = drift.check_drift(expected, self.path, LAYOUT.owned())
        files: dict[pathlib.Path, FileState] = {}
        for rel in expected:
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


def _flat(template: dict[str, Any]) -> dict[str, Any]:
    """The parts of a template state a release can change for a document, one entry each: the settings it writes, the
    defaults, the `.sty` files, and each package of the stack with its release and `output` pair (a layout change
    shows there when nothing else does)."""
    return (
        {
            f"setting {file} {value}": line
            for file, lines in template["settings"].items()
            for value, line in lines.items()
        }
        | {f"default {name}": value for name, value in template["defaults"].items()}
        | {f"sty {name}": digest for name, digest in template["sty"].items()}
        | {
            f"package {e['package']}": f"{e['release']} (output {e['output'][0]}.{e['output'][1]})"
            for e in template["stack"]
        }
    )
