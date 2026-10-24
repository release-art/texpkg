# Implementation log

One entry per phase of [implementation-plan.md](implementation-plan.md), written by the implementing agent: what was
built, which gates ran, which proposed items were adopted, which choices a reader would not guess, what is deferred.
Work is on the branch `impl/texpkg-v1`; one commit per phase.

## Phase 0: scaffolding

Built: the layout of plan §2 as docstring-only modules in `src/texpkg` and `src/texpkg_build`; `[tool.importlinter]` (four
contracts); the `build` extra and the `texpkg-build` entry point (1.1, 1.6); `tests/test_public_api.py` (the `PUBLIC` sets,
every module imports, a scratch copy of `src/` with a deliberate violation breaks a contract); `tests/spawn.py` (the one
place tests start a process); the `acme_brand` fixture's assets (`tests/fixtures/acme_brand/assets/`: a font, a lock-up
PDF, a notice; `tokens.json`); AGENTS.md gains the package-layout section and the `TP-` code rule.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports` (4 kept), `pytest` (100%): all green. No
TeX is written in this phase, so no compile tests.

Proposed items adopted: none.

Decisions:
- The `texpkg` import contract also forbids `texmodel_build`: the run time is embedded (B7) and texmodel_build is not.
- "Nothing starts a process" allows indirect imports, as texmodel's does: `texpkg_build.testing` will reach
  `texmodel_build`, which owns the one `subprocess` import.
- The font in the fixture is Latin Modern (GUST Font License, with a notice); a synthetic stand-in for a brand typeface.
- The dev dependencies `import-linter` and `jsonschema` were added with `pdm add -dG dev` (schema tests, phase 2a).
- The uncommitted maintainer edits present at the start (AGENTS.md, the plan, `docs/implementation-plan.md`,
  `docs/briefs/`) are included in this first commit, since the phase edits the same files.

Texmodel requests: none yet.

Deferred: nothing.

## Phase 1: assets and layouts (A1-A6, P10, P11)

Built: `assets.py` (`Role`, `Asset`, `Resolved`), `layout.py` (`Layout` protocol, `Flat`, `Project`, with `place`,
`preamble`, `owned`), `_internal/payload.py` (`build`, `Payload.write`/`check`/`expected`), the first of `errors.py`
(`TexpkgError`, `DeclarationError`, `PayloadError`); `tests/test_payload.py`.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports`, `pytest` (100%): green. No TeX written, so
no compile tests.

Proposed items adopted: none. (`kinds=` on `Asset` is the spec's decided shape with a proposed spelling; used as written.)

Decisions:
- `Asset.path` is relative to the declaring package and may not contain `..` (`TP-A001`); the declaration must be a
  package, so every asset lives under it and the build can copy the package whole (phase 2b). "Anywhere in the source tree"
  (P5) means anywhere under the declaration's package.
- `Distribution` will carry the root explicitly (`root=importlib.resources.files(__package__)`), so a base's assets resolve
  against the base's own copy; `Resolved(asset, source)` is the pair a payload is built from.
- A layout places by `(role, path)`; the rendered `.sty` files go through `place(Role.PACKAGE, name)`.
- `Payload.check` uses `texmodel.drift.check_drift` for content (bytes) and for `orphaned`; `bundle.stale` picks the items
  `write` has to copy. `check` returns texmodel's `Drift`; the public `Check` (phase 2) is built from it.
- `Flat` owns `*.sty` at the document root, `Project(dir)` owns everything under `dir`: a file there that the payload does
  not hold is `extra` (A4). Fonts at the root of a `Project` are not owned.
- A payload with an absent source raises `PayloadError` (`TP-A004`) from `write` and from `check`, before anything is written.
- Error codes: `TP-A001` asset path, `TP-A002` placement clash (P11), `TP-A003` layout directory, `TP-A004` incomplete payload.

Texmodel requests: none.

Deferred: nothing.

## Phase 2: the declaration and the module API, in memory (P6-P8, P23-P26, K1-K3, K6, B11)

Built: `declaration.py` (`Distribution`, `Kind`, `Variant`, `Design`, `reachable`, `raw_holes`), `contracts.py` (`Triple`,
`Pair`, `Contracts`, `Changes`), `migration.py` (`@migration`, `Migration`, `Migrated`, `Unresolved`, `DefaultChange`; the
runner is 5a), `document.py` (`Document`: `tree`, `path`, `kind`, `render`, `replace`), `protocol.py` (`PackageModule`,
`KindsModule`, `KindModule`), `_internal/release.py` (`Release`, `KindApi`), `_internal/state.py` (the two schemas),
`texpkg_build/_internal/generate.py` (the module's source), `texpkg_build/testing.py` (`load_declaration`); the `acme_brand`
fixture (two kinds, three variants, a font, a lock-up, a notice); `texpkg/__init__.py` re-exports the declaration types.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports` (4 kept), `pytest` (100%) green; compile
tests `TEXPKG_REQUIRE_TEX=1 pytest -m tex`: 6 passed (every kind and variant with only its payload beside it, `Flat` and
`Project`, a missing lock-up is a compile error). A pyright run over the generated module checks the protocols and that wrong
use is an error (`tests/test_typing.py`).

Proposed items adopted: the field name `base=` and `expose=` (used by the checks only; embedding is phase 3); `Variant` and
`variants=`; `Asset(kinds=)`; `allow_raw` spelt `Class.field` / `Class.Passthrough`.

Decisions:
- `load`, `create`, `save`, `check`, `export` are not in the surface or the protocols yet: the plan lists `load`/`create` in
  phase 2 and in 2a, and they need a directory. A kind's tests get a document from `kind_module._api.document(tree, path)`.
  The protocols and the generated module grow with 2a and 6.
- `Distribution` gains `declared_in` (the declaring package's import name, `declared_in=__name__`) and `layout`
  (default `Flat()`, D5's example is `Project(res/acme)`). `declared_in` gives the root the assets are read from and, because
  it is evaluated where it runs, still names the declaration inside a wheel; the declaration must be a package.
- The module file stem of a document is the root class's name lower-cased (`Deck` -> `deck.tex`), the plan's example.
- The `.sty` is rendered by the build and shipped as `_sty/<name>.sty` (P4); the module reads it with `importlib.resources`
  and never renders at run time, so a comment naming a declaration module cannot differ between build and wheel. The package's
  version is set on a copy of the author's `Package` for the render (V1).
- `load_declaration` writes the generated files to a temporary directory and imports them; the declaration is the module
  already imported, aliased as `<module>._declaration`, so its classes are the ones the author's tests use.
- Kind classes exported: the components its grammar reaches plus the value types (`Choice`, ...) their fields name, all
  defined in the declaration package or a base's (`TP-B002` otherwise). Generated kind modules import them relatively.
- Codes: `TP-K001` example, `TP-K002` duplicates, `TP-K003` raw holes, `TP-K004` unknown kind or variant, `TP-K005` names,
  `TP-K006` distribution, `TP-K007` expose, `TP-K008` schema mode, `TP-M001` migration target, `TP-B001` kind/model mismatch,
  `TP-B002` unexportable class, `TP-B003` pointer.
- Protocol members are read-only properties, so a module's `Final` constants satisfy them.
- A texmodel tree is not validated on construction; `render` raises texmodel's `ExceptionGroup` for a broken one, unchanged.

Texmodel requests: none.

Deferred: `load`, `create`, `save`, `check` (2a); shipping the declaration and the assets in a wheel (2b); a base's kinds and
payload in a dependent (3; note: a base asset naming kinds is matched by name, which needs a decision when kinds expand to a
base's, 3a); `changes()` returns an empty `Changes` until 5b.
