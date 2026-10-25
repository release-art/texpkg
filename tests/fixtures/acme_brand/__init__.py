"""The synthetic acme brand as a texpkg declaration: a base with two kinds and an asset for each role."""

import dataclasses
import pathlib

from texmodel.types import CMYK, Length

from texpkg import Asset, Distribution, Flat, Kind, Project, Role, Variant

from .model import Accent, Card, Compact, Deck, Fact, FactGap, Glossary, Ink, Mark, Term, Title, design, pkg


def expert_example() -> Deck:
    return Deck(
        Mark(),
        Card(Title("Fox"), Fact("Sly & quick"), Fact("50% of $5", accent=Accent.MOSS)),
        Card(Title("Owl"), Fact("Sees in the dark")),
    )


def vocab_example() -> Glossary:
    return Glossary(Term("fox", "a sly mammal"), Term("owl", "a night bird"))


dist = Distribution(
    name="acme-brand-tex",
    module="acme_brand_tex",
    package=pkg,
    declared_in=__name__,
    design=design,
    assets=(
        Asset("assets/lmroman10-regular.otf", Role.FONT, "the brand typeface"),
        Asset("assets/lockup.pdf", Role.GRAPHIC, "the brand lock-up", kinds=("expert",)),
        Asset("assets/NOTICE.txt", Role.NOTE, "the typeface's licence"),
    ),
    kinds=(
        Kind(
            "expert",
            Deck,
            presets=(FactGap(Length("3mm")),),
            example=expert_example,
            variants=(Variant("compact", (Compact(True),)), Variant("wide", (FactGap(Length("6mm")),))),
        ),
        Kind("vocab", Glossary, presets=(Ink(CMYK(0, 0, 0, 0.8)),), example=vocab_example),
    ),
    layout=Project(pathlib.PurePosixPath("res/acme")),
)

# The same declaration, changed as a later release would: for the tests that load a document with another one.
flat = dataclasses.replace(dist, layout=Flat())
changed = dataclasses.replace(
    dist,
    kinds=(dataclasses.replace(dist.kinds[0], presets=(FactGap(Length("4mm")),)), dist.kinds[1]),
)
broken = dataclasses.replace(
    dist, assets=(*dist.assets, Asset("assets/gone.pdf", Role.GRAPHIC, "a file nobody shipped"))
)

clash = dataclasses.replace(dist, assets=(*dist.assets, Asset("other/lockup.pdf", Role.GRAPHIC, "another lock-up")))

clash = dataclasses.replace(dist, assets=(*dist.assets, Asset("other/lockup.pdf", Role.GRAPHIC, "another lock-up")))

__all__ = [
    "Accent",
    "Card",
    "Compact",
    "Deck",
    "Fact",
    "FactGap",
    "Glossary",
    "Ink",
    "Mark",
    "Term",
    "Title",
    "broken",
    "changed",
    "clash",
    "dist",
    "expert_example",
    "flat",
    "vocab_example",
]
