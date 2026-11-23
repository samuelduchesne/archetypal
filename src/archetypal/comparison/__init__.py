"""Compare an archetype's simulation results with the detailed model's (spec 002, US3).

`compare` reads two EnergyPlus SQLite result files, one from the detailed model and one from
its archetype, and reports total site energy, each end use by fuel and the annual peak
heating and cooling demand: both values, their difference and whether it meets the
acceptance targets (FR-027; success criteria SC-001 to SC-003). Results that are not
comparable, because their weather, run period, units, timestep or meter reporting frequency
differ, are refused with `NotComparableError` (FR-028).

How each quantity is read, and how pumps and heat rejection are shared between heating and
cooling, is described in `archetypal.comparison.results` (research R13).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from idfkit.simulation import SQLResult

from archetypal._sqlite import open_results
from archetypal.comparison.results import (
    DISTRIBUTION_END_USES,
    RunResults,
    common_peak_frequency,
    differences,
    label_of,
    read_run,
    sha256,
)
from archetypal.errors import NotComparableError

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator

__all__ = ["AcceptanceTargets", "ComparisonResult", "ComparisonRow", "MetricKind", "compare"]

MetricKind = Literal["total_site", "end_use", "end_use_with_distribution", "peak"]
"""What a comparison row measures.

- `total_site`: total site energy (SC-001).
- `end_use`: one end use for one fuel, as EnergyPlus reports it (FR-027).
- `end_use_with_distribution`: heating or cooling over every fuel, with the pumps and heat
  rejection that served it added (SC-002 judges these, not the heating and cooling rows as
  reported).
- `peak`: annual peak heating or cooling demand (SC-003).
"""


@dataclass(frozen=True)
class AcceptanceTargets:
    """The acceptance targets of a comparison, as fractions (SC-001 to SC-003).

    Attributes:
        total_site: Largest relative difference of total site energy (SC-001: 5 %).
        end_use: Largest relative difference of an end use (SC-002: 10 %).
        end_use_min_share: An end use is judged only when it is at least this fraction of
            the detailed model's total site energy (SC-002: 5 %).
        peak: Largest relative difference of a peak demand (SC-003: 15 %).
        peak_min_share: A peak is judged only when it is at least this fraction of the larger
            of the detailed model's two peaks (SC-003: 10 %).
    """

    total_site: float = 0.05
    end_use: float = 0.10
    end_use_min_share: float = 0.05
    peak: float = 0.15
    peak_min_share: float = 0.10

    def __post_init__(self) -> None:
        """Refuse a negative target.

        Raises:
            ValueError: If a target is negative or not a number.
        """
        for name in ("total_site", "end_use", "end_use_min_share", "peak", "peak_min_share"):
            value = getattr(self, name)
            if not value >= 0:
                msg = f"AcceptanceTargets.{name} must be a non-negative fraction, not {value!r}"
                raise ValueError(msg)


@dataclass(frozen=True)
class ComparisonRow:
    """One compared quantity.

    Attributes:
        metric: The quantity's name, such as `Total site energy`, `Interior Lighting: Electricity`,
            `Heating, with pumps and heat rejection` or `Peak cooling demand`.
        kind: What the row measures.
        end_use: The end use, as EnergyPlus names it, for an end-use row; `Heating` or `Cooling`
            for a peak; `None` for total site energy.
        fuel: The fuel, as EnergyPlus names it, for an `end_use` row; `None` otherwise.
        units: The unit of `detailed`, `archetype` and `difference`: the results' tabular energy
            unit (`GJ` by default), or `W` for a peak.
        detailed: The detailed model's value.
        archetype: The archetype's value.
        difference: `archetype - detailed`.
        relative: `difference / detailed`, or `None` when `detailed` is zero.
        target: The largest relative difference allowed, or `None` when no target applies (pumps,
            heat rejection, and heating and cooling as reported, which are judged with
            distribution added).
        within_target: Whether `abs(relative)` is at most `target`; `None` when no target
            applies, or when the quantity is too small to be judged (SC-002's share of site
            energy, SC-003's share of the larger peak).
    """

    metric: str
    kind: MetricKind
    end_use: str | None
    fuel: str | None
    units: str
    detailed: float
    archetype: float
    difference: float
    relative: float | None
    target: float | None
    within_target: bool | None


@dataclass(frozen=True)
class ComparisonResult:
    """The comparison of a detailed model's results with its archetype's (data-model.md).

    Attributes:
        rows: Total site energy first, then every end use by fuel that is not zero in either
            result (pumps and heat rejection included), then heating and cooling with pumps and
            heat rejection added, then peak heating and cooling demand.
        targets: The targets the rows were judged against.
        comparable: Always `True`: incomparable results raise `NotComparableError` instead.
        weather_sha256: The SHA-256 of the weather file passed to `compare`, or `None`.
    """

    rows: tuple[ComparisonRow, ...]
    targets: AcceptanceTargets
    comparable: Literal[True] = True
    weather_sha256: str | None = None

    def __iter__(self) -> Iterator[ComparisonRow]:
        """Iterate over the rows."""
        return iter(self.rows)

    def row(self, metric: str) -> ComparisonRow:
        """Return the row of a metric.

        Args:
            metric: The row's `metric`, such as `Total site energy`.

        Returns:
            The row.

        Raises:
            KeyError: If no row has that metric.
        """
        for row in self.rows:
            if row.metric == metric:
                return row
        raise KeyError(metric)

    @property
    def failures(self) -> tuple[ComparisonRow, ...]:
        """The rows outside their target (`within_target` is `False`)."""
        return tuple(row for row in self.rows if row.within_target is False)

    @property
    def passed(self) -> bool:
        """Whether no row is outside its target."""
        return not self.failures


def _row(  # noqa: PLR0913 - one argument per column of the row
    metric: str,
    kind: MetricKind,
    units: str,
    detailed: float,
    archetype: float,
    *,
    end_use: str | None = None,
    fuel: str | None = None,
    target: float | None = None,
    judged: bool = True,
) -> ComparisonRow:
    difference = archetype - detailed
    relative = difference / detailed if detailed != 0 else None
    within = None if target is None or not judged or relative is None else abs(relative) <= target
    return ComparisonRow(
        metric=metric,
        kind=kind,
        end_use=end_use,
        fuel=fuel,
        units=units,
        detailed=detailed,
        archetype=archetype,
        difference=difference,
        relative=relative,
        target=target,
        within_target=within,
    )


def _rows(detailed: RunResults, archetype: RunResults, targets: AcceptanceTargets) -> tuple[ComparisonRow, ...]:
    units = detailed.units
    total = detailed.total_site
    rows = [_row("Total site energy", "total_site", units, total, archetype.total_site, target=targets.total_site)]
    keys = sorted(set(detailed.end_uses) | set(archetype.end_uses), key=_end_use_order(detailed, archetype))
    for end_use, fuel in keys:
        value = detailed.end_uses.get((end_use, fuel), 0.0)
        # Heating and cooling are judged with distribution added; pumps and heat rejection never.
        judged_here = end_use not in {"Heating", "Cooling", *DISTRIBUTION_END_USES}
        rows.append(
            _row(
                f"{end_use}: {fuel}",
                "end_use",
                units,
                value,
                archetype.end_uses.get((end_use, fuel), 0.0),
                end_use=end_use,
                fuel=fuel,
                target=targets.end_use if judged_here else None,
                judged=total > 0 and value / total >= targets.end_use_min_share,
            )
        )
    for mode in ("Heating", "Cooling"):
        value = detailed.with_distribution(mode)
        rows.append(
            _row(
                f"{mode}, with pumps and heat rejection",
                "end_use_with_distribution",
                units,
                value,
                archetype.with_distribution(mode),
                end_use=mode,
                target=targets.end_use,
                judged=total > 0 and value / total >= targets.end_use_min_share,
            )
        )
    # Both runs' peaks at the finest frequency they share (an Hourly run against one with
    # Zone Timestep and Hourly meters compares hourly peaks).
    common = common_peak_frequency(detailed, archetype)
    detailed_peaks = detailed.peaks_by_frequency.get(common, detailed.peaks) if common else detailed.peaks
    archetype_peaks = archetype.peaks_by_frequency.get(common, archetype.peaks) if common else archetype.peaks
    larger = max(detailed_peaks.values(), default=0.0)
    for mode in ("Heating", "Cooling"):
        value = detailed_peaks.get(mode, 0.0)
        rows.append(
            _row(
                f"Peak {mode.lower()} demand",
                "peak",
                "W",
                value,
                archetype_peaks.get(mode, 0.0),
                end_use=mode,
                target=targets.peak,
                judged=larger > 0 and value / larger >= targets.peak_min_share,
            )
        )
    return tuple(rows)


def _end_use_order(*runs: RunResults) -> Callable[[tuple[str, str]], tuple[int, int]]:
    """Sort end uses in the order the End Uses table lists them, then fuels likewise."""
    uses: list[str] = []
    fuels: list[str] = []
    for run in runs:
        for use, fuel in run.end_uses:
            if use not in uses:
                uses.append(use)
            if fuel not in fuels:
                fuels.append(fuel)

    def key(item: tuple[str, str]) -> tuple[int, int]:
        return uses.index(item[0]), fuels.index(item[1])

    return key


def _open(results: str | os.PathLike[str] | SQLResult) -> tuple[SQLResult, str, bool]:
    if isinstance(results, SQLResult):
        return results, label_of(results), False
    path = Path(results)
    if not path.is_file():
        raise FileNotFoundError(path)
    return open_results(path, SQLResult), str(path), True


def compare(
    detailed: str | os.PathLike[str] | SQLResult,
    archetype: str | os.PathLike[str] | SQLResult,
    *,
    targets: AcceptanceTargets = AcceptanceTargets(),
    weather: str | os.PathLike[str] | None = None,
) -> ComparisonResult:
    """Compare the simulation results of a detailed model and of its archetype (FR-027).

    Both results must be EnergyPlus SQLite files written with `Output:SQLite`
    (`SimpleAndTabular`), with the *AllSummary* tabular reports and the `Heating:<fuel>` and
    `Cooling:<fuel>` meters; a result with pumps or heat rejection also needs their meters
    and the energy its HVAC equipment delivered (ideal loads, coils, baseboards, radiant
    systems), at the same frequency, to share them between heating and cooling. Results
    written for reduction (`RESULTS_REQUIREMENTS`) have all of these.

    Args:
        detailed: The detailed model's results: a path, or an open `SQLResult`.
        archetype: The archetype's results: a path, or an open `SQLResult`.
        targets: The acceptance targets the rows are judged against.
        weather: The weather file both runs should have used. Each result is checked against
            its name and location, and its SHA-256 is kept in the result.

    Returns:
        One row per compared quantity, with both values, their difference and whether it is
        within target.

    Raises:
        NotComparableError: If the results differ in weather, run period, units, timestep or
            meter reporting frequency, or lack what the comparison reads. It names every
            difference at once.
        FileNotFoundError: If a results path does not exist.
    """
    opened: list[SQLResult] = []
    try:
        runs: list[RunResults] = []
        for results in (detailed, archetype):
            sql, label, owned = _open(results)
            if owned:
                opened.append(sql)
            runs.append(read_run(sql, label))
    finally:
        for sql in opened:
            sql.close()
    first, second = runs
    weather_path = None if weather is None else Path(weather)
    found = [*first.problems, *second.problems, *differences(first, second, weather=weather_path)]
    if found:
        raise NotComparableError(f"{first.label} and {second.label}", found)  # noqa: TRY003 - names the inputs
    return ComparisonResult(
        rows=_rows(first, second, targets),
        targets=targets,
        weather_sha256=None if weather_path is None else sha256(weather_path),
    )
