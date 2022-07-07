"""Energy measures modules."""
import functools
import logging

from archetypal.template.materials.material_layer import MaterialLayer

log = logging.getLogger(__name__)


def reducer(a, b):
    """Given an object, get an index/key

    Args:
        a (object): object to access
        b (key/index): something which can be used to access the object
    """
    try:
        return a[b]
    except TypeError:
        # Type error thrown when __getitem__ is not defined
        return getattr(a, b)


def get_path(root, address):
    """Given a path, get a value

    Args:
        root (object): the base object
        address (Array<string>): Where to find the target value
    """
    path = [root] + address if type(address) == list else [root, address]
    target = functools.reduce(reducer, path)
    return target


def set_path(root, address, value):
    """Given a path and a value, set a value

    Args:
        root (object): the base object
        address (Array<string>): The where to find the target object
        parameter (string): The final key for the target object
        value (any): Value to set
    """
    fullpath = [root] + address if type(address) == list else [root, address]
    path = fullpath[0:-1]
    parameter = fullpath[-1]
    target = functools.reduce(reducer, path)
    try:
        target[parameter] = value
    except TypeError:
        # Type error thrown when __setitem__ is not defined
        setattr(target, parameter, value)


class Measure:
    """Main class for the definition of measures.

    Args:
        name (str): The name of the measure.
        description (str): A description of the measure.
    """

    name = ""
    description = ""

    def __init__(self):
        self.change_loggers = {}
        self._props = set()
        self._actions = set()

    # TODO:
    # def __add__(self,other): warn if property or method names shared

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
            # log.info(f"applied '{measure_argument}' to {building_template}")

    def report_template_changelog(self, building_template):
        """Return the a dict of changes that will occur if the measure is applied to a template

        Args:
            building_template (BuildingTemplate): The building template object.
        """
        change_log = {}
        for name, get_changelog in self.change_loggers.items():
            change = get_changelog(building_template)
            if change["original_value"] != change["new_value"]:
                change_log[name] = get_changelog(building_template)
        return change_log

    def report_library_changelog(self, umi_template_library):
        """Return the a dict of changes that will occur if the measure is applied to the
        whole library, stored by template

        Args:
            umi_template_library (UmiTemplateLibrary): The library to mutate
        """
        change_logs = {}
        for bt in umi_template_library.BuildingTemplates:
            change_log = self.report_template_changelog(bt)
            if len(change_log.keys()) > 0:
                change_logs[bt.Name] = change_log
        return change_logs

    def add_modifier(
        self,
        modifier_name=None,
        modifier_prop=None,
        default=None,
        object_address=None,
        validator=None,
    ):
        """Add an action to the measure which will modify a template parameter with a new
        property value stored in the measure

        Args:
            modifier_name (String): A name for the action
            modifier_prop (String): A name for the measure prop to reference for the value
            default (any | None): Default value for the measure prop to use
            object_address (Array<String | int> | (building_template): Array<String | int>): Where to find the target in the template
            validator ((original_value: any, new_value: any, root: any | None): Boolan)
        """
        # TODO: Allow missing object_parameter and non-list-non-callable object_address
        # TODO: Consider extracting a modifier into its own class
        log.info(
            f"Adding {modifier_name} which uses prop {modifier_prop} to the measure {self.name}."
        )

        # Add the property to the measure's dict
        if default is not None:
            setattr(self, modifier_prop, default)
            if modifier_prop not in self._props:
                self._props.add(modifier_prop)
        else:
            if modifier_prop not in self._props:
                log.error(
                    f"Measure {self.name} does not yet have property {modifier_prop} and no default value was provided."
                )
                raise AttributeError

        def _address(building_template):
            return (
                object_address(building_template)
                if callable(object_address)
                else object_address
            )

        def _parameter(building_template):
            path = _address(building_template)
            if type(path) == list:
                return path[-1]
            else:
                return path

        def _original_value(building_template):
            return get_path(
                root=building_template,
                address=_address(building_template),
            )

        def _new_value(building_template):
            executes = (
                validator(
                    original_value=_original_value(building_template),
                    new_value=getattr(self, modifier_prop),
                    root=building_template,
                )
                if validator
                else True
            )
            return (
                getattr(self, modifier_prop)
                if executes
                else _original_value(building_template)
            )

        # Add a setter which dynamically finds the parameter to modify and uses the specified property from the measure
        setattr(
            self,
            modifier_name,
            lambda building_template: set_path(
                root=building_template,
                address=_address(building_template),
                value=_new_value(building_template),
            ),
        )
        self._actions.add(modifier_name)

        # Store a getter which takes in a template and produces a changelog.
        self.change_loggers[modifier_name] = lambda building_template: {
            "address": _address(building_template)[0:-1],
            "parameter": _parameter(building_template),
            "original_value": _original_value(building_template),
            "new_value": _new_value(building_template),
        }

    @property
    def props(self):
        props = {}
        for prop in self._props:
            props[prop] = getattr(self, prop)
        return props

    @property
    def actions(self):
        actions = {}
        for action in actions:
            actions[action] = getattr(self, action)
        return actions

    def __repr__(self):
        """Return a representation of self."""
        return self.description


class SetMechanicalVentilation(Measure):
    """Set the Mechanical Ventilation."""

    name = "SetMechanicalVentilation"
    description = ""

    def __init__(self, ventilation_ach=3.5, ventilation_schedule=None):
        """Initialize measure with parameters."""
        super(SetMechanicalVentilation, self).__init__()

        self.add_modifier(
            modifier_name="SetCoreVentilationAch",
            modifier_prop="ventilation_ach",
            default=ventilation_ach,
            object_address=["Core", "Ventilation", "ScheduledVentilationAch"],
        )

        self.add_modifier(
            modifier_name="SetPerimeterVentilationAch",
            modifier_prop="ventilation_ach",
            object_address=["Perimeter", "Ventilation", "ScheduledVentilationAch"],
        )

        if ventilation_schedule is not None:
            self.add_modifier(
                modifier_name="SetCoreVentilationSched",
                modifier_prop="ventilation_schedule",
                default=ventilation_schedule,
                object_address=["Core", "Ventilation", "ScheduledVentilationSchedule"],
            )
            self.add_modifier(
                modifier_name="SetPerimeterVentilationSched",
                modifier_prop="ventilation_schedule",
                object_address=["Perimeter", "Ventilation", "ScheduledVentilationAch"],
            )

        if ventilation_ach > 0:
            self.add_modifier(
                modifier_name="SetCoreVentilationStatus",
                modifier_prop="ventilation_status",
                default=True,
                object_address=["Core", "Ventilation", "IsScheduledVentilationOn"],
            )
            self.add_modifier(
                modifier_name="SetPerimeterVentilationStatus",
                modifier_prop="ventilation_status",
                object_address=["Perimeter", "Ventilation", "IsScheduledVentilationOn"],
            )


class SetCOP(Measure):
    """Set the COPs."""

    name = "SetCOP"
    description = ""

    def __init__(self, cooling_cop=3.5, heating_cop=1):
        """Initialize measure with parameters."""
        super(SetCOP, self).__init__()

        self.add_modifier(
            modifier_name="SetCoreCoolingCop",
            modifier_prop="cooling_cop",
            default=cooling_cop,
            object_address=["Core", "Conditioning", "CoolingCoeffOfPerf"],
        )
        self.add_modifier(
            modifier_name="SetPerimeterCoolingCop",
            modifier_prop="cooling_cop",
            object_address=["Perimeter", "Conditioning", "CoolingCoeffOfPerf"],
        )
        self.add_modifier(
            modifier_name="SetCoreHeatingCop",
            modifier_prop="heating_cop",
            default=heating_cop,
            object_address=["Core", "Conditioning", "HeatingCoeffOfPerf"],
        )
        self.add_modifier(
            modifier_name="SetPerimeterHeatingCop",
            modifier_prop="heating_cop",
            object_address=["Perimeter", "Conditioning", "HeatingCoeffOfPerf"],
        )


class EnergyStarUpgrade(Measure):
    """The EnergyStarUpgrade changes the equipment power density to."""

    name = "EnergyStarUpgrade"
    description = "EnergyStar for tenant spaces of 0.75 W/sf ~= 8.07 W/m2"

    def __init__(self, lighting_power_density=8.07, equipment_power_density=8.07):
        """Initialize measure with parameters."""
        super(EnergyStarUpgrade, self).__init__()

        self.add_modifier(
            modifier_name="SetCoreLightingPowerDensity",
            modifier_prop="lighting_power_density",
            default=lighting_power_density,
            object_address=["Core", "Loads", "LightingPowerDensity"],
        )
        self.add_modifier(
            modifier_name="SetPerimeterLightingPowerDensity",
            modifier_prop="lighting_power_density",
            object_address=["Perimeter", "Loads", "LightingPowerDensity"],
        )
        self.add_modifier(
            modifier_name="SetCoreEquipmentPowerDensity",
            modifier_prop="equipment_power_density",
            default=equipment_power_density,
            object_address=["Core", "Loads", "EquipmentPowerDensity"],
        )
        self.add_modifier(
            modifier_name="SetPerimeterEquipmentPowerDensity",
            modifier_prop="equipment_power_density",
            object_address=["Perimeter", "Loads", "EquipmentPowerDensity"],
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

        def get_insulation_layer_path(building_template, structural_part):
            constructions = building_template.Perimeter.Constructions
            insulation_layer_index = getattr(
                constructions, structural_part
            ).infer_insulation_layer()
            return [
                "Perimeter",
                "Constructions",
                structural_part,
                "Layers",
                insulation_layer_index,
                "r_value",
            ]

        # TODO: reproduce original warning in _set_insulation_layer_resistance
        self.add_modifier(
            modifier_name="AlterFacade",
            modifier_prop="rsi_value_facade",
            default=rsi_value_facade if rsi_value_facade else self.rsi_value_facade,
            object_address=lambda building_template: get_insulation_layer_path(
                building_template, "Facade"
            ),
        )

        self.add_modifier(
            modifier_name="AlterRoof",
            modifier_prop="rsi_value_roof",
            default=rsi_value_roof if rsi_value_roof else self.rsi_value_roof,
            object_address=lambda building_template: get_insulation_layer_path(
                building_template, "Roof"
            ),
        )


class FacadeUpgradeBest(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using best in class thermal insulation properties."""

    name = "FacadeUpgradeBest"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 0.13
    rsi_value_roof = 1 / 0.11


class FacadeUpgradeMid(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using median thermal insulation properties."""

    name = "FacadeUpgradeMid"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 0.34
    rsi_value_roof = 1 / 0.33


class FacadeUpgradeRegular(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using to-code thermal insulation properties."""

    name = "FacadeUpgradeRegular"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 1.66
    rsi_value_roof = 1 / 2.37


class FacadeUpgradeLow(SetFacadeConstructionThermalResistanceToEnergyStar):
    """A facade upgrade using affordable thermal insulation properties."""

    name = "FacadeUpgradeLow"
    description = "rsi value from climaplusbeta.com"
    rsi_value_facade = 1 / 3.5
    rsi_value_roof = 1 / 4.5


class SetInfiltration(Measure):
    name = "SetInfiltration"
    description = "This measure sets the infiltration ACH of the perimeter zone."
    infiltration_ach = 0.6

    def __init__(self, infiltration_ach=None):
        super().__init__()
        self.add_modifier(
            modifier_name="SetInfiltration",
            modifier_prop="infiltration_ach",
            default=infiltration_ach if infiltration_ach else self.infiltration_ach,
            object_address=["Perimeter", "Ventilation", "Infiltration"],
        )


class InfiltrationRegular(SetInfiltration):
    infiltration_ach = 0.6


class InfiltrationMedium(SetInfiltration):
    infiltration_ach = 0.3


class InfiltrationTight(SetInfiltration):
    infiltration_ach = 0.1
