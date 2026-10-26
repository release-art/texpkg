"""texpkg: TeX packages published as Python packages. The declaration types an author writes."""

from .assets import Asset, Role
from .declaration import Design, Distribution, Kind, Variant
from .migration import DefaultChange, Migrated, Unresolved, migration

__all__ = [
    "Asset",
    "DefaultChange",
    "Design",
    "Distribution",
    "Kind",
    "Migrated",
    "Role",
    "Unresolved",
    "Variant",
    "migration",
]
