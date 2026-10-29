"""The module a build generates, through its whole surface (P6, P24, P26, K3, K6, V26, B11)."""

import pathlib
import sys
from types import ModuleType
from typing import Annotated

import pytest

from texpkg._internal import state
from texpkg.contracts import Changes, Contracts, Pair, Triple
from texpkg.errors import DeclarationError
from texpkg.protocol import KindModule, KindsModule, PackageModule
from texpkg_build._internal import generate
from texpkg_build.testing import load_declaration

from .helpers import FIXTURES, golden

GENERATED = FIXTURES / "acme_brand" / "generated"


def test_the_module_has_the_fixed_surface(acme_brand_tex: ModuleType, expert, vocab):
    assert isinstance(acme_brand_tex, PackageModule) and isinstance(acme_brand_tex.kinds, KindsModule)
    assert acme_brand_tex.__version__ == "1.2.0"
    assert acme_brand_tex.CONTRACTS == Contracts(Triple(1, 0, 0), Triple(1, 0, 0), Pair(1, 0))
    assert acme_brand_tex.kinds.names() == ("expert", "vocab")
    assert {n: isinstance(m, KindModule) for n, m in acme_brand_tex.kinds.modules().items()} == {
        "expert": True,
        "vocab": True,
    }


def test_a_kind_module_exports_its_classes_and_value_types_never_the_packages_other_components(
    acme_brand_tex, expert, vocab
):
    assert [
        n for n in ("Deck", "Mark", "Card", "Title", "Fact", "Accent", "Glossary", "Term") if hasattr(expert, n)
    ] == [
        "Deck",
        "Mark",
        "Card",
        "Title",
        "Fact",
        "Accent",
    ]
    assert [n for n in ("Deck", "Glossary", "Term", "Accent") if hasattr(vocab, n)] == ["Glossary", "Term"]
    assert not hasattr(expert, "FactGap") and not hasattr(acme_brand_tex, "Deck")
    assert expert.NAME == "expert" and vocab.NAME == "vocab"


def test_the_two_schemas_of_a_kind(acme_brand_tex, expert):
    accepted, stored = expert.schema(), expert.schema(mode="serialization")
    assert (
        accepted == expert.schema("validation")
        and accepted["title"] == "expert"
        and accepted["properties"]["tree"] == {"$ref": "#/$defs/Deck"}
    )
    fact_in, fact_out = accepted["$defs"]["Fact"], stored["$defs"]["Fact"]
    assert fact_in["required"] == ["text"] and "$defaults" not in fact_in["properties"]
    assert fact_out["required"] == ["accent", "text", "type"]
    assert fact_out["properties"]["$defaults"]["items"] == {"enum": ["accent"]}
    assert stored["$defs"]["Title"]["properties"]["$defaults"] == {"type": "array", "maxItems": 0}
    with pytest.raises(DeclarationError) as raised:
        expert.schema("nonsense")  # type: ignore[arg-type]
    assert raised.value.code == "TP-K008"


def test_an_example_is_a_valid_tree_and_a_kind_lists_its_variants_and_changes(acme_brand_tex, expert, vocab):
    assert expert.example().violations() == [] and vocab.example().violations() == []
    assert expert.example() is not expert.example()
    assert expert.variants() == ("compact", "wide") and vocab.variants() == ()
    assert expert.changes(1, 1) == Changes()


CASES = [("expert", None, "deck"), ("expert", "compact", "deck-compact"), ("expert", "wide", "deck-wide"),
         ("vocab", None, "glossary")]  # fmt: skip


@pytest.mark.parametrize(("kind", "variant", "name"), CASES)
def test_a_kind_renders_to_its_golden(acme_brand_tex, tmp_path, kind, variant, name):
    module = acme_brand_tex.kinds.modules()[kind]
    document = module.create(tmp_path, module.example())
    assert document.kind == kind and document.path == tmp_path
    golden(GENERATED / f"{name}.tex", document.render(variant))


def test_the_sty_files_are_golden(acme_brand_tex):
    for name, text in acme_brand_tex._bound.RELEASE.sty.items():
        golden(GENERATED / name, text)


def test_a_document_renders_with_the_variants_settings_after_the_presets(acme_brand_tex, tmp_path, expert):
    document = expert.create(tmp_path, expert.example())
    plain, wide = (document.render(v) for v in (None, "wide"))
    assert "\\setlength{\\abFactGap}{3mm}\n" in plain and "{6mm}" not in plain
    assert plain.index("{3mm}") < wide.index("{6mm}") and "\\setlength{\\abFactGap}{3mm}\n" in wide


def test_a_document_refuses_an_unknown_variant_and_reports_every_violation_at_once(acme_brand_tex, tmp_path, expert):
    document = expert.create(tmp_path, expert.example())
    with pytest.raises(DeclarationError) as raised:
        document.render("nope")
    assert raised.value.code == "TP-K004"
    broken = document.replace(expert.Deck(expert.Card(expert.Title(text="x"))))
    with pytest.raises(ExceptionGroup) as grouped:
        broken.render()
    assert len(grouped.value.exceptions) >= 2  # no Mark, no Fact


def test_replace_gives_another_document_in_the_same_directory(acme_brand_tex, tmp_path, expert):
    document = expert.create(tmp_path, expert.example())
    other = document.replace(expert.Deck(expert.Mark(), expert.Card(expert.Title(text="Owl"), expert.Fact(text="x"))))
    assert other.path == document.path and other.tree is not document.tree and "Owl" in other.render()


def test_a_kind_module_checks_it_was_generated_for_the_declaration(acme_brand_tex, expert, vocab):
    with pytest.raises(DeclarationError) as raised:
        acme_brand_tex._bound.RELEASE.kind("expert", vocab.Glossary)
    assert raised.value.code == "TP-B001"


def test_a_pointer_must_name_a_distribution():
    with pytest.raises(DeclarationError) as raised:
        load_declaration("acme_brand:Deck")
    assert raised.value.code == "TP-B003"


def test_a_class_outside_the_declaration_package_cannot_be_exported():
    with pytest.raises(DeclarationError) as raised:
        generate._import_from(__import__("acme_brand").dist, pathlib.Path)
    assert raised.value.code == "TP-B002"


def test_loading_again_replaces_the_module(acme_brand_tex):
    again = load_declaration("acme_brand:dist", version="2.0.0")
    assert again is not acme_brand_tex and again.__version__ == "2.0.0"
    assert sys.modules["acme_brand_tex"] is again


def test_a_nested_class_cannot_be_exported():
    class Outer:
        class Inner:
            pass

    Outer.Inner.__module__ = "acme_brand.model"
    with pytest.raises(DeclarationError) as raised:
        generate._import_from(__import__("acme_brand").dist, Outer.Inner)
    assert raised.value.code == "TP-B002"


def test_the_value_types_of_a_field_are_found_through_its_annotation():
    from acme_brand import Accent

    hints = [list[Accent], Accent | None, Annotated[Accent, "mark"], tuple[Accent, ...], str, int | None]
    assert [list(generate._types(h)) for h in hints] == [[Accent]] * 4 + [[], []]


def test_the_stored_schema_leaves_what_has_no_properties_alone():
    validation = {"properties": {"a": {"default": 1}}, "$defs": {"Colour": {"enum": ["a"]}}}
    assert state.stored(validation)["$defs"] == {"Colour": {"enum": ["a"]}}
    assert validation["properties"] == {"a": {"default": 1}}  # the input is not changed
