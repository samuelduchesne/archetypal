"""Rebuild the unit-test fixture models and their cut-down simulation results.

Spec 002, task T028. The four fixture models are built in code here with idfkit, written as
EnergyPlus 24.2 IDF files to ``tests/fixtures/models/``, simulated for one annual run period
with the Chicago O'Hare TMY3 weather file in ``tests/fixtures/weather/``, and each run's
SQLite output is cut down to what reduction reads (contracts/results-requirements.md) and
saved next to its model as ``<name>.sql``.

The models are generated, not hand-written, so that ``ten_zone_explicit`` is the same
building as ``ten_zone_multipliers`` by construction: both are drawn from the same floor
plans, constructions, loads and HVAC builders, and differ only in how the typical floor is
represented (one floor with zone and zone-list multipliers, or ten floors drawn).

Usage (needs EnergyPlus 24.2; not run by the test suite)::

    uv run python tests/fixtures/regenerate.py            # build and simulate all four
    uv run python tests/fixtures/regenerate.py three_zone # only the named fixtures
    uv run python tests/fixtures/regenerate.py --no-simulate  # rewrite the IDF files only
"""

from __future__ import annotations

import argparse
import math
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from idfkit import new_document, save_idf, validate_document
from idfkit.simulation import simulate
from idfkit.versioned import IDFDocumentV24_2

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
WEATHER_FILE = HERE / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"

Point = tuple[float, float, float]
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1

# --------------------------------------------------------------------------------------------
# Model wrapper
# --------------------------------------------------------------------------------------------


@dataclass
class Model:
    """An EnergyPlus 24.2 document with small helpers for adding objects."""

    doc: IDFDocumentV24_2 = field(default_factory=lambda: new_document(IDFDocumentV24_2))
    surface_counter: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # new_document seeds these singletons; each model sets its own.
        for obj_type in ("Building", "SimulationControl", "GlobalGeometryRules"):
            for obj in list(self.doc[obj_type]):
                self.doc.removeidfobject(obj)

    def add(self, obj_type: str, name: str | None = None, **fields: Any) -> None:
        """Add one object; ``name`` is None for unnamed types."""
        if name is None:
            self.doc.add(obj_type, **fields)
        else:
            self.doc.add(obj_type, name, **fields)

    def surface_name(self, zone: str, kind: str) -> str:
        """Return the next surface name for a zone, such as ``Core_Wall_03``."""
        key = f"{zone}_{kind}"
        self.surface_counter[key] = self.surface_counter.get(key, 0) + 1
        return f"{key}_{self.surface_counter[key]:02d}"


# --------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------


def _newell(verts: Sequence[Point]) -> Point:
    nx = ny = nz = 0.0
    for i, (x1, y1, z1) in enumerate(verts):
        x2, y2, z2 = verts[(i + 1) % len(verts)]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def _orient(verts: Sequence[Point], outward: Point) -> list[Point]:
    """Return the vertices counterclockwise seen from outside (normal along ``outward``)."""
    n = _newell(verts)
    dot = n[0] * outward[0] + n[1] * outward[1] + n[2] * outward[2]
    return list(verts) if dot > 0 else list(reversed(verts))


def _rect_points(r: Rect, z: float) -> list[Point]:
    x0, y0, x1, y1 = r
    return [(x0, y1, z), (x0, y0, z), (x1, y0, z), (x1, y1, z)]


def _intersect(a: Rect, b: Rect) -> Rect | None:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 - x0 > 1e-9 and y1 - y0 > 1e-9:
        return (x0, y0, x1, y1)
    return None


@dataclass
class Level:
    """One storey of thermal zones: axis-aligned rectangular cells, each owned by a zone/space.

    Walls are derived from the cells: a wall wherever two different zones meet, or a zone
    meets the outside. Floors and ceilings are either set here (``ground``, ``roof``,
    ``adiabatic``) or paired with the next level by ``pair_levels``.
    """

    z0: float
    height: float
    cells: list[tuple[Rect, str, str]]  # rectangle, zone, space ("" for none)
    exterior_construction: str = "Exterior Wall"
    exterior_boundary: str = "Outdoors"
    windows: bool = False
    floor: str | None = None
    ceiling: str | None = None

    def owner(self, x: float, y: float) -> tuple[str, str] | None:
        """Zone and space at a point, or None outside the plan."""
        for (x0, y0, x1, y1), zone, space in self.cells:
            if x0 < x < x1 and y0 < y < y1:
                return zone, space
        return None


Owner = tuple[str, str] | None


def _wall_segments(level: Level) -> list[tuple[tuple[float, float], tuple[float, float], Owner, Owner]]:
    """Return merged wall segments (p, q, owner on the -side, owner on the +side)."""
    xs = sorted({c for (r, _, _) in level.cells for c in (r[0], r[2])})
    ys = sorted({c for (r, _, _) in level.cells for c in (r[1], r[3])})
    eps = 1e-6
    segments: list[tuple[tuple[float, float], tuple[float, float], Owner, Owner]] = []

    def emit(runs: list[tuple[float, float, Owner, Owner]], fixed: float, vertical: bool) -> None:
        merged: list[list[Any]] = []
        for a, b, lo, hi in runs:
            if merged and merged[-1][1] == a and merged[-1][2] == lo and merged[-1][3] == hi:
                merged[-1][1] = b
            else:
                merged.append([a, b, lo, hi])
        for a, b, lo, hi in merged:
            p, q = ((fixed, a), (fixed, b)) if vertical else ((a, fixed), (b, fixed))
            segments.append((p, q, lo, hi))

    for x in xs:
        runs: list[tuple[float, float, Owner, Owner]] = []
        for y0, y1 in zip(ys, ys[1:]):
            ym = (y0 + y1) / 2
            lo, hi = level.owner(x - eps, ym), level.owner(x + eps, ym)
            if (lo[0] if lo else None) != (hi[0] if hi else None):
                runs.append((y0, y1, lo, hi))
        emit(runs, x, vertical=True)
    for y in ys:
        runs = []
        for x0, x1 in zip(xs, xs[1:]):
            xm = (x0 + x1) / 2
            lo, hi = level.owner(xm, y - eps), level.owner(xm, y + eps)
            if (lo[0] if lo else None) != (hi[0] if hi else None):
                runs.append((x0, x1, lo, hi))
        emit(runs, y, vertical=False)
    return segments


def _add_surface(
    m: Model,
    name: str,
    surface_type: str,
    construction: str,
    owner: tuple[str, str],
    verts: Sequence[Point],
    boundary: str = "Outdoors",
    boundary_object: str = "",
) -> None:
    exposed = boundary == "Outdoors"
    m.add(
        "BuildingSurface:Detailed",
        name,
        surface_type=surface_type,
        construction_name=construction,
        zone_name=owner[0],
        space_name=owner[1],
        outside_boundary_condition=boundary,
        outside_boundary_condition_object=boundary_object,
        sun_exposure="SunExposed" if exposed else "NoSun",
        wind_exposure="WindExposed" if exposed else "NoWind",
        view_factor_to_ground="Autocalculate",
        number_of_vertices=len(verts),
        vertices=[
            {"vertex_x_coordinate": x, "vertex_y_coordinate": y, "vertex_z_coordinate": z} for x, y, z in verts
        ],
    )


def _add_window(m: Model, wall: str, a: tuple[float, float], b: tuple[float, float], z0: float, z1: float) -> None:
    """Add a strip window on a wall whose outside is to the right of a->b."""
    length = math.dist(a, b)
    if length < 2.0:
        return
    inset = 0.5
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    p = (a[0] + ux * inset, a[1] + uy * inset)
    q = (b[0] - ux * inset, b[1] - uy * inset)
    pts = [(p[0], p[1], z1), (p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], z1)]
    fields: dict[str, float] = {}
    for i, (x, y, z) in enumerate(pts, start=1):
        fields[f"vertex_{i}_x_coordinate"] = x
        fields[f"vertex_{i}_y_coordinate"] = y
        fields[f"vertex_{i}_z_coordinate"] = z
    m.add(
        "FenestrationSurface:Detailed",
        f"{wall}_Window",
        surface_type="Window",
        construction_name="Window",
        building_surface_name=wall,
        view_factor_to_ground="Autocalculate",
        multiplier=1,
        number_of_vertices=4,
        **fields,
    )


def add_level(m: Model, level: Level) -> None:
    """Add a level's walls, windows and its own (unpaired) floors and ceilings."""
    z0, z1 = level.z0, level.z0 + level.height
    for p, q, lo, hi in _wall_segments(level):
        vertical = p[0] == q[0]
        # Outward normal of the -side owner's wall points to +x (vertical line) or +y.
        plus: tuple[float, float] = (1.0, 0.0) if vertical else (0.0, 1.0)
        sides: list[tuple[tuple[str, str], tuple[float, float]]] = []
        if lo is not None:
            sides.append((lo, plus))
        if hi is not None:
            sides.append((hi, (-plus[0], -plus[1])))
        names = [m.surface_name(o[0], "Wall") for o, _ in sides]
        for i, (own, out) in enumerate(sides):
            # Order a->b so that outside is to the right: right of d is (dy, -dx).
            dx, dy = q[0] - p[0], q[1] - p[1]
            a, b = (p, q) if (dy * out[0] - dx * out[1]) > 0 else (q, p)
            verts = [(a[0], a[1], z1), (a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1)]
            if len(sides) == 2:
                _add_surface(m, names[i], "Wall", "Interior Wall", own, verts, "Surface", names[1 - i])
            else:
                _add_surface(m, names[i], "Wall", level.exterior_construction, own, verts, level.exterior_boundary)
                if level.windows and level.exterior_boundary == "Outdoors":
                    _add_window(m, names[i], a, b, z0 + 0.9, z0 + 2.4)
    for rect, zone, space in level.cells:
        if level.floor is not None:
            verts = _orient(_rect_points(rect, z0), (0.0, 0.0, -1.0))
            name = m.surface_name(zone, "Floor")
            if level.floor == "ground":
                _add_surface(m, name, "Floor", "Ground Slab", (zone, space), verts, "Ground")
            else:
                _add_surface(m, name, "Floor", "Interior Slab", (zone, space), verts, "Adiabatic")
        if level.ceiling is not None:
            verts = _orient(_rect_points(rect, z1), (0.0, 0.0, 1.0))
            if level.ceiling == "roof":
                _add_surface(m, m.surface_name(zone, "Roof"), "Roof", "Roof", (zone, space), verts)
            else:
                name = m.surface_name(zone, "Ceiling")
                _add_surface(m, name, "Ceiling", "Interior Slab", (zone, space), verts, "Adiabatic")


def pair_levels(m: Model, lower: Level, upper: Level, ceiling_construction: str, floor_construction: str) -> None:
    """Add matching interzone ceiling (lower) and floor (upper) surfaces."""
    z = lower.z0 + lower.height
    for rl, zl, sl in lower.cells:
        for ru, zu, su in upper.cells:
            piece = _intersect(rl, ru)
            if piece is None:
                continue
            ceiling, floor = m.surface_name(zl, "Ceiling"), m.surface_name(zu, "Floor")
            up = _orient(_rect_points(piece, z), (0.0, 0.0, 1.0))
            down = _orient(_rect_points(piece, z), (0.0, 0.0, -1.0))
            _add_surface(m, ceiling, "Ceiling", ceiling_construction, (zl, sl), up, "Surface", floor)
            _add_surface(m, floor, "Floor", floor_construction, (zu, su), down, "Surface", ceiling)


def add_gable_attic(m: Model, below: Level, zone: str, width: float, depth: float, rise: float) -> None:
    """Add an unconditioned attic with a gable roof (ridge along x) over ``below``."""
    zb = below.z0 + below.height
    attic = Level(z0=zb, height=0.0, cells=[((0.0, 0.0, width, depth), zone, "")])
    pair_levels(m, below, attic, "Attic Floor", "Attic Floor Reversed")
    ym, zr = depth / 2, zb + rise
    south = [(0.0, 0.0, zb), (width, 0.0, zb), (width, ym, zr), (0.0, ym, zr)]
    north = [(0.0, depth, zb), (width, depth, zb), (width, ym, zr), (0.0, ym, zr)]
    _add_surface(m, m.surface_name(zone, "Roof"), "Roof", "Attic Roof", (zone, ""), _orient(south, (0, -rise, ym)))
    _add_surface(m, m.surface_name(zone, "Roof"), "Roof", "Attic Roof", (zone, ""), _orient(north, (0, rise, ym)))
    west = [(0.0, 0.0, zb), (0.0, depth, zb), (0.0, ym, zr)]
    east = [(width, 0.0, zb), (width, depth, zb), (width, ym, zr)]
    _add_surface(m, m.surface_name(zone, "Wall"), "Wall", "Exterior Wall", (zone, ""), _orient(west, (-1, 0, 0)))
    _add_surface(m, m.surface_name(zone, "Wall"), "Wall", "Exterior Wall", (zone, ""), _orient(east, (1, 0, 0)))


def ring_plan(width: float, depth: float, core: Rect, perimeter: str, core_zone: str) -> list[tuple[Rect, str, str]]:
    """Cells of a perimeter ring zone around a core zone."""
    cx0, cy0, cx1, cy1 = core
    return [
        ((0.0, 0.0, width, cy0), perimeter, ""),
        ((0.0, cy1, width, depth), perimeter, ""),
        ((0.0, cy0, cx0, cy1), perimeter, ""),
        ((cx1, cy0, width, cy1), perimeter, ""),
        (core, core_zone, ""),
    ]


# --------------------------------------------------------------------------------------------
# Common content: run control, site, materials, constructions, schedules, outputs
# --------------------------------------------------------------------------------------------


def _compact(m: Model, name: str, limits: str, lines: Iterable[str | float]) -> None:
    m.add("Schedule:Compact", name, schedule_type_limits_name=limits, data=[{"field": v} for v in lines])


def add_run_control(m: Model, building: str, *, sizing: tuple[bool, bool, bool]) -> None:
    """Simulation control, site, weather-file run period and design days."""
    zone, system, plant = sizing
    yes_no: Callable[[bool], str] = lambda flag: "Yes" if flag else "No"
    m.add(
        "Building",
        building,
        north_axis=0.0,
        terrain="Suburbs",
        loads_convergence_tolerance_value=0.04,
        temperature_convergence_tolerance_value=0.4,
        solar_distribution="FullExterior",
        maximum_number_of_warmup_days=25,
        minimum_number_of_warmup_days=6,
    )
    m.add(
        "SimulationControl",
        do_zone_sizing_calculation=yes_no(zone),
        do_system_sizing_calculation=yes_no(system),
        do_plant_sizing_calculation=yes_no(plant),
        run_simulation_for_sizing_periods="No",
        run_simulation_for_weather_file_run_periods="Yes",
    )
    m.add(
        "GlobalGeometryRules",
        starting_vertex_position="UpperLeftCorner",
        vertex_entry_direction="Counterclockwise",
        coordinate_system="World",
        daylighting_reference_point_coordinate_system="World",
        rectangular_surface_coordinate_system="World",
    )
    m.add("Timestep", number_of_timesteps_per_hour=4)
    m.add("Site:Location", "Chicago Ohare Intl Ap", latitude=41.98, longitude=-87.92, time_zone=-6.0, elevation=201.0)
    m.add("Site:WaterMainsTemperature", calculation_method="CorrelationFromWeatherFile")
    m.add(
        "Site:GroundTemperature:BuildingSurface",
        **{
            f"{month}_ground_temperature": t
            for month, t in zip(
                (
                    "january",
                    "february",
                    "march",
                    "april",
                    "may",
                    "june",
                    "july",
                    "august",
                    "september",
                    "october",
                    "november",
                    "december",
                ),
                (18.3, 18.2, 18.3, 18.4, 20.1, 22.0, 22.3, 22.5, 22.5, 20.7, 18.9, 18.5),
            )
        },
    )
    m.add(
        "RunPeriod",
        "Annual",
        begin_month=1,
        begin_day_of_month=1,
        end_month=12,
        end_day_of_month=31,
        use_weather_file_holidays_and_special_days="Yes",
        use_weather_file_daylight_saving_period="Yes",
        apply_weekend_holiday_rule="No",
        use_weather_file_rain_indicators="Yes",
        use_weather_file_snow_indicators="Yes",
    )
    # ASHRAE 2009 design conditions from the station's .ddy file.
    m.add(
        "SizingPeriod:DesignDay",
        "Chicago Ohare Intl Ap Ann Htg 99.6% Condns DB",
        month=1,
        day_of_month=21,
        day_type="WinterDesignDay",
        maximum_dry_bulb_temperature=-20.0,
        daily_dry_bulb_temperature_range=0.0,
        humidity_condition_type="WetBulb",
        wetbulb_or_dewpoint_at_maximum_dry_bulb=-20.0,
        barometric_pressure=98934.0,
        wind_speed=4.9,
        wind_direction=270.0,
        solar_model_indicator="ASHRAEClearSky",
        sky_clearness=0.0,
    )
    m.add(
        "SizingPeriod:DesignDay",
        "Chicago Ohare Intl Ap Ann Clg .4% Condns DB=>MWB",
        month=7,
        day_of_month=21,
        day_type="SummerDesignDay",
        maximum_dry_bulb_temperature=33.3,
        daily_dry_bulb_temperature_range=10.5,
        humidity_condition_type="WetBulb",
        wetbulb_or_dewpoint_at_maximum_dry_bulb=23.7,
        barometric_pressure=98934.0,
        wind_speed=5.2,
        wind_direction=230.0,
        solar_model_indicator="ASHRAETau",
        ashrae_clear_sky_optical_depth_for_beam_irradiance_taub_=0.455,
        ashrae_clear_sky_optical_depth_for_diffuse_irradiance_taud_=2.050,
    )


MATERIALS: dict[str, tuple[str, float, float, float, float]] = {
    # name: roughness, thickness m, conductivity W/m-K, density kg/m3, specific heat J/kg-K
    "Brick": ("MediumRough", 0.1016, 0.89, 1920.0, 790.0),
    "Wall Insulation": ("MediumRough", 0.0794, 0.0432, 91.0, 837.0),
    "Gypsum": ("Smooth", 0.0127, 0.16, 784.9, 830.0),
    "Roof Membrane": ("VeryRough", 0.0095, 0.16, 1121.29, 1460.0),
    "Roof Insulation": ("MediumRough", 0.1693, 0.049, 265.0, 836.8),
    "Metal Decking": ("MediumSmooth", 0.0015, 45.006, 7680.0, 418.4),
    "Plywood": ("MediumSmooth", 0.019, 0.12, 540.0, 1210.0),
    "Ceiling Insulation": ("MediumRough", 0.2, 0.045, 30.0, 840.0),
    "Concrete 150mm": ("MediumRough", 0.15, 1.95, 2240.0, 900.0),
    "Concrete 200mm": ("MediumRough", 0.2, 1.95, 2240.0, 900.0),
    "Acoustic Tile": ("MediumSmooth", 0.0191, 0.06, 368.0, 590.0),
    "Wood": ("MediumSmooth", 0.05, 0.15, 608.0, 1630.0),
}

CONSTRUCTIONS: dict[str, tuple[str, ...]] = {
    # name: layers, outside to inside
    "Exterior Wall": ("Brick", "Wall Insulation", "Gypsum"),
    "Basement Wall": ("Concrete 200mm", "Wall Insulation"),
    "Roof": ("Roof Membrane", "Roof Insulation", "Metal Decking"),
    "Attic Roof": ("Roof Membrane", "Plywood"),
    "Attic Floor": ("Ceiling Insulation", "Gypsum"),
    "Attic Floor Reversed": ("Gypsum", "Ceiling Insulation"),
    "Ground Slab": ("Concrete 200mm",),
    "Interior Slab": ("Concrete 150mm",),
    "Drop Ceiling": ("Acoustic Tile",),
    "Interior Wall": ("Gypsum", "Wall Air Space", "Gypsum"),
    "Furniture": ("Wood",),
    "Window": ("Simple Glazing",),
}


def add_envelope_library(m: Model) -> None:
    """Materials and constructions shared by every fixture."""
    for name, (rough, thick, cond, dens, cp) in MATERIALS.items():
        m.add(
            "Material",
            name,
            roughness=rough,
            thickness=thick,
            conductivity=cond,
            density=dens,
            specific_heat=cp,
            thermal_absorptance=0.9,
            solar_absorptance=0.7,
            visible_absorptance=0.7,
        )
    m.add("Material:AirGap", "Wall Air Space", thermal_resistance=0.15)
    m.add(
        "WindowMaterial:SimpleGlazingSystem",
        "Simple Glazing",
        u_factor=2.0,
        solar_heat_gain_coefficient=0.4,
        visible_transmittance=0.6,
    )
    for name, layers in CONSTRUCTIONS.items():
        fields = {"outside_layer": layers[0]} | {f"layer_{i}": lay for i, lay in enumerate(layers[1:], start=2)}
        m.add("Construction", name, **fields)


WEEKDAY_OFFICE = ("For: Weekdays", "Until: 07:00", 0.0, "Until: 08:00", 0.5, "Until: 12:00", 0.95)
WEEKDAY_OFFICE_PM = ("Until: 13:00", 0.5, "Until: 17:00", 0.95, "Until: 18:00", 0.3, "Until: 22:00", 0.1)


def add_schedules(m: Model) -> None:
    """Schedule type limits and the schedules every fixture uses."""
    m.add("ScheduleTypeLimits", "Fraction", lower_limit_value=0.0, upper_limit_value=1.0, numeric_type="Continuous")
    m.add("ScheduleTypeLimits", "Temperature", lower_limit_value=-60, upper_limit_value=200, numeric_type="Continuous")
    m.add("ScheduleTypeLimits", "Any Number")
    m.add("ScheduleTypeLimits", "Control Type", lower_limit_value=0, upper_limit_value=4, numeric_type="Discrete")
    always = ("Through: 12/31", "For: AllDays", "Until: 24:00")
    _compact(m, "Always On", "Fraction", (*always, 1.0))
    _compact(m, "Activity Level", "Any Number", (*always, 120.0))
    _compact(m, "Thermostat Control Type", "Control Type", (*always, 4))
    occ_tail = ("Until: 24:00", 0.0)
    _compact(
        m,
        "Office Occupancy",
        "Fraction",
        (
            "Through: 12/31",
            *WEEKDAY_OFFICE,
            *WEEKDAY_OFFICE_PM,
            *occ_tail,
            "For: Saturday",
            "Until: 08:00",
            0.0,
            "Until: 14:00",
            0.3,
            *occ_tail,
            "For: SummerDesignDay",
            "Until: 24:00",
            1.0,
            "For: AllOtherDays",
            *occ_tail,
        ),
    )
    _compact(
        m,
        "Conference Occupancy",
        "Fraction",
        (
            "Through: 12/31",
            "For: Weekdays",
            "Until: 09:00",
            0.0,
            "Until: 12:00",
            0.6,
            "Until: 13:00",
            0.2,
            "Until: 16:00",
            0.8,
            "Until: 17:00",
            0.3,
            *occ_tail,
            "For: SummerDesignDay",
            "Until: 24:00",
            1.0,
            "For: AllOtherDays",
            *occ_tail,
        ),
    )
    _compact(
        m,
        "Office Lighting",
        "Fraction",
        (
            "Through: 12/31",
            "For: Weekdays",
            "Until: 07:00",
            0.05,
            "Until: 18:00",
            0.9,
            "Until: 22:00",
            0.3,
            "Until: 24:00",
            0.05,
            "For: Saturday",
            "Until: 08:00",
            0.05,
            "Until: 14:00",
            0.5,
            "Until: 24:00",
            0.05,
            "For: SummerDesignDay",
            "Until: 24:00",
            1.0,
            "For: WinterDesignDay",
            "Until: 24:00",
            0.0,
            "For: AllOtherDays",
            "Until: 24:00",
            0.05,
        ),
    )
    _compact(
        m,
        "Office Equipment",
        "Fraction",
        (
            "Through: 12/31",
            "For: Weekdays",
            "Until: 07:00",
            0.3,
            "Until: 18:00",
            0.9,
            "Until: 24:00",
            0.3,
            "For: SummerDesignDay",
            "Until: 24:00",
            1.0,
            "For: WinterDesignDay",
            "Until: 24:00",
            0.0,
            "For: AllOtherDays",
            "Until: 24:00",
            0.3,
        ),
    )
    for name, occupied, setback in (("Heating Setpoint", 21.0, 15.6), ("Cooling Setpoint", 24.0, 29.4)):
        design = ("For: WinterDesignDay", "Until: 24:00", 21.0, "For: SummerDesignDay", "Until: 24:00", 24.0)
        _compact(
            m,
            name,
            "Temperature",
            (
                "Through: 12/31",
                "For: Weekdays",
                "Until: 06:00",
                setback,
                "Until: 22:00",
                occupied,
                "Until: 24:00",
                setback,
                "For: Saturday",
                "Until: 06:00",
                setback,
                "Until: 18:00",
                occupied,
                "Until: 24:00",
                setback,
                *design,
                "For: AllOtherDays",
                "Until: 24:00",
                setback,
            ),
        )
    hvac_on = (
        "Through: 12/31",
        "For: Weekdays",
        "Until: 06:00",
        0.0,
        "Until: 22:00",
        1.0,
        "Until: 24:00",
        0.0,
        "For: Saturday",
        "Until: 06:00",
        0.0,
        "Until: 18:00",
        1.0,
        "Until: 24:00",
        0.0,
        "For: SummerDesignDay WinterDesignDay",
        "Until: 24:00",
        1.0,
        "For: AllOtherDays",
        "Until: 24:00",
        0.0,
    )
    _compact(m, "HVAC Operation", "Fraction", hvac_on)
    _compact(
        m,
        "Infiltration",
        "Fraction",
        (
            "Through: 12/31",
            "For: Weekdays",
            "Until: 06:00",
            1.0,
            "Until: 22:00",
            0.25,
            "Until: 24:00",
            1.0,
            "For: Saturday",
            "Until: 06:00",
            1.0,
            "Until: 18:00",
            0.25,
            "Until: 24:00",
            1.0,
            "For: AllOtherDays",
            "Until: 24:00",
            1.0,
        ),
    )


def add_thermostat(m: Model, zone: str) -> None:
    """Dual-setpoint thermostat on the office setpoint schedules."""
    m.add(
        "ZoneControl:Thermostat",
        f"{zone} Thermostat",
        zone_or_zonelist_name=zone,
        control_type_schedule_name="Thermostat Control Type",
        control_1_object_type="ThermostatSetpoint:DualSetpoint",
        control_1_name="Office Dual Setpoint",
    )


def add_thermostat_setpoints(m: Model) -> None:
    """The dual setpoint every conditioned zone uses."""
    m.add(
        "ThermostatSetpoint:DualSetpoint",
        "Office Dual Setpoint",
        heating_setpoint_temperature_schedule_name="Heating Setpoint",
        cooling_setpoint_temperature_schedule_name="Cooling Setpoint",
    )


def add_space_use_loads(
    m: Model,
    use: str,
    target: str,
    *,
    people_per_area: float,
    lights: float,
    equipment: float,
    occupancy: str,
) -> None:
    """People, lights and electric equipment of one space use, on a zone, zone list or space."""
    m.add(
        "People",
        f"{use} People {target}",
        zone_or_zonelist_or_space_or_spacelist_name=target,
        number_of_people_schedule_name=occupancy,
        number_of_people_calculation_method="People/Area",
        people_per_floor_area=people_per_area,
        fraction_radiant=0.3,
        sensible_heat_fraction="Autocalculate",
        activity_level_schedule_name="Activity Level",
    )
    m.add(
        "Lights",
        f"{use} Lights {target}",
        zone_or_zonelist_or_space_or_spacelist_name=target,
        schedule_name="Office Lighting",
        design_level_calculation_method="Watts/Area",
        watts_per_floor_area=lights,
        return_air_fraction=0.0,
        fraction_radiant=0.42,
        fraction_visible=0.18,
        fraction_replaceable=1.0,
        end_use_subcategory="General",
    )
    m.add(
        "ElectricEquipment",
        f"{use} Equipment {target}",
        zone_or_zonelist_or_space_or_spacelist_name=target,
        schedule_name="Office Equipment",
        design_level_calculation_method="Watts/Area",
        watts_per_floor_area=equipment,
        fraction_latent=0.0,
        fraction_radiant=0.5,
        fraction_lost=0.0,
        end_use_subcategory="General",
    )


def add_infiltration(m: Model, target: str, per_exterior_area: float) -> None:
    """Infiltration per exterior surface area on the infiltration schedule."""
    m.add(
        "ZoneInfiltration:DesignFlowRate",
        f"{target} Infiltration",
        zone_or_zonelist_or_space_or_spacelist_name=target,
        schedule_name="Infiltration",
        design_flow_rate_calculation_method="Flow/ExteriorArea",
        flow_rate_per_exterior_surface_area=per_exterior_area,
        constant_term_coefficient=1.0,
        temperature_term_coefficient=0.0,
        velocity_term_coefficient=0.0,
        velocity_squared_term_coefficient=0.0,
    )


def add_outdoor_air_spec(m: Model) -> None:
    """Outdoor air per person plus per area (ASHRAE 62.1 office rates)."""
    m.add(
        "DesignSpecification:OutdoorAir",
        "Office Outdoor Air",
        outdoor_air_method="Sum",
        outdoor_air_flow_per_person=0.0025,
        outdoor_air_flow_per_zone_floor_area=0.0003,
    )


def add_zone_sizing(m: Model, zone: str, cooling_supply: float, heating_supply: float) -> None:
    """Sizing:Zone with the office outdoor air."""
    m.add(
        "Sizing:Zone",
        zone_or_zonelist_name=zone,
        zone_cooling_design_supply_air_temperature_input_method="SupplyAirTemperature",
        zone_cooling_design_supply_air_temperature=cooling_supply,
        zone_heating_design_supply_air_temperature_input_method="SupplyAirTemperature",
        zone_heating_design_supply_air_temperature=heating_supply,
        zone_cooling_design_supply_air_humidity_ratio=0.0085,
        zone_heating_design_supply_air_humidity_ratio=0.008,
        design_specification_outdoor_air_object_name="Office Outdoor Air",
        zone_heating_sizing_factor=1.2,
        zone_cooling_sizing_factor=1.15,
        cooling_design_air_flow_method="DesignDay",
        heating_design_air_flow_method="DesignDay",
    )


def add_zone(m: Model, name: str, multiplier: int = 1, *, part_of_total_area: bool = True) -> None:
    """A Zone with autocalculated geometry."""
    m.add(
        "Zone",
        name,
        direction_of_relative_north=0.0,
        x_origin=0.0,
        y_origin=0.0,
        z_origin=0.0,
        type=1,
        multiplier=multiplier,
        ceiling_height="Autocalculate",
        volume="Autocalculate",
        floor_area="Autocalculate",
        part_of_total_floor_area="Yes" if part_of_total_area else "No",
    )


def add_outputs(m: Model, inlet_nodes: Sequence[str], meters: Sequence[str], *, fans: bool, hot_water: bool) -> None:
    """The R2 outputs (contracts/results-requirements.md), hourly, and the SQLite output.

    Items that do not apply to a model (fans, hot water) are not requested, as the contract
    allows, so EnergyPlus does not warn about outputs it cannot generate.
    """
    variables = [
        "Zone Air System Sensible Heating Energy",
        "Zone Air System Sensible Cooling Energy",
        "Zone Mechanical Ventilation Standard Density Volume Flow Rate",
        "Site Outdoor Air Drybulb Temperature",
    ]
    if fans:
        variables += ["Fan Electricity Energy", "Fan Air Mass Flow Rate"]
    if hot_water:
        variables += ["Site Mains Water Temperature", "Water Use Equipment Hot Water Volume"]
    for variable in variables:
        m.add("Output:Variable", key_value="*", variable_name=variable, reporting_frequency="Hourly")
    for node in inlet_nodes:
        m.add(
            "Output:Variable", key_value=node, variable_name="System Node Mass Flow Rate", reporting_frequency="Hourly"
        )
    for meter in meters:
        m.add("Output:Meter", key_name=meter, reporting_frequency="Hourly")
    m.add("Output:SQLite", option_type="SimpleAndTabular", unit_conversion_for_tabular_data="None")
    m.add("OutputControl:Table:Style", column_separator="HTML", unit_conversion="None")
    m.add("Output:Table:SummaryReports", reports=[{"report_name": "AllSummary"}])


def base_model(building: str, *, sizing: tuple[bool, bool, bool]) -> Model:
    """A model with everything the fixtures share."""
    m = Model()
    add_run_control(m, building, sizing=sizing)
    add_envelope_library(m)
    add_schedules(m)
    add_thermostat_setpoints(m)
    add_outdoor_air_spec(m)
    return m


# --------------------------------------------------------------------------------------------
# HVAC
# --------------------------------------------------------------------------------------------


def _equipment(m: Model, zone: str, obj_type: str, name: str, *, inlet: str, exhaust: str = "") -> None:
    m.add(
        "ZoneHVAC:EquipmentList",
        f"{zone} Equipment",
        load_distribution_scheme="SequentialLoad",
        equipment=[
            {
                "zone_equipment_object_type": obj_type,
                "zone_equipment_name": name,
                "zone_equipment_cooling_sequence": 1,
                "zone_equipment_heating_or_no_load_sequence": 1,
            }
        ],
    )
    m.add(
        "ZoneHVAC:EquipmentConnections",
        zone_name=zone,
        zone_conditioning_equipment_list_name=f"{zone} Equipment",
        zone_air_inlet_node_or_nodelist_name=inlet,
        zone_air_exhaust_node_or_nodelist_name=exhaust,
        zone_air_node_name=f"{zone} Air Node",
        zone_return_air_node_or_nodelist_name=f"{zone} Return Node",
    )


def add_dx_curves(m: Model) -> None:
    """Single-speed DX cooling and heat-pump heating performance curves (EnergyPlus examples)."""
    m.add(
        "Curve:Biquadratic",
        "Cool Cap fT",
        coefficient1_constant=0.942587793,
        coefficient2_x=0.009543347,
        coefficient3_x_2=0.000683770,
        coefficient4_y=-0.011042676,
        coefficient5_y_2=0.000005249,
        coefficient6_x_y=-0.000009720,
        minimum_value_of_x=12.77778,
        maximum_value_of_x=23.88889,
        minimum_value_of_y=18.0,
        maximum_value_of_y=46.11111,
    )
    m.add(
        "Curve:Biquadratic",
        "Cool EIR fT",
        coefficient1_constant=0.342414409,
        coefficient2_x=0.034885008,
        coefficient3_x_2=-0.000623700,
        coefficient4_y=0.004977216,
        coefficient5_y_2=0.000437951,
        coefficient6_x_y=-0.000728028,
        minimum_value_of_x=12.77778,
        maximum_value_of_x=23.88889,
        minimum_value_of_y=18.0,
        maximum_value_of_y=46.11111,
    )
    quadratics = {
        "Cool Cap fFF": (0.8, 0.2, 0.0, 0.5, 1.5),
        "Cool EIR fFF": (1.1552, -0.1808, 0.0256, 0.5, 1.5),
        "DX PLF fPLR": (0.85, 0.15, 0.0, 0.0, 1.0),
        "Heat EIR fFF": (1.3824, -0.4336, 0.0512, 0.0, 1.0),
    }
    for name, (c1, c2, c3, xmin, xmax) in quadratics.items():
        m.add(
            "Curve:Quadratic",
            name,
            coefficient1_constant=c1,
            coefficient2_x=c2,
            coefficient3_x_2=c3,
            minimum_value_of_x=xmin,
            maximum_value_of_x=xmax,
        )
    cubics = {
        "Heat Cap fT": (0.758746, 0.027626, 0.000148716, 0.0000034992, -20.0, 20.0),
        "Heat Cap fFF": (0.84, 0.16, 0.0, 0.0, 0.5, 1.5),
        "Heat EIR fT": (1.19248, -0.0300438, 0.00103745, -0.000023328, -20.0, 20.0),
    }
    for name, (c1, c2, c3, c4, xmin, xmax) in cubics.items():
        m.add(
            "Curve:Cubic",
            name,
            coefficient1_constant=c1,
            coefficient2_x=c2,
            coefficient3_x_2=c3,
            coefficient4_x_3=c4,
            minimum_value_of_x=xmin,
            maximum_value_of_x=xmax,
        )
    m.add(
        "Curve:Biquadratic",
        "Defrost EIR fT",
        coefficient1_constant=1.0,
        coefficient2_x=0.0,
        coefficient3_x_2=0.0,
        coefficient4_y=0.0,
        coefficient5_y_2=0.0,
        coefficient6_x_y=0.0,
        minimum_value_of_x=-100.0,
        maximum_value_of_x=100.0,
        minimum_value_of_y=-100.0,
        maximum_value_of_y=100.0,
    )


def _dx_cooling_coil(m: Model, name: str, inlet: str, outlet: str) -> None:
    m.add(
        "Coil:Cooling:DX:SingleSpeed",
        name,
        availability_schedule_name="Always On",
        gross_rated_total_cooling_capacity="Autosize",
        gross_rated_sensible_heat_ratio="Autosize",
        gross_rated_cooling_cop=3.4,
        rated_air_flow_rate="Autosize",
        air_inlet_node_name=inlet,
        air_outlet_node_name=outlet,
        total_cooling_capacity_function_of_temperature_curve_name="Cool Cap fT",
        total_cooling_capacity_function_of_flow_fraction_curve_name="Cool Cap fFF",
        energy_input_ratio_function_of_temperature_curve_name="Cool EIR fT",
        energy_input_ratio_function_of_flow_fraction_curve_name="Cool EIR fFF",
        part_load_fraction_correlation_curve_name="DX PLF fPLR",
    )


def add_ptac(m: Model, zone: str) -> None:
    """A packaged terminal air conditioner: on/off fan, DX cooling, gas heating, outdoor air."""
    p = f"{zone} PTAC"
    mixed, cooled, heated = f"{p} Mixed Air Node", f"{p} Cooling Outlet Node", f"{p} Heating Outlet Node"
    inlet, exhaust = f"{zone} Supply Inlet", f"{zone} Exhaust Node"
    m.add(
        "OutdoorAir:Mixer",
        f"{p} OA Mixer",
        mixed_air_node_name=mixed,
        outdoor_air_stream_node_name=f"{p} Outdoor Air Node",
        relief_air_stream_node_name=f"{p} Relief Node",
        return_air_stream_node_name=exhaust,
    )
    _dx_cooling_coil(m, f"{p} Cooling Coil", mixed, cooled)
    m.add(
        "Coil:Heating:Fuel",
        f"{p} Heating Coil",
        availability_schedule_name="Always On",
        fuel_type="NaturalGas",
        burner_efficiency=0.8,
        nominal_capacity="Autosize",
        air_inlet_node_name=cooled,
        air_outlet_node_name=heated,
    )
    m.add(
        "Fan:OnOff",
        f"{p} Fan",
        availability_schedule_name="Always On",
        fan_total_efficiency=0.5,
        pressure_rise=75.0,
        maximum_flow_rate="Autosize",
        motor_efficiency=0.9,
        motor_in_airstream_fraction=1.0,
        air_inlet_node_name=heated,
        air_outlet_node_name=inlet,
    )
    m.add(
        "ZoneHVAC:PackagedTerminalAirConditioner",
        p,
        availability_schedule_name="Always On",
        air_inlet_node_name=exhaust,
        air_outlet_node_name=inlet,
        outdoor_air_mixer_object_type="OutdoorAir:Mixer",
        outdoor_air_mixer_name=f"{p} OA Mixer",
        cooling_supply_air_flow_rate="Autosize",
        heating_supply_air_flow_rate="Autosize",
        no_load_supply_air_flow_rate="Autosize",
        cooling_outdoor_air_flow_rate="Autosize",
        heating_outdoor_air_flow_rate="Autosize",
        no_load_outdoor_air_flow_rate="Autosize",
        supply_air_fan_object_type="Fan:OnOff",
        supply_air_fan_name=f"{p} Fan",
        heating_coil_object_type="Coil:Heating:Fuel",
        heating_coil_name=f"{p} Heating Coil",
        cooling_coil_object_type="Coil:Cooling:DX:SingleSpeed",
        cooling_coil_name=f"{p} Cooling Coil",
        fan_placement="DrawThrough",
        supply_air_fan_operating_mode_schedule_name="HVAC Operation",
    )
    m.add("OutdoorAir:NodeList", nodes=[{"node_or_nodelist_name": f"{p} Outdoor Air Node"}])
    _equipment(m, zone, "ZoneHVAC:PackagedTerminalAirConditioner", p, inlet=inlet, exhaust=exhaust)


def add_ideal_loads(m: Model, zone: str) -> None:
    """Ideal loads with the office outdoor air."""
    inlet = f"{zone} Supply Inlet"
    m.add(
        "ZoneHVAC:IdealLoadsAirSystem",
        f"{zone} Ideal Loads",
        availability_schedule_name="Always On",
        zone_supply_air_node_name=inlet,
        maximum_heating_supply_air_temperature=40.0,
        minimum_cooling_supply_air_temperature=13.0,
        maximum_heating_supply_air_humidity_ratio=0.0156,
        minimum_cooling_supply_air_humidity_ratio=0.0077,
        heating_limit="NoLimit",
        cooling_limit="NoLimit",
        dehumidification_control_type="ConstantSensibleHeatRatio",
        cooling_sensible_heat_ratio=0.7,
        humidification_control_type="None",
        design_specification_outdoor_air_object_name="Office Outdoor Air",
        outdoor_air_inlet_node_name=f"{zone} Ideal Loads Outdoor Air Node",
        demand_controlled_ventilation_type="OccupancySchedule",
        outdoor_air_economizer_type="NoEconomizer",
        heat_recovery_type="None",
    )
    m.add("OutdoorAir:NodeList", nodes=[{"node_or_nodelist_name": f"{zone} Ideal Loads Outdoor Air Node"}])
    _equipment(m, zone, "ZoneHVAC:IdealLoadsAirSystem", f"{zone} Ideal Loads", inlet=inlet)


def _branch(m: Model, name: str, components: Sequence[tuple[str, str, str, str]]) -> None:
    m.add(
        "Branch",
        name,
        components=[
            {
                "component_object_type": t,
                "component_name": n,
                "component_inlet_node_name": i,
                "component_outlet_node_name": o,
            }
            for t, n, i, o in components
        ],
    )


def _pipe_branch(m: Model, name: str) -> None:
    m.add("Pipe:Adiabatic", f"{name} Pipe", inlet_node_name=f"{name} Inlet", outlet_node_name=f"{name} Outlet")
    _branch(m, name, [("Pipe:Adiabatic", f"{name} Pipe", f"{name} Inlet", f"{name} Outlet")])


def add_pthp(m: Model, zone: str) -> None:
    """A packaged terminal heat pump: on/off fan, DX cooling, heat-pump heating coil, electric backup."""
    p = f"{zone} PTHP"
    mixed, cooled, heated, fanned = (
        f"{p} Mixed Air Node",
        f"{p} Cooling Outlet Node",
        f"{p} Heat Pump Outlet Node",
        f"{p} Fan Outlet Node",
    )
    inlet, exhaust = f"{zone} Supply Inlet", f"{zone} Exhaust Node"
    m.add(
        "OutdoorAir:Mixer",
        f"{p} OA Mixer",
        mixed_air_node_name=mixed,
        outdoor_air_stream_node_name=f"{p} Outdoor Air Node",
        relief_air_stream_node_name=f"{p} Relief Node",
        return_air_stream_node_name=exhaust,
    )
    _dx_cooling_coil(m, f"{p} Cooling Coil", mixed, cooled)
    m.add(
        "Coil:Heating:DX:SingleSpeed",
        f"{p} Heat Pump Coil",
        availability_schedule_name="Always On",
        gross_rated_heating_capacity="Autosize",
        gross_rated_heating_cop=3.2,
        rated_air_flow_rate="Autosize",
        air_inlet_node_name=cooled,
        air_outlet_node_name=heated,
        heating_capacity_function_of_temperature_curve_name="Heat Cap fT",
        heating_capacity_function_of_flow_fraction_curve_name="Heat Cap fFF",
        energy_input_ratio_function_of_temperature_curve_name="Heat EIR fT",
        energy_input_ratio_function_of_flow_fraction_curve_name="Heat EIR fFF",
        part_load_fraction_correlation_curve_name="DX PLF fPLR",
        defrost_energy_input_ratio_function_of_temperature_curve_name="Defrost EIR fT",
        minimum_outdoor_dry_bulb_temperature_for_compressor_operation=-12.0,
        maximum_outdoor_dry_bulb_temperature_for_defrost_operation=5.0,
        defrost_strategy="ReverseCycle",
        defrost_control="Timed",
        defrost_time_period_fraction=0.058333,
    )
    m.add(
        "Fan:OnOff",
        f"{p} Fan",
        availability_schedule_name="Always On",
        fan_total_efficiency=0.5,
        pressure_rise=75.0,
        maximum_flow_rate="Autosize",
        motor_efficiency=0.9,
        motor_in_airstream_fraction=1.0,
        air_inlet_node_name=heated,
        air_outlet_node_name=fanned,
    )
    m.add(
        "Coil:Heating:Electric",
        f"{p} Backup Heater",
        availability_schedule_name="Always On",
        efficiency=1.0,
        nominal_capacity="Autosize",
        air_inlet_node_name=fanned,
        air_outlet_node_name=inlet,
    )
    m.add(
        "ZoneHVAC:PackagedTerminalHeatPump",
        p,
        availability_schedule_name="Always On",
        air_inlet_node_name=exhaust,
        air_outlet_node_name=inlet,
        outdoor_air_mixer_object_type="OutdoorAir:Mixer",
        outdoor_air_mixer_name=f"{p} OA Mixer",
        cooling_supply_air_flow_rate="Autosize",
        heating_supply_air_flow_rate="Autosize",
        no_load_supply_air_flow_rate="Autosize",
        cooling_outdoor_air_flow_rate="Autosize",
        heating_outdoor_air_flow_rate="Autosize",
        no_load_outdoor_air_flow_rate="Autosize",
        supply_air_fan_object_type="Fan:OnOff",
        supply_air_fan_name=f"{p} Fan",
        heating_coil_object_type="Coil:Heating:DX:SingleSpeed",
        heating_coil_name=f"{p} Heat Pump Coil",
        cooling_coil_object_type="Coil:Cooling:DX:SingleSpeed",
        cooling_coil_name=f"{p} Cooling Coil",
        supplemental_heating_coil_object_type="Coil:Heating:Electric",
        supplemental_heating_coil_name=f"{p} Backup Heater",
        maximum_supply_air_temperature_from_supplemental_heater=50.0,
        maximum_outdoor_dry_bulb_temperature_for_supplemental_heater_operation=21.0,
        fan_placement="DrawThrough",
        supply_air_fan_operating_mode_schedule_name="HVAC Operation",
    )
    m.add("OutdoorAir:NodeList", nodes=[{"node_or_nodelist_name": f"{p} Outdoor Air Node"}])
    _equipment(m, zone, "ZoneHVAC:PackagedTerminalHeatPump", p, inlet=inlet, exhaust=exhaust)


def add_vav_system(m: Model, zones: Sequence[str], plenums: dict[str, Sequence[str]]) -> tuple[str, list[str]]:  # noqa: PLR0915
    """A VAV air loop: heat recovery, economiser, chilled-water cooling, supply fan, hot-water reheat.

    ``plenums`` maps each return plenum zone to the zones that return through it; the other
    zones return straight to the return mixer. Returns the cooling coil name (chilled-water
    loop) and the reheat coil names (hot-water loop).
    """
    loop = "VAV"
    ret, mixed, cooled, supply = (
        f"{loop} Return Air Node",
        f"{loop} Mixed Air Node",
        f"{loop} Cooling Coil Outlet Node",
        f"{loop} Supply Outlet Node",
    )
    oa_in, oa_hr, relief, exhaust = (
        f"{loop} Outdoor Air Inlet Node",
        f"{loop} Heat Recovery Supply Outlet Node",
        f"{loop} Relief Air Node",
        f"{loop} Exhaust Air Node",
    )
    cooling_coil = f"{loop} Cooling Coil"
    # Outdoor-air system: heat recovery (modulated to the mixed-air setpoint), then the
    # mixer; differential dry-bulb economiser on the controller.
    m.add("OutdoorAir:NodeList", nodes=[{"node_or_nodelist_name": oa_in}])
    m.add(
        "HeatExchanger:AirToAir:SensibleAndLatent",
        f"{loop} Heat Recovery",
        availability_schedule_name="Always On",
        nominal_supply_air_flow_rate="Autosize",
        sensible_effectiveness_at_100_heating_air_flow=0.7,
        latent_effectiveness_at_100_heating_air_flow=0.0,
        sensible_effectiveness_at_100_cooling_air_flow=0.7,
        latent_effectiveness_at_100_cooling_air_flow=0.0,
        supply_air_inlet_node_name=oa_in,
        supply_air_outlet_node_name=oa_hr,
        exhaust_air_inlet_node_name=relief,
        exhaust_air_outlet_node_name=exhaust,
        nominal_electric_power=0.0,
        supply_air_outlet_temperature_control="Yes",
        heat_exchanger_type="Plate",
        frost_control_type="None",
        economizer_lockout="Yes",
    )
    m.add(
        "OutdoorAir:Mixer",
        f"{loop} OA Mixer",
        mixed_air_node_name=mixed,
        outdoor_air_stream_node_name=oa_hr,
        relief_air_stream_node_name=relief,
        return_air_stream_node_name=ret,
    )
    m.add(
        "Controller:OutdoorAir",
        f"{loop} OA Controller",
        relief_air_outlet_node_name=relief,
        return_air_node_name=ret,
        mixed_air_node_name=mixed,
        actuator_node_name=oa_in,
        minimum_outdoor_air_flow_rate="Autosize",
        maximum_outdoor_air_flow_rate="Autosize",
        economizer_control_type="DifferentialDryBulb",
        economizer_control_action_type="ModulateFlow",
        economizer_maximum_limit_dry_bulb_temperature=23.9,
        lockout_type="NoLockout",
        minimum_limit_type="FixedMinimum",
        minimum_outdoor_air_schedule_name="HVAC Operation",
        heat_recovery_bypass_control_type="BypassWhenOAFlowGreaterThanMinimum",
    )
    m.add(
        "AirLoopHVAC:ControllerList",
        f"{loop} OA Controllers",
        controller_1_object_type="Controller:OutdoorAir",
        controller_1_name=f"{loop} OA Controller",
    )
    m.add(
        "AirLoopHVAC:OutdoorAirSystem:EquipmentList",
        f"{loop} OA Equipment",
        component_1_object_type="HeatExchanger:AirToAir:SensibleAndLatent",
        component_1_name=f"{loop} Heat Recovery",
        component_2_object_type="OutdoorAir:Mixer",
        component_2_name=f"{loop} OA Mixer",
    )
    m.add(
        "AirLoopHVAC:OutdoorAirSystem",
        f"{loop} OA System",
        controller_list_name=f"{loop} OA Controllers",
        outdoor_air_equipment_list_name=f"{loop} OA Equipment",
    )
    # Supply: chilled-water coil, variable-volume fan.
    m.add(
        "Coil:Cooling:Water",
        cooling_coil,
        availability_schedule_name="Always On",
        water_inlet_node_name=f"{cooling_coil} Water Inlet",
        water_outlet_node_name=f"{cooling_coil} Water Outlet",
        air_inlet_node_name=mixed,
        air_outlet_node_name=cooled,
        type_of_analysis="SimpleAnalysis",
        heat_exchanger_configuration="CrossFlow",
    )
    m.add(
        "Controller:WaterCoil",
        f"{cooling_coil} Controller",
        control_variable="Temperature",
        action="Reverse",
        actuator_variable="Flow",
        sensor_node_name=cooled,
        actuator_node_name=f"{cooling_coil} Water Inlet",
        controller_convergence_tolerance="Autosize",
        maximum_actuated_flow="Autosize",
        minimum_actuated_flow=0.0,
    )
    m.add(
        "AirLoopHVAC:ControllerList",
        f"{loop} Controllers",
        controller_1_object_type="Controller:WaterCoil",
        controller_1_name=f"{cooling_coil} Controller",
    )
    m.add(
        "Fan:VariableVolume",
        f"{loop} Supply Fan",
        availability_schedule_name="Always On",
        fan_total_efficiency=0.6,
        pressure_rise=750.0,
        maximum_flow_rate="Autosize",
        fan_power_minimum_flow_rate_input_method="Fraction",
        fan_power_minimum_flow_fraction=0.25,
        motor_efficiency=0.9,
        motor_in_airstream_fraction=1.0,
        fan_power_coefficient_1=0.0407598940,
        fan_power_coefficient_2=0.08804497,
        fan_power_coefficient_3=-0.072926120,
        fan_power_coefficient_4=0.9437398230,
        fan_power_coefficient_5=0.0,
        air_inlet_node_name=cooled,
        air_outlet_node_name=supply,
    )
    _branch(
        m,
        f"{loop} Main Branch",
        [
            ("AirLoopHVAC:OutdoorAirSystem", f"{loop} OA System", ret, mixed),
            ("Coil:Cooling:Water", cooling_coil, mixed, cooled),
            ("Fan:VariableVolume", f"{loop} Supply Fan", cooled, supply),
        ],
    )
    m.add("BranchList", f"{loop} Branches", branches=[{"branch_name": f"{loop} Main Branch"}])
    always = ("Through: 12/31", "For: AllDays", "Until: 24:00")
    _compact(m, "VAV Supply Air Temperature", "Temperature", (*always, 12.8))
    m.add(
        "SetpointManager:Scheduled",
        f"{loop} Supply Air Temperature Manager",
        control_variable="Temperature",
        schedule_name="VAV Supply Air Temperature",
        setpoint_node_or_nodelist_name=supply,
    )
    m.add(
        "NodeList",
        f"{loop} Mixed Air Setpoint Nodes",
        nodes=[{"node_name": n} for n in (oa_hr, mixed, cooled)],
    )
    m.add(
        "SetpointManager:MixedAir",
        f"{loop} Mixed Air Manager",
        control_variable="Temperature",
        reference_setpoint_node_name=supply,
        fan_inlet_node_name=cooled,
        fan_outlet_node_name=supply,
        setpoint_node_or_nodelist_name=f"{loop} Mixed Air Setpoint Nodes",
    )
    # Demand side: VAV boxes with hot-water reheat.
    coils: list[str] = []
    splitter_out: list[str] = []
    for zone in zones:
        box_in, damper, inlet = f"{zone} VAV Inlet Node", f"{zone} Damper Outlet Node", f"{zone} Supply Inlet"
        coil = f"{zone} Reheat Coil"
        coils.append(coil)
        splitter_out.append(box_in)
        m.add(
            "Coil:Heating:Water",
            coil,
            availability_schedule_name="Always On",
            u_factor_times_area_value="Autosize",
            maximum_water_flow_rate="Autosize",
            water_inlet_node_name=f"{coil} Water Inlet",
            water_outlet_node_name=f"{coil} Water Outlet",
            air_inlet_node_name=damper,
            air_outlet_node_name=inlet,
            performance_input_method="UFactorTimesAreaAndDesignWaterFlowRate",
        )
        m.add(
            "AirTerminal:SingleDuct:VAV:Reheat",
            f"{zone} VAV Box",
            availability_schedule_name="Always On",
            damper_air_outlet_node_name=damper,
            air_inlet_node_name=box_in,
            maximum_air_flow_rate="Autosize",
            zone_minimum_air_flow_input_method="Constant",
            constant_minimum_air_flow_fraction=0.3,
            reheat_coil_object_type="Coil:Heating:Water",
            reheat_coil_name=coil,
            maximum_hot_water_or_steam_flow_rate="Autosize",
            minimum_hot_water_or_steam_flow_rate=0.0,
            air_outlet_node_name=inlet,
            convergence_tolerance=0.001,
            damper_heating_action="ReverseWithLimits",
        )
        m.add(
            "ZoneHVAC:AirDistributionUnit",
            f"{zone} ADU",
            air_distribution_unit_outlet_node_name=inlet,
            air_terminal_object_type="AirTerminal:SingleDuct:VAV:Reheat",
            air_terminal_name=f"{zone} VAV Box",
        )
        _equipment(m, zone, "ZoneHVAC:AirDistributionUnit", f"{zone} ADU", inlet=inlet)
        add_zone_sizing(m, zone, 13.0, 32.0)
    m.add(
        "AirLoopHVAC:ZoneSplitter",
        f"{loop} Zone Splitter",
        inlet_node_name=f"{loop} Zone Supply Node",
        nodes=[{"outlet_node_name": n} for n in splitter_out],
    )
    m.add(
        "AirLoopHVAC:SupplyPath",
        f"{loop} Supply Path",
        supply_air_path_inlet_node_name=f"{loop} Zone Supply Node",
        components=[{"component_object_type": "AirLoopHVAC:ZoneSplitter", "component_name": f"{loop} Zone Splitter"}],
    )
    # Return: plenums first, then the mixer.
    return_components: list[dict[str, str]] = []
    mixer_in: list[str] = []
    via_plenum = {z for served in plenums.values() for z in served}
    for plenum, served in plenums.items():
        m.add(
            "AirLoopHVAC:ReturnPlenum",
            f"{plenum} Return Plenum",
            zone_name=plenum,
            zone_node_name=f"{plenum} Air Node",
            outlet_node_name=f"{plenum} Outlet Node",
            nodes=[{"inlet_node_name": f"{z} Return Node"} for z in served],
        )
        return_components.append(
            {"component_object_type": "AirLoopHVAC:ReturnPlenum", "component_name": f"{plenum} Return Plenum"}
        )
        mixer_in.append(f"{plenum} Outlet Node")
    mixer_in += [f"{z} Return Node" for z in zones if z not in via_plenum]
    m.add(
        "AirLoopHVAC:ZoneMixer",
        f"{loop} Return Mixer",
        outlet_node_name=f"{loop} Return Path Outlet Node",
        nodes=[{"inlet_node_name": n} for n in mixer_in],
    )
    return_components.append({"component_object_type": "AirLoopHVAC:ZoneMixer", "component_name": f"{loop} Return Mixer"})
    m.add(
        "AirLoopHVAC:ReturnPath",
        f"{loop} Return Path",
        return_air_path_outlet_node_name=f"{loop} Return Path Outlet Node",
        components=return_components,
    )
    m.add(
        "AirLoopHVAC",
        loop,
        controller_list_name=f"{loop} Controllers",
        design_supply_air_flow_rate="Autosize",
        branch_list_name=f"{loop} Branches",
        supply_side_inlet_node_name=ret,
        demand_side_outlet_node_name=f"{loop} Return Path Outlet Node",
        demand_side_inlet_node_names=f"{loop} Zone Supply Node",
        supply_side_outlet_node_names=supply,
    )
    m.add(
        "Sizing:System",
        airloop_name=loop,
        type_of_load_to_size_on="Sensible",
        design_outdoor_air_flow_rate="Autosize",
        central_heating_maximum_system_air_flow_ratio=0.3,
        preheat_design_temperature=7.0,
        preheat_design_humidity_ratio=0.008,
        precool_design_temperature=12.8,
        precool_design_humidity_ratio=0.008,
        central_cooling_design_supply_air_temperature=12.8,
        central_heating_design_supply_air_temperature=12.8,
        type_of_zone_sum_to_use="NonCoincident",
        **{"100_outdoor_air_in_cooling": "No", "100_outdoor_air_in_heating": "No"},
        central_cooling_design_supply_air_humidity_ratio=0.008,
        central_heating_design_supply_air_humidity_ratio=0.008,
        cooling_supply_air_flow_rate_method="DesignDay",
        heating_supply_air_flow_rate_method="DesignDay",
        system_outdoor_air_method="ZoneSum",
        central_cooling_capacity_control_method="VAV",
    )
    return cooling_coil, coils


def _plant_demand(m: Model, prefix: str, components: Sequence[tuple[str, str, str, str]]) -> list[str]:
    """Demand-side branches: inlet pipe, one branch per component, bypass, outlet pipe."""
    _pipe_branch(m, f"{prefix} Demand Inlet")
    _pipe_branch(m, f"{prefix} Demand Bypass")
    _pipe_branch(m, f"{prefix} Demand Outlet")
    middle: list[str] = []
    for obj_type, name, inlet, outlet in components:
        _branch(m, f"{name} Branch", [(obj_type, name, inlet, outlet)])
        middle.append(f"{name} Branch")
    middle.append(f"{prefix} Demand Bypass")
    branches = [f"{prefix} Demand Inlet", *middle, f"{prefix} Demand Outlet"]
    m.add("BranchList", f"{prefix} Demand Branches", branches=[{"branch_name": b} for b in branches])
    m.add(
        "Connector:Splitter",
        f"{prefix} Demand Splitter",
        inlet_branch_name=f"{prefix} Demand Inlet",
        branches=[{"outlet_branch_name": b} for b in middle],
    )
    m.add(
        "Connector:Mixer",
        f"{prefix} Demand Mixer",
        outlet_branch_name=f"{prefix} Demand Outlet",
        branches=[{"inlet_branch_name": b} for b in middle],
    )
    m.add(
        "ConnectorList",
        f"{prefix} Demand Connectors",
        connector_1_object_type="Connector:Splitter",
        connector_1_name=f"{prefix} Demand Splitter",
        connector_2_object_type="Connector:Mixer",
        connector_2_name=f"{prefix} Demand Mixer",
    )
    return branches


def _plant_loop(
    m: Model, name: str, supply_branch: str, outlet: str, temperatures: tuple[float, float], max_flow: float | str
) -> None:
    prefix = name
    m.add("BranchList", f"{prefix} Supply Branches", branches=[{"branch_name": supply_branch}])
    m.add(
        "PlantLoop",
        name,
        fluid_type="Water",
        plant_equipment_operation_scheme_name=f"{prefix} Operation",
        loop_temperature_setpoint_node_name=outlet,
        maximum_loop_temperature=temperatures[1],
        minimum_loop_temperature=temperatures[0],
        maximum_loop_flow_rate=max_flow,
        minimum_loop_flow_rate=0.0,
        plant_loop_volume="Autocalculate",
        plant_side_inlet_node_name=f"{prefix} Supply Inlet",
        plant_side_outlet_node_name=outlet,
        plant_side_branch_list_name=f"{prefix} Supply Branches",
        demand_side_inlet_node_name=f"{prefix} Demand Inlet Inlet",
        demand_side_outlet_node_name=f"{prefix} Demand Outlet Outlet",
        demand_side_branch_list_name=f"{prefix} Demand Branches",
        demand_side_connector_list_name=f"{prefix} Demand Connectors",
        load_distribution_scheme="SequentialLoad",
    )


def add_hot_water_loop(m: Model, coils: Sequence[str]) -> None:
    """A gas boiler loop serving the reheat coils."""
    loop = "HW Loop"
    _compact(m, "HW Supply Temperature", "Temperature", ("Through: 12/31", "For: AllDays", "Until: 24:00", 80.0))
    m.add(
        "Pump:VariableSpeed",
        "HW Pump",
        inlet_node_name=f"{loop} Supply Inlet",
        outlet_node_name="HW Pump Outlet",
        design_maximum_flow_rate="Autosize",
        design_pump_head=179352.0,
        design_power_consumption="Autosize",
        motor_efficiency=0.9,
        fraction_of_motor_inefficiencies_to_fluid_stream=0.0,
        coefficient_1_of_the_part_load_performance_curve=0.0,
        coefficient_2_of_the_part_load_performance_curve=1.0,
        coefficient_3_of_the_part_load_performance_curve=0.0,
        coefficient_4_of_the_part_load_performance_curve=0.0,
        design_minimum_flow_rate=0.0,
        pump_control_type="Intermittent",
    )
    m.add(
        "Boiler:HotWater",
        "Boiler",
        fuel_type="NaturalGas",
        nominal_capacity="Autosize",
        nominal_thermal_efficiency=0.85,
        design_water_flow_rate="Autosize",
        minimum_part_load_ratio=0.0,
        maximum_part_load_ratio=1.2,
        optimum_part_load_ratio=1.0,
        boiler_water_inlet_node_name="HW Pump Outlet",
        boiler_water_outlet_node_name=f"{loop} Supply Outlet",
        water_outlet_upper_temperature_limit=95.0,
        boiler_flow_mode="LeavingSetpointModulated",
    )
    _branch(
        m,
        f"{loop} Supply Branch",
        [
            ("Pump:VariableSpeed", "HW Pump", f"{loop} Supply Inlet", "HW Pump Outlet"),
            ("Boiler:HotWater", "Boiler", "HW Pump Outlet", f"{loop} Supply Outlet"),
        ],
    )
    _plant_demand(m, loop, [("Coil:Heating:Water", c, f"{c} Water Inlet", f"{c} Water Outlet") for c in coils])
    _plant_loop(m, loop, f"{loop} Supply Branch", f"{loop} Supply Outlet", (10.0, 100.0), "Autosize")
    m.add(
        "SetpointManager:Scheduled",
        "HW Supply Temperature Manager",
        control_variable="Temperature",
        schedule_name="HW Supply Temperature",
        setpoint_node_or_nodelist_name=f"{loop} Supply Outlet",
    )
    m.add("PlantEquipmentList", "HW Equipment", equipment=[{"equipment_object_type": "Boiler:HotWater", "equipment_name": "Boiler"}])
    m.add(
        "PlantEquipmentOperation:HeatingLoad",
        "HW Heating Operation",
        load_range_1_lower_limit=0.0,
        load_range_1_upper_limit=1.0e9,
        range_1_equipment_list_name="HW Equipment",
    )
    m.add(
        "PlantEquipmentOperationSchemes",
        f"{loop} Operation",
        control_scheme_1_object_type="PlantEquipmentOperation:HeatingLoad",
        control_scheme_1_name="HW Heating Operation",
        control_scheme_1_schedule_name="Always On",
    )
    m.add(
        "Sizing:Plant",
        plant_or_condenser_loop_name=loop,
        loop_type="Heating",
        design_loop_exit_temperature=80.0,
        loop_design_temperature_difference=11.0,
    )


def add_chilled_water_loop(m: Model, coil: str) -> None:
    """An air-cooled electric chiller loop serving the air loop's cooling coil."""
    loop = "CHW Loop"
    _compact(m, "CHW Supply Temperature", "Temperature", ("Through: 12/31", "For: AllDays", "Until: 24:00", 6.7))
    biquadratics = {
        # DOE-2 air-cooled reciprocating chiller curves (EnergyPlus dataset).
        "Chiller Cap fT": (1.0215158, 0.037035864, 0.0002332476, -0.003894048, -6.52536e-05, -0.0002680452),
        "Chiller EIR fT": (0.70176857, -0.00452016, 0.0005331096, -0.005498208, 0.0005445792, -0.0007290324),
    }
    for name, (c1, c2, c3, c4, c5, c6) in biquadratics.items():
        m.add(
            "Curve:Biquadratic",
            name,
            coefficient1_constant=c1,
            coefficient2_x=c2,
            coefficient3_x_2=c3,
            coefficient4_y=c4,
            coefficient5_y_2=c5,
            coefficient6_x_y=c6,
            minimum_value_of_x=5.0,
            maximum_value_of_x=10.0,
            minimum_value_of_y=24.0,
            maximum_value_of_y=46.0,
        )
    m.add(
        "Curve:Quadratic",
        "Chiller EIR fPLR",
        coefficient1_constant=0.06369119,
        coefficient2_x=0.58488832,
        coefficient3_x_2=0.35280274,
        minimum_value_of_x=0.0,
        maximum_value_of_x=1.0,
    )
    m.add(
        "Pump:VariableSpeed",
        "CHW Pump",
        inlet_node_name=f"{loop} Supply Inlet",
        outlet_node_name="CHW Pump Outlet",
        design_maximum_flow_rate="Autosize",
        design_pump_head=179352.0,
        design_power_consumption="Autosize",
        motor_efficiency=0.9,
        fraction_of_motor_inefficiencies_to_fluid_stream=0.0,
        coefficient_1_of_the_part_load_performance_curve=0.0,
        coefficient_2_of_the_part_load_performance_curve=1.0,
        coefficient_3_of_the_part_load_performance_curve=0.0,
        coefficient_4_of_the_part_load_performance_curve=0.0,
        design_minimum_flow_rate=0.0,
        pump_control_type="Intermittent",
    )
    m.add(
        "Chiller:Electric:EIR",
        "Chiller",
        reference_capacity="Autosize",
        reference_cop=2.8,
        reference_leaving_chilled_water_temperature=6.67,
        reference_entering_condenser_fluid_temperature=35.0,
        reference_chilled_water_flow_rate="Autosize",
        reference_condenser_fluid_flow_rate="Autosize",
        cooling_capacity_function_of_temperature_curve_name="Chiller Cap fT",
        electric_input_to_cooling_output_ratio_function_of_temperature_curve_name="Chiller EIR fT",
        electric_input_to_cooling_output_ratio_function_of_part_load_ratio_curve_name="Chiller EIR fPLR",
        minimum_part_load_ratio=0.1,
        maximum_part_load_ratio=1.0,
        optimum_part_load_ratio=1.0,
        minimum_unloading_ratio=0.2,
        chilled_water_inlet_node_name="CHW Pump Outlet",
        chilled_water_outlet_node_name=f"{loop} Supply Outlet",
        condenser_inlet_node_name="Chiller Condenser Inlet Node",
        condenser_outlet_node_name="Chiller Condenser Outlet Node",
        condenser_type="AirCooled",
        condenser_fan_power_ratio=0.012,
        fraction_of_compressor_electric_consumption_rejected_by_condenser=1.0,
        leaving_chilled_water_lower_temperature_limit=2.0,
        chiller_flow_mode="LeavingSetpointModulated",
    )
    m.add("OutdoorAir:NodeList", nodes=[{"node_or_nodelist_name": "Chiller Condenser Inlet Node"}])
    _branch(
        m,
        f"{loop} Supply Branch",
        [
            ("Pump:VariableSpeed", "CHW Pump", f"{loop} Supply Inlet", "CHW Pump Outlet"),
            ("Chiller:Electric:EIR", "Chiller", "CHW Pump Outlet", f"{loop} Supply Outlet"),
        ],
    )
    _plant_demand(m, loop, [("Coil:Cooling:Water", coil, f"{coil} Water Inlet", f"{coil} Water Outlet")])
    _plant_loop(m, loop, f"{loop} Supply Branch", f"{loop} Supply Outlet", (1.0, 98.0), "Autosize")
    m.add(
        "SetpointManager:Scheduled",
        "CHW Supply Temperature Manager",
        control_variable="Temperature",
        schedule_name="CHW Supply Temperature",
        setpoint_node_or_nodelist_name=f"{loop} Supply Outlet",
    )
    m.add(
        "PlantEquipmentList",
        "CHW Equipment",
        equipment=[{"equipment_object_type": "Chiller:Electric:EIR", "equipment_name": "Chiller"}],
    )
    m.add(
        "PlantEquipmentOperation:CoolingLoad",
        "CHW Cooling Operation",
        load_range_1_lower_limit=0.0,
        load_range_1_upper_limit=1.0e9,
        range_1_equipment_list_name="CHW Equipment",
    )
    m.add(
        "PlantEquipmentOperationSchemes",
        f"{loop} Operation",
        control_scheme_1_object_type="PlantEquipmentOperation:CoolingLoad",
        control_scheme_1_name="CHW Cooling Operation",
        control_scheme_1_schedule_name="Always On",
    )
    m.add(
        "Sizing:Plant",
        plant_or_condenser_loop_name=loop,
        loop_type="Cooling",
        design_loop_exit_temperature=6.7,
        loop_design_temperature_difference=5.6,
    )


@dataclass
class WaterUse:
    """One WaterUse:Equipment: name, peak flow (m3/s) and zone (None for no zone)."""

    name: str
    peak_flow: float
    zone: str | None


def add_service_hot_water(m: Model, uses: Sequence[WaterUse]) -> None:
    """A gas water heater loop serving WaterUse:Equipment objects, with and without a zone."""
    loop = "SHW Loop"
    always = ("Through: 12/31", "For: AllDays", "Until: 24:00")
    _compact(m, "SHW Supply Temperature", "Temperature", (*always, 60.0))
    _compact(m, "SHW Target Temperature", "Temperature", (*always, 43.0))
    _compact(m, "SHW Ambient Temperature", "Temperature", (*always, 20.0))
    _compact(m, "SHW Sensible Fraction", "Fraction", (*always, 0.2))
    _compact(m, "SHW Latent Fraction", "Fraction", (*always, 0.05))
    _compact(
        m,
        "SHW Use",
        "Fraction",
        (
            "Through: 12/31",
            "For: Weekdays SummerDesignDay",
            "Until: 07:00",
            0.05,
            "Until: 09:00",
            0.6,
            "Until: 12:00",
            0.3,
            "Until: 14:00",
            0.8,
            "Until: 18:00",
            0.3,
            "Until: 24:00",
            0.05,
            "For: AllOtherDays",
            "Until: 24:00",
            0.05,
        ),
    )
    for use in uses:
        zoned: dict[str, str] = {}
        if use.zone is not None:
            zoned = {
                "zone_name": use.zone,
                "sensible_fraction_schedule_name": "SHW Sensible Fraction",
                "latent_fraction_schedule_name": "SHW Latent Fraction",
            }
        m.add(
            "WaterUse:Equipment",
            use.name,
            end_use_subcategory="Service Hot Water",
            peak_flow_rate=use.peak_flow,
            flow_rate_fraction_schedule_name="SHW Use",
            target_temperature_schedule_name="SHW Target Temperature",
            hot_water_supply_temperature_schedule_name="SHW Supply Temperature",
            **zoned,
        )
    m.add(
        "WaterUse:Connections",
        "SHW Connections",
        inlet_node_name="SHW Connections Inlet",
        outlet_node_name="SHW Connections Outlet",
        hot_water_supply_temperature_schedule_name="SHW Supply Temperature",
        connections=[{"water_use_equipment_name": u.name} for u in uses],
    )
    m.add(
        "Pump:ConstantSpeed",
        "SHW Pump",
        inlet_node_name=f"{loop} Supply Inlet",
        outlet_node_name="SHW Pump Outlet",
        design_flow_rate=0.002,
        design_pump_head=30000.0,
        design_power_consumption=110.0,
        motor_efficiency=0.9,
        fraction_of_motor_inefficiencies_to_fluid_stream=0.0,
        pump_control_type="Intermittent",
    )
    m.add(
        "WaterHeater:Mixed",
        "Water Heater",
        tank_volume=1.0,
        setpoint_temperature_schedule_name="SHW Supply Temperature",
        deadband_temperature_difference=2.0,
        maximum_temperature_limit=82.0,
        heater_control_type="Cycle",
        heater_maximum_capacity=60000.0,
        heater_minimum_capacity=0.0,
        heater_fuel_type="NaturalGas",
        heater_thermal_efficiency=0.8,
        off_cycle_parasitic_fuel_consumption_rate=0.0,
        on_cycle_parasitic_fuel_consumption_rate=0.0,
        ambient_temperature_indicator="Schedule",
        ambient_temperature_schedule_name="SHW Ambient Temperature",
        off_cycle_loss_coefficient_to_ambient_temperature=2.0,
        on_cycle_loss_coefficient_to_ambient_temperature=2.0,
        use_side_inlet_node_name="SHW Pump Outlet",
        use_side_outlet_node_name=f"{loop} Supply Outlet",
        use_side_effectiveness=1.0,
        use_side_design_flow_rate=0.002,
        source_side_design_flow_rate=0.0,
    )
    _branch(
        m,
        f"{loop} Supply Branch",
        [
            ("Pump:ConstantSpeed", "SHW Pump", f"{loop} Supply Inlet", "SHW Pump Outlet"),
            ("WaterHeater:Mixed", "Water Heater", "SHW Pump Outlet", f"{loop} Supply Outlet"),
        ],
    )
    _plant_demand(m, loop, [("WaterUse:Connections", "SHW Connections", "SHW Connections Inlet", "SHW Connections Outlet")])
    _plant_loop(m, loop, f"{loop} Supply Branch", f"{loop} Supply Outlet", (10.0, 82.0), 0.002)
    m.add(
        "SetpointManager:Scheduled",
        "SHW Temperature Manager",
        control_variable="Temperature",
        schedule_name="SHW Supply Temperature",
        setpoint_node_or_nodelist_name=f"{loop} Supply Outlet",
    )
    m.add(
        "PlantEquipmentList",
        "SHW Equipment",
        equipment=[{"equipment_object_type": "WaterHeater:Mixed", "equipment_name": "Water Heater"}],
    )
    m.add(
        "PlantEquipmentOperation:HeatingLoad",
        "SHW Heating Operation",
        load_range_1_lower_limit=0.0,
        load_range_1_upper_limit=1.0e9,
        range_1_equipment_list_name="SHW Equipment",
    )
    m.add(
        "PlantEquipmentOperationSchemes",
        f"{loop} Operation",
        control_scheme_1_object_type="PlantEquipmentOperation:HeatingLoad",
        control_scheme_1_name="SHW Heating Operation",
        control_scheme_1_schedule_name="Always On",
    )


# --------------------------------------------------------------------------------------------
# The four fixtures
# --------------------------------------------------------------------------------------------


def build_three_zone() -> Model:
    """One storey: a core zone (two spaces) and two perimeter zones; two space uses.

    Space types: ``North_Perimeter`` and ``Core`` are ``Office``, ``South_Perimeter`` is
    ``Conference``, with different load densities and occupancy schedules, so the space
    types and the load signatures give the same two space uses. PTACs (zone fans, DX
    cooling, gas heating) condition every zone. ``Core`` holds an ``InternalMass``.
    """
    m = base_model("Three Zone", sizing=(True, False, False))
    width, depth = 30.0, 15.0
    cx0, cy0, cx1, cy1 = 6.0, 4.5, 24.0, 10.5
    cells: list[tuple[Rect, str, str]] = [
        ((0.0, cy1, width, depth), "North_Perimeter", "North_Office_Space"),
        ((0.0, 7.5, cx0, cy1), "North_Perimeter", "North_Office_Space"),
        ((cx1, 7.5, width, cy1), "North_Perimeter", "North_Office_Space"),
        ((0.0, 0.0, width, cy0), "South_Perimeter", "South_Conference_Space"),
        ((0.0, cy0, cx0, 7.5), "South_Perimeter", "South_Conference_Space"),
        ((cx1, cy0, width, 7.5), "South_Perimeter", "South_Conference_Space"),
        ((cx0, cy0, 15.0, cy1), "Core", "Core_West_Space"),
        ((15.0, cy0, cx1, cy1), "Core", "Core_East_Space"),
    ]
    zones = ("Core", "North_Perimeter", "South_Perimeter")
    for zone in zones:
        add_zone(m, zone)
    spaces = {
        "North_Office_Space": ("North_Perimeter", "Office"),
        "Core_West_Space": ("Core", "Office"),
        "Core_East_Space": ("Core", "Office"),
        "South_Conference_Space": ("South_Perimeter", "Conference"),
    }
    for space, (zone, space_type) in spaces.items():
        m.add(
            "Space",
            space,
            zone_name=zone,
            ceiling_height="Autocalculate",
            volume="Autocalculate",
            floor_area="Autocalculate",
            space_type=space_type,
        )
    m.add(
        "SpaceList",
        "Office Spaces",
        spaces=[{"space_name": s} for s, (_, t) in spaces.items() if t == "Office"],
    )
    add_level(m, Level(z0=0.0, height=3.0, cells=cells, windows=True, floor="ground", ceiling="roof"))
    add_space_use_loads(
        m, "Office", "Office Spaces", people_per_area=0.05, lights=10.0, equipment=10.0, occupancy="Office Occupancy"
    )
    add_space_use_loads(
        m,
        "Conference",
        "South_Conference_Space",
        people_per_area=0.3,
        lights=12.0,
        equipment=4.0,
        occupancy="Conference Occupancy",
    )
    m.add(
        "InternalMass",
        "Core Furniture",
        construction_name="Furniture",
        zone_or_zonelist_name="Core",
        surface_area=100.0,
    )
    add_dx_curves(m)
    for zone in zones:
        add_thermostat(m, zone)
        add_zone_sizing(m, zone, 14.0, 40.0)
        add_ptac(m, zone)
    for zone in ("North_Perimeter", "South_Perimeter"):
        add_infiltration(m, zone, 0.0003)
    add_outputs(
        m,
        [f"{z} Supply Inlet" for z in zones],
        ["Heating:NaturalGas", "Cooling:Electricity", "Fans:Electricity"],
        fans=True,
        hot_water=False,
    )
    return m


TEN_W, TEN_D = 30.0, 20.0
TEN_CORE: Rect = (6.0, 6.0, 24.0, 14.0)
STOREY, PLENUM = 3.0, 1.0
TYPICAL_FLOORS = 10


def build_ten_zone(*, explicit: bool) -> Model:  # noqa: PLR0915
    """A 12-storey office over a basement, under an attic.

    Ground floor, ten typical floors and a top floor, each with a perimeter ring zone around
    a core zone; the ground and typical floors have a return plenum. With
    ``explicit=False`` the typical floor is drawn once: ``Typical_Perimeter`` has
    ``Zone`` multiplier 10; ``Typical_Core`` and ``Typical_Plenum`` have multiplier 5 and
    belong to the ``ZoneGroup`` ``Typical_Core_Group`` (zone-list multiplier 2). Floors and
    ceilings that would face another storey are adiabatic there. With ``explicit=True``
    every floor is drawn (``T01_*`` to ``T10_*``) and those surfaces are interzone.

    HVAC: the ground and typical floors are served by one VAV air loop (variable-volume
    supply fan, plate heat recovery, differential dry-bulb economiser, chilled-water cooling
    from an air-cooled chiller) with hot-water reheat from a gas boiler; the top floor by
    packaged terminal heat pumps (zone fan, DX cooling, heat-pump heating coil, electric
    backup). A gas water heater serves one ``WaterUse:Equipment`` per typical floor core
    (with a zone; EnergyPlus multiplies its flow by the zone's multipliers) and one
    building-level ``WaterUse:Equipment`` (no zone). Basement, plenums and attic are
    unconditioned.
    """
    name = "Ten Zone Explicit" if explicit else "Ten Zone Multipliers"
    m = base_model(name, sizing=(True, True, True))
    typical = [f"T{i:02d}" for i in range(1, TYPICAL_FLOORS + 1)] if explicit else ["Typical"]
    # Levels, bottom to top.
    basement = Level(
        z0=-STOREY,
        height=STOREY,
        cells=[((0.0, 0.0, TEN_W, TEN_D), "Basement", "")],
        exterior_construction="Basement Wall",
        exterior_boundary="Ground",
        floor="ground",
    )
    add_level(m, basement)
    add_zone(m, "Basement", part_of_total_area=False)
    previous = basement
    conditioned: list[str] = []  # served by the VAV air loop
    top_zones: list[str] = []  # served by packaged terminal heat pumps
    plenums: dict[str, list[str]] = {}
    # Storey index in the real building: G is 0, typical floors 1-10, top floor 11. The
    # multiplied typical floor is drawn where the first typical floor is.
    floors = [("G", 0), *((t, i) for i, t in enumerate(typical, start=1)), ("Top", TYPICAL_FLOORS + 1)]
    for floor, index in floors:
        z0 = index * (STOREY + PLENUM)
        perimeter, core, plenum = f"{floor}_Perimeter", f"{floor}_Core", f"{floor}_Plenum"
        multiplied = floor in typical and not explicit
        storey = Level(
            z0=z0,
            height=STOREY,
            cells=ring_plan(TEN_W, TEN_D, TEN_CORE, perimeter, core),
            windows=True,
            floor="adiabatic" if (multiplied or (floor == "Top" and not explicit)) else None,
        )
        add_level(m, storey)
        if storey.floor is None:
            ceiling = "Interior Slab"
            pair_levels(m, previous, storey, ceiling, ceiling)
        add_zone(m, perimeter, 10 if multiplied else 1)
        add_zone(m, core, 5 if multiplied else 1)
        if floor == "Top":
            top_zones = [perimeter, core]
            add_gable_attic(m, storey, "Attic", TEN_W, TEN_D, 3.0)
            add_zone(m, "Attic", part_of_total_area=False)
            break
        plenum_level = Level(
            z0=z0 + STOREY,
            height=PLENUM,
            cells=[((0.0, 0.0, TEN_W, TEN_D), plenum, "")],
            ceiling="adiabatic" if (multiplied or (floor == "G" and not explicit)) else None,
        )
        add_level(m, plenum_level)
        pair_levels(m, storey, plenum_level, "Drop Ceiling", "Drop Ceiling")
        add_zone(m, plenum, 5 if multiplied else 1, part_of_total_area=False)
        plenums[plenum] = [perimeter, core]
        conditioned += [perimeter, core]
        previous = plenum_level
    if not explicit:
        m.add("ZoneList", "Typical_Core_List", zones=[{"zone_name": "Typical_Core"}, {"zone_name": "Typical_Plenum"}])
        m.add("ZoneGroup", "Typical_Core_Group", zone_list_name="Typical_Core_List", zone_list_multiplier=2)
    office = [*conditioned, *top_zones]
    m.add("ZoneList", "Office_Zones", zones=[{"zone_name": z} for z in office])
    add_space_use_loads(
        m, "Office", "Office_Zones", people_per_area=0.05, lights=10.0, equipment=10.0, occupancy="Office Occupancy"
    )
    perimeters = [z for z in office if z.endswith("_Perimeter")]
    for zone in perimeters:
        add_infiltration(m, zone, 0.0003)
    m.add(
        "ZoneInfiltration:DesignFlowRate",
        "Attic Infiltration",
        zone_or_zonelist_or_space_or_spacelist_name="Attic",
        schedule_name="Always On",
        design_flow_rate_calculation_method="AirChanges/Hour",
        air_changes_per_hour=1.0,
        constant_term_coefficient=1.0,
        temperature_term_coefficient=0.0,
        velocity_term_coefficient=0.0,
        velocity_squared_term_coefficient=0.0,
    )
    for zone in office:
        add_thermostat(m, zone)
    cooling_coil, reheat_coils = add_vav_system(m, conditioned, plenums)
    add_chilled_water_loop(m, cooling_coil)
    add_hot_water_loop(m, reheat_coils)
    add_dx_curves(m)
    for zone in top_zones:
        add_zone_sizing(m, zone, 14.0, 40.0)
        add_pthp(m, zone)
    # One restroom water use per typical floor core (zone) and one building-level use (no zone).
    uses = [WaterUse(f"{floor}_Core Restroom Hot Water", 2.0e-5, f"{floor}_Core") for floor in typical]
    uses.append(WaterUse("Building Hot Water", 1.0e-4, None))
    add_service_hot_water(m, uses)
    add_outputs(
        m,
        [f"{z} Supply Inlet" for z in office],
        [
            "Heating:NaturalGas",
            "Heating:Electricity",
            "Cooling:Electricity",
            "Fans:Electricity",
            "Pumps:Electricity",
            "WaterSystems:NaturalGas",
        ],
        fans=True,
        hot_water=True,
    )
    return m


def build_bar_building() -> Model:
    """A one-storey bar of two perimeter zones (no core), ideal loads.

    Both zones have ``Daylighting:Controls`` with a reference point 3 m from the long
    facade; the building has ``Exterior:Lights`` on an astronomical clock (R20).
    """
    m = base_model("Bar Building", sizing=(True, False, False))
    width, depth = 60.0, 12.0
    cells: list[tuple[Rect, str, str]] = [
        ((0.0, 0.0, width, depth / 2), "South_Perimeter", ""),
        ((0.0, depth / 2, width, depth), "North_Perimeter", ""),
    ]
    zones = ("North_Perimeter", "South_Perimeter")
    for zone in zones:
        add_zone(m, zone)
    add_level(m, Level(z0=0.0, height=3.0, cells=cells, windows=True, floor="ground", ceiling="roof"))
    m.add("ZoneList", "Bar_Zones", zones=[{"zone_name": z} for z in zones])
    add_space_use_loads(
        m, "Office", "Bar_Zones", people_per_area=0.05, lights=10.0, equipment=10.0, occupancy="Office Occupancy"
    )
    for zone, y in (("South_Perimeter", 3.0), ("North_Perimeter", depth - 3.0)):
        point = f"{zone} Daylight Reference"
        m.add(
            "Daylighting:ReferencePoint",
            point,
            zone_or_space_name=zone,
            x_coordinate_of_reference_point=width / 2,
            y_coordinate_of_reference_point=y,
            z_coordinate_of_reference_point=0.8,
        )
        m.add(
            "Daylighting:Controls",
            f"{zone} Daylighting",
            zone_or_space_name=zone,
            daylighting_method="SplitFlux",
            availability_schedule_name="Always On",
            lighting_control_type="Continuous",
            minimum_input_power_fraction_for_continuous_or_continuousoff_dimming_control=0.3,
            minimum_light_output_fraction_for_continuous_or_continuousoff_dimming_control=0.2,
            number_of_stepped_control_steps=1,
            probability_lighting_will_be_reset_when_needed_in_manual_stepped_control=1.0,
            glare_calculation_daylighting_reference_point_name=point,
            glare_calculation_azimuth_angle_of_view_direction_clockwise_from_zone_y_axis=0.0,
            maximum_allowable_discomfort_glare_index=22.0,
            control_data=[
                {
                    "daylighting_reference_point_name": point,
                    "fraction_of_lights_controlled_by_reference_point": 1.0,
                    "illuminance_setpoint_at_reference_point": 500.0,
                }
            ],
        )
    m.add(
        "Exterior:Lights",
        "Facade and Parking Lights",
        schedule_name="Always On",
        design_level=2000.0,
        control_option="AstronomicalClock",
        end_use_subcategory="Exterior Lights",
    )
    for zone in zones:
        add_thermostat(m, zone)
        add_infiltration(m, zone, 0.0003)
        add_zone_sizing(m, zone, 13.0, 40.0)
        add_ideal_loads(m, zone)
    add_outputs(
        m,
        [f"{z} Supply Inlet" for z in zones],
        ["Heating:DistrictHeatingWater", "Cooling:DistrictCooling", "ExteriorLights:Electricity"],
        fans=False,
        hot_water=False,
    )
    return m


BUILDERS: dict[str, Callable[[], Model]] = {
    "three_zone": build_three_zone,
    "ten_zone_multipliers": lambda: build_ten_zone(explicit=False),
    "ten_zone_explicit": lambda: build_ten_zone(explicit=True),
    "bar_building": build_bar_building,
}

# --------------------------------------------------------------------------------------------
# Results: simulate and cut the SQLite file down to what reduction reads
# --------------------------------------------------------------------------------------------

KEEP_TABLES = {
    "Simulations",
    "EnvironmentPeriods",
    "Time",
    "Zones",
    "ZoneLists",
    "ZoneGroups",
    "Surfaces",
    "Constructions",
    "ConstructionLayers",
    "Materials",
    "Schedules",
    "NominalPeople",
    "NominalLighting",
    "NominalElectricEquipment",
    "NominalGasEquipment",
    "NominalHotWaterEquipment",
    "NominalSteamEquipment",
    "NominalOtherEquipment",
    "NominalBaseboardHeaters",
    "NominalInfiltration",
    "NominalVentilation",
    "ReportDataDictionary",
    "ReportData",
    "TabularData",
    "Strings",
    "StringTypes",
    "Errors",
}

KEEP_REPORTS = (
    "AnnualBuildingUtilityPerformanceSummary",
    "EnvelopeSummary",
    "EquipmentSummary",
    "InputVerificationandResultsSummary",
    "LightingSummary",
)


def trim_sql(src: Path, dst: Path) -> None:
    """Copy an EnergyPlus SQLite file keeping only the tables and reports reduction reads."""
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)
    try:
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            if table not in KEEP_TABLES:
                cur.execute(f'DROP TABLE "{table}"')
        views = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='view'")]
        for view in views:
            if view != "TabularDataWithStrings":
                cur.execute(f'DROP VIEW "{view}"')
        marks = ",".join("?" for _ in KEEP_REPORTS)
        cur.execute(
            "DELETE FROM TabularData WHERE ReportNameIndex NOT IN "
            f"(SELECT StringIndex FROM Strings WHERE Value IN ({marks}))",
            KEEP_REPORTS,
        )
        cur.execute(
            "DELETE FROM Strings WHERE StringIndex NOT IN ("
            "SELECT ReportNameIndex FROM TabularData UNION SELECT ReportForStringIndex FROM TabularData "
            "UNION SELECT TableNameIndex FROM TabularData UNION SELECT RowNameIndex FROM TabularData "
            "UNION SELECT ColumnNameIndex FROM TabularData UNION SELECT UnitsIndex FROM TabularData "
            "UNION SELECT SimulationIndex FROM TabularData)"
        )
        con.commit()
        cur.execute("VACUUM")
    finally:
        con.close()


def drop_unused_constructions(m: Model) -> None:
    """Remove library constructions a fixture does not use (EnergyPlus warns about them)."""
    for construction in list(m.doc["Construction"]):
        if not m.doc.get_referencing(construction.name):
            m.doc.removeidfobject(construction)


def run(name: str, *, do_simulate: bool, keep_runs: Path | None = None) -> None:
    """Build one fixture, write its IDF and, if asked, simulate it and write its results."""
    m = BUILDERS[name]()
    drop_unused_constructions(m)
    report = validate_document(m.doc)
    if report.errors:
        raise SystemExit(f"{name}: schema validation failed\n{report}")
    idf_path = MODELS_DIR / f"{name}.idf"
    save_idf(m.doc, idf_path)
    print(f"{name}: wrote {idf_path.relative_to(HERE.parent.parent)}")
    if not do_simulate:
        return
    with tempfile.TemporaryDirectory(prefix=f"fixture_{name}_") as tmp:
        run_dir = Path(tmp) if keep_runs is None else keep_runs / name
        result = simulate(m.doc, WEATHER_FILE, output_dir=run_dir, annual=True, expand_objects=False, timeout=3600)
        errs = result.errors
        print(f"{name}: {errs.summary()}")
        if not result.success or errs.has_severe or result.sql_path is None:
            raise SystemExit(f"{name}: simulation failed; see the summary above")
        trim_sql(result.sql_path, MODELS_DIR / f"{name}.sql")
    size = (MODELS_DIR / f"{name}.sql").stat().st_size / 1e6
    print(f"{name}: wrote {name}.sql ({size:.1f} MB)")


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help=f"fixtures to rebuild, among {', '.join(BUILDERS)} (default: all)")
    parser.add_argument("--no-simulate", action="store_true", help="only rewrite the IDF files")
    parser.add_argument("--keep-runs", type=Path, help="keep each EnergyPlus run directory under this path")
    args = parser.parse_args(argv)
    names: list[str] = list(args.names) or list(BUILDERS)
    unknown = sorted(set(names) - set(BUILDERS))
    if unknown:
        parser.error(f"unknown fixture(s): {', '.join(unknown)}")
    for name in names:
        run(name, do_simulate=not args.no_simulate, keep_runs=args.keep_runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
