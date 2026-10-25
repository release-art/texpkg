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

## Phase 2a: the document directory and its state (P27, P29, D1-D9, V21-V27; folds in spec phase 5)

Built: `_internal/state.py` (`tree_state`, `given`, `tree_from_state`, `default_paths`, `defaults_table`, `sty_hashes`),
`_internal/envelope.py`, `_internal/directory.py` (`_texpkg/`, `differing`, `write`, `rotate_history`),
`_internal/handedits.py` (`data_path`, `edits`), `Release.template/states/rendered/read/load`, `KindApi.create/load`,
`Document.save/check/hand_edits/template_changes/defaults/stack`, `Check`, `FileState`, `HandEdit`, `HandEditKind`,
`TemplateChange`, `Stack`, `StackEntry`; the errors `NotADocumentError`, `DocumentExistsError`, `KindMismatchError`,
`NewerDataError`, `MigrationError`, `HandEditError`; the generated `load` and `create`; the protocols grew with them.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports`, `pytest` (100%): green. Compile tests
`TEXPKG_REQUIRE_TEX=1 pytest -m tex`: green; they now build a directory with `create(...).save()` and compile its `.tex`
with nothing else on the search path (all kinds and variants, `Flat`, a deleted lock-up fails).

Proposed items adopted: D7's file names (`_texpkg/plan.json`, `plan-<variant>.json`); D9 is not used yet (see deferred);
`HandEdit` (`file, path, expected, found, kind, value`) and `TemplateChange(setting, old, new)` as in the plan; V24 (the
`$defaults` list per node), V26 (two schemas), V27 in this form: `save` is `model_dump(mode="json")` plus the
marks computed from `model_fields_set`; `load` drops the marked fields before validating, so the model fills the current
defaults and `model_fields_set` is what the author set.

Decisions:
- `state.json` is `{package, kind, data, tree}`; `tree` is the node state. A node's `$defaults` is written only when
  non-empty. The stored schema (`schema("serialization")`) makes every property required and limits `$defaults` to the
  node's defaulted fields; the tests validate a saved state against it with `jsonschema` (a dev dependency; the run time
  has none, validation on read is the model's).
- A marked field is dropped on load, so a default that changed in the release follows (the `FOLLOW` behaviour); `FREEZE`
  and `ASK` come with 5a.
- `template.json`: `package`, `release`, `contracts`, `settings` (per `.tex` file: value class name to the setting line,
  presets then the variant's), `defaults` (`Class.field` to its default), `sty` (file to sha256), `stack`.
  `template_changes()` compares settings, defaults and `.sty` hashes (not the release or contracts) and names each as
  `setting <file> <Value>`, `default <Class.field>`, `sty <file>`.
- History: a pair is moved to `history/1` when either state file differs from what `save` would write, and only the files
  that differ are rewritten. P29's "no history entry when the states are unchanged, so a save after a package upgrade only
  refreshes the payload" holds for an upgrade that changes neither state; an upgrade changes the template state's release,
  so it adds an entry (the old template state is what `template_changes()` of the older document needs).
- `save` renders everything and checks the payload is whole before it writes a file; the states are written last. The
  payload is written before the `.tex` so a missing source stops the save with nothing changed.
- `check` compares the whole expected directory (states, `.tex`, plans, payload) by content with `texmodel.drift`. A file
  `EXTRA` under the layout's owned globs is reported, and does not make a document not current (a save removes nothing).
  A hand-edited `.tex` shows as `CHANGED` and in `edits`.
- A line no node wrote (`header`, `document`, `preamble.*`, `settings[i]`) keeps its plan path in `HandEdit.path`; a node's
  path becomes its data path (`Deck[0]/Card[1]/Title[0]` is `/content/1/content/0`).
- `Stack` is a tuple of `StackEntry(package, release, output)`; it is read from the saved template state, or the
  release's own when none is saved.
- `save(*, force=False)` has no `now=` yet: it arrives with the provenance file (phase 4). `load(path)` has no `migrations=`
  or `default_changes=` yet (5a): a parameter that does nothing would be a lie.
- `bundle.stale` is not called: `texmodel.drift.check_drift` compares bytes for `check`, and `Payload.write` skips what is
  already identical; the plan named `bundle.stale`, the effect is the same.
- Codes: `TP-D001` not a document, `TP-D002` document exists, `TP-D003` kind mismatch, `TP-D004` newer data, `TP-D005` hand
  edit, `TP-M002` older data (replaced by the migration runner in 5a).

Texmodel requests: none. (`Edit.fields` of texmodel's uncommitted hand-edit work is not read; see D9 below.)

Deferred: D9 (a hand edit's field path and typed `value`): `HandEdit.value` is `None` until texmodel's field-level edits are
committed; migrations on `load` (5a); `now=` (4).

## Phase 2b: the build (B1-B6, B8, V1)

Built: `texpkg_build/hook.py` (`pdm_build_initialize`, `pdm_build_update_files`), `texpkg_build/_internal/checks.py`
(`declaration_directory`, `assets_are_there`, `module_satisfies_the_protocols`); the author-project fixture
`tests/consumers/acme-brand-tex/` (`pyproject.toml`, `pdm_build.py`) and `tests/projects.py` (copies it with the declaration
into a temporary project and builds a wheel or sdist in this process with `pdm.backend`); `tests/test_build.py`.
`pdm-backend` is a dev dependency and in the `build` extra.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports`, `pytest` (100%): green. No TeX is written
by the build beyond the `.sty` the compile tests already cover, and the compile tests (6) stay green.

Proposed items adopted: B7's `pydantic>=2,<3`; B10 is phase 3.

Decisions:
- The wheel holds only the generated module (`files.clear()` for the wheel target), with the declaration package copied to
  `<module>/_declaration/` whole (templates, assets, design data included); the sdist is left to the author's `includes`,
  adds the hook file (pdm does) and builds the same wheel (tested byte for byte).
- The wheel's dependencies are `pydantic>=2,<3` plus `texmodel==` and `texpkg==` the versions the build ran with. The last
  two go in phase 3 when both are embedded.
- The hook imports the declaration with `<project>/<package-dir>` on `sys.path` and forgets, afterwards, every module it
  or the generated module imported, restoring any copy that was already loaded, so building in the author's test process
  is hermetic. An editable build is refused (`TP-B008`): the module is generated, so authors test with `load_declaration`.
- The hook writes into `.pdm-build/` without `ensure_build_dir()`: its `.gitignore` would be packed into the wheel.
- The build also loads the generated module in memory and checks it against the protocols (`TP-B006`).
- Codes: `TP-B004` declaration not a package, `TP-B005` missing asset, `TP-B006` protocol, `TP-B007` no pointer, `TP-B008`
  editable build.
- Contracts are the default `Contracts()` until 5b writes them from the versions file.

Texmodel requests: `TemplateRef` reads through the file system, so a wheel cannot be imported from its zip
(`docs/texmodel-requests.md`; `test_a_wheel_runs_from_its_zip` is a strict `xfail`). Installed wheels are unpacked, so this
affects only zip imports.

Deferred: embedding (3); contracts from the versions file (5b); the absolute self-import check (3, with the rewrite).

## Phase 3: embedding (P13-P21, B7, B10, 1.5; P30 and V17 wait for 5b)

Built: `texpkg_build/_internal/embed.py` (`rewrite`, `rewrite_tree`, `scan_declaration`, `patch_generator_version`, `embed`);
the hook embeds and `LinkRunTime` makes the build see one texmodel; `Distribution.kinds_offered/owner/kind` (exposed base
kinds), `Release.bases/stack`, generated `_bound.py` with the base's `STY` and `RELEASE`, generated kind modules for exposed
kinds, a `dist` attribute on the generated module; `checks.tex_names_are_unique`; `load_declaration` for chains; fixtures
`tests/fixtures/acme_deck` (a kind of its own, the brand's `vocab` exposed) and `tests/consumers/acme-deck-tex`;
`tests/venvs.py`, `tests/test_embed.py`.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports`, `pytest` (100%): green. Compile tests
`TEXPKG_REQUIRE_TEX=1 pytest -m tex`: green, including documents saved by an installed deck wheel, in an environment that
has only pydantic, compiled with nothing else on the search path. The clean-environment tests: the deck wheel
installed with `pip install --no-deps` into a new venv in which texmodel, texpkg and the brand are not importable (pydantic
is linked in, so no index is needed): imports, renders, saves, `texmodel.package.generator_version()` is the constant; two
dependents embedding brand 1.2.0 and 1.3.0 import side by side; a chain of three holds one copy of each.

Proposed items adopted: P14 (the base is a build requirement named by object: `base=acme_brand_tex.dist`; the fixture pins it
with `==`), P15 (private copy under `_embedded`), P17 (the whole base payload, notices included, is embedded), P19's mechanism
(relative imports, absolute self-imports refused), P20's `base=`, B7's pydantic range, 1.5, B10.

Decisions:
- Imports are rewritten with `ast` positions and spliced into the source; a rewritten statement becomes one `from ... import`
  line (comments inside a multi-line import are lost). `import a.b` without `as` for an embedded name is refused (`TP-E001`).
- The rewrite works on absolute names: a relative import is resolved against its file's old package, mapped, and written
  relative to the new one, and left alone when unchanged. That is how a base moves from its own wheel into a dependent's
  (`<base>._embedded.X` becomes `<dependent>._embedded.X`; `from .._embedded import X` follows) and how a base's own bases
  are lifted beside it (P19).
- The dependent has one texmodel and one texpkg: the base's own copies are dropped and its code is pointed at the dependent's.
  The base's shipped `.sty` stays as the base rendered it.
- While the declaration is imported at build time, `<base>._embedded.texmodel` and `.texpkg` are aliased to the modules the
  build runs on (a meta path finder), so the author's classes and the base's are of one texmodel. Without it the base's
  private texmodel and the author's mix types at build time (found by the first dependent test).
- The generated module has `dist` (the declaration, for `base=`), independent of the pointer's attribute name.
- Exposed base kinds are written by the base's package (`Distribution.owner`) with the dependent's layout; an asset naming
  a base kind applies when that kind is exposed under the same name. Profile kinds that expand to a base kind are 3a.
- `Release.stack()` lists the packages of the chain, the document's own first; the template state records it.
- The author's code is refused if it imports a name outside the standard library, pydantic and the embedded packages
  (`TP-E004`), reads `importlib.metadata` (`TP-E003`), imports its own package absolutely (`TP-E002`), or imports an embedded
  or own name dynamically with a literal (`TP-E005`). A computed `import_module(name)` cannot be seen.
- In memory (`load_declaration`) a base is generated beside its dependent from its declaration, nested, and a finder makes the
  flat names of a wheel resolve to the nested modules.
- Codes: `TP-E001`..`TP-E005`, `TP-B009` (a control sequence defined by two packages of the chain). A payload path clash is
  `TP-A002`.

Texmodel requests: `generator_version()` (patched in the copy; `docs/texmodel-requests.md`).

Deferred: P30 (rebuilding against a newer base, version maps) and V17 (the base's `interface` check) to 5b; profile kinds
and assets of a base kind used by a profile kind to 3a; the embedded texmodel's `cli.py` is left out because typer is not
a dependency of a wheel.
