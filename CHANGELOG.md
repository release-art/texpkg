# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- The package layout: `texpkg` (the run time) and `texpkg_build` (the build), with import contracts, the `build` extra
  and the `texpkg-build` entry point (phase 0).
- `Asset`, `Role`, the `Flat` and `Project` layouts and a payload that is written whole or not at all, compared by
  content and checked for stale, missing and extra files (phase 1).
