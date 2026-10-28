"""Constants the datasheet's package publishes to the code that reads its documents (P31)."""

import dataclasses
from typing import Final

from texmodel.types import Length


@dataclasses.dataclass(frozen=True)
class Margin:
    top: Length
    bottom: Length


MAX_TICKS: Final = 3
STANDARD_NAMES: Final = ("ISO9001", "ISO14001")
DEFAULT_FONT: Final = "Acme Sans"
BLEED: Final = Length("3mm")
MARGIN: Final = Margin(top=Length("3mm"), bottom=Length("5mm"))

__all__ = ["BLEED", "DEFAULT_FONT", "MARGIN", "MAX_TICKS", "STANDARD_NAMES"]
