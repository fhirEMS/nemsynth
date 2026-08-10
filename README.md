# nemsynth

**Statistically grounded synthetic NEMSIS v3.5 ePCR generation — a Synthea for EMS.**

Synthetic only. No real patient data is used, produced, or implied, and none
ever will be.

## Why this exists

A NEMSIS→FHIR/v2/C-CDA translator can only be tested against documents someone
wrote for it. That is a ceiling: five *published* NEMSIS scenario samples found
nine real defects in [emsinterop](https://github.com/fhirEMS/emsinterop) that
its own six hand-authored fixtures never could — a crash, a silent data loss, a
path traversal, and conformance failures. The limit was not effort; it was that
the same people wrote the mapper and its test data.

`nemsynth` breaks that loop by producing NEMSIS documents nobody on the
consuming project designed, in volume, with the messiness real exports have.

**It deliberately does not depend on emsinterop.** A generator that imported the
consumer's assumptions could only ever generate what that consumer already
handles. The two agree through the XSD and nothing else.

## Grounding

Distributions come from the [2022 National EMS Data
Report](https://nemsis.org/wp-content/uploads/2025/02/NEMSIS-End-of-Year-Report-2023.pdf)
(NEMSIS TAC / NHTSA Office of EMS), based on 42,302,358 911-response scene
activations — transcribed, not estimated. Examples:

| Distribution | Published national figure |
|---|---|
| Service type | 911 scene 79.0%, medical transport 10.7%, interfacility 8.8% |
| Level of care | ALS-Paramedic 75.6%, BLS-Basic/EMT 18.2% |
| Disposition | Treated & transported 57.7%, cancelled prior to arrival 6.4%, refused 5.9%, AMA 5.0%, … |
| Sex | Female 51.3% |

Where the report does not publish a figure, the key is suffixed `_approx`, the
reasoning is stated inline, and `nemsynth sources` prints which is which. A
plausible-looking number should never be mistaken for measured data.

```sh
nemsynth sources     # provenance for every distribution, measured vs assumed
```

## How it works

**The document is built from the XSD, not by hand.** `schema.py` parses the
vendored NEMSIS schemas into a navigable model — ordered children, occurrence
limits, nillability, the NV codes each element accepts, the values its type
permits. `skeleton.py` walks that model and emits every required element in
order.

That inverts the work: the **schema** decides what must be present and where; a
**scenario** decides only what it has to *say*, as a flat `{element_id: value}`
map. Where a scenario is silent, the builder emits nil + NV — the honest answer,
and the shape real exports take constantly. Adding a scenario is clinical logic,
not schema archaeology, and output cannot drift from the standard because it is
derived from it.

Every document is validated against those same XSDs before being written. A
generator that emits invalid NEMSIS teaches its consumer nothing: every
downstream finding would be ambiguous between generator bug and mapper bug.

## Status

Phase 1 works. An empty skeleton with no scenario values validates with **0
errors**; all 17 mandatory sections appear; 500 documents generate in ~0.35s.
Fed through [emsinterop](https://github.com/fhirEMS/emsinterop): **0 crashes, 0
non-informational issues, 0 unmapped national elements** across 500 documents.

It earned its keep on its first run by finding a bug in *itself* — an identity
field fell through to a last-resort literal and contradicted the header, which
the consumer's issue ledger caught. XSD-valid and wrong is exactly the trap a
generator must not set.

Next: the messiness engine (NV/PN at realistic rates, the two XSD-sanctioned
sentinels, boundary values, untidy free text), then the scenario library, then
the fuzzing loop.

See [emsinterop's plan document](https://github.com/fhirEMS/emsinterop/blob/main/docs/06_Synthetic_Corpus_Plan.md)
for the full phased design, including the messiness engine (NV/PN at realistic
rates, the two XSD-sanctioned sentinels, boundary values, untidy free text) and
the fuzzing loop that is the eventual prize.

## Install

```sh
pip install -e '.[dev]'
nemsynth sources
nemsynth gen --scenario chest-pain --seed 1 --count 10 -o out/
```

Same seed, byte-identical output, forever — a defect found by generated document
#8,412 is worthless if it cannot be replayed.

## Licence

Apache-2.0.
