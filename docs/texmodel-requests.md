# What texpkg needs from texmodel

texpkg does not edit texmodel (implementation brief). What it needs and texmodel lacks is built in one self-contained
texpkg module and listed here: what, why (requirement id), where it lives in texpkg now, and the test that shows it.

## `TemplateRef` reads through the file system

- **What:** `texmodel.body.TemplateRef` (a template file beside the declaring module) is read with `pathlib` from
  `module.__file__`. A declaration that is imported from a zip (a wheel on `sys.path`, as `zipimport` or a zipapp loads it)
  fails at import with `NotADirectoryError`. Reading through `importlib.resources` would work in both.
- **Why:** P5 (a wheel, a zip and an editable install behave alike); the declaration ships inside the wheel (P22) and its
  templates with it.
- **Where in texpkg:** nowhere; texpkg does not work around it. Installed wheels are unpacked, so only zip imports are
  affected, and the assets of a payload are read with `importlib.resources` and do work from a zip
  (`tests/test_payload.py`).
- **Test:** `tests/test_build.py::test_a_wheel_runs_from_its_zip` is an `xfail(strict=True)`: it starts failing the build
  when texmodel reads templates through `importlib.resources`, which is the signal to drop the mark.
