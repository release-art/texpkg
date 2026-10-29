# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-10-29

### Changed

- Requires `texmodel>=0.10.0`. Generated output and the goldens are unchanged by it. Wheels built from now on depend on `texmodel~=0.10.0`.
- The plan records that `Document`, errors and enums are texpkg's classes, shared by every package.

## [0.3.0] - 2026-10-29

### Added

- `HandEdit.fields`: texmodel's `FieldEdit`s (`arg`, `found`, the typed `value` where it is read) of a line changed inside one argument, `()`
  otherwise. `HandEdit.path` is documented as a data path into `Document.tree`.

### Changed

- Requires `texmodel>=0.9.0`. Generated output and the goldens are unchanged by it.
- Kind modules no longer re-export texmodel's classes (`Comment`, `Length`, `CMYK`, `Raw`, `Passthrough`): import them from texmodel, now one copy. The
  package's own comment classes are still exported. The generated `acme_tex.errors` is removed: import from `texpkg.errors`.
  `Distribution.layout` is removed (`texpkg.layout.LAYOUT`).
- Importing a dependent checks the installed base: the `interface` current the dependent was built on (`Contracts.base_interface`, `[base] interface`
  in `versions.toml`) must lie in the base's `current - age` to `current`, else `TP-C007`.
- A wheel no longer embeds texmodel, texpkg or its base. It depends on what its code imports, each named explicitly: `texpkg~=X.Y.Z` and `texmodel~=X.Y.Z` (`X.Y.Z` the release it was built with, so the same
  `X.Y`), `pydantic>=2,<3` and, for a dependent, its base's wheel from the release it was built on up to the next breaking one (`>=1.2.0,<2`; before 1.0, `>=0.1.0,<0.2`).
  One texmodel is installed, so a consumer's own `Length`, `Comment` or `FieldEdit` is the class a
  tree checks. The build needs texpkg, texmodel and the base installed to name the releases (`TP-B015` otherwise).
- The `.tex` header names the texmodel installed, not the package's release: a texmodel upgrade changes every document's header, which `check`
  reports and `save` rewrites.
- A dependent in memory (`load_declaration`) imports its base as a module: the base's wheel, or its own `load_declaration` first.

### Removed

- Embedding and rewriting imports: `texpkg_build._internal.embed`, `TP-E001`, `TP-E003` and `TP-E006` are retired, and `TP-E004` now says a wheel
  depends on texpkg and its bases. A declaration may read distribution metadata.
- Two dependents on different releases of one base can no longer be installed side by side: one base is installed.
- `HandEdit.value`, which was never set: read `HandEdit.fields[i].value`.

## [0.2.6] - 2026-10-28

### Fixed

- A kind module also exports the texmodel classes a consumer builds values with: those a field is annotated with (`Length`, `CMYK`, `Raw`, ...), the
  payload type of a value (`Ink(CMYK(...))`) and `Passthrough` where a grammar accepts it. They are the embedded texmodel's; an instance of the
  consumer's own texmodel is refused by the tree.
- A kind module exports `Comment` and the comment classes its package declares (`Package(comments=[...])`). A consumer's own `Comment` was a
  different class from the embedded texmodel's, so the tree was refused ("Comment is not allowed here"). Declaring a comment class needs no
  field on `Distribution`: it is the texmodel `Package`'s, and it round-trips through `save` and `load`.

## [0.2.5] - 2026-10-28

### Added

- `doc.template_changes()` also reports each package of the stack with its release and `output` pair (`package acme-brand-tex: 1.2.0 (output 1.0) -> 1.2.1
  (output 1.1)`), so a release that changes only the layout is visible for a saved document.

### Changed

- Requires `texmodel>=0.8.0`, which indents a document's body by depth (two spaces per level). A saved document written by an earlier release is
  not reported as hand-edited: its `.tex` agrees with the plan saved beside it, `check` lists the files as changed and `save` rewrites them. The
  plan's column spans move with the indent; a plan saved by an earlier texmodel must still be readable by it.
  Packages classify the rebuilt `output` as `revision`: the typeset result is the same.

## [0.2.4] - 2026-10-28

### Added

- A published constant (`Distribution(public=)`) may also be a dataclass or pydantic instance. The `interface` snapshot writes it as
  `{"$class": name, ...fields}`; a value of another class is breaking, a new value of the same class a revision.

## [0.2.3] - 2026-10-28

### Added

- `Distribution(public="pkg.module")`: constants the package publishes. The module's `__all__` names them; the generated module re-exports them as
  `acme_tex.public`, typed, so consumers import no private path. Values are JSON-like (`TP-B014` otherwise; `TP-K022`: not a module of the declaring
  package). They are part of the `interface` snapshot: a name removed or a value of another type is breaking, a name added compatible, a new value
  of the same type a revision.

## [0.2.2] - 2026-10-28

### Added

- `Variant(name, settings, options=())`: class options a variant's `.tex` is written with, after the document's own and without repeating
  them; they need not be among the kind's `options`.
- `Kind(defaults=(Gap(...),))`: where a document of the kind starts for a settable value, written after the presets and the variant's settings and
  before the document's own, which win. The template state keeps them: when a release changes one, a document that does not set the value
  follows, keeps the old value as its own setting, or is asked about it (`default_changes`, keyed by the value's class name, path
  `/defaults/<class>`). `TP-K021`: a default for a value that is not settable.

### Fixed

- An editable install of a texpkg project (`pdm install` with the project in a dev group) is no longer refused: the hook makes no module for it
  and the project depends on `texpkg`, so tooling can import the declaration and the generator from the checkout. `TP-B008` is retired.

## [0.2.1] - 2026-10-27

### Added

- `Kind(locked_preamble=PreambleSlots(...))`: typed preamble entries every document of the kind is written with (a `\DocumentMetadata` the `.sty`
  cannot carry), in the slots given, after the layout's lines and before the document's own, and in no stored data. A document that
  names a locked entry class is refused (`TP-D007`, unresolved at `load`); a misplaced, `Raw`, repeated or also-allowed entry, and a
  profile that locks or allows what its base kind locks, are `TP-K020`.

### Fixed

- `[tool.texpkg] distribution = "pkg.declaration:dist"`, a declaration in a module of its package, works: `texpkg-build generate` and
  the build find the generated files in the declaring package (not in a directory named after the module), and the generated module
  imports the declaration from that module. The package's `__init__` can stay import-free, so a generator can share its pure modules.

## [0.2.0] - 2026-10-27

### Fixed

- A document of a kind with no graphic no longer gets `\graphicspath`, which a package that does not load `graphicx` cannot compile.
- The declaration directory the build copies is the package, also when `Distribution(root=)` names a subdirectory.

### Changed

- Requires `texmodel>=0.7.0`. Commands take keyword arguments (`Fact(text="a")`): a kind's classes, examples and a generator's source use them.
  A derived package is declared `Package(base=)`, no longer `require()` of the base's package, and its `Distribution(base=)` must be
  the distribution of that package (`TP-K019`).
- A kind's `settable` values may be the base package's, a profile kind's included (`TP-K018` otherwise).

### Added

- A document carries settings, options and preamble entries within what its kind lists: `Kind(settable=, options=, preamble=)`,
  `create(..., settings=, options=, preamble=)` typed per kind, `doc.settings`, `doc.options`, `doc.preamble` and `replace`. They
  are stored beside `tree` (texmodel's shapes), in the kind's schemas and contracts, in `state["$extras"]` for a migration, and a
  hand edit of a line they wrote has a data path. `NotAllowedError` (`TP-D007`), `TP-K016` to `TP-K018`.
- Kinds generated from data (K4): `[tool.texpkg] generate = "module:function"` names a function from the declaring package's directory
  to `{path: source}`; `texpkg-build generate [--check]` writes the files, and `pdm build` refuses one that is missing, stale,
  hand-edited or left over (`TP-B012`) and a generator that is not deterministic (`TP-B013`). Each generated file starts with
  `# fmt: off`, so a formatter leaves it as the generator wrote it.

## [0.1.0] - 2026-10-26

### Added

- The package layout: `texpkg` (the run time) and `texpkg_build` (the build), with import contracts, the `build` extra
  and the `texpkg-build` entry point.
- `Asset`, `Role`, the layout (`res/texpkg/`) and a payload that is written whole or not at all, compared by
  content and checked for stale, missing and extra files.
- The declaration (`Distribution`, `Kind`, `Variant`, `Asset`), checked when it is built; the generated module's fixed
  surface (`kinds.names()`, `kinds.modules()`, a kind's `NAME`, classes, `schema()`, `example()`, `variants()`,
  `changes()`, `__version__`, `CONTRACTS`, `errors`) with its protocols; `Document.render` and `replace`; the two schemas of
  a kind; `texpkg_build.testing.load_declaration`.
- The document directory: a kind's `create`, `load` and the package's generic `load`; `Document.save`, `check`,
  `hand_edits`, `template_changes`, `defaults` and `stack`; the state (every value written, defaults marked per node), the
  template state, the last three saves as history, the plan of each `.tex` and the hand-edit check.
- The build: `texpkg_build.hook` (`pdm_build_initialize`, `pdm_build_update_files`) generates the wheel's module from the
  declaration named in `[tool.texpkg] distribution`, renders the `.sty`, copies the declaration into it, and refuses a
  missing asset, a payload clash, a declaration that is not a package and a module that breaks the protocol.
- Embedding: a wheel carries one private copy each of texmodel, texpkg's run time and the base chain under `_embedded`,
  with every import of them rewritten as a relative import (found with `ast`), texmodel's `GENERATOR_VERSION` set to the version it was built from, and needs only pydantic. A distribution can name a `base`, expose its kinds, and the build refuses a name or
  payload path used twice along the chain, an absolute import of the package itself, a read of the distribution's metadata
  and an import the wheel does not carry.
- Profiles: `Kind(..., expand=, over=)` for a kind that expands to a kind of the base, written with the base kind's
  presets and its own locks (`render`, `save`, the payload of both kinds); `Design.load`, validated at build; the law
  `texpkg_build.testing.check_expansion`. `docs/known-limitations.md` lists what is not done.
- Provenance: every package declares `\<prefix>ProvenanceInfo`, `save` writes `<package>-provenance.sty` for each
  package of the stack with a stamp (`save(stamp=)`, default the release's version) and a time (`now=`, default the clock),
  keeps the time while nothing is materialised again, and adds the text to the PDF's Info dictionary as `/<Prefix>Provenance`
  when PDF management is active; `check(stamp=)` compares the file by stamp.
- Migrations on `load`: `load(path, *, migrations=, default_changes=)` runs the kind's and the consumer's migrations for each
  `data` boundary crossed, applies the consumer's `DefaultChange` policy (`FOLLOW`, `FREEZE`, `ASK`, per document or per
  field) to values still marked as defaults, validates the result whole, and raises `MigrationError` listing every
  unresolved item, writing nothing.
- Contract versions: `texpkg-build contracts` writes `contracts/next` (both schemas of every kind, the interface, each
  example's data and rendered `.tex`, the output fingerprint, the versions file with the proposed `current:revision:age`
  triples and release number) against the newest frozen release, `--freeze` keeps it as `contracts/<release>`; the build
  refuses a stale snapshot, an unclassified output change, a release without its frozen snapshot, a number that understates
  the contracts and a base that no longer supports the interface relied on; a wheel carries `CONTRACTS` and every frozen
  snapshot, and `changes(old, new)` explains two `data` versions; the base's migrations run at the matching boundary of an
  exposed kind.
- `export(dest, *, now=, stamp=)`: the whole payload in the layout, the provenance files, and for each kind a template (its example
  rendered with the kind's settings) and a README generated from its classes; refused whole if a file is missing.
- `texpkg_build.testing.check_isolated`: each kind's example in each variant saved with only its kind's payload and
  compiled with no search path; it fails on a missing file and on a font embedded from outside the directory.
- A built module exports `migration`, `Migrated`, `Unresolved` and `DefaultChange` (its own copies), so a consumer that has
  only the wheel can write a migration for `load`.
- A document directory places `.sty`, graphics and notes in `res/texpkg/` and fonts at its root; `Distribution(root=)` is the directory asset paths are relative to (default: the declaring module's), inside the declaring package.
- `Kind(stem=)` names the kind's `.tex` files; the default is the root class lower-cased.
- Loading a document whose stored state holds a field the model no longer has is a `MigrationError` (`TP-M003`, the field's path and value), never a silent loss; a migration removes it on purpose.
- A wheel runs from a zip. Requires `texmodel>=0.4.0`.
