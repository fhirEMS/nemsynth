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
