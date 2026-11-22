# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial project scaffold generated from [project-kit-cookiecutter](https://github.com/samuelduchesne/project-kit-cookiecutter).
- Reduction of a detailed EnergyPlus model to an SBEM archetype (`archetypal.reduction`), with a comparison of the archetype's results against the source model (`archetypal.comparison`).
- Translation between SBEM archetypes and UMI template libraries, every written library checked with UMI's own code (Basilisk) in CI.

### Changed

- archetypal now depends on `epinterface` (`>=1.5.0,<1.6`) from the SBEM fork (https://github.com/samuelduchesne/epinterface), pinned to commit `d1283ca1865c69a7117239143e1c66b94eef7834`. Beyond upstream, the fork carries the HVAC fields of UP-8 (specific fan power, supply-air limits, a temperature-dependent EIR) and UP-2's extra fields (sensible and latent heat-recovery effectiveness, an infiltration schedule, holiday and design-day week slots, window-to-wall ratios by orientation), under archetype schema version 1.1, which still reads 1.0 files. The pin will be replaced by a fork tag (`v1.5.0.post1`) once the maintainer tags it.

### Removed

- The archetypal 2 code base (`archetypal/`, the `geomeppy` submodule, Docker files, the paper, the Sphinx docs and the poetry setup). archetypal 2 stays available from the `v2.18.11` release.

## [2.18.11] - 2026-10-25

### Changed

- The README now introduces [idfkit](https://idfkit.com), the successor to archetypal, and describes archetypal's reduced maintenance scope.

### Security

- Development lockfile now resolves Pillow 13.0.0 on Python 3.11+, fixing GHSA-58r4-6rv3-gfh8 (out-of-bounds access in `_imagingmorph`) and other Pillow advisories. Pillow is not a runtime dependency of archetypal; it comes in through matplotlib, so users should upgrade Pillow in their own environments.

[unreleased]: https://github.com/samuelduchesne/archetypal/compare/v2.18.11...HEAD
[2.18.11]: https://github.com/samuelduchesne/archetypal/compare/v2.18.10...v2.18.11
