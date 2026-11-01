"""Contract snapshots, the versions file and freezing (V11, V35-V37).

`contracts/next/` is the working snapshot an author reviews and commits; `contracts/<release>/` is a frozen copy that is
never rewritten and ships in the wheel. Nothing here needs TeX: the output fingerprint is the hash of what is rendered.
"""

import dataclasses
import hashlib
import importlib
import json
import pathlib
import re
import shutil
import tomllib
import zipfile
from collections.abc import Iterator, Mapping
from typing import Any

from texmodel import history
from texmodel.components import Command, Environment, Value, control_name
from texmodel.errors import DeclarationError as TexmodelDeclarationError
from texmodel.interface import Body

from texpkg import errors
from texpkg._internal import classify, state
from texpkg._internal.release import Release
from texpkg._internal.versions import Versions
from texpkg.declaration import Distribution

from . import generate

CONTRACTS = "contracts"
NEXT = "next"
VERSIONS = "versions.toml"
_IN_WHEEL = re.compile(r"[^/]+/(?:_contracts/)?(\d+\.\d+\.\d+/.+)")  # a package wheel, or a contracts wheel


def _dumps(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sha(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def _body(body: Body) -> str:
    """What an argument holds, without a `Choice`'s members (they belong to the data contract, not the interface)."""
    return body.kind.value + (f" {body.choice.__name__}" if body.choice else "")


def _component(cls: type) -> dict[str, Any]:
    plain: type = cls  # `cls` is narrowed below; the name lookups want the declared type
    entry: dict[str, Any] = {"doc": str(getattr(cls, "__tm_doc__", ""))}
    if issubclass(cls, Command | Environment):
        entry["kind"] = "environment" if issubclass(cls, Environment) else "command"
        entry["signature"] = [[a.name, _body(a.body), a.optional] for a in cls.__tm_args__]
    elif issubclass(cls, Value):
        entry["kind"] = "value"
        entry["type"] = cls.__tm_kind__.name
    try:
        entry["cs"] = control_name(plain)
    except TexmodelDeclarationError:
        entry["cs"] = str(getattr(plain, "colour_name", None) or "")  # a colour is named, not a control sequence
    return entry


def interface_of(dist: Distribution) -> dict[str, Any]:
    """The public TeX names with their signatures, the kinds with their variants and the published constants (V11,
    P31): from the declaration."""
    components = {cls.__name__: _component(cls) for cls in dist.package.registered}
    kinds = {
        k.name: {"variants": [v.name for v in k.variants], "over": k.over or "", "exposed": k.name in dist.expose}
        for k in dist.kinds_offered()
    }
    published = {"public": generate.public_values(dist)} if dist.public else {}  # absent when nothing is published
    return {"components": components, "kinds": kinds, **published}


def build(dist: Distribution, release: Release, sty: Mapping[str, str]) -> dict[str, str]:
    """Every file of a snapshot except the versions file, by path: both schemas of every kind, the interface, each
    example's data and rendered `.tex`, and the fingerprint of the output (one hash per file, V35)."""
    files: dict[str, str] = {"interface.json": _dumps(interface_of(dist))}
    examples: dict[str, str] = {}
    for kind in dist.kinds_offered():
        files[f"kinds/{kind.name}.input.schema.json"] = _dumps(
            state.schema(kind, dist.owner(kind.name).package, "validation")
        )
        files[f"kinds/{kind.name}.stored.schema.json"] = _dumps(
            state.schema(kind, dist.owner(kind.name).package, "serialization")
        )
        tree = kind.example()
        files[f"examples/{kind.name}.json"] = _dumps(state.tree_state(tree))
        for variant, name in kind.documents():
            tex = release.plan(kind, tree, variant).text
            files[f"examples/{kind.name}/{name}"] = tex
            examples[f"{kind.name}/{name}"] = _sha(tex)
    output = {
        "sty": {name: _sha(text) for name, text in sorted(sty.items())},
        "assets": {r.asset.path: _sha(r.source.read_bytes()) for r in dist.resolved_assets()},
        "examples": examples,
    }
    files["output.json"] = _dumps(output)
    return files


def frozen(root: pathlib.Path) -> list[pathlib.Path]:
    """The frozen snapshots under `root/contracts`, oldest first."""
    base = root / CONTRACTS
    found = [p for p in base.iterdir() if p.is_dir() and classify.RELEASE.fullmatch(p.name)] if base.is_dir() else []
    return sorted(found, key=lambda p: classify.parse_version(p.name))


def read_versions(directory: pathlib.Path) -> Versions | None:
    path = directory / VERSIONS
    return Versions.parse(path.read_text(encoding="utf-8")) if path.is_file() else None


def output_changes(
    previous: pathlib.Path, dist: Distribution, release: Release, sty: Mapping[str, str]
) -> tuple[list[str], list[str]]:
    """The files whose bytes changed against the previous release, and the examples that could not be compared (V35).

    The previous release's example data is rendered with this package and compared with the previous release's
    `.tex`, so editing an example is not a change; an example whose data no longer loads is reported, never guessed.
    """
    before = json.loads((previous / "output.json").read_text(encoding="utf-8"))
    now = {
        "sty": {n: _sha(t) for n, t in sty.items()},
        "assets": {r.asset.path: _sha(r.source.read_bytes()) for r in dist.resolved_assets()},
    }
    changed = [
        f"{part}: {name}"
        for part in ("sty", "assets")
        for name in sorted(before[part].keys() | now[part].keys())
        if before[part].get(name) != now[part].get(name)
    ]
    not_compared: list[str] = []
    for kind in dist.kinds_offered():
        saved = previous / "examples" / f"{kind.name}.json"
        if not saved.is_file():
            continue  # a kind that is new has no baseline
        try:
            tree = state.tree_from_state(kind.model, json.loads(saved.read_text(encoding="utf-8")))
        except ExceptionGroup, ValueError, KeyError:
            not_compared.append(kind.name)
            continue
        for variant, name in kind.documents():
            was = before["examples"].get(f"{kind.name}/{name}")
            if was is not None and was != _sha(release.plan(kind, tree, variant).text):
                changed.append(f"example: {kind.name}/{name}")
    return changed, not_compared


def _schemas(directory: pathlib.Path) -> dict[str, str]:
    """The input schema of each kind in a snapshot, by kind name."""
    return {
        p.name.removesuffix(".input.schema.json"): p.read_text(encoding="utf-8")
        for p in sorted((directory / "kinds").glob("*.input.schema.json"))
    }


def _data_changes(was: Mapping[str, str], now: Mapping[str, str]) -> list[history.Change]:
    """What changed in the data the kinds accept (V12): each kind's schema diff, kinds added and kinds removed."""
    out: list[history.Change] = []
    for name, text in now.items():
        if name in was:
            out += [
                dataclasses.replace(c, where=f"{name}: {c.where}")
                for c in history.schema_changes(json.loads(was[name]), json.loads(text))
            ]
        else:
            out.append(history.Change(history.Level.COMPATIBLE, f"kind {name}", "added"))
    return out + [
        history.Change(history.Level.BREAKING, f"kind {n}", "removed") for n in sorted(was.keys() - now.keys())
    ]


@dataclasses.dataclass(frozen=True)
class Hint:
    """What the author states for the next release, in `[tool.texpkg.release]` of `pyproject.toml` (V12, V33): how an
    output change counts, the note of the `data` version the release introduces, the base `interface` relied on."""

    output: str = ""
    note: str = ""
    base_interface: int = 0


def read_hint(root: pathlib.Path) -> Hint:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    given = dict(config.get("tool", {}).get("texpkg", {}).get("release", {}))
    where = "[tool.texpkg.release] in pyproject.toml"
    if unknown := sorted(set(given) - {"output", "note", "base-interface"}):
        raise errors.DeclarationError(
            f"{where} has {', '.join(unknown)}",
            code="TP-C008",
            hint='the keys are output = "current" or "revision", note = "...", base-interface = 3',
        )
    if given.get("output", "") not in ("", "current", "revision"):
        raise errors.DeclarationError(
            f"{where}: output is {given['output']!r}",
            code="TP-C008",
            hint='write output = "current" (visible: proofs need approving again) or "revision"',
        )
    return Hint(given.get("output", ""), given.get("note", ""), given.get("base-interface", 0))


@dataclasses.dataclass(frozen=True)
class Proposal:
    files: dict[str, str]  # the snapshot, with the versions file as `versions.toml`
    versions: Versions
    data: list[history.Change]
    interface: list[history.Change]
    output: list[str]
    not_compared: list[str]


def propose(
    root: pathlib.Path,
    dist: Distribution,
    release: Release,
    sty: Mapping[str, str],
    *,
    first: str = "0.1.0",
    base_current: tuple[int, int] = (0, 0),
    hint: Hint,
) -> Proposal:
    """The snapshot of this declaration and the versions it implies against the newest frozen release (V12, V13),
    keeping what the author wrote in `contracts/next/versions.toml`: the `output` classification and the notes. The
    `hint` of `pyproject.toml` says the same for a project that commits no `contracts/next`."""
    files = build(dist, release, sty)
    authored = read_versions(root / CONTRACTS / NEXT)
    notes = dict(authored.notes) if authored else {}
    change = hint.output or (authored.output_change if authored else "")
    base_interface = hint.base_interface or (authored.base_interface if authored else 0)
    previous = frozen(root)
    if not previous:
        if hint.note:
            notes[1] = hint.note
        versions = Versions(
            first,
            notes=notes,
            releases={1: first},
            base_data={1: base_current[0]} if dist.base else {},
            base_interface=base_interface or base_current[1],
        )
        return Proposal(files | {VERSIONS: versions.to_text()}, versions, [], [], [], [])
    last = previous[-1]
    old = read_versions(last)
    assert old is not None
    data_changes = _data_changes(
        _schemas(last), {k.name: files[f"kinds/{k.name}.input.schema.json"] for k in dist.kinds_offered()}
    )
    interface_changes = classify.interface_changes(
        json.loads((last / "interface.json").read_text(encoding="utf-8")), json.loads(files["interface.json"])
    )
    changed, not_compared = output_changes(last, dist, release, sty)
    data = classify.bump(old.data, history.worst(data_changes))
    interface = classify.bump(old.interface, history.worst(interface_changes))
    output = classify.bump_output(old.output, change if changed else "")
    required = classify.required_release(
        old.release, history.worst(data_changes), history.worst(interface_changes), bool(changed)
    )
    if hint.output and not changed:
        raise errors.DeclarationError(
            f"[tool.texpkg.release] output = {hint.output!r}, but the output did not change",
            code="TP-C008",
            hint="remove it from pyproject.toml: it states one release",
        )
    if hint.note and data.current == old.data.current:
        raise errors.DeclarationError(
            "[tool.texpkg.release] has a note, but this release introduces no new data version",
            code="TP-C008",
            hint="remove it from pyproject.toml: it states one release",
        )
    releases = dict(old.releases)
    if data.current != old.data.current:
        releases[data.current] = required
        if hint.note:
            notes[data.current] = hint.note
    base_data = dict(old.base_data)
    if dist.base is not None and data.current != old.data.current:
        base_data[data.current] = base_current[0]
    versions = Versions(
        required,
        data,
        interface,
        output,
        change if changed else "",
        notes,
        releases,
        base_data,
        base_interface or old.base_interface,
    )
    return Proposal(
        files | {VERSIONS: versions.to_text()}, versions, data_changes, interface_changes, changed, not_compared
    )


def _held(base: pathlib.Path) -> Iterator[tuple[str, bytes]]:
    """`<version>/<file>` and its bytes for every frozen snapshot of `base`: a wheel's `_contracts`, or a directory of
    `<version>/` directories."""
    if base.is_file():
        try:
            with zipfile.ZipFile(base) as wheel:
                for name in sorted(wheel.namelist()):
                    if (found := _IN_WHEEL.fullmatch(name)) and ".." not in found[1].split("/"):
                        yield found[1], wheel.read(name)
        except zipfile.BadZipFile as exc:
            raise errors.DeclarationError(f"{base} is not a wheel", code="TP-C010", path=str(base)) from exc
    elif base.is_dir():
        for file in sorted(base.glob("*.*.*/**/*")):
            relative = file.relative_to(base).as_posix()
            if file.is_file() and classify.RELEASE.fullmatch(relative.split("/")[0]):
                yield relative, file.read_bytes()


def seed(root: pathlib.Path, base: pathlib.Path) -> list[str]:
    """Copy the frozen snapshots of `base`, the previous release's wheel or a directory, into `root/contracts`, so a
    project need not commit them. A snapshot already there must be the same bytes (V37). The releases copied."""
    held = list(_held(base))
    if not held:
        raise errors.DeclarationError(
            f"{base} holds no frozen snapshots",
            code="TP-C010",
            path=str(base),
            hint="give the previous release's wheel",
        )
    copied: dict[str, None] = {}
    for relative, data in held:
        target = root / CONTRACTS / relative
        if target.exists():
            if target.read_bytes() != data:
                raise errors.DeclarationError(
                    f"{CONTRACTS}/{relative} differs from the one in {base}",
                    code="TP-C009",
                    path=str(target),
                    hint="a frozen snapshot is never rewritten: remove contracts/ or use the right base",
                )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        copied[relative.split("/")[0]] = None
    return list(copied)


def write_next(root: pathlib.Path, files: Mapping[str, str]) -> None:
    """Write the working snapshot, replacing the previous one."""
    target = root / CONTRACTS / NEXT
    shutil.rmtree(target, ignore_errors=True)
    for rel, text in files.items():
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        (target / rel).write_text(text, encoding="utf-8")


def stale(root: pathlib.Path, files: Mapping[str, str]) -> list[str]:
    """The files of `contracts/next` that are not what this declaration gives (V12): none means it is current."""
    target = root / CONTRACTS / NEXT
    held: set[str] = (
        {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} if target.is_dir() else set()
    )
    return sorted(
        rel
        for rel in held | files.keys()
        if not (target / rel).is_file() or rel not in files or (target / rel).read_text(encoding="utf-8") != files[rel]
    )


def freeze(root: pathlib.Path) -> pathlib.Path:
    """Copy `contracts/next` to `contracts/<release>`, which is never rewritten (V37)."""
    versions = read_versions(root / CONTRACTS / NEXT)
    if versions is None:
        raise errors.DeclarationError("no contracts/next to freeze", code="TP-C001", hint="run texpkg-build contracts")
    target = root / CONTRACTS / versions.release
    if target.exists():
        raise errors.DeclarationError(
            f"contracts/{versions.release} is frozen already",
            code="TP-C002",
            path=str(target),
            hint="a frozen snapshot is never rewritten: the next release has another number",
        )
    shutil.copytree(root / CONTRACTS / NEXT, target)
    return target


def sty_of(dist: Distribution) -> dict[str, str]:
    """The `.sty` files the output fingerprint is taken from: the base chain's as the bases shipped them, this package's
    rendered at a fixed version so that a release number is not an output change."""
    shipped: dict[str, str] = {}
    if dist.base is not None:
        shipped = dict(importlib.import_module(dist.base.module)._bound.STY)  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]
    return {**shipped, **generate.render_sty(dist, "0.0.0")}


def base_current(dist: Distribution) -> tuple[int, int]:
    """The `data` and `interface` `current` of the base this is built on (P30, V17); zeros without one."""
    if dist.base is None:
        return (0, 0)
    contracts = importlib.import_module(dist.base.module).CONTRACTS  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
    return (contracts.data.current, contracts.interface.current)  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]


def required_for(previous: pathlib.Path | None, this: pathlib.Path) -> str:
    """The release number the frozen `this` needs against the one before it (V13); the first needs none."""
    after = read_versions(this)
    assert after is not None
    if previous is None:
        return after.release
    before = read_versions(previous)
    assert before is not None
    data = _data_changes(_schemas(previous), _schemas(this))
    interface = classify.interface_changes(
        json.loads((previous / "interface.json").read_text(encoding="utf-8")),
        json.loads((this / "interface.json").read_text(encoding="utf-8")),
    )
    changed = (previous / "output.json").read_text(encoding="utf-8") != (this / "output.json").read_text(
        encoding="utf-8"
    )
    return classify.required_release(before.release, history.worst(data), history.worst(interface), changed)
