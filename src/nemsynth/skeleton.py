"""Emit a valid NEMSIS document from the schema model plus supplied values.

The inversion that makes scenarios tractable: the schema decides *what must be
present and in what order*, and a scenario decides only *what it has to say*.
Adding a scenario becomes clinical logic instead of schema archaeology, and the
output cannot drift from the standard because its shape is derived from it.

For every required element with no supplied value, in order of preference:

  1. nil + NV, when the element accepts one — the honest answer, and the path
     real exports take constantly. Prefer "Not Applicable" over "Not Recorded":
     for a mandatory element a scenario has nothing to say about, the fact does
     not apply to this call rather than having been forgotten.
  2. the first enumerated value, when the type enumerates one.
  3. a pattern-satisfying literal, for the handful of typed primitives.

Anything left unfillable is raised rather than guessed at, because a document
that is *almost* valid is worse than a loud failure.
"""

from __future__ import annotations

import random
from datetime import datetime

from lxml import etree

from .schema import NV_NOT_APPLICABLE, Node, Schema

NS = "http://www.nemsis.org"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


class Unfillable(RuntimeError):
    """A required element the builder cannot satisfy — a generator bug."""


def _literal_for(schema: Schema, node: Node, rng: random.Random) -> str:
    """A schema-legal value for a required, non-nillable leaf."""
    simple = schema.simple_type(node.type_name) if node.type_name else None
    if simple and simple.enumerations:
        return simple.enumerations[0]

    base = (simple.base if simple else node.type_name) or ""
    if "dateTime" in base or "DateTime" in (node.type_name or ""):
        # NEMSIS mandates a ±hh:mm offset — `Z` is not permitted by the pattern.
        return datetime(2026, 1, 1, 12, 0, 0).strftime("%Y-%m-%dT%H:%M:%S-06:00")
    if "date" in base.lower():
        return "2026-01-01"
    if "decimal" in base or "integer" in base or "int" in base:
        return "1"
    if simple and simple.patterns:
        raise Unfillable(
            f"{node.name}: pattern-constrained type {node.type_name!r} with no "
            "enumeration — the scenario must supply this value explicitly"
        )
    # A last-resort literal satisfies the XSD but says nothing true. Mark it so
    # it is obvious in output and greppable in a corpus: a value that is valid
    # and meaningless is worse than one that is loudly synthetic, because it
    # reads as data. (An identity field reaching here is a scenario bug — see
    # eResponse.01, which contradicted the header until it was supplied.)
    return "SYNTHETIC-UNSPECIFIED"


def _fill(
    parent: etree._Element,
    node: Node,
    schema: Schema,
    values: dict[str, object],
    rng: random.Random,
) -> None:
    """Emit `node` under `parent`, recursing into containers."""
    element = etree.SubElement(parent, f"{{{NS}}}{node.name}")

    if node.is_container:
        for child in node.children:
            supplied = _subtree_has_value(child, values)
            if child.required or supplied:
                _fill(element, child, schema, values, rng)
        return

    if node.name in values:
        element.text = str(values[node.name])
        return

    if node.nv_codes:
        code = NV_NOT_APPLICABLE if NV_NOT_APPLICABLE in node.nv_codes else node.nv_codes[0]
        element.set(f"{{{XSI}}}nil", "true")
        element.set("NV", code)
        return

    element.text = _literal_for(schema, node, rng)


def _subtree_has_value(node: Node, values: dict[str, object]) -> bool:
    """Did the scenario supply anything inside this optional subtree?

    Without this, an optional container holding a supplied value would be
    skipped and the value silently lost — the same class of silent drop this
    whole project exists to prevent."""
    if node.name in values:
        return True
    return any(_subtree_has_value(child, values) for child in node.children)


def build_patient_care_report(
    schema: Schema,
    values: dict[str, object],
    uuid: str,
    rng: random.Random,
) -> etree._Element:
    """A complete, schema-shaped PatientCareReport carrying `values`."""
    node = schema.patient_care_report()
    holder = etree.Element("holder")
    _fill(holder, node, schema, values, rng)
    pcr = holder[0]
    pcr.set("UUID", uuid)
    return pcr


def build_document(
    schema: Schema,
    values: dict[str, object],
    agency: dict[str, str],
    uuid: str,
    rng: random.Random,
    schema_location: str,
) -> bytes:
    """One EMSDataSet containing one PatientCareReport."""
    root = etree.Element(f"{{{NS}}}EMSDataSet", nsmap={None: NS, "xsi": XSI})
    root.set(f"{{{XSI}}}schemaLocation", schema_location)

    header = etree.SubElement(root, f"{{{NS}}}Header")
    demographic = etree.SubElement(header, f"{{{NS}}}DemographicGroup")
    for tag, value in (
        ("dAgency.01", agency["state_id"]),
        ("dAgency.02", agency["number"]),
        ("dAgency.04", agency["state"]),
    ):
        etree.SubElement(demographic, f"{{{NS}}}{tag}").text = value

    header.append(build_patient_care_report(schema, values, uuid, rng))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                          pretty_print=True)
