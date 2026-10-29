"""A distribution bound to a release: what a built module's functions call (P7).

texpkg adds no document logic of its own: rendering is texmodel's `Package.plan`, given the kind's settings and the
layout's preamble lines.
"""

import dataclasses
import datetime
import importlib.resources.abc
import json
import pathlib
from collections.abc import Mapping, Sequence
from typing import Any, cast

from texmodel.components import AnyValue, Command, Environment, Node
from texmodel.document import Document as TexDocument
from texmodel.package import setting_line
from texmodel.plan import Plan
from texmodel.preamble import PreambleSlots

from .. import provenance
from ..assets import Role
from ..contracts import Changes, Contracts
from ..declaration import Distribution, Kind
from ..document import Document
from ..errors import (
    DeclarationError,
    DocumentExistsError,
    KindMismatchError,
    NewerDataError,
    NotADocumentError,
    NotAllowedError,
)
from ..layout import LAYOUT
from ..migration import DefaultChange, Migration
from . import directory, export, payload, snapshots, state
from .adopt import adopt
from .envelope import Envelope, dumps
from .state import Extras


@dataclasses.dataclass(frozen=True)
class Release:
    """A distribution at the release it was built as. `sty` holds the `.sty` of every package in the chain, as the build
    rendered them (P4): what is shipped is what `save` writes. `bases` are the releases it is built on (P13)."""

    dist: Distribution
    version: str
    contracts: Contracts
    sty: Mapping[str, str]
    bases: tuple["Release", ...] = ()
    snapshots: importlib.resources.abc.Traversable | None = None  # `_contracts`: the frozen snapshots a wheel carries

    def __post_init__(self) -> None:
        """A base is checked like a library by its soname (V17): the installed one must still support the `interface`
        this package was built on, `current - age` up to `current`."""
        for base in self.bases:
            relied, held = self.contracts.base_interface, base.contracts.interface
            if relied and not held.current - held.age <= relied <= held.current:
                raise DeclarationError(
                    f"{self.dist.name} was built on {base.dist.name} interface {relied}, but the installed "
                    f"{base.version} supports {held.current - held.age} to {held.current}",
                    code="TP-C007",
                    path=base.dist.name,
                    hint=f"install a {base.dist.name} that supports interface {relied}, or rebuild {self.dist.name}",
                )

    def releases(self) -> tuple["Release", ...]:
        """This release and the ones it is built on, this one first."""
        return (self, *(r for base in self.bases for r in base.releases()))

    def stack(self) -> list[dict[str, Any]]:
        """The packages a document is rendered through, this one first (V18)."""
        return [
            {"package": r.dist.name, "release": r.version, "output": list(dataclasses.astuple(r.contracts.output))}
            for r in self.releases()
        ]

    def layout_path(self, name: str) -> str:
        """Where the layout puts the package file `name` in a document directory."""
        return str(LAYOUT.place(Role.PACKAGE, pathlib.PurePosixPath(name)))

    def settings(self, kind: Kind, variant: str | None) -> tuple[AnyValue, ...]:
        """What a document of `kind` is written with (L8): for a profile kind, the base kind's presets first, then
        its own locks, then the variant's."""
        base = self.dist.base_kind(kind)
        return (*(base.presets if base else ()), *kind.settings(variant), *self.kind_defaults(kind))

    def kind_defaults(self, kind: Kind) -> tuple[AnyValue, ...]:
        """Where a document of `kind` starts for the values it may set: a profile's base kind's, then its own (V21)."""
        base = self.dist.base_kind(kind)
        return (*(base.defaults if base else ()), *kind.defaults)

    def kind_defaults_state(self, kind: Kind) -> dict[str, Any]:
        """The settable ones among them, by class name, in the data shape of a setting: what the template state keeps
        to tell, at `load`, a default the kind has changed."""
        found = tuple(v for v in self.kind_defaults(kind) if type(v) in kind.settable)
        data = state.extras_state(Extras(settings=found)).get("settings", [])
        return json.loads(dumps({type(v).__name__: d for v, d in zip(found, data, strict=True)}))

    def _has_graphics(self, kind: Kind) -> bool:
        kinds = (kind.name, *([kind.over] if kind.over else []))
        return any(r.asset.role is Role.GRAPHIC and r.asset.needed_by(kinds) for r in self.dist.resolved_assets())

    def layout_preamble(self, kind: Kind) -> PreambleSlots:
        """The lines that find the payload, which come before a document's own entries (A5)."""
        return LAYOUT.preamble(graphics=self._has_graphics(kind))

    def fixed_preamble(self, kind: Kind) -> PreambleSlots:
        """What leads each preamble slot of every document of `kind`: the layout's lines, then the entries the base kind
        locks (a profile's), then the kind's own (K020)."""
        base = self.dist.base_kind(kind)
        slots = [self.layout_preamble(kind), *([base.locked_preamble] if base else []), kind.locked_preamble]
        return PreambleSlots(
            before_class=tuple(e for s in slots for e in s.before_class),
            before_package=tuple(e for s in slots for e in s.before_package),
            after_package=tuple(e for s in slots for e in s.after_package),
        )

    def plan(self, kind: Kind, tree: Node, variant: str | None, extras: Extras = Extras()) -> Plan:  # noqa: B008
        """The `.tex` of `tree` as lines with provenance: the kind's presets, then the variant's settings (L8), then the
        document's own settings (D10); in each preamble slot the fixed entries, then the document's own.

        An exposed base kind is written by the base's package; the directory's layout is this distribution's."""
        body = tree if kind.expand is None else kind.expand(tree)
        package = self.dist.owner(kind.name).package
        found, own = self.fixed_preamble(kind), extras.preamble
        return package.plan(
            TexDocument(
                body,
                options=kind.class_options(extras.options, variant),
                settings=(*self.settings(kind, variant), *extras.settings),
                preamble=PreambleSlots(
                    before_class=(*found.before_class, *own.before_class),
                    before_package=(*found.before_package, *own.before_package),
                    after_package=(*found.after_package, *own.after_package),
                ),
            )
        )

    def export(
        self, destination: pathlib.Path | str, now: datetime.datetime | None, stamp: str | None
    ) -> tuple[pathlib.Path, ...]:
        """Write the whole payload in the layout, the provenance files, and a template and a README per kind (E1).
        Refused whole if a file is missing (A3)."""
        root = pathlib.Path(destination)
        wanted = provenance.stamp_of(stamp, self)
        files = provenance.files(self, wanted, provenance.time_of(now))
        everything = payload.build({**self.sty, **files}, tuple(self.dist.resolved_assets()), LAYOUT, None)
        everything.complete()
        names = sorted(everything.expected())
        texts: dict[str, str] = {}
        for kind in self.dist.kinds_offered():
            texts[export.template_name(kind)] = self.plan(kind, kind.example(), None).text
        listing = [*names, *texts, *(export.readme_name(k) for k in self.dist.kinds_offered())]
        for kind in self.dist.kinds_offered():
            texts[export.readme_name(kind)] = export.readme(self.dist, kind, self.version, sorted(listing))
        everything.write(root)
        directory.write(root, directory.differing(root, texts))
        return tuple(root / name for name in sorted(listing))

    def payload(self, kind: Kind, provenance: Mapping[str, str] | None = None) -> payload.Payload:
        """The payload of a document of `kind`: the `.sty` files, the provenance files if given, the assets."""
        kinds = (kind.name, *([kind.over] if kind.over else []))
        files = {**self.sty, **(provenance or {})}
        return payload.build(files, tuple(self.dist.resolved_assets()), LAYOUT, kinds)

    def rendered(self, kind: Kind, tree: Node, extras: Extras = Extras()) -> dict[str, str]:  # noqa: B008
        """Every `.tex` of the kind with the plan of it that `save` keeps (D7), by path in the directory."""
        files: dict[str, str] = {}
        for variant, name in kind.documents():
            plan = self.plan(kind, tree, variant, extras)
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
            "kind_defaults": self.kind_defaults_state(kind),
            "sty": state.sty_hashes(self.sty),
            "stack": self.stack(),
        }

    def states(self, kind: Kind, tree: Node, extras: Extras = Extras()) -> dict[str, str]:  # noqa: B008
        """The pair of states `save` and `create` write (D1)."""
        envelope = Envelope(
            self.dist.name, kind.name, self.contracts.data.current, state.tree_state(tree), state.extras_state(extras)
        )
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
        return envelope

    def load(
        self,
        path: pathlib.Path | str,
        migrations: Sequence[Migration] = (),
        default_changes: DefaultChange | Mapping[str, DefaultChange] = DefaultChange.FOLLOW,
    ) -> "Document[Any]":
        """The document in `path`, whatever its kind (the generic `load`, P26)."""
        envelope = self.read(pathlib.Path(path))
        return self.kind_of(envelope).load(path, migrations, default_changes)

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

    def extras(self, settings: Sequence[AnyValue], options: Sequence[str], preamble: PreambleSlots | None) -> Extras:
        """What a document carries besides its tree, refused whole if the kind does not allow it (D10)."""
        found = Extras(tuple(options), tuple(settings), preamble or PreambleSlots())
        if items := state.not_allowed(self.kind, found):
            shown = "; ".join(f"{i['path']}: {i['reason']}" for i in items)
            raise NotAllowedError(
                f"kind {self.kind.name}: {shown}",
                items=tuple(items),
                hint="the kind lists what a document may set: Kind(settable=, options=, preamble=)",
            )
        return found

    def create(
        self,
        path: pathlib.Path | str,
        tree: T,
        *,
        settings: Sequence[AnyValue] = (),
        options: Sequence[str] = (),
        preamble: PreambleSlots | None = None,
    ) -> Document[T]:
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
        extras = self.extras(settings, options, preamble)
        directory.write(path, self.release.states(self.kind, tree, extras))
        return Document(tree, path, self.release, self.kind, extras)

    def load(
        self,
        path: pathlib.Path | str,
        migrations: Sequence[Migration] = (),
        default_changes: DefaultChange | Mapping[str, DefaultChange] = DefaultChange.FOLLOW,
    ) -> Document[T]:
        """The document in `path`, adopted whole or not at all; writes nothing (D3). Refuses another kind's.

        Older data runs through the kind's migrations and the consumer's `migrations` (V32); `default_changes` says what
        happens to a value still marked as a default whose default this release changed (V23)."""
        path = pathlib.Path(path)
        envelope = self.release.read(path)
        if envelope.kind != self.kind.name:
            raise KindMismatchError(
                f"{path} holds a {envelope.kind!r} document, not a {self.kind.name!r} one",
                found=envelope.kind,
                expected=self.kind.name,
                path=str(path),
            )
        saved = directory.read(path, directory.TEMPLATE)
        template: dict[str, Any] = json.loads(saved) if saved else {}
        tree, extras = adopt(
            kind=self.kind,
            package=self.release.dist.owner(self.kind.name).package,
            envelope=envelope,
            current=self.release.contracts.data.current,
            age=self.release.contracts.data.age,
            consumer=migrations,
            policy=default_changes,
            saved_defaults=template.get("defaults"),
            saved_kind_defaults=template.get("kind_defaults"),
            kind_defaults=self.release.kind_defaults_state(self.kind),
            base_data=dict(self.release.contracts.base_data) if self.kind.name in self.release.dist.expose else None,
        )
        return Document(cast("T", tree), path, self.release, self.kind, extras)

    def schema(self, mode: state.Mode) -> dict[str, Any]:
        return state.schema(self.kind, self.release.dist.owner(self.kind.name).package, mode)

    def example(self) -> T:
        return cast("T", self.kind.example())

    def variants(self) -> tuple[str, ...]:
        return tuple(v.name for v in self.kind.variants)

    def changes(self, old: int, new: int) -> Changes:
        return snapshots.changes(self.release.snapshots, self.kind.name, old, new)
