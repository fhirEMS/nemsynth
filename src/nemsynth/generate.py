"""Generation entry point: seed in, XSD-valid NEMSIS documents out."""

from __future__ import annotations

import hashlib
import random
import uuid
from datetime import datetime, timedelta

from . import validate
from .scenarios import chest_pain
from .serialize import build_document

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
                 version: str = "3.5.0") -> bytes:
    """One XSD-valid EMSDataSet. Same seed, byte-identical output, forever."""
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown scenario {scenario!r}; have {sorted(SCENARIOS)}")
    rng = random.Random(seed)

    # A fixed epoch, advanced by the seed: reproducible without freezing every
    # document to the same instant (which would hide date-boundary defects).
    incident = datetime(2026, 1, 1) + timedelta(
        minutes=rng.randint(0, 365 * 24 * 60)
    )
    call = SCENARIOS[scenario](rng, incident)
    meta = {
        "uuid": _deterministic_uuid(rng),
        "pcr_number": f"NS-{seed:08d}",
        "agency_number": "9901",
        "agency_state_id": "SY-9901",
        "state": "49",
        "generator_version": __import__("nemsynth").__version__,
        "family_name": rng.choice(_FAMILY),
        "given_name": rng.choice(_GIVEN),
        "dispatch_reason": "2301067",  # Chest Pain (Non-Traumatic)
    }
    document = build_document(call, meta, version=version)
    return validate.ensure_valid(document, version)


def fingerprint(document: bytes) -> str:
    """Stable digest, for asserting reproducibility in tests."""
    return hashlib.sha256(document).hexdigest()[:16]
