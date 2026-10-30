"""Contract versions (V10-V13, V33, V35-V37)."""

import dataclasses
import json
import pathlib
import re
import shutil
import sys

import pytest
from texmodel import history
from texmodel.history import Level
from typer.testing import CliRunner

from texpkg import errors
from texpkg._internal import classify, snapshots
from texpkg._internal.versions import Versions
from texpkg.contracts import Changes, Pair, Triple
from texpkg_build._internal import snapshot
from texpkg_build.cli import app

from . import projects, spawn


@pytest.fixture
def brand(tmp_path):
    """An author's project of the acme brand, with the declaration in `src/acme_brand` (the CLI and the build import it
    and leave the process as they found it)."""
    return projects.author_project(tmp_path / "brand")


def contracts(project: pathlib.Path, *flags: str):  # noqa: ANN201
    return CliRunner().invoke(app, ["contracts", "--root", str(project), *flags])


def versions(project: pathlib.Path, where: str = "next") -> Versions:
    return Versions.parse((project / "contracts" / where / "versions.toml").read_text())


def edit(project: pathlib.Path, path: str, old: str, new: str) -> None:
    file = project / path
    text = file.read_text()
    assert old in text, (path, old)
    file.write_text(text.replace(old, new, 1))


def release(project: pathlib.Path) -> Versions:
    """Freeze what `contracts/next` says as the release it names."""
    result = contracts(project, "--freeze")
    assert result.exit_code == 0, result.output
    return versions(project, versions(project).release)


def classify_output(project: pathlib.Path, how: str) -> None:
    edit(project, "contracts/next/versions.toml", 'change = ""', f'change = "{how}"')


# -- the rules -------------------------------------------------------------------------------------------------------

FIELD = {"type": "string", "title": "Text"}


def schema(**properties):  # noqa: ANN003, ANN201
    return {"title": "Fact", "type": "object", "properties": properties, "required": ["text"], "$defs": {}}


@pytest.mark.parametrize(
    ("old", "new", "level", "words"),
    [
        (schema(text=FIELD), schema(text=FIELD), Level.NONE, ""),
        (schema(text=FIELD), schema(text=FIELD, note={"type": "string"}), Level.COMPATIBLE, "added"),
        (schema(text=FIELD, note={}), schema(text=FIELD), Level.BREAKING, "removed"),
        (schema(text=FIELD), schema(text={"type": "integer", "title": "Text"}), Level.BREAKING, "type changed"),
        (
            schema(text={**FIELD, "maxLength": 100}),
            schema(text={**FIELD, "maxLength": 70}),
            Level.BREAKING,
            "maxLength",
        ),
        (
            schema(text={**FIELD, "maxLength": 70}),
            schema(text={**FIELD, "maxLength": 100}),
            Level.COMPATIBLE,
            "maxLength",
        ),
        (schema(text={**FIELD, "minLength": 1}), schema(text={**FIELD, "minLength": 3}), Level.BREAKING, "minLength"),
        (schema(text={**FIELD, "maxItems": 3}), schema(text={**FIELD, "maxItems": 2}), Level.BREAKING, "maxItems"),
        (
            schema(text={**FIELD, "enum": ["a", "b"]}),
            schema(text={**FIELD, "enum": ["a"]}),
            Level.BREAKING,
            "no longer",
        ),
        (schema(text={**FIELD, "enum": ["a"]}), schema(text={**FIELD, "enum": ["a", "b"]}), Level.COMPATIBLE, "added"),
        (schema(text={**FIELD, "default": "a"}), schema(text={**FIELD, "default": "b"}), Level.REVISION, "default"),
        (schema(text=FIELD), schema(text={**FIELD, "description": "the name"}), Level.REVISION, "description"),
        (
            schema(text=FIELD, note={}),
            {**schema(text=FIELD, note={}), "required": ["text", "note"]},
            Level.BREAKING,
            "required",
        ),
        (schema(text=FIELD), {**schema(text=FIELD, note={}), "required": ["text", "note"]}, Level.BREAKING, "required"),
        (schema(text=FIELD, old={}), schema(text=FIELD, new={"x-renamed-from": "old"}), Level.COMPATIBLE, "renamed"),
    ],
)
def test_a_schema_change_is_classified_as_avro_does(old, new, level, words):
    found = history.schema_changes(old, new)
    assert history.worst(found) is level and (not words or any(words in c.what for c in found))


def test_classes_and_branches_that_go_or_come_are_changes():
    one = {"title": "Deck", "properties": {}, "$defs": {"Card": {"title": "Card"}}}
    two = {"title": "Deck", "properties": {}, "$defs": {"Card": {"title": "Card"}, "Mark": {"title": "Mark"}}}
    assert history.worst(history.schema_changes(one, two)) is Level.COMPATIBLE
    assert history.worst(history.schema_changes(two, one)) is Level.BREAKING

    def items(*refs: str) -> dict:  # noqa: ANN401
        return {
            "properties": {"content": {"items": {"oneOf": [{"$ref": r} for r in refs]}}},
            "title": "Deck",
        }

    assert history.worst(history.schema_changes(items("a", "b"), items("a"))) is Level.BREAKING
    assert history.worst(history.schema_changes(items("a"), items("a", "b"))) is Level.COMPATIBLE
    assert history.schema_changes(items("a"), items("a")) == []


def test_the_interface_is_names_and_signatures():
    def component(*args, doc="d", cs="abX"):  # noqa: ANN002, ANN202
        return {"components": {"X": {"doc": doc, "cs": cs, "signature": [list(a) for a in args]}}, "kinds": {}}

    base = component(("text", "Text", False))
    assert classify.interface_changes(base, base) == []
    assert (
        history.worst(classify.interface_changes(base, component(("text", "Text", False), ("n", "Text", True))))
        is Level.COMPATIBLE
    )
    assert (
        history.worst(classify.interface_changes(base, component(("text", "Text", False), ("n", "Text", False))))
        is Level.BREAKING
    )
    assert history.worst(classify.interface_changes(base, component(("other", "Text", False)))) is Level.BREAKING
    assert (
        history.worst(classify.interface_changes(base, component(("text", "Text", False), cs="abY"))) is Level.BREAKING
    )
    assert (
        history.worst(classify.interface_changes(base, component(("text", "Text", False), doc="e"))) is Level.REVISION
    )
    assert history.worst(classify.interface_changes(base, {"components": {}, "kinds": {}})) is Level.BREAKING
    kinds = lambda v: {"components": {}, "kinds": {"k": {"variants": v}}}  # noqa: E731
    assert history.worst(classify.interface_changes(kinds(["a", "b"]), kinds(["a"]))) is Level.BREAKING
    assert history.worst(classify.interface_changes(kinds(["a"]), kinds(["a", "b"]))) is Level.COMPATIBLE


def test_libtools_bump_table():
    start = Triple(2, 3, 1)
    assert [classify.bump(start, level) for level in Level] == [
        Triple(2, 3, 1),
        Triple(2, 4, 1),
        Triple(3, 0, 2),
        Triple(3, 0, 0),
    ]
    assert classify.bump_output(Pair(2, 1), "") == Pair(2, 1)
    assert classify.bump_output(Pair(2, 1), "revision") == Pair(2, 2)
    assert classify.bump_output(Pair(2, 1), "current") == Pair(3, 0)


def test_a_release_number_follows_the_contracts_and_moves_one_place_lower_before_one():
    required = classify.required_release
    assert required("0.1.0", Level.BREAKING, Level.NONE, False) == "0.2.0"
    assert required("0.1.0", Level.COMPATIBLE, Level.NONE, False) == "0.1.1"
    assert required("0.1.0", Level.NONE, Level.NONE, True) == "0.1.1"
    assert required("0.1.0", Level.NONE, Level.NONE, False) == "0.1.1"
    assert required("1.4.2", Level.NONE, Level.BREAKING, False) == "2.0.0"
    assert required("1.4.2", Level.COMPATIBLE, Level.NONE, False) == "1.5.0"
    assert required("1.4.2", Level.NONE, Level.NONE, True) == "1.5.0"
    assert required("1.4.2", Level.NONE, Level.NONE, False) == "1.4.3"
    assert classify.parse_version("1.10.2") > classify.parse_version("1.9.9")


def test_the_versions_file_round_trips():
    text = Versions(
        "1.2.0",
        Triple(3, 1, 2),
        Triple(2, 0, 1),
        Pair(4, 2),
        "revision",
        {3: "a note"},
        {1: "1.0.0", 3: "1.2.0"},
        {1: 1, 3: 2},
        5,
    )
    assert Versions.parse(text.to_text()) == text and text.contracts().base_data == ((1, 1), (3, 2))
    assert Versions.parse(Versions("0.1.0").to_text()) == Versions("0.1.0")


# -- a project over its releases -------------------------------------------------------------------------------------


def test_the_first_snapshot_is_written_reviewed_and_frozen(brand):
    result = contracts(brand)
    assert result.exit_code == 0 and "release 0.1.0: data 1:0:0 interface 1:0:0 output 1:0" in result.output
    files = sorted(
        p.relative_to(brand / "contracts/next").as_posix() for p in (brand / "contracts/next").rglob("*") if p.is_file()
    )
    assert files == [
        "examples/expert.json",
        "examples/expert/deck-compact.tex",
        "examples/expert/deck-wide.tex",
        "examples/expert/deck.tex",
        "examples/vocab.json",
        "examples/vocab/glossary.tex",
        "interface.json",
        "kinds/expert.input.schema.json",
        "kinds/expert.stored.schema.json",
        "kinds/vocab.input.schema.json",
        "kinds/vocab.stored.schema.json",
        "output.json",
        "versions.toml",
    ]
    output = json.loads((brand / "contracts/next/output.json").read_text())
    assert list(output) == ["assets", "examples", "sty"] and "acme-brand.sty" in output["sty"]
    assert set(output["examples"]) == {
        "expert/deck.tex",
        "expert/deck-compact.tex",
        "expert/deck-wide.tex",
        "vocab/glossary.tex",
    }
    assert release(brand).release == "0.1.0" and (brand / "contracts/0.1.0/output.json").is_file()


def test_the_snapshot_is_deterministic(brand, tmp_path):
    contracts(brand)
    other = projects.author_project(tmp_path / "other")
    contracts(other)
    for path in (brand / "contracts/next").rglob("*"):
        if path.is_file():
            assert (
                path.read_text() == (other / "contracts/next" / path.relative_to(brand / "contracts/next")).read_text()
            )


def test_a_frozen_snapshot_is_never_rewritten(brand):
    release(brand)
    with pytest.raises(errors.DeclarationError) as raised:
        snapshot.freeze(brand)  # `contracts/next` is still the 0.1.0 it was frozen as
    assert raised.value.code == "TP-C002" and (brand / "contracts/0.1.0/versions.toml").is_file()
    result = contracts(brand, "--freeze")  # a new proposal is the next release
    assert result.exit_code == 0 and (brand / "contracts/0.1.1").is_dir()


def test_freezing_needs_a_snapshot(brand):
    with pytest.raises(errors.DeclarationError) as raised:
        snapshot.freeze(brand)
    assert raised.value.code == "TP-C001"


def test_nothing_changed_nothing_is_proposed(brand):
    release(brand)
    result = contracts(brand)
    assert "release 0.1.1: data 1:0:0 interface 1:0:0 output 1:0" in result.output
    assert "changed" not in result.output.replace("output changed", "")


def test_an_optional_argument_is_a_compatible_addition_and_an_output_change_the_author_classifies(brand):
    release(brand)
    edit(
        brand,
        "src/acme_brand/model.py",
        '''class Title(Command):
    """The subject's name."""

    text: Text
''',
        '''class Title(Command, unused=["note"]):
    """The subject's name."""

    text: Text
    note: Text | None = None
''',
    )
    first = contracts(brand)
    assert "data: compatible: expert: Title.note: added" in first.output and "interface: compatible" in first.output
    assert "output changed: say how" in first.output and "output: changed: sty: acme-brand.sty" in first.output
    classify_output(brand, "revision")
    contracts(brand)
    now = versions(brand)
    assert (now.release, now.data, now.interface, now.output) == ("0.1.1", Triple(2, 0, 1), Triple(2, 0, 1), Pair(1, 1))
    assert now.releases == {1: "0.1.0", 2: "0.1.1"} and now.output_change == "revision"


def test_a_colour_that_changes_is_an_output_change_that_needs_proofs_approved_again(brand):
    release(brand)
    edit(brand, "src/acme_brand/tokens.json", "2F3E46", "2F3E47")
    contracts(brand)
    classify_output(brand, "current")
    contracts(brand)
    now = versions(brand)
    assert (now.data, now.interface, now.output, now.release) == (Triple(1), Triple(1), Pair(2, 0), "0.1.1")


def test_a_dropped_palette_colour_is_a_break_of_the_data_contract(brand):
    release(brand)
    edit(brand, "src/acme_brand/model.py", '    SLATE = "ab-slate"\n    MOSS = "ab-moss"\n', '    SLATE = "ab-slate"\n')
    edit(brand, "src/acme_brand/__init__.py", "accent=Accent.MOSS", "accent=Accent.SLATE")
    result = contracts(brand)
    assert "data: breaking: expert: Fact.accent: values no longer allowed" in result.output
    now = versions(brand)
    assert (now.data, now.interface, now.release) == (Triple(2, 0, 0), Triple(1), "0.2.0")
    # the previous release's example named MOSS and no longer loads: it is reported, never guessed (V35)
    assert "output: not compared: expert" in result.output


def test_editing_an_example_is_not_an_output_change(brand):
    release(brand)
    edit(brand, "src/acme_brand/__init__.py", 'Title(text="Fox")', 'Title(text="Fox again")')
    result = contracts(brand)
    assert "output: changed" not in result.output and versions(brand).output == Pair(1, 0)
    assert "Fox again" in (brand / "contracts/next/examples/expert/deck.tex").read_text()
    again = contracts(brand)  # and the new example is now the baseline
    assert "output: changed" not in again.output


def test_what_the_author_wrote_survives_a_new_proposal(brand):
    release(brand)
    edit(brand, "src/acme_brand/tokens.json", "2F3E46", "2F3E47")
    contracts(brand)
    classify_output(brand, "current")
    edit(brand, "contracts/next/versions.toml", "[notes]\n", '[notes]\n"1" = "the first"\n')
    contracts(brand)
    now = versions(brand)
    assert now.output_change == "current" and now.notes == {1: "the first"}


# -- the build holds a package to its contracts ----------------------------------------------------------------------


def set_version(project: pathlib.Path, version: str) -> None:
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        re.sub(r'^version = ".*"$', f'version = "{version}"', pyproject.read_text(), flags=re.MULTILINE)
    )


def build(project: pathlib.Path, tmp_path: pathlib.Path) -> pathlib.Path:
    return projects.wheel(project, tmp_path / "dist")


def test_a_package_without_contracts_has_the_first_versions(brand, tmp_path):
    assert not (brand / "contracts").exists()
    set_version(brand, "0.1.0")
    build(brand, tmp_path)  # no error, nothing shipped


def test_a_development_build_must_follow_the_snapshot_it_is_made_from(brand, tmp_path):
    release(brand)
    contracts(brand)  # the next release's snapshot, which a development build is made from
    set_version(brand, "0.1.1.dev1")
    build(brand, tmp_path)
    edit(brand, "src/acme_brand/model.py", 'description="The acme brand"', 'description="The acme brand!"')
    with pytest.raises(errors.DeclarationError) as raised:
        build(brand, tmp_path)
    assert raised.value.code == "TP-C001" and "output.json" in str(raised.value)
    contracts(brand)
    with pytest.raises(errors.DeclarationError) as raised:
        build(brand, tmp_path)
    assert raised.value.code == "TP-C005"
    classify_output(brand, "revision")
    contracts(brand)
    assert build(brand, tmp_path).is_file()


def test_a_release_build_needs_its_frozen_snapshot_and_a_number_that_does_not_understate_it(brand, tmp_path):
    release(brand)
    set_version(brand, "0.1.0")
    build(brand, tmp_path)
    set_version(brand, "0.1.1")
    with pytest.raises(errors.DeclarationError) as raised:
        build(brand, tmp_path)
    assert raised.value.code == "TP-C003"
    edit(brand, "src/acme_brand/model.py", '    SLATE = "ab-slate"\n    MOSS = "ab-moss"\n', '    SLATE = "ab-slate"\n')
    edit(brand, "src/acme_brand/__init__.py", "accent=Accent.MOSS", "accent=Accent.SLATE")
    contracts(brand)
    classify_output(brand, "current")
    contracts(brand)
    release(brand)
    shutil.move(brand / "contracts/0.2.0", brand / "contracts/0.1.1")  # an author's understatement
    edit(brand, "contracts/0.1.1/versions.toml", 'release = "0.2.0"', 'release = "0.1.1"')
    with pytest.raises(errors.DeclarationError) as raised:
        build(brand, tmp_path)
    assert raised.value.code == "TP-C004" and "0.2.0" in str(raised.value)


def test_a_wheel_carries_its_versions_and_every_frozen_snapshot_and_explains_what_changed(brand, tmp_path):
    release(brand)
    edit(brand, "src/acme_brand/model.py", '    SLATE = "ab-slate"\n    MOSS = "ab-moss"\n', '    SLATE = "ab-slate"\n')
    edit(brand, "src/acme_brand/__init__.py", "accent=Accent.MOSS", "accent=Accent.SLATE")
    contracts(brand)
    edit(brand, "contracts/next/versions.toml", "[notes]\n", '[notes]\n"2" = "MOSS left the palette"\n')
    contracts(brand)
    release(brand)
    set_version(brand, "0.2.0")
    built = build(brand, tmp_path)
    inside = projects.names(built)
    assert (
        "acme_brand_tex/_contracts/0.1.0/versions.toml" in inside
        and "acme_brand_tex/_contracts/0.2.0/output.json" in inside
    )
    assert not [n for n in inside if "/_contracts/next" in n]
    site = tmp_path / "site"
    import zipfile

    zipfile.ZipFile(built).extractall(site)
    code = (
        "import json, acme_brand_tex as m\n"
        "from acme_brand_tex.kinds import expert\n"
        "c = expert.changes(1, 2)\n"
        "print(json.dumps([m.CONTRACTS.data.current, m.CONTRACTS.data.age, list(c.added), list(c.removed),"
        " list(c.tightened), list(c.notes), c.releases, expert.changes(2, 2).releases]))\n"
    )
    done = spawn.run([sys.executable, "-c", code], cwd=tmp_path, env={"PYTHONPATH": str(site)})
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == [2, 0, [], [], ["Fact.accent"], ["MOSS left the palette"], {"2": "0.2.0"}, {}]


def test_what_changed_is_empty_without_snapshots_and_between_the_same_version():
    assert snapshots.changes(None, "expert", 1, 2) == Changes()


def test_a_removed_kind_breaks_the_data_contract_and_an_added_one_extends_it(brand):
    release(brand)
    path = "src/acme_brand/__init__.py"
    line = '        Kind("vocab", Glossary, presets=(Ink(CMYK(0, 0, 0, 0.8)),), example=vocab_example),\n'
    edit(brand, path, line, "")
    edit(brand, path, ", dist.kinds[1]),", ",),")  # the fixture's other declarations name the kind too
    edit(brand, path, 'kinds=("vocab",)', 'kinds=("expert",)')
    gone = contracts(brand)
    assert "data: breaking: kind vocab: removed" in gone.output and versions(brand).data == Triple(2, 0, 0)
    release(brand)
    edit(brand, path, "    ),\n)\n\n# The same", line + "    ),\n)\n\n# The same")
    added = contracts(brand)
    assert "data: compatible: kind vocab: added" in added.output and versions(brand).data == Triple(3, 0, 1)


def test_the_same_data_rendered_differently_is_an_output_change(brand):
    release(brand)
    edit(
        brand,
        "src/acme_brand/model.py",
        'class Mark(Command):\n    """The brand\'s lock-up."""\n',
        'class Mark(Command):\n    """The brand\'s lock-up."""\n\n    cs = "abLockup"\n',
    )
    result = contracts(brand)
    assert "output: changed: example: expert/deck.tex" in result.output
    assert "interface: breaking: component Mark" in result.output


def test_what_changed_between_two_data_versions_is_read_from_the_frozen_snapshots(brand):
    release(brand)
    edit(brand, "src/acme_brand/model.py", '    SLATE = "ab-slate"\n    MOSS = "ab-moss"\n', '    SLATE = "ab-slate"\n')
    edit(brand, "src/acme_brand/__init__.py", "accent=Accent.MOSS", "accent=Accent.SLATE")
    contracts(brand)
    edit(brand, "contracts/next/versions.toml", "[notes]\n", '[notes]\n"2" = "MOSS left the palette"\n')
    contracts(brand)
    release(brand)
    root = brand / "contracts"
    found = snapshots.changes(root, "expert", 1, 2)
    assert (found.added, found.removed, found.tightened) == ((), (), ("Fact.accent",))
    assert found.notes == ("MOSS left the palette",) and found.releases == {2: "0.2.0"}
    assert snapshots.changes(root, "expert", 2, 2).releases == {}
    assert snapshots.changes(root, "expert", 0, 3).releases == {1: "0.1.0", 2: "0.2.0"}  # 3 is not a version yet
    assert snapshots.changes(root, "nothing", 1, 2).tightened == ()
    assert snapshots.releases(root) == ["0.1.0", "0.2.0"] and snapshots.releases(None) == []


def test_a_base_kinds_migrations_run_at_the_dependents_matching_boundary():
    from acme_sheet import dist

    from texpkg import Migrated, migration
    from texpkg._internal.adopt import _kind_migrations

    moves = [migration(to=n)(lambda state: Migrated(state)) for n in (2, 3, 4, 5)]
    kind = dataclasses.replace(dist.kinds[0], migrations=tuple(moves))
    by_boundary = {b: [m.to for m in _kind_migrations(kind, b, {1: 1, 2: 3, 3: 5})] for b in (2, 3)}
    assert by_boundary == {2: [2, 3], 3: [4, 5]}
    assert [m.to for m in _kind_migrations(kind, 3, None)] == [3]


def test_a_base_that_no_longer_supports_the_interface_a_package_relies_on_is_refused(brand, tmp_path, monkeypatch):
    import zipfile

    set_version(brand, "0.1.0")
    release(brand)
    first = tmp_path / "site-1"
    zipfile.ZipFile(build(brand, tmp_path / "one")).extractall(first)

    edit(brand, "src/acme_brand/model.py", "    meaning: Text\n", "    gloss: Text\n")
    edit(brand, "src/acme_brand/__init__.py", "meaning=", "gloss=")  # the keyword is the name now
    edit(brand, "src/acme_brand/__init__.py", "meaning=", "gloss=")
    edit(brand, "src/acme_brand/model.py", r"#word}\quad #meaning\par", r"#word}\quad #gloss\par")
    contracts(brand)
    classify_output(brand, "current")
    contracts(brand)
    assert versions(brand).interface == Triple(2, 0, 0)
    release(brand)
    set_version(brand, "0.2.0")
    second = tmp_path / "site-2"
    zipfile.ZipFile(build(brand, tmp_path / "two")).extractall(second)

    deck = projects.author_project(tmp_path / "deck", declaration="acme_deck", project="acme-deck-tex")
    set_version(deck, "0.1.0")
    monkeypatch.syspath_prepend(str(first))
    assert contracts(deck).exit_code == 0
    assert (versions(deck).base_interface, versions(deck).base_data) == (1, {1: 1})
    assert release(deck).release == "0.1.0"
    build(deck, tmp_path / "deck-one")  # built on the first base
    sys.path.remove(str(first))
    for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(second))
    with pytest.raises(errors.DeclarationError) as raised:
        build(deck, tmp_path / "deck-two")
    assert raised.value.code == "TP-C006" and "interface 1" in str(raised.value)


# -- the command -----------------------------------------------------------------------------------------------------


def test_the_command_needs_a_pointer_to_a_distribution(brand):
    pyproject = brand / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("acme_brand:dist", "acme_brand:Deck"))
    assert contracts(brand).exit_code == 2
    pyproject.write_text(pyproject.read_text().replace('distribution = "acme_brand:Deck"', ""))
    assert contracts(brand).exit_code == 2


def test_the_command_reports_a_refusal_with_its_code_and_hint(brand, monkeypatch):
    def refuse(root):  # noqa: ANN001, ANN202
        raise errors.DeclarationError("no", code="TP-C002", hint="because")

    monkeypatch.setattr(snapshot, "freeze", refuse)
    result = contracts(brand, "--freeze")
    assert result.exit_code == 1 and "error TP-C002: no" in result.output and "hint: because" in result.output
