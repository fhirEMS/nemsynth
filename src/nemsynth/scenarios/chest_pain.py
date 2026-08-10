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

    Returns a flat {element_id: value} map. The skeleton builder decides what
    must be present and in what order; a scenario decides only what it has to
    SAY. Anything it omits that the schema requires becomes nil+NV — which is
    both correct and the shape real exports take constantly.
    """
    age = max(30, dist.age_years(rng))  # chest pain is not a paediatric call
    sex = dist.pick(rng, "sex")
    call_service_type = _SERVICE_911_SCENE

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

    values = {
        # Response / dispatch
        "eResponse.05": call_service_type,
        "eResponse.15": _LEVEL_ALS if als else _LEVEL_BLS,
        "eDispatch.01": "2301067",              # Chest Pain (Non-Traumatic)

        # Timeline. A refusal has no transport leg, so those elements are left
        # unsupplied and the builder emits nil+NV — the real-world shape.
        "eTimes.01": _iso(dispatched - timedelta(seconds=rng.randint(20, 90))),
        "eTimes.03": _iso(dispatched),
        "eTimes.05": _iso(en_route),
        "eTimes.06": _iso(on_scene),
        "eTimes.07": _iso(at_patient),
        "eTimes.13": _iso(back_in_service),

        # Patient
        "ePatient.15": age,
        "ePatient.16": "2516009",               # Age units: Years
        "ePatient.25": _SEX[sex],

        # Situation
        "eSituation.03": "2803001",             # Complaint type: Chief
        "eSituation.04": "Chest pain",
        "eSituation.11": rng.choice(["R07.9", "I20.9", "R07.89"]),

        # Vitals — one set, internally consistent
        "eVitals.01": _iso(at_patient + timedelta(seconds=rng.randint(30, 240))),
        "eVitals.02": "9923001",                # Obtained prior to care: No
        "eVitals.06": systolic,
        "eVitals.07": diastolic,
        "eVitals.10": heart_rate,
        "eVitals.12": spo2,
        "eVitals.14": resp_rate,
        "eVitals.27": pain,

        # Scene
        "eScene.01": "9923003",                 # First unit on scene: Yes
        "eScene.07": "9923001",                 # MCI: No

        # Outcome of the call
        "eDisposition.30": _DISPOSITION_REFUSED if refused else _DISPOSITION_TRANSPORTED,
    }
    if not refused:
        values.update({
            "eTimes.09": _iso(depart),
            "eTimes.11": _iso(at_destination),
            "eTimes.12": _iso(transfer),
        })
    return values
