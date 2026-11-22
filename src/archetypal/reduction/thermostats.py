"""Thermostat setpoints of a zone, for the group ledger (spec 002, research R10, FR-020).

The setpoint schedules themselves are read in `inventory`: `ZoneControl:Thermostat` is
dispatched with `match` on the `Literal` `control_n_object_type` to its `ThermostatSetpoint:*`
object (R18), and `ThermostatRecord.setpoints` evaluates them hour by hour under the
control-type schedule. This module turns them into the ledger's additive fields.

Rules
-----
- A zone is **heated** (or **cooled**) when its setpoint for that mode lies within `BAND`
  (5 to 35 °C, inclusive) at some hour; a zone without a thermostat is neither.
- A heated zone adds its floor area to `heating_setpoint.weight` and floor area · setpoint to
  `heating_setpoint.weighted`, hour by hour; the group's setpoint is `weighted / weight`
  (`WeightedProfile.value`), the floor-area-weighted mean over its heated members. Cooling is
  the same. This rule is representative, not conserving (FR-020).
- A zone not heated adds its floor area to `unheated_area` (cooling: `uncooled_area`), so the
  report can state the share of floor area not heated or not cooled.

Hours a heated zone does not heat
---------------------------------
A heated zone can still switch the mode off at some hours: a setback to -100 °C, a control
type that does not set the mode, or an uncontrolled hour (control type 0). A mean needs a value
at every hour, and the -100 °C itself would drag the mean far outside any real setpoint. So,
a decision of this module, each hour's setpoint is **clamped to the band**, and an hour without
a setpoint takes the band edge that leaves the mode off: 5 °C for heating, 35 °C for cooling.
In SBEM those values keep the mode off as the detailed model did, except where the zone would
fall below 5 °C or rise above 35 °C.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import numpy as np

from archetypal.reduction.inventory import BAND
from archetypal.reduction.ledger import DesignDays, WeightedProfile
from archetypal.reduction.schedules import design_day_evaluators

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.inventory import Mode
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator

__all__ = ["BAND", "ThermostatFields", "band_profile", "is_enabled", "ledger_fields", "setpoint_fields"]


class ThermostatFields(TypedDict):
    """The ledger fields this module fills, for one copy of a zone."""

    heating_setpoint: WeightedProfile
    cooling_setpoint: WeightedProfile
    unheated_area: float
    uncooled_area: float


_OFF: dict[Mode, float] = {"heating": BAND[0], "cooling": BAND[1]}


def is_enabled(setpoint: NDArray[np.float64]) -> bool:
    """Whether a setpoint lies within `BAND` at some hour (NaN hours set nothing).

    Args:
        setpoint: Hourly setpoint, °C, NaN where no control sets the mode.

    Returns:
        `True` when the mode is enabled at some hour.
    """
    low, high = BAND
    with np.errstate(invalid="ignore"):
        return bool(((setpoint >= low) & (setpoint <= high)).any())


def band_profile(setpoint: NDArray[np.float64], mode: Mode) -> NDArray[np.float64]:
    """Clamp a setpoint to `BAND`, filling hours without one with the edge that leaves `mode` off.

    Args:
        setpoint: Hourly setpoint, °C, NaN where no control sets the mode.
        mode: `heating` (missing hours become 5 °C) or `cooling` (35 °C).

    Returns:
        The clamped hourly setpoint, °C.
    """
    low, high = BAND
    filled = np.array(setpoint, dtype=np.float64)
    filled[np.isnan(filled)] = _OFF[mode]
    filled[filled < low] = low
    filled[filled > high] = high
    return filled


def setpoint_fields(zone: ClassifiedZone, evaluate: Callable[[str], Profile]) -> ThermostatFields:
    """Return the thermostat ledger fields of one copy of `zone`.

    Whether a mode is enabled is decided on the run period; an enabled mode's design days (when
    `evaluate` is a `ScheduleEvaluator`) are the setpoints the thermostat selects on each design
    day, clamped to `BAND` as the hourly ones.

    Args:
        zone: The classified zone.
        evaluate: Returns a schedule's hourly profile by name.

    Returns:
        `heating_setpoint`, `cooling_setpoint` (`WeightedProfile`), `unheated_area` and
        `uncooled_area` (m²).
    """
    record = zone.zone
    area = record.floor_area
    fields = ThermostatFields(
        heating_setpoint=WeightedProfile(), cooling_setpoint=WeightedProfile(), unheated_area=area, uncooled_area=area
    )
    if record.thermostat is None:
        return fields
    thermostat = record.thermostat
    heating, cooling = thermostat.setpoints(evaluate)
    design = design_day_evaluators(evaluate)
    days = {kind: thermostat.setpoints(on) for kind, on in design.items()} if design is not None else None

    def design_days(mode: Mode) -> DesignDays:
        if days is None:
            return DesignDays()
        index = 0 if mode == "heating" else 1
        return DesignDays.of(area, band_profile(days["summer"][index], mode), band_profile(days["winter"][index], mode))

    if is_enabled(heating):
        fields["heating_setpoint"] = WeightedProfile(
            weight=area, weighted=area * band_profile(heating, "heating"), design_days=design_days("heating")
        )
        fields["unheated_area"] = 0.0
    if is_enabled(cooling):
        fields["cooling_setpoint"] = WeightedProfile(
            weight=area, weighted=area * band_profile(cooling, "cooling"), design_days=design_days("cooling")
        )
        fields["uncooled_area"] = 0.0
    return fields


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> ThermostatFields:
    """The thermostat domain hook of `GroupLedger.from_zone` (one copy, multiplier not applied).

    Args:
        zone: The classified zone.
        schedules: The model's schedule evaluator.

    Returns:
        `heating_setpoint`, `cooling_setpoint`, `unheated_area` and `uncooled_area`.
    """
    return setpoint_fields(zone, schedules)
