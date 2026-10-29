"""The versions file of a contract snapshot (V36): the triples, the release they are for, the author's statements
and the version maps. A snapshot ships in the wheel, so the run time reads it too."""

import dataclasses
import json
import tomllib
from collections.abc import Mapping
from typing import Any

from ..contracts import Contracts, Pair, Triple


@dataclasses.dataclass(frozen=True)
class Versions:
    """The versions file (V36): the triples, the release they are for, the author's statements and the version maps."""

    release: str
    data: Triple = Triple(1)
    interface: Triple = Triple(1)
    output: Pair = Pair(1)
    output_change: str = ""  # the author's `current` or `revision` for an output change (V12)
    notes: Mapping[int, str] = dataclasses.field(default_factory=dict[int, str])  # one line per `data` version (V33)
    releases: Mapping[int, str] = dataclasses.field(default_factory=dict[int, str])  # the release of each (V33)
    base_data: Mapping[int, int] = dataclasses.field(default_factory=dict[int, int])  # own `data` -> the base's (P30)
    base_interface: int = 0  # the base `interface` current relied on (V17); 0 without a base

    def contracts(self) -> Contracts:
        return Contracts(
            self.data, self.interface, self.output, tuple(sorted(self.base_data.items())), self.base_interface
        )

    def to_text(self) -> str:
        def table(name: str, values: Mapping[int, Any]) -> str:
            return f"\n[{name}]\n" + "".join(f'"{k}" = {json.dumps(v)}\n' for k, v in sorted(values.items()))

        return (
            f'release = "{self.release}"\n'
            f"\n[data]\ncurrent = {self.data.current}\nrevision = {self.data.revision}\nage = {self.data.age}\n"
            f"\n[interface]\ncurrent = {self.interface.current}\nrevision = {self.interface.revision}\n"
            f"age = {self.interface.age}\n"
            f"\n[output]\ncurrent = {self.output.current}\nrevision = {self.output.revision}\n"
            f'change = "{self.output_change}"\n'
            + table("notes", self.notes)
            + table("releases", self.releases)
            + f"\n[base]\ninterface = {self.base_interface}\n"
            + table("base.data", self.base_data)
        )

    @classmethod
    def parse(cls, text: str) -> "Versions":
        found = tomllib.loads(text)
        data, interface, output = found["data"], found["interface"], found["output"]
        return cls(
            found["release"],
            Triple(data["current"], data["revision"], data["age"]),
            Triple(interface["current"], interface["revision"], interface["age"]),
            Pair(output["current"], output["revision"]),
            output.get("change", ""),
            {int(k): v for k, v in found.get("notes", {}).items()},
            {int(k): v for k, v in found.get("releases", {}).items()},
            {int(k): v for k, v in found.get("base", {}).get("data", {}).items()},
            found.get("base", {}).get("interface", 0),
        )
