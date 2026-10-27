"""The document directory and its state (P27, P29, D1-D9, V21-V27)."""

import json
import pathlib
import sys

import pytest
from acme_brand import Accent, Card, Deck, Fact, Glossary, Mark, Term, Title, expert_example
from hypothesis import (
    given,
    strategies as st,
)
from jsonschema import Draft202012Validator
from texmodel.body import Comment
from texmodel.components import Command, Environment, Passthrough
from texmodel.package import Package
from texmodel.types import Raw, Text

from texpkg._internal import directory, handedits, state
from texpkg.document import FileState, HandEditKind
from texpkg.errors import (
    DocumentExistsError,
    HandEditError,
    KindMismatchError,
    NewerDataError,
    NotADocumentError,
    PayloadError,
)
from texpkg_build.testing import load_declaration

from .helpers import FIXTURES, golden

GENERATED = FIXTURES / "acme_brand" / "generated"
EXPERT_FILES = [
    "_texpkg/plan-compact.json",
    "_texpkg/plan-wide.json",
    "_texpkg/plan.json",
    "_texpkg/state.json",
    "_texpkg/template.json",
    "deck-compact.tex",
    "deck-wide.tex",
    "deck.tex",
    "lmroman10-regular.otf",
    "res/texpkg/NOTICE.txt",
    "res/texpkg/acme-brand-provenance.sty",
    "res/texpkg/acme-brand.sty",
    "res/texpkg/lockup.pdf",
]


def files(root: pathlib.Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and "history" not in p.parts)


def mtimes(root: pathlib.Path) -> dict[str, int]:
    return {p.as_posix(): p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def doc(expert, tmp_path):
    return expert.create(tmp_path / "doc", expert.example())


# -- create, load, the round trip ------------------------------------------------------------------------------------


def test_create_writes_both_states_and_nothing_else(doc):
    assert files(doc.path) == ["_texpkg/state.json", "_texpkg/template.json"]
    assert doc.kind == "expert" and doc.tree.violations() == []


def test_create_refuses_a_directory_that_holds_a_document_and_a_tree_that_breaks_a_rule(expert, doc):
    with pytest.raises(DocumentExistsError) as raised:
        expert.create(doc.path, expert.example())
    assert raised.value.code == "TP-D002" and isinstance(raised.value, FileExistsError)
    with pytest.raises(ExceptionGroup):
        expert.create(doc.path.parent / "other", Deck(Card(Title(text="no mark, no fact"))))
    assert not (doc.path.parent / "other").exists()


def test_load_returns_the_saved_tree_and_writes_nothing(expert, doc):
    before = mtimes(doc.path)
    loaded = expert.load(doc.path)
    assert state.tree_state(loaded.tree) == state.tree_state(doc.tree) and loaded.path == doc.path
    assert mtimes(doc.path) == before


TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=12)
FACT = st.builds(
    lambda text, accent: Fact(text=text, accent=accent) if accent else Fact(text=text),
    TEXT,
    st.sampled_from([None, *Accent]),
)
CARD = st.builds(lambda title, facts: Card(Title(text=title), *facts), TEXT, st.lists(FACT, min_size=1, max_size=3))
DECK = st.builds(lambda cards: Deck(Mark(), *cards), st.lists(CARD, min_size=1, max_size=3))


@given(DECK)
def test_a_tree_survives_a_save_and_a_load(tree):
    module = load_declaration("acme_brand:dist", version="1.2.0")
    expert = module.kinds.modules()["expert"]
    root = pathlib.Path(module._scratch.name) / "round-trip"
    created = expert.create(root, tree)
    loaded = expert.load(root)
    assert state.tree_state(loaded.tree) == state.tree_state(created.tree)
    assert loaded.render() == created.render()
    (root / "_texpkg" / "state.json").unlink()
    (root / "_texpkg" / "template.json").unlink()


def test_a_value_the_author_set_to_the_default_stays_the_authors(expert, tmp_path):
    set_by_author = Deck(Mark(), Card(Title(text="a"), Fact(text="b", accent=Accent.SLATE), Fact(text="c")))
    doc = expert.create(tmp_path, set_by_author)
    assert doc.defaults == ("/content/1/content/2/accent",)
    loaded = expert.load(tmp_path)
    assert loaded.defaults == doc.defaults
    assert loaded.tree.content[1].content[1].model_fields_set == {"text", "accent"}  # pyright: ignore[reportAttributeAccessIssue]
    raw = json.loads((tmp_path / "_texpkg" / "state.json").read_text())["tree"]["content"][1]["content"]
    assert "$defaults" not in raw[1] and raw[2]["$defaults"] == ["accent"] and raw[2]["accent"] == "SLATE"


def test_a_default_follows_the_package_and_a_set_value_does_not(expert, tmp_path):
    doc = expert.create(tmp_path, expert_example())
    path = doc.path / "_texpkg" / "state.json"
    envelope = json.loads(path.read_text())
    marked = envelope["tree"]["content"][1]["content"][1]
    marked["accent"] = "MOSS"  # what an older default was: a marked value is the package's, not the author's
    path.write_text(json.dumps(envelope))
    assert expert.load(tmp_path).tree.content[1].content[1].accent is Accent.SLATE  # pyright: ignore[reportAttributeAccessIssue]


def test_the_state_validates_against_the_stored_schema(expert, doc):
    envelope = json.loads((doc.path / "_texpkg" / "state.json").read_text())
    assert list(envelope) == ["package", "kind", "data", "tree"]
    assert (envelope["package"], envelope["kind"], envelope["data"]) == ("acme-brand-tex", "expert", 1)
    schema = expert.schema("serialization")
    assert list(Draft202012Validator(schema).iter_errors({"tree": envelope["tree"]})) == []
    assert list(Draft202012Validator(expert.schema()).iter_errors({"tree": envelope["tree"]})) == []
    bad = json.loads(json.dumps(envelope["tree"]))
    del bad["content"][1]["content"][1]["accent"]
    assert list(Draft202012Validator(schema).iter_errors(bad))  # a stored value is always written


# -- refusing what is not this kind's, this package's or this release's ---------------------------------------------


def write_state(root, **changes):
    path = root / "_texpkg" / "state.json"
    envelope = json.loads(path.read_text()) | changes
    path.write_text(json.dumps(envelope))


def test_load_refuses_what_is_not_a_document(expert, tmp_path):
    with pytest.raises(NotADocumentError) as raised:
        expert.load(tmp_path)
    assert raised.value.code == "TP-D001" and isinstance(raised.value, FileNotFoundError)
    (tmp_path / "_texpkg").mkdir()
    for text in ["not json", "[]", '{"package": "x"}']:
        (tmp_path / "_texpkg" / "state.json").write_text(text)
        with pytest.raises(NotADocumentError):
            expert.load(tmp_path)


def test_load_refuses_another_kind_and_another_package(expert, vocab, doc):
    with pytest.raises(KindMismatchError) as raised:
        vocab.load(doc.path)
    assert (raised.value.found, raised.value.expected, raised.value.code) == ("expert", "vocab", "TP-D003")
    assert isinstance(raised.value, ValueError)
    write_state(doc.path, package="other-tex")
    with pytest.raises(KindMismatchError) as raised:
        expert.load(doc.path)
    assert raised.value.found == "other-tex:expert" and raised.value.expected == "acme-brand-tex"


def test_load_refuses_data_written_for_a_newer_release(expert, doc):
    write_state(doc.path, data=2)
    with pytest.raises(NewerDataError) as raised:
        expert.load(doc.path)
    assert raised.value.code == "TP-D004"


def test_the_generic_load_finds_the_kind_in_the_state(acme_brand_tex, expert, doc):
    assert acme_brand_tex.load(doc.path).kind == "expert"
    write_state(doc.path, package="other-tex")
    with pytest.raises(KindMismatchError):
        acme_brand_tex.load(doc.path)


# -- save and check --------------------------------------------------------------------------------------------------


def test_save_writes_the_states_every_tex_with_its_plan_and_the_payload_of_the_kind(doc, vocab, tmp_path):
    doc.save()
    assert files(doc.path) == EXPERT_FILES
    other = vocab.create(tmp_path / "vocab", vocab.example())
    other.save()
    assert files(other.path) == [  # the lock-up is the expert kind's only (A6)
        "_texpkg/plan.json",
        "_texpkg/state.json",
        "_texpkg/template.json",
        "glossary.tex",
        "lmroman10-regular.otf",
        "res/texpkg/NOTICE.txt",
        "res/texpkg/acme-brand-provenance.sty",
        "res/texpkg/acme-brand.sty",
    ]
    assert (doc.path / "deck.tex").read_text() == doc.render()
    assert (doc.path / "deck-wide.tex").read_text() == doc.render("wide")


def test_the_state_and_the_plan_are_golden(doc):
    doc.save()
    golden(GENERATED / "state.json", (doc.path / "_texpkg/state.json").read_text())
    golden(GENERATED / "plan.json", (doc.path / "_texpkg/plan.json").read_text())


def test_the_template_state_records_what_reached_the_document(doc):
    doc.save()
    template = json.loads((doc.path / "_texpkg/template.json").read_text())
    assert template["package"] == "acme-brand-tex" and template["release"] == "1.2.0"
    assert template["contracts"] == {"data": [1, 0, 0], "interface": [1, 0, 0], "output": [1, 0]}
    assert template["settings"]["deck.tex"] == {"FactGap": "\\setlength{\\abFactGap}{3mm}"}
    assert template["settings"]["deck-compact.tex"]["Compact"] == "\\abCompacttrue"
    assert template["settings"]["deck-wide.tex"] == {"FactGap": "\\setlength{\\abFactGap}{6mm}"}
    assert template["defaults"] == {"Fact.accent": "SLATE"}
    assert list(template["sty"]) == ["acme-brand.sty"] and len(template["sty"]["acme-brand.sty"]) == 64
    assert template["stack"] == [{"package": "acme-brand-tex", "release": "1.2.0", "output": [1, 0]}]
    stack = doc.stack
    assert [(e.package, e.release, e.output.current) for e in stack.entries] == [("acme-brand-tex", "1.2.0", 1)]


def test_the_stack_of_an_unsaved_document_is_the_releases(expert, tmp_path):
    doc = expert.create(tmp_path, expert.example())
    (tmp_path / "_texpkg/template.json").unlink()
    assert doc.stack.entries[0].release == "1.2.0"


def test_a_second_save_writes_nothing_and_adds_no_history(doc):
    doc.save()
    before = mtimes(doc.path)
    doc.save()
    assert mtimes(doc.path) == before and not (doc.path / "_texpkg/history").exists()


def test_a_save_after_a_change_keeps_the_last_three_pairs(expert, doc):
    doc.save()
    for n in range(1, 6):
        doc = doc.replace(Deck(Mark(), Card(Title(text=f"v{n}"), Fact(text="x"))))
        doc.save()
    history = doc.path / "_texpkg/history"
    assert sorted(p.name for p in history.iterdir()) == ["1", "2", "3"]
    titles = [
        json.loads((history / n / "state.json").read_text())["tree"]["content"][1]["content"][0]["text"] for n in "123"
    ]
    assert titles == ["v4", "v3", "v2"]
    assert sorted(p.name for p in (history / "1").iterdir()) == ["state.json", "template.json"]
    assert expert.load(doc.path).tree.content[1].content[0].text == "v5"  # pyright: ignore[reportAttributeAccessIssue]


def test_a_save_writes_only_what_changed(doc):
    doc.save()
    before = mtimes(doc.path)
    doc.replace(Deck(Mark(), Card(Title(text="Changed"), Fact(text="x")))).save()
    after = mtimes(doc.path)
    changed = sorted(k.removeprefix(doc.path.as_posix() + "/") for k in after if before.get(k) != after[k])
    assert changed == [
        "_texpkg/history/1/state.json",
        "_texpkg/history/1/template.json",
        "_texpkg/plan-compact.json",
        "_texpkg/plan-wide.json",
        "_texpkg/plan.json",
        "_texpkg/state.json",
        "deck-compact.tex",
        "deck-wide.tex",
        "deck.tex",
    ]


def test_save_writes_nothing_when_the_tree_or_the_payload_is_not_whole(expert, doc, tmp_path):
    broken = doc.replace(Deck(Card(Title(text="no mark"))))
    with pytest.raises(ExceptionGroup):
        broken.save()
    assert files(doc.path) == ["_texpkg/state.json", "_texpkg/template.json"]
    module = load_declaration("acme_brand:broken", version="1.2.0")
    kind = module.kinds.modules()["expert"]
    other = kind.create(tmp_path / "other", kind.example())
    with pytest.raises(PayloadError) as raised:
        other.save()
    assert raised.value.code == "TP-A004" and files(other.path) == ["_texpkg/state.json", "_texpkg/template.json"]


def test_a_kind_can_name_its_tex_files(tmp_path):
    module = load_declaration("acme_brand:renamed", version="1.2.0")
    try:
        kind = module.kinds.modules()["expert"]
        doc = kind.create(tmp_path / "doc", kind.example())
        doc.save()
        tex = sorted(p.name for p in doc.path.glob("*.tex"))
        assert tex == ["brand-deck-compact.tex", "brand-deck-wide.tex", "brand-deck.tex"]
        (doc.path / "brand-deck.tex").write_text((doc.path / "brand-deck.tex").read_text() + "% edited\n")
        assert {e.file.name for e in doc.hand_edits()} == {"brand-deck.tex"}
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
            del sys.modules[name]


def test_check_is_current_after_a_save_and_never_writes(doc):
    assert not doc.check().current
    doc.save()
    before = mtimes(doc.path)
    report = doc.check()
    assert report.current and report.edits == ()
    assert sorted(p.relative_to(doc.path).as_posix() for p in report.files) == EXPERT_FILES
    assert set(report.files.values()) == {FileState.UNCHANGED}
    assert mtimes(doc.path) == before


def test_check_reports_changed_missing_and_extra_files(doc):
    doc.save()
    (doc.path / "res/texpkg/acme-brand.sty").write_text("edited")
    (doc.path / "res/texpkg/lockup.pdf").unlink()
    (doc.path / "res/texpkg/retired.sty").write_text("old")
    report = doc.check()
    states = {p.relative_to(doc.path).as_posix(): s for p, s in report.files.items() if s is not FileState.UNCHANGED}
    assert states == {
        "res/texpkg/acme-brand.sty": FileState.CHANGED,
        "res/texpkg/lockup.pdf": FileState.MISSING,
        "res/texpkg/retired.sty": FileState.EXTRA,
    }
    assert not report.current


def test_an_extra_file_alone_does_not_make_a_document_not_current(doc):
    doc.save()
    (doc.path / "res/texpkg/retired.sty").write_text("old")
    assert doc.check().current


def test_check_sees_an_unsaved_tree(doc):
    doc.save()
    report = doc.replace(Deck(Mark(), Card(Title(text="Other"), Fact(text="x")))).check()
    changed = {p.name for p, s in report.files.items() if s is FileState.CHANGED}
    assert changed == {
        "state.json",
        "plan.json",
        "plan-compact.json",
        "plan-wide.json",
        "deck.tex",
        "deck-compact.tex",
        "deck-wide.tex",
    }


# -- hand edits ------------------------------------------------------------------------------------------------------


def edit_file(root: pathlib.Path, name: str, old: str, new: str) -> None:
    text = (root / name).read_text()
    assert old in text
    (root / name).write_text(text.replace(old, new, 1))


def test_a_hand_edited_tex_is_given_back_and_not_overwritten(expert, doc):
    doc.save()
    edit_file(doc.path, "deck.tex", "\\abTitle{Fox}", "\\abTitle{Fox!}")
    (edit,) = doc.hand_edits()
    assert (edit.file, edit.path, edit.kind, edit.value) == (
        doc.path / "deck.tex",
        "/content/1/content/0",
        HandEditKind.CHANGED,
        None,
    )
    assert (edit.expected, edit.found) == ("\\abTitle{Fox}", "\\abTitle{Fox!}")
    changed = doc.replace(Deck(Mark(), Card(Title(text="Other"), Fact(text="x"))))
    with pytest.raises(HandEditError) as raised:
        changed.save()
    assert raised.value.code == "TP-D005" and raised.value.edits == (edit,) and isinstance(raised.value, ValueError)
    assert (
        "Fox!" in (doc.path / "deck.tex").read_text() and "Other" not in (doc.path / "_texpkg/state.json").read_text()
    )
    changed.save(force=True)
    assert "Fox!" not in (doc.path / "deck.tex").read_text() and changed.hand_edits() == ()


def test_check_reports_a_hand_edit_as_changed_and_lists_it(doc):
    doc.save()
    edit_file(doc.path, "deck-wide.tex", "\\abMark\n", "\\abMark\n\\vspace{1cm}\n")
    report = doc.check()
    assert not report.current and report.files[doc.path / "deck-wide.tex"] is FileState.CHANGED
    assert [(e.kind, e.found, e.path) for e in report.edits] == [(HandEditKind.ADDED, "\\vspace{1cm}", "/content/0")]


def test_removed_and_added_lines_are_edits_too(doc):
    doc.save()
    edit_file(doc.path, "deck.tex", "\\abFact[ab-moss]{50\\% of \\$5}\n", "")
    (edit,) = doc.hand_edits()
    assert (edit.kind, edit.expected, edit.found) == (HandEditKind.REMOVED, "\\abFact[ab-moss]{50\\% of \\$5}", "")
    assert edit.path == "/content/1/content/2"


def test_an_edit_in_the_preamble_keeps_the_plans_own_path(doc):
    doc.save()
    edit_file(doc.path, "deck.tex", "\\setlength{\\abFactGap}{3mm}", "\\setlength{\\abFactGap}{9mm}")
    assert [e.path for e in doc.hand_edits()] == ["settings[0]"]


def test_a_tex_without_a_saved_plan_is_nobodys_edit(doc):
    (doc.path / "deck.tex").write_text("whatever")
    assert doc.hand_edits() == ()
    doc.save()
    assert (doc.path / "deck.tex").read_text() == doc.render()


@pytest.mark.parametrize(
    ("plan_path", "data"),
    [
        ("Deck[0]", ""),
        ("Deck[0]/Card[1]/Title[0]", "/content/1/content/0"),
        ("header", "header"),
        ("document", "document"),
        ("preamble.after_package[2]", "preamble.after_package[2]"),
        ("settings[1]", "settings[1]"),
    ],
)
def test_a_plan_path_is_mapped_to_a_data_path(plan_path, data):
    assert handedits.data_path(plan_path) == data


# -- template changes ------------------------------------------------------------------------------------------------


def test_a_document_saved_by_this_release_has_no_template_changes(doc):
    doc.save()
    assert doc.template_changes() == ()


def test_a_new_release_changes_the_template_not_the_data(expert, doc):
    doc.save()
    newer = load_declaration("acme_brand:changed", version="1.3.0")
    kind = newer.kinds.modules()["expert"]
    loaded = kind.load(doc.path)
    assert state.tree_state(loaded.tree) == state.tree_state(doc.tree)
    changes = {c.setting: (c.old, c.new) for c in loaded.template_changes()}
    assert changes["setting deck.tex FactGap"] == ("\\setlength{\\abFactGap}{3mm}", "\\setlength{\\abFactGap}{4mm}")
    assert changes["setting deck-compact.tex FactGap"][1] == "\\setlength{\\abFactGap}{4mm}"
    assert "setting deck-wide.tex FactGap" not in changes  # the variant sets it itself
    assert [k for k in changes if k.startswith("sty ")] == ["sty acme-brand.sty"]  # the version is in the .sty's header
    assert not [k for k in changes if k.startswith("default ")]
    assert list(changes) == sorted(changes)
    loaded.save()  # adopting the release rewrites the template and keeps the old pair
    assert loaded.template_changes() == () and (doc.path / "_texpkg/history/1/template.json").is_file()


def test_template_changes_need_a_saved_template(doc):
    (doc.path / "_texpkg/template.json").unlink()
    with pytest.raises(NotADocumentError):
        doc.template_changes()


# -- the directory helpers -------------------------------------------------------------------------------------------


def test_history_rotation_needs_a_pair_to_keep(tmp_path):
    directory.rotate_history(tmp_path)
    assert not (tmp_path / "_texpkg").exists()
    assert directory.plan_file(None) == "_texpkg/plan.json" and directory.plan_file("wide") == "_texpkg/plan-wide.json"


def test_a_glossary_document_round_trips_through_its_kind(vocab, tmp_path):
    tree = Glossary(Term(word="a", meaning="b"), Term(word="c", meaning="d"))
    created = vocab.create(tmp_path, tree)
    assert isinstance(vocab.load(tmp_path).tree, Glossary) and created.defaults == ()


# -- trees with comments and passthroughs ----------------------------------------------------------------------------

pages = Package("pages", prefix="pg")


@pages.command
class Line(Command):
    """A line."""

    text: Text
    mark: Text = "-"

    body = r"#mark #text"


@pages.environment
class Page(Environment):
    """A page of lines, with TeX between them."""

    begin = r"\begingroup"
    end = r"\endgroup"

    children = [Line.times.any(), Passthrough.times.any()]


def test_comments_and_passthroughs_are_state_too():
    tree = Page(Line(text="a"), Comment("a note"), Passthrough(Raw(r"\vspace{1mm}")), Line(text="b", mark="*"))
    stored = state.tree_state(tree)
    assert [c["type"] for c in stored["content"]] == ["Line", "Comment", "Passthrough", "Line"]
    assert stored["content"][1] == {"type": "Comment", "text": "a note"}
    assert stored["content"][0]["$defaults"] == ["mark"] and "$defaults" not in stored["content"][3]
    assert state.default_paths(tree) == ("/content/0/mark",)
    again = state.tree_from_state(Page, json.loads(json.dumps(stored)))
    assert state.tree_state(again) == stored
