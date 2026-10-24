"""The errors of a package: a built-in base and a stable `.code` each (B11).

No class is shared between packages (each wheel embeds its own copy of this module), so a consumer catches the built-in
base (`ValueError`, `FileNotFoundError`) and reads `.code`, which is `TP-<area><nnn>` and never reused.
"""


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
