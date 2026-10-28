"""Adopting a release: the stored state of a document becomes a valid tree of this release, or nothing does (V14, V22,
V23, V29, V31, V32).

Every migration across the `data` versions crossed runs, in the order the build's, the kind's, the consumer's; the
result is validated whole; any unresolved item, any validation error and any stored field the model no longer has
left aborts with the report.
"""

import copy
import dataclasses
import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, cast

from texmodel.components import Node
from texmodel.package import Package

from ..declaration import Kind
from ..errors import MigrationError
from ..migration import DefaultChange, Migration, Unresolved
from . import state
from .envelope import Envelope
from .history import problems, unplaced
from .state import Extras

UNRESOLVED = (
    "$unresolved"  # in the state a migration gets: what the earlier ones left, as `{"path", "reason", "value"}`
)
EXTRAS = "$extras"  # in the state a migration gets: the document's `settings`, `options` and `preamble` (D10)


def _policy(changes: DefaultChange | Mapping[str, DefaultChange], path: str, key: str) -> DefaultChange:
    """The policy for a default: the one named by the field's data path, else by `Class.field`, else `FOLLOW` (V23)."""
    if isinstance(changes, DefaultChange):
        return changes
    return changes.get(path, changes.get(key, DefaultChange.FOLLOW))


def _walk(node: dict[str, Any], path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    yield path, node
    for i, child in enumerate(node.get("content", ())):
        yield from _walk(child, f"{path}/content/{i}")


def default_changes(
    tree: dict[str, Any],
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    policy: DefaultChange | Mapping[str, DefaultChange],
) -> list[dict[str, Any]]:
    """Apply the consumer's policy to every value still marked as a default whose default this release changed (V22): a
    value that follows needs nothing (the model fills the new default); one that is frozen keeps the old value and stops
    being marked; one that asks is returned as unresolved."""
    changed = {key for key in old.keys() & new.keys() if old[key] != new[key]}
    asked: list[dict[str, Any]] = []
    for path, node in _walk(tree):
        for field in list(node.get(state.DEFAULTS, ())):
            key = f"{node.get('type')}.{field}"
            if key not in changed:
                continue
            action = _policy(policy, f"{path}/{field}", key)
            if action is DefaultChange.FREEZE:
                node[field] = old[key]
                node[state.DEFAULTS].remove(field)
            elif action is DefaultChange.ASK:
                reason = f"the default of {key} changed from {old[key]!r} to {new[key]!r}"
                asked.append(
                    {"path": f"{path}/{field}", "reason": reason, "value": node.get(field), "boundary": "defaults"}
                )
        if not node.get(state.DEFAULTS, True):
            del node[state.DEFAULTS]
    return asked


def _kind_migrations(kind: Kind, boundary: int, base_data: Mapping[int, int] | None) -> list[Migration]:
    """The kind's own migrations for `boundary`. An exposed base kind's are numbered by the base: the ones for the base
    versions that this package's `boundary` stands for run at it (P30)."""
    if base_data is None:
        return [m for m in kind.migrations if m.to == boundary]
    low, high = base_data.get(boundary - 1, 0), base_data.get(boundary, 0)
    return [m for m in kind.migrations if low < m.to <= high]


def _data_path(path: str) -> list[str]:
    """The parts of a texmodel path (`settings[1].value`) as data keys (`settings`, `1`, `value`)."""
    return [part for part in re.split(r"[.\[\]]+", path) if part]


def _value_at(data: object, keys: list[str]) -> object:
    for key in keys:
        try:
            data = (
                cast("list[object]", data)[int(key)] if isinstance(data, list) else cast("dict[str, object]", data)[key]
            )
        except KeyError, IndexError, TypeError, ValueError:
            return None
    return data


def _extras_problems(kind: Kind, package: Package, data: dict[str, Any]) -> tuple[Extras, list[dict[str, Any]]]:
    """The extras `data` describes and what stops them from being the kind's: texmodel's errors and what the kind
    does not allow, as unresolved items."""
    try:
        extras = state.extras_from(package, data)
    except ExceptionGroup as group:
        found: list[dict[str, Any]] = []
        for e in group.exceptions:
            keys = _data_path(str(getattr(e, "path", "")))
            found.append({"path": "/" + "/".join(keys), "reason": str(e), "value": _value_at(data, keys), "schema": {}})
        return Extras(), found
    return extras, state.not_allowed(kind, extras)


def kind_default_changes(
    package: Package,
    extras: Extras,
    saved: Mapping[str, Any],
    current: Mapping[str, Any],
    policy: DefaultChange | Mapping[str, DefaultChange],
) -> tuple[Extras, list[dict[str, Any]]]:
    """Apply the consumer's policy to every kind default this release changed (V22), for a value the document does
    not set itself: following needs nothing (the kind writes the new default); a frozen one becomes a setting of the
    document with the old value; one that asks is returned as unresolved. The key is the value's class name, the path
    `/defaults/<class>`."""
    own = {type(v).__name__ for v in extras.settings}
    frozen: list[Any] = []
    asked: list[dict[str, Any]] = []
    for name in sorted(saved.keys() & current.keys()):
        if saved[name] == current[name] or name in own:
            continue
        action = _policy(policy, f"/defaults/{name}", name)
        if action is DefaultChange.FREEZE:
            frozen.append(saved[name])
        elif action is DefaultChange.ASK:
            reason = f"the default of {name} changed from {saved[name]!r} to {current[name]!r}"
            asked.append({"path": f"/defaults/{name}", "reason": reason, "value": saved[name], "boundary": "defaults"})
    if not frozen:
        return extras, asked
    try:
        kept = state.extras_from(package, {"settings": frozen}).settings
    except ExceptionGroup as group:
        reason = "; ".join(str(e) for e in group.exceptions)
        return extras, [*asked, {"path": "/defaults", "reason": reason, "value": frozen, "boundary": "defaults"}]
    return dataclasses.replace(extras, settings=(*extras.settings, *kept)), asked


def adopt(
    *,
    kind: Kind,
    package: Package,
    envelope: Envelope,
    current: int,
    age: int,
    consumer: Sequence[Migration],
    policy: DefaultChange | Mapping[str, DefaultChange],
    saved_defaults: Mapping[str, Any] | None,
    saved_kind_defaults: Mapping[str, Any] | None = None,
    kind_defaults: Mapping[str, Any] | None = None,
    base_data: Mapping[int, int] | None = None,
) -> tuple[Node, Extras]:
    """The tree and extras of `kind` that `envelope` describes at `data` version `current`, or a `MigrationError` naming
    everything that no migration placed. Nothing is written."""
    tree = copy.deepcopy(envelope.tree)
    extras_data = copy.deepcopy(envelope.extras)
    left: list[dict[str, Any]] = []
    if saved_defaults is not None:
        left += default_changes(tree, saved_defaults, state.defaults_table(kind.model), policy)
    if envelope.data < current - age:
        for boundary in range(envelope.data + 1, current + 1):
            label = f"{boundary - 1} -> {boundary}"
            for migration in (*_kind_migrations(kind, boundary, base_data), *(m for m in consumer if m.to == boundary)):
                tree[UNRESOLVED], tree[EXTRAS] = left, extras_data
                result = migration(tree)
                tree = result.state
                extras_data = tree.pop(EXTRAS, {})
                left = [*tree.pop(UNRESOLVED, []), *({**vars(u), "boundary": label} for u in result.unresolved)]
    schema = state.tree_schema(kind.model, "validation")
    extras, found = _extras_problems(kind, package, extras_data)
    left += [{**p, "boundary": "validation"} for p in found]
    if saved_kind_defaults is not None and not found:
        extras, asked = kind_default_changes(package, extras, saved_kind_defaults, kind_defaults or {}, policy)
        left += asked
    left += [{**p, "boundary": "validation"} for p in unplaced(tree, schema)]
    left += [{**p, "boundary": "validation"} for p in problems(kind.model, state.given(tree), schema)]
    if left:
        items = tuple(
            Unresolved(i["path"], i["reason"], i.get("value"), i.get("schema") or {}, i.get("boundary", ""))
            for i in left
        )
        shown = "; ".join(f"{u.path or '/'} ({u.boundary}): {u.reason}" for u in items)
        raise MigrationError(
            f"{len(items)} unresolved: {shown}",
            code="TP-M003",
            unresolved=items,
            hint="extend the process with a migration of your own: load(path, migrations=[...])",
        )
    return state.tree_from_state(kind.model, tree), extras
