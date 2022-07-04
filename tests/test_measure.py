"""Test measures module."""
import pytest

from archetypal.template.measures.measure import (
    EnergyStarUpgrade,
    FacadeUpgradeBest,
    FacadeUpgradeLow,
    FacadeUpgradeMid,
    FacadeUpgradeRegular,
    InfiltrationMedium,
    InfiltrationRegular,
    InfiltrationTight,
    Measure,
    SetFacadeConstructionThermalResistanceToEnergyStar,
)


@pytest.fixture(scope="function")
def umi_library():
    """Yield an umi library for tests."""
    from archetypal import UmiTemplateLibrary

    umi = UmiTemplateLibrary.open(
        "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"
    )
    yield umi


class TestMeasure:
    """Test Measures on UmiTemplateLibraries."""

    def test_apply_measure_to_single_building_template(self, umi_library):
        """Test applying measure only to a specific building template."""
        building_template = umi_library.BuildingTemplates[0]

        assert umi_library.BuildingTemplates[0].Core.Loads.LightingPowerDensity == 12.0

        EnergyStarUpgrade().apply_measure_to_template(building_template)

        assert umi_library.BuildingTemplates[0].Core.Loads.LightingPowerDensity == 8.07
        assert umi_library.BuildingTemplates[1].Core.Loads.LightingPowerDensity == 16.0

    def test_apply_measure_to_whole_library(self, umi_library):
        """Test applying measure to whole template library."""
        assert umi_library.BuildingTemplates[0].Core.Loads.LightingPowerDensity == 12.0

        # apply the measure
        EnergyStarUpgrade().apply_measure_to_whole_library(umi_library)

        # Assert the value has changed for all ZoneLoads objects.
        for zone_loads in umi_library.ZoneLoads:
            assert zone_loads.LightingPowerDensity == 8.07

        oc = umi_library.BuildingTemplates[3].Perimeter.Constructions.Facade
        previous_thickness = oc.total_thickness
        previous_r_value = oc.r_value

        measure = SetFacadeConstructionThermalResistanceToEnergyStar(
            rsi_value_facade=3.08, rsi_value_roof=7.2
        )
        measure.apply_measure_to_whole_library(umi_library)

        # assert that the total wall r_value has increased.
        assert oc.r_value > previous_r_value

        # assert that the total wall thickness has increased since setting the
        # r-value increases the thickness of the material.
        assert oc.total_thickness > previous_thickness

    @pytest.mark.parametrize(
        "measure",
        [
            FacadeUpgradeBest(),
            FacadeUpgradeMid(),
            FacadeUpgradeRegular(),
            FacadeUpgradeLow(),
        ],
    )
    def test_facade_upgrade(self, measure, umi_library):
        """Test series of facade upgrades using parametrization."""
        # apply the measure
        facade = umi_library.BuildingTemplates[3].Perimeter.Constructions.Facade
        i = facade.infer_insulation_layer()
        oc = facade.Layers[i]

        measure.apply_measure_to_whole_library(umi_library)

        # assert that the total wall r_value has increased.
        assert oc.r_value == pytest.approx(measure.rsi_value_facade)

    @pytest.mark.parametrize(
        "measure, infiltration_ach",
        [
            (InfiltrationRegular(), 0.6),
            (InfiltrationMedium(), 0.3),
            (InfiltrationTight(), 0.1),
        ],
    )
    def test_infiltration_upgrade(self, measure, infiltration_ach, umi_library):
        """Test applying the infiltration measures."""
        measure.apply_measure_to_whole_library(umi_library)

        for bldg in umi_library.BuildingTemplates:
            assert bldg.Perimeter.Ventilation.Infiltration == infiltration_ach

    @pytest.mark.parametrize(
        "modifier_name, modifier_prop, default, object_address, object_parameter, getExpectedValue",
        [
            (
                "SetPerimeterCoolingSetpoint",
                "cooling_setpoint",
                27,
                ["Perimeter", "Conditioning"],
                "CoolingSetpoint",
                # Explicitly tell the test where to find the correct val
                lambda bt: bt.Perimeter.Conditioning.CoolingSetpoint,
            ),
            (
                "SetCoreHeatingSetpoint",
                "heating_setpoint",
                20,
                ["Core", "Conditioning"],
                "HeatingSetpoint",
                lambda bt: bt.Core.Conditioning.HeatingSetpoint,
            ),
        ],
    )
    def test_create_basic_measure(
        self,
        modifier_name,
        modifier_prop,
        default,
        object_address,
        object_parameter,
        umi_library,
        getExpectedValue,
    ):
        """Test building custom measures with the add_modifier method"""

        # Define a custom measure
        class MyMeasure(Measure):
            name = "MyMeasure"
            description = "Test Measure"

            def __init__(self):
                """Initialize measure with parameters."""
                super(MyMeasure, self).__init__()

                self.add_modifier(
                    modifier_name=modifier_name,
                    modifier_prop=modifier_prop,
                    default=default,
                    object_address=object_address,
                    object_parameter=object_parameter,
                )

        # create the measure
        measure = MyMeasure()

        # Check that the getters are working
        expectedProps = {}
        expectedProps[modifier_prop] = default
        assert measure.props == expectedProps
        assert measure._props == {modifier_prop}
        assert measure._actions == {modifier_name}

        # Test the measure application works
        measure.apply_measure_to_whole_library(umi_library)

        for bldg in umi_library.BuildingTemplates:
            assert getExpectedValue(bldg) == default

    def test_validated_measure(self, umi_library):
        """Test validated measures"""
        measure = Measure()
        measure.name = "Cooling Setpoints"
        measure.description = (
            "Set Cooling setpoints conditionally (only if they improve)"
        )

        print("here testing")

        def gtValidator(original_value, new_value, root):
            print(f"validating {root.Name}")
            print(f"Original Value: { original_value }")
            print(f"New Value: { new_value }")
            return new_value > original_value

        # Only adjust cooling cop if the new value is greater
        measure.add_modifier(
            modifier_name="SetPerimCoolingCoP",
            modifier_prop="cooling_CoP",
            default=0.01,
            object_address=["Perimeter", "Conditioning"],
            object_parameter="CoolingCoeffOfPerf",
            validator=gtValidator,
        )
        measure.add_modifier(
            modifier_name="SetCoreCoolingCoP",
            modifier_prop="cooling_cop",
            default=0.01,
            object_address=["Core", "Conditioning"],
            object_parameter="CoolingCoeffOfPerf",
            validator=gtValidator,
        )

        # Get the original value for each template and make sure it doesn't change
        # since 0.01 is worse than all of the existing values
        for bt in umi_library.BuildingTemplates:
            original_perim_cool_cop = bt.Perimeter.Conditioning.CoolingCoeffOfPerf
            original_core_cool_cop = bt.Core.Conditioning.CoolingCoeffOfPerf
            measure.apply_measure_to_template(bt)
            assert (
                original_perim_cool_cop == bt.Perimeter.Conditioning.CoolingCoeffOfPerf
            )
            assert original_core_cool_cop == bt.Core.Conditioning.CoolingCoeffOfPerf

        # update the measure
        measure.cooling_cop = 6

        # Test that all values now update
        measure.apply_measure_to_whole_library(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 6
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 6
