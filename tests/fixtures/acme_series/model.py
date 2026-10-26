"""The parts every series shares; each series' own classes are generated from `series.json` (K4)."""

from texmodel.body import TemplateRef
from texmodel.components import Command
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("acme-series", prefix="se", version="1.0.0", date="2026/10/22", description="Card series from data")

pkg.library("series", TemplateRef("series.tex"))


@pkg.command
class Title(Command):
    """The subject's name."""

    text: Text

    body = r"\par\noindent\textbf{#text}\par"
