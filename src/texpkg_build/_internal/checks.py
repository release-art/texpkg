"""What the build refuses (B4): a defect fails `pdm build`, not a consumer's import."""

import importlib
import pathlib
import re
from types import ModuleType
from typing import Any

from texmodel.components import control_name
from texmodel.errors import DeclarationError as TexmodelDeclarationError

from texpkg._internal import classify, payload
from texpkg._internal.release import Release
from texpkg.contracts import Contracts
from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError
from texpkg.protocol import KindModule, KindsModule, PackageModule

from . import snapshot


def declaration_directory(dist: Distribution) -> pathlib.Path:
    """The directory of the declaration package, which the build copies whole (P22)."""
    path = pathlib.Path(str(dist.files))
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


def tex_names_are_unique(dist: Distribution) -> None:
    """No two packages of the chain define one control sequence (P11): the later `.sty` would redefine the earlier."""
    seen: dict[str, str] = {}
    for member in reversed(dist.chain()):
        for cls in member.package.registered:
            try:
                name = control_name(cls)
            except TexmodelDeclarationError:
                continue  # a colour has no control sequence
            if seen.setdefault(name, member.name) != member.name:
                raise DeclarationError(
                    f"\\{name} is defined by {seen[name]} and by {member.name}",
                    code="TP-B009",
                    path=name,
                    hint="a package built on another must not reuse its names: choose another prefix or name",
                )


def design_is_valid(dist: Distribution) -> None:
    """The embedded data validates against its model (L1)."""
    if dist.design is None:
        return
    try:
        dist.design.load(dist.files)
    except (OSError, ValueError) as exc:  # a missing file, bad JSON and pydantic's ValidationError are all of these
        raise DeclarationError(
            f"{dist.name}: the design data {dist.design.path} is not a valid {dist.design.model.__name__}: {exc}",
            code="TP-B010",
            path=dist.design.path,
            hint="fix the file, or the model it is validated against",
        ) from exc


_RELEASE = re.compile(r"\d+\.\d+\.\d+")


def contract_gate(
    root: pathlib.Path, dist: Distribution, release: Release, version: str
) -> tuple[Contracts, list[pathlib.Path]]:
    """The contract versions this build carries, and the frozen snapshots that ship (V12, V13, V17, V37). Without a
    `contracts` directory a package has the first versions and ships none. A development build is held to `next`: it
    must be current and an output change must be classified. A release build must have its own newest frozen
    directory, and its number must not understate the contracts."""
    if not (root / snapshot.CONTRACTS).is_dir():
        return Contracts(), []
    held = snapshot.frozen(root)
    current = snapshot.base_current(dist)
    proposal = snapshot.propose(root, dist, release, snapshot.sty_of(dist), base_current=current)
    if _RELEASE.fullmatch(version):
        if not held or held[-1].name != version:
            raise DeclarationError(
                f"release {version}: contracts/{version} is not the newest frozen snapshot",
                code="TP-C003",
                hint="freeze it first: texpkg-build contracts --freeze",
            )
        required = snapshot.required_for(held[-2] if len(held) > 1 else None, held[-1])
        if classify.parse_version(version) < classify.parse_version(required):
            raise DeclarationError(
                f"release {version} understates the contracts: they need {required}",
                code="TP-C004",
                hint=f"tag {required} or later",
            )
        versions = snapshot.read_versions(held[-1])
    else:
        if stale := snapshot.stale(root, proposal.files):
            raise DeclarationError(
                f"contracts/next is not current: {', '.join(stale)}",
                code="TP-C001",
                hint="run texpkg-build contracts and review the files",
            )
        if proposal.output and not proposal.versions.output_change:
            raise DeclarationError(
                f"the output changed ({', '.join(proposal.output)}) and contracts/next/versions.toml does not say how",
                code="TP-C005",
                hint='under [output] write change = "current" (visible: proofs need approving again) or "revision"',
            )
        versions = snapshot.read_versions(root / snapshot.CONTRACTS / snapshot.NEXT)
    assert versions is not None
    if dist.base is not None and versions.base_interface:
        base: Any = importlib.import_module(dist.base.module).CONTRACTS
        if versions.base_interface < base.interface.current - base.interface.age:
            raise DeclarationError(
                f"the base no longer supports the interface {versions.base_interface} this package relies on",
                code="TP-C006",
                hint="adapt to the new base, then set [base] interface in contracts/next/versions.toml",
            )
    return versions.contracts(), held
