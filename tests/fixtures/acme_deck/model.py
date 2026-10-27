"""The synthetic acme deck: a package built on the brand, with a kind of its own."""

# The base is generated: installed for the build, embedded in the wheel, so a type checker cannot see it here.
import enum
from typing import Any

import acme_brand_tex  # pyright: ignore[reportMissingImports]
from acme_brand_tex.kinds import expert, vocab  # pyright: ignore[reportMissingImports]
from texmodel.body import Hole
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Choice, Text

pkg = Package(
    "acme-deck",
    prefix="ad",
    version="1.0.0",
    date="2026/10/22",
    description="Decks on the acme brand",
    base=acme_brand_tex.dist.package,
)


@pkg.command
class Heading(Command):
    """A slide heading, set as the brand sets a term."""

    text: Text

    def body(self):
        return vocab.Term.call(Hole("text"), "heading")


@pkg.environment
class Slide(Environment):
    """A slide: headings."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Heading.times.at_least_one()]


# A profile of the brand's `expert` kind (L2): narrower models, written by hand, and an `expand` to the brand's.


@enum.unique
class Tint(Choice):
    """Restrict: the one brand colour a point may take."""

    MOSS = "ab-moss"


class Headline(Command):
    """The brief's headline: the brand's title."""

    text: Text


class Point(Command):
    """A point of the brief: moss unless it is given another colour (default); there is no size to set (lock)."""

    text: Text
    tint: Tint = Tint.MOSS


class Brief(Environment):
    """A headline and up to three points: the brand's deck of one card (compose)."""

    children = [Headline, Point.times(1, 3)]


def expand(brief: Any) -> Any:
    """The brand's deck of one card, under the lock-up (typed loosely: the brand's classes are generated)."""
    headline, *points = brief.content
    return expert.Deck(
        expert.Mark(),
        expert.Card(
            expert.Title(text=headline.text),
            *(expert.Fact(text=p.text, accent=expert.Accent[p.tint.name]) for p in points),
        ),
    )
