"""Hand edits: a `.tex` against the plan of what was last written (D7-D9).

The plan says which node wrote each line, so an edit is found by path even when the model has moved on.
"""

import pathlib
import re
from collections.abc import Sequence

from texmodel.plan import Edit, Plan
from texmodel.preamble import PreambleSlots

from . import directory

_NODE = re.compile(r"[A-Z][A-Za-z]*\[(\d+)\]")  # a component's name: a capital, then letters (TM-M001)


_SETTING = re.compile(r"settings\[(\d+)\]")
_ENTRY = re.compile(r"preamble\.(before_class|before_package|after_package)\[(\d+)\]")


def extra_path(plan_path: str, *, locked: int, leading: PreambleSlots, fields: Sequence[str]) -> str:
    """The data path of a line that a setting, a preamble entry, the `metadata` or the `pdf` of the document wrote
    (D10), or `""`: the kind's own `locked` settings come first in the plan, then the document's, the `leading` entries
    (the layout's and the kind's locked ones) lead each preamble slot, and the kind writes the `fields` it fixes."""
    if plan_path in ("metadata", "pdf"):
        return "" if plan_path in fields else f"/{plan_path}"
    if found := _SETTING.fullmatch(plan_path):
        return f"/settings/{int(found[1]) - locked}" if int(found[1]) >= locked else ""
    if found := _ENTRY.fullmatch(plan_path):
        own = int(found[2]) - len(getattr(leading, found[1]))
        return f"/preamble/{found[1]}/{own}" if own >= 0 else ""
    return ""


def is_locked(plan_path: str, *, locked: int, leading: PreambleSlots, fields: Sequence[str]) -> bool:
    """Whether the line is one the kind fixes: a setting among its `locked` ones, an entry among the `leading` ones of
    a preamble slot, or a document field it writes itself."""
    if plan_path in fields:
        return True
    if found := _SETTING.fullmatch(plan_path):
        return int(found[1]) < locked
    if found := _ENTRY.fullmatch(plan_path):
        return int(found[2]) < len(getattr(leading, found[1]))
    return False


def data_path(plan_path: str) -> str:
    """The data path of a plan path: `Deck[0]/Card[1]/Title[0]` is `/content/1/content/0`, the root being the document.
    A line that no node wrote (`header`, `preamble.before_package[0]`, `settings[2]`) keeps its plan path."""
    nodes = [_NODE.fullmatch(part) for part in plan_path.split("/")]
    if not all(nodes):
        return plan_path
    return "".join(f"/content/{node[1]}" for node in nodes[1:] if node)


def edits(root: pathlib.Path, files: Sequence[tuple[str | None, str]]) -> list[tuple[str, Edit]]:
    """For each `(variant, file name)` that exists beside a saved plan: the file and its edits against that plan."""
    found: list[tuple[str, Edit]] = []
    for variant, name in files:
        text, saved = directory.read(root, name), directory.read(root, directory.plan_file(variant))
        if text is not None and saved is not None:
            found += [(name, edit) for edit in Plan.from_json(saved).edits(text, file=root / name)]
    return found
