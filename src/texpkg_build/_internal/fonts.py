"""Which font files a LuaTeX run embedded, and which of them came from outside the directories it was allowed (A7, A8).

Written to move into texmodel_build (N5, V9), so it imports nothing of texpkg. luaotfload can substitute a system font
for a missing one without an error; the PDF then carries a font the document directory does not hold. The log names
every embedded font file as `<path>`, relative to the directory when it is the document's own. It does not see the
fonts inside an included PDF: the check says where it stops.
"""

import re
from collections.abc import Sequence

_FONT = re.compile(r"<([^<>\s][^<>\n]*?\.(?:otf|ttf|ttc|pfb|pfa|t1))>", re.IGNORECASE)


def embedded(log: str) -> list[str]:
    """The font files the log says were embedded, as written, once each and in order."""
    return list(dict.fromkeys(m[1] for m in _FONT.finditer(log)))


def outside(log: str, allowed: Sequence[str]) -> list[str]:
    """The embedded font files that are not relative to the document directory and not under one of `allowed`."""
    return [
        path
        for path in embedded(log)
        if path.startswith("/") and not any(path == a or path.startswith(a.rstrip("/") + "/") for a in allowed)
    ]
