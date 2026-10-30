"""Two synthetic wheels end to end: `acme-brand-tex` and `acme-deck-tex` built on it.

Each is built from its project and installed into environments that have only pydantic; documents are made, saved and
compiled; then a new release of the brand is adopted by the documents the old one saved.
"""

import json
import pathlib
import sys
import textwrap
import zipfile

import pytest
from typer.testing import CliRunner

from texpkg_build.cli import app

from . import projects, venvs

pytestmark = [pytest.mark.tex, pytest.mark.timeout(600)]

USE = """
import json, sys
import acme_brand_tex, acme_deck_tex
out = {}
for module in (acme_brand_tex, acme_deck_tex):
    for name, kind in module.kinds.modules().items():
        tree = kind.example()
        if (module.__name__, name) == ("acme_brand_tex", "expert"):  # a colour the author chose, to be dropped later
            pinned = kind.Card(kind.Title(text="Pinned"), kind.Fact(text="explicit", accent=kind.Accent.SLATE))
            tree = kind.Deck(*tree.content, pinned)
        doc = kind.create(f"{sys.argv[1]}/{module.__name__}/{name}", tree)
        doc.save()
        out[f"{module.__name__}/{name}"] = kind.variants()
print(json.dumps(out))
"""

ADOPT = textwrap.dedent(
    """
    import json, sys
    import acme_brand_tex
    from acme_brand_tex import Migrated, migration
    from texpkg.errors import HandEditError, MigrationError
    from acme_brand_tex.kinds import expert

    root = sys.argv[1] + "/acme_brand_tex/expert"
    report = {}
    try:
        expert.load(root)
    except MigrationError as error:
        report["unresolved"] = [[u.path, u.value, u.boundary] for u in error.unresolved]

    @migration(to=2)
    def sand_is_moss(state):
        for node in walk(state):
            if node.get("accent") == "SLATE" and "$defaults" not in node:
                node["accent"] = "MOSS"
        return Migrated(state)

    def walk(node):
        yield node
        for child in node.get("content", ()):
            yield from walk(child)

    doc = expert.load(root, migrations=[sand_is_moss])
    report["accents"] = [f.accent.name for card in doc.tree.content[1:] for f in card.content[1:]]
    report["defaults"] = list(doc.defaults)
    report["changes"] = sorted(c.setting for c in doc.template_changes())
    report["hand_edits"] = [[e.path, e.edit.found] for e in doc.hand_edits()]
    try:
        doc.save()
    except HandEditError as error:
        report["refused"] = len(error.edits)
    doc.save(force=True)
    report["data"] = json.load(open(root + "/_texpkg/state.json"))["data"]
    report["history"] = json.load(open(root + "/_texpkg/history/1/state.json"))["data"]
    print(json.dumps(report))
    """
)


def contracts(project: pathlib.Path, *flags: str) -> None:
    result = CliRunner().invoke(app, ["contracts", "--root", str(project), *flags])
    assert result.exit_code == 0, result.output


def set_version(project: pathlib.Path, version: str) -> None:
    import re

    file = project / "pyproject.toml"
    file.write_text(re.sub(r'^version = ".*"$', f'version = "{version}"', file.read_text(), flags=re.MULTILINE))


async def test_two_wheels_are_installed_used_saved_compiled_and_a_new_release_is_adopted(
    compiler, tmp_path, monkeypatch
):
    # -- the first release of both -----------------------------------------------------------------------------
    brand = projects.author_project(tmp_path / "brand")
    set_version(brand, "0.1.0")
    contracts(brand, "--freeze")
    brand_1 = projects.wheel(brand, tmp_path / "dist-brand-1")
    site = tmp_path / "site-1"
    zipfile.ZipFile(brand_1).extractall(site)
    monkeypatch.syspath_prepend(str(site))
    deck = projects.author_project(tmp_path / "deck", declaration="acme_deck", project="acme-deck-tex")
    set_version(deck, "0.1.0")
    contracts(deck, "--freeze")
    deck_1 = projects.wheel(deck, tmp_path / "dist-deck")
    monkeypatch.undo()
    for name in [n for n in sys.modules if n.split(".")[0] == "acme_brand_tex"]:
        del sys.modules[name]

    # -- used, saved and compiled with nothing else installed ---------------------------------------------------
    first = venvs.clean_venv(tmp_path / "venv-1")
    venvs.install(first, brand_1)
    venvs.install(first, deck_1)
    used = json.loads(venvs.run(first, USE, tmp_path / "docs", cwd=tmp_path))
    assert sorted(used) == [
        "acme_brand_tex/expert",
        "acme_brand_tex/vocab",
        "acme_deck_tex/brief",
        "acme_deck_tex/slide",
        "acme_deck_tex/vocab",
    ]
    sources = sorted((tmp_path / "docs").rglob("*.tex"))
    assert (
        len(sources) == 3 + 1 + 1 + 2 + 1
    )  # expert and its two variants, vocab, then the deck's brief, slide and its variant, and vocab
    for source in sources:
        (
            await compiler.compile(
                source, tmp_path / "out" / source.parent.parent.name / source.parent.name / source.stem
            )
        ).raise_for_status()

    # -- a hand edit, then a new release of the brand ----------------------------------------------------------
    deck_tex = tmp_path / "docs/acme_brand_tex/expert/deck.tex"
    deck_tex.write_text(deck_tex.read_text().replace("\\abTitle{Fox}", "\\abTitle{Fox, edited}"))
    model = brand / "src/acme_brand/model.py"
    text = model.read_text()
    text = text.replace('    SLATE = "ab-slate"\n    MOSS = "ab-moss"\n', '    MOSS = "ab-moss"\n')
    text = text.replace("accent: Accent = Accent.SLATE", "accent: Accent = Accent.MOSS")
    model.write_text(text)
    contracts(brand)
    edit = brand / "contracts/next/versions.toml"
    edit.write_text(edit.read_text().replace('change = ""', 'change = "current"'))
    contracts(brand, "--freeze")
    set_version(brand, "0.2.0")
    brand_2 = projects.wheel(brand, tmp_path / "dist-brand-2")

    second = venvs.clean_venv(tmp_path / "venv-2")
    venvs.install(second, brand_2)
    report = json.loads(venvs.run(second, ADOPT, tmp_path / "docs", cwd=tmp_path))
    assert report["unresolved"] == [["/content/3/content/1/accent", "SLATE", "validation"]]
    assert report["accents"] == ["MOSS", "MOSS", "MOSS", "MOSS"]
    assert report["defaults"] == ["/content/1/content/1/accent", "/content/2/content/1/accent"]
    assert report["changes"] and any(c.startswith("default Fact.accent") for c in report["changes"])
    assert report["hand_edits"] == [["/content/1/content/0", "    \\abTitle{Fox, edited}"]]
    assert report["refused"] == 1 and report["data"] == 2 and report["history"] == 1
    (
        await compiler.compile(tmp_path / "docs/acme_brand_tex/expert/deck.tex", tmp_path / "out" / "after")
    ).raise_for_status()
