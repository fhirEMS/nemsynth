"""GNIS codes must stay real, and must stay in the right state.

`CityGnisCode` is a bare `xs:positiveInteger` in the NEMSIS schema, so **any
integer validates**. A made-up code passes every gate this project has and
names a different town, or nowhere. That is the exact failure mode the
generator exists not to produce, so the codes are looked up rather than
invented — and these tests keep them honest afterwards.

The live lookup is opt-in (`NEMSYNTH_VERIFY_GNIS=1`): a unit suite that depends
on a government web service is a suite that fails on a train.
"""

from __future__ import annotations

import os
import re

import pytest

from nemsynth import crew, gnis

USGS = ("https://carto.nationalmap.gov/arcgis/rest/services/"
        "geonames/MapServer/3/query")


def test_a_dozen_places_are_declared():
    assert len(gnis.PLACES) == 12
    assert len({p.gnis for p in gnis.PLACES}) == 12, "duplicate GNIS code"


def test_every_code_looks_like_a_gnis_id():
    for place in gnis.PLACES:
        assert re.fullmatch(r"[1-9][0-9]{5,7}", place.gnis), place


def test_every_place_is_in_the_agency_state():
    """The cross-check that matters. A city in the wrong state is XSD-valid,
    geographically impossible, and invisible without comparing the two."""
    wrong = [p for p in gnis.PLACES if p.state_alpha != gnis.STATE_ALPHA]
    assert wrong == [], f"places outside {gnis.STATE_ALPHA}: {wrong}"


def test_the_station_and_licensure_agree_with_the_table():
    """The station's city, the ANSI state on every address, and the crew's
    state of licensure all come from one place, so they cannot drift apart."""
    assert crew.STATION["city_gnis"] == gnis.STATION_CITY.gnis
    assert crew.STATION["state"] == gnis.ANSI_STATE
    assert crew.STATE_OF_LICENSURE == gnis.ANSI_STATE
    assert gnis.STATION_CITY.state_alpha == gnis.STATE_ALPHA


def test_scene_cities_come_from_the_verified_table():
    import random
    rng = random.Random(1)
    for _ in range(50):
        assert gnis.scene_city(rng).gnis in gnis.BY_GNIS


@pytest.mark.skipif(os.environ.get("NEMSYNTH_VERIFY_GNIS") != "1",
                    reason="set NEMSYNTH_VERIFY_GNIS=1 to re-verify against USGS")
def test_codes_still_resolve_at_usgs():
    """Re-verify against the source. Opt-in, because these are stable
    identifiers and the suite should not need a network."""
    import json
    import urllib.parse
    import urllib.request

    ids = ",".join(p.gnis for p in gnis.PLACES)
    query = urllib.parse.urlencode({
        "where": f"gaz_id IN ({ids})",
        "outFields": "gaz_id,gaz_name,state_alpha",
        "returnGeometry": "false",
        "f": "json",
    })
    with urllib.request.urlopen(f"{USGS}?{query}", timeout=60) as response:
        payload = json.load(response)
    found = {str(f["attributes"]["gaz_id"]): f["attributes"]
             for f in payload.get("features", [])}
    for place in gnis.PLACES:
        assert place.gnis in found, f"{place.name} ({place.gnis}) not found at USGS"
        assert found[place.gnis]["state_alpha"] == place.state_alpha, (
            f"{place.name} moved state: {found[place.gnis]['state_alpha']}")


def test_the_gazetteer_covers_every_place_this_package_emits():
    """A consumer resolving GNIS -> name needs the names for the places we
    actually generate. If the table grows and the gazetteer does not, the
    resolved path silently stops covering the new ones."""
    g = gnis.gazetteer()
    assert set(g) == {p.gnis for p in gnis.PLACES}
    assert all(name and not name.isdigit() for name in g.values())
    assert g["1454997"] == "Salt Lake City"
