"""A wheel depends on texpkg and its base (B7); the declaration is copied into it and checked (B4, P19)."""

import importlib.metadata
import json
import pathlib
import re
import shutil
import sys
import textwrap
import zipfile

import pytest

from texpkg.errors import DeclarationError
from texpkg_build._internal import assemble

from . import projects, venvs


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("from acme_deck import x\n", "TP-E002"),
        ("import acme_deck_tex\n", "TP-E002"),
        ("import numpy\n", "TP-E004"),
        ("import importlib\nimportlib.import_module('acme_deck.spec')\n", "TP-E005"),
        ("__import__('acme_deck')\n", "TP-E005"),
    ],
)
def test_the_build_refuses_code_that_would_break_in_a_copy(source, code):
    with pytest.raises(DeclarationError) as raised:
        assemble.scan_declaration(source, "x.py", {"acme_deck", "acme_deck_tex"}, {"texmodel", "texpkg"})
    assert raised.value.code == code


def test_code_that_is_fine_in_a_copy_passes():
    source = textwrap.dedent(
        """
        import os, pydantic
        import importlib
        import importlib.metadata
        from texmodel import spec
        from acme_brand_tex import dist
        from . import x
        importlib.import_module(name)
        importlib.import_module('texmodel.spec')
        """
    )
    assemble.scan_declaration(source, "x.py", {"acme_deck"}, {"texmodel", "texpkg", "acme_brand_tex"})


# -- wheels ----------------------------------------------------------------------------------------------------------


def deck(tmp_path: pathlib.Path, name: str = "deck") -> pathlib.Path:
    return projects.author_project(tmp_path / name, declaration="acme_deck", project="acme-deck-tex")


def requires(wheel: pathlib.Path) -> list[str]:
    with zipfile.ZipFile(wheel) as z:
        metadata = z.read(next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))).decode()
    return sorted(
        line.removeprefix("Requires-Dist: ") for line in metadata.splitlines() if line.startswith("Requires-Dist")
    )


def test_a_wheel_depends_on_what_it_imports_and_holds_no_copy_of_any(brand_site, tmp_path):
    built = projects.wheel(deck(tmp_path), tmp_path / "dist")
    release = {n: re.findall(r"\d+\.\d+\.\d+", importlib.metadata.version(n))[0] for n in ("texpkg", "texmodel")}
    assert requires(built) == [
        "acme-brand-tex<2,>=1.2.0",
        "pydantic<3,>=2",
        f"texmodel~={release['texmodel']}",
        f"texpkg~={release['texpkg']}",
    ]
    inside = projects.names(built)
    assert not [n for n in inside if "_embedded" in n or "/texmodel/" in n or "/texpkg/" in n]
    assert "acme_deck_tex/_declaration/model.py" in inside and "acme_deck_tex/_bound.py" in inside
    with zipfile.ZipFile(built) as z:
        bound = z.read("acme_deck_tex/_bound.py").decode()
        imports = z.read("acme_deck_tex/_declaration/model.py").decode()
    assert "from acme_brand_tex import _bound as _base" in bound and "_embedded" not in bound + imports


SCRIPT = """
import importlib.util, json, pathlib, sys
import acme_deck_tex as m
from acme_deck_tex.kinds import slide, vocab
from texmodel import body, plan
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
    "shared": [slide.Comment is body.Comment, slide.FieldEdit is plan.FieldEdit],
}))
"""


def test_wheels_install_into_an_environment_with_texpkg_and_run(brand_site, tmp_path):
    built = projects.wheel(deck(tmp_path), tmp_path / "dist")
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, brand_site)
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
    assert report["shared"] == [True, True]  # one texmodel: a consumer's classes are the tree's own


def retarget(project: pathlib.Path, old: str, new: str) -> None:
    """Rename text in every file of a copied project (a second dependent, a changed base)."""
    for path in project.rglob("*"):
        if (
            path.is_file()
            and path.suffix in (".py", ".toml", ".tex", ".json", ".txt")
            and old.encode() in path.read_bytes()
        ):
            path.write_text(path.read_text().replace(old, new))


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


def test_a_chain_of_three_is_installed_wheel_by_wheel(brand_site, tmp_path, monkeypatch):
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
    assert "acme-deck-tex<0.2,>=0.1.0" in requires(built)  # the brand comes through the deck
    python = venvs.clean_venv(tmp_path / "venv")
    for wheel in (brand_site, middle, built):
        venvs.install(python, wheel)
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


def test_a_build_needs_texpkg_and_the_base_installed_to_pin_them(monkeypatch):
    from texpkg_build import hook

    def missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with pytest.raises(DeclarationError) as raised:
        hook.requirements(__import__("acme_brand").dist)
    assert raised.value.code == "TP-B015" and "texpkg" in str(raised.value)


def test_a_dependent_refuses_a_base_that_no_longer_supports_the_interface_it_was_built_on(acme_brand_tex):
    from texpkg.contracts import Contracts, Pair, Triple
    from texpkg_build.testing import load_declaration

    def deck_on(base_interface: int) -> None:
        for name in [n for n in sys.modules if n.split(".")[0] in ("acme_deck_tex", "acme_deck")]:
            del sys.modules[name]
        load_declaration("acme_deck:dist", version="2.0.0", contracts=Contracts(base_interface=base_interface))

    deck_on(0)  # nothing recorded: nothing to check
    deck_on(1)  # the installed brand is at interface 1
    with pytest.raises(DeclarationError) as raised:
        deck_on(2)  # built on a newer interface than is installed
    assert raised.value.code == "TP-C007" and "acme-brand-tex" in str(raised.value)
    sys.modules.pop("acme_brand_tex")
    load_declaration("acme_brand:dist", version="1.4.0", contracts=Contracts(Triple(1), Triple(3, 0, 1), Pair(1)))
    deck_on(2)  # the installed brand supports 2 to 3
    with pytest.raises(DeclarationError) as raised:
        deck_on(1)  # which no longer includes 1
    assert "supports 2 to 3" in str(raised.value)
