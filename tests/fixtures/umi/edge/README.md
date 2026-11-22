# UMI edge-case libraries

Expected outcome of reading each file with `read_umi` (spec 003, research R18):

| File | Expected outcome |
|---|---|
| `dangling_ref.json` | Refused, `UmiFormatError`: `$ref` "99" at `/ZoneLoads/0/OccupancySchedule` points to no `$id`. |
| `forward_ref.json` | Refused, `UmiFormatError`: `/BuildingTemplates/0/Core` and `/Perimeter` point to ids defined later (`Zones` is written after `BuildingTemplates`). |
| `missing_reference.json` | Refused, `UmiValidationError` (completeness): `/ZoneLoads/0/LightsAvailabilitySchedule` is `null`, template "Office" affected. |
| `duplicate_names.json` | Read, two archetypes. Collisions reported and the later components renamed with ` #2`: opaque material "Concrete" (conductivity 1.95 and 1.4), glazing and gas material "Clear 6mm", template "Office". |
| `shared_zone.json` | Read, one archetype whose `core` and `perimeter` groups are equal (one zone definition, as written for a perimeter-only archetype). |
| `misaligned_parts.json` | Read. Year schedule "Office" switches week on 15 March and 15 October: March and October are projected and reported as approximate; every other month is exact. |
| `out_of_range.json` | Refused, `UmiValidationError` (range): conductivity −0.04 of "Bad insulation", template "Bad office". With `skip_invalid_templates=True`: "Bad office" skipped and listed, "Office" read. |
| `no_templates.json` | Read, no archetype, and the report says so; all 22 components listed as unused. |
| `unused_components.json` | Read, one archetype; "Brick", "Brick wall" and "Half on" listed as unused. |
| `archsim_dialect.json` | Read as the Archsim-era dialect: `Comment` → `Comments`, `GasType` 1 → `ARGON`, material `Type` → `Category`; `Life`, `EmbodiedEnergyStdDev`, `EmbodiedCarbonStdDev`, `PhaseChange`, `Optical` and the other keys without a Core counterpart listed as lost. |
| `legacy.xml` | Refused, `UmiFormatError`: "Legacy UMI XML library is not supported; open and save it in UMI to convert it to JSON". |

A broken reference is a format problem (research R1, R3): it raises `UmiFormatError`, which
lists each problem with its JSON pointer and is never skipped by `skip_invalid_templates`, as
contracts/python-api.md and data-model.md state. `UmiValidationError` is kept for completeness
and range problems.

All files were written by hand for these tests. Each JSON file except `archsim_dialect.json`
is in the current Core JSON dialect at Basilisk commit `5cce24e8`, with every key in
Basilisk's serialisation order. The base library has one template, "Office", with distinct
core and perimeter zone definitions, and each file changes it in one way only.

What Basilisk makes of them (`tools/basilisk-check --report`):

- pass all four checks: `archsim_dialect`, `misaligned_parts`, `no_templates`,
  `out_of_range`, `shared_zone`, `unused_components` (Basilisk checks no range and no
  calendar);
- `dangling_ref`, `forward_ref`: fail check 1 (the reference scan); `Library.FromJson` turns
  the references into `null` without error, and check 4 then finds the null required
  references;
- `missing_reference`: fails check 4;
- `duplicate_names`: fails check 4 (Basilisk's editor refuses duplicate names);
- `legacy.xml`: fails checks 1 and 2 (not JSON).
