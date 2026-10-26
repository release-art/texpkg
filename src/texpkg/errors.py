"""The errors of a package: a built-in base and a stable `.code` each (B11).

No class is shared between packages (each wheel embeds its own copy of this module), so a consumer catches the built-in
base (`ValueError`, `FileNotFoundError`) and reads `.code`, which is `TP-<area><nnn>` and never reused.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .document import HandEdit
    from .migration import Unresolved


class TexpkgError(Exception):
    """What every texpkg error carries: a stable code, where it happened and the fix."""

    def __init__(self, message: str, *, code: str, path: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path
        self.hint = hint


class DeclarationError(TexpkgError, ValueError):
    """A declaration (an asset, a layout, a kind, a distribution) is invalid."""


class PayloadError(TexpkgError, FileNotFoundError):
    """A payload that cannot be written whole: a source file is absent (A3)."""


class NotADocumentError(TexpkgError, FileNotFoundError):
    """The directory holds no readable document state (P27)."""


class DocumentExistsError(TexpkgError, FileExistsError):
    """`create` into a directory that already holds a document."""


class KindMismatchError(TexpkgError, ValueError):
    """A kind's `load` of a directory that holds another kind's document, or another package's (K3)."""

    def __init__(self, message: str, *, found: str, expected: str, path: str = "", hint: str = "") -> None:
        super().__init__(message, code="TP-D003", path=path, hint=hint)
        self.found = found
        self.expected = expected


class NewerDataError(TexpkgError, ValueError):
    """Data written for a newer `data` version than this release reads (V14)."""


class MigrationError(TexpkgError, ValueError):
    """Adopting a release failed; nothing was returned or written (V31). `unresolved` lists what no migration placed."""

    def __init__(self, message: str, *, code: str, unresolved: "tuple[Unresolved, ...]" = (), hint: str = "") -> None:
        super().__init__(message, code=code, hint=hint)
        self.unresolved = unresolved


class HandEditError(TexpkgError, ValueError):
    """`save` found a `.tex` that differs from the plan of what was last written (D8). `edits` lists them."""

    def __init__(self, message: str, *, edits: "tuple[HandEdit, ...]", hint: str = "") -> None:
        super().__init__(message, code="TP-D005", hint=hint)
        self.edits = edits
