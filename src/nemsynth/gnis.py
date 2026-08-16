"""GNIS city codes, verified against USGS.

NEMSIS stores a city as a **GNIS feature id**, not a name: `dPersonnel.05`,
`dContact.06`, `eScene.17` and friends are all `CityGnisCode`, whose schema
type is a bare `xs:positiveInteger`. Any integer validates. That is exactly the
shape of defect this generator exists to avoid producing — a made-up code would
pass every gate and name a different town, or nowhere at all.

So these are not invented. Each was looked up in the USGS National Map
Geographic Names service (`geonames/MapServer/3`, Populated Places) and carries
the state the service returned, which `test_gnis.py` cross-checks against the
ANSI state code the agency uses. A code that drifts to another state, or a
state code that stops matching, fails the suite.

    https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/3

Verified 2026-08-14.
"""

from __future__ import annotations

from dataclasses import dataclass

#: ANSI state code for Utah, which is the state the default agency serves.
#: The GNIS entries below all sit inside it, and the cross-check test is what
#: keeps that true rather than a comment claiming it.
ANSI_STATE = "49"
STATE_ALPHA = "UT"


@dataclass(frozen=True)
class Place:
    gnis: str
    name: str
    state_alpha: str
    county: str


#: Twelve Utah places, each looked up by name and returned with its state.
PLACES: tuple[Place, ...] = (
    Place("1454997", "Salt Lake City", "UT", "Salt Lake"),
    Place("1444661", "Provo", "UT", "Utah"),
    Place("1444049", "Ogden", "UT", "Weber"),
    Place("1455905", "Sandy City", "UT", "Salt Lake"),
    Place("1444110", "Orem", "UT", "Utah"),
    Place("1437843", "West Valley City", "UT", "Salt Lake"),
    Place("1442459", "Layton", "UT", "Davis"),
    Place("1442849", "Logan", "UT", "Cache"),
    Place("1455098", "Saint George", "UT", "Washington"),
    Place("1443742", "Murray", "UT", "Salt Lake"),
    Place("1427473", "Draper", "UT", "Salt Lake"),
    Place("1433590", "Tooele", "UT", "Tooele"),
)

BY_GNIS = {p.gnis: p for p in PLACES}

#: The station's own city. Kept explicit rather than PLACES[0] so a reordering
#: of the table cannot silently relocate the agency.
STATION_CITY = BY_GNIS["1454997"]


def gazetteer() -> dict[str, str]:
    """GNIS feature id -> city name, for a consumer that must resolve one.

    NEMSIS stores the id; FHIR's `Address.city` and CDA's `<city>` want the
    name, and neither standard has a coded-place element. A consumer therefore
    needs a gazetteer or it has to leave the city absent — so this package
    hands over the names for exactly the places it generates, which is what
    makes the resolved path testable at all.

    It is deliberately NOT a general gazetteer: twelve places, the ones this
    generator emits. Shipping GNIS in full is USGS's job, not this project's.
    """
    return {place.gnis: place.name for place in PLACES}


def scene_city(rng) -> Place:
    """A place for a scene address. Varied so a corpus is not all one town."""
    return rng.choice(PLACES)
