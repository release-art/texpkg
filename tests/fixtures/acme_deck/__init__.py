"""The synthetic acme deck as a texpkg declaration: a kind of its own, and the brand's `vocab` kind exposed."""

import pathlib

import acme_brand_tex  # pyright: ignore[reportMissingImports]  # generated: see model.py

from texpkg import Asset, Distribution, Kind, Project, Role

from .model import Heading, Slide, pkg


def slide_example() -> Slide:
    return Slide(Heading("Hello"), Heading("World"))


dist = Distribution(
    name="acme-deck-tex",
    module="acme_deck_tex",
    package=pkg,
    declared_in=__name__,
    assets=(Asset("assets/DECK.txt", Role.NOTE, "what the deck package is"),),
    kinds=(Kind("slide", Slide, presets=(), example=slide_example),),
    base=acme_brand_tex.dist,
    expose=("vocab",),
    layout=Project(pathlib.PurePosixPath("res/acme")),
)

__all__ = ["Heading", "Slide", "dist", "slide_example"]
