"""Diffing two snapshots into bumps (V12, V13): Avro-style rules over schemas, names and signatures over the interface.

In the run time because `changes(old, new)` diffs two shipped snapshots. Written to move into texmodel (V9, X5): it
reads
JSON Schema and plain dicts, and only the triples of texpkg.
"""

import dataclasses
import enum
import re
from typing import Any, cast

from ..contracts import Pair, Triple


@enum.unique
class Level(enum.IntEnum):
    """How much a change asks of a contract's consumers; the largest of a contract's changes decides its bump (V10)."""

    NONE = 0
    REVISION = 1  # implementation only: a description, a default, a doc
    COMPATIBLE = 2  # an addition: old data and old callers still work
    BREAKING = 3


@dataclasses.dataclass(frozen=True)
class Change:
    level: Level
    where: str  # `Class.field`, `kind expert`, `component Fact`
    what: str


_UPPER = ("maxLength", "maximum", "maxItems", "exclusiveMaximum")  # lowering one tightens it
_LOWER = ("minLength", "minimum", "minItems", "exclusiveMinimum")  # raising one tightens it


def _compare_property(where: str, old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    out: list[Change] = []
    for key in ("type", "$ref", "const", "format", "pattern"):
        if old.get(key) != new.get(key):
            out.append(Change(Level.BREAKING, where, f"{key} changed from {old.get(key)!r} to {new.get(key)!r}"))
    if (gone := [v for v in old.get("enum", ()) if v not in new.get("enum", ())]) or ("enum" in old) != ("enum" in new):
        out.append(Change(Level.BREAKING, where, f"values no longer allowed: {gone or 'any'}"))
    elif added := [v for v in new.get("enum", ()) if v not in old.get("enum", ())]:
        out.append(Change(Level.COMPATIBLE, where, f"values added: {added}"))
    for key in _UPPER + _LOWER:
        was, now = old.get(key), new.get(key)
        if was == now:
            continue
        tighter = now is not None and (was is None or (now < was if key in _UPPER else now > was))
        out.append(Change(Level.BREAKING if tighter else Level.COMPATIBLE, where, f"{key} {was} -> {now}"))
    if old.get("items") != new.get("items") and "items" in old:
        out += _compare_items(where, old["items"], new.get("items", {}))
    out += _compare_inline(where, old.get("properties", {}), new.get("properties", {}))
    for key in ("default", "description", "title"):
        if old.get(key) != new.get(key):
            out.append(Change(Level.REVISION, where, f"{key} changed"))
    return out


def _compare_inline(where: str, before: dict[str, Any], after: dict[str, Any]) -> list[Change]:
    """The properties of an object written inline in a property, not as a class of its own."""
    out: list[Change] = []
    for name in before:
        if name in after:
            out += _compare_property(f"{where}.{name}", before[name], after[name])
        else:
            out.append(Change(Level.BREAKING, f"{where}.{name}", "removed"))
    return out + [Change(Level.COMPATIBLE, f"{where}.{name}", "added") for name in sorted(after.keys() - before.keys())]


def _compare_items(where: str, old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    """The element schema of a list: a branch of a union that went is breaking, one that came is compatible."""

    def refs(items: dict[str, Any]) -> set[str]:
        branches = items.get("oneOf") or [items]
        return {b.get("$ref", b.get("type", "")) for b in branches}

    gone, added = refs(old) - refs(new), refs(new) - refs(old)
    out = [Change(Level.BREAKING, where, f"{g} is no longer allowed here") for g in sorted(gone)]
    out += [Change(Level.COMPATIBLE, where, f"{a} is allowed here") for a in sorted(added)]
    return out or ([] if old == new else _compare_property(where, old, new))


def _classes(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = {str(schema.get("title")): schema}
    out |= {str(node.get("title", name)): node for name, node in schema.get("$defs", {}).items()}
    return out


def schema_changes(old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    """What changed in the data a kind accepts (the input schema): the changes, each with its level (V12)."""
    out: list[Change] = []
    was, now = _classes(old), _classes(new)
    for title in sorted(was.keys() - now.keys()):
        out.append(Change(Level.BREAKING, title, "no longer part of the kind"))
    for title in sorted(now.keys() - was.keys()):
        out.append(Change(Level.COMPATIBLE, title, "added to the kind"))
    for title in sorted(was.keys() & now.keys()):
        before, after = was[title].get("properties", {}), now[title].get("properties", {})
        renamed = {p.get("x-renamed-from"): name for name, p in after.items() if p.get("x-renamed-from")}
        for name in before:
            if name in after:
                out += _compare_property(f"{title}.{name}", before[name], after[name])
            elif name in renamed:
                out.append(
                    Change(Level.COMPATIBLE, f"{title}.{name}", f"renamed {renamed[name]} (old name still read)")
                )
            else:
                out.append(Change(Level.BREAKING, f"{title}.{name}", "removed"))
        now_required, was_required = set(now[title].get("required", ())), set(was[title].get("required", ()))
        for name in sorted((now_required - was_required) & before.keys() & after.keys()):
            out.append(Change(Level.BREAKING, f"{title}.{name}", "became required"))
        for name in sorted(after.keys() - before.keys() - set(renamed.values())):
            level = Level.BREAKING if name in now_required else Level.COMPATIBLE
            out.append(Change(level, f"{title}.{name}", "added" + (" and required" if name in now_required else "")))
    return out


def interface_changes(old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    """What changed in the public names and their signatures, and in the kinds and variants (V12)."""
    out: list[Change] = []
    for section, label in (("components", "component"), ("kinds", "kind")):
        was, now = old.get(section, {}), new.get(section, {})
        out += [Change(Level.BREAKING, f"{label} {n}", "removed") for n in sorted(was.keys() - now.keys())]
        out += [Change(Level.COMPATIBLE, f"{label} {n}", "added") for n in sorted(now.keys() - was.keys())]
        for name in sorted(was.keys() & now.keys()):
            out += _compare_entry(f"{label} {name}", was[name], now[name])
    return out + _public_changes(old.get("public", {}), new.get("public", {}))


def _shape(value: object) -> object:
    """What a published value is the type of: its Python type, or the class of an instance (`$class`)."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value).get("$class", dict)
    return type(value)


def _public_changes(old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    """The published constants (P31): a name that went, or a value of another type, breaks the code that reads it; a
    new name is an addition; a new value of the same type is a revision, as the contracts it feeds show the rest."""
    out = [Change(Level.BREAKING, f"public {n}", "removed") for n in sorted(old.keys() - new.keys())]
    out += [Change(Level.COMPATIBLE, f"public {n}", "added") for n in sorted(new.keys() - old.keys())]
    for name in sorted(old.keys() & new.keys()):
        same = _shape(old[name]) == _shape(new[name])  # 1 == True, so equal values still differ by type
        if same and old[name] == new[name]:
            continue
        out.append(Change(Level.REVISION if same else Level.BREAKING, f"public {name}", "value changed"))
    return out


def _compare_entry(where: str, old: dict[str, Any], new: dict[str, Any]) -> list[Change]:
    out: list[Change] = []
    for key in sorted(old.keys() | new.keys()):
        if old.get(key) == new.get(key):
            continue
        if key == "variants":
            gone, added = set(old.get(key, ())) - set(new.get(key, ())), set(new.get(key, ())) - set(old.get(key, ()))
            out += [Change(Level.BREAKING, where, f"variant {v} removed") for v in sorted(gone)]
            out += [Change(Level.COMPATIBLE, where, f"variant {v} added") for v in sorted(added)]
        elif key == "doc":
            out.append(Change(Level.REVISION, where, "documentation changed"))
        elif key == "signature":
            added = new.get(key, [])[len(old.get(key, [])) :]
            keeps = new.get(key, [])[: len(old.get(key, []))] == old.get(key, [])
            if keeps and all(arg[2] for arg in added):  # trailing optional arguments: old calls still work
                out.append(Change(Level.COMPATIBLE, where, f"optional arguments added: {[a[0] for a in added]}"))
            else:
                out.append(Change(Level.BREAKING, where, "signature changed"))
        else:
            out.append(Change(Level.BREAKING, where, f"{key} changed from {old.get(key)!r} to {new.get(key)!r}"))
    return out


def worst(changes: list[Change]) -> Level:
    return max((c.level for c in changes), default=Level.NONE)


def bump(previous: Triple, level: Level) -> Triple:
    """libtool's rules (V10): none keeps it, a revision adds one, an addition raises `current` and `age`, a break
    resets them."""
    match level:
        case Level.NONE:
            return previous
        case Level.REVISION:
            return Triple(previous.current, previous.revision + 1, previous.age)
        case Level.COMPATIBLE:
            return Triple(previous.current + 1, 0, previous.age + 1)
        case Level.BREAKING:
            return Triple(previous.current + 1, 0, 0)


def bump_output(previous: Pair, change: str) -> Pair:
    """`output` has no age: `current` when the appearance changed, `revision` when only bytes did (V10). `change` is the
    author's statement; an empty one means nothing changed."""
    match change:
        case "current":
            return Pair(previous.current + 1, 0)
        case "revision":
            return Pair(previous.current, previous.revision + 1)
        case _:
            return previous


Version = tuple[int, int, int]


RELEASE = re.compile(r"\d+\.\d+\.\d+")  # `X.Y.Z` as the start of a version string


def parse_version(text: str) -> Version:
    major, minor, patch = (int(p) for p in text.split(".")[:3])
    return major, minor, patch


def required_release(previous: str, data: Level, interface: Level, output_changed: bool) -> str:
    """The smallest release number that does not understate the contracts (V13): a break is major, any other change
    minor, no contract change a patch; each one place lower before 1.0."""
    major, minor, patch = parse_version(previous)
    breaking = Level.BREAKING in (data, interface)
    changed = bool(data or interface) or output_changed
    if major == 0:
        return f"0.{minor + 1}.0" if breaking else f"0.{minor}.{patch + 1}"
    if breaking:
        return f"{major + 1}.0.0"
    return f"{major}.{minor + 1}.0" if changed else f"{major}.{minor}.{patch + 1}"
