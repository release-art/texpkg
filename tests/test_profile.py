"""Profiles and embedded data (L1-L8)."""

import dataclasses
import json
import sys
from typing import Any

import acme_brand
import pytest
from acme_brand import Ink
from hypothesis import (
    given,
    strategies as st,
)
from texmodel.preamble import PassOption, PreambleSlots, RequireMetadata
from texmodel.types import CMYK

from texpkg import Design, Kind
from texpkg.errors import DeclarationError, MigrationError, NotAllowedError
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
    tokens: Any = design.load(acme_brand.dist.files)
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


def test_a_profile_document_sets_a_value_of_the_base_and_reads_it_back(deck, tmp_path):
    ink = Ink(CMYK(0, 0, 0, 0.5))
    brief = deck.kinds.modules()["brief"]
    doc = brief.create(tmp_path, brief.example(), settings=[ink])
    assert "\\definecolor{ab-ink}{cmyk}{0,0,0,0.5}" in doc.render()
    doc.save()
    again = brief.load(tmp_path)
    assert [type(v) for v in again.settings] == [Ink] and again.render() == doc.render()


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
        lambda text, given: brief.Point(text=text, tint=brief.Tint.MOSS) if given else brief.Point(text=text),
        TEXT,
        st.booleans(),
    )
    return st.builds(
        lambda head, points: brief.Brief(brief.Headline(text=head), *points),
        TEXT,
        st.lists(point, min_size=1, max_size=3),
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
    point = model.Point(text="x")
    check_expansion(wide, "brief")  # the kind's own example is fine
    with pytest.raises(DeclarationError) as raised:
        check_expansion(wide, "brief", [model.Brief(model.Headline(text="h"), point, point, point)])
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
        check_expansion(deck_dist, "brief", [model.Brief(model.Headline(text="x"))])  # no points
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


# -- locked preamble entries (K020) ----------------------------------------------------------------------------------

LOCK = PreambleSlots(before_class=(RequireMetadata(lang="en"),))
BASE_LOCK = PreambleSlots(before_class=(PassOption("graphicx", "draft"),))  # what a base kind locks
OWN = PreambleSlots(before_class=(PassOption("xcolor", "table"),))


def test_a_kind_writes_its_locked_entries_before_the_documents_own(deck, tmp_path):
    slide = deck.kinds.modules()["slide"]
    lines = slide.create(tmp_path, slide.example(), preamble=OWN).render().splitlines()
    wanted = ["\\DocumentMetadata{pdfversion=2.0}", "\\PassOptionsToPackage{table}{xcolor}"]
    at = [lines.index(line) for line in wanted]
    assert at == sorted(at) and at[1] < next(i for i, line in enumerate(lines) if "\\documentclass" in line)


def test_a_document_may_not_carry_an_entry_class_the_kind_locks(deck, tmp_path):
    slide = deck.kinds.modules()["slide"]
    with pytest.raises(NotAllowedError) as raised:
        slide.create(tmp_path, slide.example(), preamble=LOCK)
    (item,) = raised.value.items
    assert item["path"] == "/preamble/before_class/0" and "locked by kind slide" in item["reason"]


def test_locked_entries_are_in_no_documents_data_and_a_stored_one_is_unresolved(deck, tmp_path):
    slide = deck.kinds.modules()["slide"]
    slide.create(tmp_path, slide.example(), preamble=OWN).save()
    path = tmp_path / "_texpkg/state.json"
    stored = json.loads(path.read_text())
    assert [e["type"] for e in stored["preamble"]["before_class"]] == ["PassOption"]  # not the lock
    stored["preamble"]["before_class"].append({"type": "RequireMetadata", "entries": {"lang": "en"}})
    path.write_text(json.dumps(stored))
    with pytest.raises(MigrationError) as raised:
        slide.load(tmp_path)
    assert raised.value.code == "TP-M003" and "locked by kind slide" in str(raised.value)


def test_a_hand_edit_of_the_documents_own_entry_is_found_at_its_data_path(deck, tmp_path):
    slide = deck.kinds.modules()["slide"]
    doc = slide.create(tmp_path, slide.example(), preamble=OWN)
    doc.save()
    tex = tmp_path / "slide.tex"
    tex.write_text(
        tex.read_text().replace("{table}{xcolor}", "{x11names}{xcolor}").replace("pdfversion=2.0", "pdfversion=1.7")
    )
    paths = {e.path for e in doc.hand_edits()}
    assert paths == {"/preamble/before_class/0", "preamble.before_class[0]"}  # the own entry, and the locked line


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_document_with_a_locked_entry_compiles(deck, compiler, tmp_path):
    slide = deck.kinds.modules()["slide"]
    slide.create(tmp_path / "doc", slide.example(), preamble=OWN).save()
    compiler.compile(tmp_path / "doc/slide.tex", tmp_path / "out").raise_for_status()


def locked_deck(deck, **changes):  # noqa: ANN001, ANN003, ANN201
    """The deck declaration over a brand whose `expert` kind locks `LOCK`; `changes` go to its `brief` profile."""
    import acme_deck  # noqa: PLC0415  # importable once the `deck` fixture has built the brand

    expert = dataclasses.replace(acme_brand.dist.kinds[0], locked_preamble=BASE_LOCK)
    base = dataclasses.replace(acme_brand.dist, kinds=(expert, *acme_brand.dist.kinds[1:]))
    brief = dataclasses.replace(acme_deck.dist.kind("brief"), **changes)
    return dataclasses.replace(acme_deck.dist, base=base, kinds=(acme_deck.dist.kinds[0], brief))


def test_a_profile_writes_the_locked_entries_of_its_base_kind(deck):
    wide = locked_deck(deck)
    release = dataclasses.replace(deck._bound.RELEASE, dist=wide)  # noqa: SLF001
    brief = wide.kind("brief")
    text = release.plan(brief, brief.example(), None).text
    assert text.index("\\PassOptionsToPackage{draft}{graphicx}") < text.index("\\documentclass")


def test_a_profile_may_not_lock_or_allow_what_its_base_kind_locks(deck):
    with pytest.raises(DeclarationError) as raised:
        locked_deck(deck, locked_preamble=BASE_LOCK)
    assert raised.value.code == "TP-K020" and "locked by the base kind too" in str(raised.value)
    with pytest.raises(DeclarationError) as raised:
        locked_deck(deck, preamble=(PassOption,))
    assert raised.value.code == "TP-K020" and "locked by the base kind" in str(raised.value)
