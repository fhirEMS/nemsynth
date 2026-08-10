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

## Status — early

Working: the statistical grounding, seeded reproducibility, the scenario /
serializer separation, the CLI, and the **self-validation gate** — every
document is validated against the vendored NEMSIS XSDs before it is written,
because a generator that emits invalid NEMSIS teaches its consumer nothing
(every downstream finding would be ambiguous between generator bug and mapper
bug).

Not yet working: the first scenario does not pass that gate. NEMSIS mandates
**17 sections** per PatientCareReport, many with deeply nested required
children, and hand-deriving those sequences proved to be the wrong approach —
each fix surfaced another requirement.

**Next step, and the right design:** build the document skeleton *from the XSD*
rather than by hand. A schema walker emits every required element — nil + NV
where a scenario has nothing to say — and scenarios fill in only what they care
about. That inverts the work: adding a scenario becomes clinical logic instead
of schema archaeology, and it cannot drift from the schema because it is derived
from it. The self-validation gate stays as the backstop.

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
