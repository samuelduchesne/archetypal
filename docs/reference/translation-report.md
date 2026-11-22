---
diataxis: reference
---

# Translation report

Every field of the translation report: what a UMI translation lost, and what it assumed. The
report is `archetypal.umi.report.TranslationReport`, saved as JSON and validated by the
published JSON Schema
[`translation-report-1.0.json`](../schemas/translation-report-1.0.json). The tables are
generated from that schema.

**Losses** are anything the target does not represent; **notes** are assumptions and defaults
that lose nothing. Strict mode (`TranslationReport.raise_for_losses`) raises
`LossyTranslationError` if and only if `losses` is not empty. Losses and notes are sorted by
subject, then location. A location is a JSON pointer into the UMI file on the UMI side
(`/BuildingTemplates/0/PartitionRatio`), and a dotted SBEM field path prefixed by the zone
group or `archetype.` on the SBEM side (`perimeter.Operations.HVAC.Ventilation.DCV`). A rule
is a rule of the [field correspondence](umi-correspondence.md), or one of the library-level
rules `library.unused`, `names.collision`, `layout.merged`, `layout.share_dropped`,
`layout.core_copied` and `validation.skipped`.

<!-- translation-report-schema -->
