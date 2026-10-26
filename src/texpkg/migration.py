"""Migrations: one API whoever writes them (V32): the build derives some, a kind lists some, a consumer passes some.

A migration is a function over plain data, from the stored state of `data` version `to - 1` to `to` (V28); what it
cannot place it leaves unresolved, never guessed (V15).
"""

import dataclasses
import enum
from collections.abc import Callable, Sequence
from typing import Any

from .errors import DeclarationError


@enum.unique
class DefaultChange(enum.StrEnum):
    """What a consumer does when a release changes a default that a stored document still marks as default (V23). A
    `StrEnum`, so one package's value equals another's (B11)."""

    FOLLOW = "follow"  # the marked value moves to the new default
    FREEZE = "freeze"  # it keeps the old value, which stops being marked
    ASK = "ask"  # adoption aborts with each changed default as an unresolved item


@dataclasses.dataclass(frozen=True)
class Unresolved:
    """What no migration placed: the data path, why, and the old value. texpkg fills `schema` (the new schema at that
    path) and `boundary` (`"4 -> 5"`) when it reports."""

    path: str
    reason: str
    value: object = None
    schema: dict[str, Any] = dataclasses.field(default_factory=dict[str, Any])
    boundary: str = ""


@dataclasses.dataclass(frozen=True)
class Migrated:
    """A migration's result: the state, and what it left unresolved."""

    state: dict[str, Any]
    unresolved: Sequence[Unresolved] = ()


type MigrationFunction = Callable[[dict[str, Any]], Migrated]


@dataclasses.dataclass(frozen=True)
class Migration:
    """A function from `data` version `to - 1` to `to`; make one with `@migration(to=N)`."""

    to: int
    function: MigrationFunction

    def __post_init__(self) -> None:
        if self.to < 2:
            raise DeclarationError(
                f"migration(to={self.to}): `data` version 1 is the first, so a migration goes to 2 or later",
                code="TP-M001",
                hint="@migration(to=N) migrates from `data` version N - 1 to N",
            )

    def __call__(self, state: dict[str, Any]) -> Migrated:
        return self.function(state)


def migration(*, to: int) -> Callable[[MigrationFunction], Migration]:
    """`@migration(to=5)`: from `data` version 4 to 5."""

    def wrap(function: MigrationFunction) -> Migration:
        return Migration(to, function)

    return wrap
