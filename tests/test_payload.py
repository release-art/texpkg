"""Assets, layouts and payloads (A1-A6, P10, P11)."""

import io
import pathlib
import zipfile
from importlib.resources.abc import Traversable

import pytest
from hypothesis import (
    given,
    strategies as st,
)
from texmodel.preamble import GraphicsPath, InputPath, PreambleSlots

from texpkg._internal import payload
from texpkg.assets import Asset, Resolved, Role
from texpkg.errors import DeclarationError, PayloadError
from texpkg.layout import Project

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "acme_brand" / "assets"
POSIX = pathlib.PurePosixPath
PROJECT = Project(POSIX("res/texpkg"))


def resolved(path: str, role: Role, kinds: tuple[str, ...] = (), source: Traversable | None = None) -> Resolved:
    return Resolved(Asset(path, role, "why", kinds), source or FIXTURE / pathlib.Path(path).name)


@pytest.mark.parametrize(
    ("role", "placed"),
    [
        (Role.PACKAGE, "res/texpkg/x.sty"),
        (Role.GRAPHIC, "res/texpkg/x.sty"),
        (Role.FONT, "x.sty"),
        (Role.BY_PATH, "sub/x.sty"),
        (Role.NOTE, "res/texpkg/x.sty"),
    ],
)
def test_each_role_has_a_place_in_the_layout(role, placed):
    assert PROJECT.place(role, POSIX("sub/x.sty")) == POSIX(placed)


def test_the_layout_gives_the_preamble_lines_that_find_its_files():
    assert PROJECT.preamble(graphics=False) == PreambleSlots(before_package=(InputPath("res/texpkg/"),))
    assert PROJECT.preamble(graphics=True) == PreambleSlots(
        before_package=(InputPath("res/texpkg/"),), after_package=(GraphicsPath("res/texpkg/"),)
    )
    assert PROJECT.owned() == ("res/texpkg/**/*",)


@pytest.mark.parametrize("bad", ["", "/abs", "../up", "a/../b", "a\\b"])
def test_an_asset_path_stays_inside_the_package(bad):
    with pytest.raises(DeclarationError) as raised:
        Asset(bad, Role.NOTE, "x")
    assert raised.value.code == "TP-A001"


@pytest.mark.parametrize("bad", ["", "/abs", "../up", "."])
def test_a_project_directory_stays_inside_the_document(bad):
    with pytest.raises(DeclarationError) as raised:
        Project(POSIX(bad))
    assert raised.value.code == "TP-A003"


def test_an_asset_names_the_kinds_that_need_it():
    everywhere, only = Asset("a", Role.NOTE, "x"), Asset("b", Role.NOTE, "x", ("expert",))
    kinds = [("expert",), ("other",), ("other", "expert"), None]
    assert [a.needed_by(k) for a in (everywhere, only) for k in kinds] == [True] * 4 + [True, False, True, True]


def test_a_payload_leaves_out_the_assets_of_other_kinds():
    assets = [resolved("lockup.pdf", Role.GRAPHIC, ("expert",)), resolved("NOTICE.txt", Role.NOTE)]
    names = lambda kind: sorted(str(p.dest) for p in payload.build({}, assets, PROJECT, kind).assets)  # noqa: E731
    assert names(("expert",)) == ["res/texpkg/NOTICE.txt", "res/texpkg/lockup.pdf"]
    assert names(("vocab",)) == ["res/texpkg/NOTICE.txt"]
    assert names(None) == names(("expert",))


def test_the_same_file_twice_is_one_and_two_different_files_on_one_path_are_refused(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "n.txt").write_text("one")
    (tmp_path / "b" / "n.txt").write_text("one")
    same = [resolved("a/n.txt", Role.NOTE, source=tmp_path / "a" / "n.txt"),
            resolved("b/n.txt", Role.NOTE, source=tmp_path / "b" / "n.txt")]  # fmt: skip
    assert len(payload.build({}, same, PROJECT).assets) == 1
    (tmp_path / "b" / "n.txt").write_text("two")
    with pytest.raises(DeclarationError) as raised:
        payload.build({}, same, PROJECT)
    assert raised.value.code == "TP-A002" and "a/n.txt" in str(raised.value)


def test_a_generated_sty_cannot_share_a_path_with_an_asset():
    with pytest.raises(DeclarationError) as raised:
        payload.build({"NOTICE.txt": "x"}, [resolved("NOTICE.txt", Role.NOTE)], PROJECT)
    assert raised.value.code == "TP-A002"


@given(
    st.lists(
        st.tuples(
            st.sampled_from(sorted(Role)), st.sampled_from(["a/x", "b/x", "x", "a/y", "c/d/y"]), st.binary(max_size=2)
        ),
        max_size=8,
    ),
    st.just(PROJECT),
)
def test_placement_is_injective_or_raises(entries, layout):
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        for i, (_, _, data) in enumerate(entries):
            z.writestr(f"f{i}", data)
    root = zipfile.Path(zipfile.ZipFile(zipped))
    assets = [resolved(path, role, source=root / f"f{i}") for i, (role, path, _) in enumerate(entries)]
    try:
        built = payload.build({}, assets, layout)
    except DeclarationError as exc:
        assert exc.code == "TP-A002"
    else:
        dests = [p.dest for p in built.assets]
        assert len(set(dests)) == len(dests)


def test_a_payload_is_written_whole_and_only_what_changed(tmp_path):
    assets = [resolved("lmroman10-regular.otf", Role.FONT), resolved("lockup.pdf", Role.GRAPHIC)]
    built = payload.build({"acme.sty": "\\ProvidesPackage{acme}\n"}, assets, PROJECT)
    written = built.write(tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in written) == [
        "lmroman10-regular.otf", "res/texpkg/acme.sty", "res/texpkg/lockup.pdf",
    ]  # fmt: skip
    assert built.write(tmp_path) == ()
    (tmp_path / "res/texpkg/acme.sty").write_text("edited")
    assert [p.name for p in built.write(tmp_path)] == ["acme.sty"]


def test_an_incomplete_payload_writes_nothing(tmp_path):
    assets = [resolved("lockup.pdf", Role.GRAPHIC), resolved("gone.pdf", Role.GRAPHIC)]
    built = payload.build({"acme.sty": "x"}, assets, PROJECT)
    with pytest.raises(PayloadError) as raised:
        built.write(tmp_path / "out")
    assert raised.value.code == "TP-A004" and "gone.pdf" in str(raised.value)
    assert not (tmp_path / "out").exists()
    with pytest.raises(PayloadError):
        built.check(tmp_path, ())


def test_check_reports_unchanged_changed_missing_and_extra(tmp_path):
    assets = [resolved("lmroman10-regular.otf", Role.FONT), resolved("lockup.pdf", Role.GRAPHIC)]
    built = payload.build({"acme.sty": "x"}, assets, PROJECT)
    built.write(tmp_path)
    assert built.check(tmp_path, PROJECT.owned()).ok
    (tmp_path / "res/texpkg/acme.sty").write_text("y")
    (tmp_path / "res/texpkg/lockup.pdf").unlink()
    (tmp_path / "res/texpkg/retired.sty").write_text("old")
    report = built.check(tmp_path, PROJECT.owned())
    assert (report.stale, report.missing, report.orphaned) == (
        ("res/texpkg/acme.sty",), ("res/texpkg/lockup.pdf",), ("res/texpkg/retired.sty",),
    )  # fmt: skip


def test_a_payload_from_a_zipped_package_is_written(tmp_path):
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("assets/NOTICE.txt", "notice")
    root = zipfile.Path(zipfile.ZipFile(zipped))
    built = payload.build({}, [resolved("assets/NOTICE.txt", Role.NOTE, source=root / "assets/NOTICE.txt")], PROJECT)
    built.write(tmp_path)
    assert (tmp_path / "res/texpkg/NOTICE.txt").read_text() == "notice"
