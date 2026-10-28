"""Constants the datasheet's package publishes to the code that reads its documents (P31)."""

from typing import Final

MAX_TICKS: Final = 3
STANDARD_NAMES: Final = ("ISO9001", "ISO14001")
DEFAULT_FONT: Final = "Acme Sans"

__all__ = ["DEFAULT_FONT", "MAX_TICKS", "STANDARD_NAMES"]
