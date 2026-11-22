# Contract: the loss report file

Written as `<library stem>.loss.json` by `read_umi(...).write()` and by `write_umi`. It is
validated by `docs/schemas/translation-report-1.0.json`, generated from the pydantic model
`archetypal.umi.TranslationReport` (data-model.md). Its reference page is generated from that
schema.

## Shape

```json
{
  "schema_version": "1.0",
  "direction": "umi_to_sbem",
  "source": {
    "path": "BostonTemplateLibrary_2.json",
    "sha256": "…",
    "dialect": "core-json-pre-2023",
    "archetypal": "3.0.0a1",
    "epinterface": "1.5.0.post1"
  },
  "subjects": ["B_Off_0", "B_Res_0_Masonry", "B_Res_0_WoodFrame", "B_Ret_0"],
  "losses": [
    {
      "kind": "lost",
      "subject": "B_Off_0",
      "location": "/BuildingTemplates/0/PartitionRatio",
      "value": 0.35,
      "replacement": null,
      "rule": "upstream.partition_ratio",
      "reason": "SBEM has no partition ratio yet",
      "upstream": "UP-9"
    }
  ],
  "notes": [
    {
      "kind": "defaulted",
      "subject": "B_Off_0",
      "location": "/DomesticHotWaterSettings/0/CoefficientOfPerformance",
      "value": 0.85,
      "rule": "format.basilisk_default",
      "reason": "absent from the file; Basilisk's default used"
    }
  ],
  "summary": "12 values lost (9 lost, 3 approximate) in 4 templates."
}
```

## Invariants

1. `losses` empty if and only if `summary == "Nothing was lost."`.
2. Strict mode raises if and only if `losses` is not empty. Notes never cause a failure.
3. `location` is a JSON pointer into the UMI file on the UMI side. On the SBEM side it is a
   dotted field path prefixed by the group (`perimeter.Operations.HVAC.Ventilation.DCV`) or
   `archetype.`.
4. Losses and notes are sorted by `subject`, then `location`. The file is byte-identical for
   equal inputs (FR-012).
5. Every `rule` is a rule of `CORRESPONDENCE` or a library-level rule (`library.unused`,
   `names.collision`, `layout.merged`, `layout.share_dropped`, `layout.core_copied`,
   `validation.skipped`).
6. Every difference that `diff_umi` or `diff_archetypes` finds between input and output is
   covered by a loss with the same subject and location (SC-006).
