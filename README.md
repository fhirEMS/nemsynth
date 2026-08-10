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

## Messiness

A generator that emits only clean, fully-populated records is *less* useful than
the handful of published samples: every document is the same well-formed shape,
and a consumer sails through all of them. `--messiness` reintroduces the
imperfection real exports have — reproducibly, and always **XSD-valid**.

```sh
nemsynth gen --seed 1 --count 300 --messiness high -o out/
```

| Profile | NV | PN | Sentinels | Boundaries | Untidy text |
|---|---|---|---|---|---|
| `clean` | — | — | — | — | — |
| `low` | 5% | 2% | 2% | 1% | 5% |
| `medium` (default) | 15% | 6% | 6% | 4% | 15% |
| `high` | 30% | 15% | 15% | 12% | 35% |

Validity is the constraint, not an afterthought: malformed input is rejected by
a consumer's ingest gate before any mapping code runs, so it teaches nothing.
What is generated is input the gate *accepts* and a consumer then mishandles —
`eVitals.07` `P` (palpated BP), `eVitals.18` `High` (off-scale glucose), hour-24
timestamps that are XSD-legal and FHIR-invalid, identifiers carrying `/` and
`?`, XML-significant characters in narrative, and NV/PN codes with *varied*
reasons so a consumer that flattens them all to "missing" gets caught.

Boundary values are read from the schema's own facets rather than guessed —
picking age `0` by hand produced XSD-invalid output, and the self-validation
gate rejected it.

## Status

Phases 1 and 2 work. An empty skeleton validates with **0 errors**; all 17
mandatory sections appear; 500 documents generate in ~0.35s; every profile stays
XSD-valid, and CI asserts the hostile traits actually appear rather than
trusting the knobs are wired up.

It has now found defects on both sides of the fence, which is the point:

- **In itself, on its first run** — an identity field fell through to a
  last-resort literal and contradicted the header. XSD-valid and wrong is
  exactly the trap a generator must not set.
- **In its consumer** — 300 documents at `--messiness high` reached a branch
  combination neither emsinterop's six hand-authored fixtures nor the five
  published NEMSIS samples had: symptom onset present while the primary
  impression was NV and no chief complaint existed. A national Required element
  was being dropped with no ledger entry. It is now
  [a permanent regression fixture](https://github.com/fhirEMS/emsinterop/blob/main/tests/fixtures/hostile/hostile_onset_no_impression.xml)
  there.

Next: the scenario library (12–15 clinical presentations, MCI multi-patient),
then the fuzzing loop.

See [emsinterop's plan document](https://github.com/fhirEMS/emsinterop/blob/main/docs/06_Synthetic_Corpus_Plan.md)
for the full phased design.

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
