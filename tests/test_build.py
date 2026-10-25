"""The build: `pdm build` of an author's project (phase 2b: B1-B6, B8, V1)."""

import hashlib
import importlib
import json
import pathlib
import sys
import textwrap
import zipfile

import pdm.backend
import pytest

from texpkg.errors import DeclarationError
from texpkg_build.testing import load_declaration

from . import projects, spawn
from .helpers import FIXTURES

DECLARATION = [
    "_declaration/__init__.py",
    "_declaration/acme.tex",
    "_declaration/assets/NOTICE.txt",
    "_declaration/assets/lmroman10-regular.otf",
    "_declaration/assets/lockup.pdf",
    "_declaration/model.py",
    "_declaration/other/lockup.pdf",
    "_declaration/tokens.json",
]
MODULE = [
    "__init__.py",
    "_bound.py",
    "_sty/acme-brand.sty",
    "_version.py",
    "errors.py",
    "kinds/__init__.py",
    "kinds/expert.py",
    "kinds/vocab.py",
    *DECLARATION,
]


@pytest.fixture
def project(tmp_path: pathlib.Path) -> pathlib.Path:
    return projects.author_project(tmp_path / "project")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_wheel_holds_the_generated_module_and_the_declaration_not_the_sources(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    assert built.name == "acme_brand_tex-1.2.0-py3-none-any.whl"
    inside = projects.names(built)
    own = [n for n in inside if ".dist-info/" not in n and "/_embedded/" not in n]
    assert own == sorted(f"acme_brand_tex/{n}" for n in MODULE)
    assert {n.split("/")[2] for n in inside if "/_embedded/" in n} == {"texmodel", "texpkg", "__init__.py"}
    assert not any(n.startswith("acme_brand/") for n in inside)


def test_the_wheel_needs_only_pydantic(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    with zipfile.ZipFile(built) as z:
        metadata = z.read("acme_brand_tex-1.2.0.dist-info/METADATA").decode()
    requires = sorted(line for line in metadata.splitlines() if line.startswith("Requires-Dist"))
    assert requires == ["Requires-Dist: pydantic<3,>=2"]


def test_the_sty_in_the_wheel_is_the_sty_the_module_loaded_in_memory_holds(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    memory = load_declaration("acme_brand:dist", version="1.2.0")
    with zipfile.ZipFile(built) as z:
        shipped = z.read("acme_brand_tex/_sty/acme-brand.sty").decode()
    assert shipped == memory._bound.RELEASE.sty["acme-brand.sty"] and "v1.2.0" in shipped


def test_two_builds_are_byte_identical(tmp_path):
    first = projects.wheel(projects.author_project(tmp_path / "a"), tmp_path / "dist-a")
    second = projects.wheel(projects.author_project(tmp_path / "b"), tmp_path / "dist-b")
    assert digest(first) == digest(second)


def test_an_sdist_carries_the_sources_and_builds_the_same_wheel(project, tmp_path):
    archive = projects.sdist(project, tmp_path / "dist")
    unpacked = projects.unpack_sdist(archive, tmp_path / "unpacked")
    assert (unpacked / "src/acme_brand/model.py").is_file() and (unpacked / "pdm_build.py").is_file()
    assert not list(unpacked.rglob("_bound.py"))  # no generated module in it
    direct = projects.wheel(project, tmp_path / "dist-direct")
    from_sdist = projects.wheel(unpacked, tmp_path / "dist-sdist")
    assert digest(direct) == digest(from_sdist)


def test_the_build_leaves_no_trace_in_the_process(project, tmp_path):
    importlib.import_module("acme_brand")
    before = set(sys.modules)
    projects.wheel(project, tmp_path / "dist")
    assert not {n for n in set(sys.modules) - before if n.split(".")[0] in ("acme_brand", "acme_brand_tex")}
    assert sys.modules["acme_brand"].__file__ == str(
        FIXTURES / "acme_brand" / "__init__.py"
    )  # the one already imported
    assert str(project / "src") not in sys.path


def run_wheel(built: pathlib.Path, where: pathlib.Path, path: pathlib.Path):  # noqa: ANN201
    """The module a wheel holds, imported by a fresh interpreter that has only the wheel's directory added."""
    code = textwrap.dedent(
        """
        import json, pathlib, sys, acme_brand_tex as m
        from acme_brand_tex.kinds import expert
        doc = expert.create(sys.argv[1], expert.example())
        doc.save()
        root = pathlib.Path(sys.argv[1])
        saved = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
        report = {"version": m.__version__, "names": m.kinds.names(), "tex": doc.render("wide"), "saved": saved}
        print(json.dumps(report))
        """
    )
    return spawn.run([sys.executable, "-c", code, path], cwd=where, env={"PYTHONPATH": str(built)})


def test_an_installed_wheel_needs_nothing_of_the_authors_project(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    site = tmp_path / "site"
    zipfile.ZipFile(built).extractall(site)  # what an install does
    memory = load_declaration("acme_brand:dist", version="1.2.0")
    expert = memory.kinds.modules()["expert"]
    done = run_wheel(site, tmp_path, tmp_path / "doc")
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert report["version"] == "1.2.0" and report["names"] == ["expert", "vocab"]
    assert report["tex"] == expert.create(tmp_path / "again", expert.example()).render("wide")
    assert "res/acme/lockup.pdf" in report["saved"] and "lmroman10-regular.otf" in report["saved"]
    lockup = tmp_path / "doc/res/acme/lockup.pdf"
    assert lockup.read_bytes() == (project / "src/acme_brand/assets/lockup.pdf").read_bytes()


@pytest.mark.xfail(strict=True, reason="texmodel's TemplateRef reads a file by path: docs/texmodel-requests.md")
def test_a_wheel_runs_from_its_zip(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    assert run_wheel(built, tmp_path, tmp_path / "doc").returncode == 0


def broken(tmp_path: pathlib.Path, attribute: str) -> pathlib.Path:
    project = projects.author_project(tmp_path / "project")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("acme_brand:dist", f"acme_brand:{attribute}"))
    return project


@pytest.mark.parametrize(
    ("attribute", "code"),
    [("broken", "TP-B005"), ("clash", "TP-A002"), ("Deck", "TP-B003"), ("nothing", "TP-B003")],
)
def test_the_build_refuses_what_would_ship_broken(tmp_path, attribute, code):
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(broken(tmp_path, attribute), tmp_path / "dist")
    assert raised.value.code == code
    assert not list((tmp_path / "dist").glob("*.whl"))


def test_the_build_needs_a_pointer(tmp_path):
    project = projects.author_project(tmp_path / "project")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('distribution = "acme_brand:dist"', ""))
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(project, tmp_path / "dist")
    assert raised.value.code == "TP-B007"


def test_the_declaration_must_be_a_package(tmp_path):
    project = projects.author_project(tmp_path / "project")
    (project / "src" / "solo.py").write_text(
        "from acme_brand import dist\nimport dataclasses\nsolo = dataclasses.replace(dist, declared_in='solo')\n"
    )
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("acme_brand:dist", "solo:solo"))
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(project, tmp_path / "dist")
    assert raised.value.code == "TP-B004"


def test_an_editable_install_is_refused(project, tmp_path, monkeypatch):
    monkeypatch.chdir(project)
    with pytest.raises(DeclarationError) as raised:
        pdm.backend.build_editable(str(tmp_path / "dist"))
    assert raised.value.code == "TP-B008"


def test_a_generated_module_that_breaks_the_protocol_is_refused(tmp_path, monkeypatch):
    from texpkg_build._internal import checks

    module = load_declaration("acme_brand:dist")
    monkeypatch.delattr(module, "__version__")
    with pytest.raises(DeclarationError) as raised:
        checks.module_satisfies_the_protocols(module)
    assert raised.value.code == "TP-B006" and "package module" in str(raised.value)
    monkeypatch.setattr(module, "kinds", object())
    with pytest.raises(DeclarationError) as raised:
        checks.module_satisfies_the_protocols(module)
    assert "kinds" in str(raised.value)
    module = load_declaration("acme_brand:dist")
    monkeypatch.setattr(module.kinds.modules()["expert"], "NAME", None, raising=False)
    monkeypatch.delattr(module.kinds.modules()["expert"], "schema")
    with pytest.raises(DeclarationError) as raised:
        checks.module_satisfies_the_protocols(module)
    assert "kinds.expert" in str(raised.value)
