"""One model's history: what a stored state needs to become a valid tree of the current model (V8, V9, V28, V30).

Written to move into texmodel (N5): it knows models, schemas and paths, not packages, kinds or releases. A problem is a
plain dict `{"path", "reason", "value", "schema"}` with the path a data path (`/content/1/content/0/text`).
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pydantic
from texmodel.components import Command, Environment

type Problem = dict[str, Any]

_NODE = re.compile(r"([A-Z][A-Za-z]*)(?:\[(\d+)\])?")


def pointer(loc: Sequence[str | int]) -> str:
    """The data path of a pydantic error location: a tagged child's class name follows its index and is not data."""
    out: list[str] = []
    after_index = False
    for part in loc:
        if after_index and isinstance(part, str):
            after_index = False
            continue
        after_index = isinstance(part, int)
        out.append(str(part))
    return "".join(f"/{part}" for part in out)


def violation_pointer(path: str) -> str:
    """The data path of a grammar violation's path (`Deck/Card[1]` is `/content/1`)."""
    parts = path.split("/")
    return "".join(f"/content/{m[2]}" for part in parts[1:] if (m := _NODE.fullmatch(part)) and m[2] is not None)


def schema_at(schema: Mapping[str, Any], loc: Sequence[str | int]) -> dict[str, Any]:
    """The schema of the field an error location names: `$defs[<class>].properties[<field>]`, `{}` if there is none."""
    classes = [str(p) for i, p in enumerate(loc) if isinstance(p, str) and i > 0 and isinstance(loc[i - 1], int)]
    owner = schema.get("$defs", {}).get(classes[-1]) if classes else schema
    field = loc[-1]
    found = (owner or {}).get("properties", {}).get(field) if isinstance(field, str) and field != "content" else None
    return cast("dict[str, Any]", found) if isinstance(found, dict) else {}


def problems(
    model: type[Command] | type[Environment], data: dict[str, Any], schema: Mapping[str, Any]
) -> list[Problem]:
    """Everything that stops `data` from being a valid tree of `model`: pydantic's errors with their constraint,
    then the grammar's violations (V30)."""
    try:
        tree = model.model_validate(data)
    except pydantic.ValidationError as exc:
        return [
            {
                "path": pointer(e["loc"]),
                "reason": e["msg"],
                "value": e.get("input"),
                "schema": schema_at(schema, e["loc"]),
            }
            for e in exc.errors(include_url=False)
        ]
    return [
        {"path": violation_pointer(v.path), "reason": v.message, "value": None, "schema": {}} for v in tree.violations()
    ]
