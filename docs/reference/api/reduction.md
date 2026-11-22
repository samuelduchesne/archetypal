---
diataxis: reference
---

# Reduction and comparison API

The public Python API of spec 002: reducing a detailed EnergyPlus model to an SBEM archetype,
and comparing the archetype's simulation results with the detailed model's. Each section is
generated from the docstrings.

## Reduction

`archetypal.reduce`, `archetypal.Layout` and `archetypal.ReductionOptions` are the same objects
as `archetypal.reduction.reduce` and `archetypal.reduction.options.Layout` and
`ReductionOptions`. The public names of `archetypal.reduction` are `reduce`, `Reduction`,
`RESULTS_REQUIREMENTS` and `schedule_compact`. Its modules (`sources`, `inventory`,
`classify`, `ledger`, `grouping`, `to_sbem`, `report` and the domain modules) are internal:
their names may change between milestone tags without notice.

::: archetypal.reduction
    options:
      show_root_heading: false
      members:
        - reduce
        - Reduction
        - RESULTS_REQUIREMENTS
        - schedule_compact

::: archetypal.reduction.options
    options:
      show_root_heading: false
      members:
        - Layout
        - ReductionOptions

## Comparison

`archetypal.compare` is the same function as `archetypal.comparison.compare`. It raises
`archetypal.errors.NotComparableError` when the results cannot be compared.

::: archetypal.comparison
    options:
      show_root_heading: false
      members:
        - compare
        - AcceptanceTargets
        - ComparisonResult
        - ComparisonRow
        - MetricKind
