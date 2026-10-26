"""The declaration is checked when it is built (phase 2: P25, K1, K2, K6, P20, P21)."""

import dataclasses
import pathlib

import pytest
from acme_brand import Card, Compact, Deck, Fact, FactGap, Glossary, Mark, Term, Title, dist, expert_example
from texmodel.components import Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.types import Raw, Text

from texpkg import Asset, DefaultChange, Distribution, Kind, Migrated, Role, Variant, migration
from texpkg.declaration import raw_holes, reachable
from texpkg.errors import DeclarationError

pkg = Package("hole", prefix="ho")


@pkg.command
class Free(Command):
    """TeX written as it is."""

    tex: Raw

    body = r"#tex"


@pkg.command
class Label(Command):
    """A label."""

    text: Text
    marks: tuple[Raw, ...] = ()

    body = r"#marks #text"


@pkg.environment
class Page(Environment):
    """A page."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Label, Free.times.any(), Passthrough.times.any()]


def page() -> Page:
    return Page(Label("a"))


HERE = pathlib.Path(__file__).parent


def code_of(call, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
    with pytest.raises(DeclarationError) as raised:
        call(*args, **kwargs)
    return raised.value.code


def test_the_holes_of_a_kind_are_its_raw_fields_and_passthroughs():
    assert reachable(Page) == (Page, Label, Free)
    assert raw_holes(Page) == ("Page.Passthrough", "Label.marks", "Free.tex")
    assert raw_holes(Deck) == ()


def test_a_raw_hole_is_refused_unless_the_kind_names_it():
    assert code_of(Kind, "page", Page, (), page) == "TP-K003"
    holes = ("Page.Passthrough", "Label.marks", "Free.tex")
    assert Kind("page", Page, (), page, allow_raw=holes).allow_raw == holes


def test_allow_raw_must_name_a_real_hole():
    assert code_of(Kind, "expert", Deck, (), expert_example, allow_raw=("Deck.nothing",)) == "TP-K003"


def test_the_example_must_be_a_valid_tree_of_the_model():
    assert code_of(Kind, "expert", Deck, (), lambda: Card(Title("x"), Fact("y"))) == "TP-K001"  # another model
    assert code_of(Kind, "expert", Deck, (), lambda: Deck(Mark())) == "TP-K001"  # breaks the grammar


@pytest.mark.parametrize("name", ["Expert", "1x", "a-b", "", "class"])
def test_a_kind_is_named_as_a_module(name):
    assert code_of(Kind, name, Glossary, (), lambda: Glossary(Term("a", "b"))) == "TP-K005"


def test_variant_names_are_file_name_parts_and_unique():
    assert code_of(Variant, "Fronts") == "TP-K005"
    twice = (Variant("a"), Variant("a"))
    assert code_of(Kind, "vocab", Glossary, (), lambda: Glossary(Term("a", "b")), variants=twice) == "TP-K002"


def test_a_kind_writes_its_presets_and_then_its_variant():
    expert = dist.kind("expert")
    assert expert.settings() == expert.presets
    assert [type(v) for v in expert.settings("compact")] == [FactGap, Compact]
    assert code_of(expert.settings, "missing") == "TP-K004"
    assert code_of(dist.kind, "missing") == "TP-K004"


def distribution(**changes):  # noqa: ANN003, ANN201
    fields = {
        "name": "x-tex",
        "module": "x_tex",
        "package": pkg,
    }
    return Distribution(**fields | changes)


def test_a_distribution_is_checked():
    assert code_of(distribution, name="X") == "TP-K006"
    assert code_of(distribution, module="not-a-module") == "TP-K006"
    assert code_of(distribution, module="class") == "TP-K006"
    kind = Kind("page", Page, (), page, allow_raw=("Page.Passthrough", "Label.marks", "Free.tex"))
    assert code_of(distribution, kinds=(kind, kind)) == "TP-K002"
    assert code_of(distribution, assets=(Asset("a", Role.NOTE, "x", ("nope",)),), kinds=(kind,)) == "TP-K002"


def test_a_base_kind_is_exposed_by_name_and_only_if_it_exists_and_is_not_redeclared():
    own = Kind("expert", Deck, (), expert_example)
    assert code_of(distribution, expose=("expert",)) == "TP-K007"  # no base
    assert code_of(distribution, base=dist, expose=("nope",)) == "TP-K007"
    assert code_of(distribution, base=dist, kinds=(own,), expose=("expert",)) == "TP-K007"
    assert distribution(base=dist, expose=("vocab",)).expose == ("vocab",)


def test_a_distribution_lists_its_chain_assets_and_sty():
    top = distribution(base=dist)
    assert [d.name for d in top.chain()] == ["x-tex", "acme-brand-tex"]
    assert [r.asset.path for r in top.resolved_assets()] == [a.path for a in dist.assets]
    assert all(r.source.is_file() for r in dist.resolved_assets())
    assert dist.files.joinpath("assets").is_dir()


def test_the_migration_api_is_one_decorator_over_plain_data():
    @migration(to=5)
    def to_five(state):  # noqa: ANN001, ANN202
        return Migrated({**state, "five": True})

    assert to_five.to == 5 and to_five({"a": 1}).state == {"a": 1, "five": True}
    assert code_of(migration(to=1), lambda state: Migrated(state)) == "TP-M001"
    assert [m.value for m in DefaultChange] == ["follow", "freeze", "ask"]
    assert DefaultChange.FOLLOW == "follow"


def test_the_declaring_package_is_read_from_the_call_and_root_is_a_path_inside_it():
    assert dist.declared_in == "acme_brand" and dist.root == "."
    assert dataclasses.replace(dist, name="other-tex").declared_in == "acme_brand"
    assert distribution(root="fixtures/acme_brand").root == "fixtures/acme_brand"
    assert distribution(root=str(HERE / "fixtures" / "acme_brand")).root == "fixtures/acme_brand"


@pytest.mark.parametrize("root", ["..", "../other", "/elsewhere"])
def test_a_root_outside_the_declaring_package_is_refused(root):
    assert code_of(distribution, root=root) == "TP-K013"


def test_a_root_that_leaves_the_package_through_a_symlink_or_is_missing_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = HERE / "_link_out"
    link.symlink_to(outside)
    try:
        assert code_of(distribution, root="_link_out") == "TP-K013"
    finally:
        link.unlink()
    assert code_of(distribution, root="no-such-directory") == "TP-K014"
    assert code_of(distribution, root="test_declaration.py") == "TP-K014"


def test_the_tex_file_name_is_the_root_class_lower_cased_unless_the_kind_names_it():
    expert = dist.kind("expert")
    assert expert.stem == "deck" and expert.documents()[:2] == ((None, "deck.tex"), ("compact", "deck-compact.tex"))
    named = dataclasses.replace(expert, stem="brand-deck")
    assert named.documents()[:2] == ((None, "brand-deck.tex"), ("compact", "brand-deck-compact.tex"))
    assert code_of(dataclasses.replace, expert, stem="a/b") == "TP-K015"
    assert code_of(dataclasses.replace, expert, stem="deck.tex") == "TP-K015"


def test_a_distribution_built_outside_a_package_is_refused():
    namespace = {"__name__": "script", "Distribution": Distribution, "pkg": pkg, "__file__": __file__}
    with pytest.raises(DeclarationError) as raised:
        exec('Distribution(name="x-tex", module="x_tex", package=pkg)', namespace)  # noqa: S102
    assert raised.value.code == "TP-K012"


def test_assets_are_read_from_the_root():
    moved = distribution(root="fixtures/acme_brand/assets")
    assert moved.files.joinpath("lockup.pdf").is_file()
