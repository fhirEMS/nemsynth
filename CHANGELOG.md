# Changelog

## v0.1.0 — 2026-08-14

First tagged release. All five planned phases are delivered; further work is
breadth, not new machinery.

### The generator

- **Schema-driven skeleton.** Documents are built by walking the vendored
  NEMSIS XSDs — ordered children, occurrence limits, nillability, the NV codes
  each element accepts — not from hand-derived element sequences, which failed
  repeatedly. A scenario decides only what it has to *say*; the schema decides
  what must be present and where, so output cannot drift from the standard.
- **Self-validating.** Every document is checked against those same XSDs before
  it is written. A generator that emits invalid NEMSIS makes every downstream
  finding ambiguous between generator bug and mapper bug.
- **Messiness engine** (`--messiness clean|low|medium|high`): NV/PN with varied
  reasons, the two XSD-sanctioned sentinels (`eVitals.07` `P`/`p`, `eVitals.18`
  `High`/`Low`), hour-24 timestamps that are XSD-legal and FHIR-invalid, untidy
  identifiers and narrative. Always XSD-valid: malformed input is rejected by a
  consumer's ingest gate before any mapping code runs, so it teaches nothing.
- **15 clinical presentations**, repeating groups (serial vitals, several
  medications and procedures with per-instance timestamps), and `--mci N` for
  mass-casualty datasets holding N `PatientCareReport`s.
- **DEMDataSet** (`--dem`): the agency roster. The agency's *name* exists only
  there, so without it a consumer cannot build a named `Organization`.
- **93% of the national dataset** populated with real values, measured — up
  from 22% when it was first checked.

### What it has actually found

The only measure that matters for a generator:

- **In its consumer** — `eSituation.01` symptom onset dropped with no ledger
  entry when the primary impression was NV/PN. A national Required element, in
  a branch combination neither the hand-authored fixtures nor the published
  NEMSIS samples contained.
- **In itself, twice.** An identity field fell through to a last-resort literal
  and contradicted the header. And an inverted `YesNoValues` pair (9923001 is
  *No*, 9923003 is *Yes*) had every generated call quietly declaring itself a
  mass casualty incident — XSD-valid, invisible on inspection, caught only by
  reading the code's meaning back from the XSD's own documentation.
- **A regression in itself** — moving vitals into repeating groups silently
  disabled the messiness engine's vitals knobs. Caught because CI asserts the
  hostile traits appear in output rather than trusting the knobs are wired up.

### Design constraints that will not change

- **It must never depend on emsinterop**, even at test time. A generator
  carrying its consumer's assumptions can only generate what that consumer
  already handles. The two agree through the XSD and nothing else.
- Same seed, byte-identical output, forever — a defect found by generated
  document #8,412 is worthless if it cannot be replayed.
- Synthetic only. No real patient data is used, produced or implied.
