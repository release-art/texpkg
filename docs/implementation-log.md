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
