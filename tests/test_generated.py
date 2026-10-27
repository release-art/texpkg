"""Declaration modules generated from data (K4): written by `texpkg-build generate`, refused when stale."""

import json
import os
import pathlib
import sys
import textwrap

import pytest
from typer.testing import CliRunner

from texpkg.errors import DeclarationError
from texpkg_build._internal import generated
from texpkg_build._internal.isolate import Isolation
from texpkg_build.cli import app
from texpkg_build.testing import check_isolated, load_declaration

from . import projects, spawn, venvs
from .helpers import FIXTURES
from .test_build import digest

SERIES = FIXTURES / "acme_series"
POINTER = "acme_series_gen:sources"


@pytest.fixture
def generator(tmp_path, monkeypatch):
    """A generator module `genmod` whose `fn(root)` returns what the test writes to `out.json`."""
    (tmp_path / "genmod.py").write_text(
        textwrap.dedent(
            """
            import json
            import pathlib


            def fn(root):
                return json.loads((pathlib.Path(__file__).parent / "out.json").read_text())


            X = 1
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    isolation = Isolation()
    yield isolation, tmp_path
    isolation.restore()
    sys.modules.pop("genmod", None)


def produce(generator, out):  # noqa: ANN001, ANN002, ANN201
    isolation, where = generator
    (where / "out.json").write_text(json.dumps(out))
    return generated.produce("genmod:fn", where, isolation)


def test_the_generator_is_run_and_each_file_gets_the_header(generator):
    assert produce(generator, {"_kinds/a.py": "A = 1\n"}) == {"_kinds/a.py": generated.HEADER + "A = 1\n"}


@pytest.mark.parametrize("path", ["/abs.py", "../up.py", "a/../../b.py", "notes.txt"])
def test_a_file_outside_the_package_or_not_python_is_refused(generator, path):
    with pytest.raises(DeclarationError) as raised:
        produce(generator, {path: "x"})
    assert raised.value.code == "TP-B013"


def test_a_generator_that_is_not_a_function_or_not_the_same_twice_is_refused(generator):
    isolation, where = generator
    with pytest.raises(DeclarationError) as raised:
        generated.produce("genmod:X", where, isolation)
    assert raised.value.code == "TP-B013" and "not a function" in str(raised.value)
    (where / "flip.py").write_text(
        "import itertools\nc = itertools.count()\n\ndef fn(root):\n    return {'a.py': str(next(c))}\n"
    )
    with pytest.raises(DeclarationError) as raised:
        generated.produce("flip:fn", where, isolation)
    assert "different the second time" in str(raised.value)
    sys.modules.pop("flip", None)


def test_files_are_written_once_and_a_generated_file_no_longer_produced_is_removed(tmp_path):
    root = tmp_path / "pkg"
    one = {"_kinds/a.py": generated.HEADER + "A = 1\n", "_kinds/b.py": generated.HEADER + "B = 2\n"}
    assert generated.write(root, one) == ["_kinds/a.py", "_kinds/b.py"]
    assert generated.write(root, one) == [] and generated.drift(root, one) == []
    (root / "mine.py").write_text("# hand-written\n")
    two = {"_kinds/a.py": one["_kinds/a.py"]}
    assert generated.drift(root, two) == ["_kinds/b.py: no longer generated"]
    assert generated.write(root, two) == ["_kinds/b.py"]
    assert not (root / "_kinds/b.py").exists() and (root / "mine.py").is_file()  # only generated files go


def test_a_missing_or_edited_file_is_drift_and_the_build_gate_refuses_it(tmp_path):
    root = tmp_path / "pkg"
    produced = {"a.py": generated.HEADER + "A = 1\n", "b.py": generated.HEADER + "B = 2\n"}
    generated.write(root, produced)
    (root / "a.py").write_text(generated.HEADER + "A = 99\n")
    (root / "b.py").unlink()
    assert generated.drift(root, produced) == ["a.py: differs from what the generator writes", "b.py: missing"]
    with pytest.raises(DeclarationError) as raised:
        generated.refuse_if_stale("genmod:fn", root, produced)
    assert raised.value.code == "TP-B012" and "texpkg-build generate" in raised.value.hint


# -- the committed files of the fixture, and a build from it -------------------------------------------------------


def test_the_committed_files_are_what_the_generator_writes():
    produced = generated.produce(POINTER, SERIES, Isolation())
    if os.environ.get("UPDATE_GOLDEN"):
        generated.write(SERIES, produced)
    assert generated.drift(SERIES, produced) == []


@pytest.fixture
def project(tmp_path):
    return projects.author_project(
        tmp_path / "project", declaration="acme_series", project="acme-series-tex", also=("acme_series_gen",)
    )


def test_a_wheel_holds_the_generated_classes_as_source_and_two_builds_are_byte_identical(project, tmp_path):
    first = projects.wheel(project, tmp_path / "dist-a")
    names = projects.names(first)
    for series in ("short", "long"):
        assert f"acme_series_tex/_declaration/_kinds/{series}.py" in names
        assert f"acme_series_tex/kinds/{series}.py" in names
    other = projects.author_project(
        tmp_path / "other", declaration="acme_series", project="acme-series-tex", also=("acme_series_gen",)
    )
    assert digest(first) == digest(projects.wheel(other, tmp_path / "dist-b"))


def run_cli(project, *args):  # noqa: ANN001, ANN002, ANN201
    return CliRunner().invoke(app, ["generate", "--root", str(project), *args])


def change_data(project):  # noqa: ANN001, ANN201
    path = project / "src/acme_series/series.json"
    data = json.loads(path.read_text())
    data["series"][0]["cards"] = [1, 4]
    path.write_text(json.dumps(data))


def test_the_build_refuses_files_that_are_stale_edited_or_missing(project, tmp_path):
    change_data(project)
    with pytest.raises(DeclarationError) as raised:
        projects.wheel(project, tmp_path / "dist")
    assert raised.value.code == "TP-B012" and "_kinds/short.py: differs from what the generator writes" in str(
        raised.value
    )


def test_generate_check_reports_drift_and_generate_repairs_it(project):
    assert run_cli(project, "--check").exit_code == 0
    change_data(project)
    (project / "src/acme_series/_kinds/short.py").write_text("# hand edit\n")
    (project / "src/acme_series/_kinds/long.py").unlink()
    checked = run_cli(project, "--check")
    assert checked.exit_code == 1 and "long.py: missing" in checked.output
    done = run_cli(project)
    assert done.exit_code == 0 and "wrote _kinds/short.py" in done.output
    assert run_cli(project, "--check").exit_code == 0
    assert ".times(1, 4)" in (project / "src/acme_series/_kinds/short.py").read_text()


def test_the_declaration_may_be_a_module_of_its_package_and_the_package_import_free(project, tmp_path):
    package = project / "src/acme_series"
    (package / "declaration.py").write_text((package / "__init__.py").read_text())
    (package / "__init__.py").write_text("")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace("acme_series:dist", "acme_series.declaration:dist"))
    assert run_cli(project, "--check").exit_code == 0
    change_data(project)
    assert run_cli(project, "--check").exit_code == 1 and run_cli(project).exit_code == 0
    assert "acme_series_tex/kinds/short.py" in projects.names(projects.wheel(project, tmp_path / "dist"))


def test_a_base_no_module_holds_is_refused_by_name(tmp_path):
    import dataclasses  # noqa: PLC0415

    import acme_brand  # noqa: PLC0415

    from texpkg_build import testing  # noqa: PLC0415

    copy = dataclasses.replace(acme_brand.dist)  # equal, but no module holds this one
    with pytest.raises(DeclarationError) as raised:
        testing._pointer_of(copy)  # noqa: SLF001
    assert raised.value.code == "TP-B003" and "acme-brand-tex" in str(raised.value)


def test_generate_reports_a_bad_pointer_and_a_failing_generator(project):
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('generate = "acme_series_gen:sources"', 'generate = "nothing"'))
    assert run_cli(project).exit_code != 0
    pyproject.write_text(pyproject.read_text().replace('generate = "nothing"', 'generate = "acme_series_gen:X"'))
    failed = run_cli(project)
    assert failed.exit_code == 1 and "TP-B013" in failed.output


GOOD = textwrap.dedent(
    """
    import acme_series_tex.kinds.short as short

    deck: short.ShortDeck = short.example()
    fact = short.ShortFact(text="Sly", accent=short.ShortAccent.BLUE)
    """
)
BAD = GOOD + "\nshort.LongDeck\nshort.ShortFact(text='x', accent='red')\n"


def pyright(python: pathlib.Path, source: pathlib.Path):  # noqa: ANN201
    done = spawn.run(
        [sys.executable, "-m", "pyright", "--pythonpath", python, "--outputjson", source], cwd=source.parent
    )
    return json.loads(done.stdout)["summary"]["errorCount"]


def test_a_consumer_module_type_checks_against_the_generated_classes(project, tmp_path):
    built = projects.wheel(project, tmp_path / "dist")
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, built)
    good, bad = tmp_path / "good.py", tmp_path / "bad.py"
    good.write_text(GOOD)
    bad.write_text(BAD)
    assert pyright(python, good) == 0
    assert pyright(python, bad) == 2  # an unknown name, and a string where the series' accents are an enum


def test_each_kind_of_the_generated_package_is_a_module_with_its_own_classes():
    module = load_declaration("acme_series:dist", version="0.1.0")
    assert module.kinds.names() == ("long", "short")
    assert module.kinds.modules()["short"].example().__class__.__name__ == "ShortDeck"


@pytest.mark.tex
@pytest.mark.timeout(300)
def test_every_generated_kind_compiles_with_only_its_own_payload(compiler, tmp_path):
    module = load_declaration("acme_series:dist", version="0.1.0")
    try:
        check_isolated(module, compiler, tmp_path)
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_series_tex"]:
            del sys.modules[name]


def test_a_generated_kind_lists_its_own_settable_values_and_options(tmp_path):
    from texmodel.types import Length  # noqa: PLC0415

    from texpkg.errors import NotAllowedError  # noqa: PLC0415

    module = load_declaration("acme_series:dist", version="0.1.0")
    try:
        short, long = module.kinds.modules()["short"], module.kinds.modules()["long"]
        doc = short.create(
            tmp_path / "s", short.example(), settings=[short.ShortGap(Length("5mm"))], options=["a4paper"]
        )
        assert "\\setlength{\\seShortGap}{5mm}" in doc.render() and "\\documentclass[a4paper]" in doc.render()
        with pytest.raises(NotAllowedError) as raised:  # another series' gap, and an option it does not offer
            short.create(tmp_path / "t", short.example(), settings=[long.LongGap(Length("5mm"))], options=["landscape"])
        assert [i["path"] for i in raised.value.items] == ["/settings/0", "/options/0"]
        stored = short.schema("serialization")
        assert [r["$ref"] for r in stored["properties"]["settings"]["items"]["oneOf"]] == ["#/$defs/ShortGapSetting"]
        assert long.schema()["properties"]["options"]["items"] == {"enum": ["a4paper", "landscape"]}
    finally:
        for name in [n for n in sys.modules if n.split(".")[0] == "acme_series_tex"]:
            del sys.modules[name]
