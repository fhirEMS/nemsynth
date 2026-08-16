"""The default crew.

NEMSIS splits a crew member across BOTH datasets, and the standard names the
join itself: `eCrew.01` is defined as "The state certification/licensure ID
number assigned to the crew member", and `dPersonnel.23` is "EMS Personnel's
State's Licensure ID Number". The certification number IS the key.

  * the PCR's `eCrew.CrewGroup` carries `.01` Crew Member ID, `.02` Level and
    `.03` Response Role — and no name at all;
  * the DEM's `dPersonnel.PersonnelGroup` carries the name, the licensure id
    that matches `eCrew.01`, and the certification level.

That is the same shape as the agency: the identity is in the record, the human
detail is in the roster. A consumer that has only the PCR can tell you a
paramedic ran the call and not who they were, which is exactly why the
roster-pairing this package generates matters.

These people are invented, and the certification numbers are not real. The
names are deliberate stand-ins rather than the generic pools used elsewhere,
because a crew that is stable across a corpus is easier to reason about when
you are chasing a defect through it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gnis import ANSI_STATE, STATION_CITY

#: eCrew.02 Crew Member Level
LEVEL_PARAMEDIC = "9925007"          # Paramedic
LEVEL_EMT = "9925005"                # Emergency Medical Technician (EMT)

#: dPersonnel.24 State EMS Certification Licensure Level mirrors eCrew.02.
STATE_OF_LICENSURE = ANSI_STATE      # matches the agency's ANSI state code

#: eCrew.03 Crew Member Response Role
ROLE_PRIMARY_AT_SCENE = "2403011"    # Primary Patient Caregiver-At Scene
ROLE_OTHER_AT_SCENE = "2403007"      # Other Patient Caregiver-At Scene
ROLE_DRIVER_TRANSPORT = "2403003"    # Driver/Pilot-Transport


@dataclass(frozen=True)
class CrewMember:
    """One crew member, spanning both datasets.

    `crew_id` is the join: it is `eCrew.01` in the PCR and
    `dPersonnel.NN` in the roster, and a mismatch between the two is the
    defect this pairing exists to make visible."""

    crew_id: str          # state certification number
    last: str
    first: str
    level: str            # eCrew.02
    role: str             # eCrew.03
    phone: str            # dPersonnel.09


#: The default crew. One paramedic running the call, two EMTs assisting —
#: which also gives the level/role split real values to exercise: the levels
#: differ (Paramedic vs EMT) and so do the roles (primary vs other vs driver),
#: so a consumer that collapses the two has somewhere to go wrong.
DEFAULT_CREW: tuple[CrewMember, ...] = (
    CrewMember("1911", "Albert", "Chad", LEVEL_PARAMEDIC,
               ROLE_PRIMARY_AT_SCENE, "801-555-0101"),
    CrewMember("09112", "Ritirato", "Bobette", LEVEL_EMT,
               ROLE_OTHER_AT_SCENE, "801-555-0112"),
    CrewMember("09109", "Capo", "Josephina", LEVEL_EMT,
               ROLE_DRIVER_TRANSPORT, "801-555-0109"),
)

#: A shared, invented station address. C-CDA's US Realm Header makes address
#: and telecom SHALL on the document's author, and NEMSIS has homes for both.
#: The 555 prefix is reserved for fiction and the street does not exist, so
#: nothing here can collide with a real person or place.
#: NEMSIS codes these rather than spelling them: city is a GNIS code, state is
#: the two-digit ANSI code, and PhoneNumber is pattern-checked as a full NANP
#: number — a bare "555-0100" is invalid. 555-01xx with a real area code is the
#: range reserved for fiction, so these dial nowhere.
STATION = {
    "street": "1 Synthetic Way",
    # Both from the USGS-verified table, so the GNIS code and the ANSI state
    # cannot drift apart — see gnis.py and its cross-check test.
    "city_gnis": STATION_CITY.gnis,
    "state": ANSI_STATE,
    "zip": "84101",
    "phone": "801-555-0100",
    "email": "dispatch@example.org",
}


def pcr_crew_groups(crew: tuple[CrewMember, ...] = DEFAULT_CREW) -> list[dict]:
    """`eCrew.CrewGroup` instances for a PatientCareReport."""
    return [
        {"eCrew.01": m.crew_id, "eCrew.02": m.level, "eCrew.03": m.role}
        for m in crew
    ]


def dem_personnel_groups(crew: tuple[CrewMember, ...] = DEFAULT_CREW) -> list[dict]:
    """`dPersonnel.PersonnelGroup` instances for the agency roster."""
    # Middle name is deliberately NOT supplied: an empty string underruns the
    # schema's minLength, and "" is not the same fact as "not recorded". Left
    # unsupplied, the skeleton emits nil+NV, which is what a real export does.
    return [
        {
            "dPersonnel.01": m.last,
            "dPersonnel.02": m.first,
            # The join back to eCrew.01. A roster whose licensure ids do not
            # match the records is XSD-valid and joins to nothing — the same
            # trap as an agency roster for an agency that never ran a call.
            "dPersonnel.04": STATION["street"],
            "dPersonnel.05": STATION["city_gnis"],
            "dPersonnel.06": STATION["state"],
            "dPersonnel.07": STATION["zip"],
            "dPersonnel.09": m.phone,
            "dPersonnel.22": STATE_OF_LICENSURE,
            "dPersonnel.23": m.crew_id,
            "dPersonnel.24": m.level,
        }
        for m in crew
    ]


def dem_agency_contact() -> dict:
    """`dContact` values for the agency — the CDA custodian's telecom/addr."""
    return {
        "dContact.02": "Dispatch",
        "dContact.03": "Agency",
        "dContact.05": STATION["street"],
        "dContact.06": STATION["city_gnis"],
        "dContact.07": STATION["state"],
        "dContact.08": STATION["zip"],
        "dContact.10": STATION["phone"],
        "dContact.11": STATION["email"],
    }
