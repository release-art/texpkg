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
from collections.abc import Mapping
from typing import Any

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
_RELEASE = re.compile(r"\d+\.\d+\.\d+")


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
    """The public TeX names with their signatures, and the kinds with their variants (V11): from the declaration."""
    components = {cls.__name__: _component(cls) for cls in dist.package.registered}
    kinds = {
        k.name: {"variants": [v.name for v in k.variants], "over": k.over or "", "exposed": k.name in dist.expose}
        for k in dist.kinds_offered()
    }
    return {"components": components, "kinds": kinds}


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
    found = [p for p in base.iterdir() if p.is_dir() and _RELEASE.fullmatch(p.name)] if base.is_dir() else []
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


@dataclasses.dataclass(frozen=True)
class Proposal:
    files: dict[str, str]  # the snapshot, with the versions file as `versions.toml`
    versions: Versions
    data: list[classify.Change]
    interface: list[classify.Change]
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
) -> Proposal:
    """The snapshot of this declaration and the versions it implies against the newest frozen release (V12, V13),
    keeping what the author wrote in `contracts/next/versions.toml`: the `output` classification and the notes."""
    files = build(dist, release, sty)
    authored = read_versions(root / CONTRACTS / NEXT)
    notes = dict(authored.notes) if authored else {}
    change = authored.output_change if authored else ""
    previous = frozen(root)
    if not previous:
        versions = Versions(
            first,
            notes=notes,
            releases={1: first},
            base_data={1: base_current[0]} if dist.base else {},
            base_interface=authored.base_interface if authored else base_current[1],
        )
        return Proposal(files | {VERSIONS: versions.to_text()}, versions, [], [], [], [])
    last = previous[-1]
    old = read_versions(last)
    assert old is not None
    data_changes: list[classify.Change] = []
    for kind in dist.kinds_offered():
        was = last / "kinds" / f"{kind.name}.input.schema.json"
        if was.is_file():
            data_changes += [
                dataclasses.replace(c, where=f"{kind.name}: {c.where}")
                for c in classify.schema_changes(
                    json.loads(was.read_text(encoding="utf-8")),
                    json.loads(files[f"kinds/{kind.name}.input.schema.json"]),
                )
            ]
        else:
            data_changes.append(classify.Change(classify.Level.COMPATIBLE, f"kind {kind.name}", "added"))
    kinds_before = {p.name.removesuffix(".input.schema.json") for p in (last / "kinds").glob("*.input.schema.json")}
    data_changes += [
        classify.Change(classify.Level.BREAKING, f"kind {n}", "removed")
        for n in sorted(kinds_before - {k.name for k in dist.kinds_offered()})
    ]
    interface_changes = classify.interface_changes(
        json.loads((last / "interface.json").read_text(encoding="utf-8")), json.loads(files["interface.json"])
    )
    changed, not_compared = output_changes(last, dist, release, sty)
    data = classify.bump(old.data, classify.worst(data_changes))
    interface = classify.bump(old.interface, classify.worst(interface_changes))
    output = classify.bump_output(old.output, change if changed else "")
    required = classify.required_release(
        old.release, classify.worst(data_changes), classify.worst(interface_changes), bool(changed)
    )
    releases = dict(old.releases)
    if data.current != old.data.current:
        releases[data.current] = required
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
        authored.base_interface if authored and authored.base_interface else old.base_interface,
    )
    return Proposal(
        files | {VERSIONS: versions.to_text()}, versions, data_changes, interface_changes, changed, not_compared
    )


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
    data: list[classify.Change] = []
    for path in sorted((this / "kinds").glob("*.input.schema.json")):
        old = previous / "kinds" / path.name
        data += (
            classify.schema_changes(
                json.loads(old.read_text(encoding="utf-8")), json.loads(path.read_text(encoding="utf-8"))
            )
            if old.is_file()
            else [classify.Change(classify.Level.COMPATIBLE, path.name, "added")]
        )
    data += [
        classify.Change(classify.Level.BREAKING, path.name, "removed")
        for path in (previous / "kinds").glob("*.input.schema.json")
        if not (this / "kinds" / path.name).is_file()
    ]
    interface = classify.interface_changes(
        json.loads((previous / "interface.json").read_text(encoding="utf-8")),
        json.loads((this / "interface.json").read_text(encoding="utf-8")),
    )
    changed = (previous / "output.json").read_text(encoding="utf-8") != (this / "output.json").read_text(
        encoding="utf-8"
    )
    return classify.required_release(before.release, classify.worst(data), classify.worst(interface), changed)
