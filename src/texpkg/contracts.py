"""Contract versions (V10): what a consumer relies on, versioned on its own, libtool's `current:revision:age`."""

import dataclasses
from collections.abc import Mapping


@dataclasses.dataclass(frozen=True)
class Triple:
    """`current` numbers the contract, `revision` counts implementation changes within it, `age` how many earlier
    `current`s are still supported (`current - age` ... `current`)."""

    current: int
    revision: int = 0
    age: int = 0


@dataclasses.dataclass(frozen=True)
class Pair:
    """`output` has no age: `current` when the appearance changed, `revision` when bytes changed and nothing visible
    should have."""

    current: int
    revision: int = 0


@dataclasses.dataclass(frozen=True)
class Contracts:
    """`data`: what a stored document may say. `interface`: the public TeX names and signatures. `output`: what the same
    data renders to."""

    data: Triple = Triple(1)
    interface: Triple = Triple(1)
    output: Pair = Pair(1)
    base_data: tuple[tuple[int, int], ...] = ()  # this package's `data` version -> the base's it corresponds to (P30)


@dataclasses.dataclass(frozen=True)
class Changes:
    """What changed between two `data` versions of a kind (V33): fields added, removed and tightened (by data path), the
    author's notes, and the release that introduced each `data` version crossed."""

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    tightened: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    releases: Mapping[int, str] = dataclasses.field(default_factory=dict[int, str])
