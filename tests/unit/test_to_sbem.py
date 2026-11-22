"""Tests for the ledger-to-SBEM conversion (spec 002, T039, T057, T085, T087; data-model.md, FR-025)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from epinterface.sbem.archetype import Archetype

from archetypal.errors import ReductionError
from archetypal.reduction import thermostats
from archetypal.reduction.airflow import AirflowHook
from archetypal.reduction.classify import classify
from archetypal.reduction.efficiency import efficiency_hook, fit_eir
from archetypal.reduction.envelope import FILMS, EnvelopeHook, assembly_capacities, assembly_u_factor
from archetypal.reduction.fans import effective_supply_delta, fans_hook, standard_air_density
from archetypal.reduction.grouping import Group, group_zones
from archetypal.reduction.hotwater import HotWaterHook
from archetypal.reduction.inventory import build_inventory
from archetypal.reduction.ledger import (
    AirflowTotals,
    EirSums,
    EnergyTotals,
    EnvelopeTotals,
    FanTotals,
    GainKind,
    GainTotals,
    GroupLedger,
    HotWaterTotals,
    OutdoorAirTotals,
    WeightedProfile,
    WindowTotals,
    gain_fields,
)
from archetypal.reduction.options import Layout
from archetypal.reduction.report import RULE_IDS, check_parameters
from archetypal.reduction.schedules import RunPeriodCalendar, ScheduleEvaluator, year_values
from archetypal.reduction.sources import load_sources
from archetypal.reduction.to_sbem import (
    BuildingFacts,
    Conversion,
    Derived,
    assemblies,
    conditioning_systems,
    dhw,
    equipment,
    floor_area_share,
    geometry,
    infiltration,
    lighting,
    occupancy,
    set_leaf_paths,
    storey_ratio,
    storeys,
    thermal_system,
    thermostat,
    to_archetype,
    ventilation,
    water_use,
    window,
)

if TYPE_CHECKING:
    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.features import NotRepresented

MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "models"
CAL = RunPeriodCalendar(year=2023)
HOURS = CAL.hours
HOUR = np.arange(HOURS)
DAYTIME = ((HOUR % 24 >= 8) & (HOUR % 24 < 18)).astype(np.float64)
SEASON = 0.5 + 0.5 * np.cos(2 * np.pi * HOUR / HOURS)  # 1 in winter, 0 in summer
OUTDOOR = 10.0 - 10.0 * np.cos(2 * np.pi * HOUR / HOURS)  # cold in winter


def _monthly(profile: np.ndarray) -> np.ndarray:
    return np.bincount(CAL.day_months.repeat(24), weights=profile, minlength=12)


def _ledger(name: str = "office", *, area: float = 1000.0, scale: float = 1.0) -> GroupLedger:
    """A ledger with every field set."""
    people = 50.0 * scale
    heating_d = 4e7 * SEASON * scale
    cooling_d = 3e7 * (1 - SEASON) * scale
    heating_c = heating_d / (3.0 + 0.05 * OUTDOOR)  # a heat pump: better when warmer
    oa = 0.4 * scale * (0.3 + 0.7 * DAYTIME)
    return GroupLedger(
        members=(f"{name} a", f"{name} b"),
        floor_area=area * scale,
        envelope={
            "exterior_wall": EnvelopeTotals(
                area=400.0 * scale,
                ua=200.0 * scale,
                capacity_inner=4e7 * scale,
                capacity_outer=2e7 * scale,
                area_by_orientation={"N": 100.0 * scale, "S": 100.0 * scale, "E": 100.0 * scale, "W": 100.0 * scale},
            ),
            "roof": EnvelopeTotals(
                area=300.0 * scale, ua=60.0 * scale, capacity_inner=1e7 * scale, capacity_outer=1e6 * scale
            ),
            "ground_floor": EnvelopeTotals(
                area=300.0 * scale, ua=90.0 * scale, capacity_inner=5e7 * scale, capacity_outer=3e7 * scale
            ),
            "floor_ceiling": EnvelopeTotals(
                area=600.0 * scale, ua=900.0 * scale, capacity_inner=6e7 * scale, capacity_outer=6e7 * scale
            ),
            "partition": EnvelopeTotals(
                area=200.0 * scale, ua=400.0 * scale, capacity_inner=2e6 * scale, capacity_outer=2e6 * scale
            ),
        },
        window_by_orientation={
            "S": WindowTotals(area=60.0 * scale, ua=120.0 * scale, a_shgc=24.0 * scale, a_vt=36.0 * scale),
            "N": WindowTotals(area=40.0 * scale, ua=80.0 * scale, a_shgc=16.0 * scale, a_vt=24.0 * scale),
        },
        internal_mass_capacity=8e7 * scale,
        internal_mass_area=500.0 * scale,
        gains={
            "people": GainTotals(installed=people, hourly=people * DAYTIME, radiant=0, latent=0, lost=0),
            "lights": GainTotals(installed=8000.0 * scale, hourly=8000.0 * scale * DAYTIME, radiant=1e9 * scale),
            "electric": GainTotals(installed=10000.0 * scale, hourly=10000.0 * scale * (0.2 + 0.8 * DAYTIME)),
            "gas": GainTotals(installed=2000.0 * scale, hourly=2000.0 * scale * DAYTIME, latent=1e8 * scale),
        },
        infiltration=AirflowTotals(
            design_flow=0.2 * scale,
            hourly=0.2 * scale * (1.0 - 0.75 * DAYTIME),
            constant_weighted=0.2 * scale * 0.6,
            temperature_weighted=0.2 * scale * 0.02,
            velocity_weighted=0.2 * scale * 0.1,
            velocity_squared_weighted=0.0,
        ),
        outdoor_air=OutdoorAirTotals(
            design_flow=0.4 * scale,
            hourly=oa,
            hrv_weighted={"Sensible": 0.8 * float(oa.sum()) * 3600, "NoHRV": 0.2 * float(oa.sum()) * 3600},
            economiser_weighted={"DifferentialDryBulb": float(oa.sum()) * 3600},
            effectiveness_weighted=0.75 * 0.8 * float(oa.sum()) * 3600,
        ),
        heating_setpoint=WeightedProfile(weight=area * scale, weighted=area * scale * (15.0 + 6.0 * DAYTIME)),
        cooling_setpoint=WeightedProfile(weight=area * scale, weighted=area * scale * (30.0 - 6.0 * DAYTIME)),
        hot_water=HotWaterTotals(volume=0.01 * scale * DAYTIME, heat=0.01 * scale * DAYTIME * 45.0),
        energy={
            "heating": EnergyTotals(
                delivered=float(heating_d.sum()),
                consumed_by_fuel={"Electricity": float(heating_c.sum())},
                distribution_by_fuel={"Electricity": 0.05 * float(heating_c.sum())},
                eir_sums=EirSums.from_hourly(consumed=heating_c, delivered=heating_d, outdoor_temperature=OUTDOOR),
            ),
            "cooling": EnergyTotals(
                delivered=float(cooling_d.sum()),
                consumed_by_fuel={"Electricity": float(cooling_d.sum()) / 3.5},
                eir_sums=EirSums.from_hourly(
                    consumed=cooling_d / 3.5, delivered=cooling_d, outdoor_temperature=OUTDOOR
                ),
            ),
            "hot_water": EnergyTotals(
                delivered=float((0.01 * scale * DAYTIME * 45.0).sum()) * 4.18e6,
                consumed_by_fuel={"NaturalGas": float((0.01 * scale * DAYTIME * 45.0).sum()) * 4.18e6 / 0.9},
            ),
        },
        fans=FanTotals(
            energy=2e9 * scale,
            volume=2e6 * scale,
            volume_in_mode={"heating": 8e5 * scale, "cooling": 9e5 * scale},
            delivered_in_mode={"heating": 8e9 * scale, "cooling": 9e9 * scale},
            volume_without_demand=1e4 * scale,
        ),
    )


def _core_ledger() -> GroupLedger:
    """A core group: no exterior surface, no windows, no infiltration, a rated heating system only."""
    full = _ledger("core", area=500.0)
    return full.model_copy(
        update={
            "envelope": {k: v for k, v in full.envelope.items() if k in ("floor_ceiling", "partition")},
            "window_by_orientation": {},
            "infiltration": AirflowTotals(),
            "energy": {
                "heating": EnergyTotals(rated_weight=500.0, rated_weighted=500.0 * 0.95),
                "cooling": full.energy["cooling"],
            },
        }
    )


def _facts() -> BuildingFacts:
    return BuildingFacts(calendar=CAL, storey_ratio=3.4, mains_temperature=12.0)


# --- one rule per SBEM field ---------------------------------------------------------------------


def test_area_share_and_storeys() -> None:
    share = floor_area_share(_ledger(), 4000.0)
    assert share.value == 0.25
    assert share.rule == "area.share"
    assert [s.value for s in map(storeys, (0.4, 1.0, 3.4, 3.6, 10.0))] == [1, 1, 3, 4, 10]
    assert storeys(3.6).rule == "geometry.storeys"


def test_gain_density_and_normalised_schedules_conserve_monthly_energy() -> None:
    ledger = _ledger()
    occ, lights, equip = (
        occupancy(ledger, CAL, name="g"),
        lighting(ledger, CAL, name="g"),
        equipment(ledger, CAL, name="g"),
    )

    assert occ.value.PeopleDensity == 50.0 / 1000.0
    assert lights.value.PowerDensity == 8.0
    assert equip.value.PowerDensity == 12.0  # electric + gas
    cases: tuple[tuple[object, tuple[GainKind, ...]], ...] = (
        (occ, ("people",)),
        (lights, ("lights",)),
        (equip, ("electric", "gas")),
    )
    for derived_any, kinds in cases:
        derived = cast("Derived[Any]", derived_any)
        assert derived.rule == "gain.density"
        installed = sum(ledger.gains[k].installed for k in kinds)
        hourly = np.sum([ledger.gains[k].hourly for k in kinds], axis=0)
        rebuilt = installed * year_values(derived.value.Schedule, CAL)
        np.testing.assert_allclose(_monthly(rebuilt), _monthly(hourly), rtol=1e-12)
        rules = {leaf.path: leaf.rule for leaf in derived.leaves}
        assert rules["Schedule"] == "schedule.normalised"
    fuel = [e for e in equip.not_represented if e.feature == "Fuel of non-electric equipment"]
    assert fuel
    assert fuel[0].magnitude == pytest.approx(float(ledger.gains["gas"].hourly.sum()) * 3600)


def test_setpoint_area_mean() -> None:
    derived = thermostat(_ledger(), CAL, name="g")
    assert derived.rule == "setpoint.area_mean"
    np.testing.assert_allclose(year_values(derived.value.HeatingSchedule, CAL), 15.0 + 6.0 * DAYTIME)
    np.testing.assert_allclose(year_values(derived.value.CoolingSchedule, CAL), 30.0 - 6.0 * DAYTIME)
    unheated = thermostat(_ledger().model_copy(update={"heating_setpoint": WeightedProfile()}), CAL, name="g")
    np.testing.assert_array_equal(year_values(unheated.value.HeatingSchedule, CAL), np.full(HOURS, 5.0))


def test_envelope_equivalent_and_internal_mass() -> None:
    ledger = _ledger()
    derived = assemblies(ledger, ledger, name="g")
    a = derived.value
    assert derived.rule == "envelope.equivalent"
    assert assembly_u_factor(a.FacadeAssembly, "exterior_wall") == pytest.approx(200.0 / 400.0, rel=1e-12)
    assert assembly_u_factor(a.FlatRoofAssembly, "roof") == pytest.approx(60.0 / 300.0, rel=1e-12)
    assert assembly_u_factor(a.GroundSlabAssembly, "ground_floor") == pytest.approx(0.3, rel=1e-12)
    inner, outer = assembly_capacities(a.FacadeAssembly)
    assert (inner, outer) == (pytest.approx(4e7 / 400.0), pytest.approx(2e7 / 400.0))
    assert a.FacadeAssembly.Type == "Facade"
    assert a.AtticRoofAssembly.Type == "AtticRoof"
    assert a.InternalMassExposedAreaPerArea == 0.5
    assert a.InternalMassAssembly is not None
    rules = {leaf.path: leaf.rule for leaf in derived.leaves}
    assert rules["InternalMassAssembly"] == rules["InternalMassExposedAreaPerArea"] == "mass.internal"
    assert rules["FacadeAssembly"] == "envelope.equivalent"


def test_assembly_slots_a_group_lacks_come_from_the_building() -> None:
    core, building = _core_ledger(), _ledger() + _core_ledger()
    a = assemblies(core, building, name="core").value
    walls = building.envelope["exterior_wall"]
    assert assembly_u_factor(a.FacadeAssembly, "exterior_wall") == pytest.approx(walls.ua / walls.area, rel=1e-12)
    assert set(FILMS) >= {"exterior_wall"}


def test_window_area_weighted() -> None:
    derived = window(_ledger(), name="g")
    assert derived.rule == "window.area_weighted"
    assert derived.value is not None
    assert (derived.value.UValue, derived.value.SHGF, derived.value.TVis) == pytest.approx((2.0, 0.4, 0.6))
    assert window(_core_ledger(), name="core").value is None


def test_infiltration_mean_per_exterior_area_with_schedule() -> None:
    ledger = _ledger()
    derived = infiltration(ledger, CAL, name="g")
    inf = derived.value
    assert derived.rule == "airflow.mean_per_exterior_area"
    exterior = 400.0 + 300.0 + 100.0  # walls, roof, windows
    mean = float(ledger.infiltration.hourly.mean())
    assert inf.FlowPerExteriorSurfaceArea == pytest.approx(mean / exterior, rel=1e-12)
    assert inf.CalculationMethod == "Flow/ExteriorArea"
    assert (inf.ConstantCoefficient, inf.TemperatureCoefficient, inf.WindVelocityCoefficient) == pytest.approx((
        0.6,
        0.02,
        0.1,
    ))
    assert inf.Schedule is not None
    rebuilt = inf.FlowPerExteriorSurfaceArea * exterior * year_values(inf.Schedule, CAL)
    np.testing.assert_allclose(_monthly(rebuilt), _monthly(ledger.infiltration.hourly), rtol=1e-12)
    assert "Infiltration response to weather" in {e.feature for e in derived.not_represented}
    core = infiltration(_core_ledger(), CAL, name="core")
    assert not core.value.IsOn


def test_ventilation_peak_per_area_and_dominant_categories() -> None:
    ledger = _ledger()
    derived = ventilation(ledger, CAL, name="g")
    vent = derived.value
    assert derived.rule == "airflow.peak_per_area"
    assert vent.FreshAirPerFloorArea == pytest.approx(0.4 / 1000.0, rel=1e-12)
    assert vent.FreshAirPerPerson == 0.0
    rebuilt = vent.FreshAirPerFloorArea * 1000.0 * year_values(vent.Schedule, CAL)
    np.testing.assert_allclose(_monthly(rebuilt), _monthly(ledger.outdoor_air.hourly), rtol=1e-12)
    assert (vent.Provider, vent.HRV, vent.Economizer, vent.DCV) == (
        "Mechanical",
        "Sensible",
        "DifferentialDryBulb",
        "NoDCV",
    )
    assert vent.SensibleHeatRecoveryEffectiveness == pytest.approx(0.75)
    rules = {leaf.path: leaf.rule for leaf in derived.leaves}
    assert rules["HRV"] == rules["SensibleHeatRecoveryEffectiveness"] == "airflow.dominant_category"
    features = {e.feature for e in derived.not_represented}
    assert "Heat recovery categories other than Sensible" in features
    assert "Hourly profile of mechanical outdoor air" in features


def test_hot_water_volume_per_person_and_mains_plus_rise() -> None:
    ledger = _ledger()
    use = water_use(ledger, CAL, name="g")
    annual = float(ledger.hot_water.volume.sum())
    assert use.rule == "dhw.volume_per_person"
    assert use.value.FlowRatePerPerson * 50.0 * CAL.days == pytest.approx(annual, rel=1e-12)
    assert use.value.Schedule.schedule_type_limits == "Fraction"
    hw = dhw(ledger, ledger, 12.0, name="g")
    assert hw.rule == "dhw.mains_plus_rise"
    assert (hw.value.WaterTemperatureInlet, hw.value.WaterSupplyTemperature) == pytest.approx((12.0, 57.0))
    assert hw.value.SystemCOP == pytest.approx(0.9)
    assert hw.value.FuelType == "NaturalGas"
    rules = {leaf.path: leaf.rule for leaf in hw.leaves}
    assert rules["SystemCOP"] == "efficiency.delivered_over_consumed"
    assert rules["WaterSupplyTemperature"] == "dhw.mains_plus_rise"


def test_efficiency_delivered_over_consumed_with_eir_slope() -> None:
    ledger = _ledger()
    heating = thermal_system(ledger, ledger, "heating", name="g")
    system = heating.value
    assert system is not None
    totals = ledger.energy["heating"]
    primary = totals.consumed_by_fuel["Electricity"]
    assert heating.rule == "efficiency.delivered_over_consumed"
    assert system.SystemCOP == pytest.approx(totals.delivered / primary, rel=1e-12)
    assert system.DistributionCOP == pytest.approx(1 / 1.05, rel=1e-12)  # pumps folded, fans not
    a, b, t_ref = fit_eir(totals.eir_sums)
    assert system.EIRTemperatureSlope == pytest.approx(b)
    assert system.EIRReferenceTemperature == pytest.approx(t_ref)
    assert b < 0  # the heat pump's input ratio falls as it warms
    assert 1 / system.SystemCOP == pytest.approx(a, rel=1e-12)
    # annual consumption is exact with the slope, as epinterface applies it
    consumed = float((OUTDOOR * 0 + 4e7 * SEASON * system.energy_input_ratio(OUTDOOR) * system.DistributionCOP).sum())
    assert consumed == pytest.approx(primary, rel=1e-9)
    rules = {leaf.path: leaf.rule for leaf in heating.leaves}
    assert rules["EIRTemperatureSlope"] == rules["EIRReferenceTemperature"] == "efficiency.eir_linear"
    cooling = thermal_system(ledger, ledger, "cooling", name="g").value
    assert cooling is not None
    assert cooling.SystemCOP == pytest.approx(3.5)
    assert cooling.EIRTemperatureSlope == pytest.approx(0.0, abs=1e-12)


def test_efficiency_rated_without_delivery() -> None:
    derived = thermal_system(_core_ledger(), _ledger(), "heating", name="core")
    assert derived.rule == "efficiency.rated"
    assert derived.value is not None
    assert derived.value.SystemCOP == pytest.approx(0.95)
    assert derived.value.Fuel == "Electricity"  # the building's heating fuel
    assert derived.value.EIRTemperatureSlope == 0.0


def test_fans_energy_per_volume_and_effective_supply_delta() -> None:
    ledger = _ledger()
    derived = conditioning_systems(ledger, ledger, name="g", air_density=standard_air_density(0.0))
    systems = derived.value
    assert systems.SpecificFanPower == pytest.approx(1000.0)  # 2e9 J / 2e6 m3
    dh = effective_supply_delta(ledger.fans, "heating")
    dc = effective_supply_delta(ledger.fans, "cooling")
    assert dh is not None
    assert dc is not None
    assert systems.MaximumHeatingSupplyAirTemperature == pytest.approx(21.0 + dh)
    assert systems.MinimumCoolingSupplyAirTemperature == pytest.approx(24.0 - dc)
    rules = {leaf.path: leaf.rule for leaf in derived.leaves}
    assert rules["SpecificFanPower"] == "fans.energy_per_volume"
    assert rules["MaximumHeatingSupplyAirTemperature"] == "fans.effective_supply_delta"
    assert rules["MinimumCoolingSupplyAirTemperature"] == "fans.effective_supply_delta"
    features = {e.feature for e in derived.not_represented}
    assert "Fan air volume without load or outdoor-air demand" in features


def test_crossing_supply_limits_keep_the_larger_mode() -> None:
    fans = FanTotals(
        energy=1e9,
        volume=1e8,
        volume_in_mode={"heating": 1e8, "cooling": 1e8},
        delivered_in_mode={"heating": 1e9, "cooling": 2e9},
    )
    ledger = _ledger().model_copy(update={"fans": fans})
    derived = conditioning_systems(ledger, ledger, name="g", air_density=standard_air_density(0.0))
    systems = derived.value
    assert systems.MaximumHeatingSupplyAirTemperature > systems.MinimumCoolingSupplyAirTemperature
    assert systems.MaximumHeatingSupplyAirTemperature == 30.0  # dropped: back to epinterface's default
    assert any("MaximumHeatingSupplyAirTemperature" in e.feature for e in derived.not_represented)


def test_geometry_per_orientation() -> None:
    building = _ledger()
    derived = geometry(building, 3.4)
    geo = derived.value
    assert geo.Storeys == 3
    assert geo.ConditionedFloorArea == 1000.0
    assert geo.WindowToWallRatio is not None
    assert geo.FacadeAreaPerFloorArea is not None
    assert geo.WindowToWallRatio["S"] == pytest.approx(60.0 / 160.0)
    assert geo.WindowToWallRatio["E"] == 0.0
    assert geo.WindowToWallRatio["NE"] == 0.0
    assert geo.FacadeAreaPerFloorArea["N"] == pytest.approx(0.14)
    assert geo.RoofAreaPerFloorArea == pytest.approx(0.3)
    assert geo.GroundContactAreaPerFloorArea == pytest.approx(0.3)
    rules = {leaf.path: leaf.rule for leaf in derived.leaves}
    assert rules == {
        "Storeys": "geometry.storeys",
        "ConditionedFloorArea": "area.share",
        "WindowToWallRatio": "window.area_weighted",
        "FacadeAreaPerFloorArea": "envelope.equivalent",
        "RoofAreaPerFloorArea": "envelope.equivalent",
        "ExposedFloorAreaPerFloorArea": "envelope.equivalent",
        "GroundContactAreaPerFloorArea": "envelope.equivalent",
    }


# --- the archetype -------------------------------------------------------------------------------


def _groups() -> list[Group]:
    return [
        Group(key=("office", "core"), ledger=_core_ledger()),
        Group(key=("office", "perimeter"), ledger=_ledger()),
    ]


def test_archetype_validates_and_every_set_leaf_has_a_parameter() -> None:
    conversion = to_archetype(_groups(), Layout.SPACE_USE_EXPOSURE, _facts(), name="office")
    archetype = conversion.archetype

    assert Archetype.from_json(archetype.to_json()) == archetype
    assert [g.Name for g in archetype.Groups] == ["office / core", "office / perimeter"]
    assert [g.Exposure for g in archetype.Groups] == ["core", "perimeter"]
    assert sum(g.FloorAreaShare or 0 for g in archetype.Groups) == pytest.approx(1.0)
    assert archetype.Geometry.Storeys == 3
    assert conversion.storey_ratio == 3.4
    assert conversion.conditioned_floor_area == 1500.0

    set_paths = set(set_leaf_paths(archetype))
    listed = {(p.group, p.path) for p in conversion.parameters}
    assert set_paths <= listed
    assert all(p.rule in RULE_IDS for p in conversion.parameters)
    assert len(listed) == len(conversion.parameters)
    used = {p.rule for p in conversion.parameters}
    assert used == RULE_IDS  # every rule of the derivation table produces a field


def test_check_parameters_accepts_the_conversion() -> None:
    conversion = to_archetype(_groups(), Layout.SPACE_USE_EXPOSURE, _facts(), name="office")
    counts: dict[tuple[str | None, str], int] = {}
    for p in conversion.parameters:
        counts[p.group, p.path] = counts.get((p.group, p.path), 0) + 1
    assert max(counts.values()) == 1
    assert callable(check_parameters)


def test_layout_without_exposure_leaves_it_unset() -> None:
    ledger = _ledger() + _core_ledger()
    conversion = to_archetype([Group(key=("office",), ledger=ledger)], Layout.SPACE_USE, _facts(), name="office")
    (group,) = conversion.archetype.Groups
    assert group.Exposure is None
    assert group.FloorAreaShare == 1.0


def test_up8_and_up2_fields_are_written_not_listed() -> None:
    conversion = to_archetype(_groups(), Layout.SPACE_USE_EXPOSURE, _facts(), name="office")
    perimeter = conversion.archetype.group("office / perimeter").Zone
    systems = perimeter.Operations.HVAC.ConditioningSystems
    assert systems.SpecificFanPower is not None
    assert systems.Heating is not None
    assert systems.Heating.EIRTemperatureSlope != 0.0
    assert perimeter.Envelope.Infiltration.Schedule is not None
    assert perimeter.Operations.HVAC.Ventilation.SensibleHeatRecoveryEffectiveness is not None
    assert conversion.archetype.Geometry.WindowToWallRatio is not None
    features = {e.feature for e in conversion.not_represented}
    for gone in ("Fan energy", "Infiltration schedule", "Window ratios by orientation", "Holidays"):
        assert gone not in features
    assert "Design-day schedule profiles" in features
    entries: list[NotRepresented] = list(conversion.not_represented)
    assert all(e.source in {"to_sbem", "schedules", "airflow", "efficiency", "fans", "hotwater"} for e in entries)


def test_holidays_reach_the_week_slots() -> None:
    cal = RunPeriodCalendar(year=2023, holidays=frozenset({date(2023, 7, 4)}))
    facts = BuildingFacts(calendar=cal, storey_ratio=1.0, mains_temperature=12.0)
    conversion = to_archetype(_groups(), Layout.SPACE_USE_EXPOSURE, facts, name="office")
    schedule = conversion.archetype.group("office / perimeter").Zone.Operations.SpaceUse.Occupancy.Schedule
    assert schedule.July.Holiday is not None
    assert schedule.June.Holiday is None


def test_validation_failure_raises_reduction_error_with_epinterfaces_message() -> None:
    too_much_air = _ledger().model_copy(
        update={"outdoor_air": OutdoorAirTotals(design_flow=1e3, hourly=np.full(HOURS, 100.0))}
    )
    with pytest.raises(ReductionError, match="FreshAirPerFloorArea"):
        to_archetype([Group(key=("office",), ledger=too_much_air)], Layout.SPACE_USE, _facts(), name="office")


# --- storeys on the fixtures (R6, FR-024) ------------------------------------------------------------


def _classified(model: str) -> tuple[ClassifiedZone, ...]:
    sources = load_sources(MODELS / f"{model}.idf", MODELS / f"{model}.sql")
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    return classify(build_inventory(sources, evaluate), evaluate)


@pytest.mark.parametrize(("model", "expected"), [("ten_zone_multipliers", 12), ("three_zone", 1)])
def test_storeys_of_the_fixtures(model: str, expected: int) -> None:
    zones = _classified(model)
    ratio = storey_ratio(zones)
    assert storeys(ratio).value == expected


def test_storey_ratio_counts_multiplied_typical_floors_like_drawn_ones() -> None:
    assert storey_ratio(_classified("ten_zone_multipliers")) == pytest.approx(
        storey_ratio(_classified("ten_zone_explicit")), rel=1e-3
    )


# --- real ledgers -----------------------------------------------------------------------------------


def _reduce_fixture(model: str, layout: Layout) -> Conversion:
    sources = load_sources(MODELS / f"{model}.idf", MODELS / f"{model}.sql")
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    zones = classify(build_inventory(sources, evaluate), evaluate)
    conditioned = [z for z in zones if z.role == "conditioned"]
    hot_water = HotWaterHook.from_sources(sources)
    hooks = [
        gain_fields,
        EnvelopeHook(zones),
        AirflowHook.from_model(sources.model),
        thermostats.ledger_fields,
        hot_water,
        efficiency_hook(sources, zones, evaluate),
        fans_hook(sources, zones),
    ]
    ledgers = [(z, GroupLedger.from_zone(z, evaluate, hooks=hooks)) for z in conditioned]
    grouping = group_zones(ledgers, layout=layout, threshold=0.05)
    mains = float(np.mean(hot_water.mains)) if hot_water.mains.size else None
    facts = BuildingFacts(
        calendar=sources.run_period.calendar, storey_ratio=storey_ratio(zones), mains_temperature=mains
    )
    return to_archetype(grouping.groups, layout, facts, name=model)


@pytest.mark.parametrize("model", ["three_zone", "ten_zone_multipliers"])
def test_fixture_reductions_validate_with_a_parameter_per_set_leaf(model: str) -> None:
    conversion = _reduce_fixture(model, Layout.SPACE_USE_EXPOSURE)
    archetype = conversion.archetype
    assert Archetype.from_json(archetype.to_json()) == archetype
    listed = {(p.group, p.path) for p in conversion.parameters}
    assert set(set_leaf_paths(archetype)) <= listed
    assert all(p.rule in RULE_IDS for p in conversion.parameters)
