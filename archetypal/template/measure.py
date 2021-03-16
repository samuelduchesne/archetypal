"""Energy measures modules."""
import logging

from archetypal.template import BuildingTemplate, MaterialLayer

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

    def apply_measure_to_whole_library(self, umi_template_library):
        """Apply this measure to all building templates in the library."""
        for bt in umi_template_library.BuildingTemplates:
            self.apply_measure_to_template(bt)

    def apply_measure_to_template(self, building_template):
        """Apply this measure to a specific building template.

        Args:
            building_template (BuildingTemplate): The building template object.
        """
        for _, measure_argument in self.__dict__.items():
            measure_argument(building_template) if callable(measure_argument) else None
            log.info(f"applied '{measure_argument}' to {building_template}")

    @staticmethod
    def measures():
        for a in dir(Measure):
            yield a

    def __repr__(self):
        return self.description


class EnergyStarUpgrade(Measure):
    """The EnergyStarUpgrade changes the equipment power density to."""

    name = "EnergyStarUpgrade"
    description = "EnergyStar for tenant spaces of 0.75 W/sf ~= 8.07 W/m2"

    def __init__(self):
        super(EnergyStarUpgrade, self).__init__()

        self.SetCoreEquipementPowerDensity = lambda building_template: setattr(
            building_template.Core.Loads, "LightingPowerDensity", 8.07
        )
        self.SetPerimEquipementPowerDensity = lambda building_template: setattr(
            building_template.Perimeter.Loads, "LightingPowerDensity", 8.07
        )


class SetFacadeConstructionThermalResistanceToEnergyStar(Measure):
    """This measure changes the r-value of the insulation layer of the facade
    construction to R5.78.
    """

    name = "SetFacadeConstructionThermalResistanceToEnergyStar"
    description = (
        "This measure changes the r-value of the insulation layer of the "
        "facade construction to R5.78."
    )

    def __init__(self):
        super(SetFacadeConstructionThermalResistanceToEnergyStar, self).__init__()

        self.AddThermalInsulation = self.apply

    def apply(self, bt):
        """Only apply to Perimeter facade constructions."""
        self.set_insulation_layer_resistance(bt.Perimeter.Constructions.Facade)

    @staticmethod
    def set_insulation_layer_resistance(oc):
        """Set the insulation later to r_value = 1.02."""
        layer: MaterialLayer = oc.infer_insulation_layer()
        layer.r_value = 1.017858  # R5.78 IP, will change the conductivity of the mat.
