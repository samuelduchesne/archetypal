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

## [2.18.11] - 2026-10-25

### Changed

- The README now introduces [idfkit](https://idfkit.com), the successor to archetypal, and describes archetypal's reduced maintenance scope.

### Security

- Development lockfile now resolves Pillow 13.0.0 on Python 3.11+, fixing GHSA-58r4-6rv3-gfh8 (out-of-bounds access in `_imagingmorph`) and other Pillow advisories. Pillow is not a runtime dependency of archetypal; it comes in through matplotlib, so users should upgrade Pillow in their own environments.

[unreleased]: https://github.com/samuelduchesne/archetypal/compare/v2.18.11...HEAD
[2.18.11]: https://github.com/samuelduchesne/archetypal/compare/v2.18.10...v2.18.11
