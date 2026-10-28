"""The constants a package publishes to its consumers (P31): declared, re-exported, in the interface contract."""

import dataclasses
import importlib
import sys
import types

import pytest

from texpkg._internal import classify
from texpkg._internal.classify import Level
from texpkg.errors import DeclarationError
from texpkg_build._internal import generate, snapshot

from .test_migration import sheet  # noqa: F401


def test_the_generated_module_republishes_the_constants_of_the_declared_module(sheet):  # noqa: ANN001, ANN201, F811
    acme_sheet_tex = importlib.import_module("acme_sheet_tex")
    public = importlib.import_module("acme_sheet_tex.public")

    assert public.__all__ == ["DEFAULT_FONT", "MAX_TICKS", "STANDARD_NAMES"]
    assert (public.MAX_TICKS, public.STANDARD_NAMES, public.DEFAULT_FONT) == (3, ("ISO9001", "ISO14001"), "Acme Sans")
    assert "public" in acme_sheet_tex.__all__


def test_a_distribution_without_public_has_none(acme_brand_tex):  # noqa: ANN001, ANN201
    assert not hasattr(acme_brand_tex, "public") and "public" not in acme_brand_tex.__all__
    assert "public" not in snapshot.interface_of(acme_brand_tex.dist)


def test_the_interface_snapshot_holds_the_values():
    from acme_sheet import dist

    assert snapshot.interface_of(dist)["public"] == generate.public_values(dist)
    assert generate.public_values(dist)["STANDARD_NAMES"] == ("ISO9001", "ISO14001")


def test_public_must_be_a_module_of_the_declaring_package():
    from acme_sheet import dist

    with pytest.raises(DeclarationError) as raised:
        dataclasses.replace(dist, public="elsewhere.consts")
    assert raised.value.code == "TP-K022"


def module(monkeypatch, name, **attrs):  # noqa: ANN001, ANN201
    mod = types.ModuleType(name)
    vars(mod).update(attrs)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.mark.parametrize(
    ("attrs", "text"),
    [
        ({"A": 1}, "no __all__"),
        ({"__all__": ["A"]}, "does not define"),
        ({"__all__": ["A"], "A": object()}, "not JSON-like"),
        ({"__all__": ["A"], "A": {1: "x"}}, "not JSON-like"),
        ({"__all__": ["A"], "A": ["ok", (1, {"k": None}), 2.5, True]}, None),
    ],
)
def test_what_may_be_published(monkeypatch, attrs, text):  # noqa: ANN001, ANN201
    from acme_sheet import dist

    module(monkeypatch, "acme_sheet.fake", **attrs)
    fake = dataclasses.replace(dist, public="acme_sheet.fake")
    if text is None:
        assert list(generate.public_values(fake)) == ["A"]
        return
    with pytest.raises(DeclarationError) as raised:
        generate.public_values(fake)
    assert raised.value.code == "TP-B014" and text in str(raised.value)


def test_an_enum_member_is_not_json_like(monkeypatch):  # noqa: ANN001, ANN201
    import enum

    from acme_sheet import dist

    class Color(enum.StrEnum):
        RED = "red"

    module(monkeypatch, "acme_sheet.fake", __all__=["A"], A=Color.RED)
    with pytest.raises(DeclarationError, match="Color"):
        generate.public_values(dataclasses.replace(dist, public="acme_sheet.fake"))


def test_the_levels_of_a_change_to_the_published_constants():
    def levels(old, new):  # noqa: ANN001, ANN202
        return [(c.where, c.level) for c in classify.interface_changes({"public": old}, {"public": new})]

    assert levels({"A": 1}, {"A": 1}) == []
    assert levels({"A": 1, "B": 2}, {"A": 1}) == [("public B", Level.BREAKING)]
    assert levels({"A": 1}, {"A": 1, "B": 2}) == [("public B", Level.COMPATIBLE)]
    assert levels({"A": 1}, {"A": 2}) == [("public A", Level.REVISION)]
    assert levels({"A": 1}, {"A": "1"}) == [("public A", Level.BREAKING)]
    assert levels({"A": 1}, {"A": True}) == [("public A", Level.BREAKING)]
    assert classify.interface_changes({"public": {"A": 1}}, {}) == [
        classify.Change(Level.BREAKING, "public A", "removed")
    ]
    assert classify.interface_changes({}, {}) == []
