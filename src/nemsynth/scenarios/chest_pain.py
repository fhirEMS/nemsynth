"""Scenario: adult chest pain, 911 scene response.

A scenario is a state machine over the call — dispatch, response, arrival,
assessment, intervention, transport, outcome — sampling each stage from the
national distributions where they exist, and from clinical logic where they do
not. That coupling is the point: random values inside a valid schema produce
documents that pass the XSD and describe nothing real, which finds crashes but
never finds mapping errors.

Internal consistency is a hard requirement here. A patient who refuses
transport must not carry a destination; a chest-pain complaint must produce
cardiac-flavoured impressions and interventions; vitals must be plausible for
the sampled age. Every one of those couplings is a chance for a consumer to be
wrong in an interesting way.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .. import distributions as dist

#: NEMSIS code sets used here (v3.5.0 national values).
_SEX = {"Female": "9919001", "Male": "9919003"}
_DISPOSITION_TRANSPORTED = "4230001"      # Patient Treated, Transported by EMS
_DISPOSITION_REFUSED = "4230009"          # Patient Refused Evaluation/Care
_SERVICE_911_SCENE = "2205001"            # 911 Response (Scene)
_LEVEL_ALS = "2207017"                    # ALS-Paramedic
_LEVEL_BLS = "2207011"                    # BLS-Basic/EMT


def _iso(moment: datetime) -> str:
    """NEMSIS DateTimeType: the pattern MANDATES a ±hh:mm offset (no `Z`)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S-06:00")


def build(rng: random.Random, incident_start: datetime) -> dict:
    """Sample one internally-consistent chest-pain call.

    Returns a plain dict the serializer turns into XML — keeping sampling and
    XML construction apart so a scenario can be reasoned about (and tested)
    without any XML in view.
    """
    age = max(30, dist.age_years(rng))  # chest pain is not a paediatric call
    sex = dist.pick(rng, "sex")

    # Timeline: each stage offset from the last, so the sequence is always
    # ordered no matter what the samples are. Out-of-order timestamps are a
    # real-world defect worth generating LATER, deliberately — not by accident.
    dispatched = incident_start
    en_route = dispatched + timedelta(seconds=rng.randint(30, 180))
    on_scene = en_route + timedelta(seconds=rng.randint(180, 900))
    at_patient = on_scene + timedelta(seconds=rng.randint(30, 300))
    depart = at_patient + timedelta(seconds=rng.randint(300, 1500))
    at_destination = depart + timedelta(seconds=rng.randint(300, 2400))
    transfer = at_destination + timedelta(seconds=rng.randint(120, 900))
    back_in_service = transfer + timedelta(seconds=rng.randint(120, 1200))

    # Cardiac chest pain skews toward transport; refusal remains realistic and
    # is where the interesting NV/PN paths live.
    refused = rng.random() < 0.08
    als = rng.random() < 0.85  # chest pain draws ALS far more often than average

    systolic = rng.randint(96, 178)
    # Diastolic tracks systolic rather than floating free — an 80/140 reading
    # would be nonsense that no consumer should have to accommodate.
    diastolic = max(48, min(systolic - rng.randint(30, 60), 110))
    heart_rate = rng.randint(52, 124)
    resp_rate = rng.randint(12, 28)
    spo2 = rng.randint(90, 100)
    pain = rng.randint(3, 10)

    return {
        "age": age,
        "sex_code": _SEX[sex],
        "refused": refused,
        "level_of_care": _LEVEL_ALS if als else _LEVEL_BLS,
        "service_type": _SERVICE_911_SCENE,
        "disposition": _DISPOSITION_REFUSED if refused else _DISPOSITION_TRANSPORTED,
        "times": {
            "psap": _iso(dispatched - timedelta(seconds=rng.randint(20, 90))),
            "dispatch_notified": _iso(dispatched),
            "en_route": _iso(en_route),
            "on_scene": _iso(on_scene),
            "at_patient": _iso(at_patient),
            # A refusal has no transport leg at all — omitting these is the
            # consistency rule, not a gap.
            "depart_scene": None if refused else _iso(depart),
            "at_destination": None if refused else _iso(at_destination),
            "transfer_of_care": None if refused else _iso(transfer),
            "back_in_service": _iso(back_in_service if not refused
                                    else depart + timedelta(seconds=600)),
        },
        "vitals": {
            "taken": _iso(at_patient + timedelta(seconds=rng.randint(30, 240))),
            "systolic": systolic,
            "diastolic": diastolic,
            "heart_rate": heart_rate,
            "resp_rate": resp_rate,
            "spo2": spo2,
            "pain": pain,
        },
        # ICD-10-CM, as NEMSIS 3.5.0 requires for eSituation.11/.12.
        "primary_impression": rng.choice(["R07.9", "I20.9", "R07.89"]),
        "chief_complaint": "Chest pain",
    }
