"""A consumer's type checker reads the generated module's types (P6, P23, K4): pyright over the module laid out as a
wheel would hold it."""

import json
import pathlib
import shutil
import sys

import pytest
from acme_brand import dist

from texpkg.contracts import Contracts
from texpkg_build._internal import generate

from . import spawn
from .helpers import FIXTURES

OK = """
from acme_brand_tex import kinds
from acme_brand_tex.kinds import expert, vocab
import acme_brand_tex
from texmodel.preamble import PreambleSlots
from texmodel.types import CMYK
from typing import Any
from texpkg.document import Document
from texpkg.protocol import KindModule, PackageModule

package: PackageModule = acme_brand_tex
kind: KindModule = expert
tree: expert.Deck = expert.example()
glossary: vocab.Glossary = vocab.example()
card = expert.Card(expert.Title("x"), expert.Fact("y", accent=expert.Accent.MOSS))
name: str = expert.NAME
saved: Document[expert.Deck] = expert.load("deck")
made: Document[expert.Deck] = expert.create("deck", tree)
with_more: Document[expert.Deck] = expert.create(
    "deck", tree, settings=[expert.Ink(CMYK(0, 0, 0, 1))], options=["a4paper"], preamble=PreambleSlots()
)
rendered: str = saved.render("compact")
new: Document[expert.Deck] = saved.replace(tree)
anything: Document[Any] = acme_brand_tex.load("deck")
schema: dict[str, object] = expert.schema(mode="serialization")
"""

BAD = """
from acme_brand_tex.kinds import expert, vocab
from acme_brand_tex._declaration import Compact
from texmodel.types import CMYK

wrong_tree: expert.Deck = vocab.example()
wrong_mode = expert.schema(mode="nonsense")
wrong_arguments = expert.changes("one", 2)
wrong_field = expert.Fact(1)
no_such = expert.FactGap
wrong_create = expert.create("deck", vocab.example())
wrong_replace = expert.load("deck").replace(vocab.example())
wrong_setting = expert.create("deck", expert.example(), settings=[Compact(True)])
wrong_option = expert.create("deck", expert.example(), options=["twocolumn"])
nothing_settable = vocab.create("v", vocab.example(), settings=[expert.Ink(CMYK(0, 0, 0, 1))])
"""


@pytest.fixture(scope="module")
def wheel_like(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("typing")
    module = root / dist.module
    for path, text in generate.sources(dist, "dist", "1.2.0", Contracts()).items():
        (module / path).parent.mkdir(parents=True, exist_ok=True)
        (module / path).write_text(text, encoding="utf-8")
    shutil.copytree(FIXTURES / "acme_brand", module / "_declaration", ignore=shutil.ignore_patterns("__pycache__"))
    return root


def pyright(root: pathlib.Path, name: str, source: str) -> list[str]:
    (root / name).write_text(source, encoding="utf-8")
    pyright_bin = pathlib.Path(sys.executable).parent / "pyright"
    done = spawn.run([pyright_bin, "--outputjson", "--pythonpath", sys.executable, name], cwd=root)
    report = json.loads(done.stdout)
    return [d["message"] for d in report["generalDiagnostics"] if d["severity"] == "error"]


def test_the_generated_module_satisfies_the_protocols_and_its_types_are_read(wheel_like):
    errors = pyright(wheel_like, "use_ok.py", OK)
    assert errors == [], "\n".join(errors)


def test_wrong_use_of_the_generated_module_is_an_error(wheel_like):
    errors = pyright(wheel_like, "use_bad.py", BAD)
    assert len(errors) == 10, errors
