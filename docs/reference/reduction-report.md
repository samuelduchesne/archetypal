---
diataxis: reference
---

# Reduction report

Every field of the reduction report: how each zone group of an archetype was formed, the rule
behind every SBEM value, and what the archetype does not represent. The report is
`archetypal.reduction.report.ReductionReport`, written as `<name>.report.json` beside
`<name>.sbem.json` by `Reduction.write` and validated by the published JSON Schema
[`reduction-report-1.0.json`](../schemas/reduction-report-1.0.json) (`$id`
<!-- reduction-report-schema-id -->). The tables are generated from that schema.

Any program can read the file without archetypal. Its encoding:

- UTF-8, two-space indent, object keys in model order, no timestamps;
- arrays sorted by group key, then zone name; floats as their shortest round-trip form;
- hourly profiles as base64-encoded little-endian float64 arrays with their length
  ([EncodedProfile](#encodedprofile));
- equal reductions give byte-identical files.

A reader accepts every `1.x` file; removing or redefining a field bumps the major version.
Energies are in joules, areas in m², airflows in m³/s, volumes in m³ and temperatures in °C.

Every report satisfies these invariants, which reduction checks before returning:

1. **Accounting.** Every zone of the model appears exactly once, among `groups[].members` or
   in `excluded_zones`. Attics and basements are excluded with role `attic` or `basement`.
2. **Area.** The `floor_area_share` of the groups sum to 1; their `floor_area` sum to the
   conditioned floor area of the results.
3. **Every parameter has a rule.** Every field of the archetype that reduction sets appears in
   `parameters` with one of the [rule ids](#rule-ids).
4. **Nothing dropped silently.** Every feature without an SBEM counterpart, and every value
   folded into another parameter, appears in `not_represented`.
5. **Mergeable.** `pre_threshold_groups` holds full ledgers at the finest key (space use,
   exposure), whatever the layout, so that `merge` can reach any layout that is not strictly
   finer without the model.
6. **Reproducible.** `reproducibility` holds every version, input hash and option.

[About reduction](../explanation/reduction.md) explains the rules;
[How to reduce a model](../how-to/reduce-a-model.md) shows how to read the report.

<!-- reduction-report-schema -->
