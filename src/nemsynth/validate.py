"""Self-validation against the vendored NEMSIS XSDs.

The generator validates its OWN output before writing. A generator that emits
invalid NEMSIS teaches its consumer nothing: every downstream finding would be
ambiguous between "generator bug" and "mapper bug", and that ambiguity would
poison the whole exercise. Anything failing this gate is a generator defect.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path

from lxml import etree

SUPPORTED_VERSIONS = ("3.5.0", "3.5.1")
DEFAULT_VERSION = "3.5.0"


@lru_cache(maxsize=4)
def _schema(version: str = DEFAULT_VERSION) -> etree.XMLSchema:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(
            f"unsupported NEMSIS version {version!r}; have {SUPPORTED_VERSIONS}"
        )
    root = resources.files("nemsynth").joinpath(f"schemas/{version}/EMSDataSet_v3.xsd")
    with resources.as_file(root) as path:
        return etree.XMLSchema(etree.parse(str(path)))


def errors(document: bytes, version: str = DEFAULT_VERSION) -> list[str]:
    """Validation errors for a generated document; empty means valid."""
    try:
        tree = etree.fromstring(document).getroottree()
    except etree.XMLSyntaxError as error:
        return [f"not well-formed XML: {error}"]
    schema = _schema(version)
    if schema.validate(tree):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]


class GeneratedInvalid(RuntimeError):
    """The generator produced XSD-invalid NEMSIS — always a generator bug."""

    def __init__(self, problems: list[str]):
        super().__init__(
            f"generated document failed its own XSD gate ({len(problems)} error(s)); "
            f"first: {problems[0] if problems else 'unknown'}"
        )
        self.problems = problems


def ensure_valid(document: bytes, version: str = DEFAULT_VERSION) -> bytes:
    problems = errors(document, version)
    if problems:
        raise GeneratedInvalid(problems)
    return document
