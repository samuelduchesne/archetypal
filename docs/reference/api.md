---
diataxis: reference
---

# Python API

The public Python interface of archetypal 3: five modules and the names each lists in its
`__all__`. Every other module is private, and its names may change without notice.

| Module | Public names |
|---|---|
| `archetypal` | `__version__`, `reduce`, `merge`, `compare`, `Layout`, `ReductionOptions`, `read_umi`, `write_umi` |
| `archetypal.reduction` | `reduce`, `merge`, `Reduction`, `RESULTS_REQUIREMENTS`, `schedule_compact` |
| `archetypal.comparison` | `compare`, `ComparisonResult`, `ComparisonRow`, `AcceptanceTargets`, `MetricKind` |
| `archetypal.umi` | `read_umi`, `write_umi`, `to_umi`, `UmiImport`, `UmiExport`, `TranslationReport`, `Loss`, `LossKind`, `Note`, `NoteKind`, `CORRESPONDENCE`, `FieldMapping`, `Relevance`, `MappingStatus` |
| `archetypal.errors` | the errors below |

The top-level names are the same objects as those of the modules: `archetypal.reduce` is
`archetypal.reduction.reduce`, `archetypal.read_umi` is `archetypal.umi.read_umi`.
`import archetypal` imports neither epinterface nor the reduction code: the top-level names
are loaded on first use.

- [Reduction and comparison API](api/reduction.md): `reduce`, `merge`, `Reduction`,
  `Layout`, `ReductionOptions` and `compare`, with their result types.
- [UMI translation API](api/umi.md): `read_umi`, `write_umi`, `to_umi` and the report types.

## Version

`archetypal.__version__` is the installed version, as a string.

## Errors

Every error derives from `ArchetypalError`, and its message starts with the input at fault.
The reduction errors (`ReductionError` and its subclasses) are described in the
[Reduction and comparison API](api/reduction.md).

::: archetypal.errors
    options:
      show_root_heading: false
      members_order: source
      members:
        - ArchetypalError
        - InputError
        - UnsupportedFeatureError
        - LossyTranslationError
        - LossReport
        - NotComparableError
        - OptionalDependencyError
        - RemovedInArchetypal3Error
        - UmiFormatError
        - UmiValidationError
        - Problem
