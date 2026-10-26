"""Profiles and embedded data (phase 3a: L1-L8)."""

import dataclasses
import json
import sys
from typing import Any

import acme_brand
import pytest
from hypothesis import (
    given,
    strategies as st,
)

from texpkg import Design, Kind
from texpkg.errors import DeclarationError
from texpkg_build._internal import checks
from texpkg_build.testing import check_expansion, load_declaration

from .helpers import FIXTURES, golden

DECK = FIXTURES / "acme_deck"


@pytest.fixture
def deck(acme_brand_tex):
    """The deck package, built in memory on the brand."""
    module = load_declaration("acme_deck:dist", version="2.0.0")
    yield module
    for name in [n for n in sys.modules if n.split(".")[0] in ("acme_deck_tex", "acme_deck")]:
        del sys.modules[name]


def test_the_design_data_is_validated_and_fills_the_sty(acme_brand_tex):
    design = acme_brand.dist.design
    assert design is not None
    tokens: Any = design.load(acme_brand.dist.root)
    assert tokens.palette.slate.tex == "2F3E46"
    assert "\\definecolor{ab-slate}{HTML}{2F3E46}" in acme_brand_tex._bound.RELEASE.sty["acme-brand.sty"]
    checks.design_is_valid(acme_brand.dist)
    checks.design_is_valid(dataclasses.replace(acme_brand.dist, design=None))


@pytest.mark.parametrize("path", ["missing.json", "NOTICE.txt"])
def test_design_data_that_does_not_fit_its_model_fails_the_build(path):
    dist = dataclasses.replace(acme_brand.dist, design=Design(acme_brand.design.model, f"assets/{path}"))
    with pytest.raises(DeclarationError) as raised:
        checks.design_is_valid(dist)
    assert raised.value.code == "TP-B010"


def test_a_profile_kind_is_a_smaller_surface_over_the_base_kind(deck, tmp_path):
    brief = deck.kinds.modules()["brief"]
    assert deck.kinds.names() == ("slide", "brief", "vocab")
    assert [n for n in ("Brief", "Headline", "Point", "Tint", "Deck", "Card") if hasattr(brief, n)] == [
        "Brief",
        "Headline",
        "Point",
        "Tint",
    ]
    assert not hasattr(brief.Point, "size")  # no field: locked
    doc = brief.create(tmp_path, brief.example())
    tex = doc.render()
    golden(DECK / "generated" / "brief.tex", tex)
    assert tex.count("\\abFact[") == 2 and "\\setlength{\\abFactGap}{4mm}" in tex and "\\usepackage{acme-deck}" in tex


def test_a_lock_is_written_into_every_document_after_the_base_kinds_own_presets(deck, tmp_path):
    brief = deck.kinds.modules()["brief"]
    doc = brief.create(tmp_path, brief.example())
    settings = [line for line in doc.render().splitlines() if line.startswith("\\setlength")]
    assert settings == ["\\setlength{\\abFactGap}{3mm}", "\\setlength{\\abFactGap}{4mm}"]
    doc.save()
    template = json.loads((tmp_path / "_texpkg/template.json").read_text())
    assert template["settings"]["brief.tex"] == {"FactGap": "\\setlength{\\abFactGap}{4mm}"}


def test_a_profile_document_saves_with_the_payload_of_the_kind_it_expands_to(deck, tmp_path):
    brief = deck.kinds.modules()["brief"]
    brief.create(tmp_path / "b", brief.example()).save()
    slide = deck.kinds.modules()["slide"]
    slide.create(tmp_path / "s", slide.example()).save()
    assert (tmp_path / "b/res/texpkg/lockup.pdf").is_file()  # the expert kind's lock-up
    assert not (tmp_path / "s/res/texpkg/lockup.pdf").exists()


def test_a_profile_documents_hand_edits_are_found_by_the_plans_path(deck, tmp_path):
    brief = deck.kinds.modules()["brief"]
    doc = brief.create(tmp_path, brief.example())
    doc.save()
    text = (tmp_path / "brief.tex").read_text().replace("\\abTitle{Why moss}", "\\abTitle{Why not moss}")
    (tmp_path / "brief.tex").write_text(text)
    (edit,) = doc.hand_edits()
    assert edit.path == "Deck[0]/Card[1]/Title[0]"  # a node of the expanded tree, not of the brief's data


def test_the_loaded_profile_document_round_trips(deck, tmp_path):
    brief = deck.kinds.modules()["brief"]
    brief.create(tmp_path, brief.example())
    again = brief.load(tmp_path)
    assert (
        again.defaults == ("/content/1/tint",)
        and again.render() == brief.create(tmp_path / "x", brief.example()).render()
    )


# -- the law (L3) ----------------------------------------------------------------------------------------------------

TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=8)


def trees(brief):
    point = st.builds(
        lambda text, given: brief.Point(text, tint=brief.Tint.MOSS) if given else brief.Point(text), TEXT, st.booleans()
    )
    return st.builds(
        lambda head, points: brief.Brief(brief.Headline(head), *points), TEXT, st.lists(point, min_size=1, max_size=3)
    )


def test_every_valid_profile_document_expands_to_a_valid_base_document(deck):
    brief = deck.kinds.modules()["brief"]
    dist = acme_brand.dist.__class__  # noqa: F841
    from acme_deck import dist as deck_dist

    @given(trees(brief))
    def law(tree):
        check_expansion(deck_dist, "brief", [tree])

    law()


def test_a_profile_that_widens_its_base_fails_the_law(deck):
    from acme_deck import (
        dist as deck_dist,
        model,
    )

    def widening(brief):
        deck_tree = model.expand(brief)
        card = deck_tree.content[1]
        if len(brief.content) == 4:  # a brief of three points: the example has two, so the example passes
            return type(deck_tree)(deck_tree.content[0], type(card)(*card.content, *card.content[1:]))
        return deck_tree

    wide = dataclasses.replace(
        deck_dist, kinds=(deck_dist.kinds[0], dataclasses.replace(deck_dist.kinds[1], expand=widening))
    )
    point = model.Point("x")
    check_expansion(wide, "brief")  # the kind's own example is fine
    with pytest.raises(DeclarationError) as raised:
        check_expansion(wide, "brief", [model.Brief(model.Headline("h"), point, point, point)])
    assert (
        raised.value.code == "TP-K010"
        and "widens" not in str(raised.value)
        and "expands to a tree" in str(raised.value)
    )
    with pytest.raises(DeclarationError) as raised:
        check_expansion(deck_dist, "slide")
    assert raised.value.code == "TP-K009"
    assert deck_dist.expansion_problem(deck_dist.kinds[0], deck_dist.kinds[0].example()) == "is not a profile kind"


def test_a_tree_that_is_not_valid_is_not_a_counterexample(deck):
    from acme_deck import (
        dist as deck_dist,
        model,
    )

    with pytest.raises(DeclarationError) as raised:
        check_expansion(deck_dist, "brief", [model.Brief(model.Headline("x"))])  # no points
    assert raised.value.code == "TP-K010" and "Point" in str(raised.value)


def test_a_profile_kind_is_declared_whole(deck):
    from acme_deck import dist as deck_dist
    from acme_deck.model import Brief, expand

    brief = deck_dist.kinds[1]
    with pytest.raises(DeclarationError) as raised:
        Kind("brief", Brief, (), brief.example, expand=expand)
    assert raised.value.code == "TP-K009"
    for changes, code in (
        ({"over": "nothing"}, "TP-K009"),
        ({"expand": lambda b: acme_brand.Deck(acme_brand.Mark())}, "TP-K010"),
        ({"expand": lambda b: b}, "TP-K010"),
        ({"expand": lambda b: b.nothing}, "TP-K010"),
    ):
        with pytest.raises(DeclarationError) as raised:
            dataclasses.replace(deck_dist, kinds=(dataclasses.replace(brief, **changes),))
        assert raised.value.code == code
