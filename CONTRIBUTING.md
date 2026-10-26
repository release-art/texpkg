# Contributing

Issues and pull requests are welcome.

```zsh
pdm install
git config core.hooksPath .githooks
bin/autoformat.sh   # ruff format, ruff check --fix, pyright
bin/test.sh         # pytest, 100% coverage gate
```

- Python 3.15; ruff for format and lint, pyright strict on `src`.
- New behaviour comes with a test; add a line under `## [Unreleased]` in `CHANGELOG.md` for anything user-visible.
