"""The synthetic acme deck as a texpkg declaration: a kind of its own, and the brand's `vocab` kind exposed."""

import pathlib

# The base is generated: see model.py. Its values are reached through its declaration (a package's values are not
# exported by its kinds).
import acme_brand_tex  # pyright: ignore[reportMissingImports]
from acme_brand_tex._declaration.model import FactGap, Ink  # pyright: ignore[reportMissingImports]
from texmodel.types import Length

from texpkg import Asset, Distribution, Kind, Role

from .model import Brief, Heading, Headline, Point, Slide, Tint, expand, pkg


def brief_example() -> Brief:
    return Brief(Headline(text="Why moss"), Point(text="It is calm"), Point(text="It prints well", tint=Tint.MOSS))


def slide_example() -> Slide:
    return Slide(Heading(text="Hello"), Heading(text="World"))


dist = Distribution(
    name="acme-deck-tex",
    module="acme_deck_tex",
    package=pkg,
    assets=(Asset("assets/DECK.txt", Role.NOTE, "what the deck package is"),),
    kinds=(
        Kind("slide", Slide, presets=(), example=slide_example),
        Kind(
            "brief",
            Brief,
            presets=(FactGap(Length("4mm")),),  # lock: a brief cannot set the gap, and is always written with this
            example=brief_example,
            expand=expand,
            over="expert",
            settable=(Ink,),  # the base's own value
        ),
    ),
    base=acme_brand_tex.dist,
    expose=("vocab",),
)

__all__ = ["Heading", "Slide", "dist", "slide_example"]
