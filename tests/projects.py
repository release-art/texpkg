"""An author's project made in a temporary directory, and built in this process with pdm-backend."""

import os
import pathlib
import shutil
import tarfile
import zipfile
from collections.abc import Callable

from pdm.backend import build_sdist, build_wheel

from .helpers import FIXTURES

CONSUMERS = pathlib.Path(__file__).parent / "consumers"
_IGNORE = shutil.ignore_patterns("__pycache__")


def author_project(
    root: pathlib.Path, *, declaration: str = "acme_brand", project: str = "acme-brand-tex"
) -> pathlib.Path:
    """The project `tests/consumers/<project>` with the declaration package `tests/fixtures/<declaration>` in `src/`."""
    shutil.copytree(CONSUMERS / project, root, ignore=_IGNORE)
    shutil.copytree(
        FIXTURES / declaration, root / "src" / declaration, ignore=shutil.ignore_patterns("__pycache__", "generated")
    )
    return root


def _build(build: Callable[[str], str], project: pathlib.Path, dist: pathlib.Path) -> pathlib.Path:
    old = pathlib.Path.cwd()
    os.chdir(project)
    try:
        return dist / build(str(dist))
    finally:
        os.chdir(old)


def wheel(project: pathlib.Path, dist: pathlib.Path) -> pathlib.Path:
    """The wheel of `project` built into `dist`, as `pdm build` does (the hook runs in this process)."""
    return _build(build_wheel, project, dist)


def sdist(project: pathlib.Path, dist: pathlib.Path) -> pathlib.Path:
    return _build(build_sdist, project, dist)


def unpack_sdist(archive: pathlib.Path, into: pathlib.Path) -> pathlib.Path:
    """The project directory inside an sdist."""
    with tarfile.open(archive) as tar:
        tar.extractall(into, filter="data")
    (project,) = (p for p in into.iterdir() if p.is_dir())
    return project


def names(artifact: pathlib.Path) -> list[str]:
    with zipfile.ZipFile(artifact) as z:
        return sorted(z.namelist())
