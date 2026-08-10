"""The shared shape of an EMS call, so a scenario is clinical content only.

Every call has the same plumbing: a dispatch-to-back-in-service timeline, a
patient, a set of vitals, some interventions, a disposition. Writing that out
per scenario would mean fifteen copies that drift apart, and the drift would
show up as generated documents that disagree with each other for no clinical
reason.

So the same inversion the skeleton applied to the schema is applied here to the
call: **this module owns the plumbing, a `Presentation` declares only what is
clinically distinctive** — what the patient complains of, what it is dispatched
as, what impressions fit, what gets given, what gets done, and how the vitals
should look. Adding a presentation is a paragraph of clinical logic.

Interventions are emitted as REPEATING GROUPS with per-instance timestamps.
That is deliberate: a consumer must turn N medication instances into N
resources sharing the group's .01 timestamp, and a generator that could only
emit one instance per group could never test that rule.

Code provenance, three tiers, because conflating them would be the same sin as
letting an assumed distribution pass as measured:

  - **NEMSIS codes** (routes, units, AVPU, age units) are read from the
    vendored XSD's own `xs:documentation` labels and pinned here with that
    label as the comment. `test_scenarios.py` re-reads the schema and asserts
    each code still carries the meaning claimed, so a release that reassigns a
    code fails the suite rather than silently generating nonsense.
  - **ICD-10-CM impressions** are real codes, checked against the XSD's own
    pattern for the field.
  - **RxNorm and SNOMED CT** identifiers are clinically plausible ingredient-
    and procedure-level concepts, NOT verified against a licensed release.
    They are structurally correct and good enough to exercise a mapper; they
    are not a terminology source. See `nemsynth sources`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .. import distributions as dist

# --- NEMSIS code values, pinned with the label the XSD gives them ------------
ROUTE_IV = "9927023"          # Intravenous (IV)
ROUTE_IM = "9927015"          # Intramuscular (IM)
ROUTE_IN = "9927017"          # Intranasal
ROUTE_IO = "9927021"          # Intraosseous (IO)
ROUTE_ORAL = "9927035"        # Oral
ROUTE_SL = "9927047"          # Sublingual
ROUTE_NEB = "9927071"         # Nebulizer
ROUTE_ET = "9927005"          # Endotracheal Tube (ET)

UNIT_MG = "3706021"           # Milligrams (mg)
UNIT_MCG = "3706015"          # Micrograms (mcg)
UNIT_ML = "3706025"           # Milliliters (ml)
UNIT_G = "3706001"            # Grams (gms)
UNIT_LPM = "3706035"          # Liters Per Minute (LPM [gas])
UNIT_PUFFS = "3706043"        # Puffs

AVPU_ALERT = "3326001"        # Alert
AVPU_VERBAL = "3326003"       # Verbal
AVPU_PAIN = "3326005"         # Painful
AVPU_UNRESPONSIVE = "3326007" # Unresponsive

AGE_YEARS = "2516009"         # Years
AGE_MONTHS = "2516007"        # Months

ARREST_NO = "3001001"                 # No
ARREST_BEFORE_EMS = "3001003"         # Yes, Prior to Any EMS Arrival
ARREST_AFTER_EMS = "3001005"          # Yes, After Any EMS Arrival

SEX = {"Female": "9919001", "Male": "9919003"}

# YesNoValues: 9923001 is *No* and 9923003 is *Yes*. Stated explicitly because
# getting this backwards is invisible — both values are legal everywhere the
# type is used, so every document still passes the XSD while asserting the
# opposite of what was meant. It happened here: an inverted pair silently
# declared every generated call a Mass Casualty Incident. test_scenarios.py
# now reads both labels back from the schema.
NO = "9923001"                # No
YES = "9923003"               # Yes

# eSituation.02 Possible Injury has its OWN yes/no set (9922xxx), not the
# generic one — and its codes are in a different ORDER (001 is No, 005 is Yes).
# Reusing the generic YES here produced an XSD-invalid document, which is why
# these are pinned separately with the schema's own labels.
INJURY_NO = "9922001"         # No
INJURY_UNKNOWN = "9922003"    # Unknown
INJURY_YES = "9922005"        # Yes

SERVICE_911_SCENE = "2205001"         # 911 Response (Scene)
SERVICE_INTERFACILITY = "2205009"     # Interfacility Transport
LEVEL_ALS = "2207017"                 # ALS-Paramedic
LEVEL_BLS = "2207011"                 # BLS-Basic/EMT

DISPOSITION_TRANSPORTED = "4230001"   # Patient Treated, Transported by EMS
DISPOSITION_REFUSED = "4230009"       # Patient Refused Evaluation/Care
DISPOSITION_NO_TREAT_TRANSPORTED = "4230005"
DISPOSITION_DEAD_ON_SCENE = "4230013"

COMPLAINT_CHIEF = "2803001"           # Complaint type: Chief


@dataclass(frozen=True)
class Med:
    """One medication administration. `rxnorm` is an ingredient-level RxCUI."""
    rxnorm: str
    dose: str
    units: str
    route: str
    name: str = ""      # for the human reading the corpus, not emitted


@dataclass(frozen=True)
class Proc:
    """One procedure. `snomed` is a procedure-level SNOMED CT concept."""
    snomed: str
    name: str = ""
    attempts: int = 1
    successful: bool = True


@dataclass(frozen=True)
class Vitals:
    """Plausible ranges for ONE reading. The base walks these toward normal
    across serial sets when the patient is treated, because a transport that
    records three identical vital signs is not what a real chart looks like."""
    systolic: tuple[int, int] = (104, 168)
    heart_rate: tuple[int, int] = (58, 112)
    resp_rate: tuple[int, int] = (12, 22)
    spo2: tuple[int, int] = (94, 100)
    pain: tuple[int, int] = (0, 6)
    avpu: str = AVPU_ALERT
    glucose: tuple[int, int] | None = None


@dataclass(frozen=True)
class Presentation:
    """What makes one clinical presentation different from another."""

    key: str
    complaint: str
    dispatch_code: str
    impressions: tuple[str, ...]
    symptom: str | None = None                 # eSituation.09, ICD-10-CM
    age_range: tuple[int, int] = (18, 95)
    #: Infants are charted in months, not fractional years. A consumer that
    #: assumes years silently ages a 2-month-old to 2 years, which is exactly
    #: the kind of unit error worth generating.
    age_units: str = AGE_YEARS
    als_rate: float = 0.6
    refusal_rate: float = 0.06
    vitals: Vitals = field(default_factory=Vitals)
    meds: tuple[Med, ...] = ()
    procs: tuple[Proc, ...] = ()
    injury_codes: tuple[str, ...] = ()          # eInjury.01, pattern [TV-Y]nn
    arrest: str = ARREST_NO
    service: str = SERVICE_911_SCENE
    # Interventions are what a paramedic does; a BLS crew does fewer of them.
    requires_als: bool = False


def iso(moment: datetime) -> str:
    """NEMSIS DateTimeType: the pattern MANDATES a ±hh:mm offset (no `Z`)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S-06:00")


def _drift(rng: random.Random, low: int, high: int, index: int, improving: bool) -> int:
    """A serial reading, trending toward the middle of the range when treated.

    Static serial vitals would let a consumer that reads only the first (or
    last) set pass forever; drifting values make the ordering observable."""
    value = rng.randint(low, high)
    if not improving or index == 0:
        return value
    midpoint = (low + high) // 2
    return int(value + (midpoint - value) * min(1.0, 0.35 * index))


def _vital_set(rng: random.Random, spec: Vitals, when: datetime,
               index: int, improving: bool) -> dict:
    systolic = _drift(rng, *spec.systolic, index, improving)
    # Diastolic tracks systolic rather than floating free: an 80/140 reading is
    # nonsense no consumer should have to accommodate.
    diastolic = max(40, min(systolic - rng.randint(30, 60), 120))
    reading = {
        "eVitals.01": iso(when),
        "eVitals.02": NO,                  # obtained prior to this unit's care
        "eVitals.06": systolic,
        "eVitals.07": diastolic,
        "eVitals.10": _drift(rng, *spec.heart_rate, index, improving),
        "eVitals.12": _drift(rng, *spec.spo2, index, improving),
        "eVitals.14": _drift(rng, *spec.resp_rate, index, improving),
        "eVitals.26": spec.avpu,
        "eVitals.27": _drift(rng, *spec.pain, index, improving),
    }
    if spec.glucose:
        reading["eVitals.18"] = _drift(rng, *spec.glucose, index, improving)
    return reading


def build(presentation: Presentation, rng: random.Random,
          incident_start: datetime) -> dict:
    """Sample one internally-consistent call for this presentation.

    Returns a flat {element_id: value} map, plus lists for repeating groups.
    Internal consistency is the hard requirement: a patient who refuses
    transport must not carry a destination; interventions must postdate patient
    contact and predate transfer of care. Every one of those couplings is a
    chance for a consumer to be wrong in an interesting way.
    """
    low, high = presentation.age_range
    age = (rng.randint(low, high) if presentation.age_units != AGE_YEARS
           else max(low, min(dist.age_years(rng), high)))

    dispatched = incident_start
    en_route = dispatched + timedelta(seconds=rng.randint(30, 180))
    on_scene = en_route + timedelta(seconds=rng.randint(180, 900))
    at_patient = on_scene + timedelta(seconds=rng.randint(30, 300))
    depart = at_patient + timedelta(seconds=rng.randint(300, 1500))
    at_destination = depart + timedelta(seconds=rng.randint(300, 2400))
    transfer = at_destination + timedelta(seconds=rng.randint(120, 900))
    back_in_service = transfer + timedelta(seconds=rng.randint(120, 1200))

    refused = rng.random() < presentation.refusal_rate
    als = presentation.requires_als or rng.random() < presentation.als_rate

    values: dict[str, object] = {
        "eResponse.05": presentation.service,
        "eResponse.15": LEVEL_ALS if als else LEVEL_BLS,
        "eDispatch.01": presentation.dispatch_code,

        "eTimes.01": iso(dispatched - timedelta(seconds=rng.randint(20, 90))),
        "eTimes.03": iso(dispatched),
        "eTimes.05": iso(en_route),
        "eTimes.06": iso(on_scene),
        "eTimes.07": iso(at_patient),
        "eTimes.13": iso(back_in_service),

        "ePatient.15": age,
        "ePatient.16": presentation.age_units,
        "ePatient.25": SEX[dist.pick(rng, "sex")],

        "eSituation.03": COMPLAINT_CHIEF,
        "eSituation.04": presentation.complaint,
        "eSituation.11": rng.choice(presentation.impressions),

        "eScene.01": YES,
        "eScene.07": NO,

        "eArrest.01": presentation.arrest,
        "eDisposition.30": DISPOSITION_REFUSED if refused else DISPOSITION_TRANSPORTED,
    }
    if presentation.symptom:
        values["eSituation.09"] = presentation.symptom
    if presentation.injury_codes:
        values["eSituation.02"] = INJURY_YES
        values["eInjury.01"] = rng.choice(presentation.injury_codes)

    # Serial vitals. A refusal is one set on scene; a transport gets 2-3,
    # trending toward normal once treated — the shape of a real chart.
    if refused:
        readings = [at_patient + timedelta(seconds=rng.randint(60, 300))]
    else:
        readings = [at_patient + timedelta(seconds=rng.randint(30, 240))]
        for _ in range(rng.randint(1, 2)):
            readings.append(readings[-1] + timedelta(seconds=rng.randint(300, 720)))
        readings = [t for t in readings if t < transfer] or readings[:1]

    treated = als and not refused
    values["eVitals.VitalGroup"] = [
        _vital_set(rng, presentation.vitals, when, index, improving=treated)
        for index, when in enumerate(readings)
    ]

    # Interventions. A refusal gets none; a BLS crew gets the non-drug ones.
    if not refused:
        first_contact = at_patient + timedelta(seconds=rng.randint(120, 420))
        if presentation.meds and als:
            values["eMedications.MedicationGroup"] = [
                {
                    "eMedications.01": iso(
                        first_contact + timedelta(seconds=90 * index)),
                    "eMedications.02": NO,
                    "eMedications.03": med.rxnorm,
                    "eMedications.04": med.route,
                    "eMedications.05": med.dose,
                    "eMedications.06": med.units,
                }
                for index, med in enumerate(presentation.meds)
            ]
        if presentation.procs:
            doable = presentation.procs if als else presentation.procs[:1]
            values["eProcedures.ProcedureGroup"] = [
                {
                    "eProcedures.01": iso(
                        first_contact + timedelta(seconds=60 * index)),
                    "eProcedures.02": NO,
                    "eProcedures.03": proc.snomed,
                    "eProcedures.05": proc.attempts,
                    "eProcedures.06": YES if proc.successful else NO,
                }
                for index, proc in enumerate(doable)
            ]
        values.update({
            "eTimes.09": iso(depart),
            "eTimes.11": iso(at_destination),
            "eTimes.12": iso(transfer),
        })
    return values
