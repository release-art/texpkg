# texpkg — project plan

The spec and the decisions log: what texpkg is, and (§8) what is not built yet. Status of each decision: **decided**,
**proposed** (drafted, not agreed) or **open** (a question). Requirement ids (`P1`, `A3`) are what tests and commits cite.

## 1. Purpose

A TeX package published as a **Python package**: one wheel, one version, carrying both the typed API (texmodel
declarations and document models) and the TeX that API compiles against. A Python project depends on it, generates `.tex`
from its own data through that API, and gets the files the `.tex` needs written beside it.

texpkg is the contract and runtime for such a package. texmodel models the interface and writes the TeX; texpkg ships it.

**Why.** The first consumer built this by hand: a brand package whose wheel carries its declarations, deck models, fonts,
lock-ups and output profile, and whose module validates a deck, renders `deck.tex`, installs the payload into a deck
directory and checks it later. None of that is brand-specific, and a second package would repeat it.

### Non-goals

- N1 Not a TeX distribution manager: no CTAN, no `tlmgr`, no network, no resolving of third-party TeX package versions.
- N2 No compiling. Driving `latexmk`, search-path environments and checking a PDF's fonts belong to `texmodel_build` or the
  consumer.
- N3 Nothing texmodel owns: components, document models, schemas and escaping stay there. A gap found there is fixed there
  (migrations are the exception: designed here, then moved there, V8).
- N4 No process spawning, at build time or run time, and no clock or git read: such values are passed in. **One
  exception** (**decided**): the provenance time (V2), which `save` and `export` read from the clock when the caller gives
  none; both take it as an optional argument (`now=`), so a test can pin it. The version is a constant the build writes
  (V1), not read from package metadata.

### The line between texpkg and texmodel

**texmodel owns one package and its documents, including how one model's data changed; texpkg owns what spans more than
one release, more than one package, or a wheel** (**decided**). What a package author writes (its components, kinds and
profiles' models) is neither's: it is the content being packaged, built with texmodel's parts and checked by texpkg.

| | Owner | Already in texmodel |
|---|---|---|
| components, document trees, data ↔ tree, schema, escaping | texmodel | `components`, `spec.from_dict`, `spec.json_schema` |
| copying a payload, refusing an incomplete one, content comparison, drift | texmodel | `bundle` (`Item`, `missing`, `stale`, `write`), `drift.check_drift` |
| preamble pieces | texmodel | `preamble` (`InputPath`, `GraphicsPath`), `PreambleSlots` |
| one model's history: renames, classifying a change by diffing two declarations | texmodel | renames (`x-renamed-from`); the rest is X3–X5, unbuilt (V8) |
| the TeX side of provenance (macros declared empty, a companion file loaded if present) | texmodel (`std` or `preamble`) | — |
| `Role`, `Layout`, the payload step of `save`, `export`: the policy over `bundle` | texpkg | — |
| `Distribution`, the module protocol, the build, generated typed models | texpkg | — |
| contract snapshots, the versions file, release summary | texpkg | — |
| embedding, flattening a chain, `expose`; checking a profile narrows (L3, L6) | texpkg | — |
| the envelope, the document's stack record, running migrations and reporting what is unresolved | texpkg | — |

- N5 **A gap is built aside, then moved** (**decided**): what texpkg needs from texmodel and texmodel lacks is written in
  a self-contained texpkg module (as V9) and moved into texmodel when stable; texpkg never works around texmodel.
- N6 Consumers touch texmodel types (document trees, values, choices), so texmodel's API is part of every package's public
  API (**decided**). Each package carries its own copy (B7), so those types are the package's, reached through its
  exports (P24), and never mixed between packages.

## 2. Vocabulary

| Term | Meaning |
|---|---|
| texpkg package | a Python distribution whose module has the fixed texpkg API (§4) |
| `Distribution` | what a package author declares: its texmodel package, kinds, assets, design data and base |
| asset | a file the TeX needs that texmodel does not render: a font, a graphic, a profile, a licence, notes |
| payload | every file a self-contained build of the package needs: the rendered `.sty` files and the assets |
| layout | the rule that places each payload file under a target directory |
| materialise | write the payload into a document directory: a step inside `save`, not a public call (P29) |
| export | write a plain-LaTeX bundle that needs no Python (opportunistic) |
| profile | a package that depends on another and narrows its API: defaults, locks, restricted types, composed models |
| kind | one named document model a package offers (a card template); a package may offer several |
| embedded dependency | a base copied into a dependent's wheel at build time, private to it (P13) |
| embedded data | typed data a package ships (tokens, palettes, presets) that its models and `.sty` are filled from |
| contract | what a consumer relies on, versioned on its own: `data`, `interface`, `output` (V10) |
| contract snapshot | the facts a release's contracts are compared on, committed and shipped (V11) |
| migration | a function from one `data` version's stored state to the next, from the build, a kind or a consumer (V28, V32) |
| unresolved item | what no migration placed; any one aborts adopting a release (V31) |
| provenance | the one generated file that carries a time and a stamp, saying what was materialised and when |

## 3. Distribution format

- P1 **The wheel is the primary format** (**decided**). A raw LaTeX bundle is a convenience (E1), not a requirement.
- P2 **The package carries its texmodel API** (**decided**): a Python project generates TeX from its own data through the
  package's models, validated at the data boundary and escaped by type (texmodel's job, N3).
- P3 **API and TeX at one version** (**decided**): a document is never rendered against one release and compiled against
  the payload of another; `check` reports it when it is (V3).
- P4 **The `.sty` is rendered at build time and shipped in the wheel** (**proposed**). The build renders it from the same
  declaration the module is built from (B1), so the copy cannot drift from the API, and `save` only copies bytes.
- P5 **Assets may live anywhere in the author's source tree**; the build copies them into the wheel and the module reads
  them with `importlib.resources` (**proposed**), so a wheel, a zip and an editable install behave alike.

## 3a. The build

**texpkg builds the module** (**decided**), the way the first consumer's pdm build hook puts its pack into its wheel.

- B1 The author writes a declaration (a `Distribution`: texmodel package, kinds, assets, design data, its
  base) and points the build at it; texpkg's build step generates the module with the fixed surface (§4), renders
  the `.sty`, copies the assets and writes them all into the wheel (**decided**).
- B2 The hook is a pdm-backend build hook (`pdm_build.py`, `pdm_build_update_files`) that calls `texpkg-build` (B8)
  (**decided**); `texpkg-build`, the base (P14) and whatever the declaration imports are listed in `[build-system]
  requires`, because the build runs in an isolated environment.
- B3 The declaration is named in configuration, `[tool.texpkg] distribution = "acme_tex_decl:dist"`: an
  explicit pointer, as texmodel's `render module:attr` is (**decided**).
- B4 **The build refuses what would ship broken**: a missing asset, a conflicting TeX name or payload path along the
  base chain (P11), a stale or understated versions file (V12), an incompatible base (V17), a module that does not
  satisfy the protocol. A defect fails `pdm build`, not a consumer's import (**decided**).
- B5 The generated module is deterministic: the same declaration builds byte-identical files (no clock, hash or set order),
  so a wheel can be checked by rebuilding (**decided**).
- B6 A sdist carries the declaration and the sources, not the generated module, and builds the same wheel (**decided**).
- B7 **The run time is embedded too** (**decided**): texmodel and texpkg's run time are copied into the wheel
  (`acme_tex._embedded.texmodel`, `._embedded.texpkg`) like a base (P13, P19). The same data then renders the same
  `.tex` whatever else the consumer has installed, so `output` (V10) depends on the wheel alone, and two packages built
  on different texmodel releases install side by side. Only what cannot be copied stays a dependency: pydantic (compiled),
  with a wide range (`>=2,<3`) (**proposed**, the range). The package's own versions keep the usual meaning (V13).
- B8 **texpkg's build never reaches a consumer** (**decided**): one distribution, `texpkg`, with two import packages:
  `texpkg` (the run time, the only part a wheel embeds, B7) and `texpkg_build` (the hook, code generation, snapshots,
  classification, embedding), whose dependencies sit in an extra (`texpkg[build]`) listed only in `[build-system]
  requires`. `lint-imports` forbids `texpkg` importing `texpkg_build` (implementation plan §1.1).
- B9 **fsspec is parked** (**decided**): not in v1; a document directory is a `pathlib.Path` (P27). If it returns, it comes
  as an optional extra (`acme-tex[fsspec]`).
- B10 Embedded code must not ask the environment who it is (**proposed**): texmodel reads its own version with
  `importlib.metadata.version("texmodel")` for the generated-file stamp, which inside a copy finds no metadata, or another
  installed texmodel's. The build sets texmodel's `GENERATOR_VERSION` in the copy, and refuses code that reads its own distribution's metadata (B4). The same holds for the package's own
  version (V1).
- B11 **No types are shared between packages** (**decided**): with the run time embedded (B7), one package's `Document`,
  errors and enums are its own classes, and no shared `texpkg-api` distribution exists. A consumer using several packages
  catches a built-in base and reads a stable `.code`; enums are `StrEnum`s, so values compare equal across copies; code
  over any package is duck-typed. pydantic stays the only run-time dependency.

## 4. The module API

A package author declares a `Distribution`; what a consumer installs and imports is a **Python module with a fixed,
well-known, strictly defined API** for emitting LaTeX sources, with version control and migrations (**decided**). Every
texpkg package exposes the same surface, so a consumer (or a tool) uses any of them the same way.

The surface is specified in §4a; the requirements behind it follow.

- P6 The surface is defined once in texpkg as a `typing.Protocol`; the build generates the module to satisfy it and checks
  it does (B4), and a consumer's pyright reads the generated module's types (**decided**).
- P7 Loading and rendering delegate to texmodel; texpkg adds no document logic, only the fixed surface and its contract (**decided**).
- P8 `Distribution` is declared explicitly by the package: no discovery by name or entry point (**decided**).
- P22 **The declaration ships, privately** (**decided**): `load`, `render` and embedding (P18) need it, so the wheel
  carries it as a private module (`acme_tex._declaration`), not part of the public surface.
- P23 **A document is a texmodel tree of a kind's classes; data is its serialisation** (**decided**). A consumer gets one
  either way: `load(data)` (migrated, validated) or by building it in Python from the exported classes, type-checked.
  Classes only ever describe the current version: old data reaches them through migration, and code written against an
  old release fails pyright on upgrade. Unresolved items therefore carry data, not trees, and their paths are data paths
  (V15). Going back from a tree to stored state is `doc.save()` (P29).
- P24 **What the module exports** (**decided**): the fixed surface (P6); each kind's classes (`acme_tex.kinds.expert.Deck`
  and the classes its tree is made of); the value types those use (a palette `Choice`, bounded lengths); the kind's `settable` values. **Not** the
  package's low-level components, which would bypass the kinds' narrowing and make locks meaningless; not embedded
  packages (P15).
- P25 **`Raw` is refused in a kind unless declared** (**decided**): a field typed `Raw`, or a `Passthrough`, is a hole in
  the narrowing and in "safely generate" (P2). The build refuses one unless the kind names it (`allow_raw=["Card.body"]`: `Class.field`,
  or `Class.Passthrough` for a grammar that accepts one; **proposed** spelling), so the hole is in the declaration and in the `data` snapshot.
- P26 **Kinds are modules** (**decided**): each kind is `acme_tex.kinds.<name>`, with its classes (P24), `load`,
  `create` and `schema`. `acme_tex.kinds` lists them (`names()`, `modules()`: `list` and `all` would shadow builtins,
  which the lint refuses). The caller knows and cares which kind it loads: `<kind>.load` raises on a
  directory of another kind. A generic `acme_tex.load` is a nice-to-have.
- P27 **A document is a directory** (**decided**), not a single file: it holds the document's state (JSON, possibly
  several files), the last rendered `.tex`, the materialised payload, and the consumer's own resources. `load` takes a
  `pathlib.Path` to it (**decided**); fsspec paths are **parked** (not in v1). `save` and `check` act on that directory (`render` is pure and
  writes nothing), so the layout (A2) describes a document directory.
- P28 **The document is a texpkg object** (**decided**): `load` and `create` return a `Document` that holds the kind's
  texmodel tree (`doc.tree`, typed per kind: `Document[expert.Deck]`) and carries texpkg's interface as methods
  (`render`, `save`, `check`). No module-level `render(doc)`.
- P29 **`save` writes everything; there is no public `materialise`** (**decided**): the two states and history (D1–D3),
  the `.tex`, and the payload (materialising is a step inside `save`). It writes only what changed, and adds no history
  entry when the states are unchanged, so a `save` after a package upgrade only refreshes the payload. `check` stays
  read-only and reports what a `save` would change.

### The document directory

- D1 **A saved document records two states** (**decided**): (1) the **user's state**, the values the caller gave, with
  defaults written out and marked (V21); (2) the **template state**, the package as it was when the document was saved:
  its version and contracts, the default values, the kind's presets and locks, the design values it rendered with
  (L1), its schema, and the stack (V18). With both, a later release can migrate a document at the `tex` and `design`
  level from what the document itself records, not only from the snapshots the newer wheel ships.
- D2 **The last few saves are kept** (**decided**): each `save` keeps the previous pair of states as history; the last 3
  (fixed).
- D3 `create` writes both states; `save` rewrites them, moving the previous pair to history and dropping the oldest
  beyond the kept number (D2); `load` reads, migrates in memory and writes nothing. A stored document changes only when the
  caller saves (**decided**).
- D4 What a migration reads: the user's state and the old template state from the directory, the new template state
  from the installed wheel. A default migration (V22) compares the old template's default values with the new ones and
  moves each marked value whose default changed, as the consumer's `DefaultChange` says (`FOLLOW`, `FREEZE`, `ASK`, V23).
  A design change (a preset or lock that differs, or the `.sty`'s hash, D6) leaves the user's state alone and is reported
  per document by `doc.template_changes()` ("title colour: slate → moss"), the per-document form of an `output` change
  (V10); the stack's releases and `output` pairs are compared too, so a layout change with no other difference shows
  (**decided**).
- D5 **Layout: one visible `_texpkg/` folder** (**decided**): not hidden, and named so that nothing TeX-side treats it as
  its own; the file names inside are **decided**:

  ```
  decks/birds/
      _texpkg/state.json         the user's state: values, $defaults marks, kind, data version
      _texpkg/template.json      the template state: version, contracts, defaults, presets, design values, schema, stack
      _texpkg/history/1/…        the previous pair; up to 3
      deck.tex                   the last render
      images/…                   the consumer's own resources
      res/texpkg/…, *.ttf        the materialised payload (A2)
  ```

- D6 **The template state records only what reached the document** (**decided**): the settings `render` wrote for its
  kind (presets and locks, L8), the defaults it used (V21), and, for the values the build filled into the `.sty` from the
  design data (L1), the `.sty`'s hash, not the values. A change to those shows in D4's report as "the package's `.sty`
  changed", not as the value that moved. The design file itself is not copied.
- D7 **`save` keeps the plan of what it wrote** (**decided**): with each `.tex` (one per variant, K7), `save` writes
  texmodel's `Plan` of it (every line with the node path that wrote it) into `_texpkg/` (`plan.json`, `plan-<variant>.json`,
  **proposed** names), as the baseline a hand edit is found against: the file differing from its plan is a **hand edit**;
  the plan differing from a fresh render is a **model or package change**. texmodel could not tell these apart without a
  saved render (its §21a 5).
- D8 **A hand-edited `.tex` is given back to the consumer** (**decided**): `save` raises `HandEditError` when a `.tex` in the
  directory differs from its saved plan, and writes nothing. `doc.hand_edits()` returns each edit for the consumer's code
  to handle: the file, the data path the edited lines came from (the plan's node path mapped to the state, P23), what
  texpkg wrote and what the file holds now, and whether lines were added, removed or changed. `save(force=True)`
  overwrites the hand edit; `check` reports hand edits too. Generated payload files are not covered: `check` reports them
  changed (A4) and `save` rewrites them (**proposed**).
- D9 **Which field changed, and to what value, is texmodel's** (**proposed**, following texmodel 0.4.0's `Plan.edits`): where texmodel attributes an edit to one argument (`Line.spans`, `Edit.fields`) and
  reads it back as a typed value (`ValueKind.read`), a `HandEdit` carries the field's data path and its value; where it
  cannot (an edit over several arguments, a body, a custom kind without `read`), the edit carries the node's data path and
  the raw text, and the value is unknown, never guessed. texpkg reads no TeX itself (N1); applying an edit back to the
  document stays with the consumer until texmodel offers it. Not built (§8): `HandEdit.value` is `None`.

- D10 **A document carries its own settings, options and preamble entries, within what its kind allows** (**decided**).
  texmodel 0.5 holds them in the tree (`Document(*content, options=, settings=, preamble=)`), so a document of a kind is
  its root node (`doc.tree`) and `doc.settings`, `doc.options`, `doc.preamble`. A kind lists what a document may set:
  `Kind(settable=(Ink,), options=("a4paper",), preamble=(PdfInfo,))`, none by default, and a document naming anything else
  is refused whole (`NotAllowedError`, `TP-D007`, at `create` and `replace`; at `load` it is an unresolved item). A value
  is a preset or settable, not both (`TP-K017`): a preset (L8) stays written for every document and is in no data. Likewise
  `Kind(locked_preamble=PreambleSlots(before_class=(RequireMetadata(lang="en"),)))` holds typed entries every document
  is written with, in the slots given, after the layout's lines and the base kind's locked ones and before the document's
  own; they are in no data, and a document naming a locked class is refused (`NotAllowedError`, `TP-D007`; unresolved at
  load). An entry in a slot it does not fit, a `Raw`, a class locked twice or both locked and listed in `preamble`, and a
  profile that locks or allows what its base kind locks, are `TP-K020`. `Kind(defaults=(Gap(...),))` is where a
  document starts for a settable value (`TP-K021` for a class that is not settable): written after the presets and the
  variant's settings and before the document's own, so a document that sets the value wins. The template state keeps
  them; a changed one is followed, frozen (the document gets the old value as its own setting) or asked for (unresolved,
  path `/defaults/Gap`) as `default_changes` says, keyed by the class name, unless the document sets the value. A
  settable value is registered by the kind's package or a base of it (`TP-K018`); a profile kind's can be the base's. A distribution's
  `base` and its package's `base` name the same lineage (`TP-K019`). In the envelope
  they are `settings`, `options` and `preamble` beside `tree`, left out when empty, in texmodel's shapes, so every path
  in `tree` is unchanged. A migration sees them in `state["$extras"]`, with `$unresolved`. `render` writes the kind's
  presets and the variant's settings first, then the document's; the layout's preamble lines lead each slot (A5). A hand
  edit of a line the document wrote is at its data path (`/settings/0`, `/preamble/after_package/0`); a line the kind or
  the layout wrote keeps its plan path. Raw TeX in the preamble is a hole (P25) and is never allowed.

### Dependencies between packages

- P9 **A texpkg package can depend on others** (**decided**): a deck package builds on a brand package.
- P10 `save`, `check` and `export` cover the package and everything embedded in it, each file once (**decided**).
- P11 Two packages along a base chain providing the same TeX name, or the same payload path with different bytes, are a
  build error (B4) (**decided**).
- P12 *(Removed: with one base per package and the base embedded at build time, no cycle can form, P20.)*
- P13 **A dependency is embedded, not a Python dependency** (**decided**). The build generates the dependent
  distribution with its base inside it, as a linker links statically: the base's declaration, models, migrations,
  contract history and payload are copied into the dependent's wheel. At run time there is no resolver and no second
  wheel; the base is whatever release the dependent was built with.
- P14 The base is needed only at build time (**proposed**): its wheel is listed in `[build-system] requires` (Python
  packaging still delivers it, to the build) and named in the declaration by object, `Distribution(base=brand_tex.dist)`.
  No discovery.
- P15 **The embedded copy is private** (**proposed**): it lives inside the dependent's module (`acme_deck_tex._embedded.
  acme_brand_tex`), so a consumer can install the base, the dependent, and another dependent embedding a different
  release of the same base, side by side. Their Python types are distinct; data (mappings, JSON) crosses freely.
- P16 A base change reaches a dependent only when the dependent is rebuilt and released (the static-linking trade:
  reproducible, but no fix arrives on its own). The dependent's contracts include the embedded base's (V11): a base `.sty`
  change shows in the dependent's `output` fingerprint, so the dependent's release says it.
- P17 The embedded base's licence and notes travel with it into the dependent's wheel and payload (**proposed**).
- P18 **The whole base is embedded** (**decided**): its module, declaration, models, migrations, contract history and its
  whole payload. No subset is computed: the `.sty` cannot be split (N1) and pruning Python or assets would be machinery
  for a few megabytes. Pruning assets waits until wheel size hurts.
- P19 **Stacks flatten** (**decided**): a dependent's wheel holds one copy of each package in its stack side by side
  (`_embedded.acme_brand_tex`, `_embedded.acme_base_tex`), never copies inside copies. Code in a texpkg package imports
  its own package relatively, so a copy works wherever it is placed; the generated module does so, and the build refuses
  an absolute self-import in the author's code (B4) (**proposed**, the mechanism).
- P20 **One base per package** (**decided**): a package builds on at most one base, so a stack is a chain (deck → brand
  → layout) and no diamond can form. A need for two bases becomes a chain (the layout package is the brand's base); a
  variant of the same document in another format (an A4 and an A6 Discover card) is two kinds (K1), not two bases.
  `expand`, the L3 law and `\usepackage` order follow the chain; `expose=` takes plain kind names (P21). With one base,
  the field is `base=brand.dist` rather than a `requires=` list (**proposed**).
- P21 **Exposure is explicit** (**decided**): `Distribution(base=brand.dist, expose=["discover"])`, none by default. An
  exposed base kind joins the dependent's `data` contract (its snapshot, V11); a base `data` break in it is a break of
  the dependent at its next build (P16). An unexposed kind stays internal.
- P30 **Rebuilding against a newer base** (**decided**): one numbering per package. The dependent's snapshot records, for
  each exposed kind, which base `data` version each of its own `data` versions corresponds to; texpkg runs the base's
  migrations for that kind (`to=` in the base's numbering) at the dependent's matching boundary, so the
  dependent's author re-keys nothing. What the rebuild changes
  is otherwise covered: the base's `interface` (V17), its `.sty` and assets (the dependent's `output`, P16), its design
  values (reported per document, D4), and base types the dependent's own kinds reuse (its snapshot re-derived, V12).

### Profiles: embedded data and narrowing

texmodel gives the low-level API of the TeX a package ships. A texpkg package can carry data and use it to **narrow** that
API: set defaults, lock values, and offer higher-level APIs that limit what a caller can generate (**decided**, as an
aim). The first consumer does this: its token file fixes the colours, line widths and sizes its TeX may use, its modes
preset values a deck cannot set, and its deck models are a smaller surface than the package underneath. A package that
depends on another can be such a **profile** of it, a constraining proxy over the base (**decided**, as an aim).

- L1 **Embedded data**: a package ships typed data (a pydantic model plus its file: tokens, palettes, presets), validated
  at build time (B4), read with `importlib.resources`, at the package's version (**proposed**). The build may fill the
  `.sty` from it (texmodel's `library(fill=)`); the models use it to set defaults, locks and allowed values.
- L2 **Four ways to narrow** a base's API (**proposed**), each written by the author with texmodel's parts (K2), never
  inferred:
  - *default*: a value the caller may override (a field with a default);
  - *lock*: a value the caller cannot set (no field at all; `render` writes the value into the document, L8);
  - *restrict*: a smaller type (a `Choice` of the palette's colours instead of any `Colour`, a bounded `Length`);
  - *compose*: a higher-level component or document model built from the base's components (a card from rows, a title
    and a band).
- L3 **A profile document expands to a base document** (**decided**): `render_A = render_B ∘ expand_A`. The profile's
  models are the narrower surface; `expand` fills its defaults and locks and maps composed parts to the base's
  components. This gives a checkable law: every valid profile document expands to a valid base document (a hypothesis test
  the build or the package's tests run).
- L4 A profile may ship no TeX of its own (only data, models and settings) or add its own `.sty` that requires the base's
  (**proposed**). Both name their base the same way (`base=`, P20).
- L5 **A lock holds at the Python API, not in TeX** (**proposed**): a hand-written document can still `\renewcommand` a
  locked value.
- L6 Profiles stack: a deck profile over a brand profile over a base. Each narrows only the one below; a profile must
  not widen, and widening (a default or allowed value outside its base's type) is caught by the L3 law's tests (L7), not
  proved by the build.
- L7 **A profile is hand-written** (**decided**): its own kind classes and a hand-written `expand` to the base's, as a
  kind is (K2). texpkg checks it through the L3 law (property tests); not widening (L6) is tested, not proved. No
  overlay language: how much the case matters is not known yet. A declarative projection library (pydantic-prism's
  per-scope `override=` and field presence) is a candidate if profiles become common; it fits base-owned views of one
  pydantic model. Once texmodel's components are pydantic models (V25), one obstacle is left: its scopes are tagged on
  the canonical model (the base's author, not the profile's).
- L8 **A lock is written into each generated document** (**decided**): `render` writes a kind's or a profile's locked
  values as texmodel settings after `\usepackage`, never into a `.sty`. One mechanism for kinds and profiles; the `.tex`
  shows every value it was built with; no `.sty` changes for a lock, so a profile may still ship no TeX (L4). A
  plain-LaTeX user gets the locks only from the per-kind templates of an export (E1). Not a lock, and unaffected: the
  package's own definitions filled from its design data at build time (`library(fill=)`, L1), such as the first
  consumer's brand-wide colours and faces in its `.sty`.

### Document kinds

**A package can offer several kinds of document** (**decided**): the first consumer ships three card templates
(Discover, Expert, Vocabulary Builder) from one `.sty`. Each is its own deck model with its own counts, and values its
mode presets that a deck cannot set.

- K1 **Kinds are the packager's content** (**decided**): the author writes them with texmodel's parts; texpkg gives the
  slot: how a `Distribution` lists them (`Kind`, §4a), the envelope's `kind`, dispatch, and
  kinds as part of the `data` contract. One `.sty` defines what every kind needs (which kind a document is lives in the
  data, not in which file it loads); assets may be needed by some kinds only (A6).
- K2 **A kind is narrow because its author writes it narrow** (**decided**), with texmodel's existing parts: a default is
  a field default, a restriction a `Choice` or a bound, a lock the absence of a field plus a setting the kind writes. No
  narrowing feature in either library. A profile's models over its base are written the same way; texpkg only checks
  them (L3, L6).
- K3 Data names its kind: the envelope is `{package, data, kind, ...}`. `<kind>.load` checks it and raises
  `KindMismatchError` on another kind (P26); only the optional generic `acme_tex.load` dispatches on it. Each kind gives
  its own schema (`expert.schema(mode=)`, §4a) (**decided**).
- K4 **Kinds made from data are generated source, committed and checked** (**decided**). A hand-written kind is already
  a real class (P23). A kind whose classes depend on data (a series' card counts, bounds and allowed colours, listed in
  its tokens) is written by a generator: `[tool.texpkg] generate = "module:function"` names a pure
  `function(root: Path) -> {path: source}`, `root` the declaring package's directory and each path a `.py` file inside
  it. `texpkg-build generate` writes the files (each with a header; `--check` only reports) and removes generated files
  it no longer produces (the header carries `# fmt: off`, so a formatter leaves them as written); `pdm build` runs the function again and refuses a file that is missing, differs or is left over
  (`TP-B012`), and a function that is not deterministic or returns a bad path (`TP-B013`), as it refuses a stale
  `contracts/next` (V12). The declaration imports the files like any module, so a consumer's pyright, a wheel, a zip and
  an editable install all see real classes, and the contracts are snapshotted from them (V11). The generator must not
  import a module that imports what it writes, as the declaration does; the declaration may sit in a module of its package
  (`distribution = "pkg.declaration:dist"`) with `pkg/__init__.py` free of imports, and the generator then shares the
  package's pure modules. It may import anything else, the build environment included. A class name is a TeX name (P11), so each series' root and parts need distinct names
  (`ShortDeck`, `LongDeck`). Considered and not chosen: a `Kind` generator the build writes into the wheel, which needs
  the classes before the declaration has finished importing.
- K5 Kinds are part of the `data` contract: adding one is compatible, removing or renaming one is breaking and needs a
  consumer to migrate its data (V6). A profile can offer a subset of its base's kinds, narrow them, or add its own (**decided**).
- K6 **A kind declares its variants; building them is the consumer's** (**decided**). A variant is a named set of settings
  and class options (`Variant("review", options=("nocrop",))`, written after the document's own, not repeating them, and
  not limited to the kind's `options`) applied to the same document (the first consumer's `full`, `fronts`, `backs`, preview and technical builds):
  `Kind(..., variants=[Variant("fronts", settings=[...]), ...])`, and `doc.render(variant="fronts")` returns that
  variant's `.tex`, complete, with no hook files. Compiling each variant, and checking that the backs pair with the
  fronts page for page, stay with the consumer (N2); a kind may declare the pairing (`pairs=("fronts", "backs")`) so a
  checker knows what to assert (**proposed**). Declared variants are listed by the kind (`expert.variants()`), so a
  tool driving the package (a downstream MCP server, a build script) finds them without reading code.
- K7 Details: `save` writes `deck.tex` and one `deck-<variant>.tex` per variant (`deck` is the root class lower-cased, or the kind's `stem=`, `TP-K015` if it is not a file name); the variant names are part
  of the `interface` snapshot (V11), so removing or renaming one is breaking and adding one compatible; each variant's
  rendered example joins the `output` fingerprint (**decided**).

## 4a. API reference

Every name a consumer or an author touches, with its status. **decided**: agreed with the maintainer; **proposed**: drafted
and not yet agreed (the name or the shape may change); **open**: the question is in §10. `acme_tex` stands for any built
package, `expert` for any of its kinds, `Deck` for that kind's root class.

- P31 **A package publishes constants** (**decided**): `Distribution(public="acme_tex_decl.public")` names a module of the
  declaring package (`TP-K022` otherwise) whose `__all__` lists the constants (bleed, icon names, palette names) code that
  uses the package reads. The generator writes `acme_tex/public.py`, static source re-exporting each name from the
  embedded declaration (`from ._declaration.public import BLEED as BLEED`), so a type checker reads the declared types
  and no private path is imported. Values are JSON-like (strings, numbers, booleans, `None`, lists and dicts of those) or dataclass or pydantic
  instances (a `Length`, a margin), written in the snapshot as `{"$class": name, ...fields}`, or `{"$class": name, "value": text}` when the value has a text form (`TP-B014` for anything else, also for a missing `__all__` or name). Opt-in; a base's constants are not re-published. They are part of
  the `interface` snapshot (`public` in `interface.json`, absent when nothing is published): a name removed, or a value
  of another type or class, is breaking; a name added is compatible; a new value of the same type is a revision, since what the
  value drives shows in `data` and `output`. A migration cannot repair a removal: it rewrites stored documents, not code.

### Consumer side: the package module (`acme_tex`)

| Name | Signature | Status | Ref |
|---|---|---|---|
| kinds listed | `acme_tex.kinds.names() -> tuple[str, ...]` | decided | P26 |
| kinds by name | `acme_tex.kinds.modules() -> Mapping[str, KindModule]` | decided | P26 |
| plain-LaTeX export | `acme_tex.export(dest: Path \| str, *, now: datetime \| None = None, stamp: str \| None = None) -> tuple[Path, ...]` | decided: writes the package's `.sty`, those it embeds and every asset (in the layout, A2), refused whole if a file is missing; one template `.tex` per kind and a README: proposed | E1, A3 |
| any kind | `acme_tex.load(path: Path \| str, *, migrations: Sequence[Migration] = (), default_changes: DefaultChange \| Mapping[str, DefaultChange] = DefaultChange.FOLLOW) -> Document[Any]` | decided as a nice-to-have | P26, V23 |
| release version | `acme_tex.__version__: str` | decided | V1 |
| contract versions | `acme_tex.CONTRACTS: Contracts` (`.data`, `.interface`: `Triple(current, revision, age)`; `.output`: `Pair(current, revision)`) | decided | V10 |
| errors | `acme_tex.errors`: this package's error classes | decided | §4a errors |
| published constants | `acme_tex.public`: the names of `Distribution(public=)`; present only when declared | decided | P31 |

### Consumer side: a kind module (`acme_tex.kinds.expert`)

| Name | Signature | Status | Ref |
|---|---|---|---|
| the kind's classes | `expert.Deck`, `expert.Card`, … and the value types they use (`expert.Palette`, …) | decided; never the package's low-level components | P24 |
| load | `expert.load(path: Path \| str, *, migrations: Sequence[Migration] = (), default_changes: DefaultChange \| Mapping[str, DefaultChange] = DefaultChange.FOLLOW) -> Document[Deck]` | decided: a directory, a `Path`; migrated atomically or raises; refuses a directory of another kind; writes nothing | P26, P27, V31, V32, D3 |
| create | `expert.create(path: Path \| str, tree: Deck, *, settings=(), options=(), preamble=None) -> Document[Deck]`: refuses a directory that already holds a document; `settings` are typed as the kind's `settable` values, `options` as its `options` | decided: D10 | decided | P23 |
| name | `expert.NAME: Final[str]` | decided | K1 |
| schema | `expert.schema(mode: Literal["validation", "serialization"] = "validation") -> dict[str, Any]`: the data of a document, `{"tree": …}` and the `settings`, `options` and `preamble` the kind allows | decided | V26, D10 |
| example | `expert.example() -> Deck` | decided | E1 |
| variants | `expert.variants() -> tuple[str, ...]` | decided (listing); name proposed | K6 |
| what changed | `expert.changes(old: int, new: int) -> Changes` (fields added, removed, tightened; the author's notes; the release of each `data` version) | decided | V33 |

### Consumer side: `Document[T]`

| Name | Signature | Status | Ref |
|---|---|---|---|
| tree | `doc.tree: T` (frozen texmodel tree) | decided | P23, P28 |
| settings, options, preamble | `doc.settings: tuple[Value, ...]`, `doc.options: tuple[str, ...]`, `doc.preamble: PreambleSlots`: what the document carries within what its kind allows | decided | D10 |
| render | `doc.render(variant: str \| None = None) -> str` (pure: returns the `.tex`, writes nothing) | decided: a method, no module-level `render`; `variant=` decided (K6) | P28, K6 |
| save | `doc.save(*, now: datetime \| None = None, stamp: str \| None = None, force: bool = False) -> None` (writes both states, history, the `.tex`, its plan and the payload; only what changed; `now` pins the provenance time, N4; raises `HandEditError` on a hand-edited `.tex` unless `force`) | decided | P29, D1–D3, D7, D8, N4 |
| check | `doc.check(*, stamp: str \| None = None) -> Check` (never writes; reports hand edits too) | decided | P29, A4, D8 |
| hand edits | `doc.hand_edits() -> tuple[HandEdit, ...]`; `HandEdit(file, path, expected, found, kind, value=None)`, `kind`: `ADDED`, `REMOVED`, `CHANGED`; `path` is a field's data path when texmodel attributes the edit to one, else the node's; `value` is the typed value when texmodel can read it (D9) | decided (behaviour); field names and `value` proposed | D8, D9 |
| path | `doc.path: Path` | decided | P27 |
| kind | `doc.kind: str` | decided | K3 |
| defaults | `doc.defaults` (which values are still the package's defaults) | decided | V21 |
| stack | `doc.stack: Stack` | decided | V18 |
| template changes | `doc.template_changes() -> tuple[TemplateChange, ...]`: what a new release changes for this document (a preset, a lock, a default, the `.sty`); `TemplateChange(setting, old, new)` | decided (field names proposed) | D4, D6 |
| new tree | `doc.replace(tree: T \| None = None, *, settings=None, options=None, preamble=None) -> Document[T]`: what is not given stays | decided | P23, D10 |

### TeX side: provenance

| Name | What | Status | Ref |
|---|---|---|---|
| print it | `\<prefix>ProvenanceInfo`: "acme-tex 2.0.0, stamp …, materialised …", the parts that are empty left out | decided (a command); name proposed | V2 |
| its parts | `\<prefix>ProvenanceStamp`, `\<prefix>ProvenanceTime`, empty in the `.sty`, renewed by the provenance file | proposed | V2 |
| the file | `<name>-provenance.sty`, written by `save` and `export`, loaded by the package when present | decided (behaviour); name proposed | V2 |

### Results and errors

| Name | Shape | Status | Ref |
|---|---|---|---|
| `Check` | `.current: bool`; `.files: Mapping[Path, FileState]`; `FileState`: `UNCHANGED`, `CHANGED`, `MISSING`, `EXTRA` | decided | A4 |
| `MigrationError` | raised by `load`; `.unresolved: tuple[Unresolved, ...]`, each with its `data` boundary (`4 → 5`) and release | decided | V31 |
| `KindMismatchError` | raised by `<kind>.load` on another kind's directory; `.found`, `.expected` | decided | P26 |
| `NewerDataError` | data written for a newer `data` version than this release | decided | V14 |
| `HandEditError` | raised by `save` when a `.tex` differs from its saved plan; `.edits: tuple[HandEdit, ...]` | decided | D8 |
| `NotAllowedError` | raised by `create` and `replace` for a setting, option or preamble entry the kind does not allow; `.items`, each with its data `path`, `reason` and `value` | decided | D10 |
| `NotADocumentError`, `PayloadError` | no state in the directory; a payload that cannot be written whole | decided | P27, A3 |
| shared types across packages | **none** (decided): each package's classes are its own (B7). Every error subclasses a built-in and carries a stable `.code`, so `except ValueError` plus the code works across packages: `MigrationError`, `KindMismatchError`, `NewerDataError`, `HandEditError` subclass `ValueError`; `NotADocumentError` and `PayloadError` subclass `FileNotFoundError` (**proposed**: the bases and the code scheme, e.g. `TP-M001`) | decided | B7, B11 |

### Migrations (written by a kind's author or a consumer)

| Name | Signature | Status | Ref |
|---|---|---|---|
| decorator | `@migration(to: int)`: from `data` version `to - 1` to `to` | decided | V32 |
| function | `(state: dict[str, Any]) -> Migrated`, plain data in, run before validation; the items earlier migrations left are in `state["$unresolved"]` (a list of `{path, reason, value, boundary}`), and the document's `settings`, `options` and `preamble` in `state["$extras"]`, which a migration may edit | decided; the `$unresolved` key proposed | V28, V32 |
| result | `Migrated(state: dict[str, Any], unresolved: Sequence[Unresolved] = ())` | decided | V32 |
| unresolved item | `Unresolved(path: str, reason: str, value: object)`; texpkg fills `.schema` (the new schema at that path) and `.boundary` | decided | V15, V32 |
| on a kind | `Kind(..., migrations=[...])` | decided | V32 |
| from a consumer | `<kind>.load(path, migrations=[...])` | decided | V32 |
| order | per `data` boundary: the build's (renames, defaults), the kind's, the consumer's | decided | V32 |

```py
from texpkg import Migrated, Unresolved, migration

@migration(to=5)
def standards_to_ticks(state: dict) -> Migrated:
    ticks, unknown = match(state.pop("standards"), FIXED_STANDARDS)
    state["standards"] = ticks
    return Migrated(state, unresolved=[Unresolved("/standards", "not in the fixed list", row) for row in unknown])

doc = datasheet.load(path, migrations=[place_unknown_standards])   # a consumer extends the process
```

### Author side: the declaration

Declaration types come from the run time (`texpkg`), never from `texpkg-build`: the declaration ships in the wheel (P22).

| Name | Signature | Status | Ref |
|---|---|---|---|
| distribution | `Distribution(name, module, package, root=".", design=None, assets=(), kinds=(), base=None, expose=(), public="")`; `root` is the directory asset paths are relative to: a path relative to the module that calls `Distribution(...)` (default: its own directory) or absolute, inside the declaring package; its import name (`declared_in`) is read from the call. Symlinks are followed; outside the package: `TP-K013`, not a directory: `TP-K014`; `public`: a module of that package, `TP-K022` | proposed (fields, and the name `base=`); the base named by object, `expose=` explicit, none by default: decided | B1, P14, P20, P21 |
| kind | `Kind(name, model, presets, example, migrations=(), allow_raw=(), variants=(), expand=None, over=None, stem="", settable=(), options=(), preamble=(), locked_preamble=PreambleSlots(), defaults=())`; `Variant(name, settings=(), options=())` | decided (`variants=` and `Variant` spelling proposed) | K1, V32, P25, K6 |
| asset | `Asset(path, role: Role, why: str, kinds=())`; `Role`: `PACKAGE`, `GRAPHIC`, `FONT`, `BY_PATH`, `NOTE` | decided (`kinds=` spelling proposed) | A1, A6 |
| embedded data | `Design(model: type[BaseModel], path: str)` | decided | L1 |
| default policy | `DefaultChange.FOLLOW`, `.FREEZE`, `.ASK`: an `@enum.unique` enum (a `StrEnum`, so one package's value equals another's), passed by the consumer to `load(default_changes=...)`; the `FOLLOW` default and the per-path mapping are proposed | decided | V23 |
| `Raw` in a kind | refused unless named: `allow_raw=["Card.body"]` | decided | P25 |

### Author side: the project and the build

```toml
[build-system]
requires = ["pdm-backend", "texpkg[build]>=0.4", "acme-brand-tex==7.0.0"]   # a base pinned exactly: it is embedded
build-backend = "pdm.backend"

[project]
name = "acme-tex"
dynamic = ["version", "dependencies"]          # the build writes pydantic's range (B7)

[tool.texpkg]
distribution = "acme_tex_decl:dist"
```

| Name | What | Status | Ref |
|---|---|---|---|
| the hook | `pdm_build.py` re-exports `texpkg_build`'s pdm hook functions | decided | B2 |
| the declaration's pointer | `[tool.texpkg] distribution = "module:attr"` | decided | B3 |
| the generator (optional) | `[tool.texpkg] generate = "module:function"`; `texpkg-build generate [--check]` | decided | K4 |
| base pinned exactly | `==` in `[build-system] requires` | proposed | P14 |
| contract versions | `texpkg-build contracts`: compares with the last snapshot, writes the versions file | decided: a command, for authors | V12 |
| build | `pdm build`: generates the module, renders the `.sty`, embeds, refuses what would ship broken | decided (behaviour) | B1, B4 |

## 5. Assets and the layout

- A1 An asset is `Asset(path, role, why, kinds=())`; `Role` is an enum (**decided**): `PACKAGE` (`.sty`), `GRAPHIC`, `FONT`,
  `BY_PATH` (named by path in a preamble, keeps that path), `NOTE` (notes, licences). The role decides placement; no rule is
  inferred from a suffix.
- A2 The layout (**decided**): one, fixed, not part of the declaration API. `.sty` and graphics go in `res/texpkg/`, fonts
  at the root because luaotfload reads no document-side search path, `BY_PATH` at its own path. Every distribution in a
  chain writes there, so one set of preamble lines finds all of it; `save` and `export` both use it. A TDS / `TEXMFHOME`
  layout waits for a consumer that needs it.
- A3 Materialising refuses the whole payload if any file is missing, writes bytes (never a link or a path) and removes
  nothing (**decided**).
- A4 `check` compares by content, never by mtime. Each file is `unchanged`, `changed`, `missing` or `extra` (`extra`: a
  file in a place materialising writes to that it did not write, such as a retired `.sty`). Generated files that hold a
  time are compared by stamp (**decided**).
- A5 The layout also gives the preamble lines a document needs (`\input@path` before `\usepackage`, and `\graphicspath{{}{dir/}}`
  after it for a kind that has a graphic: `\graphicspath` is `graphicx`'s) so the generated `.tex` and the layout cannot disagree (**decided**).
- A6 **An asset may name the kinds that need it** (**decided**): `Asset(..., kinds=["expert"])`; an asset naming none is
  needed by every kind. `save` writes the `.sty` and the assets the document's kind needs; `check` compares that set;
  `export` still writes everything (E1). texpkg does not read TeX to find what a kind loads (N1), so the declaration is
  proved on the packager's side (A7).
- A7 **A per-kind payload is proved by compiling** (**proposed**): a test helper of `texpkg_build.testing` (`check_isolated`) saves each kind's
  example, in each of its variants, into a fresh directory holding only that kind's payload, and compiles it with the
  search environment unset (no `TEXINPUTS`, no `OSFONTDIR`), through texmodel_build. It fails on a missing file, and on
  any embedded font or graphic read from outside the directory, since luaotfload can substitute a system font without an
  error (the first consumer's font check). It proves only what the example uses, so a kind's example exercises the whole
  kind: every optional part and variant (the same examples feed the `output` fingerprint, V11).
- A8 **The embedded-font check is texmodel_build's** (**decided**): `texmodel_build.fonts` reads each embedded font's
  path from the LuaTeX log and flags any outside the allowed directories; A7 uses it. It does not see fonts inside an
  included PDF: a check that says where it stops.

## 6. Versions and provenance

- V1 The release version: `\ProvidesPackage`, the provenance stamp and `acme_tex.__version__` come from one constant the
  build writes into the generated module, from the distribution's version at build time (**decided**), never from
  `importlib.metadata` at run time: an embedded copy has no metadata of its own (B10). It names a release; what changed in it is said by the
  contract versions below (V10), and it summarises them (V13).
- V2 **Provenance is a command a document can print** (**decided**), as the first consumer's `\bbBundleInfo`: the
  package declares `\<prefix>ProvenanceInfo`, which composes the package and version (from the `.sty`, always there) with a
  stamp and a time (empty in the `.sty`), so a proof can carry it on the page (a slug, a crop margin) and a PDF says what it
  was built from once it leaves the directory. `save` and `export` write `<name>-provenance.sty`, which renews the stamp
  and the time (the clock's, or the `now=` given: N4) and which the package loads when present; it is the only payload file with a time, so every other stays
  byte-comparable (A4). Names (**proposed**): `\<prefix>ProvenanceInfo`, `\<prefix>ProvenanceStamp`,
  `\<prefix>ProvenanceTime`, `<name>-provenance.sty`. The declaring side is a texmodel component (§1, N5); it compares
  against an empty value declared the same way as the values (`\newcommand` makes a `\long` macro, which `\ifx` against
  `\@empty` never equals: a trap the first consumer recorded).
- V3 `check` reads the stamp in the provenance file and reports a payload from another version.
- V4 A build stamp with a commit hash (`<ver>-<hash>[-dirty]`) is the consumer's; texpkg takes the stamp as an argument
  (N4).
- V34 **Provenance goes into the PDF's metadata too** (**decided**): a proof's slug is cut before print, the metadata stays.
  The provenance file adds the same text as a custom Info entry (`/<Prefix>Provenance`, **proposed** name) through LaTeX's
  PDF management, as texmodel's `PdfInfo` does, only when it is active (`\IfPDFManagementActiveTF`); without it the
  entry is skipped, not an error. It lives in the provenance file, not the generated `.tex`, so the page and the metadata
  carry the same time and `render` stays pure (**proposed**). Proved by compiling (read back from the PDF) and by veraPDF
  against PDF/A-2b and PDF/X, which constrain metadata; if a custom Info key fails them, an XMP property in a texpkg
  namespace replaces it.

### Document versions and migrations

- V5 **Documents are versioned data** (**decided**: the module API has version control and migrations). A consumer stores
  its documents as data recording the `data` contract version they were written for (V14); `load` brings older data to
  the current version where the package can, then validates. Data from a newer version than the installed one is refused.
- V6 **Who migrates what follows who knows what it means** (**decided**). texpkg never transforms content; it runs migrations
  and reports.

  | Content | Migrated by |
  |---|---|
  | what the package owns: defaults, presets and locks, design values, the template state, the payload | the package, automatically (V22, D4, P29); renames by alias |
  | a field the kind defines (a datasheet's table of standards, a fabric's specs) | **a migration shipped with the kind**, written by its author, who designed both shapes |
  | what only the consumer knows (content whose structure the consumer chose) | **a migration the consumer supplies** to `load` |

  Example: the designers of a datasheet replace its table of standards with a text box, or with a fixed list of every
  standard and a tick against those met. The kind's migration maps each row to the fixed list; a row naming a standard the
  list does not hold cannot be placed. That migration is specific to the datasheet.
- V7 A release freezes its contract snapshot (V11), so a consumer can diff what a document may say between two releases.
- V8 **Migrations are worked out here and crystallise into texmodel** (**decided**). texmodel has declared renames
  (`renamed_from`) and the rest is not built; texpkg is where the real needs show up, so the design is found here first. What is about one
  model moves to texmodel once it is stable; what is about packages stays here. Proposed split:
  - *texmodel*: one model's history: declared renames (aliases), classifying a change (compatible or breaking) by
    diffing two declarations.
  - *texpkg*: the package around them: the data envelope (`package`, `data`, `kind`, the stack, V18), contract versions
    (V10–V17), the migration API and running migrations in order (V28, V32), default migrations (V22), kinds added or
    removed between releases (K5), the frozen schemas of earlier releases shipped in the wheel (V7, V33), and the report
    of what is unresolved (V15, V31).
- V9 Until a piece moves, texpkg code that will become texmodel's is kept in one module with no texpkg-only dependency, so
  the move is a cut, not a rewrite (**proposed**). Each move is a texmodel change with its own tests, and texpkg then imports
  it.
- V31 **Adopting a new release is atomic** (**decided**): every migration across the versions crossed runs, and the
  result validates whole, or `load` raises, with nothing returned and nothing written. A migration that cannot place
  everything does not return half a document: it leaves the item unresolved, and any unresolved item, or any validation
  error left after all migrations, aborts. The exception (`MigrationError`) lists each
  unresolved item (path, what changed, the old value, the new schema), so the consumer **extends or amends the process**
  with a migration of its own and loads again.
- V32 **One migration API, whoever writes it** (**decided**): a kind lists its migrations (`Kind(..., migrations=[...])`)
  and a consumer passes its own (`expert.load(path, migrations=[...])`); the
  default policy (V23) runs first, then for each `data` boundary crossed the kind's migrations and the consumer's, in
  order, each seeing what the earlier ones left unresolved (`state["$unresolved"]`). All are optional: a breaking change with no migration
  anywhere aborts with the report.

  ```py
  from texpkg import Migrated, Unresolved, migration

  @migration(to=5)                                     # from data version 4 to 5
  def standards_to_ticks(state: dict) -> Migrated:     # plain data in (V28)
      ticks, unknown = match(state.pop("standards"), FIXED_STANDARDS)
      state["standards"] = ticks
      return Migrated(state, unresolved=[Unresolved("/standards", "not in the fixed list", row) for row in unknown])
  ```
- V33 **A `data` version can be traced to a release and explained** (**decided**): each snapshot records the release
  that introduced each `data` version, so a report says "data 5 (acme-tex 2.0.0)"; the changelog lists `data` versions
  ("data 5 (2.0.0): the datasheet's table of standards became a tick list"), generated from the snapshot diff and the
  author's one-line note; and a kind answers `changes(old, new)`: what changed between two `data` versions (fields
  added, removed, tightened, and the note), read from the shipped snapshots. A consumer writing a migration reads that,
  not the package's source.

### Contract versions

A package is versioned by **contract**, by what its consumers rely on, not by the layer an author edits (**decided**).
A change in one layer can break several contracts (a design change can invalidate stored data and change every proof),
so the layers (the TeX, the embedded data, the kinds) only say where a change came from.

| Contract | What it promises | Format | Consumer |
|---|---|---|---|
| `data` | what a stored document may say: the JSON Schema of every kind | `current:revision:age` | stored documents |
| `interface` | the public TeX names and their signatures, and the component classes that mirror them | `current:revision:age` | hand-written `.tex`, an export, profiles built on the package |
| `output` | what the same data renders to | `current:revision` | approved proofs, print runs |

- V10 **The format is libtool's** (**decided**). `current` numbers the contract, `revision` counts implementation changes
  within it, `age` how many earlier `current`s are still supported (`current - age` … `current`). The rules:

  | Change to the contract | Bump |
  |---|---|
  | none | none |
  | implementation only | `c:r+1:a` |
  | compatible addition | `c+1:0:a+1` |
  | breaking change | `c+1:0:0` |

  `output` has no age ("earlier output is still valid" means nothing): `current` when the appearance changed and proofs
  need approving again, `revision` when bytes changed and nothing visible should have.
- V11 **A contract snapshot per release** (**proposed**): the build writes, under a committed `contracts/<release>/` and
  into the wheel, the facts each contract is compared on. None needs TeX:
  - `data`: each kind's JSON Schema;
  - `interface`: the public names with their argument signatures, from the texmodel declaration;
  - `output`: a fingerprint of the rendered `.sty` (the embedded base's too, P16), of each kind's example rendered to
    `.tex` in every variant (K7), and of the asset bytes (rendering is deterministic, B5, so any change shows); the
    snapshot also stores each example's data (V35).
- V12 **Numbers are computed, then recorded** (**proposed**). The build diffs the snapshot with the previous release's
  and classifies each contract: `data` by Avro-style rules (an optional field added is compatible; a field removed or
  renamed without an alias, a bound tightened, a type changed is breaking; a description changed is a revision);
  `interface` the same way over names and signatures (a body changed is a revision). It proposes the new triples; a
  function writes them to a committed versions file the author reviews. The build refuses a stale versions file and an
  unclassified `output` change: whether a fingerprint change is visible is the one judgement a program cannot make
  without compiling, so the author states `current` or `revision`. Nothing is inferred silently: the file is the record.
- V13 **The release version follows the bump table (V10)** (**decided**): a breaking or possibly breaking change (an
  age reset, or a change the build cannot classify) is **major**; any other change is **minor**, an `output` change
  included; a release that changes no contract (packaging, docs) is a patch (**proposed**). Each moves one place lower
  before 1.0. So a consumer's Python range (`>=1.4,<2`) means "until it breaks me". The wheel version is still the git
  tag (V1); the build refuses a tag that understates the contracts (**proposed**).
- V14 **Loading by `data` age** (**proposed**). The envelope records the `data` current `w` the document was written
  for. `current - age ≤ w ≤ current`: it validates as it is (after renames and default migrations). `w` older: the migrations for
  each boundary crossed run in order (the build's, the kind's, the consumer's, V32), and the result must validate whole (V31).
  `w > current`: refused.
- V15 **What no migration resolved is reported, never guessed** (**decided**). An unresolved item names the path, what
  changed, the new constraint (the JSON Schema of that path) and the old value; it comes from a migration that could not
  place something, or from validation after the migrations (V30). A stored field the model no longer has is reported the
  same way, since loading would drop it without a word: only a migration removes content, on purpose. texpkg never
  transforms user content and never calls a model (N4).
- V16 **Only what breaks is reported** (**proposed**): a tightened bound (a shorter `max_length`, fewer rows) or a value
  removed from a restricted palette (L2) reports only the values that break it; data that still fits migrates silently.
  How: V30.
- V17 **Stacks are checked at build time only** (**proposed**): with the base embedded (P13), nothing can change under
  the dependent after it is built. The build records which base contracts the dependent relies on (`interface` always,
  `data` when it composes over the base's kinds) and, on a rebuild against a newer base, refuses when the base no longer
  supports the recorded `interface` current, as a linker checks a soname, or reports what the dependent must migrate.
- V18 **A document records its stack** (**proposed**): the `data` current of its own package and the `output`
  `current:revision` of every package in the stack it was rendered through, so "rendered with exactly this" can be checked
  later. It is the document's lockfile. With embedding (P13) the stack follows from the top release, and is written out
  anyway so a reader needs no wheel to know it.
- V19 Whether text still fits is measured by TeX, not by any contract (texmodel's `Overset`): an `output` change can leave
  data valid and overflow a card. **A compile's "does not fit" stays separate** from the migration report (**decided**):
  `load` is pure Python and atomic (V31) and texpkg never compiles (N2), so overflow remains a texmodel_build diagnostic
  (`Overset`) with its TeX location, which the consumer handles on its own.
- V20 The brand pack's own version (`0.13.2`) stays a label: it names a design for people, carried in the provenance
  file (V2), and promises no compatibility.
- V35 **The `output` fingerprint compares the same data** (**decided**): the build renders the **previous** release's
  example data with the new package and compares it with the previous release's `.tex`, so editing an example is not
  an output change, and the package's `.sty` is rendered at a fixed version, so the release number is not one either; a new or edited example is the baseline for the next release, and an example whose data no longer
  loads (a `data` break) is reported as not compared, never guessed. The snapshot holds **one hash per file** (each
  `.sty`, each example `.tex` per variant, each asset), so the build reports which files changed. **Every byte counts**:
  a comment or texmodel's generator stamp changing is an output change the author classifies as a `revision` (V12);
  nothing is stripped, since that would mean reading TeX (N1).
- V36 **The versions file is a file of its own, inside each snapshot** (**decided**): `contracts/<…>/versions.toml` holds
  the triples, the release, the author's `output` classification and the one-line notes (V33), apart from
  `pyproject.toml` and the declaration, so a command never rewrites hand-written configuration or Python.
- V37 **Snapshots freeze at release** (**proposed**), as texmodel's plan X2 does for schemas: `texpkg-build contracts`
  rewrites `contracts/next/` while developing (the versions file, both schemas per kind, `interface.json`, `output.json`
  with one hash per file, each example's data and rendered `.tex`) and proposes the next release version (V13); a
  release step freezes `next/` into `contracts/<version>/`, never rewritten after; right after a freeze `next` describes the release just made, and `texpkg-build contracts` starts the next; the build refuses a tag that does not
  match the newest frozen directory or understates it. The wheel carries every frozen directory (`changes`, migrations
  and V35 read them).

Examples:

| Event | `data` | `interface` | `output` | Migration |
|---|---|---|---|---|
| a short text box type added, optional in a kind | 1:0:0 → 2:0:1 | 1:0:0 → 2:0:1 | 1:0 → 1:1 | none: old data is still valid |
| the brand changes a colour's value | – | – | 1:1 → 2:0 | none; proofs approved again |
| the brand drops a palette colour | 2:0:1 → 3:0:0 | – | → 3:0 | aborts for documents that named it, unless a migration maps the colour |
| a field shortened by 30% | 3:0:0 → 4:0:0 | – | maybe | aborts for values that no longer fit, unless a migration shortens them |
| a datasheet's table of standards becomes a fixed tick list | 4:0:0 → 5:0:0 | maybe | → 4:0 | the kind's migration maps rows to ticks; an unknown standard aborts until a consumer migration places it |

### Defaults in stored documents

- V21 **Defaults are written out and marked as defaults** (**decided**). A saved document holds every value it was
  rendered with, so it reproduces on its own; the mark says which values came from the package rather than the author.
- V22 **Default changes migrate automatically, with the distribution** (**decided**, as the rule; exceptions exist). When
  a release changes a default, a value still marked as default moves to the new one (under the consumer's `FOLLOW`, V23), and stays marked; a value the author
  set is left alone. It compares the defaults the document saved (its template state, D1) with the installed package's, so it
  needs no snapshot and nothing hand-written.
- V23 **Whether a document accepts a changed default is the consumer's decision** (**decided**): a downstream migration
  decision, like every other data-level one (V6). The package ships what changed (old and new default values, D1, V22);
  the consumer chooses at `load`: `default_changes=DefaultChange.FOLLOW` (marked values move to the new default),
  `.FREEZE` (they keep the old value, which stops being marked) or `.ASK` (adoption aborts with each changed default as
  an unresolved item, V31); one policy for the document, or a mapping from path to policy (**proposed**). The package
  author declares no policy.
- V24 The mark is kept on each node: a node's state lists which of its own fields hold defaults (`"$defaults":
  ["colour"]`) (**proposed**). Local names, not pointers into the whole document, so a migration that moves or
  restructures a node carries its marks with it instead of rewriting a global list; values stay plain. The state is
  texpkg's storage format, read by `load` and migrations, not designed for other readers.
- V25 **Telling a default from a value the author set is pydantic's `model_fields_set`** (**decided**), on every tree,
  however it was built: texmodel's components become pydantic models (a texmodel decision, reversing its "component
  classes stay stdlib dataclasses"; texpkg depends on it, N5). A value equal to the default but set by the author stays
  the author's. texmodel has switched since 0.4.0 (its components are frozen pydantic models,
  `model_fields_set` is what the caller passed).

### Pydantic for state, schemas and migrations

**texpkg follows pydantic's patterns and uses pydantic for the stored state and its migrations** (**decided**). The state
is the data boundary, where the project's rule already puts pydantic; texmodel builds pydantic models from its
components today (`spec`), so each kind's state model is one of those, extended.

- V26 **Two schemas per kind, from pydantic's two modes** (**proposed**): `model_json_schema(mode="validation")` is the
  input schema (a field with a default is optional and carries `"default"`); `mode="serialization"` is the stored
  schema (every field is written, V21, so every field is required). `expert.schema()` is the input one; the contract
  snapshot (V11) records both.
- V27 **Writing and reading the mark** (**proposed**): `save` is `model_dump(mode="json")` with defaults kept, and a
  wrap serializer adds each node's `$defaults` from its `model_fields_set`. `load` strips `$defaults` in a before
  validator and rebuilds `model_fields_set` from it, so a round trip keeps what was given. The stored schema limits
  `$defaults` to the node's defaulted fields, and an after validator checks a marked value equals its default.
- V28 **A migration is a before validator over plain data** (**decided**): a function from the stored dict of one `data`
  version to the next, returning the data and what it left unresolved (`Migrated`, V32). A rename is read by texmodel
  before validation (`field(renamed_from=)`) and a changed default is applied from the document's saved template state
  (V22), so neither needs a derived migration; a kind's and a consumer's are written by hand. Old data is never validated against an old model: only the result validates,
  against the current model, so the wheel needs no old model classes, only the migrations and the snapshots.
- V29 Default migrations run on every load that crosses a default change, whatever the age (V14): a changed default breaks no
  data (a revision by the bump table) yet must move marked values (**proposed**).
- V30 **What validation leaves is pydantic's errors** (**proposed**): all migrations run, the result validates against the
  current model, and each remaining `ValidationError` entry (`loc`, `type`, `ctx` such as `max_length`) becomes an
  unresolved item: path, what is wrong, the constraint. A tightened bound or a dropped
  palette value needs no code to produce its item, and data that still fits passes.

## 7. Export (opportunistic)

- E1 `export(dir)`: the payload in the layout (A2), a template and a README per kind; the templates carry the layout's search-path lines and compile with a bare `latexmk -lualatex`.

## 8. Not built yet

- **Move the per-model core into texmodel** (V8, V9) once it is stable: `_internal/history.py` (data paths, problems,
  unplaced fields), `classify.py`, `versions.py`, `provenance_tex.py`. texpkg then imports it.
- **Port the first consumer** (acceptance): its `pack` becomes a texpkg declaration with no change to its output. Its
  kinds are its series, generated from its tokens (K4); cards become texmodel nodes; its hook files become
  variants (K6). Accepted when its generated `.sty`, `deck.tex` for every series and its `derived/` files are
  byte-identical before and after. A byte difference is attributed to texmodel or texpkg before it is fixed.
- **A hand edit's field and value** (D9): `HandEdit.value` is `None`; texmodel 0.4.0 offers `Plan.edits` and
  `texmodel_build.hand_edits.read_edits`, which read an edit through TeX stubs. texpkg spawns no process (N4), so how
  the value reaches `HandEdit` is open.
- **A template project** for starting a package (open question 3).
- A TDS / `TEXMFHOME` layout and fsspec paths wait for a consumer that needs them (A2, B9).

## 9. Decisions log

| Decision | Status |
|---|---|
| The wheel is the primary distribution format; a raw LaTeX bundle is opportunistic | decided |
| A texpkg package carries its texmodel API so a project generates TeX from its own data | decided |
| API and TeX ship at one version | decided |
| texpkg is a pure library: no process, no clock; stamps and times are arguments, except the provenance time, read from the clock unless `now=` is given | decided |
| one fixed layout, `res/texpkg/`, for `save` and `export`; TDS later | decided |
| No command line for consumers in v1 (a library only); authors get the `texpkg-build` command | decided |
| Compiling, search-path environments and the font check are outside texpkg | decided |
| texpkg packages can depend on each other | decided |
| An installed package is a Python module with a fixed, well-known, strictly defined API for emitting LaTeX | decided |
| That API has version control and migrations: documents are versioned data, lifted to the current version on load | decided |
| A dependency is embedded into the dependent at build time (static linking), not a Python run-time dependency | decided |
| The base is a build requirement, named by object; the embedded copy is private to the dependent | proposed |
| Base compatibility is checked at build time only | proposed |
| The whole base is embedded; stacks flatten to one copy per package; one base per package (a chain); base kinds are exposed only when listed | decided |
| The API surface is a `Protocol` plus a conformance check | decided |
| A package can carry data and narrow a base's API with defaults, locks and higher-level models; a dependent package can be a constraining proxy (profile) of its base | decided |
| Narrowing is written by the author as default, lock, restrict or compose (no narrowing feature); a profile document expands to a base document (the L3 law) | decided |
| A lock holds at the Python API only | proposed |
| A package can offer several document kinds | decided |
| A kind narrows its own package's API because its author writes it narrow; data names its kind | decided |
| The build generates a typed model per kind | decided |
| The declaration ships as a private module | decided |
| A document is a texmodel tree of a kind's classes; data is its serialisation | decided |
| The module exports the fixed surface, kind classes and their value types; never low-level components | decided |
| `Raw` in a kind is refused unless the kind declares it | decided |
| Each kind is a module with its own `load`; `<kind>.load` refuses another kind; generic `load` is a nice-to-have | decided |
| A document is a directory, loaded from a `pathlib.Path` (fsspec parked) | decided |
| A saved document records the user's state and the template state; the last 3 saves are kept as history | decided |
| A saved document writes defaults out and marks them; a default change migrates marked values by a migration the build derives and bundles; whether a document accepts it is the consumer's choice (V23) | decided |
| `load` returns a texpkg `Document` holding the kind's tree, with `render`, `save`, `check` as methods | decided |
| `save` writes the states, the `.tex` and the payload; no public `materialise` | decided |
| Kinds are the packager's content, built from texmodel's parts; texpkg provides the slot; no narrowing feature in either library | decided |
| texmodel owns one package and its documents (and one model's history); texpkg owns what spans releases, packages or a wheel | decided |
| A texmodel gap is built aside in texpkg, then moved; texpkg never works around texmodel | decided |
| texmodel's API is part of every package's public API; each package's copy is its own | decided |
| The TeX side of provenance goes to texmodel; texpkg writes the contents | decided |
| Migrations are designed in texpkg; the per-model part moves to texmodel when stable, the package layer stays | decided |
| A package is versioned by contract (`data`, `interface`, `output`), not by layer; layers say where a change came from | decided |
| Contract versions use libtool's `current:revision:age` (`output`: `current:revision`) | decided |
| Contract versions are computed from snapshot diffs and recorded in a committed file; the build refuses a stale one | proposed |
| The release version follows the bump table: breaking or possibly breaking is major, any other change minor | decided |
| A document records its stack (its lockfile); stacks are checked by `interface` age | proposed |
| Who migrates follows who knows the meaning: the package what it owns, a kind's migration its fields, a consumer's migration its own content; texpkg runs migrations and reports | decided |
| A `data` version maps to its release; the changelog lists `data` versions; a kind answers `changes(old, new)` | decided |
| Whether a document accepts a changed default is the consumer's choice at `load` (`default_changes=`); the author declares no policy | decided |
| Provenance is a command the package declares (`\<prefix>ProvenanceInfo`), printable on a proof; the provenance file renews its parts | decided |
| Provenance also goes into the PDF's metadata, written by the provenance file | decided |
| A profile is hand-written (its classes and `expand`), checked by the L3 law; no overlay language | decided |
| A lock is written into each generated document by `render`, never into a `.sty` | decided |
| An exposed base kind joins the dependent's numbering; the snapshot maps versions and texpkg runs the base's migrations at the matching boundary | decided |
| A kind declares its variants and `render(variant=)` writes each as a complete `.tex`; compiling and pairing checks are the consumer's | decided |
| An asset may name the kinds that need it; `save` writes only the document's kind's payload; proved by compiling each kind's example in isolation | decided |
| The embedded-font check (the first consumer's `fonts.py`) moves into texmodel_build, generalised to allowed directories | decided |
| A compile's "does not fit" stays a texmodel_build diagnostic, separate from the migration report | decided |
| The `output` fingerprint renders the previous release's example data with the new package; one hash per file; every byte counts | decided |
| The versions file is its own file inside each contract snapshot, not `pyproject.toml` or the declaration | decided |
| No types are shared between packages: errors subclass built-ins with a stable `.code`; enums are `StrEnum`s | decided |
| The template state records the kind's settings, its defaults and the `.sty`'s hash, not the design file | decided |
| `save` keeps a plan of each `.tex`; a hand-edited `.tex` raises `HandEditError`, `doc.hand_edits()` gives the edits to the consumer, `save(force=True)` overwrites | decided |
| Adopting a release is atomic: all migrations succeed whole or `load` raises, asking the consumer to extend the process | decided |
| One migration API (`@migration(to=N)`, `Migrated`, `migrations=[...]`) for the build's, a kind's and a consumer's migrations; a migration is a before validator over plain data | decided |
| State, schemas and migrations follow pydantic's patterns and use pydantic | decided |
| texmodel's components are pydantic models, so every tree carries `model_fields_set` (texmodel 0.4.0) | decided |
| texpkg builds the module from the author's declaration at wheel build time | decided |
| texmodel and texpkg's run time are embedded in each wheel; only pydantic stays a dependency | decided |
| texpkg is one distribution with two import packages: the run time (embedded) and the build (never reaching a consumer) | decided |
| fsspec is parked: not in v1, a document directory is a `pathlib.Path` | decided |
| The package's version keeps the usual major / minor / patch meaning | decided |
| The build is a pdm-backend hook calling `texpkg-build`; the declaration is named in `[tool.texpkg]` | decided |
| The build refuses what would ship broken | decided |
| The `.sty` is rendered at build time and shipped | proposed |
| Assets may live anywhere in the source tree; the build copies them in, the module reads them with `importlib.resources` | proposed |
| Placement follows an explicit `Role`, not file suffixes | decided |
| Asset paths are relative to `Distribution.root`, by default the declaring module's directory, and stay inside the declaring package | decided |
| A stored field the model no longer has is an unresolved item, never dropped; only a migration removes content | decided |
| `Kind(stem=)` names the kind's `.tex` files; the default is the root class lower-cased | decided |
| A document carries settings, options and preamble entries within what its kind lists (`settable`, `options`, `preamble`); in the tree in texmodel 0.5, beside `tree` in the envelope | decided |
| An editable install of a texpkg project links the sources and makes no module (it depends on `texpkg`); only a wheel is generated | decided |
| A kind gives a settable value its own start (`defaults`, `TP-K021`): written after the presets and the variant, before the document's settings; the template state keeps them, so `default_changes` (key: the class name) follows, freezes or asks for a changed one the document does not set | decided |
| A hand edit is a line of the `.tex` against the plan saved with it, indentation included (texmodel 0.8 indents a body by depth): a document saved by an earlier release is not hand-edited, `check` lists its files as changed and `save` rewrites them | decided |
| A package publishes JSON-like, dataclass or pydantic constants (`public=`, `acme_tex.public`, `TP-K022`, `TP-B014`): part of the `interface` snapshot, a removal breaks | decided |
| A kind locks preamble entries every document is written with (`locked_preamble`, a `PreambleSlots`: the slot is written, not inferred); a document may not carry a locked class (`TP-K020`) | decided |
| A derived package is `Package(base=)` (texmodel 0.7) and its distribution's `base` is that package's distribution (`TP-K019`); a settable value may be the base's, a profile kind's included | decided |
| Kinds made from data are generated source: `[tool.texpkg] generate`, `texpkg-build generate`, committed and refused when stale by the build | decided |
| A kind's document is a texmodel tree; a pydantic root with a render function is not supported, because `Plan`, hand edits, the defaults marks and the schemas need nodes | decided |
| A document does not carry its package's version as a field; the stack in `template.json` and the provenance command do | decided |
| The version is a constant the build writes into the module, never read from metadata at run time | decided |

## 10. Open questions

1. **Where the migration split falls** (V8): the line between one model's history and the package's is a first guess.
2. **The remaining names.** `Distribution`'s fields; the provenance names (`\<prefix>ProvenanceInfo`, `…Stamp`, `…Time`,
   `<name>-provenance.sty`, `/<Prefix>Provenance`).
3. **Starting a texpkg package.** A template project, or only the docs and the test examples.
4. **Design points to revisit:** `state["$unresolved"]` as the way a later migration sees earlier leftovers; the `output`
   fingerprint rendering the `.sty` at a fixed version; the `next` snapshot one release behind after a freeze.
