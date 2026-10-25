"""The plain-LaTeX export (E1): what a project that does not use Python needs, written for each kind.

A kind's template is its example rendered with the kind's settings (L8), so locks reach a plain-LaTeX user; its
README is generated from the kind's classes.
"""

from collections.abc import Sequence

from texmodel.components import Command, Environment, control_name
from texmodel.package import setting_line

from ..declaration import Distribution, Kind, reachable


def template_name(kind: Kind) -> str:
    return f"{kind.name}-template.tex"


def readme_name(kind: Kind) -> str:
    return f"README-{kind.name}.md"


def _call(cls: type[Command] | type[Environment]) -> str:
    """The TeX shape of a component: `\\abFact[accent]{text}` or `\\begin{abCard}` ... `\\end{abCard}`."""
    optional_first = [a for a in cls.__tm_args__ if a.optional and not a.placed]
    ordered = [*optional_first, *(a for a in cls.__tm_args__ if a not in optional_first)]
    args = "".join(f"{a.delimiter.open}{a.name}{a.delimiter.close}" for a in ordered)
    name = control_name(cls)
    return f"\\begin{{{name}}}{args} ... \\end{{{name}}}" if issubclass(cls, Environment) else f"\\{name}{args}"


def readme(dist: Distribution, kind: Kind, release: str, files: Sequence[str]) -> str:
    """The README of `kind`: how to compile its template, what the template is written with, and its commands."""
    base = dist.base_kind(kind)
    model = base.model if base else kind.model
    commands = "\n".join(f"- `{_call(c)}`: {c.__tm_doc__}" for c in reachable(model))
    settings = "\n".join(f"- `{setting_line(v)}`" for v in (*(base.presets if base else ()), *kind.presets))
    variants = ", ".join(f"`{v.name}`" for v in kind.variants) or "none"
    listing = "\n".join(f"- `{name}`" for name in files)
    return (
        f"# {kind.name}: {dist.name} {release}\n\n"
        f"{kind.model.__tm_doc__}\n\n"
        f"Compile the template with LuaLaTeX from this directory:\n\n"
        f"    latexmk -lualatex {template_name(kind)}\n\n"
        f"## Files\n\n{listing}\n\n"
        f"## The template is written with\n\n{settings or 'no settings of its own'}\n\n"
        f"Variants of the kind (the Python module writes them; the template is the kind's own): {variants}.\n\n"
        f"## Commands\n\n{commands}\n"
    )
