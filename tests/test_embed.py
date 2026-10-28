"""Embedding (P13-P21, B7, B10): a wheel that needs only pydantic."""

import ast
import pathlib
import re
import shutil
import sys
import textwrap
import zipfile

import pytest

import texpkg
from texpkg.errors import DeclarationError
from texpkg_build._internal import embed

from . import projects, venvs


def rewritten(source: str, old=("m", "pkg"), new=("m", "pkg"), mapping=None) -> str:  # noqa: ANN001
    mapping = mapping or (lambda name: f"m._embedded.{name}" if name.split(".")[0] in ("texmodel", "base") else None)
    return embed.rewrite(textwrap.dedent(source), old, new, mapping, "x.py")


def test_a_relative_import_reaches_a_target_from_a_package():
    assert embed.relative(("m", "a", "b"), ("m", "_embedded", "texmodel", "x")) == (3, "_embedded.texmodel.x")
    assert embed.relative(("m",), ("m", "_embedded")) == (1, "_embedded")
    assert embed.relative(("m", "a"), ("m", "a")) == (1, "")


def test_every_form_of_an_import_of_an_embedded_name_is_pointed_at_the_copy():
    out = rewritten(
        """
        import os
        import texmodel
        import texmodel.components as c
        from texmodel.components import (
            Command,
            Environment as Env,
        )
        from base import kinds
        from . import sibling
        from .sibling import thing
        from pydantic import BaseModel

        def f():
            from texmodel import spec

        if True:
            import base.kinds as bk, os.path
        """
    )
    assert out == textwrap.dedent(
        """
        import os
        from .._embedded import texmodel
        from .._embedded.texmodel import components as c
        from .._embedded.texmodel.components import Command, Environment as Env
        from .._embedded import kinds
        from . import sibling
        from .sibling import thing
        from pydantic import BaseModel

        def f():
            from .._embedded.texmodel import spec

        if True:
            from .._embedded.base import kinds as bk
            import os.path
        """
    ).replace("from .._embedded import kinds", "from .._embedded.base import kinds")


def test_a_dotted_import_without_a_name_cannot_be_pointed_at_a_copy():
    with pytest.raises(DeclarationError) as raised:
        rewritten("import texmodel.components\n")
    assert raised.value.code == "TP-E001" and "from texmodel import components" in str(raised.value.hint)


def test_a_moved_package_keeps_its_internal_relative_imports_and_changes_the_ones_into_a_copy():
    def mapping(name: str) -> str | None:
        return "m._embedded." + name.removeprefix("b._embedded.") if name.startswith("b._embedded.") else None

    source = "from .model import X\nfrom .._embedded.texmodel import spec\nfrom .. import _bound\n"
    out = embed.rewrite(source, ("b", "_declaration"), ("m", "_embedded", "b", "_declaration"), mapping, "x.py")
    assert out == "from .model import X\nfrom ...texmodel import spec\nfrom .. import _bound\n"


def test_text_around_a_rewritten_import_is_kept_byte_for_byte():
    mapping = lambda name: "m._embedded." + name if name == "texmodel" else None  # noqa: E731
    out = embed.rewrite('"""é"""\nx = 1; import texmodel  # note\n    \n', ("m",), ("m",), mapping, "x.py")
    assert out == '"""é"""\nx = 1; from ._embedded import texmodel  # note\n    \n'


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("from acme_deck import x\n", "TP-E002"),
        ("import acme_deck_tex\n", "TP-E002"),
        ("import importlib.metadata\n", "TP-E003"),
        ("from importlib.metadata import version\n", "TP-E003"),
        ("from importlib import metadata\n", "TP-E003"),
        ("import numpy\n", "TP-E004"),
        ("import importlib\nimportlib.import_module('texmodel.spec')\n", "TP-E005"),
        ("__import__('acme_deck')\n", "TP-E005"),
    ],
)
def test_the_build_refuses_code_that_would_break_in_a_copy(source, code):
    with pytest.raises(DeclarationError) as raised:
        embed.scan_declaration(source, "x.py", {"acme_deck", "acme_deck_tex"}, {"texmodel", "texpkg"})
    assert raised.value.code == code


def test_code_that_is_fine_in_a_copy_passes():
    source = textwrap.dedent(
        """
        import os, pydantic
        import importlib
        from texmodel import spec
        from . import x
        importlib.import_module(name)
        """
    )
    embed.scan_declaration(source, "x.py", {"acme_deck"}, {"texmodel", "texpkg"})


def test_generator_version_is_set_in_the_copy():
    original = 'GENERATOR_VERSION: str | None = None\n"""doc"""\nX = 2\n'
    out = embed.set_generator_version(original, "9.8.7")
    assert out == 'GENERATOR_VERSION: str | None = \'9.8.7\'\n"""doc"""\nX = 2\n'
    with pytest.raises(DeclarationError) as raised:
        embed.set_generator_version("X = 2\n", "9.8.7")
    assert raised.value.code == "TP-E006"


# -- wheels ----------------------------------------------------------------------------------------------------------


def deck(tmp_path: pathlib.Path, name: str = "deck") -> pathlib.Path:
    return projects.author_project(tmp_path / name, declaration="acme_deck", project="acme-deck-tex")


def test_a_wheel_embeds_texmodel_texpkg_and_one_copy_of_each_base(brand_site, tmp_path):
    built = projects.wheel(deck(tmp_path), tmp_path / "dist")
    assert callable(texpkg.migration)  # the build's linking left the real package as it was
    inside = projects.names(built)
    embedded = {n.split("/")[2] for n in inside if "/_embedded/" in n}
    assert embedded == {"__init__.py", "texmodel", "texpkg", "acme_brand_tex"}
    assert not [n for n in inside if "/acme_brand_tex/_embedded/" in n]  # never a copy inside a copy
    assert not [n for n in inside if n.endswith("texmodel/cli.py")]
    assert "acme_deck_tex/_embedded/acme_brand_tex/_sty/acme-brand.sty" in inside
    with zipfile.ZipFile(built) as z:
        package_py = z.read("acme_deck_tex/_embedded/texmodel/package.py").decode()
        assert re.search(r"^GENERATOR_VERSION: str \| None = '\d+\.\d+\.\d+", package_py, re.MULTILINE)
        imports = z.read("acme_deck_tex/_declaration/model.py").decode()
        assert "from .._embedded.acme_brand_tex" in imports and "from .._embedded.texmodel" in imports
        kind_py = z.read("acme_deck_tex/kinds/slide.py").decode()
        assert (
            "from .._embedded.texmodel.body import Comment as Comment" in kind_py
        )  # the consumer's Comment is the embedded texmodel's, the one the grammar checks against
        assert "from .._embedded.texmodel.types import CMYK as CMYK" in kind_py  # so is a value's class
        for name in inside:
            if name.endswith(".py"):
                tree = ast.parse(z.read(name))
                tops = {
                    n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module and n.level == 0 else ""
                    for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom)
                }
                assert not tops & {"texmodel", "texpkg", "acme_brand_tex"}, name
        metadata = z.read("acme_deck_tex-0.1.0.dist-info/METADATA").decode()
    assert [line for line in metadata.splitlines() if line.startswith("Requires-Dist")] == [
        "Requires-Dist: pydantic<3,>=2"
    ]


SCRIPT = """
import importlib.util, json, pathlib, sys
assert importlib.util.find_spec("texmodel") is None and importlib.util.find_spec("texpkg") is None
assert importlib.util.find_spec("acme_brand_tex") is None
import acme_deck_tex as m
from acme_deck_tex.kinds import slide, vocab
root = pathlib.Path(sys.argv[1])
a = slide.create(root / "slide", slide.example()); a.save()
b = vocab.create(root / "vocab", vocab.example()); b.save()
def files(d):
    found = (p for p in (root / d).rglob("*") if p.is_file() and "history" not in p.parts)
    return sorted(str(p.relative_to(root / d)) for p in found)
print(json.dumps({
    "names": m.kinds.names(), "version": m.__version__, "slide": files("slide"), "vocab": files("vocab"),
    "stack": [e.package + " " + e.release for e in a.stack.entries],
    "tex": a.render(), "again": m.load(root / "vocab").kind,
    "texmodel": m.kinds.slide.Slide.__module__,
    "generator": __import__("acme_deck_tex._embedded.texmodel.package", fromlist=["x"]).generator_version(),
}))
"""


def test_a_wheel_installs_into_a_fresh_environment_that_has_only_pydantic(brand_site, tmp_path):
    import json

    built = projects.wheel(deck(tmp_path), tmp_path / "dist")
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, built)
    report = json.loads(venvs.run(python, SCRIPT, tmp_path / "out", cwd=tmp_path))
    assert report["names"] == ["slide", "brief", "vocab"] and report["version"] == "0.1.0"
    assert report["slide"] == [
        "_texpkg/plan-review.json",
        "_texpkg/plan.json",
        "_texpkg/state.json",
        "_texpkg/template.json",
        "lmroman10-regular.otf",
        "res/texpkg/DECK.txt",
        "res/texpkg/NOTICE.txt",
        "res/texpkg/acme-brand-provenance.sty",
        "res/texpkg/acme-brand.sty",
        "res/texpkg/acme-deck-provenance.sty",
        "res/texpkg/acme-deck.sty",
        "slide-review.tex",
        "slide.tex",
    ]
    assert "res/texpkg/acme-brand.sty" in report["vocab"] and "glossary.tex" in report["vocab"]
    assert report["stack"] == ["acme-deck-tex 0.1.0", "acme-brand-tex 1.2.0"]
    assert report["generator"].count(".") == 2


def retarget(project: pathlib.Path, old: str, new: str) -> None:
    """Rename text in every file of a copied project (a second dependent, a changed base)."""
    for path in project.rglob("*"):
        if (
            path.is_file()
            and path.suffix in (".py", ".toml", ".tex", ".json", ".txt")
            and old.encode() in path.read_bytes()
        ):
            path.write_text(path.read_text().replace(old, new))


def test_two_dependents_on_different_releases_of_the_base_import_side_by_side(tmp_path, monkeypatch):
    import json

    old = projects.wheel(projects.author_project(tmp_path / "brand-1"), tmp_path / "dist-1")
    new_project = projects.author_project(tmp_path / "brand-2")
    retarget(new_project, 'version = "1.2.0"', 'version = "1.3.0"')
    new = projects.wheel(new_project, tmp_path / "dist-2")
    wheels = []
    for number, brand in ((1, old), (2, new)):
        site = tmp_path / f"site-{number}"
        zipfile.ZipFile(brand).extractall(site)
        monkeypatch.syspath_prepend(str(site))
        project = deck(tmp_path, f"deck-{number}")
        retarget(project, "acme-brand-tex==1.2.0", f"acme-brand-tex=={'1.2.0' if number == 1 else '1.3.0'}")
        if number == 2:
            retarget(project, "acme_deck_tex", "acme_deck2_tex")
            retarget(project, "acme-deck-tex", "acme-deck2-tex")
        wheels.append(projects.wheel(project, tmp_path / f"deck-dist-{number}"))
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
            del sys.modules[name]
        monkeypatch.undo()
    python = venvs.clean_venv(tmp_path / "venv")
    for wheel in wheels:
        venvs.install(python, wheel)
    code = (
        "import json\n"
        "import acme_deck_tex as a, acme_deck2_tex as b\n"
        "from acme_deck_tex._embedded import acme_brand_tex as ba\n"
        "from acme_deck2_tex._embedded import acme_brand_tex as bb\n"
        "print(json.dumps([ba.__version__, bb.__version__, ba is bb, a.__version__, b.__version__]))\n"
    )
    assert json.loads(venvs.run(python, code, cwd=tmp_path)) == ["1.2.0", "1.3.0", False, "0.1.0", "0.1.0"]


def test_a_clash_along_the_chain_fails_the_build(brand_site, tmp_path):
    reused = deck(tmp_path, "names")
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(_with_title(reused), tmp_path / "dist")
    assert raised.value.code == "TP-B009"
    heavy = deck(tmp_path, "assets")
    (heavy / "src/acme_deck/assets/lockup.pdf").write_text("another lock-up")
    retarget(heavy, 'Asset("assets/DECK.txt"', 'Asset("assets/lockup.pdf", Role.GRAPHIC, "x"), Asset("assets/DECK.txt"')
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(heavy, tmp_path / "dist")
    assert raised.value.code == "TP-A002"


def _with_title(project: pathlib.Path) -> pathlib.Path:
    model = project / "src/acme_deck/model.py"
    model.write_text(
        model.read_text()
        + "\n\n@pkg.command\nclass Title(Command):\n"
        + '    """Clashes with the brand."""\n\n    cs = "abTitle"\n    text: Text\n    body = r"#text"\n'
    )
    return project


def test_the_dev_loop_builds_a_dependent_in_memory(tmp_path, acme_brand_tex):
    from texpkg_build.testing import load_declaration

    module = load_declaration("acme_deck:dist", version="2.0.0")
    try:
        slide = module.kinds.modules()["slide"]
        vocab = module.kinds.modules()["vocab"]
        assert module.kinds.names() == ("slide", "brief", "vocab") and vocab.NAME == "vocab"
        doc = vocab.create(tmp_path / "v", vocab.example())
        doc.save()
        assert (tmp_path / "v/res/texpkg/acme-brand.sty").is_file() and "abGlossary" in doc.render()
        assert slide.create(tmp_path / "s", slide.example()).render().count("\\adHeading") == 2
        assert [e.package for e in doc.stack.entries] == ["acme-deck-tex", "acme-brand-tex"]
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] in ("acme_deck_tex", "acme_deck")]:
            del sys.modules[name]


def test_a_chain_of_three_flattens_to_one_copy_of_each(brand_site, tmp_path, monkeypatch):
    import json

    middle = projects.wheel(deck(tmp_path), tmp_path / "middle-dist")
    site = tmp_path / "middle-site"
    zipfile.ZipFile(middle).extractall(site)
    monkeypatch.syspath_prepend(str(site))
    poster = deck(tmp_path, "poster")
    shutil.rmtree(poster / "src/acme_deck")
    package = poster / "src/acme_poster"
    package.mkdir()
    (package / "model.py").write_text(
        textwrap.dedent(
            '''
            import acme_deck_tex
            from acme_deck_tex.kinds import vocab
            from texmodel.body import Hole
            from texmodel.components import Command, Environment
            from texmodel.package import Package
            from texmodel.types import Text

            pkg = Package(
                "acme-poster", prefix="ap", version="1.0.0", date="2026/10/22", description="Posters",
                base=acme_deck_tex.dist.package,
            )


            @pkg.command
            class Line(Command):
                """A line of a poster, set as a term of the brand."""

                text: Text

                def body(self):
                    return vocab.Term.call(Hole("text"), "line")


            @pkg.environment
            class Slide(Environment):
                """A poster."""

                begin = r"\\begingroup"
                end = r"\\endgroup"
                children = [Line.times.at_least_one()]
            '''
        )
    )
    (package / "__init__.py").write_text(
        textwrap.dedent(
            """
            import acme_deck_tex

            from texpkg import Distribution, Kind

            from .model import Line, Slide, pkg

            dist = Distribution(
                name="acme-poster-tex",
                module="acme_poster_tex",
                package=pkg,
                kinds=(Kind("slide", Slide, (), lambda: Slide(Line(text="a"))),),
                base=acme_deck_tex.dist,
                expose=("vocab",),
            )
            """
        )
    )
    pyproject = poster / "pyproject.toml"
    for old, new in (
        ("acme_deck", "acme_poster"),
        ("acme-deck", "acme-poster"),
        ("acme-brand-tex==1.2.0", "acme-deck-tex==0.1.0"),
    ):
        pyproject.write_text(pyproject.read_text().replace(old, new))
    built = projects.wheel(poster, tmp_path / "dist")
    inside = projects.names(built)
    assert {n.split("/")[2] for n in inside if "/_embedded/" in n} == {
        "__init__.py",
        "texmodel",
        "texpkg",
        "acme_deck_tex",
        "acme_brand_tex",
    }
    assert not [n for n in inside if "/acme_deck_tex/_embedded/" in n]
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, built)
    code = (
        "import acme_poster_tex as m\n"
        "from acme_poster_tex.kinds import slide\n"
        "import json, sys\n"
        "doc = slide.create(sys.argv[1], slide.example()); doc.save()\n"
        "print(json.dumps([e.package for e in doc.stack.entries]))\n"
    )
    assert json.loads(venvs.run(python, code, tmp_path / "doc", cwd=tmp_path)) == [
        "acme-poster-tex",
        "acme-deck-tex",
        "acme-brand-tex",
    ]
    assert (tmp_path / "doc/res/texpkg/acme-brand.sty").is_file() and (
        tmp_path / "doc/res/texpkg/acme-deck.sty"
    ).is_file()
