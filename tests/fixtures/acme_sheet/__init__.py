"""The datasheet as a texpkg declaration with one migration, written by the kind's author (V6, V32)."""

from pathlib import PurePosixPath
from typing import Any

from texpkg import Distribution, Kind, Migrated, Unresolved, migration

from .model import Heading, Sheet, Standard, Ticks, pkg

KNOWN = {s.value: s.name for s in Standard}


@migration(to=5)
def standards_to_ticks(state: dict[str, Any]) -> Migrated:
    """Release 4 had a row per standard, as text; release 5 ticks the fixed list. A row that names a standard the
    list does not hold cannot be placed: it stays unresolved until a migration of the consumer's places it."""
    rows = [(i, c) for i, c in enumerate(state["content"]) if c["type"] == "Row"]
    met = [KNOWN[c["standard"]] for _, c in rows if c["standard"] in KNOWN]
    unknown = [
        Unresolved(f"/content/{i}", "not in the fixed list of standards", c["standard"])
        for i, c in rows
        if c["standard"] not in KNOWN
    ]
    state["content"] = [*(c for c in state["content"] if c["type"] != "Row"), {"type": "Ticks", "met": met}]
    return Migrated(state, unknown)


def example() -> Sheet:
    return Sheet(Heading(text="Pump"), Ticks(met=(Standard.ISO9001,)))


dist = Distribution(
    name="acme-sheet-tex",
    module="acme_sheet_tex",
    package=pkg,
    kinds=(Kind("datasheet", Sheet, (), example, migrations=(standards_to_ticks,)),),
)

__all__ = ["Heading", "Sheet", "Standard", "Ticks", "dist", "example", "standards_to_ticks"]
