# What texpkg needs from texmodel

Nothing is open. texpkg builds on texmodel 0.4.0, which provides `GENERATOR_VERSION` (a copy embedded in a wheel sets it
instead of reading installed metadata), reads a `TemplateRef` through `importlib.resources` (a wheel runs from a zip) and
has `texmodel_build.fonts` (the embedded-font check behind `check_isolated`).

An open request goes here with what it is, why (the requirement id), where texpkg works around it and the test that shows
the workaround.
