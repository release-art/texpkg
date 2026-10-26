"""The synthetic acme brand: a `.sty` with two document kinds on it (`expert` and `vocab`)."""

import enum
import importlib.resources

import pydantic
from texmodel.body import TemplateRef
from texmodel.components import Command, Environment, Value
from texmodel.package import Package
from texmodel.types import CMYK, Choice, Colour, Length, Raw, Text

from texpkg import Design


class Palette(pydantic.BaseModel):
    slate: Raw
    moss: Raw


class Tokens(pydantic.BaseModel):
    """The brand's design data."""

    palette: Palette


design = Design(Tokens, "tokens.json")
tokens = design.load(importlib.resources.files(__package__ or "acme_brand"))  # the .sty is filled from it (L1)

pkg = Package("acme-brand", prefix="ab", version="1.0.0", date="2026/10/21", description="The acme brand")
pkg.library("acme", TemplateRef("acme.tex"), fill=tokens)


@pkg.value
class FactGap(Value[Length]):
    """Space under each fact."""

    default = Length("2mm")


@pkg.value
class Ink(Value[Colour]):
    """The text colour."""

    default = CMYK(0, 0, 0, 0.95)


@pkg.value
class Compact(Value[bool]):
    """Tighten the layout."""

    default = False


@enum.unique
class Accent(Choice):
    """The brand colours a fact may take."""

    SLATE = "ab-slate"
    MOSS = "ab-moss"


@pkg.command
class Mark(Command):
    """The brand's lock-up."""

    body = r"\par\noindent\includegraphics[height=6mm]{lockup.pdf}\par"


@pkg.command
class Title(Command):
    """The subject's name."""

    text: Text

    body = r"\par\noindent{\ifabCompact\large\else\Large\fi\bfseries\color{ab-ink}#text}\par"


@pkg.command
class Fact(Command):
    """One short sentence under the title."""

    text: Text
    accent: Accent = Accent.SLATE

    body = r"\par\noindent\textcolor{#accent}{#text}\par\vspace{\abFactGap}"


@pkg.command
class Term(Command):
    """A word and what it means."""

    word: Text
    meaning: Text

    body = r"\par\noindent\textbf{#word}\quad #meaning\par"


@pkg.environment
class Card(Environment):
    """A card: a title and up to three facts."""

    begin = r"\begin{minipage}{\linewidth}"
    end = r"\end{minipage}\par\medskip"

    children = [Title, Fact.times(1, 3)]


@pkg.environment
class Deck(Environment):
    """Cards under the brand's lock-up."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Mark, Card.times.at_least_one()]


@pkg.environment
class Glossary(Environment):
    """Words and their meanings."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Term.times.at_least_one()]
