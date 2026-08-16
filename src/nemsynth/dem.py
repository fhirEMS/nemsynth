"""DEMDataSet: the agency roster that the patient records point at.

NEMSIS is two documents, not one. `EMSDataSet` carries patient care reports;
`DEMDataSet` carries the agency, its personnel, vehicles and the facilities it
transports to. They are joined only by the agency identity — a PCR header
carries `dAgency.01/.02/.04` and nothing else, so **the agency's NAME exists
only in the DEM**.

That join is the reason this module exists. A consumer building a FHIR
`Organization` has no name to give it from the PCR alone, and US Core requires
one; without a DEM it must honestly withhold the claim. Generating only
EMSDataSets therefore leaves that whole path — the pairing, the lookup, and the
resource it produces — permanently untested.

The identity here is deliberately the SAME agency the EMS side generates, so a
DEM and a corpus from this package pair up. A roster describing an agency that
appears in no patient record would validate perfectly and join to nothing.
"""

from __future__ import annotations

import random

from lxml import etree

from . import messiness, schema, skeleton, validate
from .crew import dem_agency_contact, dem_personnel_groups
from .skeleton import NS, XSI, Absent

#: The agency every generated document belongs to. Shared with `generate.py`
#: rather than repeated: two literals that must agree are two literals that
#: eventually will not.
AGENCY = {"state_id": "SY-9901", "number": "9901", "state": "49"}

#: ANSI codes for the agency's service area. A county code BEGINS with its
#: state code (49 = Utah, 49035 = Salt Lake County), so these cannot be picked
#: independently — a roster serving a county in another state is XSD-valid and
#: geographically impossible.
_STATE = AGENCY["state"]
_COUNTY = "49035"
assert _COUNTY.startswith(_STATE), "county code must sit inside its state"

_SCHEMA_LOCATION = {
    "3.5.0": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/DEMDataSet_v3.xsd",
    "3.5.1": "http://www.nemsis.org https://nemsis.org/media/nemsis_v3/release-3.5.1/XSDs/NEMSIS_XSDs/DEMDataSet_v3.xsd",
}

#: Obviously-invented agency and facility names. This is a structural
#: generator, not a directory of real services, and a plausible-looking real
#: agency name in synthetic data is a liability rather than realism.
_AGENCY_NAMES = [
    "Synthetic Valley EMS",
    "Example County Ambulance Authority",
    "Testfield Fire & Rescue",
    "Nemsynth Regional Medical Transport",
]
_FACILITIES = [
    ("Synthetic Valley General Hospital", "SYN-001"),
    ("Example County Trauma Center", "SYN-002"),
    ("Testfield Community Hospital", "SYN-003"),
    ("Nemsynth Children's Medical Center", "SYN-004"),
]


def _report_values(rng: random.Random, name: str | None) -> dict:
    """One DemographicReport's supplied values.

    `name` of None means dAgency.03 is nil+NV — an agency that reports no name.
    That is legal, it happens, and it is the case a consumer most easily gets
    wrong by treating the absence as an empty string instead of as absent.
    """
    values: dict[str, object] = {
        "dAgency.01": AGENCY["state_id"],
        "dAgency.02": AGENCY["number"],
        "dAgency.04": AGENCY["state"],
        "dAgency.03": name if name is not None else Absent("7701003"),
        # Service area. Pattern-constrained with no enumeration, so the
        # skeleton refuses to guess them — correctly: an invented ANSI code
        # would be structurally valid and name nowhere.
        "dAgency.05": _STATE,
        "dAgency.06": _COUNTY,
        "dConfiguration.01": _STATE,
    }
    # The personnel roster. A PCR names crew members by id and nothing else, so
    # without this a consumer can say a paramedic ran the call but not who.
    values["dPersonnel.PersonnelGroup"] = dem_personnel_groups()
    values.update(dem_agency_contact())

    facility, code = rng.choice(_FACILITIES)
    values["dFacility.02"] = facility
    values["dFacility.03"] = code
    return values


def generate_dem(seed: int, version: str = "3.5.0", profile: str = "clean",
                 unnamed: bool = False) -> bytes:
    """One DEMDataSet for the agency the EMS corpus belongs to.

    `unnamed` nils dAgency.03, which is the branch a consumer must not collapse
    into an empty name — the resulting Organization has to withhold its US Core
    claim rather than assert a name it does not have.
    """
    rng = random.Random(seed)
    model = schema.load(version)
    name = None if unnamed else rng.choice(_AGENCY_NAMES)
    values = _report_values(rng, name)
    values = messiness.apply(values, rng, messiness.PROFILES[profile], model)

    root = etree.Element(f"{{{NS}}}DEMDataSet", nsmap={None: NS, "xsi": XSI})
    root.set(f"{{{XSI}}}schemaLocation", _SCHEMA_LOCATION[version])
    holder = etree.Element("holder")
    skeleton._fill(holder, model.demographic_report(), model, values, rng)
    root.append(holder[0])

    document = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                              pretty_print=True)
    return validate.ensure_valid(document, version, dataset="DEMDataSet")
