# Brief: implement texpkg, unattended

Paste everything below the line as the first message of an agent session started in `/Users/ilo/Devel/Release.art/texpkg`.

---

You are implementing **texpkg** from its spec, unattended, phase by phase. Work without asking; stop and ask only for the
cases listed under **Stop and ask**. Everything else you decide yourself, following the documents below, and record.

## Read first, in this order

1. `AGENTS.md`: the rules of this repository. They hold except where this brief explicitly grants more (git, proposed
   items).
2. `docs/texpkg-plan.md`: the spec. Requirement ids (`P26`, `D8`) are what tests, commits and the log cite. §4a is the
   API reference; §9 the decisions log; §10 the open questions.
3. `docs/implementation-plan.md`: how and in which order to build it. §1's six decisions are taken. §2 is the module
   layout. §3 the phases, each with what it builds, reuses, tests, and when it is done. §5 lists spec items still marked
   proposed, by phase.
4. The sibling texmodel checkout (`../texmodel`, installed editable): its `AGENTS.md`, `docs/guide/`, and the modules the
   plan reuses: `bundle`, `drift`, `preamble`, `plan`, `spec`, `package`, `components`, `types`. Read the code, not only
   the docs, before relying on a behaviour.

## Scope

Phases **0, 1, 2, 2a, 2b, 3, 3a, 4, 5a, 5b, 6, 6a, 7** of the implementation plan, in its §4 order. Out of scope: phase
5c (moving code into texmodel) and phase 8 (porting the first consumer): both happen in other repositories.

## What you may do without asking

- **Git, on one branch:** create `impl/texpkg-v1` from the current branch, and commit each finished phase (or sub-phase)
  there, one commit per phase, message `Phase N: <title>` plus the requirement ids it built. Never push, tag, merge,
  rebase, or touch another branch.
- **Build on items the spec marks proposed**, in the form the spec or the implementation plan writes them, when a phase
  needs them. List every one you adopted in that phase's log entry (below), so the maintainer can confirm or change it.
- **Choose what the documents leave to implementation:** private names, internal structure, test layout, the exact
  `TP-` codes (scheme in plan §1.3), small helpers. Prefer the smallest thing that meets the requirement; no options,
  abstractions or dependencies the spec does not call for.
- **Fix the spec's wording** where it is plainly stale against what is decided (a renamed function, a moved id), and
  say so in the log. Do not change what a decided item means.
- **Add development dependencies** with `pdm add -dG dev`, when a test needs one that is standard (hypothesis plugins,
  `jsonschema` for schema tests). Log each.

## Rules that do not bend

- **Gates, every phase** (AGENTS.md): `pdm run ruff format --check src tests`, `pdm run ruff check src tests`,
  `pdm run pyright` (0 errors), `pdm run lint-imports` (from phase 0), `pdm run pytest` (100% coverage). Judge each by
  its exit code. Never weaken one: no `# pragma: no cover`, no blanket `noqa` or `type: ignore`, no loosened config.
- **TeX is proved by compiling.** Phases that write TeX (2, 2a, 4, 6, 6a, 7) also pass the compile tests. A local TeX
  Live (`lualatex`, `latexmk`) is installed, and texmodel's reference image `texmodel-test:latest` exists in Docker; use
  texmodel_build to compile, as texmodel's own tests do. If the compile tests cannot run, that phase is not done.
- **The library spawns no process and reads no clock** (N4, with its one stated exception). Tests may spawn (pip into a
  clean venv, phase 3) through one test helper.
- **Do not edit texmodel, texmodel_build or any other repository.** Other work is in progress there, uncommitted. What
  texpkg needs from texmodel and texmodel lacks is built in one self-contained texpkg module (N5, V9), and recorded in
  `docs/texmodel-requests.md`: what, why (requirement id), where it lives in texpkg now, and the test that shows it.
  Never work around a texmodel defect: see **Stop and ask**.
- **Nothing real or private enters the repo:** synthetic `acme` packages only (`tests/fixtures/`, `tests/consumers/`).
- **Scratch files** go in your scratchpad, never in the repo.

## After each phase

1. Gates green, compile tests green where the phase writes TeX.
2. The spec's §8 row marked built, `CHANGELOG.md` under `## [Unreleased]`, and any doc the change touches (README, AGENTS)
   updated.
3. An entry appended to `docs/implementation-log.md`:
   - the phase, and the requirement ids built;
   - the gates and compile tests run, with their result;
   - **proposed items adopted** (id, the form used);
   - **decisions you made** that a reader would not guess from the plan (one line each, with why);
   - texmodel requests added;
   - anything deferred, and to which phase.
4. Commit the phase on `impl/texpkg-v1`.

Then go straight on to the next phase.

## Stop and ask

Stop, write what you found and what you propose in `docs/implementation-log.md`, and ask the maintainer, only when:

- a **decided** item turns out to be impossible, contradictory, or clearly wrong once built against the real code (not a
  wording slip: a design that cannot hold);
- **texmodel behaves differently** from what a decided item relies on, or has a defect that blocks a phase, and building
  it aside in texpkg would mean working around texmodel instead of filling a gap;
- a phase needs a **new run-time dependency** (anything besides pydantic in a built wheel), or changes what a wheel
  embeds;
- a gate or the compile tests **cannot pass without weakening them**, or TeX fails for a reason you cannot explain after
  reading the log;
- the work would need to **change another repository**, push, or touch a branch other than `impl/texpkg-v1`;
- the spec's §10 open questions (2, 6, 7) block a phase in a way the implementation plan does not cover.

Not reasons to stop: a proposed item you can build as written (log it), a name the plan leaves to you, a test that is
hard to write, a long test run, an internal refactor within texpkg.

## When you finish

Write a closing entry in `docs/implementation-log.md`: phases done, the commits, every proposed item adopted, every
texmodel request, what is left (phases 5c and 8, open questions), and how to check the result
(`pdm run pytest`, the compile tests, phase 7's clean-venv test).
