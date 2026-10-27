"""The generator of `acme_series`: Python source for each series in `series.json` (K4). It never imports `acme_series`,
whose `__init__` imports what this writes."""

import json
import pathlib
import string
import textwrap
from typing import Any

_SERIES = string.Template(
    textwrap.dedent(
        r'''
        """The `$name` series: $cards_min to $cards_max cards, $facts_min to $facts_max facts on each."""

        import enum

        from texmodel.components import Command, Environment, Value
        from texmodel.types import Choice, Length, Text

        from ..model import Title, pkg


        @enum.unique
        class ${prefix}Accent(Choice):
            """The accents a fact of the $name series may take."""

        $members


        @pkg.value
        class ${prefix}Gap(Value[Length]):
            """Space under each fact of a $name card."""

            default = Length("$gap")


        @pkg.command
        class ${prefix}Fact(Command):
            """One fact of a $name card."""

            text: Text
            accent: ${prefix}Accent = ${prefix}Accent.$first

            body = r"\par\noindent[#accent] #text\par"


        @pkg.environment
        class ${prefix}Card(Environment):
            """A $name card."""

            begin = r"\begin{minipage}{\linewidth}"
            end = r"\end{minipage}\par\medskip"

            children = [Title, ${prefix}Fact.times($facts_min, $facts_max)]


        @pkg.environment
        class ${prefix}Deck(Environment):
            """A $name deck."""

            begin = r"\begingroup"
            end = r"\endgroup"

            children = [${prefix}Card.times($cards_min, $cards_max)]


        NAME = "$name"
        ROOT = ${prefix}Deck
        SETTABLE = (${prefix}Gap,)
        OPTIONS = ($options)


        def example() -> ${prefix}Deck:
            card = ${prefix}Card(Title(text="Fox"), *[${prefix}Fact(text="Sly") for _ in range($facts_min)])
            return ${prefix}Deck(*[card for _ in range($cards_min)])
        '''
    ).strip()
    + "\n"
)


def _module(series: dict[str, Any]) -> str:
    name = str(series["name"])
    cards, facts, accents, options = (series["cards"], series["facts"], series["accents"], series["options"])
    return _SERIES.substitute(
        name=name,
        prefix=name.capitalize(),
        cards_min=cards[0],
        cards_max=cards[1],
        facts_min=facts[0],
        facts_max=facts[1],
        first=str(accents[0]).upper(),
        gap=series["gap"],
        options="".join(f'"{o}", ' for o in options),
        members="\n".join(f'    {str(a).upper()} = "{a}"' for a in accents),
    )


def sources(root: pathlib.Path) -> dict[str, str]:
    series = sorted(json.loads((root / "series.json").read_text(encoding="utf-8"))["series"], key=lambda s: s["name"])
    names = ", ".join(s["name"] for s in series)
    return {f"_kinds/{s['name']}.py": _module(s) for s in series} | {
        "_kinds/__init__.py": f"from . import {names}\n\nALL = ({names})\n"
    }
