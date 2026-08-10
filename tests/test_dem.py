"""The DEMDataSet — the agency roster the patient records point at.

NEMSIS is two documents joined only by agency identity. A PCR header carries
`dAgency.01/.02/.04` and nothing else, so the agency's **name** exists solely
in the DEM. Generating only EMSDataSets leaves that join, and the named
`Organization` a consumer builds from it, permanently untested.

Two properties are asserted throughout: the roster must be valid against the
DEM schema (a *different* root from EMSDataSet), and it must describe the same
agency the patient records do — a roster that validates perfectly and joins to
nothing is worse than no roster, because it looks like coverage.
"""

from __future__ import annotations

import re

import pytest
from lxml import etree

from nemsynth import validate
from nemsynth.skeleton import NS, XSI
from nemsynth.dem import AGENCY, generate_dem
from nemsynth.generate import generate_one


def text_of(document: bytes, tag: str) -> str | None:
    """The element's text, or None when it is nil or absent.

    Parsed rather than matched with a regex: a self-closing nil element is
    exactly the shape these tests are about, and `[^>]*` happily swallows the
    `/` of `<dAgency.03 ... />` and then captures the following whitespace as
    if it were content. That is a bug in the test, reported as a bug in the
    generator — the worst kind."""
    root = etree.fromstring(document)
    found = root.find(f".//{{{NS}}}{tag}")
    if found is None or found.get(f"{{{XSI}}}nil") in ("true", "1"):
        return None
    return (found.text or "").strip() or None


def test_dem_validates_against_the_dem_schema():
    """Against DEMDataSet_v3.xsd, not the EMS root: a DEM checked against the
    wrong schema fails for a reason that tells you nothing."""
    assert validate.errors(generate_dem(seed=1), dataset="DEMDataSet") == []


def test_dem_is_not_valid_as_an_emsdataset():
    """The two roots are genuinely different. Without this, `dataset=` could be
    ignored entirely and every test here would still pass."""
    assert validate.errors(generate_dem(seed=1), dataset="EMSDataSet")


@pytest.mark.parametrize("version", validate.SUPPORTED_VERSIONS)
def test_dem_generates_for_every_supported_release(version):
    assert validate.errors(generate_dem(seed=3, version=version),
                           version=version, dataset="DEMDataSet") == []


def test_roster_describes_the_same_agency_as_the_records():
    """The join. A roster for an agency that appears in no patient record is
    XSD-valid and useless."""
    dem = generate_dem(seed=1)
    pcr = generate_one(seed=1, scenario="chest-pain", profile="clean")
    for tag, expected in (("dAgency.01", AGENCY["state_id"]),
                          ("dAgency.02", AGENCY["number"]),
                          ("dAgency.04", AGENCY["state"])):
        assert text_of(dem, tag) == expected
    # The PCR header carries the same identity, which is the only thing
    # connecting the two documents.
    assert text_of(pcr, "dAgency.02") == AGENCY["number"]


def test_service_area_codes_are_geographically_consistent():
    """An ANSI county code begins with its state code. Picking them
    independently yields a roster serving a county in another state — valid
    against the schema, impossible on a map."""
    dem = generate_dem(seed=1)
    state, county = text_of(dem, "dAgency.05"), text_of(dem, "dAgency.06")
    assert county.startswith(state)
    assert len(state) == 2 and len(county) == 5


def test_named_agency_carries_a_name():
    assert text_of(generate_dem(seed=1), "dAgency.03")


def test_unnamed_agency_is_absent_not_empty():
    """The correctness trap. An agency that reports no name must be nil+NV, so
    a consumer keeps its data-absent path and withholds the US Core claim,
    rather than asserting a name of ''."""
    dem = generate_dem(seed=2, unnamed=True)
    element = re.search(rb"<dAgency\.03[^>]*>", dem).group(0)
    assert b'nil="true"' in element
    assert b"NV=" in element
    assert text_of(dem, "dAgency.03") is None


def test_required_attributes_are_emitted_from_the_schema():
    """The DEM hangs a required UUID on almost every group and a timeStamp on
    the report. The document is invalid without them however correct its
    element content is, so the skeleton derives them from the schema rather
    than each caller setting them by hand."""
    dem = generate_dem(seed=1)
    assert re.search(rb"<DemographicReport[^>]+timeStamp=", dem)
    uuids = re.findall(rb'UUID="([^"]+)"', dem)
    assert len(uuids) >= 5, "group UUIDs were not emitted"
    assert len(set(uuids)) == len(uuids), "group UUIDs must be distinct"


def test_dem_is_reproducible():
    assert generate_dem(seed=7) == generate_dem(seed=7)
    assert generate_dem(seed=7) != generate_dem(seed=8)


def test_numeric_literals_respect_their_lower_bound():
    """dConfiguration.07 has minInclusive=100000. A bare "1" fallback was
    XSD-invalid — the same class of defect as guessing an out-of-range age,
    and caught the same way, by the self-validation gate."""
    value = text_of(generate_dem(seed=1), "dConfiguration.07")
    if value is not None:      # nil when the schema allows NV
        assert int(value) >= 100000
