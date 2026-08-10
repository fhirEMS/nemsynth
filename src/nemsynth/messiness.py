"""Realistic imperfection — the part that makes a generated corpus useful.

A generator that emits only clean, fully-populated records is *less* useful
than the handful of published samples, because every document is the same
well-formed shape and a consumer sails through all of them. Real ePCRs are
incomplete, occasionally strange, and legal anyway. This module reintroduces
that, deliberately and reproducibly.

Everything here stays XSD-VALID. The point is not malformed input — the ingest
gate rejects that and nobody learns anything. The point is input the gate lets
through and a consumer then mishandles, which is where every defect this
project has found actually lived:

  - eVitals.07 "P" (palpated BP) crashed a converter outright
  - eVitals.18 "High" was flattened into "malformed data", losing a finding
  - a PCR number containing "/" escaped a configured output directory
  - a comment inside a value silently destroyed the reading
  - hour-24 timestamps are XSD-legal and FHIR-invalid

Each knob below exists because something in that list got through.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .schema import NV_NOT_APPLICABLE, NV_NOT_RECORDED, Schema
from .skeleton import Absent, Negative

#: NEMSIS NV codes (7701xxx) and the pertinent negatives (8801xxx) worth
#: generating. Variety matters: a consumer that maps every NV to "unknown" is
#: losing the distinction the standard exists to carry.
NV_NOT_REPORTING = "7701005"
PN_REFUSED = "8801019"
PN_UNABLE = "8801023"
PN_NO_KNOWN_ALLERGY = "8801013"

#: Free text that is ordinary in a narrative and hostile to naive handling:
#: XML-significant characters, quotes, newlines, and a very long run.
_UNTIDY_TEXT = [
    'Pt states "it feels like an elephant on my chest" & rates 8/10',
    "Spouse reports onset ~30 min prior; hx CABG x3\nNo relief w/ home NTG",
    "Pt uncooperative <combative on arrival> — see supplemental",
    "R/O ACS; ASA 324mg PO given @ 0714 (chewed) & 12-lead obtained",
    "L" + "o" * 180 + "ng narrative",
]

#: PCR numbers that are legal (eRecord.01 is xs:string, no pattern) and have
#: broken a consumer: path separators, query/fragment markers, spaces.
_UNTIDY_IDS = [
    "PCR {n}/2026",
    "PCR-{n}&amp;A",
    "PCR {n} #2",
    "2026/{n}?rev=2",
]


@dataclass(frozen=True)
class Profile:
    """How messy a generated corpus should be.

    Rates are per-element probabilities, so a corpus of N documents exercises
    each path roughly N x rate times — the reason to generate volume rather
    than hand-write cases."""

    name: str
    nv_rate: float          # a supplied value becomes nil+NV instead
    pn_rate: float          # an element asserts a pertinent negative
    sentinel_rate: float    # XSD-sanctioned non-numeric values (P/p, High/Low)
    boundary_rate: float    # hour-24, extreme ages, max-length strings
    untidy_text_rate: float # XML-significant characters in free text
    untidy_id_rate: float   # path/query characters in identifiers

    @property
    def is_clean(self) -> bool:
        return self.nv_rate == 0 and self.sentinel_rate == 0


CLEAN = Profile("clean", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
LOW = Profile("low", 0.05, 0.02, 0.02, 0.01, 0.05, 0.00)
MEDIUM = Profile("medium", 0.15, 0.06, 0.06, 0.04, 0.15, 0.02)
HIGH = Profile("high", 0.30, 0.15, 0.15, 0.12, 0.35, 0.10)

PROFILES = {p.name: p for p in (CLEAN, LOW, MEDIUM, HIGH)}

#: Elements whose absence is realistic and interesting. Deliberately NOT the
#: identity or timeline spine: a corpus where the patient has no age and the
#: call has no times is not "messy", it is useless.
#:
#: Split by SCOPE, because vitals live inside a repeating group. A knob written
#: against the top-level map stops firing the moment its element moves into a
#: group instance — which is exactly what happened when the scenario library
#: introduced serial vitals, and why CI asserts the traits appear rather than
#: trusting that the engine is wired up.
_ABSENTABLE_DOCUMENT = ("eSituation.11", "eScene.07", "eResponse.15")
_ABSENTABLE_VITALS = ("eVitals.12", "eVitals.14", "eVitals.27", "eVitals.10")

#: Elements that meaningfully carry a pertinent negative.
_NEGATABLE = {
    "eHistory.06": PN_NO_KNOWN_ALLERGY,   # No Known Drug Allergy
    "eHistory.08": PN_REFUSED,
}


def _apply_to_instance(instance: dict, rng: random.Random,
                       profile: Profile) -> dict:
    """Messiness scoped to ONE repeating-group instance.

    The two XSD-sanctioned sentinels live here, because both are vitals and
    both belong to a single reading rather than to the record: a palpated blood
    pressure on the second set does not make the first one palpated."""
    for element in _ABSENTABLE_VITALS:
        if element in instance and rng.random() < profile.nv_rate:
            instance[element] = Absent(_nv_code(rng))

    # eVitals.07 "P"/"p" — a palpated BP, routine on hypotensive patients, and
    # a crash in a real consumer.
    if "eVitals.07" in instance and rng.random() < profile.sentinel_rate:
        instance["eVitals.07"] = rng.choice(["P", "p"])
    # eVitals.18 "High"/"Low" — above or below the meter's range. Set even when
    # the scenario recorded no glucose: a reading that only exists because it
    # was off-scale is precisely the real-world case.
    if rng.random() < profile.sentinel_rate:
        instance["eVitals.18"] = rng.choice(["High", "Low"])
    return instance


def _age_bounds(schema: Schema) -> tuple[int, ...]:
    """The legal extremes of ePatient.15, read from the schema."""
    node = None
    for section in schema.patient_care_report().children:
        for child in section.children:
            for leaf in (child, *child.children):
                if leaf.name == "ePatient.15":
                    node = leaf
    if node is None or not node.type_name:
        return ()
    simple = schema.simple_type(node.type_name)
    if simple is None:
        return ()
    bounds = []
    for value in (simple.min_inclusive, simple.max_inclusive):
        if value is not None and value.lstrip("-").isdigit():
            bounds.append(int(value))
    return tuple(bounds)


def _nv_code(rng: random.Random) -> str:
    """Vary the reason. Real exports use all three, and they mean different
    things — flattening them is a consumer bug worth provoking."""
    return rng.choices(
        [NV_NOT_RECORDED, NV_NOT_APPLICABLE, NV_NOT_REPORTING],
        weights=[0.6, 0.3, 0.1], k=1,
    )[0]


def _to_hour_24(timestamp: str) -> str:
    """XSD-legal end-of-day, and invalid FHIR — hours cap at 23 there."""
    if "T" not in timestamp:
        return timestamp
    date, _, rest = timestamp.partition("T")
    offset = rest[-6:] if len(rest) >= 6 else "-06:00"
    return f"{date}T24:00:00{offset}"


def apply(
    values: dict[str, object],
    rng: random.Random,
    profile: Profile,
    schema: Schema,
) -> dict[str, object]:
    """Return a messier copy of a scenario's values.

    Takes a copy rather than mutating: a scenario stays reproducible and
    inspectable on its own, and the messiness is a separable layer that can be
    turned off to isolate whether a finding is scenario or profile driven.
    """
    if profile.is_clean:
        return dict(values)
    messy = dict(values)

    # Repeating-group instances get their own treatment: each set of serial
    # vitals is a separate observation event and goes missing independently.
    for key, value in list(messy.items()):
        if isinstance(value, list):
            messy[key] = [_apply_to_instance(dict(instance), rng, profile)
                          for instance in value]

    # 1. Values that go absent, with a VARIED reason.
    for element in _ABSENTABLE_DOCUMENT:
        if element in messy and rng.random() < profile.nv_rate:
            messy[element] = Absent(_nv_code(rng))

    # 2. Pertinent negatives — assertions, not gaps.
    for element, code in _NEGATABLE.items():
        if rng.random() < profile.pn_rate:
            messy[element] = Negative(code)

    # 4. Boundaries: hour-24 timestamps and age extremes.
    if rng.random() < profile.boundary_rate:
        for element in ("eTimes.09", "eTimes.11", "eTimes.12", "eTimes.13"):
            if isinstance(messy.get(element), str):
                messy[element] = _to_hour_24(messy[element])
                break
    # Age extremes taken FROM THE SCHEMA, not guessed: an out-of-range value
    # would fail the XSD gate, and this tier's whole purpose is input that is
    # legal. (Guessing 0 did exactly that — the gate caught it.)
    if "ePatient.15" in messy and rng.random() < profile.boundary_rate:
        bounds = _age_bounds(schema)
        if bounds:
            messy["ePatient.15"] = rng.choice(bounds)

    # 5. Free text a naive consumer mishandles.
    if rng.random() < profile.untidy_text_rate:
        messy["eSituation.04"] = rng.choice(_UNTIDY_TEXT)

    # 6. Identifiers carrying path and query characters. eRecord.01 is
    #    xs:string with NO pattern, so all of this is legal.
    if rng.random() < profile.untidy_id_rate and "eRecord.01" in messy:
        suffix = str(messy["eRecord.01"]).rsplit("-", 1)[-1]
        messy["eRecord.01"] = rng.choice(_UNTIDY_IDS).format(n=suffix)

    return messy
