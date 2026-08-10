"""The messiness engine.

Two properties matter and they pull against each other: the output must stay
XSD-VALID (invalid input teaches a consumer nothing — the ingest gate just
rejects it), and it must actually be messy (a profile that quietly changes
nothing is worse than no profile, because the corpus looks exercised and is
not). Every test here pins one side or the other.
"""

from __future__ import annotations

import random

import pytest

from nemsynth import messiness, schema, validate
from nemsynth.generate import generate_one
from nemsynth.skeleton import Absent, Negative


@pytest.fixture(scope="module")
def model():
    return schema.load("3.5.0")


def test_clean_profile_changes_nothing():
    """The control. Without it, a corpus difference cannot be attributed to the
    profile rather than the scenario."""
    values = {"ePatient.15": 44, "eSituation.04": "Chest pain"}
    assert messiness.apply(values, random.Random(1), messiness.CLEAN, None) == values


def test_high_profile_actually_changes_something(model):
    """A profile that is a no-op is the failure this test exists to catch: the
    engine wired in but never firing looks identical to a clean run."""
    values = {
        "ePatient.15": 44,
        "eVitals.07": 78,
        "eVitals.10": 84,
        "eVitals.27": 4,
        "eSituation.04": "Chest pain",
        "eSituation.11": "R07.9",
        "eScene.07": "9923001",
        "eResponse.15": "2215001",
        "eRecord.01": "PCR-2026-00001",
    }
    changed = [
        key for key, value in messiness.apply(
            values, random.Random(7), messiness.HIGH, model
        ).items()
        if values.get(key) != value
    ]
    assert changed, "HIGH profile was a no-op"


def test_age_boundaries_come_from_the_schema(model):
    """ePatient.15 is minInclusive=1. A hand-picked 'boundary' of 0 is XSD-
    illegal and was caught by the self-validation gate — hence reading the
    facet instead of guessing it."""
    bounds = messiness._age_bounds(model)
    assert bounds, "no bounds read from the schema"
    assert min(bounds) >= 1


def test_absent_and_negative_are_distinct_facts():
    """"Not recorded" and "no known drug allergy" are different assertions.
    A consumer that flattens both to "missing" is losing the distinction the
    standard exists to carry, so the generator must be able to emit both."""
    assert Absent("7701003").code != Negative("8801013").code


def test_nv_codes_vary(model):
    """Real exports use all three NV reasons. A generator emitting only one
    would let a consumer that hardcodes it pass forever."""
    rng = random.Random(3)
    assert len({messiness._nv_code(rng) for _ in range(200)}) >= 2


def test_hour_24_is_xsd_legal_and_fhir_invalid():
    """24:00:00 is valid per the NEMSIS pattern and rejected by FHIR, where
    hours cap at 23 — a real interop trap, and the reason this knob exists."""
    assert messiness._to_hour_24("2026-08-06T14:02:10-06:00") == \
        "2026-08-06T24:00:00-06:00"
    # Offset is mandatory in NEMSIS; dropping it would fail the XSD pattern.
    assert messiness._to_hour_24("2026-08-06T14:02:10-06:00").endswith("-06:00")


@pytest.mark.parametrize("profile", ["low", "medium", "high"])
def test_every_profile_still_produces_valid_nemsis(profile):
    """The hard constraint. Messiness that breaks the XSD is worthless: the
    consumer's ingest gate rejects it and no mapping code is ever reached."""
    for seed in range(12):
        document = generate_one(seed=seed, profile=profile)
        assert validate.errors(document) == []


def test_messiness_is_reproducible():
    """A defect found by messy document #8,412 must be replayable."""
    assert generate_one(seed=99, profile="high") == generate_one(seed=99, profile="high")


def test_profiles_differ_from_clean_at_corpus_scale():
    """Per-document the rates are probabilistic; across a corpus the profiles
    must be visibly different, which is what a consumer actually consumes."""
    clean = {generate_one(seed=s, profile="clean") for s in range(15)}
    high = {generate_one(seed=s, profile="high") for s in range(15)}
    assert not (clean & high), "HIGH produced documents identical to CLEAN"
