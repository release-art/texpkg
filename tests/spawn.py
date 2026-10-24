"""The one place tests start a process (the library never does, N4): import-linter on a scratch tree, pip in a venv."""

import os
import pathlib
import subprocess
import sys
from collections.abc import Mapping, Sequence


def run(
    argv: Sequence[str | pathlib.Path], *, cwd: pathlib.Path, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """`argv` run in `cwd` with `env` added to this process's environment; stdout and stderr are captured."""
    return subprocess.run(  # noqa: S603  # argv is a list built by the tests, never a shell string
        [str(a) for a in argv],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def lint_imports(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """import-linter over the packages under `root`, with the repository's own contracts."""
    code = "from importlinter.cli import lint_imports_command as c; c()"
    return run([sys.executable, "-c", code], cwd=root, env={"PYTHONPATH": str(root)})
