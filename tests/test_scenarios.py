"""The scenario library.

The failure mode this file targets is a scenario that is XSD-valid and
clinically nonsense — a document that passes every gate and teaches its
consumer something untrue. Codes are the sharpest edge: a NEMSIS value is an
opaque seven-digit number, so a wrong one is invisible on inspection and still
validates whenever it happens to belong to the same enumeration.

So the codes are checked against the schema's own `xs:documentation` labels
rather than trusted. Both defects found while building this library were of
exactly that kind: `eSituation.02` has its own yes/no set in a DIFFERENT order
from the generic one (9922001 is *No*), and an external-cause code was used as
a primary impression, which the field's pattern excludes.
"""

from __future__ import annotations

import random
import re
from datetime import datetime

import pytest
from lxml import etree

from nemsynth import schema, validate
from nemsynth.generate import generate_mci, generate_one, scenario_for
from nemsynth.scenarios import base
from nemsynth.skeleton import NS
from nemsynth.scenarios.library import LIBRARY


@pytest.fixture(scope="module")
def model():
    return schema.load("3.5.0")


def _node(model, name):
    def walk(node):
        if node.name == name:
            return node
        for child in node.children:
            found = walk(child)
            if found:
                return found
    return walk(model.patient_care_report())


#: Every NEMSIS code this library pins, and the meaning it claims. The label is
#: matched as a prefix so the schema's parenthetical suffixes ("Milligrams
#: (mg)") do not have to be reproduced exactly.
PINNED = {
    "eMedications.04": {
        base.ROUTE_IV: "Intravenous", base.ROUTE_IM: "Intramuscular",
        base.ROUTE_IN: "Intranasal", base.ROUTE_IO: "Intraosseous",
        base.ROUTE_ORAL: "Oral", base.ROUTE_SL: "Sublingual",
        base.ROUTE_NEB: "Nebulizer", base.ROUTE_ET: "Endotracheal",
    },
    "eMedications.06": {
        base.UNIT_MG: "Milligrams (mg)", base.UNIT_MCG: "Micrograms (mcg)",
        base.UNIT_ML: "Milliliters", base.UNIT_G: "Grams",
        base.UNIT_LPM: "Liters Per Minute", base.UNIT_PUFFS: "Puffs",
    },
    "eVitals.26": {
        base.AVPU_ALERT: "Alert", base.AVPU_VERBAL: "Verbal",
        base.AVPU_PAIN: "Painful", base.AVPU_UNRESPONSIVE: "Unresponsive",
    },
    "ePatient.16": {base.AGE_YEARS: "Years", base.AGE_MONTHS: "Months"},
    "eArrest.01": {
        base.ARREST_NO: "No", base.ARREST_BEFORE_EMS: "Yes, Prior to Any EMS",
        base.ARREST_AFTER_EMS: "Yes, After Any EMS",
    },
    # The set that already bit us: note 001 is No and 005 is Yes, the reverse
    # of the generic 9923xxx ordering.
    "eSituation.02": {
        base.INJURY_NO: "No", base.INJURY_UNKNOWN: "Unknown",
        base.INJURY_YES: "Yes",
    },
    "ePatient.25": {base.SEX["Female"]: "Female", base.SEX["Male"]: "Male"},
    # The generic yes/no pair. Pinned because an inversion here is invisible:
    # both values are legal wherever the type appears, so the document still
    # validates while asserting the opposite of what the scenario meant.
    "eScene.07": {base.YES: "Yes", base.NO: "No"},
    # An ECG rhythm is the sharpest example of why this test exists: 9901035
    # is PEA, and picking it for a routine chest-pain patient would have put
    # every one of them in cardiac arrest — clinically absurd, XSD-valid, and
    # invisible without reading the label back.
    "eVitals.03": {base.ECG_RHYTHM_SINUS: "Sinus Rhythm"},
    "eVitals.04": {base.ECG_TYPE_12_LEAD: "12 Lead"},
    "eArrest.11": {base.RHYTHM_VFIB: "Ventricular Fibrillation",
                   base.RHYTHM_ASYSTOLE: "Asystole"},
    "eArrest.12": {base.ROSC_NO: "No",
                   base.ROSC_PRIOR_TO_ED: "Yes, Prior to Arrival at the ED"},
    "eArrest.18": {base.END_ROSC_FIELD: "ROSC in the Field",
                   base.END_EXPIRED_FIELD: "Expired in the Field"},
    "eDisposition.16": {base.TRANSPORT_GROUND: "Ground-Ambulance"},
    "eDisposition.21": {base.DEST_ED: "Hospital-Emergency Department"},
    "eDisposition.19": {base.ACUITY_CRITICAL: "Critical (Red)",
                        base.ACUITY_LOWER: "Lower Acuity (Green)"},
    "eMedications.10": {base.ROLE_PARAMEDIC: "Paramedic"},
    "eMedications.08": {base.MED_NO_COMPLICATION: "None"},
    "eProcedures.07": {base.PROC_NO_COMPLICATION: "None"},
}

#: RxCUI -> RxNorm "Name" (ingredient level), retrieved 2026-08-16 from NLM's
#: public RxNorm REST API: rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/property.json
#: ?propName=RxNorm%20Name. That data is public domain (no UMLS license
#: needed), so this is a live source, not an assumption — pinned here so the
#: suite fails offline instead of re-querying the network on every run.
RXNORM_NAMES = {
    "1191": ("aspirin",), "4917": ("nitroglycerin",), "4337": ("fentanyl",),
    "7052": ("morphine",), "26225": ("ondansetron",), "7242": ("naloxone",),
    "435": ("albuterol",), "7213": ("ipratropium",), "3992": ("epinephrine",),
    "3498": ("diphenhydramine",), "6902": ("methylprednisolone",),
    "6960": ("midazolam",),
    "4850": ("glucose", "dextrose"),  # RxNorm's ingredient name; dextrose is the clinical synonym
    "4832": ("glucagon",), "703": ("amiodarone",), "7806": ("oxygen",),
    "9863": ("sodium chloride",),
}


def test_medication_rxcuis_resolve_to_the_ingredient_the_library_claims():
    """Each `Med.rxnorm` must be the RxCUI for the drug `Med.name` says it is —
    otherwise a document is a structurally valid, real-looking RxCUI attached
    to the wrong medication, which is worse than an obviously fake one."""
    seen = set()
    for presentation in LIBRARY.values():
        for med in presentation.meds:
            seen.add(med.rxnorm)
            assert med.rxnorm in RXNORM_NAMES, (
                f"{med.rxnorm} ({med.name}) is not a verified RxCUI; "
                f"look it up at rxnav.nlm.nih.gov before adding it"
            )
            aliases = RXNORM_NAMES[med.rxnorm]
            # "Dextrose 50%" / "Sodium chloride 0.9%" carry strength the bare
            # ingredient name does not, so match on containment, not equality.
            assert any(alias in med.name.lower() for alias in aliases), (
                f"RxCUI {med.rxnorm} is {aliases!r} per RxNorm, "
                f"library calls it {med.name!r}"
            )
    assert seen == set(RXNORM_NAMES), "RXNORM_NAMES has entries the library never uses"


#: Every ICD-10-CM code the library assigns as an impression, symptom or
#: injury code, retrieved 2026-08-16 from NLM's public Clinical Table Search
#: Service (clinicaltables.nlm.nih.gov/api/icd10cm — public domain, built from
#: CMS's own ICD-10-CM release). A code missing here is either fake or, like
#: the two this test caught, a real category missing its mandatory 7th
#: character: `T14.90` isn't billable on its own (only T14.90XA/XD/XS are),
#: and `V29.9XXA` doesn't exist at all — V29 is bicycle codes, not cars.
ICD10CM_DESCRIPTIONS = {
    "R07.9": "chest pain, unspecified",
    "I20.9": "angina pectoris, unspecified",
    "R07.89": "other chest pain",
    "I46.9": "cardiac arrest, cause unspecified",
    "I46.2": "cardiac arrest due to underlying cardiac condition",
    "R09.2": "respiratory arrest",
    "I63.9": "cerebral infarction, unspecified",
    "G45.9": "transient cerebral ischemic attack, unspecified",
    "I61.9": "nontraumatic intracerebral hemorrhage, unspecified",
    "R47.01": "aphasia",
    "J44.1": "chronic obstructive pulmonary disease with (acute) exacerbation",
    "J45.901": "unspecified asthma with (acute) exacerbation",
    "J18.9": "pneumonia, unspecified organism",
    "R06.02": "shortness of breath",
    "E11.649": "type 2 diabetes mellitus with hypoglycemia without coma",
    "E11.65": "type 2 diabetes mellitus with hyperglycemia",
    "E16.2": "hypoglycemia, unspecified",
    "R41.82": "altered mental status, unspecified",
    "T40.1X1A": "poisoning by heroin, accidental (unintentional), initial encounter",
    "T40.601A": "poisoning by unspecified narcotics, accidental (unintentional), initial encounter",
    "F11.90": "opioid use, unspecified, uncomplicated",
    "R06.89": "other abnormalities of breathing",
    "R56.9": "unspecified convulsions",
    "G40.909": "epilepsy, unspecified, not intractable, without status epilepticus",
    "S09.90XA": "unspecified injury of head, initial encounter",
    "S29.9XXA": "unspecified injury of thorax, initial encounter",
    "T14.90XA": "injury, unspecified, initial encounter",
    "R52": "pain, unspecified",
    "V43.52XA": "car driver injured in collision with other type car in traffic accident, initial encounter",
    "V47.5XXA": "car driver injured in collision with fixed or stationary object in traffic accident, initial encounter",
    "V49.9XXA": "car occupant (driver) (passenger) injured in unspecified traffic accident, initial encounter",
    "S72.001A": "fracture of unspecified part of neck of right femur, initial encounter for closed fracture",
    "S00.03XA": "contusion of scalp, initial encounter",
    "M25.551": "pain in right hip",
    "W19.XXXA": "unspecified fall, initial encounter",
    "W18.30XA": "fall on same level, unspecified, initial encounter",
    "W01.0XXA": "fall on same level from slipping, tripping and stumbling without subsequent striking against object, initial encounter",
    "T78.2XXA": "anaphylactic shock, unspecified, initial encounter",
    "T78.40XA": "allergy, unspecified, initial encounter",
    "T78.00XA": "anaphylactic reaction due to unspecified food, initial encounter",
    "R22.9": "localized swelling, mass and lump, unspecified",
    "R10.9": "unspecified abdominal pain",
    "R10.31": "right lower quadrant pain",
    "K59.00": "constipation, unspecified",
    "F29": "unspecified psychosis not due to a substance or known physiological condition",
    "R45.851": "suicidal ideations",
    "F41.9": "anxiety disorder, unspecified",
    "R45.4": "irritability and anger",
    "O80": "encounter for full-term uncomplicated delivery",
    "O47.9": "false labor, unspecified",
    "Z34.90": "encounter for supervision of normal pregnancy, unspecified, unspecified trimester",
    "R50.9": "fever, unspecified",
    "J06.9": "acute upper respiratory infection, unspecified",
    "R56.00": "simple febrile convulsions",
    "I50.9": "heart failure, unspecified",
    "N18.6": "end stage renal disease",
    "J96.00": "acute respiratory failure, unspecified whether with hypoxia or hypercapnia",
    "R06.00": "dyspnea, unspecified",
}


def test_icd10_codes_are_real_billable_codes():
    """A code that matches the field's regex but isn't in CMS's actual
    ICD-10-CM release is invisible in review and wrong in the corpus — this
    checks existence, which the pattern test deliberately does not."""
    seen = set()
    for presentation in LIBRARY.values():
        codes = (*presentation.impressions,
                 *((presentation.symptom,) if presentation.symptom else ()),
                 *presentation.injury_codes)
        seen.update(codes)
        for code in codes:
            assert code in ICD10CM_DESCRIPTIONS, (
                f"{presentation.key}: {code!r} is not a real ICD-10-CM code; "
                f"check clinicaltables.nlm.nih.gov/api/icd10cm before adding it"
            )
    assert seen == set(ICD10CM_DESCRIPTIONS), (
        "ICD10CM_DESCRIPTIONS has entries the library never uses"
    )


@pytest.mark.parametrize("element", sorted(PINNED))
def test_pinned_codes_still_mean_what_they_claim(model, element):
    """A code that silently changes meaning between releases would produce a
    corpus that validates and lies. Read the label back from the schema."""
    labels = model.simple_type(_node(model, element).type_name).labels
    for code, expected in PINNED[element].items():
        assert code in labels, f"{element}: {code} is not a legal value"
        assert labels[code].startswith(expected), (
            f"{element} {code}: schema says {labels[code]!r}, "
            f"library claims {expected!r}"
        )


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_clinical_codes_satisfy_the_fields_pattern(model, key):
    """Impressions, symptoms and injury codes each go in a field with its OWN
    ICD-10 pattern. eSituation.11 admits [A-QSTUZ] but not V-Y, so an
    external-cause code is legal in eInjury.01 and illegal as an impression —
    which is precisely the mistake this catches."""
    presentation = LIBRARY[key]
    for element, codes in (
        ("eSituation.11", presentation.impressions),
        ("eSituation.09", (presentation.symptom,) if presentation.symptom else ()),
        ("eInjury.01", presentation.injury_codes),
    ):
        (pattern,) = model.simple_type(_node(model, element).type_name).patterns
        for code in codes:
            assert re.fullmatch(pattern, code), (
                f"{key}: {code!r} is not valid for {element}"
            )


@pytest.mark.parametrize("key", sorted(LIBRARY))
def test_every_scenario_generates_valid_nemsis(key):
    """Across seeds and profiles, because the branches (refusal, ALS/BLS,
    number of serial vitals) are sampled per document."""
    for seed in range(6):
        for profile in ("clean", "high"):
            assert validate.errors(
                generate_one(seed=seed, scenario=key, profile=profile)) == []


def test_library_covers_the_declared_presentations():
    assert len(LIBRARY) == 15
    for key, presentation in LIBRARY.items():
        assert presentation.key == key, "key and mapping disagree"


def test_repeating_groups_actually_repeat():
    """The capability the library exists to exercise: a consumer must turn N
    instances into N resources sharing the group's .01 timestamp, and could
    never be tested against a generator that emitted one instance per group."""
    seen_multi = 0
    for seed in range(40):
        document = generate_one(seed=seed, scenario="chest-pain", profile="clean")
        if document.count(b"<eVitals.VitalGroup>") > 1:
            seen_multi += 1
        # Each instance must carry its OWN timestamp, not a shared one.
        stamps = re.findall(rb"<eVitals\.01>([^<]+)</eVitals\.01>", document)
        assert len(stamps) == len(set(stamps)), "serial vitals share a timestamp"
    assert seen_multi, "no document had more than one vitals group"


def test_refusal_has_no_transport_leg():
    """Internal consistency: a patient who refuses is not delivered anywhere.
    A document asserting both would be XSD-valid and clinically impossible."""
    checked = 0
    for seed in range(150):
        document = generate_one(seed=seed, scenario="overdose", profile="clean")
        if base.DISPOSITION_REFUSED.encode() not in document:
            continue
        checked += 1
        # eTimes.11 (arrived at destination) must be nil for a refusal.
        arrival = re.search(rb"<eTimes\.11[^>]*>", document).group(0)
        assert b'nil="true"' in arrival, "a refusal carried a destination arrival"
    assert checked, "no refusal generated in 150 seeds"


def test_mixed_rotates_the_whole_library():
    """A mixed corpus must contain every presentation in a known proportion, so
    a finding is attributable without re-deriving the draw."""
    drawn = {scenario_for(seed, "mixed") for seed in range(len(LIBRARY) * 2)}
    assert drawn == set(LIBRARY)
    assert scenario_for(7, "chest-pain") == "chest-pain"


def test_pediatric_ages_are_charted_in_months():
    """An infant charted in years is a unit error a consumer will propagate."""
    presentation = LIBRARY["pediatric-fever"]
    assert presentation.age_units == base.AGE_MONTHS
    values = base.build(presentation, random.Random(3), datetime(2026, 5, 1, 9))
    assert values["ePatient.16"] == base.AGE_MONTHS
    assert 1 <= values["ePatient.15"] <= 23


def test_mci_holds_several_reports_in_one_dataset():
    """A mass-casualty file carries N PatientCareReports. This is the shape
    that catches a consumer assuming one report per file — a reasonable-looking
    assumption that silently discards every patient but the first."""
    document = generate_mci(seed=1, patients=5, profile="clean")
    assert validate.errors(document) == []
    assert document.count(b"<PatientCareReport ") == 5


def test_mci_patients_share_the_incident_but_not_the_chart():
    """The defining property. Shared incident number, distinct records: a
    consumer that keys on either alone gets a different wrong answer."""
    document = generate_mci(seed=4, patients=6, profile="clean")
    incidents = set(re.findall(rb"<eResponse\.03>([^<]+)</eResponse\.03>", document))
    records = re.findall(rb"<eRecord\.01>([^<]+)</eRecord\.01>", document)
    uuids = re.findall(rb'<PatientCareReport UUID="([^"]+)"', document)
    assert len(incidents) == 1, "patients must share one incident number"
    assert len(set(records)) == 6, "each patient needs their own record number"
    assert len(set(uuids)) == 6, "each report needs its own UUID"


def test_mci_is_flagged_as_one_and_triaged():
    """eScene.07 must say Yes — and it is the field an inverted yes/no pair
    silently corrupted, so it is asserted by value, not by presence."""
    document = generate_mci(seed=9, patients=4, profile="clean")
    flags = re.findall(rb"<eScene\.07[^>]*>([^<]*)</eScene\.07>", document)
    assert flags and all(f.decode() == base.YES for f in flags)
    triage = re.findall(rb"<eScene\.08[^>]*>([^<]*)</eScene\.08>", document)
    assert len(triage) == 4
    legal = {"2708001", "2708003", "2708005", "2708007", "2708009"}
    assert {t.decode() for t in triage} <= legal


def test_only_the_first_unit_is_first_on_scene():
    """Every patient claiming to be the first arrival is internally
    inconsistent, and the kind of thing a consumer may reasonably rely on."""
    document = generate_mci(seed=2, patients=5, profile="clean")
    first = re.findall(rb"<eScene\.01[^>]*>([^<]*)</eScene\.01>", document)
    assert [f.decode() for f in first].count(base.YES) == 1


def test_mci_rejects_an_empty_incident():
    with pytest.raises(ValueError):
        generate_mci(seed=1, patients=0)


def test_arrest_outcome_is_internally_consistent():
    """A patient with return of spontaneous circulation is not also expired in
    the field, and CPR discontinued "for ROSC" must not appear on a patient who
    never got it. Both contradictions are XSD-valid and would teach a consumer
    something false."""
    import random as _random
    for seed in range(60):
        block = base._arrest_block(_random.Random(seed))
        rosc = block["eArrest.12"] != base.ROSC_NO
        assert block["eArrest.18"] == (base.END_ROSC_FIELD if rosc
                                       else base.END_EXPIRED_FIELD)
        assert block["eArrest.16"] == (base.CPR_STOPPED_ROSC if rosc
                                       else base.CPR_STOPPED_PROTOCOL)


def test_glasgow_components_sum_to_the_total():
    """A chart whose GCS components contradict its total is the sort of
    internal inconsistency a consumer may reasonably trust and be wrong on."""
    for seed in range(40):
        document = generate_one(seed=seed, scenario="chest-pain", profile="clean")
        root = etree.fromstring(document)
        for group in root.iter(f"{{{NS}}}eVitals.VitalGroup"):
            def value(tag):
                found = group.find(f"{{{NS}}}{tag}")
                return int(found.text) if found is not None and found.text else None
            eye, verbal, motor = value("eVitals.19"), value("eVitals.20"), value("eVitals.21")
            total = value("eVitals.23")
            if None in (eye, verbal, motor, total):
                continue
            assert eye + verbal + motor == total, "GCS components != total"
            assert 3 <= total <= 15


def test_delay_codes_are_not_shared_between_elements():
    """Each of the five delay elements has its OWN enumeration. Reusing one
    element's code across all five was XSD-invalid, and the gate caught it."""
    codes = {element: (delay, none) for element, delay, none in base._DELAYS}
    assert len(codes) == 5
    prefixes = {element: delay[:4] for element, (delay, _) in codes.items()}
    assert len(set(prefixes.values())) == 5, "delay codes share a prefix"
