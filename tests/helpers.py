"""Shared by the tests: the fixtures directory and the golden-file comparison."""

import os
import pathlib
import re

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
STAMP = re.compile(r"generated with texmodel \d+\.\d+\.\d+")


def golden(path: pathlib.Path, text: str) -> None:
    """Compare `text` with the committed file, the generator's version masked so a texmodel release does not churn it;
    `UPDATE_GOLDEN=1` rewrites it (then read the diff)."""
    text = STAMP.sub("generated with texmodel X.Y.Z", text)
    if os.environ.get("UPDATE_GOLDEN"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text, f"{path} differs; UPDATE_GOLDEN=1 rewrites it"
