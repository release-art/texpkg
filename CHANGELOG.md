# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The package layout: `texpkg` (the run time) and `texpkg_build` (the build), with import contracts, the `build` extra
  and the `texpkg-build` entry point (phase 0).
- `Asset`, `Role`, the `Flat` and `Project` layouts and a payload that is written whole or not at all, compared by
  content and checked for stale, missing and extra files (phase 1).
- The declaration (`Distribution`, `Kind`, `Variant`, `Asset`), checked when it is built; the generated module's fixed
  surface (`kinds.names()`, `kinds.modules()`, a kind's `NAME`, classes, `schema()`, `example()`, `variants()`,
  `changes()`, `__version__`, `CONTRACTS`, `errors`) with its protocols; `Document.render` and `replace`; the two schemas of
  a kind; `texpkg_build.testing.load_declaration` (phase 2).
- The document directory: a kind's `create`, `load` and the package's generic `load`; `Document.save`, `check`,
  `hand_edits`, `template_changes`, `defaults` and `stack`; the state (every value written, defaults marked per node), the
  template state, the last three saves as history, the plan of each `.tex` and the hand-edit check (phase 2a).
- The build: `texpkg_build.hook` (`pdm_build_initialize`, `pdm_build_update_files`) generates the wheel's module from the
  declaration named in `[tool.texpkg] distribution`, renders the `.sty`, copies the declaration into it, and refuses a
  missing asset, a payload clash, a declaration that is not a package and a module that breaks the protocol (phase 2b).
- Embedding: a wheel carries one private copy each of texmodel, texpkg's run time and the base chain under `_embedded`,
  with every import of them rewritten as a relative import (found with `ast`), texmodel's `generator_version()` fixed to a
  constant, and needs only pydantic. A distribution can name a `base`, expose its kinds, and the build refuses a name or
  payload path used twice along the chain, an absolute import of the package itself, a read of the distribution's metadata
  and an import the wheel does not carry (phase 3).
- Profiles: `Kind(..., expand=, over=)` for a kind that expands to a kind of the base, written with the base kind's
  presets and its own locks (`render`, `save`, the payload of both kinds); `Design.load`, validated at build; the law
  `texpkg_build.testing.check_expansion` (phase 3a). `docs/known-limitations.md` lists what is not done.
- Provenance: every package declares `\<prefix>ProvenanceInfo`, `save` writes `<package>-provenance.sty` for each
  package of the stack with a stamp (`save(stamp=)`, default the release's version) and a time (`now=`, default the clock),
  keeps the time while nothing is materialised again, and adds the text to the PDF's Info dictionary as `/<Prefix>Provenance`
  when PDF management is active; `check(stamp=)` compares the file by stamp (phase 4).
