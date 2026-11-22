---
diataxis: reference
---

# UMI translation API

The public Python API of spec 003: reading UMI template libraries into SBEM archetypes,
writing archetypes back as one library, and comparing libraries and archetypes field by field.
`archetypal.read_umi` and `archetypal.write_umi` are the same functions as
`archetypal.umi.read_umi` and `archetypal.umi.write_umi`. Each section is
generated from the docstrings; [Translation report](../translation-report.md) describes the
report's fields and [UMI correspondence](../umi-correspondence.md) what each UMI field becomes.

## Reading

::: archetypal.umi.read
    options:
      show_root_heading: false
      members:
        - read_umi
        - UmiImport

## Writing

::: archetypal.umi.write
    options:
      show_root_heading: false
      members:
        - write_umi
        - to_umi
        - UmiExport
        - approximate_merge
        - CorePerimeter

## Report

::: archetypal.umi.report
    options:
      show_root_heading: false
      members:
        - TranslationReport
        - Loss
        - LossKind
        - Note
        - NoteKind

## Round trips

`diff_umi` compares two libraries and `diff_archetypes` two SBEM archetypes, field by field;
[Check a round trip with `diff_umi`](../../how-to/write-archetypes-to-umi.md#check-a-round-trip-with-diff_umi)
shows them in use.

::: archetypal.umi.diff
    options:
      show_root_heading: false
      members:
        - diff_umi
        - diff_archetypes
        - UmiDiff
        - ArchetypeDiff
        - Difference

## Correspondence

[UMI correspondence](../umi-correspondence.md) renders `CORRESPONDENCE` as one table per UMI
class.

::: archetypal.umi.correspondence
    options:
      show_root_heading: false
      show_attribute_values: false
      members:
        - CORRESPONDENCE
        - FieldMapping
        - Relevance
        - MappingStatus
