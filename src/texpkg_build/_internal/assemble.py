"""The wheel's module: the generated files, the author's declaration copied into it and the frozen contracts (P22, B6).

The wheel depends on texpkg and on the base's wheel (B7); nothing else is copied into it. The declaration is imported
under another name than the author's, so what the build refuses is code that would break there.
"""

import ast
import pathlib
import shutil
import sys
from collections.abc import Iterator, Sequence

from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

# What a declaration may import besides the standard library, its own relative modules, texpkg, texmodel and its bases.
ALLOWED = frozenset({"pydantic"})  # the wheel's other direct dependency (B7)


def _fail(code: str, message: str, where: str, hint: str) -> DeclarationError:
    return DeclarationError(message, code=code, path=where, hint=hint)


def imported_names(source: str) -> Iterator[tuple[str, ast.Import | ast.ImportFrom]]:
    """Every absolute module name `source` imports, with its node: `import a.b` and `from a.b import c` give `a.b`."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node


def scan_declaration(source: str, where: str, own: set[str], installed: set[str]) -> None:
    """What the build refuses in the author's code (B4): an absolute import of the package itself or a dynamic import of
    it, which a copy under another name cannot resolve (P19), and a module the wheel does not depend on. `installed`
    are the packages it does: texmodel, texpkg and the bases."""
    for name, node in imported_names(source):
        top = name.split(".")[0]
        if top in own:
            raise _fail(
                "TP-E002",
                f"{where}:{node.lineno}: absolute import of {name}, which is this package's own name",
                where,
                "import the package's own modules relatively (from .model import X), so a copy works anywhere",
            )
        if top not in sys.stdlib_module_names and top not in ALLOWED and top not in installed:
            raise _fail(
                "TP-E004",
                f"{where}: imports {name}, which the wheel does not depend on",
                where,
                "a wheel depends on texpkg (so texmodel and pydantic) and its bases, and imports nothing else",
            )
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            value = node.args[0].value
            if called in ("import_module", "__import__") and isinstance(value, str) and value.split(".")[0] in own:
                raise _fail(
                    "TP-E005",
                    f"{where}:{node.lineno}: dynamic import of {value}",
                    where,
                    "import the package's own modules relatively, with a plain import statement",
                )


def copy_tree(source: pathlib.Path, dest: pathlib.Path) -> None:
    """Copy a directory, leaving out caches."""
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), dirs_exist_ok=True)


def assemble(
    out: pathlib.Path,
    dist: Distribution,
    declaration: pathlib.Path,
    generated: dict[str, str],
    frozen: Sequence[pathlib.Path] = (),
) -> None:
    """Write the module of `dist` into `out` (`<build dir>/<module>`): the generated files, the declaration copied to
    `_declaration` and the frozen snapshots to `_contracts`."""
    installed = {"texmodel", "texpkg", *(d.module for d in dist.chain()[1:])}
    own = {dist.declared_in.split(".")[0], dist.module}
    copy_tree(declaration, out / "_declaration")
    for snapshot in frozen:
        copy_tree(snapshot, out / "_contracts" / snapshot.name)
    for path in sorted((out / "_declaration").rglob("*.py")):
        scan_declaration(path.read_text(encoding="utf-8"), str(path.relative_to(out)), own, installed)
    for rel, text in generated.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding="utf-8")
