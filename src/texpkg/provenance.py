"""The provenance file: what a document directory was materialised from and when (V2, V34).

`save` writes `<package>-provenance.sty` for every package of the stack, the only payload file that holds a time. A
document can print what it was built from with `\\<prefix>ProvenanceInfo`, and the PDF carries the same text.
"""

import dataclasses
import datetime
import pathlib
from typing import TYPE_CHECKING

from ._internal import directory, provenance_tex
from .errors import DeclarationError

if TYPE_CHECKING:
    from ._internal.release import Release


@dataclasses.dataclass(frozen=True)
class Provenance:
    stamp: str
    time: str


def stamp_of(stamp: str | None, release: "Release") -> str:
    """The stamp a save or a check uses: the consumer's (V4, e.g. `1.2.0-3f9c2ab-dirty`), else the release's version."""
    chosen = release.version if stamp is None else stamp
    if not provenance_tex.STAMP.fullmatch(chosen):
        raise DeclarationError(
            f"stamp {chosen!r}: letters, digits and . + : / @ - and space only",
            code="TP-D006",
            hint="it is printed on the page and written into the PDF's metadata, so it has to be the same text in both",
        )
    return chosen


def time_of(now: datetime.datetime | None) -> str:
    """`now` in UTC, or the clock's. This is the one place texpkg reads the clock (N4): a caller that wants the
    time pinned passes `now`."""
    moment = now or datetime.datetime.now(datetime.UTC)
    if moment.tzinfo is not None:
        moment = moment.astimezone(datetime.UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def files(release: "Release", stamp: str, time: str) -> dict[str, str]:
    """The provenance file of every package in the stack, by file name."""
    return {
        provenance_tex.file_name(r.dist.package.name): provenance_tex.companion(
            r.dist.package.prefix, r.dist.package.name, r.version, stamp, time
        )
        for r in release.releases()
    }


def saved(root: pathlib.Path, release: "Release") -> Provenance | None:
    """The stamp and time of the top package's provenance file in `root`; `None` if it is not there."""
    text = directory.read(root, release.layout_path(provenance_tex.file_name(release.dist.package.name)))
    if text is None:
        return None
    return Provenance(*provenance_tex.read(text, release.dist.package.prefix))
