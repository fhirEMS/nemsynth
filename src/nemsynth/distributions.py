"""Weighted sampling over the national distributions, seeded and reproducible.

Every draw goes through a `random.Random` the caller owns, so `--seed 42`
produces byte-identical output forever. That is not a nicety: a defect found by
generated document #8,412 is worthless if it cannot be replayed.

Keys suffixed `_approx` in the data file are working assumptions rather than
measured national figures; `is_measured()` reports which, so a caller (or a
reader of the output) can always tell the difference.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def national() -> dict[str, Any]:
    """The bundled national distributions, with their provenance."""
    ref = resources.files("nemsynth").joinpath("data/national_distributions.json")
    return json.loads(ref.read_text())


def source() -> dict[str, Any]:
    """Where the numbers came from — carried into generated file headers."""
    return national()["_source"]


def is_measured(name: str) -> bool:
    """Is this distribution transcribed from published national data, or our
    working assumption? Callers should surface the difference rather than let a
    plausible-looking number pass as evidence."""
    return bool(national()[name].get("_measured", False))


def _weights(name: str) -> dict[str, float]:
    return {
        k: v
        for k, v in national()[name].items()
        if not k.startswith("_") and isinstance(v, (int, float))
    }


def pick(rng: random.Random, name: str) -> str:
    """One weighted draw from a named distribution."""
    weights = _weights(name)
    if not weights:
        raise KeyError(f"{name} has no weighted values")
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def age_years(rng: random.Random) -> int:
    """An age drawn from the banded distribution.

    EMS skews markedly geriatric — the largest single published band is 71-80 —
    so a generator sampling ages uniformly would exercise the wrong pathways
    entirely (no polypharmacy, no falls, no dementia-adjacent refusals)."""
    bands = national()["age_years_approx"]["bands"]
    band = rng.choices(bands, weights=[b["weight"] for b in bands], k=1)[0]
    return rng.randint(band["min"], band["max"])
