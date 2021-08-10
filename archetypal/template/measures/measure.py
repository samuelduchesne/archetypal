"""Energy measures modules."""
import logging

from archetypal.template.materials.material_layer import MaterialLayer

log = logging.getLogger(__name__)


class Measure:
    """Main class for the definition of measures.

    Args:
        name (str): The name of the measure.
        description (str): A description of the measure.
    """

    name = ""
    description = ""

    def __init__(self):
        pass

    def apply_measure_to_whole_library(self, umi_template_library, *args):
        """Apply this measure to all building templates in the library."""
        for bt in umi_template_library.BuildingTemplates:
            self.apply_measure_to_template(bt, *args)

    def apply_measure_to_template(self, building_template, *args):
        """Apply this measure to a specific building template.

        Args:
            building_template (BuildingTemplate): The building template object.
        """
        for _, measure_argument in self.__dict__.items():
            measure_argument(building_template, *args) if callable(
                measure_argument
            ) else None
            log.info(f"applied '{measure_argument}' to {building_template}")

    def __repr__(self):
        """Return a representation of self."""
        return self.description

class SetMechanicalVentilation(Measure):
    """Set the Mechanical Ventilation."""

    name = "SetMechanicalVentilation"
    description = ""

    def __init__(self, ach=3.5, ventilation_schedule=None):
        """Initialize measure with parameters."""
        super(SetMechanicalVentilation, self).__init__()

        self.SetCoreVentilationAch = lambda building_template: setattr(
            building_template.Core.Ventilation, "ScheduledVentilationAch", ach
        )
        self.SetPerimVentilationAch = lambda building_template: setattr(
            building_template.Perimeter.Ventilation, "ScheduledVentilationAch", ach
        )
        if ventilation_schedule is not None:
            self.SetCoreVentilation = lambda building_template: setattr(
                building_template.Core.Ventilation, "ScheduledVentilationSchedule", ventilation_schedule
            )
            self.SetPerimVentilation = lambda building_template: setattr(
                building_template.Perimeter.Ventilation, "ScheduledVentilationSchedule", ventilation_schedule
            )
        if ach > 0:
            self.SetCoreScheduledVentilationOn = lambda building_template: setattr(
                building_template.Perimeter.Ventilation, "IsScheduledVentilationOn", True
            )
            self.SetPerimeterScheduledVentilationOn = lambda building_template: setattr(
                building_template.Perimeter.Ventilation, "IsScheduledVentilationOn", True
            )

class SetCOP(Measure):
    """Set the COPs."""

    name = "SetCOP"
    description = ""

    def __init__(self, cooling_cop=3.5, heating_cop=1):
        """Initialize measure with parameters."""
        super(SetCOP, self).__init__()

        self.SetCoreCoolingCOP = lambda building_template: setattr(
            building_template.Core.Conditioning, "CoolingCoeffOfPerf", cooling_cop
        )
        self.SetPerimCoolingCOP = lambda building_template: setattr(
            building_template.Perimeter.Conditioning, "CoolingCoeffOfPerf", cooling_cop
        )
        self.SetCoreHeatingCOP = lambda building_template: setattr(
            building_template.Core.Conditioning, "HeatingCoeffOfPerf", heating_cop
        )
        self.SetPerimHeatingCOP = lambda building_template: setattr(
            building_template.Perimeter.Conditioning, "HeatingCoeffOfPerf", heating_cop
        )


class EnergyStarUpgrade(Measure):
    """The EnergyStarUpgrade changes the equipment power density to."""

    name = "EnergyStarUpgrade"
    description = "EnergyStar for tenant spaces of 0.75 W/sf ~= 8.07 W/m2"

    def __init__(self, lighting_power_density=8.07, equipment_power_density=8.07):
        """Initialize measure with parameters."""
        super(EnergyStarUpgrade, self).__init__()

        self.SetCoreLightingPowerDensity = lambda building_template: setattr(
            building_template.Core.Loads, "LightingPowerDensity", lighting_power_density
        )
        self.SetPerimLightingPowerDensity = lambda building_template: setattr(
            building_template.Perimeter.Loads,
            "LightingPowerDensity",
            lighting_power_density,
        )
        self.SetCoreEquipementPowerDensity = lambda building_template: setattr(
            building_template.Core.Loads,
            "EquipmentPowerDensity",
            equipment_power_density,
        )
        self.SetPerimEquipementPowerDensity = lambda building_template: setattr(
            building_template.Perimeter.Loads,
            "EquipmentPowerDensity",
            equipment_power_density,
        )


class SetFacadeConstructionThermalResistanceToEnergyStar(Measure):
    """Facade upgrade.

    Changes the r-value of the insulation layer of the facade construction to R5.78.
    """

    name = "SetFacadeConstructionThermalResistanceToEnergyStar"
    description = (
        "This measure changes the r-value of the insulation layer of the "
        "facade construction to R5.78."
    )
    rsi_value_facade = 3.08
    rsi_value_roof = 5.02

    def __init__(self, rsi_value_facade=None, rsi_value_roof=None):
        """Initialize measure with parameters.

        Notes:
            Changes the thickness of the insulation layer to match the selected
            rsi_value.

        Args:
            rsi_value_facade (float): The new rsi value for external walls.
        """
        super(SetFacadeConstructionThermalResistanceToEnergyStar, self).__init__()

        if rsi_value_facade is not None:
            self.rsi_value_facade = rsi_value_facade
            self.rsi_value_roof = rsi_value_roof

        self.AlterFacade = (
            lambda building_template: self._set_insulation_layer_resistance(
                building_template.Perimeter.Constructions.Facade, self.rsi_value_facade
            )
        )
        self.AlterRoof = (
            lambda building_template: self._set_insulation_layer_resistance(
                building_template.Perimeter.Constructions.Roof, self.rsi_value_roof
            )
        )

    def _set_insulation_layer_resistance(self, opaque_construction, rsi_value):
        """Set the insulation later to r_value = 3.08.

        Hint:
            See `Table 2`_: Minimum Effective Thermal Resistance of Opaque Assemblies.

        .. _Table 2:
            https://www.nrcan.gc.ca/energy-efficiency/energy-star-canada/
            about-energy-star-canada/energy-star-announcements/energy-starr-
            new-homes-standard-version-126/14178
        """
        # First, find the insulation layer
        i = opaque_construction.infer_insulation_layer()
        layer: MaterialLayer = opaque_construction.Layers[i]

        # Then, change the r_value (which changes the thickness) of that layer only.
        energy_star_rsi = rsi_value
        if layer.r_value > energy_star_rsi:
            log.debug(
                f"r_value is already higher for material_layer '{layer}' of "
                f"opaque_construction '{opaque_construction}'"
            )
        layer.r_value = energy_star_rsi


class FacadeUpgradeBest(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using best in class thermal insulation properties."""

    name = "FacadeUpgradeBest"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 0.13


class FacadeUpgradeMid(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using median thermal insulation properties."""

    name = "FacadeUpgradeMid"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 0.34


class FacadeUpgradeRegular(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using to-code thermal insulation properties."""

    name = "FacadeUpgradeRegular"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 1.66


class FacadeUpgradeLow(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using affordable thermal insulation properties."""

    name = "FacadeUpgradeLow"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 3.5


class SetInfiltration(Measure):
    name = "SetInfiltration"
    description = "This measure sets the infiltration ACH of the perimeter zone."
    infiltration_ach = 0.6

    def __init__(self, infiltration_ach=None):
        super().__init__()
        if infiltration_ach is not None:
            self.infiltration_ach = infiltration_ach

        self.SetInfiltration = lambda building_template: setattr(
            building_template.Perimeter.Ventilation,
            "Infiltration",
            self.infiltration_ach,
        )

    def _apply(self, building_template):
        """Only apply to Perimeter zone ventilation.

        Args:
            building_template (BuildingTemplate): The building template object.
        """
        building_template.Perimeter.Ventilation.Infiltration = self.infiltration_ach


class InfiltrationRegular(SetInfiltration):
    infiltration_ach = 0.6


class InfiltrationMedium(SetInfiltration):
    infiltration_ach = 0.3


class InfiltrationTight(SetInfiltration):
    infiltration_ach = 0.1
