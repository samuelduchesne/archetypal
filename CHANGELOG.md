# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

To be released as 3.0.0a1, the first milestone of archetypal 3. archetypal 3 keeps the archetype
half of archetypal 2 and builds it on [SBEM](https://github.com/samuelduchesne/epinterface)
archetypes, [idfkit](https://idfkit.com) and epinterface; the rest of archetypal 2 is removed.
Read [How to migrate from archetypal 2](https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/)
before upgrading.

### Added

- `reduce` reduces a detailed EnergyPlus model (22.1 or later) and its annual results to an SBEM
  archetype: zones grouped by space use and exposure, with envelope, loads, schedules,
  ventilation, hot water, fans and system efficiencies conserved against the detailed model.
  `reduce(..., simulate=True, weather=...)` runs the one simulation it needs.
- `merge` merges an archetype to a coarser layout (space use, core and perimeter, single zone);
  `Layout` and `ReductionOptions` choose the layout and the small-group threshold.
- `compare` compares an archetype's simulated results with the detailed model's, by total,
  end use and peak.
- `schedule_compact` writes an SBEM schedule as an EnergyPlus `Schedule:Compact`.
- `read_umi` translates a UMI template library to SBEM archetypes; `write_umi` and `to_umi`
  translate archetypes to a UMI library. Every library archetypal writes is read by UMI's own
  code (Basilisk) in CI. Two losses wait on an upstream item and are reported, not dropped:
  - UMI's airflow-network, zone-mixing and interior-window settings (`WindowSettings.Afn*`,
    `ZoneMixing*`, `IsVirtualPartition` and `Type`, and `ZoneVentilation.Afn`) have no SBEM
    field even with UP-9; reading reports each one that differs from Basilisk's default as
    lost, with `"upstream": "UP-9"`.
  - A simple-glazing window is written as the equivalent glazing layer EnergyPlus builds from
    it and reported as approximate; archetypal computes that layer until idfkit provides it
    (UP-10).
- `diff_umi` compares two UMI libraries and `diff_archetypes` two SBEM archetypes, field by
  field.
- The `archetypal` command, with `reduce`, `merge`, `compare` and `translate`. Exit status 4
  means success with losses or approximations reported.
- Report files beside every output: `<model>.report.json` for a reduction (groups, conservation
  checks, and each feature of the detailed model the archetype does not represent, with what it
  is folded into; none of these waits on an upstream item) and `<library>.loss.json` for a UMI
  translation (each lost, approximate or renamed value). Both follow published JSON schemas.
- `RESULTS_REQUIREMENTS` and the
  [Results requirements](https://samuelduchesne.github.io/archetypal/reference/results-requirements/)
  page list the outputs a reduction reads. A missing output raises `MissingResults`, which names
  it in IDF syntax.
- A removed archetypal 2 name, module, command or option raises `RemovedInArchetypal3Error` (an
  `ImportError`), or exit status 2 on the command line, naming its replacement.
- A documentation site with a tutorial, how-to guides, explanations and reference pages.
- The reduction report holds `notes`, the grouping's remarks; `to_umi(..., path=...)` records
  the library's file in the loss report, as `write_umi` does.

### Changed

- archetypal 3 supports Python 3.10 to 3.12; pip refuses to install it on other versions.
- **Breaking:** until 3.0.0 is on PyPI, install archetypal 3 from git together with the SBEM
  fork of epinterface (https://github.com/samuelduchesne/epinterface), as
  [How to install archetypal 3](https://samuelduchesne.github.io/archetypal/how-to/install/)
  shows; the epinterface releases on PyPI lack the SBEM changes and require archetypal 2.
- archetypal depends on `epinterface` (`>=1.5.0,<1.6`) from the fork, pinned to commit
  `dee8d343eb9aaceb8ae43819ab95232b94fae63a` until the maintainer tags `v1.5.0.post1`. Beyond
  upstream, the fork carries the HVAC fields of UP-8 (specific fan power, supply-air limits, a
  temperature-dependent EIR), UP-2's fields (sensible and latent heat-recovery effectiveness, an
  infiltration schedule, holiday and design-day week slots, window-to-wall ratios by
  orientation, zone groups with unset shares) and UP-9's fields for UMI (natural and scheduled
  ventilation, a mechanical ventilation schedule, ideal-loads limits, availability schedules,
  adiabatic assemblies, partitions, daylighting, layered glazing, window settings, metadata,
  life-cycle fields), under archetype schema version 1.2, which still reads 1.0 and 1.1 files.
  The pip install of 3.0.0 waits on these changes reaching PyPI (UP-3).

### Removed

- **Breaking:** the rest of archetypal 2: the `IDF` class and model editing, simulation and
  version transition, the template library classes, the `transition` command and the v2
  options of `reduce`, among 314 names, modules, commands and options. idfkit and epinterface
  replace most of them; the
  [migration guide](https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/) and
  [Removed v2 capabilities](https://samuelduchesne.github.io/archetypal/reference/removed/)
  give the replacement of each. archetypal 2 stays available from the `v2.18.11` release.
- The `geomeppy` submodule, Docker files, the paper, the Sphinx docs and the poetry setup.

### Fixed

- `reduce` reads the hot-water temperature of equipment on a `WaterUse:Connections` from the
  water heaters' setpoint before the equipment's own target schedule: the hot-water heat was
  understated by a third for a 43 °C target drawn from a 60 °C plant.
- `reduce` attributes the heat exchanger and the coils of an
  `AirLoopHVAC:DedicatedOutdoorAirSystem` to the zones of the loops it feeds, and the heat
  recovery of a `ZoneHVAC:EnergyRecoveryVentilator` or `ZoneHVAC:OutdoorAirUnit` to its zone.
- `reduce` charges heat-rejection energy to cooling only; shares a `Heating` meter with hot water
  only for the fuels of the boilers and district heating; and combines rated efficiencies as
  output over input (two chillers of COP 2 and 6 are 3, not 4).
- `reduce` no longer hangs on a building with a large cluster of adjacent excluded zones.
- `reduce` counts storeys from the largest level, so a small lobby or partial basement under the
  typical floors no longer multiplies `Geometry.Storeys`.
- `reduce` handles a leap `RunPeriod` begin year that EnergyPlus ran on 365 days, reads
  daylight-saving dates whatever the process's locale, truncates the thermostat control type as
  EnergyPlus does, and clamps an "off" setpoint sentinel at each timestep, not on the hourly mean.
- `reduce` gives a `DesignSpecification:OutdoorAir:SpaceList` that omits a space of the zone the
  listed spaces' share of the zone, not all of it.
- `reduce` reports a mode that is delivered energy without a metered consumption or rated
  efficiency, a hot-water efficiency it had to assume, an economiser without a design
  outdoor-air flow, and a heat exchanger of unknown effectiveness, instead of writing them
  silently.
- `write_umi` conserves the annual infiltration volume when it merges groups whose infiltration
  schedules differ.
- Archetypes translated from UMI are written with epinterface's `Archetype.to_json`, as reduced
  ones are, and writing an archetype no longer encodes it a second time as indented JSON just to
  check its floats: several times faster for large archetypes.
- `reduce` refuses results without a weather-file run period, naming the `SimulationControl`
  switch, and its single run turns that switch on: a model set to run only its design days, such
  as many EnergyPlus example files, failed with a NumPy broadcast error.
- `reduce` gives every schedule of the archetype the detailed model's summer and winter design
  days, so epinterface sizes with them rather than with always-on gains and extreme setpoints;
  outdoor air and hot water, read from run-period results, repeat Monday and are reported.
  Writing to UMI reports each design-day slot as lost.
- `reduce` given a glob keeps only model files (`.idf`, `.epJSON`).
- A removed archetypal 2 module nested in another names its own replacement, not its parent's.
- UMI translation:
  - NaN and infinite values are refused instead of written; Archsim's `Type` field is reported
    as lost.
  - `diff_umi` reports unused components found only in the result, reports a renamed template
    as missing and extra instead of matching it by place, and treats two NaN values as equal.
  - Archetype file names are unique without regard to letter case and accepted by Windows;
    files are written to temporary files and moved into place only once all are written.
  - Construction systems are written with Basilisk's key order; components used only by
    skipped templates are reported; components with equal content are still recognised after
    one of them is renamed.
  - A template's window, window settings and partitions come from the group exposed as
    perimeter, whatever its name.
  - Material types, and costs or carbon at a density of 0, are reported as lost; values that
    are zero are no longer reported as losses.
  - Ventilation limits UMI cannot hold are reported as lost instead of raising an error.
  - Glazing and gas embodied carbon is converted from its rate unit (per m³ through the
    density) or reported as lost; gas carbon is no longer copied whatever its unit.
  - Constant scheduled ventilation round-trips; hot water per person is reported as lost
    where UMI cannot hold it.
  - A merged group gives its infiltration in air changes per hour, which epinterface uses,
    instead of keeping the largest member's calculation method.
  - The attic floor takes the slab's layers in reverse order, the way up epinterface places
    it.
  - Windows reduced to simple glazing apply each pane's dirt factor; window costs, carbon and
    assembly life-cycle values UMI or SBEM cannot hold are reported as lost; a four-pane window
    is no longer typed as triple glazing; a template takes another group's window when the
    perimeter group has none, instead of a default clear glazing.
  - Each dropped ideal-loads limit is reported with the limit type actually written.
  - People read from UMI give off UMI's 125.28 W each (about 1.348 met), not epinterface's
    1.2 met; a scheduled infiltration is written as its annual mean and the schedule reported;
    natural ventilation that SBEM would drop (no wind or buoyancy driver) is reported.
- Reduction:
  - Backup heaters are left out of the rated heating efficiency.
  - Outdoor air honours the `Maximum` method of `DesignSpecification:OutdoorAir`.
  - Tables in IP units are converted to SI, or refused when they cannot be.
  - Hot water without a zone is assigned to the conditioned zones, and the rule used is
    reported.
  - Infiltration coefficients are found for objects that a ZoneList or SpaceList copies; small
    fuel uses are kept; the distribution fuel entry is read.
  - `compare` uses the RunPeriod frequency and compares peaks at the frequency both models
    share.
  - Approximate infiltration follows each object's calculation method.
  - Skylights are kept out of facade window ratios and exposure, and reported as not
    represented.
  - The mechanical outdoor-air schedule is derived; ideal-loads limits are written only when
    derived from the model.
  - The number of storeys is rounded; a group of zero floor area raises a clear error.
  - Fan energy of excluded zones is reported; fan energy is split across several air loops,
    and zones served from a loop's supply side are counted.
  - Equivalent envelope assemblies subtract the films EnergyPlus used for the Envelope
    Summary's U (ASHRAE 90.1 nominal films) instead of ISO 6946's, so they keep the source
    layers' resistance; uninsulated walls, roofs and partitions no longer raise an error.
  - The hot-water temperature rise uses the hot and cold water schedules of the
    `WaterUse:Connections` an equipment belongs to, and a cold water schedule instead of the
    mains temperature.
  - An air loop's coil energy is split between its zones by the air that loop supplies, not by
    every loop's air entering the zone.
  - Pump energy is shared between heating, cooling and hot water, so service hot-water pumps
    are no longer charged to space conditioning; a negative hot-water delivery no longer
    inflates other zones' share of the consumption.
  - A zone served by several air loops takes the heat recovery and economiser of the loop that
    treats its outdoor air most, whatever the loops' names.
  - Holidays are averaged into their weekdays, since epinterface declares none: they no longer
    run as working days in the archetype; the lost holiday profile is reported.
  - People give off the detailed model's activity level (`MetabolicRate`), not a fixed 111.55 W.
  - Schedules are evaluated at the model's own timestep and follow its daylight saving period,
    as EnergyPlus applies them.
  - The hot-water pumps' energy reaches the archetype's distribution COP; hot water that is never
    heated is off and reported instead of heated by an assumed 45 K; a leap-year run period's
    hot-water volume and a hot-water fuel SBEM lacks are reported once, correctly.
  - The minimum outdoor air of a group with an economiser is the design minimum; the
    economiser's free-cooling air is left to the archetype's economiser.
  - Window assembly U-factor and SHGC (frame included) are counted over the whole opening.
  - Design outdoor air reads `DesignSpecification:OutdoorAir:SpaceList` and the
    proportional-control and IAQ methods instead of giving zero; infiltration objects of a
    SpaceList take their own coefficients.
  - Gain schedules above 1, half storey ratios and averaged thermostat control types are
    handled; zoneless hot water is never dropped; supply-air limits outside epinterface's range,
    infiltration by leakage area or flow coefficient, and the infiltration's dropped weather
    response are reported.
  - A run period that crosses 1 January is refused with an explanation instead of reduced out
    of step with its schedules.
- `reduce` follows EnergyPlus more closely:
  - A relative `Schedule:File` is read from the model's folder, not the working directory, and
    `simulate=True` names it by its absolute path so that the single run finds it.
  - Daylight saving time takes the last hour of each day from the next day's first, skips a
    `Schedule:File` that opts out, and shifts design days that observe it; thermostat control
    types are read at the model's timestep, so an hour that changes type no longer takes a type
    that never applied.
  - The hot-water efficiency uses the cold-water schedule the ledger uses, and hot water
    heated by the heating plant (no `WaterSystems` meter) shares the heating meter instead of
    taking its efficiency from pump energy alone. An equipment without a temperature schedule
    draws at the water heaters' shared setpoint.
  - The hot-water volume per person follows the occupants `occupancy` writes when the people
    schedule exceeds 1.
  - Adiabatic floors and ceilings keep their layers' resistance (EnergyPlus gives them their
    own film twice); a glass door is a window; ground conductance uses EnergyPlus's films.
  - A heating setpoint above the cooling setpoint is capped at it and reported.
  - Fan air density uses the elevation EnergyPlus ran with, from the results.
  - A `DesignSpecification:OutdoorAir:SpaceList` adds each space's per-zone flow.
  - Air loops without a return path serve their zones through PIU, beam, induction and
    dual-duct terminals; outdoor air units deliver their coils' energy; unmeasured units and
    loops that serve no zone are reported.
  - Exterior lights and equipment reported in kBtu are converted correctly (they were 1000 times
    too small).
- `reduce` refuses, with a `ReductionError` naming the input: a run period that is not one
  whole year, results with two weather-file run periods, a file that is not EnergyPlus SQLite
  results, and a model holding HVACTemplate objects. Results without the Envelope Summary
  raise `MissingResults`. A path holding `#`, `?` or `%` opens that file instead of creating
  another. Design objects and radiant surface groups are no longer taken for equipment, and
  the single run meters district heating under its names before EnergyPlus 23.2.
- `reduce` no longer fails on a negative OtherEquipment (a heat sink, now reported), or on a
  building without the surfaces of SBEM's basement ceiling; a space-use mapping that names one
  zone in two letter cases with two uses is refused.
- The report records the grouping's notes (such as a layout without core zones); in-memory
  results hash the same data the same way; `Reduction.read` refuses a report of another
  reduction and names a report of an unknown schema version. The archetype and its report are
  written together, so a failed write leaves the previous files.
- `compare` refuses meters that share no peak frequency instead of reporting a 0 W peak,
  compares two runs at the finest frequency they share, converts End Uses cells in mixed units,
  and accepts run periods of two years with the same calendar.
- CLI: `-o` may name a folder for the UMI library; a worker that dies fails its own model only;
  model names that differ only in case are refused; hidden files in a folder are skipped; a
  removed archetypal 2 option given as `--opt=value` gets the migration message; the loss
  report records the library's file name.
- `dir(archetypal)` lists the lazily imported API; a removed v2 module run with `python -m`
  raises the migration error.
- UMI translation:
  - Written files follow the umask (they were owner-only); a failed write leaves no
    temporary file.
  - Archetypes read from one library no longer share zone objects.
  - Numbers too large for a float are refused; values the rules lose (an illuminance target of
    0, a heat-recovery efficiency above 1, negative life-cycle values, ...) are lost as the
    correspondence notes say instead of refusing the template; a glass without conductivity is
    a validation problem.
  - A schedule named as epinterface reserves (`AllOn`, `AlwaysOn`, ...) is renamed; an
    `On/Off` schedule is a fraction, not always on; a month split between parts of one week is
    copied exactly.
  - Nameless window, ventilation and hot-water settings, negative cost or carbon, a live-loading
    preset SBEM lacks and negative mass ratios no longer refuse the template; simple glazing
    outside EnergyPlus's range is written approximately.
  - Hot water in a zone with people off is read: epinterface draws it by the people density.
  - Writing: the attic floor keeps a name of its own (it replaced the floor/ceiling
    construction in epinterface); a merged zone is named once and its natural ventilation keeps
    its window schedule; the window and its settings come from one group; a renamed duplicate
    archetype keeps its own losses; metadata of components UMI has no place for is reported.
  - `diff_umi` and `diff_archetypes` rate list elements by their list, compare unused
    components only with unused ones, and match renamed duplicates after a skipped template.

## [2.18.11] - 2026-10-25

### Changed

- The README now introduces [idfkit](https://idfkit.com), the successor to archetypal, and describes archetypal's reduced maintenance scope.

### Security

- Development lockfile now resolves Pillow 13.0.0 on Python 3.11+, fixing GHSA-58r4-6rv3-gfh8 (out-of-bounds access in `_imagingmorph`) and other Pillow advisories. Pillow is not a runtime dependency of archetypal; it comes in through matplotlib, so users should upgrade Pillow in their own environments.

[unreleased]: https://github.com/samuelduchesne/archetypal/compare/v2.18.11...HEAD
[2.18.11]: https://github.com/samuelduchesne/archetypal/compare/v2.18.10...v2.18.11
