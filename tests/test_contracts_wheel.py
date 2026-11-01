"""The contracts wheel (V38): the frozen snapshots of every release in a wheel of their own, which the package depends
on at its own version."""

import pathlib
import re
import zipfile

import pytest
from typer.testing import CliRunner

from texpkg import errors
from texpkg_build.cli import app

from . import projects, venvs

HISTORY = "acme_brand_tex_contracts"


@pytest.fixture
def brand(tmp_path):
    project = projects.author_project(tmp_path / "brand")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            'distribution = "acme_brand:dist"', 'distribution = "acme_brand:dist"\ncontracts = "wheel"'
        )
    )
    return project


def contracts(project: pathlib.Path, *flags: str):  # noqa: ANN201
    return CliRunner().invoke(app, ["contracts", "--root", str(project), *flags])


def set_version(project: pathlib.Path, version: str) -> None:
    pyproject = project / "pyproject.toml"
    pyproject.write_text(re.sub(r'^version = ".*"$', f'version = "{version}"', pyproject.read_text(), flags=re.M))


def released(project: pathlib.Path, tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """The contracts wheel and the wheel of release 0.1.0."""
    set_version(project, "0.1.0")
    result = contracts(project, "--freeze", "--wheel", str(tmp_path / "history"))
    assert result.exit_code == 0, result.output
    return next((tmp_path / "history").glob("*.whl")), projects.wheel(project, tmp_path / "dist")


def read(wheel: pathlib.Path, suffix: str) -> str:
    with zipfile.ZipFile(wheel) as z:
        (name,) = (n for n in z.namelist() if n.endswith(suffix))
        return z.read(name).decode()


def test_the_wheel_holds_every_frozen_snapshot_and_is_a_function_of_them(brand, tmp_path):
    history, _ = released(brand, tmp_path)
    assert history.name == f"{HISTORY}-0.1.0-py3-none-any.whl"
    names = projects.names(history)
    assert f"{HISTORY}/0.1.0/versions.toml" in names and f"{HISTORY}/__init__.py" in names
    assert not any("/next/" in n for n in names)
    assert "Name: acme-brand-tex-contracts" in read(history, "METADATA")
    again = contracts(brand, "--wheel", str(tmp_path / "again"))
    assert again.exit_code == 0, again.output
    assert (tmp_path / "again" / history.name).read_bytes() == history.read_bytes()


def test_a_release_depends_on_its_contracts_wheel_and_does_not_carry_the_snapshots(brand, tmp_path):
    _, built = released(brand, tmp_path)
    assert "Requires-Dist: acme-brand-tex-contracts==0.1.0" in read(built, "METADATA")
    assert not any("_contracts/" in n for n in projects.names(built))
    assert f"files('{HISTORY}')" in read(built, "_bound.py")


def test_both_wheels_installed_the_package_reads_its_history_from_the_contracts_wheel(brand, tmp_path):
    history, built = released(brand, tmp_path)
    python = venvs.clean_venv(tmp_path / "venv")
    venvs.install(python, history)
    venvs.install(python, built)
    code = (
        "from acme_brand_tex import _bound, kinds\n"
        "from texpkg._internal import snapshots\n"
        "print(snapshots.releases(_bound._SNAPSHOTS), kinds.modules()['expert'].changes(1, 1))"
    )
    assert venvs.run(python, code, cwd=tmp_path).startswith("['0.1.0']")


def test_the_contracts_wheel_is_the_base_of_the_next_release(brand, tmp_path):
    history, _ = released(brand, tmp_path)
    other = projects.author_project(tmp_path / "other")
    result = contracts(other, "--base", str(history))
    assert result.exit_code == 0 and "copied contracts/0.1.0" in result.output
    assert (other / "contracts/0.1.0/output.json").is_file()


def test_a_development_build_carries_its_snapshots_since_its_release_has_no_wheel(brand, tmp_path):
    released(brand, tmp_path)
    contracts(brand)
    set_version(brand, "0.1.1.dev1")
    built = projects.wheel(brand, tmp_path / "dev")
    assert any("_contracts/0.1.0/" in n for n in projects.names(built))
    assert "contracts" not in read(built, "METADATA").replace("acme-brand-tex", "")


def test_there_is_nothing_to_put_in_a_wheel_before_a_freeze(brand, tmp_path):
    result = contracts(brand, "--wheel", str(tmp_path / "history"))
    assert result.exit_code == 1 and "TP-C011" in result.output


def test_the_setting_is_one_of_two(brand, tmp_path):
    pyproject = brand / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('contracts = "wheel"', 'contracts = "both"'))
    with pytest.raises(errors.DeclarationError) as raised:
        projects.wheel(brand, tmp_path / "dist")
    assert raised.value.code == "TP-B016"
