"""Generation entry point: seed in, XSD-valid NEMSIS documents out."""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

from . import messiness, schema, skeleton, validate
from .scenarios import chest_pain

_SCHEMA_LOCATION = {
    "3.5.0": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
    "3.5.1": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.1/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
}

SCENARIOS = {"chest-pain": chest_pain.build}

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


def fingerprint(document: bytes) -> str:
    """Stable digest, for asserting reproducibility in tests."""
    return hashlib.sha256(document).hexdigest()[:16]
