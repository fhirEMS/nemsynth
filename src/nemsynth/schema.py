"""A navigable model of the NEMSIS XSD.

Hand-deriving element sequences does not work: NEMSIS mandates 17 sections per
PatientCareReport, many with deeply nested required children, and every fix
surfaces another requirement. So read the schema instead of guessing at it —
then a document is correct by construction rather than by iteration, and it
cannot drift from the standard because it is derived from it.

The model is intentionally small: enough to emit a valid document, not a
general XSD implementation. It captures, per element, the things generation
actually needs — order, whether it is required, whether it is a container or a
leaf, whether it may be nil, which NV codes it accepts, and what values its
type permits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

from lxml import etree

XS = "http://www.w3.org/2001/XMLSchema"


@dataclass
class Node:
    """One element in the schema tree."""

    name: str
    min_occurs: int
    max_occurs: int          # -1 = unbounded
    nillable: bool
    nv_codes: tuple[str, ...]   # NV values this element accepts (may be empty)
    type_name: str | None       # simple type backing a leaf
    children: list["Node"] = field(default_factory=list)

    @property
    def is_container(self) -> bool:
        return bool(self.children)

    @property
    def required(self) -> bool:
        return self.min_occurs >= 1


@dataclass
class SimpleType:
    """What a leaf may contain."""

    name: str
    base: str | None
    enumerations: tuple[str, ...]
    patterns: tuple[str, ...]

    @property
    def is_enumerated(self) -> bool:
        return bool(self.enumerations)


#: NV codes, by meaning. "Not Applicable" is the honest default when a scenario
#: has nothing to say about a mandatory element — the fact was not withheld or
#: forgotten, it simply does not apply to this call.
NV_NOT_APPLICABLE = "7701001"
NV_NOT_RECORDED = "7701003"


class Schema:
    """The parsed NEMSIS schema set for one release."""

    def __init__(self, version: str = "3.5.0"):
        self.version = version
        self._complex: dict[str, etree._Element] = {}
        self._simple: dict[str, etree._Element] = {}
        self._elements: dict[str, etree._Element] = {}
        self._load()

    def _load(self) -> None:
        root = resources.files("nemsynth").joinpath(f"schemas/{self.version}")
        with resources.as_file(root) as directory:
            for path in sorted(directory.glob("*.xsd")):
                tree = etree.parse(str(path))
                for node in tree.getroot():
                    name = node.get("name")
                    if name is None:
                        continue
                    tag = etree.QName(node).localname
                    if tag == "complexType":
                        self._complex.setdefault(name, node)
                    elif tag == "simpleType":
                        self._simple.setdefault(name, node)
                    elif tag == "element":
                        # EMSDataSet is a top-level ELEMENT, not a named type,
                        # and PatientCareReport lives inside it — so the root
                        # of everything we generate is only reachable here.
                        self._elements.setdefault(name, node)

    # -- simple types ------------------------------------------------------
    @lru_cache(maxsize=None)
    def simple_type(self, name: str) -> SimpleType | None:
        node = self._simple.get(name)
        if node is None:
            return None
        restriction = node.find(f"{{{XS}}}restriction")
        if restriction is None:
            # A union (e.g. "a number OR the literal High/Low") — take the
            # members' enumerations so a generated value is always legal.
            union = node.find(f"{{{XS}}}union")
            members = (union.get("memberTypes") or "").split() if union is not None else []
            enums: list[str] = []
            for member in members:
                inner = self.simple_type(member)
                if inner:
                    enums.extend(inner.enumerations)
            return SimpleType(name, None, tuple(enums), ())
        return SimpleType(
            name,
            restriction.get("base"),
            tuple(e.get("value") for e in restriction.findall(f"{{{XS}}}enumeration")),
            tuple(p.get("value") for p in restriction.findall(f"{{{XS}}}pattern")),
        )

    # -- element tree ------------------------------------------------------
    def _nv_codes(self, element: etree._Element) -> tuple[str, ...]:
        """NV values this element's inline type permits, resolved through the
        union of NV.* member types the schema declares."""
        codes: list[str] = []
        for attribute in element.iter(f"{{{XS}}}attribute"):
            if attribute.get("name") != "NV":
                continue
            for union in attribute.iter(f"{{{XS}}}union"):
                for member in (union.get("memberTypes") or "").split():
                    inner = self.simple_type(member)
                    if inner:
                        codes.extend(inner.enumerations)
        return tuple(dict.fromkeys(codes))

    def _sequence_of(self, element: etree._Element) -> etree._Element | None:
        """The xs:sequence defining a container's children, inline or named."""
        inline = element.find(f"{{{XS}}}complexType/{{{XS}}}sequence")
        if inline is not None:
            return inline
        type_name = element.get("type")
        if type_name and type_name in self._complex:
            return self._complex[type_name].find(f"{{{XS}}}sequence")
        return None

    def _base_type(self, element: etree._Element) -> str | None:
        extension = element.find(
            f"{{{XS}}}complexType/{{{XS}}}simpleContent/{{{XS}}}extension"
        )
        if extension is not None:
            return extension.get("base")
        return element.get("type")

    def _node(self, element: etree._Element, depth: int = 0) -> Node:
        max_raw = element.get("maxOccurs", "1")
        node = Node(
            name=element.get("name"),
            min_occurs=int(element.get("minOccurs", "1")),
            max_occurs=-1 if max_raw == "unbounded" else int(max_raw),
            nillable=element.get("nillable") == "true",
            nv_codes=self._nv_codes(element),
            type_name=self._base_type(element),
        )
        sequence = self._sequence_of(element)
        if sequence is not None and depth < 8:  # guard against pathological nesting
            for child in sequence.findall(f"{{{XS}}}element"):
                node.children.append(self._node(child, depth + 1))
        return node

    def _find_declaration(self, name: str) -> etree._Element:
        pools = (self._elements.values(), self._complex.values())
        for pool in pools:
            for candidate in pool:
                if candidate.get("name") == name and etree.QName(candidate).localname == "element":
                    return candidate
                for element in candidate.iter(f"{{{XS}}}element"):
                    if element.get("name") == name:
                        return element
        raise LookupError(f"{name} not found in the schema set")

    @lru_cache(maxsize=4)
    def patient_care_report(self) -> Node:
        """The PatientCareReport subtree — the thing a generator must fill."""
        return self._node(self._find_declaration("PatientCareReport"))

    @lru_cache(maxsize=4)
    def demographic_group(self) -> Node:
        """The Header's DemographicGroup (agency identity)."""
        return self._node(self._find_declaration("DemographicGroup"))


@lru_cache(maxsize=4)
def load(version: str = "3.5.0") -> Schema:
    return Schema(version)
