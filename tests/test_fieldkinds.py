"""What an argument holds, as `raw_holes` and the `interface` snapshot read it from texmodel's types (P25, V10)."""

import enum

from texmodel.components import Command
from texmodel.keys import PGFKEYS
from texmodel.keyvals import KeyVals
from texmodel.package import Package
from texmodel.types import Choice, Length, Raw, Text

from texpkg._internal import fieldkinds
from texpkg.declaration import raw_holes

pkg = Package("probe", prefix="pb")


@enum.unique
class Shade(Choice):
    DARK = "dark"


class Options(KeyVals, rules=PGFKEYS):
    width: Length | None = None


@pkg.command
class Probe(Command):
    """Every shape of field."""

    text: Text
    size: Length
    count: int
    shade: Shade
    options: Options
    tex: Raw
    tex_list: list[Raw]
    tex_pair: tuple[int, Raw]
    tex_or_size: Raw | Length
    sizes: list[Length]
    pair: tuple[int, Length]

    body = "#text#size#count#shade#options#tex#tex_list#tex_pair#tex_or_size#sizes#pair"


def test_an_argument_is_labelled_by_what_it_holds():
    labels = {a.name: fieldkinds.label(a.type) for a in Probe.__tm_args__}
    assert labels == {
        "text": "Text",
        "size": "Length",
        "count": "int",
        "shade": "Choice Shade",
        "options": "KeyVals",
        "tex": "Raw",
        "tex_list": "list",
        "tex_pair": "tuple",
        "tex_or_size": "union",
        "sizes": "list",
        "pair": "tuple",
    }


def test_raw_is_found_in_a_list_a_tuple_and_a_union():
    assert raw_holes(Probe) == ("Probe.tex", "Probe.tex_list", "Probe.tex_pair", "Probe.tex_or_size")
