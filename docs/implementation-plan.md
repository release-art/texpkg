# texpkg — implementation plan

How the spec ([texpkg-plan.md](texpkg-plan.md)) gets built: the order, what each phase writes, what it reuses from
texmodel, how it is tested and when it is done. The spec says *what*; this says *how and in which order*. Requirement ids
(`P26`, `D8`) are the spec's. Where this plan needs a decision the spec does not hold, it says so in §1; nothing in a
phase builds on an item the spec marks **proposed** or **open** until that item is settled.

## 0. Ground rules for every phase

- **One phase, one change.** Each phase (or sub-phase) is a reviewable change with its tests, the spec's status updates
  (§8 of the spec), and a `CHANGELOG.md` line under `## [Unreleased]`. The maintainer commits.
- **Gates** (AGENTS.md): `ruff format --check`, `ruff check`, `pyright` (strict on `src`, 0 errors), `lint-imports` (from
  phase 0), `pytest` at 100% coverage. Phases that write TeX that TeX must accept (2, 4, 6a, 7) also run the compile tests:
  `TEXPKG_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov`, against texmodel's reference image or a local TeX Live.
- **Synthetic data only.** Tests and examples use `acme`: `tests/fixtures/acme_brand/` (a base: a `.sty`, a font, a
  lock-up PDF, two kinds) and `tests/fixtures/acme_deck/` (a profile on it). No real brand.
- **texmodel first.** Anything texpkg needs that texmodel lacks is written in one self-contained texpkg module with no
  texpkg-only imports (N5, V9) and moved into texmodel later. texpkg never patches around texmodel.
- **texmodel is the sibling checkout**, installed editable (AGENTS.md, Development environment), on its pydantic
  components. Its hand-edit work (field spans, `FieldEdit`, `texmodel_build.hand_edits`) is in progress there,
  uncommitted; phase 2a uses only `Plan.edits` as committed, and picks the field-level edits up when they land (D9).

## 1. Decisions taken for the implementation

All six were accepted by the maintainer (2026-10-25) as proposed below.

| # | Before | Question | Decided |
|---|---|---|---|
| 1.1 | phase 0 | **One distribution or two.** B8 says texpkg is two distributions. Since every wheel embeds the run time (B7), a consumer never installs texpkg at all; only authors install the build. | One distribution `texpkg` with two import packages, `texpkg` (run time, the part that is embedded) and `texpkg_build` (build only), as texmodel ships `texmodel` and `texmodel_build`; build-only dependencies in an extra (`texpkg[build]`); `lint-imports` forbids `texpkg` importing `texpkg_build`. B8's aim (nothing of the build reaches a consumer) holds because only the `texpkg` package is copied into a wheel. Amends B8. |
| 1.2 | phase 2a | **State format earlier.** The spec's phase 5 (pydantic state: two schemas, defaults written and marked, V21–V27) comes after phase 2a, which already has to write `state.json`. Writing it once, in its final form, avoids a format change. | Fold phase 5 into 2a. |
| 1.3 | phase 2 | **Error codes.** §4a proposes `TP-M001`-style codes, after texmodel's `TM-…`. | `TP-<area><nnn>`: `A` assets, `D` document, `K` kinds, `M` migration, `B` build, `C` contracts, `E` embedding; never reused (`grep -rhoE "TP-[A-Z][0-9]+" src`). |
| 1.4 | phase 2 | **The dev loop.** An author's tests must not need a wheel build per run. | `texpkg_build.testing.load_declaration(pointer)` builds the module in memory from the declaration (same code path as the hook, no wheel, no embedding), so `pytest` exercises the real API. |
| 1.5 | phase 3 | **Imports in embedded code.** The author's declaration imports `texmodel`, `texpkg` and its base by absolute name; in the wheel those are copies under `_embedded/`. P19 covers only a package's own imports. | The build rewrites absolute imports of embedded names (`texmodel`, `texpkg`, the base chain) to the private copies, as pip's vendoring does, using `ast` to locate `import`/`from` nodes (no regex over source); any other absolute import of an embedded name is refused (B4). |
| 1.6 | phase 2b | **The build command.** `texpkg-build contracts` (V12) needs a CLI; texmodel uses typer. | typer, in the `build` extra; only `texpkg_build/cli.py` prints (as texmodel). |

## 2. Target layout

Public modules at the top level, the rest in `_internal` (texmodel's pattern); every public module is listed in a
`PUBLIC` set in `tests/test_public_api.py`.

```
src/texpkg/                      the run time: embedded into every built wheel (B7); imports only texmodel and pydantic
    __init__.py                  the declaration types re-exported: Distribution, Kind, Variant, Asset, Role, Design,
                                 migration, Migrated, Unresolved, DefaultChange
    declaration.py               Distribution, Kind, Variant, Design (frozen; checked at construction)
    assets.py                    Asset, Role
    layout.py                    LAYOUT: placement and preamble lines
    document.py                  Document[T], Check, FileState, HandEdit, TemplateChange
    migration.py                 migration, Migrated, Unresolved, DefaultChange; the runner (V28–V32)
    errors.py                    TexpkgError and the error classes of §4a (built-in bases, stable `.code`)
    provenance.py                the provenance file's text and the Info entry (V2, V34)
    _internal/
        state.py                 state.json and template.json: write, read, `$defaults` marks (V21–V27, D1, D6)
        directory.py             _texpkg/ layout, history rotation, plan files (D2, D3, D5, D7)
        payload.py               assembling items for texmodel.bundle from importlib.resources (A3, A6, P10)
        handedits.py             saved plan vs file, node path to data path (D7–D9)
        envelope.py              {package, data, kind, ...} (K3)
        history.py               the per-model migration core kept for texmodel (V9): problems of a state
        classify.py              diffing two snapshots into bumps (V12, V13); run time: `changes()` diffs shipped snapshots
        versions.py, snapshots.py  the versions file and the shipped snapshots, read at run time (V33, V36)

src/texpkg_build/                build only: never embedded
    __init__.py
    hook.py                      pdm_build_initialize / pdm_build_update_files (B2)
    testing.py                   load_declaration, the L3 law helper, the isolated-compile helper (1.4, L7, A7)
    cli.py                       `texpkg-build contracts` (V12, V37)
    _internal/
        generate.py              the generated module's source (P6, K4, V1)
        embed.py                 copying and import rewriting (P13–P19, B7, B10, 1.5)
        snapshot.py              contract snapshots, the versions file, freezing (V11, V35–V37)
        checks.py                what the build refuses (B4)
```

Import contracts (`lint-imports`, phase 0): `texpkg` does not import `texpkg_build`; `texpkg` imports nothing outside the
standard library, texmodel and pydantic; only `texpkg_build/cli.py` prints; nothing in either imports `subprocess` (N4).

## 3. Phases

Each phase lists: **goal**, **builds** (modules, the key signatures), **reuses** (texmodel), **tests**, **done when**,
**waits on**. The order follows dependencies, not the spec's §8 numbering where they differ (noted).

### Phase 0: scaffolding (the plan and AGENTS.md are done)

- **Builds:** the layout of §2 as empty modules; `[tool.importlinter]` contracts and `lint-imports` in the gates and the
  pre-commit hook; `tests/test_public_api.py`; the `acme_brand` fixture skeleton (`acme.sty` source, a font, a PDF, a
  `tokens.json`); the `build` extra (1.1, 1.6); AGENTS.md gains the package-layout section and the `TP-` code rule (1.3).
- **Done when:** gates pass on the empty layout; `lint-imports` fails a deliberate violation in a test branch.
- **Waits on:** 1.1, 1.3, 1.6.

### Phase 1: assets and layouts (A1–A6, P10, P11)

- **Goal:** turn a declaration's assets and rendered `.sty` into a payload, place it under a directory by layout, write
  it, and check it.
- **Builds:**
  - `assets.py`: `@enum.unique class Role(StrEnum)`; `Asset(path: str, role: Role, why: str, kinds: tuple[str, ...] = ())`,
    frozen, `path` relative to the declaring package's root, read with `importlib.resources.files(...)`.
  - `layout.py`: `Project(dir: PurePosixPath)`, with `place(asset) -> PurePosixPath` (A1, A2: fonts at
    the root for `Project`, `BY_PATH` keeps its path) and `preamble() -> PreambleSlots` pieces (A5, from texmodel's
    `InputPath`, `GraphicsPath`).
  - `_internal/payload.py`: `items(sty: Mapping[str, str], assets, layout, kind) -> tuple[bundle.Item, ...]`; a
    `Traversable` that is not a real file (a zipped wheel) is materialised with `importlib.resources.as_file` for the
    copy; an asset whose `kinds` excludes `kind` is left out (A6).
  - `check(...) -> Check`: `bundle.stale` for content, `drift.check_drift` for `missing` and `extra` (orphaned files in
    the places the layout writes to), the provenance file compared by stamp (A4).
- **Reuses:** `texmodel.bundle` (`Item`, `missing`, `stale`, `write`: refuses incomplete, writes bytes, removes nothing,
  A3), `texmodel.drift`, `texmodel.preamble`.
- **Tests:** a table test per `Role` × layout; hypothesis: placement is injective or raises (two assets cannot land on one
  path, P11); `write` refuses a payload with one missing file and writes nothing; `check` reports each of the four states;
  a payload from a zipped package.
- **Done when:** gates; the A-ids and P10/P11 marked built in the spec's §8.

### Phase 2: the declaration and the module API, in memory (P6–P8, P22–P28, K1–K7, B11, §4a)

- **Goal:** everything a consumer calls, working from a declaration loaded in the same process (1.4), before any wheel
  exists.
- **Builds:**
  - `declaration.py`: `Distribution(name, module, package, declared_in, design=None, assets=(), kinds=(), base=None, expose=())`,
    `Kind(name, model, presets, example, migrations=(), allow_raw=(), variants=())`, `Variant(name, settings)`,
    `Design(model, path)`. Checked at construction: kind names unique, `example()` validates against `model`, `allow_raw`
    names real fields and every `Raw`/`Passthrough` field is listed (P25), variant names unique.
  - `texpkg_build.testing.load_declaration(pointer) -> ModuleType`: builds the module object a wheel would contain (the
    same generator as phase 2b, in memory).
  - The kind module surface: `NAME`, the kind's classes and value types (P24), `load`, `create`, `schema(mode=)`,
    `example()`, `variants()`, `changes(old, new)` (returns an empty `Changes` until phase 5b).
  - `document.py`: `Document[T]` with `tree`, `path`, `kind`, `render(variant=None) -> str` (texmodel `Package.plan` with
    the kind's presets and the variant's settings as `settings=`, the layout's preamble lines, L8, K6), `replace(tree)`.
    `save`, `check`, `hand_edits`, `template_changes` arrive in 2a.
  - `errors.py`: the classes of §4a with built-in bases and `TP-` codes (B11, 1.3).
  - The protocol: `PackageModule`, `KindModule` as `typing.Protocol`s, checked by pyright against a generated module in a
    test (P6).
- **Reuses:** texmodel `Package.plan` / `document`, `spec.json_schema` (V26's two modes come from pydantic on the kind's
  root class), `spec.from_dict` / `to_dict`.
- **Tests:** `acme_brand`'s two kinds through the whole surface; `render` byte-for-byte against goldens (one per kind and
  variant) **and** compiled (`-m tex`); `Raw` refused unless listed; a pyright run over a test file that uses the
  generated module with wrong types must fail (a typing test, `pyright --outputjson` on a fixture file).
- **Done when:** gates and the compile tests pass.
- **Waits on:** phase 1; 1.3, 1.4.

### Phase 2a: the document directory and its state (P27, P29, D1–D9, V21–V27; folds in spec phase 5, 1.2)

- **Goal:** `create`, `load`, `save`, `check`, `hand_edits`, `template_changes` on a real directory.
- **Builds:**
  - `_internal/state.py`: `state.json` = the envelope (K3: `package`, `kind`, `data` version) plus the tree's state:
    every value written (V21), each node's `$defaults` from `model_fields_set` (V24, V25, V27; texmodel's `to_dict`
    already writes what was given), validated on read against the stored (serialization) schema (V26).
    `template.json` = version, contracts, the kind's settings, its defaults, the `.sty` hash, the stack (D1, D6, V18).
  - `_internal/directory.py`: `_texpkg/` layout (D5), history rotation keeping the last 3 (D2, D3), `plan.json` and
    `plan-<variant>.json` (D7).
  - `Document.save(*, now=None, force=False)`: the hand-edit check first (D8: each `.tex` against its saved plan; raise
    `HandEditError` with the edits unless `force`), then states, history, `.tex` per variant (K7), plans, payload
    (phase 1, the kind's assets only, A6), provenance placeholder (phase 4 fills it); writes only what changed, no
    history entry when the states are unchanged (P29).
  - `Document.hand_edits()`: texmodel `Plan.from_json(saved).edits(text)` per file; node path mapped to the state's data
    path (`_internal/handedits.py`), `value` filled when texmodel's field-level edits provide it (D9), else `None`.
  - `Document.template_changes()`: old `template.json` against the installed package's (D4, D6).
  - `load(path, migrations=(), default_changes=DefaultChange.FOLLOW)`: reads, refuses another kind
    (`KindMismatchError`), a newer `data` version (`NewerDataError`), a non-document (`NotADocumentError`); same
    `data` version only until phase 5a (an older one raises `MigrationError` naming the missing machinery).
  - `create(path, tree)`: refuses a directory that holds a document.
- **Reuses:** texmodel `Plan` (`to_json`, `from_json`, `edits`), `spec.to_dict` / `from_dict`, pydantic schemas.
- **Tests:** round trip `load(save(create(...)))` equal (hypothesis over `acme` trees); a value set to the default by the
  author stays the author's (V25); history keeps 3 and drops the oldest; a hand-edited `.tex` raises, lists the edit by
  data path, and `force=True` overwrites; `check` reports a hand edit and a stale payload; `template_changes` after a
  changed preset.
- **Done when:** gates; the compile test builds a saved directory with nothing else on the search path.
- **Waits on:** phase 2; 1.2.

### Phase 2b: the build (B1–B6, B8, V1)

- **Goal:** `pdm build` of an author's project produces a wheel whose module is the one phase 2 built in memory.
- **Builds:**
  - `hook.py`: `pdm_build_initialize(context)` reads `[tool.texpkg] distribution` (B3), imports the declaration, sets
    the wheel's dependencies (pydantic's range, B7; while embedding is not built, texmodel and texpkg too, removed in
    phase 3); `pdm_build_update_files(context, files)` adds the generated files.
  - `_internal/generate.py`: the module's source (`__init__.py`, `kinds/__init__.py`, `kinds/<name>.py`,
    `_version.py` with `VERSION = "<the distribution's version>"`, V1), the rendered `.sty` and the assets as package
    data, the declaration copied as `_declaration` (P22). Deterministic: sorted, no clock (B5).
  - `_internal/checks.py`: what B4 lists that exists by now (missing asset, TeX-name or payload clash, protocol).
- **Tests:** build `acme_brand` in-process with `pdm.backend` into `tmp_path` (no subprocess); the wheel's file list and
  bytes are identical across two builds (B5); the sdist builds the same wheel (B6); a declaration with a missing asset
  fails the build with its `TP-B` code.
- **Done when:** gates.
- **Waits on:** phase 2; 1.1, 1.6.

### Phase 3: embedding (P13–P21, P30, B7, B10, V17)

- **Goal:** a wheel that needs only pydantic: the base chain, texmodel and texpkg's run time copied in privately.
- **Builds:** `_internal/embed.py`: copy each package of the chain to `_embedded/<module>/` (one copy each, P19), the base's
  payload and contract history with it (P18), licences and notes (P17); texmodel and `texpkg` sources to
  `_embedded/texmodel/` and `_embedded/texpkg/` (B7); import rewriting (1.5); the version constant into the texmodel copy
  (B10, with the texmodel change below); exposed kinds re-exported (P21); the base's recorded `interface` checked (V17).
- **Texmodel change (N5):** `generator_version()` (`package.py`) reads a module constant when present instead of
  `importlib.metadata.version("texmodel")`; built aside in texpkg first, then proposed to texmodel.
- **Tests:** a wheel of `acme_deck` (base `acme_brand`) installed into a fresh venv with only pydantic: imports, renders
  and saves (the venv is made by `venv.EnvBuilder`; pip has no in-process API, so the install runs pip as a process
  from one test helper: tests may spawn, the library never does, N4); two dependents embedding different `acme_brand` releases import side
  by side; a clash along the chain fails the build.
- **Done when:** gates; the clean-venv test passes.
- **Waits on:** phase 2b; 1.5.

### Phase 3a: profiles (L1–L8)

- **Builds:** `Design` loading (L1, validated at build); `Kind(..., expand=...)` for a profile's kind (L3, L7: hand-written
  `expand` to the base's tree); `render` of a profile kind is the base's render of `expand(tree)` with the profile's
  locks (L8); `texpkg_build.testing.check_expansion(kind, examples=...)`, the L3 law as a hypothesis test the author runs
  (L6, L7).
- **Tests:** `acme_deck` narrows a colour to a palette `Choice`, locks a size, composes a card; the law holds; a widening
  default fails it.
- **Waits on:** phase 3.

### Phase 4: provenance (V2–V4, V34)

- **Builds:** the TeX component (macros declared empty, the companion file loaded if present, the `\long` trap handled,
  V2) in one texpkg module for texmodel (N5); `provenance.py` writes `<name>-provenance.sty` with the stamp and time
  (`now=`, N4) and the Info entry when PDF management is active (V34); `save` and `export` write it; `check` compares it
  by stamp (A4, V3).
- **Tests:** compile a document printing `\acProvenanceInfo`; read the Info entry back from the PDF; veraPDF against
  PDF/A-2b and PDF/X through texmodel_build's verifier (fallback to XMP if a custom key fails, V34).
- **Waits on:** phase 2a.

### Phase 5a: migrations (V5–V9, V14–V16, V28–V33)

- **Builds:** `migration.py`: `@migration(to=N)`, `Migrated`, `Unresolved`, `DefaultChange`; the runner: for each `data`
  boundary crossed, the build's (renames, defaults), the kind's, then the consumer's migrations, each seeing what the
  last left unresolved (V32); validation of the result; `MigrationError` with every unresolved item, nothing returned or
  written (V31); default migrations under the consumer's `default_changes` (V22, V23, V29); validation errors as
  unresolved items (V30). The per-model core (renames, applying a chain) in `_internal/history.py`, texmodel-shaped (V9).
- **Tests:** the datasheet example (standards table to a fixed tick list): a kind migration maps known standards, an
  unknown one aborts until a consumer migration places it; atomicity (no partial result, no write); `FREEZE` and `ASK`.
- **Waits on:** phase 2a. Derived renames and default migrations need snapshots: they land in 5b.

### Phase 5b: contract versions (V10–V13, V17–V20, V33, V35–V37)

- **Builds:** `_internal/snapshot.py`: `contracts/next/` (both schemas per kind, `interface.json`, `output.json` with one
  hash per file, each example's data and `.tex`, the versions file) and the freeze into `contracts/<version>/` (V37);
  `_internal/classify.py`: Avro-style rules over schemas, names and signatures over the interface (V12), the version
  maps (V33, P30); derived renames and default migrations from two snapshots (V28); `cli.py`: `texpkg-build contracts`;
  the build refuses a stale versions file, an unclassified `output` change, a tag that understates the contracts (V12,
  V13); `changes(old, new)` from the shipped snapshots (V33).
- **Texmodel gap:** classifying a change by diffing two declarations (texmodel's X5) is built here in `classify.py` (V9),
  moved in 5c.
- **Tests:** each row of the spec's examples table (a field added, a colour value changed, a colour dropped, a field
  shortened, a table to a tick list) gives the expected triples and release bump; editing an example is not an output
  change (V35); `changes(4, 5)` names what changed.
- **Waits on:** phase 5a.

### Phase 5c: the per-model core moves to texmodel

- A texmodel change with its own tests (renames, chain application, classification); texpkg then imports it and deletes
  its copy.

### Phase 6: export (E1)

- **Builds:** `acme_tex.export(dest, *, now=None)`: the whole payload in the layout, one template `.tex` per kind (its
  `example()` rendered with the kind's settings, so locks reach plain-LaTeX users, L8), a README per kind generated from
  the kind's classes, and the provenance file.
- **Tests:** compile each template in the export with the search environment unset.
- **Waits on:** phase 4.

### Phase 6a: per-kind payloads proved, the font check in texmodel_build (A7, A8)

- **Builds:** `texpkg_build.testing.check_isolated(module)`: each kind's example in each variant saved into a fresh
  directory with only that kind's payload, compiled with no `TEXINPUTS` and no `OSFONTDIR`; fails on a missing file or a
  font embedded from outside the directory. The font check is the first consumer's `fonts.py` generalised to allowed
  directories, written for texmodel_build (A8) and proposed there.
- **Waits on:** phase 2a (and phase 6 for exports).

### Phase 7: two synthetic wheels end to end

- `acme-brand-tex` and `acme-deck-tex` built on it, as real projects under `tests/consumers/`, each built, installed
  into a clean venv with nothing else (the phase 3 helper), then: create, render every kind and variant, save, compile; a release bump with a
  default change, a dropped palette colour and a hand edit run through `load` and `save`.

### Phase 8: the first consumer's port (acceptance)

- In the first consumer's repository, by its maintainer: its `pack` module becomes a texpkg declaration; its kinds are
  its series (K4: generated from its tokens); cards become texmodel nodes (today they are assembled as text, a known
  shortcut there); its hook files become variants (K6). Accepted when its generated `.sty`, `deck.tex` for every series
  and its committed `derived/` files are byte-identical before and after, and its deck tests pass.

## 4. Order and parallel work

```
0 → 1 → 2 → 2a → 2b → 3 → 3a
              ↘ 4 → 6
              ↘ 5a → 5b → 5c
              ↘ 6a (after 2a; its export half after 6)
3, 3a, 5b, 6 → 7 → 8
```

After phase 2a, phases 4, 5a and 6a touch different modules and can run as separate changes in parallel; 2b and 3 are
sequential (embedding extends the build).

## 5. Still proposed in the spec, by the phase that needs it settled

| Phase | Items |
|---|---|
| 1 | — |
| 2 | P14 (`==` pin), P15, P17, P19's mechanism, P20's `base=` name, the `Variant`/`variants=` spelling, `TemplateChange` and `HandEdit` field names |
| 2a | D9 (field-level values), D7's file names |
| 3 | B7's pydantic range, 1.5 |
| 3a | L1, L2, L4, L5 |
| 4 | V2's and V34's names |
| 5a | V14, V16, V23's default and mapping, V24, V26, V27, V29, V30 |
| 5b | V11, V12, V17, V18, V37 |
| 6 | E1's templates and README |
| 6a | A7 |

## 6. Risks

| Risk | Where | Mitigation |
|---|---|---|
| Import rewriting misses a dynamic import in author code | 3 | refuse `importlib.import_module` of embedded names in the declaration (B4); the clean-venv test |
| A zipped wheel breaks `bundle`'s pathlib copies | 1 | `importlib.resources.as_file`; a zipped-package test |
| texmodel's pydantic switch or hand-edit work changes under texpkg | 2, 2a | the editable install tracks it; pin the commit texpkg was tested on in the changelog until texmodel releases |
| Custom PDF Info keys fail PDF/A or PDF/X | 4 | veraPDF test decides; XMP fallback (V34) |
| The L3 law needs generators for arbitrary kind trees | 3a | hypothesis strategies from the kind's pydantic schema; examples supplied by the author when a strategy cannot be derived |
| The port shows a byte difference that is texmodel's, not texpkg's | 8 | compare each artefact separately (`.sty`, `deck.tex`, `derived/`) and attribute before fixing |
