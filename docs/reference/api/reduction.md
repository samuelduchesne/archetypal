---
diataxis: reference
---

# Reduction and comparison API

The public Python API of spec 002: reducing a detailed EnergyPlus model to an SBEM archetype,
and comparing the archetype's simulation results with the detailed model's. Each section is
generated from the docstrings.

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
