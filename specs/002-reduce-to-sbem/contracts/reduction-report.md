# Contract: the reduction report file

`<name>.report.json` sits beside `<name>.sbem.json`. Its JSON Schema is generated from the
`ReductionReport` pydantic model and published with the documentation
(`docs/reference/reduction-report.md`). Any program can read the file without archetypal, as
spec 001's FR-014 requires. Field meanings are in [../data-model.md](../data-model.md),
section ReductionReport.

## Invariants (tested)

1. **Accounting.** Every zone of the model appears exactly once, either among
   `groups[].members` or in `excluded_zones` (SC-006). Attics and basements appear in
   `excluded_zones` with role `attic` or `basement`.
2. **Area.** Σ `groups[].floor_area_share` = 1 within 1e-12. Σ `groups[].floor_area` equals the
   conditioned floor area of the results (FR-014).
3. **Every parameter has a rule.** Every leaf field of the archetype that reduction sets
   appears in `parameters[]` with a rule id from the derivation table (FR-025).
4. **Nothing dropped silently.** Every feature in the model that has no SBEM counterpart, and
   every value folded into another parameter, appears in `not_represented[]` (FR-026).
5. **Mergeable.** `pre_threshold_groups[]` holds full ledgers, enough for `merge` to work
   without the model (FR-010, FR-011).
6. **Reproducible.** The `reproducibility` block holds all versions, hashes and options
   (Key Entities: Reduction report). Two reductions with equal inputs produce byte-identical
   files.
7. **Schema version.**
   - `schema_version` follows semantic versioning.
   - A reader accepts every 1.x file.
   - Removing or redefining a field bumps the major version, with a migration note.

## Encoding

- UTF-8, two-space indent.
- Object keys in model order; arrays sorted by group key, then zone name.
- Floats as shortest round-trip `repr`.
- No timestamps.
- Profiles (8760 values) are stored as base64-encoded little-endian float64 arrays with their
  length. This keeps a reference-building report in the low megabytes, and the schema
  documents the encoding.
