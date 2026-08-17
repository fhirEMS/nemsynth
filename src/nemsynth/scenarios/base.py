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
  - **RxNorm** ingredient RxCUIs are verified against NLM's public RxNorm REST
    API (rxnav.nlm.nih.gov — public domain, no UMLS license required): every
    `Med.rxnorm` in the library resolves to the ingredient `Med.name` claims.
    `test_scenarios.py` pins the (RxCUI, name) pairs so a typo'd digit fails
    the suite instead of silently generating a real code for the wrong drug.
  - **SNOMED CT** procedure concepts are clinically plausible and match codes
    commonly cited in public NEMSIS/CMS implementation guidance, but are NOT
    verified against a licensed release — SNOMED CT terms require a member's
    license to redistribute, and this project does not carry one. Treat them
    as structurally correct and good enough to exercise a mapper, not as a
    terminology source. See `nemsynth sources`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .. import distributions as dist
from ..crew import pcr_crew_groups
from ..gnis import ANSI_STATE, scene_city

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

# --- Disposition. Every transport answers these, and none were being
# generated, so the mapper's whole destination/handoff path went unexercised.
TRANSPORT_GROUND = "4216005"          # Ground-Ambulance
MODE_EMERGENT = "4217001"             # Emergent (Immediate Response)
MODE_NON_EMERGENT = "4217005"         # Non-Emergent
ACUITY_CRITICAL = "4219001"           # Critical (Red)
ACUITY_EMERGENT = "4219003"           # Emergent (Yellow)
ACUITY_LOWER = "4219005"              # Lower Acuity (Green)
ACUITY_DEAD_WITH_EFFORT = "4219009"   # Dead with Resuscitation Efforts
REASON_CLOSEST = "4220001"            # Closest Facility
REASON_PROTOCOL = "4220019"           # Protocol
DEST_ED = "4221003"                   # Hospital-Emergency Department
CAPABILITY_GENERAL = "9908007"        # Hospital (General)
ALERT_NONE = "4224001"                # No
ALERT_CARDIAC_ARREST = "4224005"      # Yes-Cardiac Arrest
CARE_PROVIDED = "4228001"             # Patient Evaluated and Care Provided
CARE_REFUSED = "4228007"              # Patient Refused Evaluation/Care
CREW_PRIMARY = "4229001"              # Initiated and Continued Primary Care
LEVEL_BLS_PROTOCOL = "4232001"        # BLS - All Levels
LEVEL_ALS_PROTOCOL = "4232005"        # ALS - Paramedic

# --- ECG, GCS qualifier, stroke scale.
ECG_RHYTHM_SINUS = "9901047"          # Sinus Rhythm
# 9901035 is PEA. Guessing it here would have put every routine chest-pain
# patient into pulseless electrical activity — clinically absurd, perfectly
# XSD-valid, and invisible without reading the label back.
ECG_TYPE_12_LEAD = "3304007"          # 12 Lead-Left Sided (Normal)
ECG_INTERP_MANUAL = "3305003"         # Manual Interpretation
GCS_LEGITIMATE = "3322003"            # Initial GCS has legitimate value
STROKE_SCALE_CINCINNATI = "3330001"   # Cincinnati Prehospital Stroke Scale
STROKE_NEGATIVE = "3329001"           # Negative

# --- Cardiac arrest registry. Thirteen national elements, none generated
# before: the arrest scenario set eArrest.01 and stopped.
ETIOLOGY_CARDIAC = "3002001"          # Cardiac (Presumed)
RESUS_COMPRESSIONS = "3003005"        # Initiated Chest Compressions
WITNESSED_BYSTANDER = "3004007"       # Witnessed by Bystander
WITNESSED_NOT = "3004001"             # Not Witnessed
AED_NO = "3007001"                    # No
AED_WITH_DEFIB = "3007005"            # Yes, With Defibrillation
CPR_MANUAL = "3009001"                # Compressions-Manual
RHYTHM_VFIB = "3011011"               # Ventricular Fibrillation
RHYTHM_ASYSTOLE = "3011001"           # Asystole
ROSC_NO = "3012001"                   # No
ROSC_PRIOR_TO_ED = "3012005"          # Yes, Prior to Arrival at the ED
CPR_STOPPED_ROSC = "3016011"          # Return of Spontaneous Circulation
CPR_STOPPED_PROTOCOL = "3016009"      # Protocol/Policy Requirements Completed
ARRIVAL_RHYTHM_ASYSTOLE = "9901003"   # Asystole
END_ROSC_FIELD = "3018007"            # ROSC in the Field
END_EXPIRED_FIELD = "3018003"         # Expired in the Field
BY_BYSTANDER = "3020001"              # Bystander
BY_EMS_FIRST_RESPONDER = "3020007"    # First Responder (EMS)
AED_BY_EMS = "3021007"                # First Responder (EMS)
DEFIB_BY_EMS = "3022007"              # First Responder (EMS)


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
    #: Emit the full cardiac-arrest registry (eArrest.02-.22), not just .01.
    arrest_detail: bool = False
    #: Emit ECG rhythm/type/interpretation on each vitals set.
    ecg: bool = False
    #: Emit a prehospital stroke scale result on each vitals set.
    stroke_scale: bool = False
    #: eSituation.07 / .08 — where the complaint is, and which organ system.
    body_site: str | None = None
    organ_system: str | None = None
    #: eProtocols.01, the protocol the crew worked under.
    protocol: str | None = None
    #: eSituation.20, required in substance for an interfacility transfer.
    transfer_reason: str | None = None
    #: eHistory.17 — alcohol/drug indicators noted at the scene.
    substance_indicators: bool = False
    #: eVitals.31 — the reperfusion checklist, for a suspected STEMI.
    reperfusion: bool = False
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
               index: int, improving: bool, ecg: bool = False,
               stroke_scale: bool = False, reperfusion: bool = False) -> dict:
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

    # Glasgow Coma Score. The components MUST sum to the total — a chart where
    # they do not is the sort of internal contradiction a consumer may
    # reasonably trust and be wrong about.
    eye = 1 if spec.avpu == AVPU_UNRESPONSIVE else rng.randint(3, 4)
    verbal = 1 if spec.avpu == AVPU_UNRESPONSIVE else rng.randint(3, 5)
    motor = 1 if spec.avpu == AVPU_UNRESPONSIVE else rng.randint(4, 6)
    reading.update({
        "eVitals.19": eye,
        "eVitals.20": verbal,
        "eVitals.21": motor,
        "eVitals.22": GCS_LEGITIMATE,
        "eVitals.23": eye + verbal + motor,
    })
    if ecg:
        reading.update({
            "eVitals.03": ECG_RHYTHM_SINUS,
            "eVitals.04": ECG_TYPE_12_LEAD,
            "eVitals.05": ECG_INTERP_MANUAL,
        })
    if reperfusion:
        reading["eVitals.31"] = REPERFUSION_NO_CONTRA
    if stroke_scale:
        reading.update({
            "eVitals.29": STROKE_NEGATIVE,
            "eVitals.30": STROKE_SCALE_CINCINNATI,
        })
    return reading


#: Intervention outcome/attribution, per group instance. A medication given
#: with no recorded response, by nobody in particular, is a chart nobody wrote.
MED_RESPONSE_IMPROVED = "9916001"     # Improved
MED_RESPONSE_UNCHANGED = "9916003"    # Unchanged
ROLE_PARAMEDIC = "9905007"            # Paramedic
PROC_NO_COMPLICATION = "3907033"      # None
MED_NO_COMPLICATION = "3708031"       # None

#: Demographics and administrative elements every real chart carries.
PAYMENT_INSURANCE = "2601001"         # Insurance
SERVICE_LEVEL_BLS = "2650007"         # BLS
SCENE_PATIENTS_SINGLE = "2707005"     # Single
SCENE_PATIENTS_MULTIPLE = "2707001"   # Multiple
EMD_WITH_INSTRUCTIONS = "2302003"     # Yes, With Pre-Arrival Instructions
ACUITY_INITIAL = {
    ACUITY_CRITICAL: "2813001",       # Critical (Red)
    ACUITY_EMERGENT: "2813003",       # Emergent (Yellow)
    ACUITY_LOWER: "2813005",          # Lower Acuity (Green)
    ACUITY_DEAD_WITH_EFFORT: "2813007",
}

#: (element, a real delay, the explicit "None/No Delay"). Each element has its
#: own enumeration; the codes are NOT interchangeable between them.
_DELAYS = (
    ("eResponse.08", "2208005", "2208013"),   # High Call Volume     / None
    ("eResponse.09", "2209001", "2209011"),   # Crowd                / None
    ("eResponse.10", "2210001", "2210017"),   # Awaiting Air Unit    / None
    ("eResponse.11", "2211001", "2211011"),   # Crowd                / None
    ("eResponse.12", "2212001", "2212015"),   # Clean-up             / None
)


BARRIERS_NONE = "3101009"             # None Noted
DRUG_USE_ADMITS = "3117005"           # Patient Admits to Alcohol Use
TRAUMA_HIGH_RISK = "2903005"          # Chest wall instability/deformity/flail
TRAUMA_MODERATE_RISK = "2904001"      # Pedestrian/bicycle rider thrown/run over
REPERFUSION_NO_CONTRA = "3331003"     # No Contraindications to Thrombolytic Use

#: ePatient.14 Race. Drawn uniformly: this is a STRUCTURAL generator, and
#: inventing a racial distribution would be a demographic claim the project has
#: no basis for and no business making. The point is only that the element
#: carries a real value so a consumer's mapping of it is exercised.
_RACES = ("2514001", "2514003", "2514005", "2514007", "2514009", "2514011")


def _arrest_block(rng: random.Random) -> dict:
    """The cardiac-arrest registry (eArrest.02-.22).

    Thirteen national elements that were never generated: the arrest scenario
    set eArrest.01 and stopped, so everything a resuscitation actually records
    — who witnessed it, who started CPR, the first monitored rhythm, whether
    circulation returned — was invisible to any consumer being tested.

    The outcome drives the rest. A patient with ROSC is not also expired in the
    field, and CPR discontinued for "return of spontaneous circulation" must
    not appear on a patient who never got any; those contradictions are
    XSD-valid and would teach a consumer something false.
    """
    rosc = rng.random() < 0.35
    witnessed = rng.random() < 0.6
    bystander_cpr = witnessed and rng.random() < 0.5
    shockable = rng.random() < 0.4
    return {
        "eArrest.02": ETIOLOGY_CARDIAC,
        "eArrest.03": RESUS_COMPRESSIONS,
        "eArrest.04": WITNESSED_BYSTANDER if witnessed else WITNESSED_NOT,
        "eArrest.07": AED_WITH_DEFIB if bystander_cpr and shockable else AED_NO,
        "eArrest.09": CPR_MANUAL,
        "eArrest.11": RHYTHM_VFIB if shockable else RHYTHM_ASYSTOLE,
        "eArrest.12": ROSC_PRIOR_TO_ED if rosc else ROSC_NO,
        "eArrest.16": CPR_STOPPED_ROSC if rosc else CPR_STOPPED_PROTOCOL,
        "eArrest.17": ARRIVAL_RHYTHM_ASYSTOLE,
        "eArrest.18": END_ROSC_FIELD if rosc else END_EXPIRED_FIELD,
        "eArrest.20": BY_BYSTANDER if bystander_cpr else BY_EMS_FIRST_RESPONDER,
        "eArrest.21": AED_BY_EMS,
        "eArrest.22": DEFIB_BY_EMS,
    }


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

        # Scene location. The GNIS code and state come from the verified
        # table together, so a corpus can vary the town without ever placing a
        # city in the wrong state.
        "eScene.17": scene_city(rng).gnis,
        "eScene.18": ANSI_STATE,
        "eScene.01": YES,
        "eScene.06": SCENE_PATIENTS_SINGLE,
        "eScene.07": NO,
        "eDispatch.02": EMD_WITH_INSTRUCTIONS,
        "ePatient.14": rng.choice(_RACES),
        "ePayment.01": PAYMENT_INSURANCE,
        "ePayment.50": SERVICE_LEVEL_BLS,
        "eHistory.01": BARRIERS_NONE,

        "eArrest.01": presentation.arrest,
        # The crew that ran the call. Repeating group: one instance per member,
        # carrying only IDs and codes — the names live in the DEM roster, which
        # is the join this package exists to exercise.
        "eCrew.CrewGroup": pcr_crew_groups(),
        "eDisposition.30": DISPOSITION_REFUSED if refused else DISPOSITION_TRANSPORTED,
    }
    if presentation.symptom:
        values["eSituation.09"] = presentation.symptom
    if presentation.body_site:
        values["eSituation.07"] = presentation.body_site
    if presentation.organ_system:
        values["eSituation.08"] = presentation.organ_system
    if presentation.protocol:
        values["eProtocols.01"] = presentation.protocol
    if presentation.transfer_reason:
        values["eSituation.20"] = presentation.transfer_reason
    if presentation.substance_indicators:
        values["eHistory.17"] = DRUG_USE_ADMITS
    if presentation.injury_codes:
        values["eSituation.02"] = INJURY_YES
        values["eInjury.01"] = rng.choice(presentation.injury_codes)
        # Trauma triage criteria drive destination choice in the field, so a
        # trauma chart without them is missing the thing that justified it.
        if rng.random() < 0.4:
            values["eInjury.03"] = TRAUMA_HIGH_RISK
        elif rng.random() < 0.5:
            values["eInjury.04"] = TRAUMA_MODERATE_RISK

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
        _vital_set(rng, presentation.vitals, when, index, improving=treated,
                   ecg=presentation.ecg, stroke_scale=presentation.stroke_scale,
                   reperfusion=presentation.reperfusion)
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
                    "eMedications.07": (MED_RESPONSE_IMPROVED if index == 0
                                        else MED_RESPONSE_UNCHANGED),
                    "eMedications.08": MED_NO_COMPLICATION,
                    "eMedications.10": ROLE_PARAMEDIC,
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
                    "eProcedures.07": PROC_NO_COMPLICATION,
                    "eProcedures.08": MED_RESPONSE_IMPROVED,
                    "eProcedures.10": ROLE_PARAMEDIC,
                }
                for index, proc in enumerate(doable)
            ]
        values.update({
            "eTimes.09": iso(depart),
            "eTimes.11": iso(at_destination),
            "eTimes.12": iso(transfer),
            # The destination/handoff block. Every transport answers these, and
            # none were generated before, so the mapper's whole destination
            # path went unexercised at volume.
            "eDisposition.16": TRANSPORT_GROUND,
            "eDisposition.17": MODE_EMERGENT if als else MODE_NON_EMERGENT,
            "eDisposition.20": rng.choice([REASON_CLOSEST, REASON_PROTOCOL]),
            "eDisposition.21": DEST_ED,
            "eDisposition.23": CAPABILITY_GENERAL,
            "eDisposition.24": (ALERT_CARDIAC_ARREST if presentation.arrest_detail
                                else ALERT_NONE),
        })

    # Acuity on release must agree with the rest of the chart: a patient who
    # arrested and was not resuscitated is not "lower acuity".
    if presentation.arrest_detail:
        acuity = ACUITY_DEAD_WITH_EFFORT if not refused else ACUITY_CRITICAL
    elif refused:
        acuity = ACUITY_LOWER
    else:
        acuity = ACUITY_EMERGENT if als else ACUITY_LOWER
    values["eSituation.13"] = ACUITY_INITIAL[acuity]
    values.update({
        "eDisposition.19": acuity,
        "eDisposition.28": CARE_REFUSED if refused else CARE_PROVIDED,
        "eDisposition.29": CREW_PRIMARY,
        "eDisposition.32": LEVEL_ALS_PROTOCOL if als else LEVEL_BLS_PROTOCOL,
    })

    if presentation.arrest_detail:
        values.update(_arrest_block(rng))

    # Delays. Each of the five is a DIFFERENT enumeration with its own code
    # prefix — reusing one element's code across all five was XSD-invalid, and
    # the self-validation gate caught it. Both a real delay and an explicit
    # "None/No Delay" are worth generating: the second is an assertion, not a
    # gap, and a consumer that treats them alike loses that.
    for element, delay, none in _DELAYS:
        if rng.random() < 0.10:
            values[element] = delay
        elif rng.random() < 0.25:
            values[element] = none
    return values
