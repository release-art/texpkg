"""The document directory (P27, D5): one visible `_texpkg/` folder beside the `.tex`, the payload and the consumer's own
files. Everything here takes the directory and text; nothing knows what a kind is."""

import pathlib
import shutil
from collections.abc import Mapping

DIR = "_texpkg"
STATE = f"{DIR}/state.json"  # the user's state (D1)
TEMPLATE = f"{DIR}/template.json"  # the package as it was when the document was saved (D1, D6)
HISTORY = 3  # the last saves kept (D2)


def plan_file(variant: str | None) -> str:
    """The saved plan of the `.tex` of `variant` (D7)."""
    return f"{DIR}/plan.json" if variant is None else f"{DIR}/plan-{variant}.json"


def read(root: pathlib.Path, rel: str) -> str | None:
    path = root / rel
    return path.read_text(encoding="utf-8") if path.is_file() else None


def differing(root: pathlib.Path, files: Mapping[str, str]) -> dict[str, str]:
    """The files whose text on disk is not `files`' (absent counts): content, never time (A4)."""
    return {rel: text for rel, text in files.items() if read(root, rel) != text}


def write(root: pathlib.Path, files: Mapping[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def rotate_history(root: pathlib.Path) -> None:
    """Keep the pair of states on disk as `history/1`, the earlier ones one further, and drop what is beyond `HISTORY`
    (D2, D3). Nothing happens when there is no pair yet."""
    pair = [rel for rel in (STATE, TEMPLATE) if (root / rel).is_file()]
    if not pair:
        return
    history = root / DIR / "history"
    shutil.rmtree(history / str(HISTORY), ignore_errors=True)
    for n in range(HISTORY - 1, 0, -1):
        if (history / str(n)).is_dir():
            (history / str(n)).rename(history / str(n + 1))
    (history / "1").mkdir(parents=True)
    for rel in pair:
        shutil.copyfile(root / rel, history / "1" / pathlib.PurePosixPath(rel).name)
