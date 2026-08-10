"""Generation entry point: seed in, XSD-valid NEMSIS documents out."""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

from . import messiness, schema, skeleton, validate
from .scenarios import base
from .scenarios.library import LIBRARY

_SCHEMA_LOCATION = {
    "3.5.0": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
    "3.5.1": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.1/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
}

SCENARIOS = {
    key: (lambda rng, start, p=presentation: base.build(p, rng, start))
    for key, presentation in LIBRARY.items()
}

# Synthetic name pools. Deliberately small and obviously invented — this is a
# structural generator, not a demographic simulator, and nothing here is or
# resembles a real person.
_FAMILY = ["Alderton", "Boysen", "Caraway", "Dhillon", "Eastwood", "Fenwick",
           "Girard", "Hollis", "Imani", "Jessup", "Kovach", "Lindqvist"]
_GIVEN = ["Adair", "Bryn", "Caelan", "Dara", "Emory", "Frankie", "Greer",
          "Harlow", "Indigo", "Jules", "Kaya", "Lennox"]


def _deterministic_uuid(rng: random.Random) -> str:
    """A UUID from the seeded RNG, so a seed reproduces ids exactly."""
    return str(uuid.UUID(bytes=bytes(rng.getrandbits(8) for _ in range(16)), version=4))


def scenario_for(seed: int, choice: str) -> str:
    """Resolve 'mixed' to one presentation, deterministically per seed.

    Rotating rather than sampling: a mixed corpus of N then contains every
    presentation in a known proportion, so a defect found in document #8,412 is
    attributable to a specific scenario without re-deriving the draw."""
    if choice != "mixed":
        return choice
    keys = sorted(SCENARIOS)
    return keys[seed % len(keys)]


def generate_one(seed: int, scenario: str = "chest-pain",
                 version: str = "3.5.0",
                 profile: str = "medium") -> bytes:
    """One XSD-valid EMSDataSet. Same seed, byte-identical output, forever."""
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown scenario {scenario!r}; have {sorted(SCENARIOS)}")
    rng = random.Random(seed)

    # A fixed epoch, advanced by the seed: reproducible without freezing every
    # document to the same instant (which would hide date-boundary defects).
    incident = datetime(2026, 1, 1) + timedelta(
        minutes=rng.randint(0, 365 * 24 * 60)
    )
    values = SCENARIOS[scenario](rng, incident)
    agency = {"state_id": "SY-9901", "number": "9901", "state": "49"}
    values.update({
        "eRecord.01": f"NS-{seed:08d}",
        "ePatient.02": rng.choice(_FAMILY),
        "ePatient.03": rng.choice(_GIVEN),
        # Identity must agree with the header. The skeleton's last-resort
        # literal would satisfy the XSD while contradicting dAgency.02 — valid
        # and wrong, which is the exact trap a generator must not set. (Found
        # on the first real run, by a consumer's issue ledger.)
        "eResponse.01": agency["number"],
        "eResponse.03": agency["number"],
    })
    # Messiness is applied AFTER the scenario and before serialization, so a
    # scenario stays clean and inspectable on its own and any finding can be
    # isolated to one layer or the other.
    values = messiness.apply(
        values, rng, messiness.PROFILES[profile], schema.load(version))

    document = skeleton.build_document(
        schema.load(version),
        values,
        agency=agency,
        uuid=_deterministic_uuid(rng),
        rng=rng,
        schema_location=_SCHEMA_LOCATION[version],
    )
    return validate.ensure_valid(document, version)


#: START triage classification, with the label the XSD gives each code.
#: Proportions are ASSUMED, not measured — published MCI triage mixes vary
#: enormously by incident type, and inventing a national figure would be
#: exactly the false precision `nemsynth sources` exists to prevent.
_TRIAGE = [
    ("2708005", 0.55),   # Green - Minimal (Minor)
    ("2708003", 0.22),   # Yellow - Delayed
    ("2708001", 0.15),   # Red - Immediate
    ("2708007", 0.05),   # Gray - Expectant
    ("2708009", 0.03),   # Black - Deceased
]

#: The presentations an MCI actually produces. A bus rollover does not generate
#: obstetric and interfacility calls, and a scenario mix that ignores that is
#: not a mass-casualty incident, just several unrelated calls in one file.
_MCI_PRESENTATIONS = ("trauma-mvc", "trauma-fall", "respiratory",
                      "allergic-reaction", "cardiac-arrest")


def generate_mci(seed: int, patients: int = 4, version: str = "3.5.0",
                 profile: str = "medium") -> bytes:
    """One EMSDataSet holding N PatientCareReports from a single incident.

    They share the incident number and the scene, and each carries its own
    triage classification — the shape that catches a consumer assuming one
    report per file, which silently discards every patient but the first.
    """
    if patients < 1:
        raise ValueError("an MCI needs at least one patient")
    rng = random.Random(seed)
    model = schema.load(version)
    agency = {"state_id": "SY-9901", "number": "9901", "state": "49"}
    incident = datetime(2026, 1, 1) + timedelta(
        minutes=rng.randint(0, 365 * 24 * 60))
    # One incident number for every patient on the scene.
    incident_number = f"MCI-{seed:06d}"

    codes, weights = zip(*_TRIAGE)
    reports = []
    for index in range(patients):
        key = _MCI_PRESENTATIONS[index % len(_MCI_PRESENTATIONS)]
        values = SCENARIOS[key](rng, incident + timedelta(seconds=30 * index))
        values.update({
            "eRecord.01": f"NS-{seed:06d}-P{index + 1:02d}",
            "ePatient.02": rng.choice(_FAMILY),
            "ePatient.03": rng.choice(_GIVEN),
            "eResponse.01": agency["number"],
            "eResponse.03": incident_number,
            "eScene.07": base.YES,                       # Mass Casualty Incident
            "eScene.08": rng.choices(codes, weights=weights, k=1)[0],
            # Only the first unit to arrive is the first unit on scene.
            "eScene.01": base.YES if index == 0 else base.NO,
        })
        values = messiness.apply(
            values, rng, messiness.PROFILES[profile], model)
        reports.append((values, _deterministic_uuid(rng)))

    return validate.ensure_valid(
        skeleton.build_dataset(model, reports, agency, rng,
                               _SCHEMA_LOCATION[version]),
        version,
    )


def fingerprint(document: bytes) -> str:
    """Stable digest, for asserting reproducibility in tests."""
    return hashlib.sha256(document).hexdigest()[:16]
