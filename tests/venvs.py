"""A fresh virtual environment holding what a wheel depends on (pydantic, texmodel, texpkg), to install built wheels
into (tests may spawn)."""

import importlib.metadata
import importlib.util
import pathlib
import sys
import venv

from . import spawn

RUN_TIME = (
    "pydantic",
    "pydantic_core",
    "annotated_types",
    "typing_extensions",
    "typing_inspection",
    "texmodel",
    "texpkg",
)


def clean_venv(root: pathlib.Path) -> pathlib.Path:
    """The python of a new environment that can import texpkg, texmodel and pydantic and nothing else of this one (not
    texpkg_build). They are linked in, so the test needs no index."""
    venv.EnvBuilder(with_pip=False, symlinks=True).create(root)
    python = root / "bin" / "python"
    links = root / "run-time"
    links.mkdir()
    for name in RUN_TIME:
        spec = importlib.util.find_spec(name)
        assert spec is not None and spec.origin is not None
        origin = pathlib.Path(spec.origin)
        target = origin.parent if origin.name == "__init__.py" else origin
        (links / target.name).symlink_to(target)
    site = next((root / "lib").glob("python*/site-packages"))
    (site / "run-time.pth").write_text(f"{links}\n")
    for name in ("texmodel", "texpkg"):  # texmodel reads its version from its metadata
        where = pathlib.Path(str(importlib.metadata.distribution(name).locate_file(".")))
        (info,) = where.glob(f"{name}-*.dist-info")
        (site / info.name).symlink_to(info)
    return python


def install(python: pathlib.Path, wheel: pathlib.Path) -> None:
    done = spawn.run(
        [sys.executable, "-m", "pip", "--python", python, "install", "--no-deps", "--no-index", wheel], cwd=wheel.parent
    )
    assert done.returncode == 0, done.stderr


def run(python: pathlib.Path, code: str, *args: str | pathlib.Path, cwd: pathlib.Path) -> str:
    done = spawn.run([python, "-c", code, *args], cwd=cwd)
    assert done.returncode == 0, done.stderr
    return done.stdout
