"""Check the UP-10 bridge against EnergyPlus and write `tests/data/umi/simple_glazing_energyplus.json`.

Spec 003, T032 (research R8). For each of 12 (U, SHGC, VT) cases spanning single to triple
glazing, the script builds one model with idfkit holding two identical windows on the south
wall of a box zone: one with a `WindowMaterial:SimpleGlazingSystem`, one whose only layer is
the `WindowMaterial:Glazing` that `archetypal.umi._bridges.equivalent_glazing_layer` returns.
It runs EnergyPlus 24.2 through `idfkit.simulation` and reads each window's U-factor, SHGC
and visible transmittance from the *Envelope Summary* report's *Exterior Fenestration*
table. It also reads, from the `.eio` file, the layer EnergyPlus itself derives from the
simple glazing. The inputs, the bridge's layer, EnergyPlus's layer and both windows' results
are written to the JSON file, which `tests/unit/umi/test_rules_windows.py` reads.

Run it from the repository root with EnergyPlus 24.2 installed:

```console
$ uv run python verification/umi/simple_glazing.py [tests/data/umi/simple_glazing_energyplus.json]
```

EnergyPlus reports U, SHGC and VT with three decimals and the `.eio` layer with five
significant digits, so the file holds them at that precision.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

from idfkit import new_document
from idfkit.simulation import find_energyplus, simulate
from idfkit.versioned import IDFDocumentV24_2

from archetypal.umi._bridges import EquivalentGlazingLayer, equivalent_glazing_layer

if TYPE_CHECKING:
    from idfkit.simulation import EnergyPlusConfig

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "tests" / "data" / "umi" / "simple_glazing_energyplus.json"
WEATHER = ROOT / "tests" / "fixtures" / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"

CASES: tuple[tuple[float, float, float], ...] = (
    # (U-factor W/m2-K, SHGC, VT): single glazing ...
    (5.8, 0.82, 0.88),
    (5.0, 0.60, 0.55),
    (6.5, 0.30, 0.25),
    # ... the interpolated range 3.4 <= U <= 4.5 ...
    (4.5, 0.70, 0.75),
    (4.0, 0.75, 0.80),
    (3.4, 0.45, 0.50),
    # ... double glazing ...
    (2.8, 0.70, 0.78),
    (1.8, 0.40, 0.60),
    (1.4, 0.25, 0.45),
    (1.6, 0.12, 0.10),
    # ... and triple glazing.
    (1.0, 0.50, 0.70),
    (0.7, 0.35, 0.55),
)
"""The (U, SHGC, VT) grid: single to triple glazing, crossing EnergyPlus's breakpoints."""

SIMPLE = "Simple window"
LAYER = "Layer window"
_WIDTH, _DEPTH, _HEIGHT = 10.0, 6.0, 3.0


def _box(doc: IDFDocumentV24_2) -> None:
    """Add a 10 m x 6 m x 3 m zone with an opaque envelope."""
    doc.materials.add(
        "Wall material",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=0.5,
        density=1800.0,
        specific_heat=900.0,
    )
    doc.constructions.add("Opaque", outside_layer="Wall material")
    doc.zones.add("Box")
    w, d, h = _WIDTH, _DEPTH, _HEIGHT
    walls = {
        "South": [(0.0, 0.0, h), (0.0, 0.0, 0.0), (w, 0.0, 0.0), (w, 0.0, h)],
        "East": [(w, 0.0, h), (w, 0.0, 0.0), (w, d, 0.0), (w, d, h)],
        "North": [(w, d, h), (w, d, 0.0), (0.0, d, 0.0), (0.0, d, h)],
        "West": [(0.0, d, h), (0.0, d, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, h)],
    }
    surfaces = [(name, "Wall", "Outdoors", points) for name, points in walls.items()]
    surfaces.append(("Floor", "Floor", "Ground", [(0.0, d, 0.0), (w, d, 0.0), (w, 0.0, 0.0), (0.0, 0.0, 0.0)]))
    surfaces.append(("Roof", "Roof", "Outdoors", [(0.0, 0.0, h), (w, 0.0, h), (w, d, h), (0.0, d, h)]))
    for name, surface_type, boundary, points in surfaces:
        exposed = "NoSun" if boundary == "Ground" else "SunExposed"
        doc.building_surfaces.add(
            name,
            surface_type=surface_type,
            construction_name="Opaque",
            zone_name="Box",
            outside_boundary_condition=boundary,
            sun_exposure=exposed,
            wind_exposure="NoWind" if boundary == "Ground" else "WindExposed",
            vertices=[{"vertex_x_coordinate": x, "vertex_y_coordinate": y, "vertex_z_coordinate": z} for x, y, z in points],
        )


def _window(doc: IDFDocumentV24_2, name: str, construction: str, x0: float) -> None:
    x1 = x0 + 3.0
    doc.fenestration_surfaces.add(
        name,
        surface_type="Window",
        construction_name=construction,
        building_surface_name="South",
        number_of_vertices=4,
        vertex_1_x_coordinate=x0,
        vertex_1_y_coordinate=0.0,
        vertex_1_z_coordinate=2.5,
        vertex_2_x_coordinate=x0,
        vertex_2_y_coordinate=0.0,
        vertex_2_z_coordinate=0.5,
        vertex_3_x_coordinate=x1,
        vertex_3_y_coordinate=0.0,
        vertex_3_z_coordinate=0.5,
        vertex_4_x_coordinate=x1,
        vertex_4_y_coordinate=0.0,
        vertex_4_z_coordinate=2.5,
    )


def build_model(u_factor: float, shgc: float, vt: float, layer: EquivalentGlazingLayer) -> IDFDocumentV24_2:
    """Return the model of one case: the simple-glazing window and the equivalent-layer window."""
    doc = new_document(IDFDocumentV24_2)
    doc.timestep.add(number_of_timesteps_per_hour=4)
    for control in doc.simulation_control:
        control.update(
            do_zone_sizing_calculation="No",
            do_system_sizing_calculation="No",
            do_plant_sizing_calculation="No",
            run_simulation_for_sizing_periods="No",
            run_simulation_for_weather_file_run_periods="Yes",
        )
    doc.run_periods.add("Day", begin_month=1, begin_day_of_month=1, end_month=1, end_day_of_month=1)
    _box(doc)
    doc.window_material_simple_glazing_systems.add(
        "Simple glazing", u_factor=u_factor, solar_heat_gain_coefficient=shgc, visible_transmittance=vt
    )
    doc.window_material_glazings.add(
        "Equivalent layer",
        optical_data_type="SpectralAverage",
        thickness=layer.thickness,
        solar_transmittance_at_normal_incidence=layer.solar_transmittance,
        front_side_solar_reflectance_at_normal_incidence=layer.front_solar_reflectance,
        back_side_solar_reflectance_at_normal_incidence=layer.back_solar_reflectance,
        visible_transmittance_at_normal_incidence=layer.visible_transmittance,
        front_side_visible_reflectance_at_normal_incidence=layer.front_visible_reflectance,
        back_side_visible_reflectance_at_normal_incidence=layer.back_visible_reflectance,
        infrared_transmittance_at_normal_incidence=layer.infrared_transmittance,
        front_side_infrared_hemispherical_emissivity=layer.front_infrared_emissivity,
        back_side_infrared_hemispherical_emissivity=layer.back_infrared_emissivity,
        conductivity=layer.conductivity,
    )
    doc.constructions.add(SIMPLE, outside_layer="Simple glazing")
    doc.constructions.add(LAYER, outside_layer="Equivalent layer")
    _window(doc, SIMPLE, SIMPLE, 1.0)
    _window(doc, LAYER, LAYER, 6.0)
    doc.output_sqlite.add(option_type="SimpleAndTabular")
    doc.output_table_summary_reports.add(reports=[{"report_name": "EnvelopeSummary"}])
    # Writes each material, including the layer EnergyPlus derives from the simple glazing, to the .eio file.
    doc.output_constructions.add(details_type_1="Constructions", details_type_2="Materials")
    return doc


_EIO_FIELDS = (
    # Field positions of a `WindowMaterial:Glazing` line of the .eio file (its header in EnergyPlus 24.2).
    ("thickness", 4),
    ("solar_transmittance", 5),
    ("front_solar_reflectance", 6),
    ("back_solar_reflectance", 7),
    ("visible_transmittance", 8),
    ("front_visible_reflectance", 9),
    ("back_visible_reflectance", 10),
    ("infrared_transmittance", 11),
    ("front_infrared_emissivity", 12),
    ("back_infrared_emissivity", 13),
    ("conductivity", 14),
)


def energyplus_layer(eio: Path, material: str) -> dict[str, float]:
    """Return the glazing layer EnergyPlus reports in the .eio file for one material.

    For a `WindowMaterial:SimpleGlazingSystem`, it is the equivalent layer EnergyPlus derived
    and simulates, printed with five significant digits.
    """
    for line in eio.read_text(encoding="utf-8").splitlines():
        fields = [field.strip() for field in line.split(",")]
        if fields[:2] == ["WindowMaterial:Glazing", material.upper()]:
            return {key: float(fields[index]) for key, index in _EIO_FIELDS}
    msg = f"{eio} has no WindowMaterial:Glazing line for {material!r}"
    raise LookupError(msg)


_COLUMNS = {
    "u_factor": "Glass U-Factor",
    "shgc": "Glass SHGC",
    "visible_transmittance": "Glass Visible Transmittance",
}


def run_case(
    u_factor: float, shgc: float, vt: float, energyplus: EnergyPlusConfig
) -> dict[str, dict[str, float]]:
    """Simulate one case and return its inputs, layer and the two windows' reported values."""
    layer = equivalent_glazing_layer(u_factor, shgc, vt)
    doc = build_model(u_factor, shgc, vt, layer)
    with simulate(doc, WEATHER, energyplus=energyplus) as result:
        result.raise_for_status()
        sql = result.sql
        if sql is None:  # pragma: no cover - Output:SQLite is in the model
            msg = "EnergyPlus wrote no SQLite output"
            raise RuntimeError(msg)
        reported = {
            window: {
                key: sql.get_tabular_float(
                    report_name="EnvelopeSummary",
                    table_name="Exterior Fenestration",
                    row_name=window.upper(),
                    column_name=column,
                )
                for key, column in _COLUMNS.items()
            }
            for window in (SIMPLE, LAYER)
        }
        derived = energyplus_layer(result.run_dir / "eplus.eio", "Simple glazing")
    return {
        "inputs": {"u_factor": u_factor, "shgc": shgc, "visible_transmittance": vt},
        "layer": dataclasses.asdict(layer),
        "energyplus_layer": derived,
        "simple_glazing": reported[SIMPLE],
        "equivalent_layer": reported[LAYER],
    }


def main(argv: list[str] | None = None) -> int:
    """Run every case and write the JSON file."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    energyplus = find_energyplus(version=(24, 2, 0))
    cases = [run_case(u, shgc, vt, energyplus) for u, shgc, vt in CASES]
    data = {
        "description": (
            "U-factor, SHGC and visible transmittance EnergyPlus reports (Envelope Summary, Exterior "
            "Fenestration) for a WindowMaterial:SimpleGlazingSystem and for the single "
            "WindowMaterial:Glazing archetypal.umi._bridges.equivalent_glazing_layer returns for it."
        ),
        "generated_by": "verification/umi/simple_glazing.py",
        "energyplus": ".".join(str(part) for part in energyplus.version),
        "idfkit": version("idfkit"),
        "cases": cases,
    }
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    worst = {
        key: max(abs(case["equivalent_layer"][key] - case["inputs"][key]) for case in cases) for key in _COLUMNS
    }
    sys.stdout.write(f"wrote {output}; largest |layer - target|: {worst}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
