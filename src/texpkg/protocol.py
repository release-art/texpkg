"""The fixed surface of a built package (P6), as protocols: the build generates a module to satisfy them and checks it
does, and a consumer's type checker reads the generated module's own types."""

from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

from .contracts import Changes, Contracts


@runtime_checkable
class KindModule(Protocol):
    """`acme_tex.kinds.expert`: besides these, the kind's own classes (P24)."""

    @property
    def NAME(self) -> str: ...  # noqa: N802
    def schema(self, mode: Literal["validation", "serialization"] = "validation") -> dict[str, Any]: ...
    def example(self) -> Any: ...  # noqa: ANN401  # the kind's root class
    def variants(self) -> tuple[str, ...]: ...
    def changes(self, old: int, new: int) -> Changes: ...


@runtime_checkable
class KindsModule(Protocol):
    """`acme_tex.kinds`."""

    def names(self) -> tuple[str, ...]: ...
    def modules(self) -> Mapping[str, KindModule]: ...


@runtime_checkable
class PackageModule(Protocol):
    """`acme_tex`."""

    @property
    def __version__(self) -> str: ...
    @property
    def CONTRACTS(self) -> Contracts: ...  # noqa: N802
    @property
    def kinds(self) -> KindsModule: ...
