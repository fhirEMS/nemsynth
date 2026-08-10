"""The self-validation gate. A generator that can emit invalid NEMSIS makes
every downstream finding ambiguous between generator bug and mapper bug."""

import pytest

from nemsynth import validate


def test_invalid_output_is_refused():
    with pytest.raises(validate.GeneratedInvalid) as caught:
        validate.ensure_valid(b"<EMSDataSet>not nemsis</EMSDataSet>")
    assert caught.value.problems


def test_malformed_xml_is_reported_not_raised_as_lxml():
    problems = validate.errors(b"<not xml")
    assert problems and "well-formed" in problems[0]


def test_both_releases_are_vendored():
    assert validate.SUPPORTED_VERSIONS == ("3.5.0", "3.5.1")
    for version in validate.SUPPORTED_VERSIONS:
        assert validate.errors(b"<EMSDataSet/>", version)  # loads the schema


def test_generated_documents_are_valid_and_reproducible():
    """The whole contract in one test: schema-derived shape, self-validated,
    byte-identical for a given seed."""
    from nemsynth.generate import fingerprint, generate_one

    first = generate_one(1)
    assert fingerprint(generate_one(1)) == fingerprint(first)
    assert fingerprint(generate_one(2)) != fingerprint(first)


def test_skeleton_fills_every_mandatory_section():
    """NEMSIS mandates 17 sections; a scenario that mentions three of them must
    still yield a document carrying all 17 — that is the inversion working."""
    import random

    from lxml import etree

    from nemsynth import schema, skeleton

    loaded = schema.load("3.5.0")
    pcr = skeleton.build_patient_care_report(
        loaded, {"ePatient.15": 44}, "11111111-1111-4111-8111-111111111111",
        random.Random(1))
    present = {etree.QName(c).localname for c in pcr}
    required = {c.name for c in loaded.patient_care_report().children if c.required}
    assert required <= present, f"missing mandatory sections: {required - present}"


def test_unsupplied_mandatory_leaves_carry_nv_not_a_guess():
    """Where a scenario says nothing, the document must say 'not applicable' —
    not invent a plausible-looking value."""
    import random

    from nemsynth import schema, skeleton

    doc = skeleton.build_patient_care_report(
        schema.load("3.5.0"), {}, "11111111-1111-4111-8111-111111111111",
        random.Random(1))
    nils = doc.findall(".//*[@NV]")
    assert len(nils) > 20, "expected many NV-marked mandatory elements"
