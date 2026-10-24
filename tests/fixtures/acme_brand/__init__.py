"""The synthetic acme brand as a texpkg declaration: a base with two kinds and an asset for each role."""

import pathlib

from texmodel.types import CMYK, Length

from texpkg import Asset, Distribution, Kind, Project, Role, Variant

from .model import Accent, Card, Compact, Deck, Fact, FactGap, Glossary, Ink, Mark, Term, Title, pkg


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

__all__ = ["Accent", "Card", "Compact", "Deck", "Fact", "FactGap", "Glossary", "Ink", "Mark", "Term", "Title", "dist"]
