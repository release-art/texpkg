"""`texpkg-build` (V12, V37). The only module of the build that prints."""

import importlib
import pathlib
import tomllib
from typing import Annotated

import typer

from texpkg.declaration import Distribution
from texpkg.errors import TexpkgError

from ._internal import snapshot
from ._internal.isolate import author_source
from .testing import load_declaration

app = typer.Typer(pretty_exceptions_enable=False, help="Build tools for texpkg packages.", no_args_is_help=True)


def _project(root: pathlib.Path) -> tuple[str, pathlib.Path]:
    """The pointer in `[tool.texpkg] distribution` and the directory the project's source is in."""
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pointer = str(config.get("tool", {}).get("texpkg", {}).get("distribution", ""))
    if not all(pointer.partition(":")[::2]):
        raise typer.BadParameter(f"{root / 'pyproject.toml'}: [tool.texpkg] distribution is not module:attribute")
    return pointer, root / config.get("tool", {}).get("pdm", {}).get("build", {}).get("package-dir", ".")


@app.callback()
def main() -> None:
    """Build tools for texpkg packages."""


@app.command()
def contracts(
    root: Annotated[pathlib.Path, typer.Option(help="The project directory.")] = pathlib.Path(),
    freeze: Annotated[bool, typer.Option(help="Freeze contracts/next as contracts/<release>.")] = False,
    first: Annotated[str, typer.Option(help="The release number of a first snapshot.")] = "0.1.0",
) -> None:
    """Write contracts/next: the snapshot of the declaration and the versions it implies against the newest frozen
    release. Review the files; with --freeze, keep them as the release."""
    root = root.resolve()
    pointer, source = _project(root)
    module, _, attr = pointer.partition(":")
    try:
        with author_source(source) as isolation:
            isolation.forget(module.split(".")[0])
            dist = getattr(importlib.import_module(module), attr)
            if not isinstance(dist, Distribution):
                raise typer.BadParameter(f"{pointer} is not a Distribution")
            isolation.forget(dist.module)
            for base in dist.chain()[1:]:
                isolation.drop(base.module)
            release = load_declaration(pointer, version="0.0.0")._bound.RELEASE  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
            proposal = snapshot.propose(
                root,
                dist,
                release,  # pyright: ignore[reportUnknownArgumentType]
                snapshot.sty_of(dist),
                first=first,
                base_current=snapshot.base_current(dist),
            )
        snapshot.write_next(root, proposal.files)
        for label, found in (("data", proposal.data), ("interface", proposal.interface)):
            for change in found:
                typer.echo(f"{label}: {change.level.name.lower()}: {change.where}: {change.what}")
        for name in proposal.output:
            typer.echo(f"output: changed: {name}")
        for name in proposal.not_compared:
            typer.echo(f"output: not compared: {name} (its example data no longer loads)")
        v = proposal.versions
        typer.echo(
            f"release {v.release}: data {v.data.current}:{v.data.revision}:{v.data.age} "
            f"interface {v.interface.current}:{v.interface.revision}:{v.interface.age} "
            f"output {v.output.current}:{v.output.revision}"
        )
        if proposal.output and not v.output_change:
            typer.echo('output changed: say how in contracts/next/versions.toml, change = "current" or "revision"')
        if freeze:
            typer.echo(f"frozen: {snapshot.freeze(root)}")
    except TexpkgError as exc:
        typer.echo(f"error {exc.code}: {exc}" + (f"\n  hint: {exc.hint}" if exc.hint else ""), err=True)
        raise typer.Exit(1) from exc
