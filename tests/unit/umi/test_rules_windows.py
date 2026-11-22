"""The window rules (spec 003, T017, research R8): simple glazing from layers, the equivalent layer, placement."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import idfkit.thermal
import pytest
from epinterface.sbem.components.envelope import GlazingConstructionLayeredComponent, GlazingConstructionSimpleComponent
from idfkit import new_document
from idfkit.thermal import calculate_shgc, calculate_u_value, calculate_visible_transmittance

from archetypal.umi import _refs
from archetypal.umi._bridges import equivalent_glazing_layer
from archetypal.umi._format import (
    GasMaterial,
    GlazingMaterial,
    MaterialLayer,
    ShadingType,
    WindowConstruction,
    WindowSettings,
)
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind
from archetypal.umi.rules import windows

from .test_rules_loads import read_schedule, reading, umi_schedule, write_schedule, writing

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
SAMPLES = {"B2": UMI / "BostonTemplateLibrary_2.json", "UZ": UMI / "umi_samples_BostonTemplateLibrary.json"}
ENERGYPLUS = Path(__file__).parents[2] / "data" / "umi" / "simple_glazing_energyplus.json"
CASES: list[dict[str, Any]] = json.loads(ENERGYPLUS.read_text(encoding="utf-8"))["cases"]

# EnergyPlus reports U, SHGC and VT with three decimals. A WindowMaterial:Glazing layer whose
# properties EnergyPlus derived from a simple glazing reproduces the simple glazing's targets
# within these tolerances...
U_TOLERANCE = 0.025  # W/m2-K
SHGC_TOLERANCE = 0.005
VT_TOLERANCE = 0.003
# ... except that, with its standard film coefficients, EnergyPlus computes at most this U for
# any glazing layer (W/m2-K); a simple glazing above it is written as a layer at this U.
LAYER_U_MAX = windows.LAYER_U_MAX


def window_constructions() -> list[tuple[str, WindowConstruction]]:
    found: list[tuple[str, WindowConstruction]] = []
    for sample, path in SAMPLES.items():
        library = _refs.resolve(json.loads(path.read_text(encoding="utf-8")), sample).library
        found.extend((f"{sample}:{c.name}", c) for c in library.window_constructions)
    return found


CONSTRUCTIONS = window_constructions()


def case_id(case: dict[str, Any]) -> str:
    inputs = case["inputs"]
    return f"U{inputs['u_factor']}-SHGC{inputs['shgc']}-VT{inputs['visible_transmittance']}"


def idfkit_values(construction: WindowConstruction) -> tuple[float, float, float]:
    """U, SHGC and VT of the layers, computed by idfkit.thermal on a construction built here."""
    doc = new_document(version=(24, 2, 0))
    layers: list[str] = []
    for index, layer in enumerate(construction.layers):
        material = layer.material
        name = f"Layer {index}"
        if isinstance(material, GlazingMaterial):
            doc.add(
                "WindowMaterial:Glazing",
                name,
                optical_data_type="SpectralAverage",
                thickness=layer.thickness,
                solar_transmittance_at_normal_incidence=material.solar_transmittance,
                front_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_front,
                back_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_back,
                visible_transmittance_at_normal_incidence=material.visible_transmittance,
                front_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_front,
                back_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_back,
                infrared_transmittance_at_normal_incidence=material.ir_transmittance,
                front_side_infrared_hemispherical_emissivity=material.ir_emissivity_front,
                back_side_infrared_hemispherical_emissivity=material.ir_emissivity_back,
                conductivity=material.conductivity,
                dirt_correction_factor_for_solar_and_visible_transmittance=material.dirt_factor,
            )
        else:
            assert isinstance(material, GasMaterial)
            gas = material.type if material.type.upper() in {"AIR", "ARGON", "KRYPTON", "XENON"} else material.name
            assert gas is not None
            doc.add("WindowMaterial:Gas", name, gas_type=gas.capitalize(), thickness=layer.thickness)
        layers.append(name)
    fields: dict[str, Any] = {
        "outside_layer": layers[0],
        **{f"layer_{i}": n for i, n in enumerate(layers[1:], start=2)},
    }
    window = doc.add("Construction", "Window", fields)
    u, shgc, vt = calculate_u_value(window), calculate_shgc(window), calculate_visible_transmittance(window)
    assert shgc is not None
    assert vt is not None
    return u, shgc, vt


def simple(
    name: str = "Simple", u: float = 1.8, shgc: float = 0.4, vt: float = 0.6
) -> GlazingConstructionSimpleComponent:
    return GlazingConstructionSimpleComponent(Name=name, UValue=u, SHGF=shgc, TVis=vt, Type="Double")


# --- Registration ------------------------------------------------------------------------------


def test_rules_are_registered_in_windows() -> None:
    assert get_rule("window.layers").to_sbem is windows.layers_to_sbem
    assert get_rule("window.layers").to_umi is windows.layers_to_umi
    assert get_rule("window.placement").to_sbem is windows.place_window
    assert get_rule("window.placement").to_umi is windows.template_window
    assert get_rule("window.settings").to_sbem is windows.settings_to_sbem
    assert get_rule("window.settings").to_umi is windows.settings_to_umi


# --- window.layers (UP-9's layered windows) ----------------------------------------------------


@pytest.mark.parametrize(("label", "construction"), CONSTRUCTIONS, ids=[label for label, _ in CONSTRUCTIONS])
def test_layers_read_and_write_back_exactly(label: str, construction: WindowConstruction) -> None:
    window, losses = windows.layers_to_sbem(construction, subject="T", location="/WindowConstructions/0")
    assert isinstance(window, GlazingConstructionLayeredComponent), label
    assert losses == []
    assert len(window.Layers) == len(construction.layers)
    for layer, original in zip(window.Layers, construction.layers, strict=True):
        assert layer.Thickness == original.thickness
    back, losses = windows.layers_to_umi(window, subject="A", location="perimeter.Envelope.Window")
    assert losses == []
    assert [layer.thickness for layer in back.layers] == [layer.thickness for layer in construction.layers]
    for layer, original in zip(back.layers, construction.layers, strict=True):
        material, source = layer.material, original.material
        assert type(material) is type(source)
        if isinstance(material, GlazingMaterial) and isinstance(source, GlazingMaterial):
            for field in ("solar_transmittance", "visible_transmittance", "ir_emissivity_front", "conductivity"):
                assert getattr(material, field) == getattr(source, field), (label, field)
        elif isinstance(material, GasMaterial) and isinstance(source, GasMaterial):
            assert material.type == windows._gas_type(source).upper()  # pyright: ignore[reportPrivateUsage]


def test_layers_the_fork_cannot_hold_give_simple_glazing() -> None:
    glass = GlazingMaterial(Name="Glass", Conductivity=0.9)
    air = GasMaterial(Name="Air", Type="AIR")
    layer = MaterialLayer[GlazingMaterial | GasMaterial]
    panes = [layer(Material=glass, Thickness=0.003), layer(Material=air, Thickness=0.012)] * 4
    construction = WindowConstruction(Name="Quintuple", Layers=(*panes, layer(Material=glass, Thickness=0.003)))
    window, losses = windows.layers_to_sbem(construction, subject="T", location="/WindowConstructions/0")
    assert isinstance(window, GlazingConstructionSimpleComponent)
    assert all(loss.rule == "window.layers" and loss.upstream is None for loss in losses)
    assert "5 panes" in losses[0].reason


def test_a_simple_window_is_written_as_its_equivalent_layer() -> None:
    window = simple("Low-e double", u=1.8, shgc=0.4, vt=0.6)
    construction, losses = windows.layers_to_umi(window, subject="A", location="perimeter.Envelope.Window")
    assert len(construction.layers) == 1
    (loss,) = losses
    assert (loss.kind, loss.rule) == (LossKind.APPROXIMATE, "window.layers")


# --- window.simple_from_layers (reading) -------------------------------------------------------


def test_samples_have_window_constructions() -> None:
    assert len(CONSTRUCTIONS) == 10


@pytest.mark.parametrize(("label", "construction"), CONSTRUCTIONS, ids=[label for label, _ in CONSTRUCTIONS])
def test_simple_from_layers_equals_idfkit(label: str, construction: WindowConstruction) -> None:
    window, _ = windows.simple_from_layers(construction, subject="T", location="/WindowConstructions/0")
    u, shgc, vt = idfkit_values(construction)
    assert window.UValue == pytest.approx(u, rel=1e-12)
    assert pytest.approx(shgc, rel=1e-12) == window.SHGF
    assert window.TVis == pytest.approx(vt, rel=1e-12)
    assert window.Name == construction.name
    glazings = sum(isinstance(layer.material, GlazingMaterial) for layer in construction.layers)
    assert window.Type == {1: "Single", 2: "Double"}[glazings], label


def test_simple_from_layers_lists_layers_lost_and_values_approximate() -> None:
    _, construction = next(c for c in CONSTRUCTIONS if c[1].name == "B_Dbl_Arg_Le")
    window, losses = windows.simple_from_layers(construction, subject="B_Off_0", location="/WindowConstructions/3")
    lost = [loss for loss in losses if loss.kind is LossKind.LOST]
    assert [loss.location for loss in lost] == [f"/WindowConstructions/3/Layers/{i}" for i in range(3)]
    assert all(loss.rule == "window.layers" and loss.upstream is None for loss in lost)
    assert all(loss.subject == "B_Off_0" for loss in losses)
    assert isinstance(lost[1].value, dict)
    assert lost[1].value["Thickness"] == 0.006
    (approximate,) = (loss for loss in losses if loss.kind is LossKind.APPROXIMATE)
    assert approximate.rule == "window.layers"
    assert approximate.replacement == {"UValue": window.UValue, "SHGF": window.SHGF, "TVis": window.TVis}
    assert "idfkit" in approximate.reason
    assert len(losses) == 4


def test_simple_from_layers_refuses_a_gas_energyplus_lacks() -> None:
    glass = GlazingMaterial(Name="Glass", Conductivity=0.9)
    sf6 = GasMaterial(Name="SF6", Type="SF6")
    construction = WindowConstruction(
        Name="SF6 unit",
        Layers=(
            MaterialLayer[GlazingMaterial | GasMaterial](Material=glass, Thickness=0.003),
            MaterialLayer[GlazingMaterial | GasMaterial](Material=sf6, Thickness=0.012),
            MaterialLayer[GlazingMaterial | GasMaterial](Material=glass, Thickness=0.003),
        ),
    )
    with pytest.raises(ValueError, match="SF6"):
        windows.simple_from_layers(construction, subject="T", location="/WindowConstructions/0")


def test_simple_from_layers_refuses_a_construction_without_glazing() -> None:
    with pytest.raises(ValueError, match="no glazing"):
        windows.simple_from_layers(WindowConstruction(Name="Empty"), subject="T", location="/WindowConstructions/0")


def test_triple_glazing_is_typed_triple() -> None:
    glass = GlazingMaterial(Name="Glass", Conductivity=0.9)
    air = GasMaterial(Name="AIR", Type="AIR")
    layer = MaterialLayer[GlazingMaterial | GasMaterial]
    construction = WindowConstruction(
        Name="Triple",
        Layers=(
            layer(Material=glass, Thickness=0.003),
            layer(Material=air, Thickness=0.012),
            layer(Material=glass, Thickness=0.003),
            layer(Material=air, Thickness=0.012),
            layer(Material=glass, Thickness=0.003),
        ),
    )
    window, _ = windows.simple_from_layers(construction, subject="T", location="/WindowConstructions/0")
    assert window.Type == "Triple"
    assert window.UValue == pytest.approx(idfkit_values(construction)[0], rel=1e-12)


# --- window.equivalent_layer (writing) and the UP-10 bridge ------------------------------------


def test_energyplus_data_covers_twelve_cases() -> None:
    assert len(CASES) == 12
    assert json.loads(ENERGYPLUS.read_text(encoding="utf-8"))["energyplus"] == "24.2.0"


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_equivalent_layer_is_the_recorded_layer(case: dict[str, Any]) -> None:
    inputs, recorded = case["inputs"], case["layer"]
    window = simple(u=inputs["u_factor"], shgc=inputs["shgc"], vt=inputs["visible_transmittance"])
    construction, _ = windows.equivalent_layer(window, subject="A", location="perimeter.Envelope.Window")
    (layer,) = construction.layers
    glass = layer.material
    assert isinstance(glass, GlazingMaterial)
    written = {
        "thickness": layer.thickness,
        "conductivity": glass.conductivity,
        "solar_transmittance": glass.solar_transmittance,
        "front_solar_reflectance": glass.solar_reflectance_front,
        "back_solar_reflectance": glass.solar_reflectance_back,
        "visible_transmittance": glass.visible_transmittance,
        "front_visible_reflectance": glass.visible_reflectance_front,
        "back_visible_reflectance": glass.visible_reflectance_back,
        "infrared_transmittance": glass.ir_transmittance,
        "front_infrared_emissivity": glass.ir_emissivity_front,
        "back_infrared_emissivity": glass.ir_emissivity_back,
    }
    assert written == pytest.approx(recorded, rel=1e-12, abs=1e-15)
    assert glass.dirt_factor == 1.0
    assert construction.name == window.Name


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_bridge_layer_is_energyplus_layer(case: dict[str, Any]) -> None:
    # EnergyPlus prints the layer it derives from the simple glazing with five significant digits.
    for key, value in case["energyplus_layer"].items():
        assert case["layer"][key] == pytest.approx(value, rel=1e-4, abs=2e-5), key


@pytest.mark.parametrize("case", CASES, ids=case_id)
def test_energyplus_reproduces_targets_with_the_layer(case: dict[str, Any]) -> None:
    inputs, result = case["inputs"], case["equivalent_layer"]
    assert result["u_factor"] == pytest.approx(min(inputs["u_factor"], LAYER_U_MAX), abs=U_TOLERANCE)
    assert result["shgc"] == pytest.approx(inputs["shgc"], abs=SHGC_TOLERANCE)
    assert result["visible_transmittance"] == pytest.approx(inputs["visible_transmittance"], abs=VT_TOLERANCE)


def test_equivalent_layer_lists_the_window_as_approximate() -> None:
    window = simple("Low-e double", u=1.8, shgc=0.4, vt=0.6)
    construction, losses = windows.equivalent_layer(window, subject="A", location="perimeter.Envelope.Window")
    (loss,) = losses
    assert loss.kind is LossKind.APPROXIMATE
    assert loss.rule == "window.layers"
    assert loss.location == "perimeter.Envelope.Window"
    assert loss.value == {"UValue": 1.8, "SHGF": 0.4, "TVis": 0.6, "Type": "Double"}
    assert loss.replacement == {
        "Layers": [{"Material": "Low-e double glazing", "Thickness": construction.layers[0].thickness}]
    }


def test_equivalent_layer_above_the_layer_maximum_says_so() -> None:
    _, losses = windows.equivalent_layer(simple(u=6.5, shgc=0.3, vt=0.25), subject="A", location="core.Envelope.Window")
    assert str(LAYER_U_MAX) in losses[0].reason


@pytest.mark.parametrize(
    ("u", "shgc", "vt"),
    [(0.0, 0.4, 0.6), (7.1, 0.4, 0.6), (1.8, 0.0, 0.6), (1.8, 1.0, 0.6), (1.8, 0.4, 1.0), (math.nan, 0.4, 0.6)],
)
def test_bridge_refuses_inputs_energyplus_refuses(u: float, shgc: float, vt: float) -> None:
    with pytest.raises(ValueError, match="WindowMaterial:SimpleGlazingSystem"):
        equivalent_glazing_layer(u, shgc, vt)


def test_bridge_without_vt_uses_the_solar_values() -> None:
    layer = equivalent_glazing_layer(1.8, 0.4)
    assert layer.visible_transmittance == layer.solar_transmittance
    assert layer.front_visible_reflectance == layer.front_solar_reflectance
    assert layer.back_visible_reflectance == layer.back_solar_reflectance


def test_remove_bridge_once_idfkit_releases_up10() -> None:
    offered = [name for name in dir(idfkit.thermal) if "equivalent" in name.lower()]
    assert not offered, (
        f"idfkit.thermal now offers {offered}: UP-10 is released. Do T072: call it from "
        "archetypal.umi.rules.windows, delete archetypal/umi/_bridges.py and this test."
    )


# --- window.placement --------------------------------------------------------------------------


def test_reading_gives_both_groups_the_template_window() -> None:
    window = simple()
    assert windows.place_window(window, ("core", "perimeter")) == {"core": window, "perimeter": window}
    assert windows.place_window(None, ("core", "perimeter")) == {"core": None, "perimeter": None}


def test_writing_uses_the_perimeter_window() -> None:
    perimeter = simple("Perimeter window")
    window, losses = windows.template_window({"core": perimeter, "perimeter": perimeter}, subject="A")
    assert window is perimeter
    assert losses == []


def test_writing_lists_a_different_core_window_as_lost() -> None:
    perimeter, core = simple("Perimeter window"), simple("Core window", u=2.8)
    window, losses = windows.template_window({"core": core, "perimeter": perimeter}, subject="A")
    assert window is perimeter
    (loss,) = losses
    assert loss.kind is LossKind.LOST
    assert loss.rule == "window.placement"
    assert loss.location == "core.Envelope.Window"
    assert loss.subject == "A"
    assert loss.value == core.model_dump(mode="json", exclude_none=True)
    assert loss.replacement == "Perimeter window"


def test_writing_without_a_perimeter_group_uses_the_only_group() -> None:
    only = simple("Only")
    assert windows.template_window({"whole": only}, subject="A") == (only, [])
    assert windows.template_window({"core": None, "perimeter": None}, subject="A") == (None, [])


# --- window.settings (UP-9) --------------------------------------------------------------------


def umi_settings(**fields: object) -> WindowSettings:
    values: dict[str, object] = {
        "Name": "Shaded",
        "OperableArea": 0.5,
        "IsShadingSystemOn": True,
        "ShadingSystemType": ShadingType.InteriorShade,
        "ShadingSystemSetpoint": 250.0,
        "ShadingSystemTransmittance": 0.3,
        "ShadingSystemAvailabilitySchedule": umi_schedule("summer", 0.0),
        "AfnWindowAvailability": umi_schedule("on"),
        "ZoneMixingAvailabilitySchedule": umi_schedule("on"),
    }
    values.update(fields)
    return WindowSettings.model_validate(values)


def test_settings_map_to_the_window_settings_component() -> None:
    context = reading("/BuildingTemplates/0/Windows")
    component = windows.settings_to_sbem(umi_settings(), schedule=read_schedule, context=context)
    assert context.losses == []
    assert (component.Name, component.OperableArea, component.IsShadingSystemOn) == ("Shaded", 0.5, True)
    assert (component.ShadingSystemType, component.ShadingSystemSetpoint) == ("InteriorShade", 250.0)
    assert component.ShadingSystemTransmittance == 0.3
    assert component.ShadingSystemAvailabilitySchedule is not None
    back = windows.settings_to_umi(
        component,
        WindowConstruction(Name="W"),
        schedule=write_schedule,
        context=writing("perimeter.Envelope.WindowSettings"),
    )
    original = umi_settings()
    for field in (
        "name",
        "operable_area",
        "is_shading_system_on",
        "shading_system_type",
        "shading_system_setpoint",
        "shading_system_transmittance",
    ):
        assert getattr(back, field) == getattr(original, field), field


def test_interior_window_and_airflow_network_fields_stay_lost_with_up9() -> None:
    context = reading("/BuildingTemplates/0/Windows")
    windows.settings_to_sbem(
        umi_settings(IsZoneMixingOn=True, AfnDischargeC=0.5, Type=1), schedule=read_schedule, context=context
    )
    lost = {(loss.location.rsplit("/", 1)[1], loss.upstream, loss.rule) for loss in context.losses}
    assert lost == {
        ("IsZoneMixingOn", "UP-9", "window.settings"),
        ("AfnDischargeC", "UP-9", "window.settings"),
        ("Type", "UP-9", "window.settings"),
    }


def test_no_settings_write_operable_unshaded_windows() -> None:
    context = writing("perimeter.Envelope.WindowSettings")
    written = windows.settings_to_umi(None, WindowConstruction(Name="W"), schedule=write_schedule, context=context)
    assert (written.name, written.operable_area, written.is_shading_system_on) == ("W settings", 1.0, False)
    assert context.losses == []


def test_writing_uses_the_perimeter_settings_and_loses_another() -> None:
    context = reading("/BuildingTemplates/0/Windows")
    shaded = windows.settings_to_sbem(umi_settings(), schedule=read_schedule, context=context)
    group, chosen, losses = windows.template_settings({"core": None, "perimeter": shaded}, subject="A")
    assert (group, chosen) == ("perimeter", shaded)
    (loss,) = losses
    assert (loss.location, loss.rule, loss.replacement) == ("core.Envelope.WindowSettings", "window.settings", "Shaded")
