"""Read what a comparison needs from one set of EnergyPlus results (spec 002, research R13).

For each run this module reads:

- **end uses by fuel**, from the tabular *Annual Building Utility Performance Summary*
  (*End Uses* table), in the run's tabular energy unit;
- **total site energy**, from the same report (*Site and Source Energy*);
- **peak heating and cooling demand**: the maximum, over the run period, of the summed
  `Heating:<fuel>` (and `Cooling:<fuel>`) end-use meters at the run's meter reporting
  frequency, divided by the length of a reporting interval (W);
- **the split of pumps and heat rejection** between heating and cooling: each interval's
  energy is shared in proportion to the energy delivered to the zones in each mode
  (`Zone Air System Sensible Heating/Cooling Energy`, times the zone multipliers), as
  research R12 does for reduction. Intervals with no delivery are not attributed;
- **the conditions comparability depends on** (FR-028): the weather file named in the
  *Input Verification and Results Summary*, with its location; the run period, from the
  meters' first and last intervals; the tabular energy unit; the timesteps per hour (the
  `Simulations` table); and the meters' reporting frequency.

Lookups that fail are collected as *problems*, so `compare` can name all of them at once.

The static tables (`Simulations`, `Zones`) are read through `archetypal.reduction._sql_tables`,
imported where it is used: importing `archetypal.reduction` loads epinterface, which reads its
settings from the environment, and `import archetypal` must not (FR-006).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from idfkit.exceptions import ResultLookupError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from idfkit.simulation import SQLResult
    from idfkit.simulation.parsers.sql import TimeSeriesResult, VariableInfo

__all__ = [
    "DISTRIBUTION_END_USES",
    "RunResults",
    "differences",
    "epw_location",
    "read_run",
    "sha256",
]

ABUPS = "AnnualBuildingUtilityPerformanceSummary"
INPUT_SUMMARY = "InputVerificationandResultsSummary"

DISTRIBUTION_END_USES = ("Pumps", "Heat Rejection")
"""End uses SBEM has no counterpart for; they are added to the heating and cooling they serve."""

_MODE_METERS = {"Heating": "Heating", "Cooling": "Cooling", "Pumps": "Pumps", "Heat Rejection": "HeatRejection"}
_NOT_FUELS = frozenset({"EnergyTransfer", "Water"})
_DELIVERED = {mode: f"Zone Air System Sensible {mode} Energy" for mode in ("Heating", "Cooling")}

# Meter reporting frequencies as the SQLite file names them, finest first.
_FREQUENCIES = ("HVAC System Timestep", "Zone Timestep", "Hourly", "Daily", "Monthly", "Run Period", "Annual")
_PEAK_FREQUENCIES = ("Zone Timestep", "Hourly", "Daily")


@dataclass(frozen=True)
class RunResults:
    """What a comparison reads from one run.

    Attributes:
        label: How the results are named in messages (their file path).
        units: The tabular energy unit (`GJ`, `kWh`, `kBtu`, ...).
        total_site: Total site energy, in `units`.
        end_uses: Each non-zero end use by fuel, as `(end use, fuel)`, in `units`.
        weather: The weather file as EnergyPlus names it, with its latitude and longitude.
        weather_name: The weather file's name alone (`<city> <state> <country> <source> WMO#=<n>`).
        timesteps_per_hour: The zone timesteps per hour.
        frequency: The finest reporting frequency of the heating and cooling meters.
        period: The run period as `(start, end)`, from the meters' first and last intervals.
        peaks: Peak demand by mode (`Heating`, `Cooling`), in W.
        to_heating: For each distribution end use, the fraction of its energy that served
            heating.
        to_cooling: For each distribution end use, the fraction that served cooling.
        problems: Lookups that failed; a run with problems cannot be compared.
    """

    label: str
    units: str = ""
    total_site: float = 0.0
    end_uses: dict[tuple[str, str], float] = field(default_factory=dict[tuple[str, str], float])
    weather: str = ""
    weather_name: str = ""
    timesteps_per_hour: int = 0
    frequency: str = ""
    period: tuple[datetime, datetime] | None = None
    peaks: dict[str, float] = field(default_factory=dict[str, float])
    to_heating: dict[str, float] = field(default_factory=dict[str, float])
    to_cooling: dict[str, float] = field(default_factory=dict[str, float])
    problems: tuple[str, ...] = ()

    def end_use_total(self, end_use: str) -> float:
        """Return an end use summed over every fuel, in `units`.

        Args:
            end_use: The end use as the End Uses table names it, such as `Heating`.

        Returns:
            Its total over every fuel.
        """
        return sum(value for (use, _fuel), value in self.end_uses.items() if use == end_use)

    def with_distribution(self, mode: str) -> float:
        """Return a mode's end use with its share of pumps and heat rejection added (SC-002).

        Args:
            mode: `Heating` or `Cooling`.

        Returns:
            The mode's end use over every fuel, plus the pumps and heat rejection that served
            it, in `units`.
        """
        shares = self.to_heating if mode == "Heating" else self.to_cooling
        added = sum(self.end_use_total(use) * shares.get(use, 0.0) for use in DISTRIBUTION_END_USES)
        return self.end_use_total(mode) + added


def label_of(results: str | Path | SQLResult) -> str:
    """Return how a set of results is named in messages: its path."""
    if isinstance(results, (str, Path)):
        return str(results)
    from archetypal.reduction._sql_tables import database_path  # noqa: PLC0415 - see the module docstring

    path = database_path(results)
    return "<SQLResult>" if path is None else str(path)


def sha256(path: str | Path) -> str:
    """Return the SHA-256 of a file, in hexadecimal."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def epw_location(path: str | Path) -> str:
    """Return a weather file's name as EnergyPlus reports it, from its `LOCATION` line.

    EnergyPlus names the weather file `<city> <state> <country> <source> WMO#=<number>`
    in the *Input Verification and Results Summary*.

    Args:
        path: The EPW file.

    Returns:
        The name, such as `Chicago Ohare Intl Ap IL USA TMY3 WMO#=725300`.

    Raises:
        ValueError: If the file does not start with a `LOCATION` line.
    """
    with Path(path).open(encoding="latin-1") as file:
        first = file.readline()
    fields = [part.strip() for part in first.split(",")]
    if len(fields) < 6 or fields[0].upper() != "LOCATION":  # noqa: PLR2004 - LOCATION and five fields
        msg = f"{path}: not an EPW file; its first line is not a LOCATION record"
        raise ValueError(msg)
    city, state, country, source, wmo = fields[1:6]
    return f"{city} {state} {country} {source} WMO#={wmo}"


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def _tabular(sql: SQLResult, report: str, table: str, row: str, column: str) -> tuple[str, str]:
    """Return a cell's text and units; raise `ResultLookupError` when it is absent."""
    rows = sql.get_tabular_data(report_name=report, table_name=table, row_name=row, column_name=column)
    if not rows:
        raise ResultLookupError(f"{report} / {table} / {row} / {column}")  # noqa: TRY003 - idfkit's error
    return rows[0].value, rows[0].units


def _read_energy(sql: SQLResult) -> tuple[str, float, dict[tuple[str, str], float]]:
    text, units = _tabular(sql, ABUPS, "Site and Source Energy", "Total Site Energy", "Total Energy")
    total = float(text)
    end_uses: dict[tuple[str, str], float] = {}
    for row in sql.get_tabular_data(report_name=ABUPS, table_name="End Uses"):
        if row.row_name == "Total End Uses" or row.column_name == "Water" or not row.value:
            continue
        value = row.as_float()
        if value != 0:
            end_uses[row.row_name, row.column_name] = value
    return units, total, end_uses


def _read_weather(sql: SQLResult) -> tuple[str, str]:
    """Return the weather file's name, and its name with its latitude and longitude.

    The elevation is left out: its unit follows the tabular unit system, which is checked
    on its own.
    """
    name, _ = _tabular(sql, INPUT_SUMMARY, "General", "Weather File", "Value")
    latitude, _ = _tabular(sql, INPUT_SUMMARY, "General", "Latitude", "Value")
    longitude, _ = _tabular(sql, INPUT_SUMMARY, "General", "Longitude", "Value")
    return name.strip(), f"{name.strip()} (latitude {latitude.strip()}, longitude {longitude.strip()})"


def _end_use_meters(variables: Iterable[VariableInfo]) -> dict[str, list[VariableInfo]]:
    """Group the end-use meters (`Heating:<fuel>`, ...) by end use."""
    meters: dict[str, list[VariableInfo]] = {use: [] for use in _MODE_METERS}
    for variable in variables:
        if not variable.is_meter:
            continue
        for use, prefix in _MODE_METERS.items():
            match = re.fullmatch(rf"{prefix}:(\w+)", variable.name)
            if match and match.group(1) not in _NOT_FUELS:
                meters[use].append(variable)
    return meters


def _finest(frequencies: Iterable[str]) -> str | None:
    ranked = sorted(set(frequencies), key=lambda f: _FREQUENCIES.index(f) if f in _FREQUENCIES else len(_FREQUENCIES))
    return ranked[0] if ranked else None


def _interval(frequency: str, timesteps_per_hour: int) -> timedelta:
    if frequency == "Zone Timestep":
        return timedelta(hours=1) / max(timesteps_per_hour, 1)
    if frequency == "Daily":
        return timedelta(days=1)
    return timedelta(hours=1)


def _summed(series: Sequence[TimeSeriesResult]) -> list[float]:
    if not series:
        return []
    return [sum(values) for values in zip(*(s.values for s in series), strict=True)]


@dataclass
class _Reader:
    """Reads one run, collecting the lookups that fail."""

    sql: SQLResult
    label: str
    problems: list[str] = field(default_factory=list[str])

    def read(self) -> RunResults:
        units, total, end_uses = self._energy()
        weather_name, weather = self._weather()
        timesteps = self._timesteps()
        meters = _end_use_meters(self.sql.list_variables())
        mode_meters = meters["Heating"] + meters["Cooling"]
        frequency = _finest(v.frequency for v in mode_meters)
        period: tuple[datetime, datetime] | None = None
        peaks: dict[str, float] = {}
        if frequency is None:
            self.problems.append(
                f"missing: {self.label} report no Heating:<fuel> or Cooling:<fuel> meter; "
                "add Output:Meter objects for them to the model and run it again"
            )
        elif frequency not in _PEAK_FREQUENCIES:
            self.problems.append(
                f"reporting frequency: {self.label} report the heating and cooling meters {frequency}; "
                f"peak demand needs them {', '.join(_PEAK_FREQUENCIES)}"
            )
        else:
            period, peaks = self._peaks(meters, frequency, timesteps)
        to_heating, to_cooling = self._distribution(meters, end_uses)
        return RunResults(
            label=self.label,
            units=units,
            total_site=total,
            end_uses=end_uses,
            weather=weather,
            weather_name=weather_name,
            timesteps_per_hour=timesteps,
            frequency=frequency or "",
            period=period,
            peaks=peaks,
            to_heating=to_heating,
            to_cooling=to_cooling,
            problems=tuple(self.problems),
        )

    def _energy(self) -> tuple[str, float, dict[tuple[str, str], float]]:
        try:
            return _read_energy(self.sql)
        except (ResultLookupError, ValueError):
            self.problems.append(
                f"missing: {self.label} have no Annual Building Utility Performance Summary; "
                "add Output:Table:SummaryReports (AllSummary) and Output:SQLite (SimpleAndTabular)"
            )
            return "", 0.0, {}

    def _weather(self) -> tuple[str, str]:
        try:
            return _read_weather(self.sql)
        except ResultLookupError:
            self.problems.append(
                f"missing: {self.label} have no Input Verification and Results Summary, which names the "
                "weather file; add Output:Table:SummaryReports (AllSummary)"
            )
            return "", ""

    def _timesteps(self) -> int:
        from archetypal.reduction._sql_tables import SQLTableError, read_simulations  # noqa: PLC0415

        try:
            simulations = read_simulations(self.sql)
        except SQLTableError as error:
            self.problems.append(f"missing: {self.label}: {error}")
            return 0
        return simulations[0].timesteps_per_hour if simulations else 0

    def _peaks(
        self, meters: dict[str, list[VariableInfo]], frequency: str, timesteps: int
    ) -> tuple[tuple[datetime, datetime] | None, dict[str, float]]:
        heating = [v for v in meters["Heating"] if v.frequency == frequency]
        cooling = [v for v in meters["Cooling"] if v.frequency == frequency]
        series = self.sql.get_timeseries_many([*heating, *cooling])
        step = _interval(frequency, timesteps)
        seconds = step.total_seconds()
        peaks = {
            "Heating": max(_summed(series[: len(heating)]), default=0.0) / seconds,
            "Cooling": max(_summed(series[len(heating) :]), default=0.0) / seconds,
        }
        stamps = series[0].timestamps
        period = (stamps[0] - step, stamps[-1]) if stamps else None
        return period, peaks

    def _distribution(
        self, meters: dict[str, list[VariableInfo]], end_uses: dict[tuple[str, str], float]
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Split pumps and heat rejection between heating and cooling by delivered mode (R12)."""
        to_heating: dict[str, float] = {}
        to_cooling: dict[str, float] = {}
        for use in DISTRIBUTION_END_USES:
            if not any(u == use for u, _ in end_uses):
                continue
            shares = self._split(meters[use], use)
            if shares is not None:
                to_heating[use], to_cooling[use] = shares
        return to_heating, to_cooling

    def _split(self, meters: list[VariableInfo], use: str) -> tuple[float, float] | None:
        variables = self.sql.list_variables()
        for frequency in sorted({v.frequency for v in meters}, key=_FREQUENCIES.index):
            delivered = {
                mode: [v for v in variables if v.name == name and v.frequency == frequency]
                for mode, name in _DELIVERED.items()
            }
            if not delivered["Heating"] and not delivered["Cooling"]:
                continue
            return self._shares([v for v in meters if v.frequency == frequency], delivered)
        self.problems.append(
            f"missing: {self.label} report {use} energy but not, at a common frequency, the "
            f"{use} meters and {_DELIVERED['Heating']} and {_DELIVERED['Cooling']} for every zone; "
            "they split it between heating and cooling"
        )
        return None

    def _shares(self, meters: list[VariableInfo], delivered: dict[str, list[VariableInfo]]) -> tuple[float, float]:
        from archetypal.reduction._sql_tables import SQLTableError, read_zones  # noqa: PLC0415

        try:
            zones = read_zones(self.sql)
        except SQLTableError as error:
            self.problems.append(f"missing: {self.label}: {error}")
            return 0.0, 0.0
        multipliers = {zone.name.upper(): float(zone.multiplier * zone.list_multiplier) for zone in zones}
        heating_vars, cooling_vars = delivered["Heating"], delivered["Cooling"]
        series = self.sql.get_timeseries_many([*meters, *heating_vars, *cooling_vars])
        energy = _summed(series[: len(meters)])
        mode_series = {
            "Heating": series[len(meters) : len(meters) + len(heating_vars)],
            "Cooling": series[len(meters) + len(heating_vars) :],
        }
        mode_delivered = {
            mode: [
                sum(multipliers.get(s.key_value.upper(), 1.0) * s.values[i] for s in found) for i in range(len(energy))
            ]
            for mode, found in mode_series.items()
        }
        total = sum(energy)
        if total == 0:
            return 0.0, 0.0
        heating = cooling = 0.0
        for i, value in enumerate(energy):
            both = mode_delivered["Heating"][i] + mode_delivered["Cooling"][i]
            if both > 0:
                heating += value * mode_delivered["Heating"][i] / both
                cooling += value * mode_delivered["Cooling"][i] / both
        return heating / total, cooling / total


def read_run(sql: SQLResult, label: str) -> RunResults:
    """Read what a comparison needs from one set of results.

    Args:
        sql: The results.
        label: How the results are named in messages.

    Returns:
        The run's end uses, peaks, distribution split and conditions, with every lookup that
        failed in `problems`.
    """
    return _Reader(sql, label).read()


def _format_period(period: tuple[datetime, datetime] | None) -> str:
    if period is None:
        return "unknown"
    start, end = period
    hours = (end - start).total_seconds() / 3600
    return f"{start:%m-%d %H:%M} to {end:%m-%d %H:%M} ({hours:g} hours)"


def differences(detailed: RunResults, archetype: RunResults, *, weather: str | Path | None = None) -> list[str]:
    """List every condition on which two runs differ (FR-028).

    Each item starts with what differs (`weather`, `run period`, `units`, `timestep`,
    `reporting frequency`), then gives both values.

    Args:
        detailed: The detailed model's run.
        archetype: The archetype's run.
        weather: The weather file both runs should have used; each run is checked against
            the name in its `LOCATION` line.

    Returns:
        The differences, in that order; empty when the runs are comparable.
    """
    found: list[str] = []
    if weather is not None:
        expected = epw_location(weather)
        found.extend(
            f"weather: {run.label} were run with {run.weather}, not {weather} ({expected})"
            for run in (detailed, archetype)
            if run.weather_name and _normal(run.weather_name) != _normal(expected)
        )
    elif _normal(detailed.weather) != _normal(archetype.weather):
        found.append(f"weather: {detailed.weather} for {detailed.label}, {archetype.weather} for {archetype.label}")
    if detailed.period is not None and archetype.period is not None and detailed.period != archetype.period:
        found.append(
            f"run period: {_format_period(detailed.period)} for {detailed.label}, "
            f"{_format_period(archetype.period)} for {archetype.label}"
        )
    if detailed.units and archetype.units and detailed.units != archetype.units:
        found.append(f"units: {detailed.units} for {detailed.label}, {archetype.units} for {archetype.label}")
    if 0 not in {detailed.timesteps_per_hour, archetype.timesteps_per_hour} and (
        detailed.timesteps_per_hour != archetype.timesteps_per_hour
    ):
        found.append(
            f"timestep: {detailed.timesteps_per_hour} per hour for {detailed.label}, "
            f"{archetype.timesteps_per_hour} per hour for {archetype.label}"
        )
    if detailed.frequency and archetype.frequency and detailed.frequency != archetype.frequency:
        found.append(
            f"reporting frequency: heating and cooling meters {detailed.frequency} for {detailed.label}, "
            f"{archetype.frequency} for {archetype.label}"
        )
    return found
