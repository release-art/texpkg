# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- A document of a kind with no graphic no longer gets `\graphicspath`, which a package that does not load `graphicx` cannot compile.
- The declaration directory the build copies is the package, also when `Distribution(root=)` names a subdirectory.

### Added

- Kinds generated from data (K4): `[tool.texpkg] generate = "module:function"` names a function from the declaring package's directory
  to `{path: source}`; `texpkg-build generate [--check]` writes the files, and `pdm build` refuses one that is missing, stale,
  hand-edited or left over (`TP-B012`) and a generator that is not deterministic (`TP-B013`).
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
