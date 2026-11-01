"""The wheel of a package's frozen contract snapshots (V38): `<name>-contracts`, one release per wheel, holding every
snapshot up to that release, so the package depends on exactly the history that belongs to it and the next release
starts from this wheel (`contracts --base`)."""

import base64
import hashlib
import pathlib
import zipfile
from collections.abc import Mapping

from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

from . import snapshot

_STAMP = (1980, 1, 1, 0, 0, 0)  # a wheel is a function of its contents
_WHEEL = "Wheel-Version: 1.0\nGenerator: texpkg-build\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def name_of(dist: Distribution) -> str:
    return f"{dist.name}-contracts"


def module_of(dist: Distribution) -> str:
    return f"{dist.module}_contracts"


def _record(files: Mapping[str, bytes], record: str) -> str:
    def row(path: str, data: bytes) -> str:
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        return f"{path},sha256={digest},{len(data)}\n"

    return "".join(row(p, d) for p, d in files.items()) + f"{record},,\n"


def build(dist: Distribution, root: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
    """The wheel of every frozen snapshot of the project at `root`, written into `into`."""
    held = snapshot.frozen(root)
    if not held:
        raise DeclarationError(
            "no frozen snapshots to put in a wheel",
            code="TP-C011",
            hint="freeze a release first: texpkg-build contracts --freeze",
        )
    version, module = held[-1].name, module_of(dist)
    info = f"{module}-{version}.dist-info"
    files: dict[str, bytes] = {f"{module}/__init__.py": f'"""Frozen contract snapshots of {dist.name}."""\n'.encode()}
    for directory in held:
        for file in sorted(directory.rglob("*")):
            if file.is_file():
                files[f"{module}/{file.relative_to(root / snapshot.CONTRACTS).as_posix()}"] = file.read_bytes()
    files[f"{info}/METADATA"] = (
        f"Metadata-Version: 2.1\nName: {name_of(dist)}\nVersion: {version}\n"
        f"Summary: Frozen contract snapshots of {dist.name}\n"
    ).encode()
    files[f"{info}/WHEEL"] = _WHEEL.encode()
    record = f"{info}/RECORD"
    files[record] = _record(files, record).encode()
    into.mkdir(parents=True, exist_ok=True)
    target = into / f"{module}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as wheel:
        for path, data in files.items():
            entry = zipfile.ZipInfo(path, _STAMP)
            entry.external_attr = 0o644 << 16
            wheel.writestr(entry, data, zipfile.ZIP_DEFLATED)
    return target
