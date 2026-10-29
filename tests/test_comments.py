"""Comment classes in a kind's trees: exported by the kind module and kept through `save` and `load`."""

import importlib

from acme_sheet.model import (
    Audit as DeclaredAudit,
    Heading,
    Sheet,
)
from texmodel.body import Comment

from texpkg._internal import state

from .test_migration import sheet  # noqa: F401


def test_a_kind_module_exports_the_packages_comment_classes(sheet):  # noqa: ANN001, ANN201, F811
    module = importlib.import_module(sheet.__name__)
    assert module.Audit is DeclaredAudit
    assert module.Heading is Heading


def test_a_comment_class_is_accepted_and_round_trips(sheet, tmp_path):  # noqa: ANN001, ANN201, F811
    module = importlib.import_module(sheet.__name__)
    tree = Sheet(module.Heading(text="Pump"), module.Ticks(met=()), module.Audit(who="Ana"), Comment("checked twice"))
    sheet.create(tmp_path / "d", tree).save()
    text = next((tmp_path / "d").glob("*.tex")).read_text()
    assert "audited by Ana" in text and "checked twice" in text
    loaded = sheet.load(tmp_path / "d")
    assert state.tree_state(loaded.tree) == state.tree_state(tree)
    assert [type(c).__name__ for c in loaded.tree.content] == ["Heading", "Ticks", "Audit", "Comment"]
