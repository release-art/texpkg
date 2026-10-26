"""What a document carries besides its tree: settings, options and preamble entries its kind allows (D10)."""

import json
import sys

import pytest
from acme_brand import Compact, FactGap, Ink
from jsonschema import Draft202012Validator
from texmodel.preamble import InputPath, PdfInfo, PreambleSlots, RequireMetadata
from texmodel.types import CMYK, Length

from texpkg import Migrated, migration
from texpkg._internal import classify, state
from texpkg._internal.classify import Level
from texpkg.contracts import Contracts, Triple
from texpkg.errors import MigrationError, NotAllowedError
from texpkg_build.testing import load_declaration

GREY = Ink(CMYK(0, 0, 0, 0.5))
SLOTS = PreambleSlots(before_class=(RequireMetadata(pdfversion="2.0"),), after_package=(PdfInfo(Title="Rex"),))


@pytest.fixture
def expert(acme_brand_tex):
    return acme_brand_tex.kinds.modules()["expert"]


@pytest.fixture
def doc(expert, tmp_path):
    return expert.create(tmp_path / "doc", expert.example(), settings=[GREY], options=["a4paper"], preamble=SLOTS)


def test_a_document_carries_the_settings_options_and_preamble_its_kind_allows(doc):
    assert (doc.settings, doc.options, doc.preamble) == ((GREY,), ("a4paper",), SLOTS)
    text = doc.render()
    lines = text.splitlines()
    assert lines[1] == "\\DocumentMetadata{pdfversion=2.0}" and lines[2] == "\\documentclass[a4paper]{article}"
    assert lines.index("\\setlength{\\abFactGap}{3mm}") < lines.index(
        "\\definecolor{ab-ink}{cmyk}{0,0,0,0.5}"
    )  # presets first
    assert lines.index("\\graphicspath{{}{res/texpkg/}}") < lines.index(
        r"\csname pdfmanagement_add:nnn\endcsname{Info}{Title}{(\detokenize{Rex})}"
    )


def test_they_are_stored_beside_the_tree_in_texmodels_shapes_and_come_back(doc, expert):
    doc.save()
    envelope = json.loads((doc.path / "_texpkg/state.json").read_text())
    assert list(envelope) == ["package", "kind", "data", "tree", "settings", "options", "preamble"]
    assert envelope["settings"] == [{"type": "Ink", "value": {"c": 0.0, "m": 0.0, "y": 0.0, "k": 0.5}}]
    assert envelope["options"] == ["a4paper"]
    assert envelope["preamble"]["after_package"] == [{"type": "PdfInfo", "entries": {"Title": "Rex"}}]
    again = expert.load(doc.path)
    assert again.options == doc.options and again.preamble == doc.preamble
    assert [type(v) for v in again.settings] == [Ink] and again.settings[0].value == GREY.value
    assert again.render() == doc.render() and again.check().current


def test_a_document_with_none_stores_none(expert, tmp_path):
    plain = expert.create(tmp_path / "plain", expert.example())
    assert list(json.loads((plain.path / "_texpkg/state.json").read_text())) == ["package", "kind", "data", "tree"]
    assert (plain.settings, plain.options, plain.preamble) == ((), (), PreambleSlots())


def test_replace_changes_what_is_given_and_keeps_the_rest(doc):
    other = doc.replace(options=["landscape"])
    assert other.options == ("landscape",) and other.settings == doc.settings and other.preamble == doc.preamble
    assert doc.replace(settings=[]).settings == () and doc.replace(preamble=PreambleSlots()).preamble == PreambleSlots()
    assert doc.replace().render() == doc.render()


@pytest.mark.parametrize(
    ("given", "path"),
    [
        ({"settings": [Compact(True)]}, "/settings/0"),
        ({"settings": [GREY, FactGap(Length("1mm"))]}, "/settings/1"),
        ({"options": ["a4paper", "twocolumn"]}, "/options/1"),
        ({"preamble": PreambleSlots(before_package=(InputPath("x/"),))}, "/preamble/before_package/0"),
    ],
)
def test_what_the_kind_does_not_allow_is_refused_whole(expert, doc, tmp_path, given, path):
    with pytest.raises(NotAllowedError) as raised:
        expert.create(tmp_path / "other", expert.example(), **given)
    assert (
        raised.value.code == "TP-D007"
        and raised.value.items[0]["path"] == path
        and isinstance(raised.value, ValueError)
    )
    assert not (tmp_path / "other").exists()
    with pytest.raises(NotAllowedError):
        doc.replace(**given)


def test_a_kind_that_allows_nothing_takes_nothing(acme_brand_tex, tmp_path):
    vocab = acme_brand_tex.kinds.modules()["vocab"]
    with pytest.raises(NotAllowedError):
        vocab.create(tmp_path / "v", vocab.example(), options=["a4paper"])


def test_a_hand_edit_of_a_line_the_document_wrote_is_found_at_its_data_path(doc):
    doc.save()
    tex = doc.path / "deck.tex"
    text = tex.read_text()
    text = text.replace("\\definecolor{ab-ink}{cmyk}{0,0,0,0.5}", "\\definecolor{ab-ink}{cmyk}{0,0,0,0.9}")
    text = text.replace("{Title}{(\\detokenize{Rex})}", "{Title}{(\\detokenize{Fox})}")
    text = text.replace("\\setlength{\\abFactGap}{3mm}", "\\setlength{\\abFactGap}{9mm}")
    text = text.replace("\\documentclass[a4paper]", "\\documentclass[a5paper]")
    tex.write_text(text)
    paths = {e.path for e in doc.hand_edits()}
    assert {"/settings/0", "/preamble/after_package/0"} <= paths  # the document's own lines
    assert "settings[0]" in paths and not any(p.startswith("/settings/") and p != "/settings/0" for p in paths)
    assert "header" in paths or any("documentclass" in e.found for e in doc.hand_edits())  # the class line


def test_the_stored_schema_describes_what_the_kind_allows(expert, acme_brand_tex):
    stored = expert.schema("serialization")
    assert set(stored["properties"]) == {"tree", "settings", "options", "preamble"} and stored["required"] == ["tree"]
    assert stored["properties"]["options"]["items"] == {"enum": ["a4paper", "landscape"]}
    assert [r["$ref"] for r in stored["properties"]["settings"]["items"]["oneOf"]] == ["#/$defs/InkSetting"]
    slot = stored["properties"]["preamble"]["properties"]["after_package"]["items"]["oneOf"]
    assert [r["$ref"] for r in slot] == ["#/$defs/RequireMetadataEntry", "#/$defs/PdfInfoEntry"]
    assert {"InkSetting", "PdfInfoEntry", "RequireMetadataEntry", "Deck"} <= set(stored["$defs"])
    assert "FactGapSetting" not in stored["$defs"]  # only what the kind allows, with what those name
    plain = acme_brand_tex.kinds.modules()["vocab"].schema()
    assert set(plain["properties"]) == {"tree"}
    validator = Draft202012Validator(stored)
    data = json.loads(
        json.dumps({"tree": state.tree_state(expert.example()), **state.extras_state(state.Extras((), (GREY,)))})
    )
    assert list(validator.iter_errors(data)) == []
    assert list(validator.iter_errors({**data, "settings": [{"type": "Compact", "value": True}]}))


def test_allowing_more_is_compatible_and_allowing_less_is_breaking(expert, acme_brand_tex):
    new = expert.schema()
    for change in ("options", "settings", "preamble"):
        old = json.loads(json.dumps(new))
        del old["properties"][change]
        assert [c.level for c in classify.schema_changes(old, new)] == [Level.COMPATIBLE]
        assert [c.level for c in classify.schema_changes(new, old)] == [Level.BREAKING]
    narrower = json.loads(json.dumps(new))
    narrower["properties"]["options"]["items"]["enum"].remove("landscape")
    narrower["properties"]["preamble"]["properties"]["after_package"]["items"]["oneOf"].pop()
    levels = {(c.where, c.level) for c in classify.schema_changes(new, narrower)}
    assert ("expert.options", Level.BREAKING) in levels
    assert ("expert.preamble.after_package", Level.BREAKING) in levels
    fewer = json.loads(json.dumps(new))
    del fewer["properties"]["preamble"]["properties"]["before_class"]
    assert [(c.where, c.level) for c in classify.schema_changes(new, fewer)] == [
        ("expert.preamble.before_class", Level.BREAKING)
    ]
    assert classify.schema_changes(narrower, new) and all(
        c.level is Level.COMPATIBLE for c in classify.schema_changes(narrower, new)
    )


# -- loading what the kind no longer allows --------------------------------------------------------------------------


def stored_with(doc, **extras):
    path = doc.path / "_texpkg/state.json"
    envelope = json.loads(path.read_text())
    envelope.update(extras)
    path.write_text(json.dumps(envelope))


def test_a_stored_setting_the_kind_no_longer_allows_is_unresolved_and_a_migration_can_remove_it(doc, expert, tmp_path):
    doc.save()
    stored_with(doc, settings=[{"type": "Compact", "value": True}], options=["a4paper", "twocolumn"])
    with pytest.raises(MigrationError) as raised:
        expert.load(doc.path)
    assert {(i.path, i.boundary) for i in raised.value.unresolved} == {
        ("/settings/0", "validation"),
        ("/options/1", "validation"),
    }

    @migration(to=2)
    def drop(state):  # noqa: ANN001, ANN202
        state["$extras"]["settings"] = []
        state["$extras"]["options"] = ["a4paper"]
        return Migrated(state)

    newer = load_declaration("acme_brand:dist", version="1.3.0", contracts=Contracts(data=Triple(2)))
    try:
        moved = newer.kinds.modules()["expert"].load(doc.path, migrations=[drop])
        assert moved.settings == () and moved.options == ("a4paper",)
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
            del sys.modules[name]


def test_stored_extras_texmodel_cannot_read_are_unresolved_with_their_value(doc, expert):
    doc.save()
    stored_with(doc, settings=[{"type": "Nope", "value": 1}, {"type": "Ink"}], options=["!"])
    with pytest.raises(MigrationError) as raised:
        expert.load(doc.path)
    by_path = {i.path: i for i in raised.value.unresolved}
    assert by_path["/settings/1/value"].value is None  # nothing stored there
    assert by_path["/settings/0"].value == {"type": "Nope", "value": 1} and by_path["/options/0"].value == "!"
    assert "Nope" in by_path["/settings/0"].reason


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_a_document_with_settings_options_and_preamble_compiles(doc, compiler, tmp_path):
    doc.save()
    result = compiler.compile(doc.path / "deck.tex", tmp_path / "out")
    result.raise_for_status()
    assert result.pages == 1
