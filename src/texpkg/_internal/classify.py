"""Diffing two snapshots into bumps (V12, V13): Avro-style rules over schemas, names and signatures over the interface.

In the run time because `changes(old, new)` diffs two shipped snapshots. The schema half is texmodel's
(`texmodel.history`).
"""

import re
from typing import Any, cast

from texmodel.history import Change, Level

from ..contracts import Pair, Triple


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
