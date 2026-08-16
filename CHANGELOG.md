# Changelog

## v0.4.0 — 2026-08-16

- **`gnis.gazetteer()`** — GNIS feature id -> city name for the twelve places
  this package emits. NEMSIS stores the id; FHIR's `Address.city` and CDA's
  `<city>` want the name, and neither standard has a coded-place element, so a
  consumer needs a gazetteer or must leave the city absent. Handing over the
  names for exactly what we generate is what makes the resolved path testable
  at all.

  Deliberately **not** a general gazetteer — twelve places, not GNIS in full.
  Shipping that is USGS's job.

## v0.3.0 — 2026-08-14

### Added — real GNIS city codes, cross-checked against their state

NEMSIS stores a city as a **GNIS feature id**, not a name — `dPersonnel.05`,
`dContact.06` and `eScene.17` are all `CityGnisCode`, whose schema type is a
bare `xs:positiveInteger`. **Any integer validates.** A made-up code passes
every gate this project has and names a different town, or nowhere at all,
which is precisely the class of defect a generator must not manufacture.

So twelve Utah places were looked up in the USGS National Map Geographic Names
service and recorded with the state the service returned:

| GNIS | Place | County |
|---|---|---|
| 1454997 | Salt Lake City | Salt Lake |
| 1444661 | Provo | Utah |
| 1444049 | Ogden | Weber |
| 1455905 | Sandy City | Salt Lake |
| 1444110 | Orem | Utah |
| 1437843 | West Valley City | Salt Lake |
| 1442459 | Layton | Davis |
| 1442849 | Logan | Cache |
| 1455098 | Saint George | Washington |
| 1443742 | Murray | Salt Lake |
| 1427473 | Draper | Salt Lake |
| 1433590 | Tooele | Tooele |

`test_gnis.py` cross-checks every one against the agency's ANSI state — a city
in the wrong state is XSD-valid, geographically impossible, and invisible
unless the two are compared. An opt-in test (`NEMSYNTH_VERIFY_GNIS=1`)
re-resolves all twelve at USGS; it is opt-in because a unit suite that needs a
government web service is one that fails on a train.

The station city, the ANSI state on every address, and the crew's state of
licensure now all derive from that one table, so they cannot drift apart. Scene
addresses vary across all twelve, so a corpus is no longer all one town.

## v0.2.0 — 2026-08-14

- **A default crew, spanning both datasets.** NEMSIS names the join itself:
  `eCrew.01` is the state certification/licensure number and `dPersonnel.23`
  is the same number in the roster. The PCR now carries three crew members
  (a paramedic running the call plus two EMTs, with distinct levels AND roles),
  and the DEM carries their names, licensure and contact details.
- Invented contact detail so a consumer can satisfy C-CDA's US Realm Header:
  `801-555-01xx` (the fiction range, and NEMSIS pattern-checks full NANP
  numbers, so a bare 555-0101 is invalid), a GNIS-coded city and ANSI state.

The people are invented and the certification numbers are not real.

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
