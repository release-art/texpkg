"""The envelope of a stored document: `{package, kind, data, tree}` (K3). It names the package and kind the tree belongs
to and the `data` version it was written for (V14)."""

import dataclasses
import json
from typing import Any

from ..errors import NotADocumentError


def dumps(value: object) -> str:
    """The text of a state file: stable, readable, one trailing newline."""
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


@dataclasses.dataclass(frozen=True)
class Envelope:
    package: str
    kind: str
    data: int
    tree: dict[str, Any]

    def to_text(self) -> str:
        return dumps({"package": self.package, "kind": self.kind, "data": self.data, "tree": self.tree})

    @classmethod
    def parse(cls, text: str, where: str) -> "Envelope":
        try:
            found = json.loads(text)
            return cls(str(found["package"]), str(found["kind"]), int(found["data"]), dict(found["tree"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise NotADocumentError(
                f"{where}: not a document state ({exc!r})",
                code="TP-D001",
                path=where,
                hint="it is written by a kind's create and save",
            ) from exc
