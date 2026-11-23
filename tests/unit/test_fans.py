"""Tests for fan energy and air volume (spec 002, T037; FR-022a, research R19)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from idfkit import new_document

from archetypal.reduction.fans import (
    AIR_SPECIFIC_HEAT,
    BuildingFans,
    FanAttribution,
    FanSeries,
    air_loops,
    attribute_fans,
    building_fans,
    effective_supply_delta,
    fans_hook,
    ledger_fields,
    specific_fan_power,
    standard_air_density,
)
from archetypal.reduction.ledger import FanTotals, GroupLedger

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

MODELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "models"
RHO = standard_air_density(0.0)


def _a(*values: float) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def _data(fans: tuple[FanSeries, ...], **overrides: object) -> BuildingFans:
    """Zones A (multiplier 1) and B (multiplier 2) over three hours."""
    values: dict[str, object] = {
        "fans": fans,
        "inlet_flow": {"A": _a(1.0, 0.0, 1.0), "B": _a(3.0, 2.0, 0.0)},
        "multipliers": {"A": 1, "B": 2},
        "floor_area": {"A": 100.0, "B": 50.0},
        "delivered": {
            "heating": {"A": _a(1000.0, 0.0, 0.0), "B": _a(0.0, 500.0, 0.0)},
            "cooling": {"A": _a(0.0, 0.0, 0.0), "B": _a(300.0, 0.0, 0.0)},
        },
        "outdoor_air": {"A": _a(0.1, 0.0, 0.0), "B": _a(0.0, 0.0, 0.0)},
        "air_density": RHO,
    }
    values.update(overrides)
    return BuildingFans(**values)  # pyright: ignore[reportArgumentType]


LOOP = FanSeries("AHU fan", energy=_a(400.0, 200.0, 100.0), mass_flow=_a(4.0, 2.0, 1.0), loop_zones=("A", "B"))


def test_standard_density_is_energyplus_std_rho_air() -> None:
    assert pytest.approx(1.204309, abs=1e-6) == RHO
    assert standard_air_density(1000.0) < RHO


def test_zone_equipment_fan_belongs_to_its_zone_per_copy() -> None:
    fan = FanSeries("PTHP fan", energy=_a(60.0, 0.0, 0.0), mass_flow=_a(0.5, 0.0, 0.0), zone="B")
    result = attribute_fans(_data((fan,)))
    assert result.zones["B"].energy == pytest.approx(30.0)  # outputs cover every copy
    assert result.zones["B"].volume == pytest.approx(0.25 * 3600 / RHO)
    assert result.zones["A"].energy == 0.0


def test_air_loop_fan_is_split_by_hourly_inlet_node_flow() -> None:
    result = attribute_fans(_data((LOOP,)))
    # hour 0: A 1/4, B 3/4 (all copies); hour 1: B only; hour 2: A only.
    assert result.zones["A"].energy == pytest.approx(100.0 + 100.0)
    assert result.zones["B"].energy == pytest.approx((300.0 + 200.0) / 2)
    total = sum(result.multipliers_applied(z).energy for z in ("A", "B"))
    assert total == pytest.approx(700.0)
    volume = sum(result.multipliers_applied(z).volume for z in ("A", "B"))
    assert volume == pytest.approx(7.0 * 3600 / RHO)


def test_hours_without_inlet_flow_fall_back_to_the_annual_share() -> None:
    data = _data((LOOP,), inlet_flow={"A": _a(0.0, 0.0, 0.0), "B": _a(0.0, 1.0, 0.0)})
    result = attribute_fans(data)
    assert result.zones["B"].energy * 2 + result.zones["A"].energy == pytest.approx(700.0)


def test_specific_fan_power_times_volume_is_fan_energy() -> None:
    result = attribute_fans(_data((LOOP,)))
    group = result.zones["A"] + result.zones["B"].scaled(2)
    sfp = specific_fan_power(group)
    assert sfp is not None
    assert sfp * group.volume == pytest.approx(700.0)
    assert specific_fan_power(FanTotals()) is None


def test_volume_per_mode_and_effective_supply_delta() -> None:
    result = attribute_fans(_data((LOOP,)))
    a = result.zones["A"]
    # A heats in hour 0 only: volume 1 kg/s * 3600 / rho, delivered 1000 J.
    assert a.volume_in_mode["heating"] == pytest.approx(3600 / RHO)
    assert a.delivered_in_mode["heating"] == pytest.approx(1000.0)
    delta = effective_supply_delta(a, "heating", air_density=RHO)
    assert delta == pytest.approx(1000.0 / (RHO * AIR_SPECIFIC_HEAT * 3600 / RHO))
    assert effective_supply_delta(a, "cooling", air_density=RHO) is None
    b = result.zones["B"]
    assert b.volume_in_mode["cooling"] == pytest.approx(1.5 * 3600 / RHO)
    assert b.volume_in_mode["heating"] == pytest.approx(1.0 * 3600 / RHO)


def test_volume_without_demand_is_reported() -> None:
    result = attribute_fans(_data((LOOP,)))
    # A: hour 2 has neither load nor outdoor air; hour 0 has a load.
    assert result.zones["A"].volume_without_demand == pytest.approx(1.0 * 3600 / RHO)
    assert result.zones["B"].volume_without_demand == 0.0


def test_unmatched_fans_are_reported() -> None:
    orphan = FanSeries("lost fan", energy=_a(5.0, 5.0, 5.0), mass_flow=_a(1.0, 1.0, 1.0))
    result = attribute_fans(_data((orphan,)))
    assert result.unattributed_energy == pytest.approx(15.0)
    assert result.unattributed_fans == ("lost fan",)


def test_a_loop_splits_by_its_own_units_inlet_flow() -> None:
    """D10: a DOAS feeding only A is not split by B's VAV inlet flow."""
    doas = FanSeries(
        "DOAS fan",
        energy=_a(100.0, 100.0, 100.0),
        mass_flow=_a(1.0, 1.0, 1.0),
        loop_zones=("A", "B"),
        loop_inlet_flow={"A": _a(1.0, 1.0, 1.0), "B": _a(0.0, 0.0, 0.0)},
    )
    result = attribute_fans(_data((doas,)))  # B's whole inlet flow (VAV) is larger than A's
    assert result.zones["A"].energy == pytest.approx(300.0)
    assert result.zones["B"].energy == 0.0


def _two_loop_model() -> Any:
    """Zones A and B on a VAV loop (with a return path), and A also on a DOAS (no return path)."""
    doc = new_document()

    def add(kind: str, name: str, **fields: object) -> None:
        doc.add(kind, name, validate=False, **fields)  # pyright: ignore[reportArgumentType]

    for zone in ("A", "B"):
        add("Zone", zone)
        units = [("VAV", f"{zone} VAV inlet", f"{zone} VAV box")] + (
            [("DOAS", "A DOAS inlet", "A DOAS box")] * (zone == "A")
        )
        add(
            "ZoneHVAC:EquipmentConnections",
            "",
            zone_name=zone,
            zone_conditioning_equipment_list_name=f"{zone} equipment",
            zone_air_inlet_node_or_nodelist_name=f"{zone} inlets",
            zone_air_node_name=f"{zone} air",
            zone_return_air_node_or_nodelist_name=f"{zone} return",
        )
        add("NodeList", f"{zone} inlets", nodes=[{"node_name": node} for _, node, _ in units])
        add(
            "ZoneHVAC:EquipmentList",
            f"{zone} equipment",
            equipment=[
                {"zone_equipment_object_type": "ZoneHVAC:AirDistributionUnit", "zone_equipment_name": f"{box} ADU"}
                for _, _, box in units
            ],
        )
        for _, node, box in units:
            add(
                "ZoneHVAC:AirDistributionUnit",
                f"{box} ADU",
                air_distribution_unit_outlet_node_name=node,
                air_terminal_object_type="AirTerminal:SingleDuct:ConstantVolume:NoReheat",
                air_terminal_name=box,
            )
            add(
                "AirTerminal:SingleDuct:ConstantVolume:NoReheat",
                box,
                air_inlet_node_name=f"{box} in",
                air_outlet_node_name=node,
            )
    for loop, zones in (("VAV", ("A", "B")), ("DOAS", ("A",))):
        add(
            "AirLoopHVAC",
            loop,
            demand_side_inlet_node_names=f"{loop} demand in",
            demand_side_outlet_node_name=f"{loop} demand out",
        )
        add(
            "AirLoopHVAC:SupplyPath",
            f"{loop} supply path",
            supply_air_path_inlet_node_name=f"{loop} demand in",
            components=[{"component_object_type": "AirLoopHVAC:ZoneSplitter", "component_name": f"{loop} splitter"}],
        )
        add(
            "AirLoopHVAC:ZoneSplitter",
            f"{loop} splitter",
            inlet_node_name=f"{loop} demand in",
            nodes=[{"outlet_node_name": f"{z} {loop} box in"} for z in zones],
        )
    add(
        "AirLoopHVAC:ReturnPath",
        "VAV return path",
        return_air_path_outlet_node_name="VAV demand out",
        components=[{"component_object_type": "AirLoopHVAC:ZoneMixer", "component_name": "VAV mixer"}],
    )
    add(
        "AirLoopHVAC:ZoneMixer",
        "VAV mixer",
        outlet_node_name="VAV demand out",
        nodes=[{"inlet_node_name": "A return"}, {"inlet_node_name": "B return"}],
    )
    return doc


def test_a_loop_without_return_path_serves_the_zones_its_supply_path_feeds() -> None:
    """D11: a DOAS without a return path serves A; each loop knows its own units' inlet nodes."""
    loops = air_loops(_two_loop_model(), ("A", "B"))
    assert loops.served == {"vav": ("A", "B"), "doas": ("A",)}
    assert loops.loop_inlet_nodes == {
        "vav": {"A": ("A VAV inlet",), "B": ("B VAV inlet",)},
        "doas": {"A": ("A DOAS inlet",)},
    }


def test_fan_energy_of_excluded_zones_is_reported() -> None:
    """D9: fan energy attributed to a plenum is listed, not dropped."""
    from archetypal.reduction import _unattributed_fans  # pyright: ignore[reportPrivateUsage]  # noqa: PLC0415

    attribution = FanAttribution(
        zones={"Room": FanTotals(energy=10.0), "Plenum": FanTotals(energy=4.0)},
        multipliers={"Room": 1, "Plenum": 3},
        air_density=RHO,
    )
    room = cast("ClassifiedZone", SimpleNamespace(zone=SimpleNamespace(name="Room")))
    (entry,) = _unattributed_fans(attribution, [room])
    assert entry.feature == "Fan energy of excluded zones"
    assert entry.affected_zones == ("Plenum",)
    assert entry.magnitude == pytest.approx(12.0)


def test_the_module_hook_needs_building_data() -> None:
    with pytest.raises(ValueError, match="fans_hook"):
        ledger_fields(None, None)  # pyright: ignore[reportArgumentType]


# --- fixtures -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ten(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    return detailed("ten_zone_multipliers")


@pytest.fixture(scope="module")
def three(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    return detailed("three_zone")


def _series(sources: SourceData, name: str, key: str) -> np.ndarray:
    (series,) = sources.results.get_timeseries_many([(name, key, "Hourly")])
    return np.asarray(series.values, dtype=np.float64)


def test_fixture_fans_are_assigned(ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]) -> None:
    sources, zones, _ = ten
    data = building_fans(sources, zones)
    by_name = {fan.name.upper(): fan for fan in data.fans}
    assert by_name["TOP_CORE PTHP FAN"].zone == "Top_Core"
    assert set(by_name["VAV SUPPLY FAN"].loop_zones) == {"G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core"}
    assert set(data.inlet_flow) == {"G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core"}
    vav = by_name["VAV SUPPLY FAN"].loop_inlet_flow  # the single loop's units are traced
    assert vav is not None
    assert set(vav) == set(data.inlet_flow)


def test_fixture_fan_energy_and_volume_are_conserved(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, evaluate = ten
    hook = fans_hook(sources, zones)
    ledgers = [GroupLedger.from_zone(z, evaluate, hooks=[hook]) for z in zones if z.conditioned]
    total = sum(ledgers, GroupLedger()).fans
    (meter,) = sources.results.get_timeseries_many([("Fans:Electricity", "*", "Hourly")])
    assert total.energy == pytest.approx(float(np.sum(meter.values)), rel=1e-9)
    flow = sum(
        _series(sources, "Fan Air Mass Flow Rate", key).sum()
        for key in ("VAV SUPPLY FAN", "TOP_CORE PTHP FAN", "TOP_PERIMETER PTHP FAN")
    )
    assert total.volume == pytest.approx(flow * 3600 / hook.air_density, rel=1e-6)
    sfp = specific_fan_power(total)
    assert sfp is not None
    assert sfp * total.volume == pytest.approx(total.energy)
    vav = _series(sources, "Fan Electricity Energy", "VAV SUPPLY FAN").sum()
    vav_zones = sum(
        hook.multipliers_applied(name).energy for name in ("G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core")
    )
    assert vav_zones == pytest.approx(vav, rel=1e-6)
    assert 0.0 <= total.volume_without_demand <= total.volume
    delta = effective_supply_delta(total, "heating", air_density=hook.air_density)
    assert delta is not None
    assert 0.0 < delta < 40.0


def test_fixture_zone_equipment_fans_three_zone(
    three: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, _ = three
    hook = fans_hook(sources, zones)
    for zone in ("Core", "North_Perimeter", "South_Perimeter"):
        key = f"{zone} PTAC Fan".upper()
        assert hook.zones[zone].energy == pytest.approx(_series(sources, "Fan Electricity Energy", key).sum())
    assert hook.unattributed_fans == ()


def test_fixture_without_fans_bar_building(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> None:
    sources, zones, _ = detailed("bar_building")
    hook = fans_hook(sources, zones)
    assert all(totals == FanTotals() for totals in hook.zones.values())
    assert hook.unattributed_fans == ()


def test_the_elevation_is_the_one_energyplus_ran_with(tmp_path: Path) -> None:
    """The results' elevation (the weather file's for an annual run) wins over Site:Location's."""
    import shutil  # noqa: PLC0415
    import sqlite3  # noqa: PLC0415

    from idfkit import new_document  # noqa: PLC0415
    from idfkit.simulation import SQLResult  # noqa: PLC0415

    from archetypal.reduction.fans import _elevation  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]

    doc = new_document()
    doc.add("Site:Location", "Here", validate=False, elevation=0.0)
    results = SQLResult(MODELS / "three_zone.sql")
    try:
        assert _elevation(doc, results) == pytest.approx(201.0)
    finally:
        results.close()
    assert _elevation(doc) == 0.0
    copy = tmp_path / "ip.sql"
    shutil.copyfile(MODELS / "three_zone.sql", copy)
    with sqlite3.connect(copy) as conn:
        conn.execute(
            "UPDATE Strings SET Value = 'ft' WHERE StringIndex IN (SELECT UnitsIndex FROM TabularData td "
            "JOIN Strings r ON td.RowNameIndex = r.StringIndex WHERE r.Value = 'Elevation')"
        )
    conn.close()
    results = SQLResult(copy)
    try:
        assert _elevation(doc, results) == pytest.approx(201.0 * 0.3048)
    finally:
        results.close()
