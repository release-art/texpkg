"""What the build refuses (B4): a defect fails `pdm build`, not a consumer's import."""

import pathlib
from types import ModuleType

from texpkg._internal import payload
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError
from texpkg.protocol import KindModule, KindsModule, PackageModule


def declaration_directory(dist: Distribution) -> pathlib.Path:
    """The directory of the declaration package, which the build copies whole (P22)."""
    path = pathlib.Path(str(dist.root))
    if not (path / "__init__.py").is_file():
        raise DeclarationError(
            f"{dist.declared_in}: the declaration must be a package (a directory with an __init__.py)",
            code="TP-B004",
            path=dist.declared_in,
            hint="move the declaration into a package; its assets and templates live beside it",
        )
    return path


def assets_are_there(dist: Distribution) -> None:
    """Every asset of the chain is a file (A3), and no two land on one payload path (P11, `TP-A002`)."""
    if gone := [r.asset.path for r in dist.resolved_assets() if not r.source.is_file()]:
        raise DeclarationError(
            f"missing assets: {', '.join(gone)}",
            code="TP-B005",
            path=gone[0],
            hint=f"they are read from the package {dist.declared_in}",
        )
    payload.build({f"{d.package.name}.sty": "" for d in dist.chain()}, tuple(dist.resolved_assets()), dist.layout)


def module_satisfies_the_protocols(module: ModuleType) -> None:
    """The generated module has the fixed surface (P6)."""
    name = module.__name__
    candidate: object = module
    kinds: object = getattr(module, "kinds", None)
    problems = [] if isinstance(candidate, PackageModule) else ["the package module"]
    if isinstance(kinds, KindsModule):
        problems += [
            f"kinds.{n}" for n, m in dict[str, object](kinds.modules()).items() if not isinstance(m, KindModule)
        ]
    else:
        problems.append("kinds")
    if problems:
        raise DeclarationError(
            f"the generated module {name} does not satisfy the protocol: {', '.join(problems)}",
            code="TP-B006",
            path=name,
            hint="this is a texpkg defect: texpkg.protocol lists the surface",
        )
