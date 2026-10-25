"""A payload: the rendered `.sty` files and the assets a document needs, placed by a layout (A3, A6, P10, P11).

It reads assets with `importlib.resources`, so a wheel, a zip and an editable install behave alike (P5); a file that is
not a real one on disk (a zipped package) is copied out for as long as the write takes.
"""

import contextlib
import dataclasses
import importlib.resources
import importlib.resources.abc
import pathlib
from collections.abc import Collection, Mapping, Sequence

from texmodel import bundle, drift

from ..assets import Resolved, Role
from ..errors import DeclarationError, PayloadError
from ..layout import Layout


@dataclasses.dataclass(frozen=True)
class Placed:
    """One asset at its place under the document directory."""

    source: importlib.resources.abc.Traversable
    dest: pathlib.PurePosixPath
    why: str
    origin: str  # the asset's declared path, for messages


@dataclasses.dataclass(frozen=True)
class Payload:
    generated: Mapping[str, str]  # dest -> text: the rendered `.sty` files
    assets: tuple[Placed, ...]

    def absent(self) -> tuple[Placed, ...]:
        return tuple(p for p in self.assets if not p.source.is_file())

    def complete(self) -> None:
        """Raise `PayloadError` unless every source file is there (A3)."""
        if absent := self.absent():
            names = ", ".join(str(p.dest) for p in absent)
            raise PayloadError(
                f"payload incomplete, missing sources for: {names}",
                code="TP-A004",
                hint="the package was built without them, or its files were removed",
            )

    def expected(self) -> dict[str, str | bytes]:
        """Every file of the payload by destination, as bytes or text (A4 compares content, never time)."""
        self.complete()
        return {str(p.dest): p.source.read_bytes() for p in self.assets} | dict(self.generated)

    def check(self, root: pathlib.Path, owned: Sequence[str]) -> drift.Drift:
        """What `root` holds against the payload: `stale`, `missing`, and `orphaned` (files under `owned` globs that no
        payload file explains)."""
        return drift.check_drift(self.expected(), root, owned)

    def write(self, root: pathlib.Path) -> tuple[pathlib.Path, ...]:
        """The files `root` does not hold already, byte for byte. Refuses the whole payload if one source is absent
        (A3) and removes nothing."""
        self.complete()
        with contextlib.ExitStack() as stack:
            items = [
                bundle.Item(
                    stack.enter_context(importlib.resources.as_file(p.source)), pathlib.Path(*p.dest.parts), p.why
                )
                for p in self.assets
            ]
            changed = {
                dest: text
                for dest, text in self.generated.items()
                if not (root / dest).is_file() or (root / dest).read_text(encoding="utf-8") != text
            }
            return bundle.write(bundle.stale(items, root), root, changed)


def build(
    sty: Mapping[str, str], assets: Sequence[Resolved], layout: Layout, kinds: Collection[str] | None = None
) -> Payload:
    """The payload of a document of `kinds` (a kind and the base kind a profile kind expands to; `None`: every kind, for
    an export) in `layout`. An asset naming other kinds is left out
    (A6). The same file twice is one (P10); two different files on one path are an error (P11)."""
    placed: dict[pathlib.PurePosixPath, Placed] = {}
    for resolved in assets:
        asset = resolved.asset
        if not asset.needed_by(kinds):
            continue
        dest = layout.place(asset.role, pathlib.PurePosixPath(asset.path))
        earlier = placed.get(dest)
        if earlier is not None:
            if earlier.source.read_bytes() != resolved.source.read_bytes():
                raise DeclarationError(
                    f"two different files would be written to {dest}: {earlier.origin!r} and {asset.path!r}",
                    code="TP-A002",
                    path=asset.path,
                    hint="rename one, or give one role/layout another place",
                )
            continue
        placed[dest] = Placed(resolved.source, dest, asset.why, asset.path)
    generated = {str(layout.place(Role.PACKAGE, pathlib.PurePosixPath(name))): text for name, text in sty.items()}
    if clash := sorted(set(generated) & {str(d) for d in placed}):
        raise DeclarationError(
            f"{clash[0]} is both a generated .sty and an asset",
            code="TP-A002",
            path=clash[0],
            hint="a package's name is the name of its rendered .sty",
        )
    return Payload(generated, tuple(placed.values()))
