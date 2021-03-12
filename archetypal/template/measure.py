"""Energy measures modules."""
from archetypal.template import ZoneLoad, BuildingTemplate
import logging

log = logging.getLogger(__name__)


class Measure:
    """Main class for the definition of EnergyMeasures."""

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


class EnergyStarUpgrade(Measure):
    """The EnergyStarUpgrade changes the equipment power density to."""

    def __init__(self):
        super().__init__()

        self.SetEquipementPowerDensity = lambda bt: setattr(
            bt.Core.Loads, "EquipmentPowerDensity", 3
        )
