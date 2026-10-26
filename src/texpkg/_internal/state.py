"""The stored form of a document: its schemas (V26).

Two schemas per kind, from pydantic's two modes: the input one (a field with a default is optional) and the stored one
(every field is written, V21, so every field is required, and a node lists the fields that hold defaults in
`$defaults`).
"""

import copy
import hashlib
from collections.abc import Mapping
from typing import Any, Literal

from texmodel import spec
from texmodel.body import Comment
from texmodel.components import Command, Environment, Node, Passthrough

from ..declaration import Model
from ..errors import DeclarationError

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


def schema(model: Model, mode: Mode) -> dict[str, Any]:
    """The JSON Schema of the data a kind's `model` takes (`validation`) or stores (`serialization`)."""
    if mode not in ("validation", "serialization"):
        raise DeclarationError(
            f"schema mode {mode!r}", code="TP-K008", hint='use "validation" (the input) or "serialization" (the stored)'
        )
    validation = spec.json_schema(model)
    return validation if mode == "validation" else stored(validation)


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
