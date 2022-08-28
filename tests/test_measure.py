"""Test measures module."""
import pytest

from archetypal.template.measures.measure import (
    Measure,
    MeasureAction,
    MeasureProperty,
    SetCOP,
    SetElectricLoadsEfficiency,
    SetFacadeInsulationThermalResistance,
    SetFacadeThermalResistance,
    SetInfiltration,
    SetMechanicalVentilation,
)


@pytest.fixture(scope="function")
def umi_library():
    """Yield an umi library for tests."""
    from archetypal import UmiTemplateLibrary

    umi = UmiTemplateLibrary.open(
        "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"
    )
    yield umi


@pytest.fixture(scope="function")
def building_templates(umi_library):
    """Yield building templates."""
    a = umi_library.BuildingTemplates[0]
    b = umi_library.BuildingTemplates[1]
    c = umi_library.BuildingTemplates[2]
    d = umi_library.BuildingTemplates[3]

    yield a, b, c, d


class TestMeasure:
    def test_create_measure(self, umi_library):
        equipment_default = 4
        lighting_default = 5
        equipment_alt = 2
        lighting_alt = 3
        # Create Actions
        prerimeter_equipment_action = MeasureAction(
            Name="Change Perimeter Equipment Power Density",
            Lookup=["Perimeter", "Loads", "EquipmentPowerDensity"],
        )
        core_equipment_action = MeasureAction(
            Name="Change Core Equipment Power Density",
            Lookup=["Core", "Loads", "EquipmentPowerDensity"],
        )
        prerimeter_lighting_action = MeasureAction(
            Name="Change Perimeter Lighting Power Density",
            Lookup=["Perimeter", "Loads", "LightingPowerDensity"],
        )
        core_lighting_action = MeasureAction(
            Name="Change Core Lighting Power Density",
            Lookup=["Core", "Loads", "LightingPowerDensity"],
        )
        # Create Props
        equipment_prop = MeasureProperty(
            Name="Equipment Power Density",
            AttrName="EquipmentPowerDensity",
            Description="Change Equipment Power Density",
            Default=equipment_default,
            Actions=[prerimeter_equipment_action, core_equipment_action],
        )
        lighting_prop = MeasureProperty(
            Name="Lighting Power Density",
            AttrName="LightingPowerDensity",
            Description="Change Lighting Power Density",
            Default=lighting_default,
            Actions=[prerimeter_lighting_action, core_lighting_action],
        )
        # Create measure
        loads_measure = Measure(
            Name="EnergyStar",
            Description="Change Loads Efficiency",
            Properties=[equipment_prop, lighting_prop],
        )

        """Test that getattr and getitem are working"""
        assert loads_measure["Equipment Power Density"] == equipment_default
        assert loads_measure["Lighting Power Density"] == lighting_default
        assert loads_measure.EquipmentPowerDensity == equipment_default
        assert loads_measure.LightingPowerDensity == lighting_default

        """Test that setattr is working"""
        loads_measure.EquipmentPowerDensity = equipment_alt
        loads_measure.LightingPowerDensity = lighting_alt
        assert loads_measure["Equipment Power Density"] == equipment_alt
        assert loads_measure["Lighting Power Density"] == lighting_alt
        assert loads_measure.EquipmentPowerDensity == equipment_alt
        assert loads_measure.LightingPowerDensity == lighting_alt

        """Test that setitem is working"""
        loads_measure["Equipment Power Density"] = equipment_default
        loads_measure["Lighting Power Density"] = lighting_default
        assert loads_measure["Equipment Power Density"] == equipment_default
        assert loads_measure["Lighting Power Density"] == lighting_default
        assert loads_measure.EquipmentPowerDensity == equipment_default
        assert loads_measure.LightingPowerDensity == lighting_default

        """Test that we correctly identify objects to mutate"""
        bt = umi_library.BuildingTemplates[0]
        loads = bt.Perimeter.Loads
        assert loads == bt.Core.Loads and loads.id == bt.Core.Loads.id
        objects_to_mutate = loads_measure.lookup_objects_to_mutate(bt)
        assert len(objects_to_mutate) == 1
        assert len(objects_to_mutate[loads]) == 4

        """Test that library mutation works"""
        loads_measure.EquipmentPowerDensity = equipment_alt
        loads_measure.LightingPowerDensity = lighting_alt
        loads_measure.mutate(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Loads.EquipmentPowerDensity == equipment_alt
            assert bt.Perimeter.Loads.EquipmentPowerDensity == equipment_alt
            assert bt.Perimeter.Loads.LightingPowerDensity == lighting_alt
            assert bt.Core.Loads.LightingPowerDensity == lighting_alt

    def test_changelog(self, umi_library):
        measure = SetInfiltration.Tight() + SetElectricLoadsEfficiency()
        original_values = []
        for bt in umi_library.BuildingTemplates:
            original_values.append(
                {
                    "Infiltration": bt.Perimeter.Ventilation.Infiltration,
                    "PerimeterEPD": bt.Perimeter.Loads.EquipmentPowerDensity,
                    "CoreEPD": bt.Core.Loads.EquipmentPowerDensity,
                    "PerimeterLPD": bt.Perimeter.Loads.LightingPowerDensity,
                    "CoreLPD": bt.Core.Loads.LightingPowerDensity,
                }
            )
        changelog = measure.changelog(umi_library)
        assert len(changelog) == len(umi_library.BuildingTemplates)
        for original_value, bt in zip(original_values, umi_library.BuildingTemplates):
            assert (
                original_value["Infiltration"] == bt.Perimeter.Ventilation.Infiltration
            )
            assert (
                original_value["PerimeterEPD"]
                == bt.Perimeter.Loads.EquipmentPowerDensity
            )
            assert original_value["CoreEPD"] == bt.Core.Loads.EquipmentPowerDensity
            assert (
                original_value["PerimeterLPD"]
                == bt.Perimeter.Loads.LightingPowerDensity
            )
            assert original_value["CoreLPD"] == bt.Core.Loads.LightingPowerDensity
            assert len(changelog[bt]) == 5
            for change in changelog[bt]:
                assert change in [
                    (
                        ["Perimeter", "Ventilation", "Infiltration"],
                        original_value["Infiltration"],
                        measure.Infiltration,
                    ),
                    (
                        ["Core", "Loads", "EquipmentPowerDensity"],
                        original_value["CoreEPD"],
                        measure.EquipmentPowerDensity,
                    ),
                    (
                        ["Perimeter", "Loads", "EquipmentPowerDensity"],
                        original_value["PerimeterEPD"],
                        measure.EquipmentPowerDensity,
                    ),
                    (
                        ["Core", "Loads", "LightingPowerDensity"],
                        original_value["CoreLPD"],
                        measure.LightingPowerDensity,
                    ),
                    (
                        ["Perimeter", "Loads", "LightingPowerDensity"],
                        original_value["PerimeterLPD"],
                        measure.LightingPowerDensity,
                    ),
                ]

    def test_create_measure_with_shortcut(self, umi_library):
        """Test creating a measure and property with the action creator shortcut via Lookup"""
        prop = MeasureProperty(
            Name="Ventilation ACH",
            AttrName="VentilationACH",
            Description="Cange Ventilation ACH",
            Default=1.2,
            Lookup=["Perimeter", "Ventilation", "ScheduledVentilationAch"],
        )
        measure = Measure(
            Name="Ventilation", Description="Change Ventilation", Properties=prop
        )

        measure.mutate_library(umi_library)

        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Ventilation.ScheduledVentilationAch == 1.2

    def test_add_and_iadd_measures(self, umi_library):
        measure_a = SetCOP(HeatingCoP=4, CoolingCoP=4)
        measure_b = SetInfiltration(Infiltration=0.1)
        measure_c = measure_a + measure_b
        measure_c.mutate(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Conditioning.HeatingCoeffOfPerf == 4
            assert bt.Perimeter.Conditioning.HeatingCoeffOfPerf == 4
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 4
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 4
            assert bt.Perimeter.Ventilation.Infiltration == 0.1

        measure_a += measure_b
        measure_a.HeatingCoP = 5
        measure_a.CoolingCoP = 5
        measure_a.Infiltration = 0.05
        measure_a.mutate(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Conditioning.HeatingCoeffOfPerf == 5
            assert bt.Perimeter.Conditioning.HeatingCoeffOfPerf == 5
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 5
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 5
            assert bt.Perimeter.Ventilation.Infiltration == 0.05

    def test_mutate_single_building_template(self, building_templates):
        """Test applying measure only to a specific building template."""
        a, b, c, d = building_templates

        assert a.Core.Loads.LightingPowerDensity == 12.0

        SetElectricLoadsEfficiency().mutate(a)

        """ Make sure template mutated"""
        assert a.Core.Loads.LightingPowerDensity == 8.07
        assert a.Perimeter.Loads.LightingPowerDensity == 8.07
        assert a.Core.Loads.EquipmentPowerDensity == 8.07
        assert a.Perimeter.Loads.EquipmentPowerDensity == 8.07

        """ Verify that the other templates did not mutate"""
        assert b.Core.Loads.LightingPowerDensity == 16.0
        assert b.Perimeter.Loads.LightingPowerDensity == 16.0

    def test_apply_measure_to_whole_library(self, umi_library):
        """Test applying measure to whole template library."""
        assert umi_library.BuildingTemplates[0].Core.Loads.LightingPowerDensity == 12.0

        # apply the measure
        SetElectricLoadsEfficiency().mutate(umi_library)

        # Assert the value has changed for all ZoneLoads objects.
        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Loads.LightingPowerDensity == 8.07
            assert bt.Perimeter.Loads.LightingPowerDensity == 8.07
            assert bt.Core.Loads.EquipmentPowerDensity == 8.07
            assert bt.Perimeter.Loads.EquipmentPowerDensity == 8.07

        oc = umi_library.BuildingTemplates[3].Perimeter.Constructions.Facade
        previous_thickness = oc.total_thickness
        previous_r_value = oc.r_value

        measure = SetFacadeThermalResistance(FacadeRValue=3.08, RoofRValue=7.2)
        measure.mutate(umi_library)

        # assert that the total wall r_value has increased.
        assert oc.r_value > previous_r_value

        # assert that the total wall thickness has increased since setting the
        # r-value increases the thickness of the material.
        assert oc.total_thickness > previous_thickness

    @pytest.mark.parametrize(
        "measure",
        [
            SetFacadeThermalResistance.Best(),
            SetFacadeThermalResistance.Mid(),
            SetFacadeThermalResistance.Regular(),
            SetFacadeThermalResistance.Low(),
        ],
    )
    def test_facade_upgrade(self, measure, umi_library):
        """Test series of facade upgrades using parametrization."""
        # apply the measure
        facade = umi_library.BuildingTemplates[3].Perimeter.Constructions.Facade

        measure.mutate(umi_library)

        # assert that the total wall r_value has changed.
        for bt in umi_library.BuildingTemplates:
            facade = bt.Perimeter.Constructions.Facade
            assert facade.r_value == pytest.approx(measure.FacadeRValue)

    @pytest.mark.parametrize(
        "measure",
        [
            SetFacadeInsulationThermalResistance.Best(),
            SetFacadeInsulationThermalResistance.Mid(),
            SetFacadeInsulationThermalResistance.Regular(),
            SetFacadeInsulationThermalResistance.Low(),
        ],
    )
    def test_facade_insulation_upgrade(self, measure, umi_library):
        """Test series of facade upgrades using parametrization."""
        insulation_indices = [
            bt.Perimeter.Constructions.Facade.infer_insulation_layer()
            for bt in umi_library.BuildingTemplates
        ]

        measure.mutate(umi_library)

        # assert that the total wall r_value has increased.
        for i, bt in zip(insulation_indices, umi_library.BuildingTemplates):
            facade = bt.Perimeter.Constructions.Facade
            oc = facade.Layers[insulation_indices[i]]
            assert oc.r_value == pytest.approx(measure.FacadeRValue)

    @pytest.mark.parametrize(
        "measure, infiltration_ach",
        [
            (SetInfiltration.Regular(), 0.6),
            (SetInfiltration.Medium(), 0.3),
            (SetInfiltration.Tight(), 0.1),
        ],
    )
    def test_infiltration_upgrade(self, measure, infiltration_ach, umi_library):
        """Test applying the infiltration measures."""
        measure.mutate(umi_library)

        for bldg in umi_library.BuildingTemplates:
            assert bldg.Perimeter.Ventilation.Infiltration == infiltration_ach

    @pytest.mark.parametrize(
        "prop_description, prop_name, prop_attr, default, action_name, object_address, get_expected_value",
        [
            (
                "Set Cooling Setpoint",
                "Cooling Setpoint",
                "CoolingSetpoint",
                27,
                "Change Perimeter Cooling Setpoint",
                ["Perimeter", "Conditioning", "CoolingSetpoint"],
                # Explicitly tell the test where to find the correct val
                lambda bt: bt.Perimeter.Conditioning.CoolingSetpoint,
            ),
            (
                "Set Heating Setpoint",
                "Heating Setpoint",
                "HeatingSetpoint",
                20,
                "Change Core Heating Setpoint",
                ["Core", "Conditioning", "HeatingSetpoint"],
                lambda bt: bt.Core.Conditioning.HeatingSetpoint,
            ),
        ],
    )
    def test_create_basic_class(
        self,
        prop_description,
        prop_name,
        prop_attr,
        default,
        action_name,
        object_address,
        get_expected_value,
        umi_library,
    ):
        """Test building custom measures with the add_modifier method"""

        # Define a custom measure
        class MyMeasure(Measure):
            def __init__(self, **kwargs):
                """Initialize measure with parameters."""
                super(MyMeasure, self).__init__(**kwargs)
                prop = MeasureProperty(
                    Name=prop_name,
                    AttrName=prop_attr,
                    Description=prop_description,
                    Default=default,
                )
                prop.add_action(
                    MeasureAction(
                        Name=action_name,
                        Lookup=object_address,
                    )
                )
                self.add_property(prop)

        # create the measure
        measure = MyMeasure()

        # Test the measure application works
        measure.mutate(umi_library)

        for bldg in umi_library.BuildingTemplates:
            assert get_expected_value(bldg) == default

    def test_validated_measure(self, umi_library):
        """Test validated measures"""
        measure = Measure()
        measure.Name = "Cooling Efficiency"
        measure.Description = (
            "Change cooling coefficient of performance in core and perimeter"
        )

        def gtValidator(original_value, new_value, building_template):
            return new_value > original_value

        action = MeasureAction(
            Name="Change Perimeter CoP",
            Lookup=["Perimeter", "Conditioning", "CoolingCoeffOfPerf"],
        )
        """Tests that the validator gets added to an action added to a prop before when the prop is initted or after"""

        # Only adjust cooling cop if the new value is greater
        prop = MeasureProperty(
            Name="Cooling CoP",
            AttrName="CoolingCoP",
            Description="Set cooling CoP conditionally",
            Default=0.01,
            Validator=gtValidator,
            Actions=action,
        )

        measure.add_property(prop)

        prop.add_action(
            MeasureAction(
                Name="Change Core CoP",
                Lookup=["Core", "Conditioning", "CoolingCoeffOfPerf"],
                Validator=gtValidator,
            )
        )

        # Get the original value for each template and make sure it doesn't change
        # since 0.01 is worse than all of the existing values
        for bt in umi_library.BuildingTemplates:
            original_perim_cool_cop = bt.Perimeter.Conditioning.CoolingCoeffOfPerf
            original_core_cool_cop = bt.Core.Conditioning.CoolingCoeffOfPerf
            measure.mutate(bt)
            assert (
                original_perim_cool_cop == bt.Perimeter.Conditioning.CoolingCoeffOfPerf
            )
            assert original_core_cool_cop == bt.Core.Conditioning.CoolingCoeffOfPerf

        # update the measure
        measure.CoolingCoP = 6

        # Test that all values now update
        measure.mutate(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 6
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 6

        measure["Cooling CoP"] = 4

        # Test that all values did not update
        measure.mutate(umi_library)
        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 6
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 6

        """ Test that using the Validator setter works"""

        def difference_validator(original_value, new_value, **kwargs):
            return new_value - original_value > 2

        prop.Validator = difference_validator
        measure.CoolingCoP = 8
        measure.mutate(umi_library)

        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 6
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 6

        def difference_validator(original_value, new_value, **kwargs):
            return new_value - original_value > 1

        prop.Validator = difference_validator
        measure.mutate(umi_library)

        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 8
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 8

    def test_create_percentage_class(self, umi_library):
        measure = Measure(
            Name="Relative Equipment Efficiency",
            Description="Proportionally improve equipment efficiency",
        )

        def percent_decrease(original_value, proposed_transformer_value, **kwargs):
            """Decrease by the transformer argument interpreted as a percentage"""
            fraction = (100 - proposed_transformer_value) / 100
            return original_value * fraction

        def percent_increase(original_value, proposed_transformer_value, **kwargs):
            """Decrease by the transformer argument interpreted as a percentage"""
            fraction = (100 + proposed_transformer_value) / 100
            return original_value * fraction

        """ Test that the transformer works when action is added to prop during init or after, but not if action already had transformer"""
        core_epd_action = MeasureAction(
            Name="Change Core Equipment Power Density",
            Lookup=["Core", "Loads", "EquipmentPowerDensity"],
        )
        core_lpd_action = MeasureAction(
            Name="Change Core Equipment Power Density",
            Lookup=["Core", "Loads", "LightingPowerDensity"],
            Transformer=percent_increase,
        )
        prop = MeasureProperty(
            Name="Equipment Power Density Percentage",
            AttrName="EquipmentPowerDensityPercentage",
            Description="Equipment Power Density percent improvement",
            Default=5,
            Transformer=percent_decrease,
            Actions=[core_epd_action, core_lpd_action],
        )

        prop.add_action(
            MeasureAction(
                Name="Change Equipment Power Density",
                Lookup=["Perimeter", "Loads", "EquipmentPowerDensity"],
            )
        )

        measure.add_property(prop)

        original_epd_peri_values = []
        original_epd_core_values = []
        original_lpd_core_values = []
        for bt in umi_library.BuildingTemplates:
            original_epd_peri_values.append(bt.Perimeter.Loads.EquipmentPowerDensity)
            original_epd_core_values.append(bt.Core.Loads.EquipmentPowerDensity)
            original_lpd_core_values.append(bt.Core.Loads.LightingPowerDensity)

        measure.mutate(umi_library)

        for original_value, bt in zip(
            original_lpd_core_values, umi_library.BuildingTemplates
        ):
            assert bt.Core.Loads.LightingPowerDensity == pytest.approx(
                1.05 * original_value
            )
        for original_value, bt in zip(
            original_epd_peri_values, umi_library.BuildingTemplates
        ):
            assert bt.Perimeter.Loads.EquipmentPowerDensity == pytest.approx(
                0.95 * original_value
            )
        for original_value, bt in zip(
            original_epd_core_values, umi_library.BuildingTemplates
        ):
            assert bt.Core.Loads.EquipmentPowerDensity == pytest.approx(
                0.95 * original_value
            )

        """Test that using the Transformer setter overwrites all transformers for the prop"""
        prop.Transformer = percent_decrease

        original_epd_peri_values = []
        original_epd_core_values = []
        original_lpd_core_values = []
        for bt in umi_library.BuildingTemplates:
            original_epd_peri_values.append(bt.Perimeter.Loads.EquipmentPowerDensity)
            original_epd_core_values.append(bt.Core.Loads.EquipmentPowerDensity)
            original_lpd_core_values.append(bt.Core.Loads.LightingPowerDensity)

        measure.mutate(umi_library)

        for original_value, bt in zip(
            original_epd_peri_values, umi_library.BuildingTemplates
        ):
            assert bt.Perimeter.Loads.EquipmentPowerDensity == pytest.approx(
                0.95 * original_value
            )
        for original_value, bt in zip(
            original_epd_core_values, umi_library.BuildingTemplates
        ):
            assert bt.Core.Loads.EquipmentPowerDensity == pytest.approx(
                0.95 * original_value
            )
        for original_value, bt in zip(
            original_lpd_core_values, umi_library.BuildingTemplates
        ):
            assert bt.Core.Loads.LightingPowerDensity == pytest.approx(
                0.95 * original_value
            )

    def test_contextual_callbacks_with_kwargs(self, umi_library):
        """Test transformers and validators which use building template context and args/kwargs"""

        def validate_lower_than_lpd_by_factor(
            building_template, new_value, factor, zone, **kwargs
        ):
            perimeter_lpd = building_template[zone].Loads.LightingPowerDensity
            return new_value < (perimeter_lpd / factor)

        def lookup_object(change_zone, **kwargs):
            return [change_zone, "Loads", "EquipmentPowerDensity"]

        def subtract(proposed_transformer_value, difference, **kwargs):
            return proposed_transformer_value - difference

        measure = Measure()
        prop = MeasureProperty(
            Name="EPD",
            AttrName="EPD",
            Description="Change EPD conditionally",
            Default=1,
            Validator=validate_lower_than_lpd_by_factor,
            Transformer=subtract,
        )
        prop.add_action(
            MeasureAction(
                Name="Change EPD conditionally",
                Lookup=lookup_object,
            )
        )
        measure.add_property(prop)
        original_values = []
        for bt in umi_library.BuildingTemplates:
            original_values.append(bt.Core.Loads.EquipmentPowerDensity)

        # No templates should mutate since we are checking for
        # being less than perimeter lpd by a factor of 20
        measure.mutate(
            umi_library, factor=20, zone="Perimeter", change_zone="Core", difference=0.2
        )
        for original_value, bt in zip(original_values, umi_library.BuildingTemplates):
            assert bt.Core.Loads.EquipmentPowerDensity == original_value

        # Change the runtime argument to a less strict validator
        measure.mutate(
            umi_library, factor=2, zone="Perimeter", change_zone="Core", difference=0.3
        )
        for original_value, bt in zip(original_values, umi_library.BuildingTemplates):
            assert bt.Core.Loads.EquipmentPowerDensity == 0.7

    def test_callback_signatures(self, umi_library):
        prop = MeasureProperty(
            Name="Test Prop", AttrName="TestProp", Description="Test prop", Default=1
        )
        fn = lambda building_template: ["Perimeter"]

        with pytest.raises(
            AssertionError,
            match=".*building_template.*original_value.*proposed_transformer_value.*",
        ):
            prop.Transformer = fn
        with pytest.raises(
            AssertionError, match=".*building_template.*original_value.*new_value*"
        ):
            prop.Validator = fn

        action = MeasureAction(Name="Test Action", Lookup=fn)
        with pytest.raises(
            AssertionError,
            match=".*building_template.*original_value.*proposed_transformer_value.*",
        ):
            action.Transformer = fn
        with pytest.raises(
            AssertionError, match=".*building_template.*original_value.*new_value*"
        ):
            action.Validator = fn

        with pytest.raises(AssertionError, match=".*building_template.*"):
            action.Lookup = lambda x: ["Perimeter"]

        action.Lookup = lambda zone, **kwargs: [zone, "Loads", "LightingPowerDensity"]
        prop.add_action(action)
        measure = Measure(
            Name="Test measure", Description="Test measure", Properties=[prop]
        )
        measure.mutate(umi_library, zone="Perimeter")
        for bt in umi_library.BuildingTemplates:
            assert bt.Perimeter.Loads.LightingPowerDensity == 1
            assert bt.Core.Loads.LightingPowerDensity != 1
        measure.mutate(umi_library, zone="Core")
        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Loads.LightingPowerDensity == 1

    def test_disentanglement(self, building_templates):
        _, _, c, d = building_templates
        c_peri_loads = c.Perimeter.Loads
        c_core_loads = c.Core.Loads
        d_peri_loads = d.Perimeter.Loads
        d_core_loads = d.Core.Loads

        """ Confirm that all of the objects are the same"""
        loads = set((c_peri_loads, d_peri_loads, c_core_loads, d_core_loads))
        assert len(loads) == 1

        measure = Measure()
        prop = MeasureProperty(
            Name="EPD", AttrName="EPD", Description="Change EPD", Default=3
        )
        prop.add_action(
            MeasureAction(
                Name="change epd",
                Lookup=["Perimeter", "Loads", "EquipmentPowerDensity"],
            )
        )
        measure.add_property(prop)

        # Since both templates use the same Zone Definition for peri and core,
        # Changing the EPD in one template's perimeter will affect both peris and both cores
        measure.mutate(c, disentangle=False)

        c_peri_loads = c.Perimeter.Loads
        c_core_loads = c.Core.Loads
        d_peri_loads = d.Perimeter.Loads
        d_core_loads = d.Core.Loads
        loads = loads.union((c_peri_loads, d_peri_loads, c_core_loads, d_core_loads))
        assert len(loads) == 1
        assert d.Perimeter.Loads.EquipmentPowerDensity == measure.EPD
        assert d.Core.Loads.EquipmentPowerDensity == measure.EPD
        assert c.Perimeter.Loads.EquipmentPowerDensity == measure.EPD
        assert c.Core.Loads.EquipmentPowerDensity == measure.EPD

        measure.EPD = 2

        measure.mutate(c, disentangle=True)  # Also true if omitted

        """Check that the C Perimeter is now different but others still the same"""
        c_peri_loads = c.Perimeter.Loads
        c_core_loads = c.Core.Loads
        d_peri_loads = d.Perimeter.Loads
        d_core_loads = d.Core.Loads
        loads = loads.union((c_peri_loads, d_peri_loads, c_core_loads, d_core_loads))
        assert len(loads) == 2
        assert c_peri_loads.EquipmentPowerDensity == 2
        assert c_core_loads.EquipmentPowerDensity == 3
        assert d_peri_loads.EquipmentPowerDensity == 3
        assert d_core_loads.EquipmentPowerDensity == 3

    def test_class_inheritance(self, umi_library):
        class GSHPandVent(SetCOP, SetMechanicalVentilation):
            HeatingCoP = 4
            CoolingCoP = 3
            VentilationACH = 1.33
            VentilationSchedule = umi_library.YearSchedules[0]

        measure = GSHPandVent()

        measure.mutate(umi_library)

        for bt in umi_library.BuildingTemplates:
            assert bt.Core.Conditioning.CoolingCoeffOfPerf == 3
            assert bt.Perimeter.Conditioning.CoolingCoeffOfPerf == 3
            assert bt.Core.Conditioning.HeatingCoeffOfPerf == 4
            assert bt.Perimeter.Conditioning.HeatingCoeffOfPerf == 4
            assert bt.Perimeter.Ventilation.ScheduledVentilationAch == 1.33
            assert (
                bt.Perimeter.Ventilation.ScheduledVentilationSchedule
                == umi_library.YearSchedules[0]
            )
            assert bt.Core.Ventilation.ScheduledVentilationAch == 1.33
            assert (
                bt.Core.Ventilation.ScheduledVentilationSchedule
                == umi_library.YearSchedules[0]
            )

    def test_getters_and_setters_and_equality(self, building_templates):
        a, _, _, _ = building_templates
        measure = Measure(Name="A Measure", Description="This is the measure")
        assert measure.Name == "A Measure"
        assert measure.Description == "This is the measure"

        prop_a = MeasureProperty(
            Name="A Property",
            AttrName="Prop",
            Description="This is the property",
            Default=2,
        )
        prop_b = MeasureProperty(
            Name="A Property",
            AttrName="Prop",
            Description="This is the property",
            Default=3,
            Validator=lambda x, **kwargs: x,
        )

        assert prop_a.Name == "A Property"
        assert prop_a.Description == "This is the property"
        assert prop_a.Default == 2
        assert prop_a.Validator == None
        assert prop_a.Transformer == None
        assert prop_a == prop_b
        measure.add_property(prop_a)
        pytest.raises(AssertionError, match="Measure.*already.*property.*Name")
        prop_b.Validator = None
        assert prop_b.Validator == None
        prop_b.Default = 2
        assert prop_b.Default == 2

        action_a = MeasureAction(
            Name="An action", Lookup=["Perimeter", "Conditioning", "HeatingCoeffOfPerf"]
        )
        action_b = MeasureAction(
            Name="An action with a different name",
            Lookup=["Perimeter", "Conditioning", "HeatingCoeffOfPerf"],
        )
        assert (
            action_a.determine_parameter_name(building_template=a)
            == "HeatingCoeffOfPerf"
        )

        assert action_a.Name == "An action"
        assert action_a.Validator == None
        assert action_a.Transformer == None
        assert action_a.Lookup == ["Perimeter", "Conditioning", "HeatingCoeffOfPerf"]
        assert action_a == action_b
