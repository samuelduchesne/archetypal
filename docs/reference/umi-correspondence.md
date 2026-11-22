---
diataxis: reference
---

# UMI to SBEM field correspondence

Every field of a UMI template library, as Basilisk serialises it, and how it maps to
epinterface's SBEM archetype model. The tables are generated from
`archetypal.umi.correspondence.CORRESPONDENCE`, the table the translator applies, so they list
exactly what the translation does.

Each field appears once, under the Basilisk class that declares it: a field shared by several
classes, such as `Name`, is listed under their common base class (`LibraryComponent`). SBEM
fields are dotted paths from a zone's `ZoneComponent`, from a component class
(`ConstructionMaterialComponent.Conductivity`) or from the archetype (`archetype.…`). The rule
is the identifier that losses and notes name in the
[translation report](translation-report.md). A field with status `upstream` is reported as lost
until the upstream item named in its row adds an SBEM field for it.

<!-- umi-correspondence -->
