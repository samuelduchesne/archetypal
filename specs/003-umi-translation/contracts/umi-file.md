# Contract: UMI library files written by archetypal

What `write_umi` produces (research R13, R15). The target is Basilisk Core JSON at commit
`5cce24e8`.

1. **Collections**, in this order, all present (possibly empty): `GasMaterials`,
   `GlazingMaterials`, `OpaqueMaterials`, `OpaqueConstructions`, `WindowConstructions`,
   `StructureDefinitions`, `DaySchedules`, `WeekSchedules`, `YearSchedules`,
   `DomesticHotWaterSettings`, `VentilationSettings`, `ZoneConditionings`,
   `ZoneConstructionSets`, `ZoneLoads`, `Zones`, `BuildingTemplates`, `WindowSettings`.
2. **References.**
   - Every component except building templates has `$id` as its first key, numbered `"1"`,
     `"2"`, … in document order.
   - Every later occurrence is `{"$ref": "<id>"}`, pointing backwards.
   - Window settings are defined inline at first use in `BuildingTemplates[i].Windows`; the
     `WindowSettings` collection holds only `$ref`s.
3. **No unused component, no missing component.** Every component is reachable from a
   building template. `OrphanedComponents()` is empty.
4. **Names** are non-null and unique per collection, glazing and gas materials together.
   Building-template names are also unique.
5. **Completeness.** Every reference listed in research R3 is non-null; every day has 24
   values; every week has 7 days; year parts cover 1/1–12/31 (February ends on the 29th)
   without overlap.
6. **Values.** Enums are integers. Integer fields are JSON integers. Floats are the shortest
   round-trip representation, never rounded. Every field of the current Basilisk classes is
   written, including Basilisk's defaults for fields SBEM does not hold (each noted in the
   report).
7. **Bytes.** UTF-8 without BOM, two-space indentation, `\n` line ends, a final newline.
   Equal inputs give equal bytes.

Checked on every pull request by `tools/basilisk-check` (SC-002), and in the unit tier by
`tests/umi/basilisk_rules.py`.
