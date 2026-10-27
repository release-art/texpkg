"""The stored form of a document: its schemas (V26) and what it carries besides its tree (D10).

Two schemas per kind, from pydantic's two modes: the input one (a field with a default is optional) and the stored one
(every field is written, V21, so every field is required, and a node lists the fields that hold defaults in
`$defaults`). A document's data is `{"tree": …}` and, when it has any, `settings`, `options` and `preamble` in the
shapes texmodel writes a `Document`'s in.
"""

import copy
import dataclasses
import hashlib
from collections.abc import Mapping
from typing import Any, Literal, cast

from texmodel import spec
from texmodel.body import Comment
from texmodel.components import AnyValue, Command, Environment, Node, Passthrough
from texmodel.document import Document as TexDocument
from texmodel.package import Package
from texmodel.preamble import PreambleSlots

from ..declaration import Kind, Model
from ..errors import DeclarationError
from .envelope import EXTRA_KEYS

type Mode = Literal["validation", "serialization"]

DEFAULTS = "$defaults"  # V24: the fields of a node that hold the package's defaults


def stored(validation: dict[str, Any]) -> dict[str, Any]:
    """The stored schema of an input schema: every property required, `$defaults` limited to the node's own defaulted
    fields (V27)."""
    out = copy.deepcopy(validation)
    for node in (out, *out.get("$defs", {}).values()):
        properties: dict[str, Any] | None = node.get("properties")
        if not properties:
            continue
        defaulted = sorted(name for name, schema in properties.items() if "default" in schema)
        node["required"] = sorted(properties)
        properties[DEFAULTS] = (
            {"type": "array", "items": {"enum": defaulted}, "uniqueItems": True}
            if defaulted
            else {"type": "array", "maxItems": 0}
        )
    return out


def tree_schema(model: Model, mode: Mode) -> dict[str, Any]:
    """The JSON Schema of the tree a kind's `model` takes (`validation`) or stores (`serialization`)."""
    if mode not in ("validation", "serialization"):
        raise DeclarationError(
            f"schema mode {mode!r}", code="TP-K008", hint='use "validation" (the input) or "serialization" (the stored)'
        )
    validation = spec.json_schema(model)
    return validation if mode == "validation" else stored(validation)


@dataclasses.dataclass(frozen=True)
class Extras:
    """What a document carries besides its tree, within what its kind allows: class `options`, `settings` (values set
    after the package loads) and `preamble` entries."""

    options: tuple[str, ...] = ()
    settings: tuple[AnyValue, ...] = ()
    preamble: PreambleSlots = dataclasses.field(default_factory=PreambleSlots)


def extras_state(extras: Extras) -> dict[str, Any]:
    """The keys of a document's data besides `tree`, in texmodel's shapes; empty ones left out."""
    data = spec.to_dict(TexDocument(options=extras.options, settings=extras.settings, preamble=extras.preamble))
    return {key: data[key] for key in EXTRA_KEYS if key in data}


def extras_from(package: Package, data: Mapping[str, Any]) -> Extras:
    """The extras `data` describes; raises an `ExceptionGroup` of texmodel `ValidationError` for data the package does
    not read."""
    found = spec.from_dict(package, {"type": "Document", **data, "content": []})
    return Extras(found.options, found.settings, found.preamble)


def not_allowed(kind: Kind, extras: Extras) -> list[dict[str, Any]]:
    """What `extras` holds that `kind` does not allow, as unresolved items (`path`, `reason`, `value`)."""
    data = extras_state(extras)
    settable = {c.__name__ for c in kind.settable}
    entries = {c.__name__ for c in kind.preamble}
    locked = set(kind.locked_classes())
    found = [
        (f"/settings/{i}", f"{type(v).__name__} is not settable in kind {kind.name}", data["settings"][i])
        for i, v in enumerate(extras.settings)
        if type(v).__name__ not in settable
    ]
    found += [
        (f"/options/{i}", f"option {o!r} is not allowed in kind {kind.name}", o)
        for i, o in enumerate(extras.options)
        if o not in kind.options
    ]
    found += [
        (
            f"/preamble/{slot}/{i}",
            f"{type(item).__name__} is locked by kind {kind.name}"
            if type(item).__name__ in locked
            else f"{type(item).__name__} is not an allowed preamble entry in kind {kind.name}",
            data["preamble"][slot][i],
        )
        for slot, i, item in extras.preamble.items()
        if type(item).__name__ not in entries
    ]
    return [{"path": path, "reason": reason, "value": value, "schema": {}} for path, reason, value in found]


def _closure(defs: Mapping[str, Any], roots: list[str]) -> dict[str, Any]:
    """The definitions `roots` name and the ones those name, in name order."""
    found: dict[str, Any] = {}
    todo = list(roots)
    while todo:
        name = todo.pop()
        if name not in found:
            found[name] = defs[name]
            todo += [r.rsplit("/", 1)[1] for r in _refs(defs[name])]
    return dict(sorted(found.items()))


def _refs(node: object) -> list[str]:
    """Every `$ref` under `node`."""
    if isinstance(node, dict):
        found: list[str] = []
        for key, value in cast("dict[str, object]", node).items():
            found += [str(value)] if key == "$ref" else _refs(value)
        return found
    if isinstance(node, list):
        return [ref for item in cast("list[object]", node) for ref in _refs(item)]
    return []


def schema(kind: Kind, package: Package, mode: Mode) -> dict[str, Any]:
    """The JSON Schema of the data of a document of `kind`: its `tree`, and the settings, options and preamble entries
    the kind allows, read by `package`, the one that renders it."""
    tree = tree_schema(kind.model, mode)
    defs: dict[str, Any] = tree.pop("$defs", {})
    title = str(tree["title"])
    defs[title] = tree
    properties: dict[str, Any] = {"tree": {"$ref": f"#/$defs/{title}"}}
    wanted: list[str] = []
    if kind.settable:
        names = [f"{c.__name__}Setting" for c in kind.settable]
        wanted += names
        properties["settings"] = {"type": "array", "items": {"oneOf": [{"$ref": f"#/$defs/{n}"} for n in names]}}
    if kind.options:
        properties["options"] = {"type": "array", "uniqueItems": True, "items": {"enum": list(kind.options)}}
    if kind.preamble:
        names = [f"{c.__name__}Entry" for c in kind.preamble]
        wanted += names
        slot = {"type": "array", "items": {"oneOf": [{"$ref": f"#/$defs/{n}"} for n in names]}}
        properties["preamble"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": dict.fromkeys(("before_class", "before_package", "after_package"), slot),
        }
    shared: dict[str, Any] = spec.json_schema(package)["$defs"] if wanted else {}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": kind.name,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["tree"],
        "$defs": dict(sorted((defs | _closure(shared, wanted)).items())),
    }


def _fields(node: Command | Environment | Passthrough) -> dict[str, Any]:
    return node.model_dump(mode="json", exclude={"content"})


def tree_state(node: Node) -> dict[str, Any]:
    """The state of a tree: every value written (V21), and for each node the fields that hold the package's defaults in
    `$defaults` (V24), known from `model_fields_set`, which says what the caller passed (V25)."""
    if isinstance(node, Comment):
        return {"type": type(node).__name__} | {f: getattr(node, f) for f in node.__tm_fields__}
    if isinstance(node, Passthrough):
        return {"type": "Passthrough"} | _fields(node)
    fields = _fields(node)
    out: dict[str, Any] = {"type": type(node).__name__} | fields
    if defaulted := [name for name in fields if name not in node.model_fields_set]:
        out[DEFAULTS] = defaulted
    if isinstance(node, Environment):
        out["content"] = [tree_state(child) for child in node.content]
    return out


def given(state: dict[str, Any]) -> dict[str, Any]:
    """`state` as the caller would have passed it: the fields marked as defaults left out, so the model fills them with
    its current defaults and `model_fields_set` is what the author set (V27)."""
    out = {k: v for k, v in state.items() if k not in (DEFAULTS, *state.get(DEFAULTS, ()))}
    if "content" in out:
        out["content"] = [given(child) for child in out["content"]]
    return out


def tree_from_state(model: Model, state: dict[str, Any]) -> Node:
    """The tree a stored state describes; raises an `ExceptionGroup` of texmodel `ValidationError` for one that does not
    fit the model."""
    return spec.from_dict(model, given(state))


def default_paths(node: Node, path: str = "") -> tuple[str, ...]:
    """The data paths of the fields that hold defaults (`/content/1/accent`), in document order."""
    if isinstance(node, Comment):
        return ()
    own = tuple(f"{path}/{name}" for name in _fields(node) if name not in node.model_fields_set)
    if isinstance(node, Environment):
        return own + tuple(
            p for i, child in enumerate(node.content) for p in default_paths(child, f"{path}/content/{i}")
        )
    return own


def defaults_table(model: Model) -> dict[str, Any]:
    """The defaults of the classes a kind's trees are made of, by `Class.field`: what the package would fill in."""
    validation = spec.json_schema(model)
    table: dict[str, Any] = {}
    for node in (validation, *validation.get("$defs", {}).values()):
        for name, schema in node.get("properties", {}).items():
            if "default" in schema:
                table[f"{node['title']}.{name}"] = schema["default"]
    return dict(sorted(table.items()))


def sty_hashes(sty: Mapping[str, str]) -> dict[str, str]:
    """The `.sty` files the template state records by hash, not by value (D6)."""
    return {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in sorted(sty.items())}
