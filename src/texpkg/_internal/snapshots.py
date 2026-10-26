"""The contract snapshots a wheel ships (V11, V33, V37), read at run time: what changed between two `data` versions."""

import importlib.resources.abc
import json
import re

from ..contracts import Changes
from . import classify
from .versions import Versions

_RELEASE = re.compile(r"\d+\.\d+\.\d+")
VERSIONS = "versions.toml"


def releases(root: importlib.resources.abc.Traversable | None) -> list[str]:
    """The frozen releases a wheel carries, oldest first."""
    found = (
        [p.name for p in root.iterdir() if p.is_dir() and _RELEASE.fullmatch(p.name)] if root and root.is_dir() else []
    )
    return sorted(found, key=classify.parse_version)


def changes(root: importlib.resources.abc.Traversable | None, kind: str, old: int, new: int) -> Changes:
    """What changed in `kind` between `data` versions `old` and `new`: fields added, removed and tightened, the author's
    notes and the release of each version crossed (V33), read from the shipped snapshots. Empty where there are none."""
    held = releases(root)
    if root is None or not held:
        return Changes()
    latest = Versions.parse(root.joinpath(held[-1], VERSIONS).read_text(encoding="utf-8"))
    crossed = range(old + 1, new + 1)
    out = Changes(
        notes=tuple(latest.notes[v] for v in crossed if latest.notes.get(v)),
        releases={v: latest.releases[v] for v in crossed if v in latest.releases},
    )
    first, last = latest.releases.get(old), latest.releases.get(new)
    name = f"kinds/{kind}.input.schema.json"
    if (
        not first
        or not last
        or first == last
        or not (root.joinpath(first, *name.split("/")).is_file() and root.joinpath(last, *name.split("/")).is_file())
    ):
        return out
    before = json.loads(root.joinpath(first, *name.split("/")).read_text(encoding="utf-8"))
    after = json.loads(root.joinpath(last, *name.split("/")).read_text(encoding="utf-8"))
    found = classify.schema_changes(before, after)
    gone = {"removed", "no longer part of the kind"}
    added = [c.where for c in found if c.what.startswith("added") or c.what.endswith("added to the kind")]
    removed = [c.where for c in found if c.what in gone]
    tightened = [
        c.where
        for c in found
        if c.level is classify.Level.BREAKING and c.what not in gone and not c.what.startswith("added")
    ]
    return Changes(
        added=tuple(dict.fromkeys(added)),
        removed=tuple(dict.fromkeys(removed)),
        tightened=tuple(dict.fromkeys(tightened)),
        notes=out.notes,
        releases=out.releases,
    )
