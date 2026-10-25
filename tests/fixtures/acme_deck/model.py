"""The synthetic acme deck: a package built on the brand, with a kind of its own."""

# The base is generated: installed for the build, embedded in the wheel, so a type checker cannot see it here.
import acme_brand_tex  # pyright: ignore[reportMissingImports]
from acme_brand_tex.kinds import vocab  # pyright: ignore[reportMissingImports]
from texmodel.body import Hole
from texmodel.components import Command, Environment
from texmodel.package import Package
from texmodel.types import Text

pkg = Package("acme-deck", prefix="ad", version="1.0.0", date="2026/10/22", description="Decks on the acme brand")
pkg.require(acme_brand_tex.dist.package)


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
