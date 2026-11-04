# Known limitations

What texpkg does not do yet, and what it cannot do because of the layer below.

- **A hand edit's typed value is not read through TeX** (D9). `HandEdit.edit.fields` names the edited arguments with their text;
  `FieldEdit.value` is set only where texmodel reads it without a process, and texpkg spawns none (plan N4).
- **A profile kind's hand edits are named by the plan's path, not by a data path.** A profile's tree is expanded by a
  function before it is written, so a line belongs to a node of the base's tree; there is no general way back to the
  profile's own data (`HandEdit.path` is the plan path), so `Document.restore()` refuses a profile kind (`TP-D008`).
- **A profile reaches its base's values through the base's `_declaration`.** A kind module exports the classes a tree is
  made of, the value types they use and the kind's own `settable` values, not the package's other settings (`FactGap`), so a profile that locks one imports it from
  `<base module>._declaration`.
- **A local override goes stale by file, not by macro.** `Override.stale` says the package's `.sty` changed, not that the
  overridden macro did (plan O6). `Override.names` reads `\renewcommand` and its kin, not `\def` or `\let` (plan O7).
- **A field's type is read through texmodel's internals.** It has no public form of `FieldType`, so `_internal/fieldkinds.py`
  imports it, and a texmodel release can move it (`tests/test_fieldkinds.py` shows what is relied on; N5).
- **An override is seen where a document's directory holds it.** A `<name>-local.sty` or `<name>.sty` elsewhere on TeX's search
  path (`TEXINPUTS`) is not reported, and a root copy of a `.sty` does not mark the PDF (plan O4, O5).
- **A lock holds at the Python API only** (L5): a hand-written document can still `\renewcommand` a locked value.
- **Computed dynamic imports are not seen.** The build refuses `importlib.import_module("texmodel...")` with a literal, not
  one with a computed name.
- **A bad preamble slot is found at render, not at `create`.** Which slot an entry may sit in is texmodel's check
  (`TM-C008`), made when the `.tex` is written.

