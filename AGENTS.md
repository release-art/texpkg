# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

`texpkg`: TeX packages published as Python packages, in Python 3.15. A texpkg package is a wheel that carries a texmodel
API and the TeX it compiles against at one version. Installed, it is a Python module with one fixed, strictly defined API
for emitting LaTeX from versioned (migratable) data; packages can depend on each other: a wheel requires the texpkg it was
built with (same `X.Y`) and its base's wheel. texpkg builds that module from
the author's declaration at wheel build time (`texpkg-build`, a pdm build hook) and defines the API behind it: load a
document directory, render it, save it with the files it needs, check it later.
[docs/texpkg-plan.md](docs/texpkg-plan.md) is the spec, the API reference (§4a), what is not built yet (§8), the decisions log (§9)
and the open questions (§10); [docs/known-limitations.md](docs/known-limitations.md) is what texpkg does not do. texmodel owns
components, document models and escaping.

**Pre-1.0:** no backward compatibility for the Python API or the saved output: rename or remove directly. List every
such change under `Changed` or `Removed` in `CHANGELOG.md`.

**Early stage:** the design is still being shaped with the maintainer. A decision marked *proposed* or *open* in the plan is
not settled: ask before building on it.

## Principles

- Follow the Zen of Python. Explicit, simple and flat code; named methods and enums, nothing found by name or inferred
  silently.
- DRY: reuse what exists (here and in texmodel) before adding anything. Delete what a change makes dead.
- Small, focused changes. No speculative abstractions, options or dependencies.
- Keep docs, docstrings and comments brief. Comments say *why*, not *what*. Docs describe the current state; the changelog
  tells change.
- A pure library: no process spawning, no clock reads, no printing (`logging` and `warnings` only). Times and stamps are
  arguments.
- **Nothing real or private enters this repo.** No customer, brand or person's name, no real package, no real data: examples
  and tests use a synthetic `acme` package. A defect found in a real consumer becomes a synthetic test that shows it.
- When a change alters behaviour, update in the same change: the plan (the section it touches, the decisions log),
  `docs/known-limitations.md`, the README if the front page changes, and `CHANGELOG.md` under `## [Unreleased]`.

## Quality gates (mandatory)

```bash
pdm run ruff format --check src tests
pdm run ruff check src tests
pdm run pyright                 # strict on src, 0 errors
pdm run lint-imports            # the package contracts (below)
pdm run pytest                  # coverage over both packages must stay at 100%
TEXPKG_REQUIRE_TEX=1 pdm run pytest -m tex --no-cov   # when TeX written by the library or the build changed
```

- `bin/autoformat.sh` formats, fixes and runs pyright and import-linter; `bin/test.sh` runs pytest; `.githooks/pre-commit`
  runs ruff, pyright and import-linter (`git config core.hooksPath .githooks`).
- Judge each gate by its exit code. Run the files you touched first, the whole suite last.
- Output that TeX must accept is proved by compiling, not by comparing text.
- Do not weaken the gates: no `# pragma: no cover`, no blanket `# noqa` or `# type: ignore`, no loosened config. A narrow
  `# noqa: CODE` or `# pyright: ignore[rule]` carries its reason.
- Every new code path needs a test; new behaviour needs one that fails without it. Say which gates you ran.

## Package layout (pydantic pattern)

- One distribution, two import packages. `src/texpkg` is the run time: it is what every built wheel depends on (B7), so it
  imports only the standard library, texmodel and pydantic. `src/texpkg_build` is the author's build (hook, generation,
  snapshots, assembling the module) and is never a wheel's dependency; its dependencies sit in the `build` extra.
- Public modules sit at the top level of each package; `_internal/` is what we deliberately hide. A new module goes in
  `_internal` unless users should import it; then add it to `PUBLIC` in `tests/test_public_api.py` and document it.
- `texpkg` never imports `texpkg_build`; nothing starts a process (tests do, through `tests/spawn.py`); only
  `texpkg_build/cli.py` prints. `lint-imports` enforces these.
- What texpkg needs from texmodel and texmodel lacks is written in one self-contained texpkg module and listed in
  `docs/known-limitations.md` with the test that shows it (N5, V9). Do not edit texmodel from here.

## Conventions

- Errors carry a new, stable code `TP-<area><nnn>`: `A` assets, `D` document, `K` kinds, `M` migration, `B` build,
  `C` contracts, `E` the declaration copied into a wheel. `grep -rhoE "TP-[A-Z][0-9]+" src | sort -u` for the next free one; a code is never reused.
- Mark every `Enum`/`StrEnum` `@enum.unique`.
- Values are frozen dataclasses; output is a pure function of its inputs: no clocks, hashes, set or dict order in what is
  written. Pydantic only at the data boundary.
- Errors say what is wrong, where, and the fix.
- Tests: pytest, `hypothesis` where there is a law, `monkeypatch`, temp projects under `tmp_path`.
- Dependencies: `pdm add` (runtime) or `pdm add -dG dev` so `pdm.lock` stays in sync.

## Working with the maintainer

- Work from the plan's §8; for a design choice it leaves open, propose rather than pick silently.
- Git is the maintainer's: read-only commands only (`status`, `diff`, `log`, `show`) unless explicitly asked. Releasing is theirs; the version is the git tag.
- Uncommitted changes aren't yours: read `git status` and `git diff` first, build on them, never revert them.
- Scratch files go in your scratchpad, never in the repo.

## Development environment

- `pdm install`; run tools as `pdm run ...`. Python is 3.15 only. The compile tests are `async` (`pytest-asyncio`, auto mode).
- texmodel is the released one (`texmodel>=0.11.0`). To try a change in the sibling checkout, `pdm add -e ../texmodel --dev` locally
  and do not commit that.
