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

#: eCrew.02 Crew Member Level
LEVEL_PARAMEDIC = "9925007"          # Paramedic
LEVEL_EMT = "9925005"                # Emergency Medical Technician (EMT)

#: dPersonnel.24 State EMS Certification Licensure Level mirrors eCrew.02.
STATE_OF_LICENSURE = "49"            # matches the agency's ANSI state code

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


#: The default crew. One paramedic running the call, two EMTs assisting —
#: which also gives the level/role split real values to exercise: the levels
#: differ (Paramedic vs EMT) and so do the roles (primary vs other vs driver),
#: so a consumer that collapses the two has somewhere to go wrong.
DEFAULT_CREW: tuple[CrewMember, ...] = (
    CrewMember("1911", "Albert", "Chad", LEVEL_PARAMEDIC, ROLE_PRIMARY_AT_SCENE),
    CrewMember("09112", "Ritirato", "Bobette", LEVEL_EMT, ROLE_OTHER_AT_SCENE),
    CrewMember("09109", "Capo", "Josephina", LEVEL_EMT, ROLE_DRIVER_TRANSPORT),
)


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
            "dPersonnel.22": STATE_OF_LICENSURE,
            "dPersonnel.23": m.crew_id,
            "dPersonnel.24": m.level,
        }
        for m in crew
    ]
