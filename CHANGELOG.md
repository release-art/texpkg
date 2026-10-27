# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
