"""The scenario library: fifteen presentations covering what EMS actually runs.

Chosen for **mapping coverage**, not for clinical variety on its own. Each one
reaches something a translator has to get right and the others do not:

  chest-pain          cardiac interventions, ALS-heavy, serial vitals
  cardiac-arrest      arrest fields, resuscitation, death on scene
  stroke              last-known-well timing, stroke scale
  respiratory         nebulised route, SpO2 as the driving vital
  diabetic            glucose as a value, and the off-scale sentinel path
  overdose            intranasal naloxone, altered LOC, refusal-after-reversal
  seizure             postictal altered mental status, no memory of event
  trauma-mvc          injury codes, mechanism, trauma-centre destination
  trauma-fall         geriatric fall, anticoagulated, low-acuity injury
  allergic-reaction   IM epinephrine, rapid improvement across serial vitals
  abdominal-pain      the ordinary BLS transport, minimal intervention
  psychiatric         behavioural, restraint, capacity — no drug therapy
  obstetric           age-banded female, imminent delivery
  pediatric-fever     age in MONTHS, weight-based dosing, paediatric vitals
  interfacility       not a 911 scene response: the service-type branch

Refusal, no-treatment and dead-on-scene dispositions fall out of the rates
rather than being separate scenarios, so every presentation can produce them.
"""

from __future__ import annotations

from .base import (
    AGE_MONTHS,
    ARREST_AFTER_EMS,
    ARREST_BEFORE_EMS,
    AVPU_ALERT,
    AVPU_PAIN,
    AVPU_UNRESPONSIVE,
    AVPU_VERBAL,
    ROUTE_ET,
    ROUTE_IM,
    ROUTE_IN,
    ROUTE_IO,
    ROUTE_IV,
    ROUTE_NEB,
    ROUTE_ORAL,
    ROUTE_SL,
    SERVICE_INTERFACILITY,
    UNIT_G,
    UNIT_LPM,
    UNIT_MCG,
    UNIT_MG,
    UNIT_ML,
    Med,
    Presentation,
    Proc,
    Vitals,
)

# --- interventions, reused across presentations ------------------------------
ASPIRIN = Med("1191", "324", UNIT_MG, ROUTE_ORAL, "Aspirin")
NITRO = Med("4917", "0.4", UNIT_MG, ROUTE_SL, "Nitroglycerin")
FENTANYL = Med("4337", "100", UNIT_MCG, ROUTE_IV, "Fentanyl")
MORPHINE = Med("7052", "4", UNIT_MG, ROUTE_IV, "Morphine")
ONDANSETRON = Med("26225", "4", UNIT_MG, ROUTE_IV, "Ondansetron")
NALOXONE = Med("7242", "2", UNIT_MG, ROUTE_IN, "Naloxone")
ALBUTEROL = Med("435", "2.5", UNIT_MG, ROUTE_NEB, "Albuterol")
IPRATROPIUM = Med("7213", "0.5", UNIT_MG, ROUTE_NEB, "Ipratropium")
EPI_IM = Med("3992", "0.3", UNIT_MG, ROUTE_IM, "Epinephrine")
EPI_IV = Med("3992", "1", UNIT_MG, ROUTE_IV, "Epinephrine")
DIPHENHYDRAMINE = Med("3498", "50", UNIT_MG, ROUTE_IV, "Diphenhydramine")
METHYLPRED = Med("6902", "125", UNIT_MG, ROUTE_IV, "Methylprednisolone")
MIDAZOLAM = Med("6960", "5", UNIT_MG, ROUTE_IM, "Midazolam")
DEXTROSE = Med("4850", "25", UNIT_G, ROUTE_IV, "Dextrose 50%")
GLUCAGON = Med("4832", "1", UNIT_MG, ROUTE_IM, "Glucagon")
AMIODARONE = Med("703", "300", UNIT_MG, ROUTE_IO, "Amiodarone")
OXYGEN = Med("7806", "15", UNIT_LPM, ROUTE_ET, "Oxygen")
SALINE = Med("9863", "500", UNIT_ML, ROUTE_IV, "Sodium chloride 0.9%")

IV_ACCESS = Proc("392230005", "Peripheral IV cannulation")
ECG_12_LEAD = Proc("268400002", "12-lead ECG")
GLUCOSE_CHECK = Proc("33747003", "Blood glucose measurement")
CPR = Proc("89666000", "Cardiopulmonary resuscitation")
DEFIB = Proc("429500007", "Defibrillation")
INTUBATION = Proc("112798008", "Endotracheal intubation")
BVM = Proc("425447009", "Bag-valve-mask ventilation")
SPINAL = Proc("32114007", "Spinal immobilisation")
SPLINT = Proc("771275007", "Application of splint")
WOUND_CARE = Proc("225158009", "Wound dressing")
NEBULISER = Proc("56251003", "Nebuliser therapy")
RESTRAINT = Proc("55217003", "Application of restraint")
DELIVERY = Proc("237001001", "Assisted delivery")

LIBRARY: dict[str, Presentation] = {
    "chest-pain": Presentation(
        key="chest-pain",
        complaint="Chest pain",
        dispatch_code="2301067",                  # Chest Pain (Non-Traumatic)
        impressions=("R07.9", "I20.9", "R07.89"),
        symptom="R07.9",
        age_range=(30, 95),
        als_rate=0.85,
        refusal_rate=0.08,
        vitals=Vitals(systolic=(96, 178), heart_rate=(52, 124), pain=(3, 10)),
        meds=(ASPIRIN, NITRO, FENTANYL),
        procs=(ECG_12_LEAD, IV_ACCESS),
    ),
    "cardiac-arrest": Presentation(
        key="cardiac-arrest",
        complaint="Cardiac arrest",
        dispatch_code="2301009",                  # Cardiac Arrest / Death
        impressions=("I46.9", "I46.2"),
        symptom="R09.2",
        age_range=(40, 95),
        als_rate=1.0,
        refusal_rate=0.0,
        requires_als=True,
        arrest=ARREST_BEFORE_EMS,
        vitals=Vitals(systolic=(0, 60), heart_rate=(0, 40), resp_rate=(0, 6),
                      spo2=(0, 70), pain=(0, 0), avpu=AVPU_UNRESPONSIVE),
        meds=(EPI_IV, AMIODARONE, OXYGEN),
        procs=(CPR, DEFIB, INTUBATION, IV_ACCESS),
    ),
    "stroke": Presentation(
        key="stroke",
        complaint="Facial droop and left-sided weakness",
        dispatch_code="2301027",                  # Stroke / CVA
        impressions=("I63.9", "G45.9", "I61.9"),
        symptom="R47.01",
        age_range=(45, 95),
        als_rate=0.9,
        refusal_rate=0.02,
        vitals=Vitals(systolic=(130, 210), heart_rate=(58, 104),
                      pain=(0, 2), avpu=AVPU_VERBAL),
        procs=(ECG_12_LEAD, GLUCOSE_CHECK, IV_ACCESS),
    ),
    "respiratory": Presentation(
        key="respiratory",
        complaint="Shortness of breath",
        dispatch_code="2301005",                  # Breathing Problem
        impressions=("J44.1", "J45.901", "J18.9"),
        symptom="R06.02",
        age_range=(18, 95),
        als_rate=0.7,
        refusal_rate=0.05,
        vitals=Vitals(systolic=(108, 176), heart_rate=(86, 138),
                      resp_rate=(22, 40), spo2=(78, 93), pain=(0, 3)),
        meds=(ALBUTEROL, IPRATROPIUM, METHYLPRED),
        procs=(NEBULISER, IV_ACCESS),
    ),
    "diabetic": Presentation(
        key="diabetic",
        complaint="Altered mental status, known diabetic",
        dispatch_code="2301013",                  # Diabetic Problem
        impressions=("E11.649", "E11.65", "E16.2"),
        symptom="R41.82",
        age_range=(18, 90),
        als_rate=0.8,
        refusal_rate=0.18,       # a reversed hypoglycaemic very often refuses
        vitals=Vitals(systolic=(102, 168), heart_rate=(62, 118),
                      pain=(0, 2), avpu=AVPU_PAIN, glucose=(28, 62)),
        meds=(DEXTROSE, GLUCAGON),
        procs=(GLUCOSE_CHECK, IV_ACCESS),
    ),
    "overdose": Presentation(
        key="overdose",
        complaint="Unresponsive, suspected opioid overdose",
        dispatch_code="2301049",                  # Overdose / Poisoning
        impressions=("T40.1X1A", "T40.601A", "F11.90"),
        symptom="R06.89",
        age_range=(18, 70),
        als_rate=0.75,
        refusal_rate=0.22,       # refusal after reversal is extremely common
        vitals=Vitals(systolic=(88, 138), heart_rate=(48, 92),
                      resp_rate=(4, 12), spo2=(72, 92), pain=(0, 1),
                      avpu=AVPU_UNRESPONSIVE),
        meds=(NALOXONE, OXYGEN),
        procs=(BVM, IV_ACCESS, GLUCOSE_CHECK),
    ),
    "seizure": Presentation(
        key="seizure",
        complaint="Witnessed seizure, now postictal",
        dispatch_code="2301059",                  # Seizure
        impressions=("R56.9", "G40.909"),
        symptom="R56.9",
        age_range=(18, 85),
        als_rate=0.7,
        refusal_rate=0.14,
        vitals=Vitals(systolic=(110, 172), heart_rate=(84, 132),
                      pain=(0, 2), avpu=AVPU_VERBAL, glucose=(70, 150)),
        meds=(MIDAZOLAM,),
        procs=(GLUCOSE_CHECK, IV_ACCESS),
    ),
    "trauma-mvc": Presentation(
        key="trauma-mvc",
        complaint="Motor vehicle collision, restrained driver",
        dispatch_code="2301041",                  # Traffic / Transportation Incident
        impressions=("S09.90XA", "S29.9XXA", "T14.90"),
        symptom="R52",
        age_range=(16, 85),
        als_rate=0.75,
        refusal_rate=0.16,       # refusal at an MVC is very common
        injury_codes=("V43.52XA", "V47.5XXA", "V29.9XXA"),
        vitals=Vitals(systolic=(92, 158), heart_rate=(70, 130), pain=(2, 9)),
        meds=(FENTANYL, SALINE),
        procs=(SPINAL, IV_ACCESS, WOUND_CARE),
    ),
    "trauma-fall": Presentation(
        key="trauma-fall",
        complaint="Fall from standing, hip pain",
        dispatch_code="2301019",                  # Falls
        impressions=("S72.001A", "S00.03XA", "M25.551"),
        symptom="M25.551",
        age_range=(65, 99),
        als_rate=0.45,
        refusal_rate=0.10,
        injury_codes=("W19.XXXA", "W18.30XA", "W01.0XXA"),
        vitals=Vitals(systolic=(104, 176), heart_rate=(58, 104), pain=(4, 10)),
        meds=(MORPHINE, ONDANSETRON),
        procs=(SPLINT, IV_ACCESS),
    ),
    "allergic-reaction": Presentation(
        key="allergic-reaction",
        complaint="Hives and throat tightness after eating",
        dispatch_code="2301003",                  # Allergic Reaction / Stings
        impressions=("T78.2XXA", "T78.40XA", "T78.00XA"),
        symptom="R22.9",
        age_range=(5, 80),
        als_rate=0.8,
        refusal_rate=0.09,
        vitals=Vitals(systolic=(80, 132), heart_rate=(96, 148),
                      resp_rate=(20, 34), spo2=(86, 97), pain=(0, 4)),
        meds=(EPI_IM, DIPHENHYDRAMINE, METHYLPRED),
        procs=(IV_ACCESS,),
    ),
    "abdominal-pain": Presentation(
        key="abdominal-pain",
        complaint="Abdominal pain and nausea",
        dispatch_code="2301001",                  # Abdominal Pain
        impressions=("R10.9", "R10.31", "K59.00"),
        symptom="R10.9",
        age_range=(18, 90),
        als_rate=0.35,           # the ordinary BLS transport
        refusal_rate=0.10,
        vitals=Vitals(systolic=(106, 162), heart_rate=(64, 108), pain=(3, 9)),
        meds=(ONDANSETRON,),
        procs=(IV_ACCESS,),
    ),
    "psychiatric": Presentation(
        key="psychiatric",
        complaint="Agitated, threatening self-harm",
        dispatch_code="2301053",                  # Psychiatric / Behavioral
        impressions=("F29", "R45.851", "F41.9"),
        symptom="R45.4",
        age_range=(14, 75),
        als_rate=0.4,
        refusal_rate=0.12,
        vitals=Vitals(systolic=(112, 168), heart_rate=(88, 138), pain=(0, 3)),
        meds=(MIDAZOLAM,),
        procs=(RESTRAINT,),
    ),
    "obstetric": Presentation(
        key="obstetric",
        complaint="Active labour, contractions two minutes apart",
        dispatch_code="2301045",                  # Pregnancy / Childbirth
        impressions=("O80", "O47.9", "Z34.90"),
        symptom="O80",
        age_range=(15, 45),
        als_rate=0.6,
        refusal_rate=0.03,
        vitals=Vitals(systolic=(104, 152), heart_rate=(78, 126), pain=(6, 10)),
        meds=(SALINE,),
        procs=(DELIVERY, IV_ACCESS),
    ),
    "pediatric-fever": Presentation(
        key="pediatric-fever",
        complaint="Fever and lethargy in an infant",
        dispatch_code="2301061",                  # Sick Person
        impressions=("R50.9", "J06.9", "R56.00"),
        symptom="R50.9",
        age_range=(1, 23),       # MONTHS, not years
        age_units=AGE_MONTHS,
        als_rate=0.55,
        refusal_rate=0.07,
        vitals=Vitals(systolic=(70, 104), heart_rate=(120, 180),
                      resp_rate=(24, 50), spo2=(92, 100), pain=(0, 4),
                      avpu=AVPU_VERBAL),
        procs=(GLUCOSE_CHECK,),
    ),
    "interfacility": Presentation(
        key="interfacility",
        complaint="Interfacility transfer for higher level of care",
        dispatch_code="2301061",                  # Sick Person
        impressions=("I50.9", "N18.6", "J96.00"),
        symptom="R06.00",
        age_range=(35, 95),
        als_rate=0.9,
        refusal_rate=0.0,
        service=SERVICE_INTERFACILITY,
        vitals=Vitals(systolic=(98, 158), heart_rate=(62, 112), pain=(0, 5)),
        meds=(SALINE,),
        procs=(IV_ACCESS, ECG_12_LEAD),
    ),
}
