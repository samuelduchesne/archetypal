"""The private UMI format model `archetypal.umi._format` (spec 003, T011, research R1)."""

from __future__ import annotations

import inspect
import json
import re
from enum import Enum, IntEnum
from pathlib import Path

import pytest
from pydantic import ValidationError

import archetypal.umi
from archetypal.umi import _format

FIELDS_PATH = Path(__file__).parents[2] / "data" / "basilisk_fields.json"
BASILISK_FIELDS: dict[str, list[str]] = json.loads(FIELDS_PATH.read_text(encoding="utf-8"))

# data-model.md, "Private format model": one model per Basilisk Core class, plus UmiLibrary.
DATA_MODEL_CLASSES = [
    "GasMaterial",
    "GlazingMaterial",
    "OpaqueMaterial",
    "MaterialLayer",
    "OpaqueConstruction",
    "WindowConstruction",
    "StructureInformation",
    "MassRatios",
    "DaySchedule",
    "WeekSchedule",
    "YearSchedule",
    "YearSchedulePart",
    "DomesticHotWaterSettings",
    "ZoneVentilation",
    "ZoneConditioning",
    "ZoneConstructions",
    "ZoneLoads",
    "ZoneDefinition",
    "WindowSettings",
    "BuildingTemplate",
    "UmiLibrary",
]

SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


def model_for(basilisk_class: str) -> type[_format.FormatModel]:
    """The format model named after a Basilisk class (`Library` is `UmiLibrary`)."""
    name = "UmiLibrary" if basilisk_class == "Library" else basilisk_class
    model = getattr(_format, name)
    assert isinstance(model, type)
    assert issubclass(model, _format.FormatModel)
    return model


def aliases(model: type[_format.FormatModel]) -> set[str]:
    return {field.alias or name for name, field in model.model_fields.items()}


@pytest.mark.parametrize("name", DATA_MODEL_CLASSES)
def test_one_frozen_model_per_class(name: str) -> None:
    model = model_for(name)
    assert model.model_config.get("frozen") is True


def test_models_cannot_be_changed() -> None:
    loads = _format.ZoneLoads()
    with pytest.raises(ValidationError):
        loads.people_density = 1.0  # pyright: ignore[reportAttributeAccessIssue]


@pytest.mark.parametrize("basilisk_class", sorted(BASILISK_FIELDS))
def test_every_basilisk_key_has_a_model_field(basilisk_class: str) -> None:
    model = model_for(basilisk_class)
    missing = set(BASILISK_FIELDS[basilisk_class]) - aliases(model)
    assert not missing, f"{model.__name__} has no field for {sorted(missing)}"


@pytest.mark.parametrize("basilisk_class", sorted(BASILISK_FIELDS))
def test_fields_are_snake_case_with_basilisk_aliases(basilisk_class: str) -> None:
    model = model_for(basilisk_class)
    for name, field in model.model_fields.items():
        assert SNAKE_CASE.match(name), name
        assert field.alias is not None, name
        assert field.alias[0].isupper(), field.alias


def test_models_are_read_by_alias_and_by_name() -> None:
    by_alias = _format.ZoneLoads.model_validate({"LightingPowerDensity": 8.5})
    by_name = _format.ZoneLoads.model_validate({"lighting_power_density": 8.5})
    assert by_alias == by_name
    assert by_alias.lighting_power_density == 8.5


def test_unknown_keys_are_ignored() -> None:
    loads = _format.ZoneLoads.model_validate({"Life": 1, "PeopleDensity": 0.1})
    assert loads.people_density == 0.1


# (model, Basilisk key, Basilisk's effective default): its [DefaultValue], else its initialiser.
DEFAULTS: list[tuple[str, str, object]] = [
    ("BuildingTemplate", "DefaultWindowToWallRatio", 0.4),
    ("BuildingTemplate", "Version", "v1.0"),
    ("BuildingTemplate", "Lifespan", 0),
    ("BuildingTemplate", "YearFrom", None),
    ("BuildingTemplate", "Country", ()),
    ("BuildingTemplate", "Category", "Uncategorized"),
    ("BuildingTemplate", "Name", None),
    ("DaySchedule", "Type", "Fraction"),
    ("DaySchedule", "Category", "Day"),
    ("WeekSchedule", "Type", "Fraction"),
    ("WeekSchedule", "Category", "Week"),
    ("YearSchedule", "Category", "Year"),
    ("GasMaterial", "Category", "Gases"),
    ("GasMaterial", "Type", "AIR"),
    ("GlazingMaterial", "DirtFactor", 1.0),
    ("GlazingMaterial", "IRTransmittance", 0.0),
    ("GlazingMaterial", "SolarTransmittance", 0.837),
    ("GlazingMaterial", "SubstitutionRatePattern", (1.0,)),
    ("OpaqueMaterial", "Roughness", None),
    ("OpaqueMaterial", "DesignStrength", None),
    ("DomesticHotWaterSettings", "CoefficientOfPerformance", 0.85),
    ("DomesticHotWaterSettings", "FlowRatePerFloorArea", 0.03),
    ("DomesticHotWaterSettings", "FuelType", _format.DomesticHotWaterFuelType.NaturalGas),
    ("DomesticHotWaterSettings", "IsOn", True),
    ("DomesticHotWaterSettings", "WaterSupplyTemperature", 65.0),
    ("WindowSettings", "IsShadingSystemOn", True),  # [DefaultValue(true)] wins over the initialiser
    ("WindowSettings", "OperableArea", 0.8),
    ("WindowSettings", "ShadingSystemType", _format.ShadingType.ExteriorShade),
    ("WindowSettings", "Type", _format.WindowType.External),
    ("ZoneConditioning", "CoolingSetpoint", 26.0),
    ("ZoneConditioning", "HeatingSetpoint", 20.0),
    ("ZoneConditioning", "HeatingFuelType", _format.FuelType.NaturalGas),
    ("ZoneConditioning", "CoolingFuelType", _format.FuelType.Electricity),
    ("ZoneConditioning", "HeatRecoveryEfficiencySensible", 0.7),
    ("ZoneConditioning", "MinFreshAirPerArea", 0.001),
    ("ZoneConditioning", "HeatingCoeffOfPerf", 0.0),
    ("ZoneLoads", "LightingPowerDensity", 12.0),
    ("ZoneLoads", "IlluminanceTarget", 500.0),
    ("ZoneLoads", "PeopleDensity", 0.2),
    ("ZoneLoads", "DimmingType", _format.DimmingType.Continuous),
    ("ZoneVentilation", "Infiltration", 0.1),
    ("ZoneVentilation", "IsBuoyancyOn", True),
    ("ZoneVentilation", "IsWindOn", False),
    ("ZoneDefinition", "DaylightMeshResolution", 1.0),
    ("ZoneDefinition", "DaylightWorkplaneHeight", 0.8),
    ("ZoneDefinition", "InternalMassExposedPerFloorArea", 0.0),
    ("StructureInformation", "UseAdvancedModel", False),
    ("StructureInformation", "MassRatios", ()),
]


@pytest.mark.parametrize(("name", "key", "expected"), DEFAULTS)
def test_absent_key_takes_basilisk_default_and_is_recorded(name: str, key: str, expected: object) -> None:
    model = model_for(name)
    absent = model.model_validate({})
    field = next(n for n, f in model.model_fields.items() if f.alias == key)
    value = getattr(absent, field)
    assert value == expected
    assert type(value) is type(expected)
    assert key in absent.defaulted_keys


def test_present_key_is_not_defaulted() -> None:
    loads = _format.ZoneLoads.model_validate({"LightingPowerDensity": 12.0, "Name": None})
    assert "LightingPowerDensity" not in loads.defaulted_keys
    assert "Name" not in loads.defaulted_keys
    assert "PeopleDensity" in loads.defaulted_keys


def test_fixed_categories_ignore_the_file() -> None:
    # Basilisk's getter returns a constant and its setter ignores the file's value.
    assert _format.DaySchedule.model_validate({"Category": "Weekday"}).category == "Day"
    assert _format.GasMaterial.model_validate({"Category": "Gas"}).category == "Gases"


def test_advanced_structural_model_defaults() -> None:
    structure = _format.StructureInformation()
    model = structure.advanced_model
    assert model.column_wall_spacing.primary_span == 8.0
    assert model.foundation_soil_settings.foundation_soil_value == 72.0
    assert model.loading_settings.live_loading_preset is _format.LiveLoadingPreset.Offices
    assert (
        model.construction_systems.beams.construction_system_type is _format.ConstructionSystemTypeBeam.RectangularSolid
    )
    assert model.construction_systems.beams.material is None


ENUMS: list[tuple[type[IntEnum], list[str]]] = [
    (
        _format.FuelType,
        [
            "None_",
            "Electricity",
            "NaturalGas",
            "PropaneGas",
            "FuelOil1",
            "FuelOil2",
            "Diesel",
            "Gasoline",
            "Coal",
            "OtherFuel1",
            "OtherFuel2",
            "Steam",
            "DistrictHeating",
            "DistrictCooling",
        ],
    ),
    (_format.IdealSystemLimit, ["NoLimit", "LimitFlowRate", "LimitCapacity", "LimitFlowRateAndCapacity"]),
    (_format.EconomizerType, ["NoEconomizer", "DifferentialDryBulb", "DifferentialEnthalpy"]),
    (_format.HeatRecoveryType, ["None_", "Enthalpy", "Sensible"]),
    (_format.DimmingType, ["Continuous", "Off", "Stepped"]),
    (_format.ShadingType, ["ExteriorShade", "InteriorShade"]),
    (_format.WindowType, ["External", "Internal"]),
    (_format.DomesticHotWaterFuelType, ["Unset", "Electricity", "NaturalGas", "Oil"]),
]


@pytest.mark.parametrize(("enum", "names"), ENUMS, ids=[e.__name__ for e, _ in ENUMS])
def test_enums_are_int_enums_with_basilisk_values(enum: type[IntEnum], names: list[str]) -> None:
    assert issubclass(enum, IntEnum)
    assert [member.name for member in enum] == names
    assert [member.value for member in enum] == list(range(len(names)))


def test_fuel_type_spans_0_to_13() -> None:
    assert min(_format.FuelType) == 0
    assert max(_format.FuelType) == 13


def test_enums_read_from_integers_and_names() -> None:
    by_int = _format.ZoneConditioning.model_validate({"HeatingFuelType": 1, "EconomizerType": 2})
    by_name = _format.ZoneConditioning.model_validate({
        "HeatingFuelType": "Electricity",
        "EconomizerType": "differentialenthalpy",
    })
    assert by_int.heating_fuel_type is _format.FuelType.Electricity
    assert by_int.economizer_type is _format.EconomizerType.DifferentialEnthalpy
    assert by_name == by_int
    # Basilisk's `None` members: the integer and the C# name both read.
    assert _format.ZoneConditioning.model_validate({"HeatRecoveryType": "None"}).heat_recovery_type == 0


def test_structural_enums_are_written_by_name() -> None:
    for enum in (
        _format.ConstructionSystemTypeBeam,
        _format.ConstructionSystemTypeColumn,
        _format.ConstructionSystemTypeFloor,
        _format.ConstructionSystemTypeFoundation,
        _format.ConstructionSystemTypeLateralSystem,
        _format.FoundationSoilPreset,
        _format.LiveLoadingPreset,
    ):
        assert issubclass(enum, Enum)
        assert all(member.value == member.name for member in enum)


def test_library_collections_in_basilisk_order() -> None:
    assert [f.alias for f in _format.UmiLibrary.model_fields.values()] == BASILISK_FIELDS["Library"]
    assert _format.UmiLibrary().zones == ()


def test_basilisk_key_order_is_derived_class_first() -> None:
    # Newtonsoft writes the members of the most derived class first (as in B2).
    keys = [alias for _, alias in _format.GasMaterial.basilisk_keys()]
    assert keys[:2] == ["Category", "Type"]
    assert keys[-3:] == ["Comments", "DataSource", "Name"]
    assert keys.count("Category") == 1


def test_nothing_from_format_is_exported() -> None:
    assert _format.__all__ == []
    public = set(getattr(archetypal.umi, "__all__", ()))
    exported = {name for name in dir(archetypal.umi) if not name.startswith("_")}
    format_names = {name for name, value in vars(_format).items() if inspect.isclass(value)}
    assert not (public | exported) & format_names


def test_format_model_is_independent_of_epinterface() -> None:
    source = Path(inspect.getfile(_format)).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+epinterface", source, flags=re.MULTILINE)
    assert "roadmap C-02" in (_format.__doc__ or "")
