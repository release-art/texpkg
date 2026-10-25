"""Copying embedded packages and rewriting their imports (P13-P19, B7, B10, 1.5).

A wheel holds one copy of texmodel, of texpkg's run time and of each package in its base chain, side by side under
`<module>/_embedded/`. Every import of an embedded name, absolute or relative into another embedded copy, is found with
`ast` and rewritten as a relative import of the private copy; nothing is matched by regular expression.
"""

import ast
import pathlib
import shutil
import sys
from collections.abc import Callable, Iterator

from texpkg.declaration import Distribution
from texpkg.errors import DeclarationError

EMBEDDED = "_embedded"
RUN_TIME = ("texmodel", "texpkg")
ALLOWED = frozenset({"pydantic", "pydantic_core", "annotated_types", "typing_extensions", "typing_inspection"})
_SKIP = shutil.ignore_patterns("__pycache__", "*.pyc")

type Mapping = Callable[[str], str | None]


def relative(package: tuple[str, ...], target: tuple[str, ...]) -> tuple[int, str]:
    """The level and module of the relative import that reaches `target` from a module in `package`."""
    common = 0
    while common < min(len(package), len(target)) and package[common] == target[common]:
        common += 1
    return len(package) - common + 1, ".".join(target[common:])


def _absolute(node: ast.ImportFrom, package: tuple[str, ...]) -> tuple[str, ...]:
    base = package[: len(package) - (node.level - 1)] if node.level else ()
    return (*base, *(node.module.split(".") if node.module else ()))


def _fail(code: str, message: str, where: str, hint: str) -> DeclarationError:
    return DeclarationError(message, code=code, path=where, hint=hint)


def _names(aliases: list[ast.alias]) -> str:
    return ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in aliases)


def _from_statement(node: ast.ImportFrom, old: tuple[str, ...], new: tuple[str, ...], mapping: Mapping) -> str | None:
    mapped = mapping(".".join(_absolute(node, old)))
    if mapped is None:
        return None
    level, module = relative(new, tuple(mapped.split(".")))
    if (level, module) == (node.level, node.module or ""):
        return None  # a relative import inside what moves rigidly stays as it is
    return f"from {'.' * level}{module} import {_names(node.names)}"


def _import_statement(node: ast.Import, new: tuple[str, ...], mapping: Mapping, where: str) -> str | None:
    if not any(mapping(a.name) is not None for a in node.names):
        return None
    lines: list[str] = []
    for alias in node.names:
        mapped = mapping(alias.name)
        if mapped is None:
            lines.append(f"import {_names([alias])}")
            continue
        if "." in alias.name and not alias.asname:
            parent, _, child = alias.name.rpartition(".")
            raise _fail(
                "TP-E001",
                f"{where}: `import {alias.name}` binds the top package, which cannot be pointed at the private copy",
                where,
                f"write `from {parent} import {child}`",
            )
        *parent, last = mapped.split(".")
        level, module = relative(new, tuple(parent))
        lines.append(f"from {'.' * level}{module} import {last}" + (f" as {alias.asname}" if alias.asname else ""))
    return ("\n" + " " * node.col_offset).join(lines)


def rewrite(source: str, old: tuple[str, ...], new: tuple[str, ...], mapping: Mapping, where: str) -> str:
    """`source`, a module of package `old` that is moved to package `new`, with each import whose absolute name
    `mapping` changes written as a relative import from `new`. Other imports are left as they are."""
    raw = source.encode("utf-8")
    starts = [0]
    for line in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            text = _from_statement(node, old, new, mapping)
        elif isinstance(node, ast.Import):
            text = _import_statement(node, new, mapping, where)
        else:
            continue
        if text is not None and node.end_lineno is not None and node.end_col_offset is not None:
            edits.append(
                (starts[node.lineno - 1] + node.col_offset, starts[node.end_lineno - 1] + node.end_col_offset, text)
            )
    for start, end, text in sorted(edits, reverse=True):
        raw = raw[:start] + text.encode("utf-8") + raw[end:]
    return raw.decode("utf-8")


def imported_names(source: str) -> Iterator[tuple[str, ast.Import | ast.ImportFrom]]:
    """Every absolute module name `source` imports, with its node: `import a.b` and `from a.b import c` give `a.b`."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node


def scan_declaration(source: str, where: str, own: set[str], embedded: set[str]) -> None:
    """What the build refuses in the author's code (B4): an absolute import of the package itself (P19), a read of the
    distribution's metadata (B10), a dynamic import of an embedded name, and a module the wheel does not carry."""
    for name, node in imported_names(source):
        top = name.split(".")[0]
        if top in own:
            raise _fail(
                "TP-E002",
                f"{where}:{node.lineno}: absolute import of {name}, which is this package's own name",
                where,
                "import the package's own modules relatively (from .model import X), so a copy works anywhere",
            )
        if name.startswith("importlib.metadata") or (
            name == "importlib" and isinstance(node, ast.ImportFrom) and any(a.name == "metadata" for a in node.names)
        ):
            raise _fail(
                "TP-E003",
                f"{where}: reads distribution metadata ({name}); an embedded copy has none of its own",
                where,
                "take the version from the constant the build writes (the module's __version__)",
            )
        if top not in sys.stdlib_module_names and top not in ALLOWED and top not in embedded:
            raise _fail(
                "TP-E004",
                f"{where}: imports {name}, which the wheel does not carry",
                where,
                "a wheel needs only the standard library, pydantic, texmodel, texpkg and its bases",
            )
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            value = node.args[0].value
            if (
                called in ("import_module", "__import__")
                and isinstance(value, str)
                and value.split(".")[0] in own | embedded
            ):
                raise _fail(
                    "TP-E005",
                    f"{where}:{node.lineno}: dynamic import of {value}",
                    where,
                    "import it with a plain import statement, which the build can point at the private copy",
                )


def patch_generator_version(source: str, version: str) -> str:
    """texmodel's `generator_version()` with the version written in (B10): a copy has no metadata to ask."""
    tree = ast.parse(source)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generator_version")
    lines = source.splitlines(keepends=True)
    assert func.end_lineno is not None
    body = (
        "def generator_version() -> str:\n"
        f'    """The texmodel this copy was embedded from, written when it was embedded (B10)."""\n'
        f"    return {version!r}\n"
    )
    return "".join(lines[: func.lineno - 1]) + body + "".join(lines[func.end_lineno :])


def copy_tree(source: pathlib.Path, dest: pathlib.Path, *, skip: tuple[str, ...] = ()) -> list[pathlib.Path]:
    """Copy a package directory, leaving out caches and `skip`; the `.py` files copied, for rewriting."""
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", *skip), dirs_exist_ok=True)
    return sorted(dest.rglob("*.py"))


def rewrite_tree(root: pathlib.Path, old: tuple[str, ...], new: tuple[str, ...], mapping: Mapping) -> None:
    """Rewrite every `.py` under `root`, a package that stands at `old` and is moved to `new`."""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        package_old = (*old, *rel.parts[:-1])
        package_new = (*new, *rel.parts[:-1])
        text = path.read_text(encoding="utf-8")
        changed = rewrite(text, package_old, package_new, mapping, str(path))
        if changed != text:
            path.write_text(changed, encoding="utf-8")


def _package_dir(name: str) -> pathlib.Path:
    """Where the importable package `name` is installed in this build environment."""
    module = sys.modules.get(name) or __import__(name)
    return pathlib.Path(next(iter(module.__path__)))


def embed(out: pathlib.Path, dist: Distribution, declaration: pathlib.Path, generated: dict[str, str]) -> None:
    """Write the module of `dist` into `out` (`<build dir>/<module>`): the generated files, the declaration copied to
    `_declaration`, and under `_embedded` one copy each of texmodel, texpkg's run time and the base chain (P19), all
    with their imports of one another rewritten (1.5)."""
    from texmodel.package import generator_version

    module = dist.module
    embedded = {*RUN_TIME, *(d.module for d in dist.chain()[1:])}
    own = {dist.declared_in.split(".")[0], module}

    def to_copy(name: str) -> str | None:
        return f"{module}._embedded.{name}" if name.split(".")[0] in embedded else None

    copy_tree(declaration, out / "_declaration")
    for path in sorted((out / "_declaration").rglob("*.py")):
        scan_declaration(path.read_text(encoding="utf-8"), str(path.relative_to(out)), own, embedded)
    for rel, text in generated.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(text, encoding="utf-8")
    rewrite_tree(out, (module,), (module,), to_copy)
    base = out / EMBEDDED
    base.mkdir()
    (base / "__init__.py").write_text("", encoding="utf-8")
    for name, skip in (("texmodel", ("cli.py",)), ("texpkg", ())):
        copy_tree(_package_dir(name), base / name, skip=skip)
        rewrite_tree(base / name, (name,), (module, EMBEDDED, name), to_copy)
    patched = base / "texmodel" / "package.py"
    patched.write_text(
        patch_generator_version(patched.read_text(encoding="utf-8"), generator_version()), encoding="utf-8"
    )
    if dist.base is not None:
        _embed_base(base, module, dist.base.module)


def _embed_base(base: pathlib.Path, module: str, base_module: str) -> None:
    """The installed base, flattened: its own files, then each package of its `_embedded` that is not texmodel or texpkg
    (the dependent has its own copy of those, and the base's code is pointed at it)."""
    source = _package_dir(base_module)
    prefix = f"{base_module}.{EMBEDDED}."

    def moved(name: str) -> str | None:
        if name == prefix.removesuffix("."):
            return f"{module}.{EMBEDDED}"  # `from .._embedded import x`: the bases are now beside this one
        return f"{module}.{EMBEDDED}.{name.removeprefix(prefix)}" if name.startswith(prefix) else None

    copy_tree(source, base / base_module, skip=(EMBEDDED,))
    rewrite_tree(base / base_module, (base_module,), (module, EMBEDDED, base_module), moved)
    lifted = source / EMBEDDED
    for path in sorted(lifted.iterdir()) if lifted.is_dir() else ():
        if path.is_dir() and path.name not in RUN_TIME:
            copy_tree(path, base / path.name)
            rewrite_tree(base / path.name, (base_module, EMBEDDED, path.name), (module, EMBEDDED, path.name), moved)
