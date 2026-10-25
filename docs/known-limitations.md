# Known limitations

What texpkg does not do yet, and what it cannot do because of the layer below.

- **A zipped wheel cannot be imported.** texmodel reads `TemplateRef` files by path (`docs/texmodel-requests.md`). Installed
  wheels are unpacked, so only a wheel put on `sys.path` as a zip is affected.
- **A hand edit's field and value are not read back** (D9). `HandEdit.value` is `None` until texmodel's field-level edits
  are committed.
- **A profile kind's hand edits are named by the plan's path, not by a data path.** A profile's tree is expanded by a
  function before it is written, so a line belongs to a node of the base's tree; there is no general way back to the
  profile's own data (`HandEdit.path` is the plan path).
- **A profile reaches its base's values through the base's `_declaration`.** A kind module exports the classes a tree is
  made of and the value types they use, not the package's settings (`FactGap`), so a profile that locks one imports it from
  `<base module>._declaration`.
- **A lock holds at the Python API only** (L5): a hand-written document can still `\renewcommand` a locked value.
- **Computed dynamic imports are not seen.** The build refuses `importlib.import_module("texmodel...")` with a literal, not
  one with a computed name.
- **Older stored data is not migrated yet** (phase 5a): `load` reads the current `data` version only.
