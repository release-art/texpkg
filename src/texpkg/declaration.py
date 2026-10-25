"""The declaration an author writes: `Distribution`, `Kind`, `Variant`, `Design` (P8, K1).

Checked when it is built, so a mistake fails at import, not at a consumer's `load`.
"""

import dataclasses
import importlib.resources
import importlib.resources.abc
import keyword
import re
from collections.abc import Callable, Iterator

import pydantic
from texmodel.components import AnyValue, Command, Environment, Node, Passthrough
from texmodel.interface import Body, BodyKind
from texmodel.package import Package

from .assets import Asset, Resolved
from .errors import DeclarationError
from .layout import Flat, Layout
from .migration import Migration

_KIND = re.compile(r"[a-z][a-z0-9_]*")  # a kind is a module, `acme_tex.kinds.<name>`
_VARIANT = re.compile(r"[a-z][a-z0-9-]*")  # a variant is part of a file name
_DISTRIBUTION = re.compile(r"[a-z][a-z0-9-]*")

type Model = type[Command] | type[Environment]


@dataclasses.dataclass(frozen=True)
class Variant:
    """A named set of settings applied to the same document (K6): `doc.render(variant="compact")`."""

    name: str
    settings: tuple[AnyValue, ...] = ()

    def __post_init__(self) -> None:
        if not _VARIANT.fullmatch(self.name):
            raise DeclarationError(
                f"variant name {self.name!r} must match [a-z][a-z0-9-]*",
                code="TP-K005",
                path=self.name,
                hint="it is part of a file name: deck-<variant>.tex",
            )
        object.__setattr__(self, "settings", tuple(self.settings))


@dataclasses.dataclass(frozen=True)
class Design:
    """Typed data a package ships (tokens, palettes), validated at build time and read with `importlib.resources`
    (L1). `path` is relative to the declaring package."""

    model: type[pydantic.BaseModel]
    path: str


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
    Every `Raw` field and `Passthrough` the kind can hold is named in `allow_raw` (P25)."""

    name: str
    model: Model
    presets: tuple[AnyValue, ...]
    example: Callable[[], Node]
    migrations: tuple[Migration, ...] = ()
    allow_raw: tuple[str, ...] = ()
    variants: tuple[Variant, ...] = ()

    def __post_init__(self) -> None:
        for field in ("presets", "migrations", "allow_raw", "variants"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if not _KIND.fullmatch(self.name) or keyword.iskeyword(self.name):
            raise DeclarationError(
                f"kind name {self.name!r} must match [a-z][a-z0-9_]* and not be a Python keyword",
                code="TP-K005",
                path=self.name,
                hint="a kind is a module: acme_tex.kinds.<name>",
            )
        self._unique("variant", [v.name for v in self.variants])
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

    def _unique(self, what: str, names: list[str]) -> None:
        if twice := next((n for n in names if names.count(n) > 1), None):
            raise DeclarationError(
                f"kind {self.name}: {what} {twice!r} is declared twice", code="TP-K002", path=self.name
            )

    @property
    def stem(self) -> str:
        """The name of the kind's `.tex` files: the root class's, lower-cased (`Deck` is `deck.tex`)."""
        return self.model.__name__.lower()

    def documents(self) -> tuple[tuple[str | None, str], ...]:
        """The `.tex` a save writes, as `(variant, file name)`: the kind's own, then one per variant (K7)."""
        return ((None, f"{self.stem}.tex"), *((v.name, f"{self.stem}-{v.name}.tex") for v in self.variants))

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


@dataclasses.dataclass(frozen=True)
class Distribution:
    """What a package author declares (B1): the texmodel `package` whose `.sty` is shipped, its `kinds`, its `assets`,
    the `base` it is built on (P20) and which of the base's kinds it `expose`s (P21).

    `declared_in` is the import name of the package that holds the declaration: write `declared_in=__name__` in its
    `__init__.py`. Assets are read from it (`importlib.resources`), and so are they in a built wheel, where the
    declaration is copied (P22). `layout` is how `save` places the payload in a document directory.
    """

    name: str
    module: str
    package: Package
    declared_in: str
    design: Design | None = None
    assets: tuple[Asset, ...] = ()
    kinds: tuple[Kind, ...] = ()
    base: "Distribution | None" = None
    expose: tuple[str, ...] = ()
    layout: Layout = Flat()

    def __post_init__(self) -> None:
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
        if unknown := next((k for a in self.assets for k in a.kinds if k not in (*names, *self.expose)), None):
            raise DeclarationError(
                f"an asset names kind {unknown!r}, which {self.name} does not offer",
                code="TP-K002",
                path=self.name,
                hint=f"the kinds are {[*names, *self.expose]}",
            )

    @property
    def root(self) -> importlib.resources.abc.Traversable:
        """The declaring package, where the assets are."""
        return importlib.resources.files(self.declared_in)

    def chain(self) -> tuple["Distribution", ...]:
        """This distribution, then its base, then the base's base (P19, P20)."""
        return (self, *(self.base.chain() if self.base else ()))

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
                yield Resolved(asset, dist.root.joinpath(*asset.path.split("/")))
