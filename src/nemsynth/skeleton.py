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
import uuid
from datetime import datetime

from lxml import etree

from .schema import NV_NOT_APPLICABLE, Node, Schema


class Absent:
    """Emit this element as nil + a SPECIFIC NV code.

    A scenario or the messiness engine uses this to say *why* a value is
    missing — "not recorded" is a different fact from "not applicable", and a
    consumer that flattens the two is losing information the standard went out
    of its way to carry."""

    __slots__ = ("code",)

    def __init__(self, code: str):
        self.code = code


class Negative:
    """Emit this element as nil + a PN (pertinent negative) code.

    "No known drug allergy" is an assertion, not a gap. Generating these is the
    only way to exercise a consumer's negation handling."""

    __slots__ = ("code",)

    def __init__(self, code: str):
        self.code = code

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
        # Honour the type's own bounds. Returning a bare "1" ignored
        # minInclusive and produced XSD-invalid output on any element with a
        # floor (dConfiguration.07 starts at 100000) — the same class of defect
        # as guessing an out-of-range age.
        if simple and simple.min_inclusive:
            return simple.min_inclusive
        if simple and simple.max_inclusive and simple.max_inclusive.lstrip("-").isdigit():
            if int(simple.max_inclusive) < 1:
                return simple.max_inclusive
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
    #
    # Clamp to the type's own maxLength: the full marker is 21 characters and
    # plenty of NEMSIS string types are shorter, so an unclamped literal is
    # itself XSD-invalid. Truncated, it stays greppable.
    literal = "SYNTHETIC-UNSPECIFIED"
    limit = simple.max_length if simple else None
    return literal[:limit] if limit else literal


def _fill(
    parent: etree._Element,
    node: Node,
    schema: Schema,
    values: dict[str, object],
    rng: random.Random,
) -> None:
    """Emit `node` under `parent`, recursing into containers."""
    element = etree.SubElement(parent, f"{{{NS}}}{node.name}")
    _set_required_attributes(element, node, rng)

    if node.is_container:
        for child in node.children:
            # A repeating group: the scenario supplies a LIST of instance maps,
            # one per occurrence. Serial vitals, several medications, several
            # procedures — the shape of any real transport, and the shape a
            # consumer must turn into N resources sharing the group's .01
            # timestamp. A generator that can only emit one instance can never
            # test that rule at all.
            instances = values.get(child.name)
            if isinstance(instances, list) and child.is_container:
                if child.max_occurs != -1 and len(instances) > child.max_occurs:
                    raise Unfillable(
                        f"{child.name}: {len(instances)} instances supplied but "
                        f"the schema allows at most {child.max_occurs}"
                    )
                for instance in instances:
                    # Instance values shadow the document-wide ones, so a group
                    # can carry its own timestamp while still seeing shared
                    # context.
                    _fill(element, child, schema, {**values, **instance}, rng)
                continue
            if child.required or _subtree_has_value(child, values):
                _fill(element, child, schema, values, rng)
        return

    supplied = values.get(node.name)
    if isinstance(supplied, Absent):
        code = supplied.code if supplied.code in node.nv_codes else (
            node.nv_codes[0] if node.nv_codes else None)
        if code is None:
            raise Unfillable(f"{node.name} accepts no NV code")
        element.set(f"{{{XSI}}}nil", "true")
        element.set("NV", code)
        return
    if isinstance(supplied, Negative):
        code = supplied.code if supplied.code in node.pn_codes else (
            node.pn_codes[0] if node.pn_codes else None)
        if code is None:
            raise Unfillable(f"{node.name} accepts no PN code")
        element.set(f"{{{XSI}}}nil", "true")
        element.set("PN", code)
        return
    if node.name in values:
        element.text = str(supplied)
        return

    if node.nv_codes:
        code = NV_NOT_APPLICABLE if NV_NOT_APPLICABLE in node.nv_codes else node.nv_codes[0]
        element.set(f"{{{XSI}}}nil", "true")
        element.set("NV", code)
        return

    element.text = _literal_for(schema, node, rng)


def _set_required_attributes(element: etree._Element, node: Node,
                             rng: random.Random) -> None:
    """Fill attributes the schema marks required.

    The DEMDataSet hangs a required UUID on almost every group, and the
    document is invalid without them however correct its element content is.
    Deriving them from the schema rather than hand-setting them per caller
    keeps this working for any group added in a future release.
    """
    for name, type_name in node.attributes:
        if element.get(name) is not None:
            continue
        if "UUID" in name or "UUID" in type_name:
            element.set(name, _uuid_from(rng))
        elif "DateTime" in type_name:
            element.set(name, datetime(2026, 1, 1, 12, 0, 0)
                        .strftime("%Y-%m-%dT%H:%M:%S-06:00"))
        elif "date" in type_name.lower():
            element.set(name, "2026-01-01")
        else:
            element.set(name, "SYNTHETIC")


def _uuid_from(rng: random.Random) -> str:
    """A UUID from the seeded RNG, so a seed reproduces the document exactly."""
    return str(uuid.UUID(bytes=bytes(rng.getrandbits(8) for _ in range(16)),
                         version=4))


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


def build_dataset(
    schema: Schema,
    reports: list[tuple[dict[str, object], str]],
    agency: dict[str, str],
    rng: random.Random,
    schema_location: str,
) -> bytes:
    """One EMSDataSet carrying N PatientCareReports.

    N > 1 is a mass-casualty incident: several patients from one scene, sharing
    the incident but each with their own chart. It is also the shape that
    catches a consumer which assumes one report per file — a reasonable-looking
    assumption that silently discards every patient but the first.
    """
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

    for values, uuid in reports:
        header.append(build_patient_care_report(schema, values, uuid, rng))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                          pretty_print=True)


def build_document(
    schema: Schema,
    values: dict[str, object],
    agency: dict[str, str],
    uuid: str,
    rng: random.Random,
    schema_location: str,
) -> bytes:
    """One EMSDataSet containing one PatientCareReport."""
    return build_dataset(schema, [(values, uuid)], agency, rng, schema_location)
