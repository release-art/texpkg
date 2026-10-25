"""Migrations (phase 5a: V5-V9, V14-V16, V22, V23, V28-V32)."""

import json
import pathlib
import sys

import pytest
from acme_sheet import dist as sheet_dist  # noqa: F401

from texpkg import DefaultChange, Migrated, Unresolved, migration
from texpkg._internal import history
from texpkg.contracts import Contracts, Triple
from texpkg.errors import MigrationError
from texpkg_build.testing import load_declaration

from .test_document import mtimes


@pytest.fixture
def sheet(tmp_path):
    """The datasheet package at `data` 5, and a directory written by release 4."""
    module = load_declaration("acme_sheet:dist", version="5.0.0", contracts=Contracts(data=Triple(5)))
    yield module.kinds.modules()["datasheet"]
    for name in [n for n in sys.modules if n.split(".")[0] in ("acme_sheet_tex",)]:
        del sys.modules[name]


def release_4(root: pathlib.Path, *standards: str, data: int = 4) -> pathlib.Path:
    rows = [{"type": "Row", "standard": s} for s in standards]
    tree = {"type": "Sheet", "content": [{"type": "Heading", "text": "Pump"}, *rows]}
    (root / "_texpkg").mkdir(parents=True)
    envelope = {"package": "acme-sheet-tex", "kind": "datasheet", "data": data, "tree": tree}
    (root / "_texpkg/state.json").write_text(json.dumps(envelope))
    return root


@migration(to=5)
def place_unknown_standards(state):  # noqa: ANN001, ANN201
    """The consumer knows what its own rows meant: an old ISO number is the 14001 tick."""
    ticks = state["content"][-1]
    placed = []
    for item in state.pop("$unresolved"):
        if item["value"] == "ISO 14k":
            ticks["met"].append("ISO14001")
            placed.append(item)
    state["$unresolved"] = [i for i in state.pop("$unresolved", []) if i not in placed]
    return Migrated(state)


def test_a_kinds_migration_places_what_it_knows_and_leaves_the_rest_unresolved(sheet, tmp_path):
    root = release_4(tmp_path, "ISO 9001", "ISO 14k")
    with pytest.raises(MigrationError) as raised:
        sheet.load(root)
    error = raised.value
    assert error.code == "TP-M003" and isinstance(error, ValueError)
    (item,) = error.unresolved
    assert (item.path, item.value, item.boundary) == ("/content/2", "ISO 14k", "4 -> 5")
    assert "not in the fixed list" in item.reason and "/content/2" in str(error)


def test_a_consumers_migration_places_the_rest_and_the_document_loads(sheet, tmp_path):
    root = release_4(tmp_path, "ISO 9001", "ISO 14k")
    doc = sheet.load(root, migrations=[place_unknown_standards])
    ticks = doc.tree.content[-1]
    assert [s.name for s in ticks.met] == ["ISO9001", "ISO14001"]


def test_adopting_is_atomic_nothing_is_returned_and_nothing_written(sheet, tmp_path):
    root = release_4(tmp_path, "ISO 14k")
    before = mtimes(root)
    with pytest.raises(MigrationError):
        sheet.load(root)
    assert mtimes(root) == before and json.loads((root / "_texpkg/state.json").read_text())["data"] == 4


def test_a_saved_adopted_document_is_written_for_the_current_data(sheet, tmp_path):
    root = release_4(tmp_path, "ISO 9001")
    doc = sheet.load(root)
    doc.save()
    envelope = json.loads((root / "_texpkg/state.json").read_text())
    assert envelope["data"] == 5 and [c["type"] for c in envelope["tree"]["content"]] == ["Heading", "Ticks"]
    assert json.loads((root / "_texpkg/history/1/state.json").read_text())["data"] == 4
    assert sheet.load(root).tree == doc.tree


def test_a_boundary_with_no_migration_changes_nothing(sheet, tmp_path):
    root = release_4(
        tmp_path, data=3
    )  # 3 -> 4 has no migration, 4 -> 5 turns the (empty) table into an empty tick list
    assert [s.name for s in sheet.load(root).tree.content[-1].met] == []


def test_a_consumer_migration_for_another_boundary_is_not_run(sheet, tmp_path):
    ran = []

    @migration(to=3)
    def old(state):  # noqa: ANN001, ANN202
        ran.append(state)
        return Migrated(state)

    sheet.load(release_4(tmp_path, "ISO 9001"), migrations=[old])
    assert ran == []


def test_the_consumers_migration_sees_what_the_kinds_left_in_the_state_and_in_the_unresolved_list(sheet, tmp_path):
    seen = []

    @migration(to=5)
    def look(state):  # noqa: ANN001, ANN202
        seen.append(([c["type"] for c in state["content"]], [i["boundary"] for i in state["$unresolved"]]))
        state["$unresolved"] = []
        return Migrated(state)

    sheet.load(release_4(tmp_path, "ISO 14k"), migrations=[look])
    assert seen == [(["Heading", "Ticks"], ["4 -> 5"])]


def test_a_migration_may_leave_its_own_unresolved_items(sheet, tmp_path):
    @migration(to=5)
    def refuse(state):  # noqa: ANN001, ANN202
        return Migrated(state, [Unresolved("/content/0", "ask the author", "Pump")])

    with pytest.raises(MigrationError) as raised:
        sheet.load(release_4(tmp_path, "ISO 9001"), migrations=[refuse])
    assert [u.reason for u in raised.value.unresolved] == ["ask the author"]


def test_data_still_in_the_age_window_is_not_migrated(tmp_path):
    module = load_declaration("acme_sheet:dist", version="5.1.0", contracts=Contracts(data=Triple(5, 0, 2)))
    try:
        sheet = module.kinds.modules()["datasheet"]
        root = tmp_path / "doc"
        sheet.create(root, sheet.example())
        state_file = root / "_texpkg/state.json"
        envelope = json.loads(state_file.read_text())
        state_file.write_text(json.dumps(envelope | {"data": 3}))
        assert sheet.load(root).tree == sheet.example()  # 3 is within 5 - 2: it validates as it is
        state_file.write_text(json.dumps(envelope | {"data": 2}))
        with pytest.raises(MigrationError):
            sheet.load(root)  # 2 is outside it: migrated, and the kind's migration finds no table
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_sheet_tex"]:
            del sys.modules[name]


def test_what_does_not_validate_is_unresolved_with_its_constraint(expert, tmp_path):
    doc = expert.create(tmp_path, expert.example())
    state_file = tmp_path / "_texpkg/state.json"
    envelope = json.loads(state_file.read_text())
    envelope["tree"]["content"][1]["content"][2]["accent"] = "PINK"
    state_file.write_text(json.dumps(envelope))
    with pytest.raises(MigrationError) as raised:
        expert.load(tmp_path)
    (item,) = raised.value.unresolved
    assert item.path == "/content/1/content/2/accent" and item.value == "PINK" and item.boundary == "validation"
    assert item.schema["enum"] == ["SLATE", "MOSS"] and doc.path == tmp_path


def test_a_grammar_violation_is_unresolved_too(expert, tmp_path):
    expert.create(tmp_path, expert.example())
    state_file = tmp_path / "_texpkg/state.json"
    envelope = json.loads(state_file.read_text())
    envelope["tree"]["content"][1]["content"] = envelope["tree"]["content"][1]["content"][:1]  # a card without facts
    state_file.write_text(json.dumps(envelope))
    with pytest.raises(MigrationError) as raised:
        expert.load(tmp_path)
    assert [(u.path, "Fact" in u.reason) for u in raised.value.unresolved] == [("/content/1", True)]


# -- default changes -------------------------------------------------------------------------------------------------


def old_default(root: pathlib.Path) -> None:
    """The document was saved when `Fact.accent` defaulted to MOSS: the stored value was MOSS, still marked."""
    template = root / "_texpkg/template.json"
    saved = json.loads(template.read_text())
    saved["defaults"]["Fact.accent"] = "MOSS"
    template.write_text(json.dumps(saved))
    state_file = root / "_texpkg/state.json"
    envelope = json.loads(state_file.read_text())
    for card in envelope["tree"]["content"][1:]:
        for fact in card["content"][1:]:
            if "$defaults" in fact:
                fact["accent"] = "MOSS"
    state_file.write_text(json.dumps(envelope))


def accents(doc):  # noqa: ANN001, ANN201
    return [f.accent.name for card in doc.tree.content[1:] for f in card.content[1:]]


def test_a_marked_value_follows_a_changed_default_unless_the_consumer_says_otherwise(expert, tmp_path):
    expert.create(tmp_path, expert.example())
    old_default(tmp_path)
    assert accents(expert.load(tmp_path)) == [
        "SLATE",
        "MOSS",
        "SLATE",
    ]  # FOLLOW: the marked ones move to the new default
    assert accents(expert.load(tmp_path, default_changes=DefaultChange.FOLLOW)) == ["SLATE", "MOSS", "SLATE"]


def test_freeze_keeps_the_old_value_and_it_stops_being_marked(expert, tmp_path):
    expert.create(tmp_path, expert.example())
    old_default(tmp_path)
    doc = expert.load(tmp_path, default_changes=DefaultChange.FREEZE)
    assert accents(doc) == ["MOSS", "MOSS", "MOSS"] and doc.defaults == ()


def test_ask_aborts_with_each_changed_default(expert, tmp_path):
    expert.create(tmp_path, expert.example())
    old_default(tmp_path)
    with pytest.raises(MigrationError) as raised:
        expert.load(tmp_path, default_changes=DefaultChange.ASK)
    assert [u.path for u in raised.value.unresolved] == ["/content/1/content/1/accent", "/content/2/content/1/accent"]
    assert "changed from 'MOSS' to 'SLATE'" in raised.value.unresolved[0].reason


def test_a_policy_can_be_chosen_per_field_by_its_data_path_or_its_class(expert, tmp_path):
    expert.create(tmp_path, expert.example())
    old_default(tmp_path)
    by_path = expert.load(tmp_path, default_changes={"/content/1/content/1/accent": DefaultChange.FREEZE})
    assert accents(by_path) == ["MOSS", "MOSS", "SLATE"]
    by_class = expert.load(tmp_path, default_changes={"Fact.accent": DefaultChange.FREEZE})
    assert accents(by_class) == ["MOSS", "MOSS", "MOSS"]
    exact_wins = expert.load(
        tmp_path,
        default_changes={"Fact.accent": DefaultChange.FREEZE, "/content/1/content/1/accent": DefaultChange.FOLLOW},
    )
    assert accents(exact_wins) == ["SLATE", "MOSS", "MOSS"]


def test_the_generic_load_takes_the_same_arguments(acme_brand_tex, expert, tmp_path):
    expert.create(tmp_path, expert.example())
    old_default(tmp_path)
    doc = acme_brand_tex.load(tmp_path, default_changes=DefaultChange.FREEZE)
    assert accents(doc) == ["MOSS", "MOSS", "MOSS"]


# -- the pieces ------------------------------------------------------------------------------------------------------


def test_locations_become_data_paths():
    assert history.pointer(("content", 1, "Card", "content", 0, "Title", "text")) == "/content/1/content/0/text"
    assert history.pointer(("content",)) == "/content" and history.pointer(()) == ""
    assert (
        history.violation_pointer("Deck") == ""
        and history.violation_pointer("Deck/Card[1]/Fact[0]") == "/content/1/content/0"
    )


def test_the_schema_of_a_field_is_found_or_empty():
    schema = {"$defs": {"Fact": {"properties": {"accent": {"enum": ["a"]}}}}, "properties": {"content": {}}}
    assert history.schema_at(schema, ("content", 1, "Fact", "accent")) == {"enum": ["a"]}
    assert history.schema_at(schema, ("content", 1, "Nothing", "accent")) == {}
    assert history.schema_at(schema, ("content",)) == {}
