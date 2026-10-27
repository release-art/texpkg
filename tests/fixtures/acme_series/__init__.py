"""A package whose kinds are series: their classes are generated from `series.json` by `acme_series_gen` (K4)."""

from texpkg import Asset, Distribution, Kind, Role

from ._kinds import ALL
from .model import pkg

dist = Distribution(
    name="acme-series-tex",
    module="acme_series_tex",
    package=pkg,
    assets=(Asset("assets/lmroman10-regular.otf", Role.FONT, "the typeface"),),
    kinds=tuple(
        Kind(series.NAME, series.ROOT, (), series.example, settable=series.SETTABLE, options=series.OPTIONS)
        for series in ALL
    ),
)

__all__ = ["dist"]
