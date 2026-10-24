"""Hand edits: a `.tex` against the plan of what was last written (D7-D9).

The plan says which node wrote each line, so an edit is found by path even when the model has moved on.
"""

import pathlib
import re
from collections.abc import Sequence

from texmodel.plan import Edit, Plan

from . import directory

_NODE = re.compile(r"[A-Z][A-Za-z]*\[(\d+)\]")  # a component's name: a capital, then letters (TM-M001)


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
            found += [(name, edit) for edit in Plan.from_json(saved).edits(text)]
    return found
