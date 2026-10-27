"""The declaration is checked when it is built (P25, K1, K2, K6, P20, P21)."""

import dataclasses
import pathlib
import sys
import zipfile

import pytest
from acme_brand import Card, Compact, Deck, Fact, FactGap, Glossary, Ink, Mark, Term, Title, dist, expert_example
from texmodel.components import Command, Environment, Passthrough, Value
from texmodel.package import Package
from texmodel.preamble import PdfInfo
from texmodel.types import Length, Raw, Text

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
    return Page(Label(text="a"))


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
    assert (
        code_of(Kind, "expert", Deck, (), lambda: Card(Title(text="x"), Fact(text="y"))) == "TP-K001"
    )  # another model
    assert code_of(Kind, "expert", Deck, (), lambda: Deck(Mark())) == "TP-K001"  # breaks the grammar


@pytest.mark.parametrize("name", ["Expert", "1x", "a-b", "", "class"])
def test_a_kind_is_named_as_a_module(name):
    assert code_of(Kind, name, Glossary, (), lambda: Glossary(Term(word="a", meaning="b"))) == "TP-K005"


def test_variant_names_are_file_name_parts_and_unique():
    assert code_of(Variant, "Fronts") == "TP-K005"
    twice = (Variant("a"), Variant("a"))
    assert (
        code_of(Kind, "vocab", Glossary, (), lambda: Glossary(Term(word="a", meaning="b")), variants=twice) == "TP-K002"
    )


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
    if base := changes.get("base"):
        fields["package"] = Package("hole-derived", prefix="hd", base=base.package)
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


def test_a_package_derives_from_the_package_of_its_distributions_base():
    derived = Package("derived", prefix="dr", base=dist.package)
    assert code_of(distribution, base=dist, package=pkg) == "TP-K019"  # the package does not derive from the base's
    assert code_of(distribution, package=derived) == "TP-K019"  # the distribution has no base
    assert distribution(base=dist, package=derived).package.base is dist.package


def test_a_settable_value_may_be_the_bases():
    derived = Package("derived", prefix="dr", base=dist.package)
    profile = Kind("short", Deck, (), expert_example, settable=(Ink,))
    assert distribution(base=dist, package=derived, kinds=(profile,)).kind("short").settable == (Ink,)
    assert code_of(distribution, package=pkg, kinds=(profile,)) == "TP-K018"  # a package without that base


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


def test_a_distribution_declared_in_a_zipped_package_checks_its_root_through_the_package(tmp_path, monkeypatch):
    source = (
        "from texmodel.package import Package\n"
        "from texpkg import Distribution\n"
        "pkg = Package('x-tex', prefix='x', version='1.0.0', date='2026/10/22', description='d')\n"
        "dist = Distribution(name='x-tex', module='x_tex', package=pkg, root='data')\n"
    )
    with zipfile.ZipFile(tmp_path / "zpkg.zip", "w") as z:
        z.writestr("zpkg/__init__.py", source)
        z.writestr("zpkg/data/note.txt", "x")
    monkeypatch.syspath_prepend(str(tmp_path / "zpkg.zip"))
    try:
        import zpkg  # noqa: PLC0415  # pyright: ignore[reportMissingImports]

        assert zpkg.dist.root == "data" and zpkg.dist.files.joinpath("note.txt").read_text() == "x"
    finally:
        sys.modules.pop("zpkg", None)


# -- what a kind lets a document carry (D10) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"options": ("a4paper", "a4paper")}, "TP-K002"),
        ({"settable": (Ink, Ink)}, "TP-K002"),
        ({"preamble": (PdfInfo, PdfInfo)}, "TP-K002"),
        ({"options": ("two words",)}, "TP-K016"),
        ({"options": ("!",)}, "TP-K016"),
        ({"settable": (FactGap,)}, "TP-K017"),  # a preset of the kind
        ({"settable": (Compact,)}, "TP-K017"),  # a variant's setting
    ],
)
def test_what_a_kind_lets_a_document_carry_is_checked(changes, code):
    assert code_of(dataclasses.replace, dist.kind("expert"), **changes) == code


def test_a_settable_value_is_registered_by_the_package_that_reads_it_back():
    other = Package("other", prefix="ot", version="1.0.0", date="2026/10/22", description="Another")

    @other.value
    class Gap(Value[Length]):
        """A gap."""

        default = Length("1mm")

    kind = dataclasses.replace(dist.kind("expert"), settable=(Gap,))
    assert code_of(dataclasses.replace, dist, kinds=(kind, *dist.kinds[1:])) == "TP-K018"
