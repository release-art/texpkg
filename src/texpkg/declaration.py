"""The declaration an author writes: `Distribution`, `Kind`, `Variant`, `Design` (P8, K1).

Checked when it is built, so a mistake fails at import, not at a consumer's `load`.
"""

import dataclasses
import importlib.resources
import importlib.resources.abc
import inspect
import keyword
import os
import pathlib
import re
from collections.abc import Callable, Iterator
from typing import Any

import pydantic
from texmodel.components import AnyValue, Command, Environment, Node, Passthrough, Value
from texmodel.document import OPTION
from texmodel.interface import Body, BodyKind
from texmodel.package import Package
from texmodel.preamble import Entry, PreambleSlots

from .assets import Asset, Resolved
from .errors import DeclarationError
from .layout import LAYOUT, Project
from .migration import Migration

_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # a `.tex` file name without its suffix
_KIND = re.compile(r"[a-z][a-z0-9_]*")  # a kind is a module, `acme_tex.kinds.<name>`
_VARIANT = re.compile(r"[a-z][a-z0-9-]*")  # a variant is part of a file name
_DISTRIBUTION = re.compile(r"[a-z][a-z0-9-]*")

type Model = type[Command] | type[Environment]


@dataclasses.dataclass(frozen=True)
class Variant:
    """A named set of settings and class options applied to the same document (K6): `doc.render(variant="compact")`.
    The options are written after the document's own, and need not be among the kind's `options`: the variant is the
    author's choice, not the document's."""

    name: str
    settings: tuple[AnyValue, ...] = ()
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _VARIANT.fullmatch(self.name):
            raise DeclarationError(
                f"variant name {self.name!r} must match [a-z][a-z0-9-]*",
                code="TP-K005",
                path=self.name,
                hint="it is part of a file name: deck-<variant>.tex",
            )
        object.__setattr__(self, "settings", tuple(self.settings))
        object.__setattr__(self, "options", tuple(self.options))
        if bad := next((o for o in self.options if not OPTION.fullmatch(o)), None):
            raise DeclarationError(
                f"variant {self.name}: option {bad!r} is not a class option",
                code="TP-K016",
                path=self.name,
                hint="letters, digits, '=', '.' and '-', starting with a letter or digit",
            )
        if twice := next((o for o in self.options if self.options.count(o) > 1), None):
            raise DeclarationError(
                f"variant {self.name}: option {twice!r} is declared twice", code="TP-K002", path=self.name
            )


@dataclasses.dataclass(frozen=True)
class Design:
    """Typed data a package ships (tokens, palettes), validated at build time and read with `importlib.resources`
    (L1). `path` is relative to the declaring package."""

    model: type[pydantic.BaseModel]
    path: str

    def load(self, root: importlib.resources.abc.Traversable) -> pydantic.BaseModel:
        """The data, read from `root` (the declaring package) and validated: JSON for the model."""
        text = root.joinpath(*self.path.split("/")).read_text(encoding="utf-8")
        return self.model.model_validate_json(text)


def _raw(body: Body) -> bool:
    return body.kind is BodyKind.RAW or any(_raw(item) for item in body.items)


def reachable(model: Model) -> tuple[type[Command] | type[Environment], ...]:
    """`model` and every component its grammars name (`Passthrough` excluded), in the order they are first met."""
    found: dict[type[Command] | type[Environment], None] = {model: None}
    todo = [model]
    while todo:
        cls = todo.pop(0)
        if issubclass(cls, Environment):
            for term in cls.__tm_grammar__:
                kind = term.kind
                if kind is not Passthrough and kind not in found and issubclass(kind, Command | Environment):
                    found[kind] = None
                    todo.append(kind)
    return tuple(found)


def raw_holes(model: Model) -> tuple[str, ...]:
    """The places a tree of `model` can hold TeX written as it is (P25): `Class.field` for a `Raw` field and
    `Class.Passthrough` for a grammar that accepts a `Passthrough`."""
    holes: list[str] = []
    for cls in reachable(model):
        holes += [f"{cls.__name__}.{a.name}" for a in cls.__tm_args__ if _raw(a.body)]
        if issubclass(cls, Environment) and any(t.kind is Passthrough for t in cls.__tm_grammar__):
            holes.append(f"{cls.__name__}.Passthrough")
    return tuple(holes)


@dataclasses.dataclass(frozen=True)
class Kind:
    """One named document model a package offers (K1): `model` is the root class of its trees, `presets` the settings
    every document of the kind is written with (L8), `example` a valid tree that exercises the whole kind (A7, V11).
    Every `Raw` field and `Passthrough` the kind can hold is named in `allow_raw` (P25). `stem` names the kind's `.tex`
    files (`deck` gives `deck.tex` and `deck-<variant>.tex`); left out, it is the root class's name, lower-cased.

    A document may carry what the kind allows and nothing else: `settable` (values a document sets, after `presets`,
    which every document is written with), `options` (class options) and `preamble` (entry classes). A value is a preset
    or settable, not both. `defaults` are the kind's own start values for settable ones: written after the presets and
    the variant's settings and before the document's own, so a document that sets the value overrides them (V21).
    `locked_preamble` holds entries every document is written with, in the slots given, after
    the layout's lines and before the document's own: a document may not carry an entry class that is locked."""

    name: str
    model: Model
    presets: tuple[AnyValue, ...]
    example: Callable[[], Node]
    migrations: tuple[Migration, ...] = ()
    allow_raw: tuple[str, ...] = ()
    variants: tuple[Variant, ...] = ()
    expand: Callable[[Any], Node] | None = None
    over: str | None = None
    stem: str = ""
    settable: tuple[type[Value[Any]], ...] = ()
    options: tuple[str, ...] = ()
    preamble: tuple[type[Entry], ...] = ()
    locked_preamble: PreambleSlots = dataclasses.field(default_factory=PreambleSlots)
    defaults: tuple[AnyValue, ...] = ()

    def __post_init__(self) -> None:
        for field in ("presets", "migrations", "allow_raw", "variants", "settable", "options", "preamble", "defaults"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if not _KIND.fullmatch(self.name) or keyword.iskeyword(self.name):
            raise DeclarationError(
                f"kind name {self.name!r} must match [a-z][a-z0-9_]* and not be a Python keyword",
                code="TP-K005",
                path=self.name,
                hint="a kind is a module: acme_tex.kinds.<name>",
            )
        self._unique("variant", [v.name for v in self.variants])
        self._check_allowed()
        if (self.expand is None) != (self.over is None):
            raise DeclarationError(
                f"kind {self.name}: expand and over go together",
                code="TP-K009",
                path=self.name,
                hint="a profile kind names the base kind it expands to (over=) and the function that does it (expand=)",
            )
        holes = raw_holes(self.model)
        if unknown := [a for a in self.allow_raw if a not in holes]:
            raise DeclarationError(
                f"kind {self.name}: allow_raw names {unknown[0]!r}, which is no Raw field or Passthrough of the kind",
                code="TP-K003",
                path=self.name,
                hint=f"the holes are {list(holes) or 'none'}",
            )
        if unlisted := [h for h in holes if h not in self.allow_raw]:
            raise DeclarationError(
                f"kind {self.name}: {unlisted[0]} holds TeX written as it is and is not allowed",
                code="TP-K003",
                path=f"{self.name}.{unlisted[0]}",
                hint=f"narrow the field, or name it: allow_raw=[{unlisted[0]!r}]",
            )
        tree = self.example()
        if not isinstance(tree, self.model):
            raise self._bad_example(f"is not a {self.model.__name__}")
        if problems := tree.violations():
            raise self._bad_example(problems[0].message)

    def _bad_example(self, what: str) -> DeclarationError:
        return DeclarationError(
            f"kind {self.name}: example() {what}",
            code="TP-K001",
            path=self.name,
            hint="the example is rendered for the output fingerprint and compiled by the author's tests",
        )

    def _check_allowed(self) -> None:
        """What a document may carry (D10): no name twice, real class options, nothing both written and settable."""
        self._unique("settable value", [c.__name__ for c in self.settable])
        self._unique("preamble entry", [c.__name__ for c in self.preamble])
        self._check_locked()
        self._unique("option", list(self.options))
        if bad := next((o for o in self.options if not OPTION.fullmatch(o)), None):
            raise DeclarationError(
                f"kind {self.name}: option {bad!r} is not a class option",
                code="TP-K016",
                path=self.name,
                hint="letters, digits, '=', '.' and '-', starting with a letter or digit",
            )
        written = {type(v) for v in (*self.presets, *(s for var in self.variants for s in var.settings))}
        if clash := next((c for c in self.settable if c in written), None):
            raise DeclarationError(
                f"kind {self.name}: {clash.__name__} is a preset or a variant's setting and settable",
                code="TP-K017",
                path=self.name,
                hint="a value is written for every document or set by a document, not both",
            )
        self._unique("default", [type(v).__name__ for v in self.defaults])
        if loose := next((v for v in self.defaults if type(v) not in self.settable), None):
            raise DeclarationError(
                f"kind {self.name}: a default for {type(loose).__name__}, which is not settable",
                code="TP-K021",
                path=self.name,
                hint="a default is where a document starts for a value it may set: add the class to settable",
            )
        object.__setattr__(self, "stem", self.stem or self.model.__name__.lower())
        if not _STEM.fullmatch(self.stem):
            raise DeclarationError(
                f"kind {self.name}: stem {self.stem!r} is not a file name without its suffix",
                code="TP-K015",
                path=self.name,
                hint="letters, digits, '_' and '-', e.g. stem='brand-deck' for brand-deck.tex",
            )

    def locked_classes(self) -> tuple[str, ...]:
        """The names of the entry classes the kind writes into every document."""
        return tuple(type(item).__name__ for _, _, item in self.locked_preamble.items())

    def _check_locked(self) -> None:
        """Locked entries are typed, in a slot they fit, each class once, and not also allowed to a document (K020)."""
        for slot, _, item in self.locked_preamble.items():
            slots = getattr(item, "slots", ())
            if slot not in slots:
                raise self.locked_error(
                    f"{type(item).__name__} cannot sit in {slot}" if slots else "is not a typed entry",
                    f"a typed entry (RequireMetadata, PdfInfo, ...) in a slot it fits: {list(slots) or 'none'}",
                    item,
                )
        names = self.locked_classes()
        if twice := next((n for n in names if names.count(n) > 1), None):
            raise self.locked_error("is locked twice", "lock each entry class once", twice)
        if both := next((c for c in self.preamble if c.__name__ in names), None):
            raise self.locked_error(
                "is locked and also allowed to a document", "a class is locked or allowed, not both", both.__name__
            )

    def locked_error(self, what: str, hint: str, entry: object) -> DeclarationError:
        name = entry if isinstance(entry, str) else type(entry).__name__
        return DeclarationError(
            f"kind {self.name}: locked preamble entry {name} {what}", code="TP-K020", path=self.name, hint=hint
        )

    def _unique(self, what: str, names: list[str]) -> None:
        if twice := next((n for n in names if names.count(n) > 1), None):
            raise DeclarationError(
                f"kind {self.name}: {what} {twice!r} is declared twice", code="TP-K002", path=self.name
            )

    def documents(self) -> tuple[tuple[str | None, str], ...]:
        """The `.tex` a save writes, as `(variant, file name)`: the kind's own, then one per variant (K7)."""
        return ((None, f"{self.stem}.tex"), *((v.name, f"{self.stem}-{v.name}.tex") for v in self.variants))

    def class_options(self, own: tuple[str, ...], variant: str | None = None) -> tuple[str, ...]:
        """The class options of a `.tex` (K6): the document's `own`, then the variant's that are not among them."""
        found = next((v for v in self.variants if v.name == variant), None)
        return (*own, *(o for o in (found.options if found else ()) if o not in own))

    def settings(self, variant: str | None = None) -> tuple[AnyValue, ...]:
        """What a document of the kind is written with (L8): the presets, then the settings of `variant`, if named."""
        if variant is None:
            return self.presets
        found = next((v for v in self.variants if v.name == variant), None)
        if found is None:
            raise DeclarationError(
                f"kind {self.name} has no variant {variant!r}",
                code="TP-K004",
                path=self.name,
                hint=f"its variants are {[v.name for v in self.variants]}",
            )
        return (*self.presets, *found.settings)


def _declared_in(name: str, root: str) -> tuple[str, str]:
    """The package of the module that called `Distribution(...)` and `root` (a path, relative to that module or
    absolute) made relative to it: past this function, `__post_init__` and the generated `__init__`."""
    frame = inspect.currentframe()
    for _ in range(3):
        frame = frame.f_back if frame else None
    package = frame.f_globals.get("__package__") if frame else None
    if not package:
        raise DeclarationError(
            "the declaring module is not in a package, so the package the assets are read from is unknown",
            code="TP-K012",
            path=name,
            hint="declare the distribution in a module of a package",
        )
    here = pathlib.Path(str(frame.f_globals["__file__"])).parent if frame else pathlib.Path()
    if here.is_dir():  # symlinks and `..` followed, so what is checked is where the files are
        here, target = here.resolve(), (here / root).resolve()
    else:  # a package imported from a zip has no directory to resolve
        target = pathlib.Path(os.path.normpath(here / root))
    if not target.is_relative_to(here):
        raise DeclarationError(
            f"root {root!r} is outside the package that declares {name}",
            code="TP-K013",
            path=name,
            hint="the wheel carries the declaring package only: keep the assets inside it",
        )
    relative = target.relative_to(here).as_posix()
    if not importlib.resources.files(str(package)).joinpath(*pathlib.PurePosixPath(relative).parts).is_dir():
        raise DeclarationError(
            f"root {root!r} is not a directory of the package that declares {name}",
            code="TP-K014",
            path=name,
            hint="a path relative to the declaring module, e.g. root='data'",
        )
    return str(package), relative


@dataclasses.dataclass(frozen=True)
class Distribution:
    """What a package author declares (B1): the texmodel `package` whose `.sty` is shipped, its `kinds`, its `assets`,
    the `base` it is built on (P20) and which of the base's kinds it `expose`s (P21). `public` names a module of the
    declaring package whose `__all__` lists constants the generated module re-exports as `public` (P31).

    `root` is the directory an asset's `path` is relative to: a path relative to the module that calls
    `Distribution(...)`, or absolute, and inside the package that holds it (the wheel carries that package, P22).
    `declared_in`, the import name of that package, is read from the call and not passed.
    The payload goes in a directory as `LAYOUT` places it.
    """

    name: str
    module: str
    package: Package
    root: str = "."
    design: Design | None = None
    assets: tuple[Asset, ...] = ()
    kinds: tuple[Kind, ...] = ()
    base: "Distribution | None" = None
    expose: tuple[str, ...] = ()
    public: str = ""
    declared_in: str = ""

    @property
    def layout(self) -> Project:
        return LAYOUT

    def __post_init__(self) -> None:
        if not self.declared_in:  # stored, so `dataclasses.replace` keeps both
            declared_in, root = _declared_in(self.name, self.root)
            object.__setattr__(self, "declared_in", declared_in)
            object.__setattr__(self, "root", root)
        for field in ("assets", "kinds", "expose"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if not _DISTRIBUTION.fullmatch(self.name):
            raise DeclarationError(
                f"distribution name {self.name!r} must match [a-z][a-z0-9-]*", code="TP-K006", path=self.name
            )
        if not self.module.isidentifier() or keyword.iskeyword(self.module):
            raise DeclarationError(
                f"module {self.module!r} is not a Python module name",
                code="TP-K006",
                path=self.name,
                hint="the generated module is imported by this name",
            )
        names = [k.name for k in self.kinds]
        if twice := next((n for n in names if names.count(n) > 1), None):
            raise DeclarationError(f"kind {twice!r} is declared twice", code="TP-K002", path=self.name)
        self._check_public()
        self._check_lineage()
        self._check_settable()
        base_offers = [k.name for k in self.base.kinds_offered()] if self.base else []
        if bad := next((n for n in self.expose if n not in base_offers), None):
            raise DeclarationError(
                f"expose names {bad!r}, which is no kind of the base",
                code="TP-K007",
                path=self.name,
                hint=f"the base offers {base_offers}" if self.base else "a distribution without a base exposes nothing",
            )
        if clash := next((n for n in self.expose if n in names or self.expose.count(n) > 1), None):
            raise DeclarationError(
                f"kind {clash!r} is both declared and exposed from the base, or exposed twice",
                code="TP-K007",
                path=self.name,
            )
        for kind in self.kinds:
            self._check_profile(kind)
        if unknown := next((k for a in self.assets for k in a.kinds if k not in (*names, *self.expose)), None):
            raise DeclarationError(
                f"an asset names kind {unknown!r}, which {self.name} does not offer",
                code="TP-K002",
                path=self.name,
                hint=f"the kinds are {[*names, *self.expose]}",
            )

    def _check_public(self) -> None:
        if self.public and self.public != self.declared_in and not self.public.startswith(self.declared_in + "."):
            raise DeclarationError(
                f"public module {self.public!r} is not inside {self.declared_in}",
                code="TP-K022",
                path=self.name,
                hint=f"name a module of {self.declared_in}, which the wheel carries, e.g. '{self.declared_in}.consts'",
            )

    def _check_profile(self, kind: Kind) -> None:
        """A profile kind expands to a kind of the base, and its example does so to a valid tree of it (L3, L7)."""
        if kind.over is None or kind.expand is None:
            return
        offered = {k.name: k for k in (self.base.kinds_offered() if self.base else ())}
        if kind.over not in offered:
            raise DeclarationError(
                f"kind {kind.name} expands to {kind.over!r}, which the base does not offer",
                code="TP-K009",
                path=kind.name,
                hint=f"the base offers {list(offered) or 'no kinds'}",
            )
        if problem := self.expansion_problem(kind, kind.example()):
            raise self._bad_expansion(kind, problem)
        base = offered[kind.over]
        if clash := next((n for n in kind.locked_classes() if n in base.locked_classes()), None):
            raise kind.locked_error(
                "is locked by the base kind too", "the base kind's locked entries are written first", clash
            )
        if clash := next((c for c in kind.preamble if c.__name__ in base.locked_classes()), None):
            raise kind.locked_error(
                "is locked by the base kind", "a profile cannot allow what its base locks", clash.__name__
            )

    def expansion_problem(self, kind: Kind, tree: Node) -> str | None:
        """Why `tree` of a profile kind does not expand to a valid tree of the base kind (L3); `None` if it does."""
        base = self.base_kind(kind)
        if base is None or kind.expand is None:
            return "is not a profile kind"
        try:
            expanded = kind.expand(tree)
        except (LookupError, ValueError, TypeError, AttributeError) as exc:
            return f"cannot be expanded: {exc!r}"
        if not isinstance(expanded, base.model):
            return "is not a tree of the base kind"
        problems = expanded.violations()
        return problems[0].message if problems else None

    def _bad_expansion(self, kind: Kind, what: str) -> DeclarationError:
        return DeclarationError(
            f"kind {kind.name}: its example expands to a tree that {what}",
            code="TP-K010",
            path=kind.name,
            hint="every valid document of a profile must expand to a valid base document (L3)",
        )

    def base_kind(self, kind: Kind) -> Kind | None:
        """The base kind a profile kind expands to; `None` for any other."""
        return self.base.kind(kind.over) if self.base and kind.over else None

    @property
    def files(self) -> importlib.resources.abc.Traversable:
        """The directory the assets are read from, in the declaring package."""
        return importlib.resources.files(self.declared_in).joinpath(*pathlib.PurePosixPath(self.root).parts)

    def chain(self) -> tuple["Distribution", ...]:
        """This distribution, then its base, then the base's base (P19, P20)."""
        return (self, *(self.base.chain() if self.base else ()))

    def _check_lineage(self) -> None:
        """The package derives from the base distribution's package, so a document reads the base's values (K019)."""
        wanted = self.base.package if self.base else None
        if self.package.base is not wanted:
            have = self.package.base.name if self.package.base else "nothing"
            raise DeclarationError(
                f"package {self.package.name} derives from {have}, but the distribution's base is "
                f"{self.base.name if self.base else 'none'}",
                code="TP-K019",
                path=self.name,
                hint="declare Package(base=) and Distribution(base=) together, each the other's base",
            )

    def _check_settable(self) -> None:
        """A document's settings are read back through the package that renders its kind, so that package, or a base
        of it, registers them."""
        for kind in self.kinds:
            if gone := next((c for c in kind.settable if c not in self.package.visible), None):
                shadow = self.package.value_named(gone.__name__)
                why = (
                    f"is shadowed by {shadow.__module__}.{shadow.__qualname__}"
                    if shadow
                    else f"is not registered by package {self.package.name} or its base"
                )
                raise DeclarationError(
                    f"kind {kind.name}: settable {gone.__name__} {why}",
                    code="TP-K018",
                    path=kind.name,
                    hint="register it on the kind's package or its base, under a name the package does not reuse",
                )

    def kinds_offered(self) -> tuple[Kind, ...]:
        """The kinds of this distribution's module: its own, then the base's that it exposes (P21)."""
        exposed = tuple(k for k in (self.base.kinds_offered() if self.base else ()) if k.name in self.expose)
        return (*self.kinds, *exposed)

    def owner(self, kind: str) -> "Distribution":
        """The distribution whose package renders `kind`: this one, or the base that declares an exposed kind."""
        if any(k.name == kind for k in self.kinds) or self.base is None:
            return self
        return self.base.owner(kind)

    def kind(self, name: str) -> Kind:
        found = next((k for k in self.kinds_offered() if k.name == name), None)
        if found is None:
            raise DeclarationError(
                f"{self.name} has no kind {name!r}",
                code="TP-K004",
                path=name,
                hint=f"its kinds are {[k.name for k in self.kinds_offered()]}",
            )
        return found

    def resolved_assets(self) -> Iterator[Resolved]:
        """Every asset of the chain, with the file it names: this distribution's first (P10)."""
        for dist in self.chain():
            for asset in dist.assets:
                yield Resolved(asset, dist.files.joinpath(*asset.path.split("/")))
