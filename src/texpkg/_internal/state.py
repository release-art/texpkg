"""The stored form of a document: its schemas (V26).

Two schemas per kind, from pydantic's two modes: the input one (a field with a default is optional) and the stored one
(every field is written, V21, so every field is required, and a node lists the fields that hold defaults in
`$defaults`).
"""

import copy
from typing import Any, Literal

from texmodel import spec

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
