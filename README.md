# texpkg

TeX packages published as Python packages. A texpkg package is one wheel: a typed [texmodel](https://github.com/release-art/texmodel)
API and the TeX it compiles against, at one version. Installed, it is a Python module with a fixed API to load, render,
save and check document directories, with versioned data and migrations; packages can build on each other, the base
embedded in the dependent at build time.

An author declares a package (`Distribution`, `Kind`, `Asset`) and builds it with `texpkg-build`, a pdm build hook. The
spec, the API reference and the decisions are in [docs/texpkg-plan.md](docs/texpkg-plan.md); what texpkg does not do is in
[docs/known-limitations.md](docs/known-limitations.md).

```zsh
pdm install
git config core.hooksPath .githooks   # pre-commit runs ruff, pyright and import-linter
bin/autoformat.sh
bin/test.sh                           # pytest, 100% coverage gate
```
