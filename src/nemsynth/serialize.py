"""Sampled call -> NEMSIS EMSDataSet XML.

Kept apart from the scenarios so clinical logic can be read and tested without
XML in view, and so element ordering — which the XSD enforces as a sequence —
lives in exactly one place.

Nothing here is written to disk without passing `validate.ensure_valid()`.
"""

from __future__ import annotations

from lxml import etree

NS = "http://www.nemsis.org"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
_SCHEMA_LOCATION = {
    "3.5.0": f"{NS} https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
    "3.5.1": f"{NS} https://nemsis.org/media/nemsis_v3/release-3.5.1/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd",
}


def _el(parent, tag: str, text=None, **attrs):
    node = etree.SubElement(parent, f"{{{NS}}}{tag}")
    for key, value in attrs.items():
        if key == "nil":
            node.set(f"{{{XSI}}}nil", value)
        else:
            node.set(key, value)
    if text is not None:
        node.text = str(text)
    return node


def _section(pcr, name):
    return etree.SubElement(pcr, f"{{{NS}}}{name}")


def build_document(call: dict, meta: dict, version: str = "3.5.0") -> bytes:
    """One PatientCareReport inside a complete EMSDataSet."""
    root = etree.Element(
        f"{{{NS}}}EMSDataSet", nsmap={None: NS, "xsi": XSI}
    )
    root.set(f"{{{XSI}}}schemaLocation", _SCHEMA_LOCATION[version])

    header = _el(root, "Header")
    demographic = _el(header, "DemographicGroup")
    _el(demographic, "dAgency.01", meta["agency_state_id"])
    _el(demographic, "dAgency.02", meta["agency_number"])
    _el(demographic, "dAgency.04", meta["state"])

    pcr = etree.SubElement(header, f"{{{NS}}}PatientCareReport")
    pcr.set("UUID", meta["uuid"])

    # Element ORDER is an XSD sequence, and group wrappers are mandatory —
    # both mirrored from a known-valid document rather than re-derived, with
    # validate.ensure_valid() as the backstop.
    record = _section(pcr, "eRecord")
    _el(record, "eRecord.01", meta["pcr_number"])
    software = _el(record, "eRecord.SoftwareApplicationGroup")
    _el(software, "eRecord.02", "fhirEMS")
    _el(software, "eRecord.03", "nemsynth")
    _el(software, "eRecord.04", meta["generator_version"])

    response = _section(pcr, "eResponse")
    agency = _el(response, "eResponse.AgencyGroup")
    _el(agency, "eResponse.01", meta["agency_number"])
    _el(response, "eResponse.03", meta["agency_number"])
    _el(response, "eResponse.04", "9903001")   # Agency type: EMS
    service = _el(response, "eResponse.ServiceGroup")
    _el(service, "eResponse.05", call["service_type"])
    _el(response, "eResponse.07", "2207019")
    _el(response, "eResponse.15", call["level_of_care"])

    dispatch = _section(pcr, "eDispatch")
    _el(dispatch, "eDispatch.01", meta["dispatch_reason"])
    _el(dispatch, "eDispatch.02", "2302001")

    times = _section(pcr, "eTimes")
    # .01/.03/.05/.06/.07/.09/.11/.12/.13 are all REQUIRED by the sequence, so
    # a refusal (no transport leg) carries nil+NV rather than omitting them —
    # which is exactly the NV path a consumer must handle.
    required_order = [
        ("eTimes.01", call["times"]["psap"]),
        ("eTimes.03", call["times"]["dispatch_notified"]),
        ("eTimes.05", call["times"]["en_route"]),
        ("eTimes.06", call["times"]["on_scene"]),
        ("eTimes.07", call["times"]["at_patient"]),
        ("eTimes.09", call["times"]["depart_scene"]),
        ("eTimes.11", call["times"]["at_destination"]),
        ("eTimes.12", call["times"]["transfer_of_care"]),
        ("eTimes.13", call["times"]["back_in_service"]),
    ]
    for tag, value in required_order:
        if value is None:
            _el(times, tag, None, nil="true", NV="7701001")  # Not Applicable
        else:
            _el(times, tag, value)

    patient = _section(pcr, "ePatient")
    _el(patient, "ePatient.01", meta["pcr_number"])
    names = _el(patient, "ePatient.PatientNameGroup")
    _el(names, "ePatient.02", meta["family_name"])
    _el(names, "ePatient.03", meta["given_name"])
    _el(patient, "ePatient.14", "2514009")     # Race: White
    age_group = _el(patient, "ePatient.AgeGroup")
    _el(age_group, "ePatient.15", call["age"])
    _el(age_group, "ePatient.16", "2516009")
    _el(patient, "ePatient.25", call["sex_code"])

    # ePayment and eScene are MANDATORY sections; a chest-pain scene call has
    # nothing to say in either, so they carry NV rather than being omitted —
    # which is precisely the NV path worth generating in bulk.
    payment = _section(pcr, "ePayment")
    _el(payment, "ePayment.01", None, nil="true", NV="7701003")

    scene = _section(pcr, "eScene")
    _el(scene, "eScene.01", "9923003")         # First unit on scene: Yes
    _el(scene, "eScene.06", "2707005")         # Number of patients: Single
    _el(scene, "eScene.07", "9923001")         # MCI: No

    situation = _section(pcr, "eSituation")
    complaint = _el(situation, "eSituation.PatientComplaintGroup")
    _el(complaint, "eSituation.03", "2803001")
    _el(complaint, "eSituation.04", call["chief_complaint"])
    _el(situation, "eSituation.11", call["primary_impression"])

    # More mandatory sections with nothing to report for this scenario.
    injury = _section(pcr, "eInjury")
    _el(injury, "eInjury.01", None, nil="true", NV="7701001")

    arrest = _section(pcr, "eArrest")
    _el(arrest, "eArrest.01", "3001001")       # Cardiac arrest: No

    history = _section(pcr, "eHistory")
    _el(history, "eHistory.01", None, nil="true", NV="7701003")

    vitals = _section(pcr, "eVitals")
    group = _el(vitals, "eVitals.VitalGroup")
    _el(group, "eVitals.01", call["vitals"]["taken"])
    _el(group, "eVitals.02", "9923001")
    bp = _el(group, "eVitals.BloodPressureGroup")
    _el(bp, "eVitals.06", call["vitals"]["systolic"])
    _el(bp, "eVitals.07", call["vitals"]["diastolic"])
    hr = _el(group, "eVitals.HeartRateGroup")
    _el(hr, "eVitals.10", call["vitals"]["heart_rate"])
    _el(group, "eVitals.12", call["vitals"]["spo2"])
    _el(group, "eVitals.14", call["vitals"]["resp_rate"])
    pain_group = _el(group, "eVitals.PainScaleGroup")
    _el(pain_group, "eVitals.27", call["vitals"]["pain"])

    protocols = _section(pcr, "eProtocols")
    protocol_group = _el(protocols, "eProtocols.ProtocolGroup")
    _el(protocol_group, "eProtocols.01", "9914001")   # Protocol: not applicable

    medications = _section(pcr, "eMedications")
    _el(medications, "eMedications.MedicationGroup")

    procedures = _section(pcr, "eProcedures")
    _el(procedures, "eProcedures.ProcedureGroup")

    disposition = _section(pcr, "eDisposition")
    incident = _el(disposition, "eDisposition.IncidentDispositionGroup")
    _el(incident, "eDisposition.30", call["disposition"])

    outcome = _section(pcr, "eOutcome")
    _el(outcome, "eOutcome.01", None, nil="true", NV="7701001")

    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True
    )
