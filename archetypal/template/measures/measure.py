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


class EnergyStarUpgrade(Measure):
    """The EnergyStarUpgrade changes the equipment power density to."""

    name = "EnergyStarUpgrade"
    description = "EnergyStar for tenant spaces of 0.75 W/sf ~= 8.07 W/m2"

    def __init__(self, lighting_power_density=8.07):
        """Initialize measure with parameters."""
        super(EnergyStarUpgrade, self).__init__()

        self.SetCoreEquipementPowerDensity = lambda building_template: setattr(
            building_template.Core.Loads, "LightingPowerDensity", lighting_power_density
        )
        self.SetPerimEquipementPowerDensity = lambda building_template: setattr(
            building_template.Perimeter.Loads,
            "LightingPowerDensity",
            lighting_power_density,
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
    rsi_value = 3.08

    def __init__(self, rsi_value=None):
        """Initialize measure with parameters.

        Notes:
            Changes the thickness of the insulation layer to match the selected
            rsi_value.

        Args:
            rsi_value (float): The new rsi value for external walls.
        """
        super(SetFacadeConstructionThermalResistanceToEnergyStar, self).__init__()

        if rsi_value is not None:
            self.rsi_value = rsi_value
        self.AddThermalInsulation = self._apply

    def _apply(self, bt):
        """Only apply to Perimeter facade constructions.

        Args:
            rsi_value:
        """
        self._set_insulation_layer_resistance(
            bt.Perimeter.Constructions.Facade, self.rsi_value
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
            log.warning(
                f"r_value is already higher for material_layer '{layer}' of "
                f"opaque_construction '{opaque_construction}'"
            )
        layer.r_value = energy_star_rsi


class FacadeUpgradeBest(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using best in class thermal insulation properties."""

    name = "FacadeUpgradeBest"
    description = "rsi value from climaplusbeta.com"
    rsi_value = 1 / 0.13


class FacadeUpgradeMid(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using median thermal insulation properties."""

    name = "FacadeUpgradeMid"
    description = "rsi value from climaplusbeta.com"
    rsi_value = 1 / 0.34


class FacadeUpgradeRegular(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using to-code thermal insulation properties."""

    name = "FacadeUpgradeRegular"
    description = "rsi value from climaplusbeta.com"
    rsi_value = 1 / 1.66


class FacadeUpgradeLow(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using affordable thermal insulation properties."""

    name = "FacadeUpgradeLow"
    description = "rsi value from climaplusbeta.com"
    rsi_value = 1 / 3.5
