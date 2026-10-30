"""The synthetic acme datasheet: the table of standards of release 4 became a fixed tick list in release 5."""

import enum

from texmodel.body import Comment
from texmodel.components import Command, Environment
from texmodel.ext.fit import Fit
from texmodel.package import Package
from texmodel.types import Choice, Length, Text


class Audit(Comment):
    """Who checked the sheet: a comment in the `.tex`, kept in the data."""

    template = "audited by #who"
    who: str


pkg = Package("acme-sheet", prefix="as", version="5.0.0", date="2026/10/25", description="Datasheets", comments=[Audit])

# A fitted heading: `\asFitTitle`, with the lengths `\asTitleSize` and `\asTitleLineSize` (`\newlength`).
fit = Fit("Title", target=Length("8mm"), floor=Length("4mm"), room=Length("10mm"))
fit.declare(pkg)


@enum.unique
class Standard(Choice):
    """A standard a product can meet."""

    ISO9001 = "ISO 9001"
    ISO14001 = "ISO 14001"


@pkg.command
class Heading(Command):
    """The product's name."""

    text: Text

    body = r"\par\textbf{#text}\par"


@pkg.command
class Ticks(Command):
    """The standards the product meets, ticked from the fixed list."""

    met: tuple[Standard, ...]

    body = r"\par Standards: #met\par"


@pkg.environment
class Sheet(Environment):
    """A product's datasheet."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Heading, Ticks]
