"""The grounding: distributions must be real, provenanced, and reproducible."""

import random

import pytest

from nemsynth import distributions as dist


def test_source_is_recorded():
    """Every number must be traceable — a generator whose distributions have no
    provenance is just invented data wearing a lab coat."""
    source = dist.source()
    assert "nemsis.org" in source["url"]
    assert "42,302,358" in source["basis"]


@pytest.mark.parametrize("name", ["service_type", "level_of_care", "disposition",
                                  "sex", "transport_method"])
def test_measured_distributions_are_flagged_and_sum_to_one(name):
    assert dist.is_measured(name), f"{name} should be transcribed national data"
    total = sum(v for k, v in dist.national()[name].items()
                if not k.startswith("_") and isinstance(v, (int, float)))
    assert 0.97 <= total <= 1.03, f"{name} sums to {total}"


@pytest.mark.parametrize("name", ["dispatch_reason_approx", "age_years_approx"])
def test_assumed_distributions_are_labelled_as_such(name):
    """A working assumption must never pass as measured data."""
    assert not dist.is_measured(name)
    assert dist.national()[name]["_reasoning"]


def test_sampling_is_reproducible():
    """Same seed, same draws — or a defect found at document #8,412 cannot be
    replayed tomorrow."""
    a = [dist.pick(random.Random(7), "disposition") for _ in range(5)]
    b = [dist.pick(random.Random(7), "disposition") for _ in range(5)]
    assert a == b


def test_age_reflects_the_geriatric_skew():
    """EMS is disproportionately old; uniform ages would exercise the wrong
    clinical pathways entirely."""
    rng = random.Random(3)
    ages = [dist.age_years(rng) for _ in range(3000)]
    assert sum(a >= 65 for a in ages) / len(ages) > 0.35
