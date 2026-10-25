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

## Phase 3a: profiles (L1-L8)

Built: `Design.load`, `checks.design_is_valid` (`TP-B010`); `Kind.expand`/`over`, `Distribution.base_kind` and
`expansion_problem`, the check of a profile kind at declaration (`TP-K009` kind declared whole, `TP-K010` its example does
not expand to a valid base tree); `Release.settings/plan/payload` for profile kinds; `texpkg_build.testing.check_expansion`;
fixtures: the brand's `.sty` is filled from `tokens.json` (`library(fill=)`), the deck has a `brief` kind over the brand's
`expert` (restrict: `Tint`; default: `Point.tint`; lock: no size field plus the `FactGap` preset; compose: headline and
points to a card); `tests/test_profile.py`; `docs/known-limitations.md`.

Gates: `ruff format --check`, `ruff check`, `pyright` (0 errors), `lint-imports`, `pytest` (100%): green; compile tests
`-m tex`: green, including a profile document compiled as the base kind it expands to.

Proposed items adopted: L1 (embedded data validated at build, read with `importlib.resources`, the `.sty` filled from it),
L2 (the four ways, written by the author), L4 (a profile has its own `.sty` that requires the base's), L5 (a lock holds at the
Python API), as written.

Decisions:
- A profile kind is `Kind(name, model, presets, example, expand=fn, over="<base kind>")`; both or neither (`TP-K009`). `render`
  is the profile package's `plan` of `expand(tree)`, so the `.tex` loads the profile's `.sty`, which requires the base's.
- Settings written: the base kind's presets, then the profile's locks (its `presets`), then the variant's (L8). The template
  state records exactly those per file.
- A profile document's payload is the assets of its kind and of the kind it expands to (`over`).
- The L3 law is `check_expansion(dist, kind, examples)`: the kind's example and any trees given, each valid and expanding to a
  valid base tree; an `expand` that raises `LookupError`, `ValueError`, `TypeError` or `AttributeError` for a valid tree is a
  failure of the law. The test runs it over trees a hypothesis strategy builds. Widening is caught by the law (a profile whose
  expansion breaks the base grammar for some valid tree), not proved.
- Design data is JSON validated by a pydantic model; the author loads it in the declaration (`Design.load`) and uses it, so
  the build can only check it still validates.

Texmodel requests: none.

Deferred: nothing; see `docs/known-limitations.md` for the profile hand-edit paths and values.

## Phase 4: provenance (V2-V4, V34)

Built: `_internal/provenance_tex.py` (the TeX, no texpkg imports: for texmodel, N5), `provenance.py` (`stamp_of`, `time_of`,
`files`, `saved`), the block added to every package's `.sty` by `render_sty`, `Release.releases/layout_path`,
`Payload.pending`, `Document.save(now=, stamp=)` and `Document.check(stamp=)`; `tests/test_provenance.py` and the compile and
verifier tests in `tests/test_compile.py`. `pikepdf` and `proof-pdf` are dev dependencies.

Gates: all five green (`pytest` 100%); compile tests `-m tex`: green: the log of a compiled document carries
`PROVENANCE: acme-brand 1.2.0, stamp 1.2.0-3f9c2ab, materialised 2026-10-25T12:30:05Z`, the same text is
`/AbProvenance` in the PDF's Info dictionary (read back with pikepdf), and without the file the command prints the package
and version only and no entry is written. texmodel_build's `proof-pdf` verifier (veraPDF and Ghostscript on the host):
a minimal document with `pdfstandard=A-2b` and the entry has no finding; with `{A-2b,X-4}` the only findings are the missing
TrimBox and the missing PDF/X output intent of the minimal page, nothing about the entry. The XMP fallback (V34) was not
needed.

Proposed items adopted: V2's names (`\<prefix>ProvenanceInfo`, `...Stamp`, `...Time`, `<package>-provenance.sty`), V34's
`/<Prefix>Provenance` (the prefix capitalised, `/AbProvenance`), the entry living in the provenance file.

Decisions:
- `save` and `check` gain `stamp=` (V4: texpkg takes the stamp as an argument). The default stamp is the release's version, so
  `check()` reports a directory written by another release even where the `.sty` happens to be equal. A consumer that stamps
  passes the same stamp to `check`.
- The time is kept (the file is not rewritten) while the stamp is the same and nothing else of the payload is written again,
  so a second `save` writes nothing (P29); it is renewed when the stamp changes or any payload file is written. `check`
  takes the time from the file, so the time is never a difference (A4).
- The clock is read only in `provenance.time_of` when `now` is not given (N4's one exception). A time is UTC, `YYYY-MM-DDTHH:MM:SSZ`.
- A stamp is `[A-Za-z0-9.+:/@ -]*` (`TP-D006`): the same text in TeX, on the page and in a PDF string. `_` is left out
  because it is a TeX error in text.
- The macros are declared with `\def`, not `\newcommand` (a `\long` macro is never `\ifx`-equal to `\@empty`, the trap the
  first consumer recorded); the file is read with `\InputIfFileExists`, which also follows `\input@path`.
- Every package of the stack gets a file (the base's too), all with the dependent's stamp and time. A package without a prefix
  cannot declare the command (`TP-B011`).
- The block is added to a deep copy of the author's `Package` at build time, so the declaration and its own `render()` are
  unchanged.

Texmodel requests: none.

Deferred: `export` writes the file too (phase 6).

## Phase 5a: migrations (V5-V9, V14-V16, V22, V23, V28-V33 except the build's derived steps)

Built: `_internal/history.py` (data paths from pydantic locations, the schema of a field, `problems`: validation errors and
grammar violations as plain items; no texpkg imports: for texmodel, N5, V9), `_internal/adopt.py` (the runner and the default
policies), `load(path, *, migrations=, default_changes=)` on every kind and on the package, the protocols and generated
code; `tests/test_migration.py` with the datasheet fixture `tests/fixtures/acme_sheet` (the table of standards of release 4
becomes a tick list in release 5).

Gates: all five green (`pytest` 100%). No TeX is written in this phase.

Proposed items adopted: V14 (age window), V16/V30 (only what breaks is reported: pydantic's errors and the grammar's
violations become unresolved items with the constraint), V23's default (`FOLLOW`) and the mapping (a data path or
`Class.field`, the path first), V24/V27 as in 2a, V29 (default changes are applied on every load, whatever the age).

Decisions:
- What earlier migrations left unresolved reaches later ones in the state, as `state["$unresolved"]`, a list of
  `{path, reason, value, boundary}`. A migration may remove an entry it places; what it returns in `Migrated.unresolved` is
  added. Plain data in and out (V28), so the one signature `(state) -> Migrated` serves the build's, the kind's and the
  consumer's, and nothing is dropped unless a migration drops it.
- Order: the default policy first (it compares the saved template state's defaults with the installed ones, so it needs no
  snapshot), then for each `data` boundary crossed the kind's migrations and the consumer's, in the order given. Boundaries are
  crossed only when the document's `data` is older than `current - age` (V14); inside the window it is validated as it is.
  A migration whose `to` is not crossed is not run.
- `FREEZE` keeps the stored value, which is the old default, and removes the mark; `ASK` adds an unresolved item per
  marked value whose default changed; `FOLLOW` is the model filling the current default for a field the load leaves out.
- Every load validates, current data included: a state that no longer fits the model is a `MigrationError` (`TP-M003`) with its
  items, no longer an `ExceptionGroup`. `TP-M002` of 2a is gone.
- An item's `schema` is the schema of the field the error names; `boundary` is `4 -> 5`, `defaults` or `validation`.

Texmodel requests: none (the per-model core in `history.py` is the candidate for 5c).

Deferred: the build's derived renames and default migrations from snapshots, `changes(old, new)`, the version maps (5b).

## Phase 5b: contract versions (V10-V13, V17-V20, V33, V35-V37, P30)

Built: run time: `_internal/classify.py` (Avro-style rules over schemas, names and signatures over the interface, libtool
bumps, the release number the contracts need), `_internal/versions.py` (the versions file), `_internal/snapshots.py`
(`changes(old, new)` from the shipped snapshots), `Contracts.base_data`, `Release.snapshots`, the base kind's migrations at
the dependent's matching boundary (`adopt._kind_migrations`); build: `_internal/snapshot.py` (the snapshot, the proposal, the
output fingerprint, freezing), `checks.contract_gate`, `_internal/isolate.py` (the hook's isolation, shared with the command),
`cli.py` (`texpkg-build contracts [--root] [--freeze] [--first]`); the wheel ships `_contracts/<release>/`; `tests/test_contracts.py`.

Gates: all five green (`pytest` 100%); compile tests `-m tex` green. The snapshot needs no TeX.

Proposed items adopted: V11 (the snapshot's contents), V12 (computed, then recorded), V13's patch rule and "the build refuses a
tag that understates", V17 (stacks checked at build time), V18 (the stack record, from 3), V37 (freezing), P30 (the version
map). V36 as decided: `versions.toml` inside each snapshot.

Decisions:
- `contracts/` absent means no contracts: a package has the first versions (`1:0:0`, `1:0:0`, `1:0`) and ships no snapshots.
  Present, a development build (a version with a `.dev` or local part) must match `contracts/next` byte for byte
  (`TP-C001`) and have its output change classified (`TP-C005`); a release build (`X.Y.Z`) needs `contracts/X.Y.Z` as the newest
  frozen directory (`TP-C003`) and a number the contracts do not understate (`TP-C004`).
- Right after a freeze `next` describes the release just made; `texpkg-build contracts` is run again to start the next one,
  and a build in between is refused as stale. That is V12's "refuses a stale versions file".
- The `output` fingerprint hashes this package's `.sty` rendered at a fixed version, so the release number is not an output
  change (it would make every release one, and the number is what the changes decide); the base's `.sty` are hashed as the
  base shipped them, so a base release shows (P16). Editing an example is not a change: the previous release's example data is
  rendered with this package and compared with the previous `.tex` (V35); data that no longer loads is reported as not compared.
- The interface compares names, control sequences and signatures (argument names, kind of body and the `Choice` class, not its
  members, which are the data contract's), the kinds and their variants. Trailing optional arguments are a compatible addition.
- The versions file is plain TOML written by hand (`Versions.to_text`), with the author's statements kept across proposals: the
  `output` classification `change = "current" | "revision"`, the notes by `data` version, and `[base] interface`.
- `classify.py` and `versions.py` live in the run time because `changes()` reads and diffs two shipped snapshots; they import
  nothing of texpkg but the triples, so they can move to texmodel with the per-model core (5c).
- The base's `data` and `interface` `current` are read from the installed base module (`CONTRACTS`); a dependent records
  `[base.data]` (its `data` version to the base's) and `[base] interface`.
- Not built, and why: **the build's derived renames and default migrations from two snapshots** (V28). A rename is already read
  by texmodel's `field(renamed_from=)` before validation, and a changed default is applied from the document's own saved
  template state (5a), which holds exactly the old defaults, so no snapshot is needed. **A hand-written derived `changes`
  note** is the author's line in `[notes]`.
- A hook running in the author's process restores the real `texpkg` package's namespace after the base's private copy is
  linked to it: importing `<base>._embedded.texpkg.migration` bound `migration` on `texpkg` over the exported function.
- Codes: `TP-C001` next stale or missing, `TP-C002` a frozen snapshot is never rewritten, `TP-C003` no frozen snapshot for the
  release, `TP-C004` a number that understates, `TP-C005` an unclassified output change, `TP-C006` the base no longer supports
  the interface relied on.

Texmodel requests: none.

Deferred: nothing; derived renames and default migrations are decided against above.

## Phase 6: export (E1)

Built: `Release.export`, `_internal/export.py` (`readme`, the file names), the generated `export` function and its protocol
entry, `Release.plan(layout=)`; `tests/test_export.py` and the compile test in `tests/test_compile.py`.

Gates: all five green (`pytest` 100%); compile tests `-m tex` green: the template of every kind of an export compiles with
LuaLaTeX from the export directory alone, no search path set.

Proposed items adopted: E1's templates and README.

Decisions:
- `export(dest, *, now=None, stamp=None)` takes the stamp as `save` does (V4). It returns every file of the export, not only the
  ones it wrote, and writes only what differs.
- A template is `<kind>-template.tex`, the kind's example rendered in the `Flat` layout (no `\input@path`, no `\graphicspath`)
  with the kind's presets, so a lock reaches a plain-LaTeX user (L8); `README-<kind>.md` lists the files, what the template is
  written with and the commands of the kind's classes (for a profile kind, of the base kind it expands to) with their
  TeX shape. Variants are not exported as files; the README says so.
- Every kind the module offers, an exposed base kind included, has a template and a README.

Texmodel requests: none.

Deferred: nothing.

## Phase 6a: per-kind payloads proved, the font check (A7, A8)

Built: `texpkg_build/_internal/fonts.py` (`embedded`, `outside`), `texpkg_build.testing.check_isolated(module, compiler,
workdir)`, the fixture `acme_brand.misdeclared` (the lock-up declared for the wrong kind); `tests/test_isolated.py`.

Gates: all five green; compile tests `-m tex`: green, including a whole package passing, a lock-up declared for the wrong kind
failing (`expert/deck.tex` does not compile without it) and a substituted system font being found.

Proposed items adopted: A7 as written.

Decisions:
- A8 is built aside: `fonts.py` is self-contained (no texpkg imports), listed in `docs/texmodel-requests.md` for
  texmodel_build. It reads the `<path>` of each embedded font from the log; a relative path is the document's own, an
  absolute one must be under the directory the compiler saw (`/work/src` in the image, or the document directory).
- `check_isolated` takes the author's `Compiler` (image, fonts cache) and raises `DeclarationError` `TP-K011` listing every
  problem at once; a kind's example proves only what it uses (A7).

Texmodel requests: the embedded-font check (`docs/texmodel-requests.md`).

Deferred: nothing.

## Phase 7: two synthetic wheels end to end

Built: `tests/test_end_to_end.py` over the projects `tests/consumers/acme-brand-tex` and `acme-deck-tex` (with the declarations
`tests/fixtures/acme_brand` and `acme_deck`); the generated module now exports `migration`, `Migrated`, `Unresolved` and
`DefaultChange` (found by the test: a consumer with only the wheel could not otherwise write a migration).

What the test does: builds the brand (contracts frozen as 0.1.0), builds the deck on it, installs both into an environment that
has only pydantic, makes and saves a document of every kind of both packages (the brand's `expert` with variants and `vocab`,
the deck's `slide`, `brief` and the brand's `vocab` exposed through it), compiles all seven `.tex` files; hand-edits one; makes a
new brand release that changes a default and drops a palette colour (contracts frozen as 0.2.0, output classified), installs it in
a second environment, and loads the documents the first release saved: the dropped colour is reported with its path, a
consumer migration maps it, the marked default follows the new one, `template_changes()` names the default and the `.sty`,
the hand edit is found by data path and refuses `save`, `save(force=True)` adopts the release (`data` 2, history keeps `data` 1),
and the saved document compiles.

Gates: all five green (`pytest` 100%); compile tests `-m tex` green, this one included.

Proposed items adopted: none new.

Decisions: none beyond the export of the migration types above.

Texmodel requests: none.

Deferred: nothing.
