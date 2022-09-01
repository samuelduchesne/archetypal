"""Energy measures modules."""
import functools
import inspect
import logging

from archetypal.template.building_template import BuildingTemplate
from archetypal.template.schedule import UmiSchedule
from archetypal.umi_template import UmiTemplateLibrary

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


class MeasureAction:
    """Stores an Archetypal parameter (or lookup) which
       can be associated with a measure
    Args:
        Name (str): The name of the action
        Lookup (callable | list<str>): Either an archetypal path array to the target, or a function which returns one
        Validator (callable | None): Passed building_template, original_value, new_value and returns boolean
        Transformer (callable | None): Passed building_template, original_value, proposed_transformer_value and returns a new value for the target
    """

    def __init__(self, Name, Lookup, Validator=None, Transformer=None):
        self._name = Name  # Names are not mutable
        self.Lookup = Lookup
        self.Validator = Validator
        self.Transformer = Transformer

    def __repr__(self):
        return f"{self.Name}:{self.Lookup}"

    def __str__(self):
        """string representation of the object as Name:address"""
        return self.__repr__()

    def __hash__(self):
        return hash(self.__repr__())

    def __eq__(self, other):
        return self.Lookup == other.Lookup

    @property
    def Name(self):
        return self._name

    @property
    def is_dynamic(self):
        return callable(self.Lookup)

    @property
    def Lookup(self):
        """Get or set the action's target lookup"""
        return self._lookup

    @Lookup.setter
    def Lookup(self, lookup):
        """Get or set a measure action target lookup

        Args:
            lookup (callable | none): if callable, the function will be passed a 'building_template' and can also accept additional **kwargs.
            If any of the expected arguments are omitted, it should accept **kwargs.
        """
        if isinstance(lookup, list):
            self._lookup = lookup
        else:
            sig = inspect.signature(lookup)
            if any((arg not in sig.parameters for arg in ("building_template",))):
                assert (
                    "kwargs" in sig.parameters
                ), f"The supplied lookup for action {self} must accept **kwargs if it does not accept 'building_template'"
            self._lookup = lookup

    @property
    def Validator(self):
        """Get or set a measure action validator"""
        return self._validator

    @Validator.setter
    def Validator(self, validator):
        """Get or set a measure action validator

        Args:
            validator (callable | none): if callable, the function will be passed a 'building_template', 'original_value', and 'new_value'
            and can also accept additional **kwargs.  If any of the expected arguments are omitted, it should accept **kwargs.
        """
        if validator is None:
            self._validator = None
        else:
            sig = inspect.signature(validator)
            if any(
                (
                    arg not in sig.parameters
                    for arg in ("building_template", "original_value", "new_value")
                )
            ):
                assert (
                    "kwargs" in sig.parameters
                ), f"The supplied validator for {self} must accept **kwargs if it does not accept all of 'building_template', 'original_value', and 'new_value'"
            self._validator = validator

    @property
    def Transformer(self):
        """Get or set a measure action transformer """

        return self._transformer

    @Transformer.setter
    def Transformer(self, transformer):
        """Get or set a measure action transformer

        Args:
            transformer (callable | none): if callable, the function will be passed a 'building_template', 'original_value', and 'proposed_transformer_value'
            and can also accept additional **kwargs.  If any of the expected arguments are omitted, it should accept **kwargs.
        """
        if transformer is None:
            self._transformer = None
        else:
            sig = inspect.signature(transformer)
            if any(
                (
                    arg not in sig.parameters
                    for arg in (
                        "building_template",
                        "original_value",
                        "proposed_transformer_value",
                    )
                )
            ):
                assert (
                    "kwargs" in sig.parameters
                ), f"The supplied transformer for {self} must accept **kwargs if it does not accept all of 'building_template', 'original_value', and 'proposed_transformer_value'"
            self._transformer = transformer

    def determine_full_address(self, building_template, *args, **kwargs):
        """Determine the full mutation path for the action in a given building template

        Args:
            building_template: the building template to find the path in
        """

        return (
            self.Lookup(building_template=building_template, *args, **kwargs)
            if self.is_dynamic
            else self.Lookup
        )

    def determine_parameter_name(self, building_template, *args, **kwargs):
        """Determine the parameter name to mutate for the action in a given building template

        Args:
            building_template: the building template to find the path in
        """
        path = self.determine_full_address(
            building_template=building_template, *args, **kwargs
        )
        return path[-1]

    def determine_object_address(self, building_template, *args, **kwargs):
        """Determine the path to the object to mutate for the action in a given building template

        Args:
            building_template: the building template to find the path in
        """

        path = self.determine_full_address(
            building_template=building_template, *args, **kwargs
        )
        path = path.copy()
        path.pop()
        return path

    def lookup_original_value(self, building_template, *args, **kwargs):
        """Find the current value of the target parameter in a given building template

        Args:
            building_template: the building template to find the parameter value in
        """
        return get_path(
            root=building_template,
            address=self.determine_full_address(
                building_template=building_template, *args, **kwargs
            ),
        )

    def lookup_original_object(self, building_template, *args, **kwargs):
        """Find the object to mutate in a given building template

        Args:
            building_template: the building template to find the object in
        """
        object_address = self.determine_object_address(
            building_template=building_template, *args, **kwargs
        )
        return get_path(
            root=building_template,
            address=object_address,
        )

    def compute_new_value(
        self, building_template, proposed_transformer_value, *args, **kwargs
    ):
        """Return a proposed new value for the target parameter in a building template

        Args:
            building_template: the building template to validate a change in
            proposed_transformer_value: the input to the transformer which generates a new value
        """
        original_value = self.lookup_original_value(
            building_template=building_template, *args, **kwargs
        )
        new_value = (
            self.Transformer(
                building_template=building_template,
                original_value=original_value,
                proposed_transformer_value=proposed_transformer_value,
                *args,
                **kwargs,
            )
            if getattr(self, "Transformer", None)
            else proposed_transformer_value
        )
        return new_value

    def _validate(self, building_template, new_value, *args, **kwargs):
        """Validate a proposed change to a building template and return the new value

        Args:
            building_template: the building template to validate a change in
            new_value: the new value for the target parameter
        """

        original_value = self.lookup_original_value(
            building_template=building_template, *args, **kwargs
        )
        return (
            self.Validator(
                building_template=building_template,
                original_value=original_value,
                new_value=new_value,
                *args,
                **kwargs,
            )
            if getattr(self, "Validator", None)
            else True
        )

    def mutate(
        self,
        building_template,
        proposed_transformer_value,
        changelog_only=False,
        *args,
        **kwargs,
    ):
        new_value = self.compute_new_value(
            building_template=building_template,
            proposed_transformer_value=proposed_transformer_value,
            *args,
            **kwargs,
        )
        original_value = self.lookup_original_value(
            building_template=building_template, *args, **kwargs
        )
        validated = self._validate(
            building_template=building_template, new_value=new_value, *args, **kwargs
        )
        if validated:
            address = self.determine_full_address(
                building_template=building_template, *args, **kwargs
            )
            if not changelog_only:
                set_path(root=building_template, address=address, value=new_value)
            return (address, original_value, new_value)
        else:
            return None


class MeasureProperty:
    """Class for controlling multiple actions with a single property value"""

    __slots__ = (
        "_name",
        "_attr_name",
        "_description",
        "_default",
        "_value",
        "_actions",
        "_transformer",
        "_validator",
    )

    def __init__(
        self,
        Name,
        AttrName,
        Description,
        Default,
        Transformer=None,
        Validator=None,
        Actions=None,
        Lookup=None,
    ):
        assert isinstance(Name, str)
        assert isinstance(AttrName, str) and AttrName.isidentifier()
        self._name = Name
        self._attr_name = AttrName
        self._description = Description
        self._actions = set()
        self.Default = Default
        self.Transformer = Transformer
        self.Validator = Validator

        if isinstance(Actions, MeasureAction):
            Actions = [Actions]
        self._actions = set()
        for action in Actions or []:
            self.add_action(action)

        self.Value = Default
        if Lookup is not None:
            action = MeasureAction(Name=self.Name, Lookup=Lookup)
            self.add_action(action)

    @property
    def Name(self):
        return self._name

    @property
    def AttrName(self):
        return self._attr_name

    @property
    def Description(self):
        return self._description

    @property
    def Default(self):
        return self._default

    @Default.setter
    def Default(self, value):
        self._default = value
        self.Value = value

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, value):
        # In case we want to do some sort of type checking later
        self._value = value

    @property
    def Validator(self):
        """Get or set a measure property validator """
        return self._validator

    @Validator.setter
    def Validator(self, validator):
        """Get or set a measure property validator

        Args:
            validator (callable | none): Will overwrite the associated action validators. the function will be passed a 'building_template', 'original_value', and 'new_value'
            and can also accept additional **kwargs.  If any of the expected arguments are omitted, it should accept **kwargs.
        """
        if validator is None:
            self._validator = None
        else:
            sig = inspect.signature(validator)
            if any(
                (
                    arg not in sig.parameters
                    for arg in ("building_template", "original_value", "new_value")
                )
            ):
                assert (
                    "kwargs" in sig.parameters
                ), f"The supplied validator for {self} must accept **kwargs if it does not accept all of 'building_template', 'original_value', and 'new_value'"
            self._validator = validator
        for action in self._actions:
            action.Validator = validator

    @property
    def Transformer(self):
        """Get or set a measure action transformer"""
        return self._transformer

    @Transformer.setter
    def Transformer(self, transformer):
        """Get or set a measure property transformer

        Args:
            transformer (callable | none): will overwrite associated action transformers; the function will be passed a 'building_template', 'original_value', and 'proposed_transformer_value'
            and can also accept additional **kwargs.  If any of the expected arguments are omitted, it should accept **kwargs.
        """
        if transformer is None:
            self._transformer = None
        else:
            sig = inspect.signature(transformer)
            if any(
                (
                    arg not in sig.parameters
                    for arg in (
                        "building_template",
                        "original_value",
                        "proposed_transformer_value",
                    )
                )
            ):
                assert (
                    "kwargs" in sig.parameters
                ), f"The supplied transformer for {self} must accept **kwargs if it does not accept all of 'building_template', 'original_value', and 'proposed_transformer_value'"
            self._transformer = transformer
        for action in self._actions:
            action.Transformer = transformer

    def add_action(self, action):
        """Add an action which will be controlled by this property

        Args:
            action (MeasureAction): the action to add
        """
        assert isinstance(action, MeasureAction)
        if self.Validator and getattr(action, "Validator", None) is None:
            action.Validator = self.Validator
        if self.Transformer and getattr(action, "Transformer", None) is None:
            action.Transformer = self.Transformer
        self._actions.add(action)

    def lookup_objects_to_mutate(self, building_template, *args, **kwargs):
        """Lookup all objects which will be mutated by this property

        Args:
            building_template: the template to identify all mutation targets in
        """
        objects_to_mutate = {}  # store the objects to mutate and the path to find it at
        for action in self:
            object_to_mutate = action.lookup_original_object(
                building_template=building_template, *args, **kwargs
            )
            object_address = action.determine_object_address(
                building_template=building_template, *args, **kwargs
            )
            full_path = action.determine_full_address(
                building_template=building_template, *args, **kwargs
            )
            if object_to_mutate not in objects_to_mutate:
                objects_to_mutate[object_to_mutate] = []
            objects_to_mutate[object_to_mutate].append(
                {"path": full_path, "object_address": object_address}
            )
        return objects_to_mutate

    def mutate(self, building_template, changelog_only=False, *args, **kwargs):
        mutations = []
        for action in self:
            mutation = action.mutate(
                building_template=building_template,
                proposed_transformer_value=self.Value,
                changelog_only=changelog_only,
                *args,
                **kwargs,
            )
            if mutation:
                mutations.append(mutation)
        return mutations

    def __repr__(self):
        """Return a representation of self."""
        return ":".join([str(self.Name), str(self.AttrName)])

    def __str__(self):
        """string representation of the object as Name:AttrName"""
        return self.__repr__()

    def __hash__(self):
        # Hash using name and attr name
        return hash(self.__repr__())

    def __eq__(self, other):
        # If two properties have the same name and will use the same attribute, they should be considered equal
        return self.__repr__() == other.__repr__()

    def __iter__(self):
        for action in self._actions:
            yield action


class Measure(object):
    """Main class for the definition of measures.

    Args:
        Name (str): The name of the measure.
        Description (str): A description of the measure.
        Properties (list<MeasureProperty>): Initial properties that are part of the measure
    """

    # TODO: Write change log functions
    # TODO: Write Properties / Actions getters
    __slots__ = (
        "_name",
        "_description",
        "_properties",
    )

    def __init__(self, Name="Measure", Description="Upgrade Templates", Properties=[]):
        super().__setattr__("_properties", set())

        self.Name = Name or self._name
        self.Description = Description or self._description

        if isinstance(Properties, MeasureProperty):
            Properties = [Properties]

        for prop in Properties or []:
            self.add_property(prop)

    @property
    def Name(self):
        """Get or set the Measure's name"""
        return self._name

    @Name.setter
    def Name(self, name):
        """Get or set the Measure's name"""
        self._name = name

    @property
    def Description(self):
        """Get or set the Measure's description"""
        return self._description

    @Description.setter
    def Description(self, description):
        """Get or set the Measure's description"""
        self._description = description

    def __iter__(self):
        for prop in self._properties:
            yield prop

    def __add__(self, other):
        # prefer LHS metadata
        new_measure = Measure(
            Name=self.Name,
            Description=self.Description,
            Properties=[prop for prop in self],
        )
        for prop in other:
            new_measure.add_property(prop)

        return new_measure

    def __iadd__(self, other):
        for prop in other:
            self.add_property(prop)
        return self

    def _get_property_by_name(self, name):
        """find a MeasureProperty object by Name"""
        prop = next(
            iter((x for x in self._properties if x.Name == name)),
            None,
        )
        return prop

    def _get_property_by_attr_name(self, attr_name):
        """find a MeasureProperty object by AttrName"""
        prop = next(
            iter((x for x in self._properties if x.AttrName == attr_name)),
            None,
        )
        return prop

    def __setitem__(self, name, value):
        """Change a MeasureProperty's value using the property's Name"""
        prop = self._get_property_by_name(name)
        assert isinstance(
            prop, MeasureProperty
        ), f"Measure:{self.Name} does not have a property named '{name}'"
        prop.Value = value

    def __getitem__(self, name):
        """Get a MeasureProperty's value using the property's Name"""
        prop = self._get_property_by_name(name)
        assert isinstance(
            prop, MeasureProperty
        ), f"Measure:{self.Name} does not have a property named '{name}'"
        return prop.Value

    def __setattr__(self, attr_name, value):
        """Change a MeasurProperty's value using the property's AttrName"""
        prop = self._get_property_by_attr_name(attr_name)
        if prop is not None:
            prop.Value = value
        else:
            super().__setattr__(attr_name, value)

    def __getattr__(self, attr_name):
        """Get a MeasureProperty's value using the property AttrName"""
        prop = self._get_property_by_attr_name(attr_name)
        if isinstance(prop, MeasureProperty):
            return prop.Value
        else:
            super().__getattr__(attr_name)

    @property
    def Properties(self):
        """Get or set the measure's properties"""
        return self._properties

    @Properties.setter
    def Properties(self, Properties):
        """Get or set the measure's properties"""
        self._properties = set()
        if isinstance(Properties, MeasureProperty):
            Properties = [Properties]
        for prop in Properties:
            print(f"adding a prop - {prop}")
            self.add_property(prop)

    @property
    def PropNames(self):
        return [prop.Name for prop in self]

    @property
    def PropAttrs(self):
        return [prop.AttrName for prop in self]

    def get_property(self, AttrName=None, Name=None):
        if AttrName:
            return self._get_property_by_attr_name(AttrName)
        else:
            return self._get_property_by_name(Name)

    def remove_property(self, AttrName=None, Name=None):
        prop = self.get_property(AttrName, Name)
        self._properties.remove(prop)

    def add_property(self, prop):
        """Add a property to a measure

        Args:
            prop (MeasureProperty): The property to add
        """
        assert isinstance(prop, MeasureProperty)
        assert prop.Name not in [
            _prop.Name for _prop in self._properties
        ], f"Measure {self} already has a property with the Name {prop.Name}"
        assert prop.AttrName not in [
            _prop.AttrName for _prop in self._properties
        ], f"Measure {self} already has a property with the AttrName {prop.AttrName}"
        if hasattr(self, prop.AttrName):
            prop.Value = getattr(self, prop.AttrName)
        self._properties.add(prop)

    def lookup_objects_to_mutate(self, building_template, *args, **kwargs):
        """Returns a dict of objects which will be mutated by this measure,
        with objects as keys and the path data about the mutations as values.
        Useful for disentanglement before mutation

        Args:
            building_template: the building template to determine mutations in
        """
        measure_objects_to_mutate = {}
        for prop in self._properties:
            prop_objects_to_mutate = prop.lookup_objects_to_mutate(
                building_template=building_template, *args, **kwargs
            )
            for object_to_mutate, addresses in prop_objects_to_mutate.items():
                if object_to_mutate not in measure_objects_to_mutate:
                    measure_objects_to_mutate[object_to_mutate] = []
                measure_objects_to_mutate[object_to_mutate].extend(addresses)
        return measure_objects_to_mutate

    def changelog(self, target, *args, **kwargs):
        """Report a changelog for all BuildingTemplates in target without mutation
        Args:
            target (BuildingTemplate or UmiTemplateLibrary): The object to report changelog for

        Returns:
            changelog: dict<BuildingTemplate, (List of str, value, value)
        """
        return self.mutate(
            target=target, disentangle=False, changelog_only=True, *args, **kwargs
        )

    def mutate(self, target, disentangle=True, changelog_only=False, *args, **kwargs):
        """Mutate a template or a whole library

        Args:
            target (BuildingTemplate or UmiTemplateLibrary): The template or library to upgrade
            disentangle (boolean): If true, the tree of each upgraded object will be duplicated and replaced before mutation
            changelog_only (boolean): If true, reports a changelog without mutating the target
        """
        mutations = {}
        if isinstance(target, BuildingTemplate):
            bt_mutations = self.mutate_template(
                target,
                disentangle=disentangle,
                changelog_only=changelog_only,
                *args,
                **kwargs,
            )
            mutations[target] = bt_mutations
        elif isinstance(target, UmiTemplateLibrary):
            mutations = self.mutate_library(
                target,
                disentangle=disentangle,
                changelog_only=changelog_only,
                *args,
                **kwargs,
            )
        return mutations

    def mutate_template(
        self, building_template, disentangle=True, changelog_only=False, *args, **kwargs
    ):
        """Mutate a template

        Args:
            target (BuildingTemplate): The template to upgrade
        """
        assert isinstance(
            building_template, BuildingTemplate
        ), "'building_template' argument must be a BuildingTemplate"
        if disentangle and not changelog_only:
            # Every object which gets mutated is given an entirely new tree to separate it
            # from other templates which may have used the objects or even other objects
            # within the same template which may use it
            objects_to_mutate = self.lookup_objects_to_mutate(
                building_template=building_template, *args, **kwargs
            )
            for metadatas in objects_to_mutate.values():
                for metadata in metadatas:
                    object_address = metadata["object_address"]
                    for i in range(1, len(object_address) + 1):
                        address = object_address[0:i]
                        original_object = get_path(
                            root=building_template, address=address
                        )
                        new_object = (
                            original_object.duplicate()
                            if hasattr(original_object, "duplicate")
                            else original_object.copy()
                        )
                        set_path(
                            root=building_template, address=address, value=new_object
                        )

        mutations = []
        for prop in self:
            prop_mutations = prop.mutate(
                building_template=building_template,
                changelog_only=changelog_only,
                *args,
                **kwargs,
            )
            mutations.extend(prop_mutations)
        return mutations

    def mutate_library(
        self, library, disentangle=True, changelog_only=False, *args, **kwargs
    ):
        """Mutate a library

        Args:
            target (UmiTemplateLibrary): The library to upgrade
        """
        assert isinstance(
            library, UmiTemplateLibrary
        ), "'library' argument must be an UmiTemplateLibrary"
        mutations = {}
        for bt in library.BuildingTemplates:
            bt_mutations = self.mutate_template(
                bt,
                disentangle=disentangle,
                changelog_only=changelog_only,
                *args,
                **kwargs,
            )
            mutations[bt] = bt_mutations
        library.update_components_list()
        return mutations


class SetMechanicalVentilation(Measure):
    """Set the Mechanical Ventilation."""

    _name = ("Set Mechanical Ventilation",)
    _description = ("Change mechanical ventilation rates and schedules",)

    def __init__(self, VentilationACH=3.5, VentilationSchedule=None, **kwargs):
        """Initialize measure with parameters."""
        super(SetMechanicalVentilation, self).__init__(
            **kwargs,
        )

        # Configure Ventilation ACH Property and actions
        ventilation_ach_property = MeasureProperty(
            Name="Ventilation ACH",
            AttrName="VentilationACH",
            Description="Set Ventilation ACH",
            Default=VentilationACH,
        )
        ventilation_ach_property.add_action(
            MeasureAction(
                Name="Set Perimeter Ventilation ACH",
                Lookup=["Perimeter", "Ventilation", "ScheduledVentilationAch"],
            )
        )
        ventilation_ach_property.add_action(
            MeasureAction(
                Name="Set Core Ventilation ACH",
                Lookup=["Core", "Ventilation", "ScheduledVentilationAch"],
            )
        )

        # Configure Ventilation boolean actions
        ventilation_boolean_property = MeasureProperty(
            Name="Is Ventilation On",
            AttrName="IsVentilationOn",
            Description="Automatically turn on scheduled ventilation",
            Default=True,
        )
        ventilation_boolean_property.add_action(
            MeasureAction(
                Name="Set Perimeter Ventilation Toggle",
                Lookup=["Perimeter", "Ventilation", "IsScheduledVentilationOn"],
            )
        )
        ventilation_boolean_property.add_action(
            MeasureAction(
                Name="Set Core Ventilation Toggle",
                Lookup=["Core", "Ventilation", "IsScheduledVentilationOn"],
            )
        )

        # Configure schedule actions
        ventilation_schedule_property = MeasureProperty(
            Name="Ventilation Schedule",
            AttrName="VentilationSchedule",
            Description="Set Ventilation Schedule",
            Default=VentilationSchedule,
            Validator=lambda new_value, **kwargs: isinstance(new_value, UmiSchedule),
        )
        ventilation_schedule_property.add_action(
            MeasureAction(
                Name="Set Perimeter Ventilation Schedule",
                Lookup=["Perimeter", "Ventilation", "ScheduledVentilationSchedule"],
            )
        )
        ventilation_schedule_property.add_action(
            MeasureAction(
                Name="Set Core Ventilation Schedule",
                Lookup=["Core", "Ventilation", "ScheduledVentilationSchedule"],
            )
        )
        # Add properties to measure
        self.add_property(ventilation_ach_property)
        self.add_property(ventilation_boolean_property)
        self.add_property(ventilation_schedule_property)


class SetCOP(Measure):
    """Set the COPs."""

    _name = ("Set HVAC CoP",)
    _description = ("Set heating and cooling coefficients of performance",)

    def __init__(self, CoolingCoP=3.5, HeatingCoP=1, **kwargs):
        """Initialize measure with parameters."""
        super(SetCOP, self).__init__(**kwargs)

        # Configure Heating Property and Actions
        heating_property = MeasureProperty(
            Name="Heating CoP",
            AttrName="HeatingCoP",
            Description="Set Heating Coefficient of Performance",
            Default=HeatingCoP,
        )
        heating_property.add_action(
            MeasureAction(
                Name="Set Perimeter Heating CoP",
                Lookup=["Perimeter", "Conditioning", "HeatingCoeffOfPerf"],
            )
        )
        heating_property.add_action(
            MeasureAction(
                Name="Set Core Heating CoP",
                Lookup=["Core", "Conditioning", "HeatingCoeffOfPerf"],
            )
        )

        # Configure Cooling Property and Actions
        cooling_property = MeasureProperty(
            Name="Cooling CoP",
            AttrName="CoolingCoP",
            Description="Set Cooling Coefficient of Performance",
            Default=CoolingCoP,
        )
        cooling_property.add_action(
            MeasureAction(
                Name="Set Perimeter Cooling CoP",
                Lookup=["Perimeter", "Conditioning", "CoolingCoeffOfPerf"],
            )
        )
        cooling_property.add_action(
            MeasureAction(
                Name="Set Core Core Cooling CoP",
                Lookup=["Core", "Conditioning", "CoolingCoeffOfPerf"],
            )
        )

        # Add properties to measure
        self.add_property(heating_property)
        self.add_property(cooling_property)


class SetElectricLoadsEfficiency(Measure):
    """The EnergyStarUpgrade changes the equipment power density too."""

    _name = ("Electric Loads Efficiency",)
    _description = ("Change equipment and lighting loads efficiency",)

    def __init__(self, LightingPowerDensity=8.07, EquipmentPowerDensity=8.07, **kwargs):
        """Initialize measure with parameters."""
        super(SetElectricLoadsEfficiency, self).__init__(**kwargs)

        # Configure Equipment Properties and Actions
        equipment_property = MeasureProperty(
            Name="Equipment Power Density",
            AttrName="EquipmentPowerDensity",
            Description="Change Equipment Power Density",
            Default=EquipmentPowerDensity,
        )
        equipment_property.add_action(
            MeasureAction(
                Name="Change Perimeter Equipment Power Density",
                Lookup=["Perimeter", "Loads", "EquipmentPowerDensity"],
            )
        )
        equipment_property.add_action(
            MeasureAction(
                Name="Change Core Equipment Power Density",
                Lookup=["Core", "Loads", "EquipmentPowerDensity"],
            )
        )

        # Configure Lighting Properties and Actions
        lighting_property = MeasureProperty(
            Name="Lighting Power Density",
            AttrName="LightingPowerDensity",
            Description="Change Lighting Power Density",
            Default=LightingPowerDensity,
        )
        lighting_property.add_action(
            MeasureAction(
                Name="Change Perimeter Lighting Power Density",
                Lookup=["Perimeter", "Loads", "LightingPowerDensity"],
            )
        )
        lighting_property.add_action(
            MeasureAction(
                Name="Change Core Lighting Power Density",
                Lookup=["Core", "Loads", "LightingPowerDensity"],
            )
        )

        # Add properties to measure
        self.add_property(equipment_property)
        self.add_property(lighting_property)


class SetFacadeInsulationThermalResistance(Measure):

    _name = "Facade Upgrade (Insulation Only)"
    _description = "Upgrade roof and facade insulation by specifying R-Values for the Insulation Layers."

    def __init__(self, RoofRValue=5.02, FacadeRValue=3.08, **kwargs):
        super(SetFacadeInsulationThermalResistance, self).__init__(**kwargs)

        def make_get_insulation_layer_path(structural_part):
            def get_insulation_layer_path(building_template):
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

            return get_insulation_layer_path

        get_facade_insulation_layer_path = make_get_insulation_layer_path("Facade")
        get_roof_insulation_layer_path = make_get_insulation_layer_path("Roof")

        facade_insulation_property = MeasureProperty(
            Name="Facade Insulation R-Value",
            AttrName="FacadeRValue",
            Description="Set facade insulation layer R-Value",
            Default=FacadeRValue,
        )
        facade_insulation_property.add_action(
            MeasureAction(
                Name="Change Facade Insualtion Layer R-Value",
                Lookup=get_facade_insulation_layer_path,
            )
        )
        self.add_property(facade_insulation_property)

        roof_insulation_property = MeasureProperty(
            Name="Roof Insulation R-Value",
            AttrName="RoofRValue",
            Description="Set roof insulation layer R-Value",
            Default=RoofRValue,
        )
        roof_insulation_property.add_action(
            MeasureAction(
                Name="Change Roof Insualtion Layer R-Value",
                Lookup=get_roof_insulation_layer_path,
            )
        )
        self.add_property(roof_insulation_property)

    @classmethod
    def Best(cls):
        return cls(
            FacadeRValue=1 / 0.13,
            RoofRValue=1 / 0.11,
            Name="Facade Upgrade Best",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Mid(cls):
        return cls(
            FacadeRValue=1 / 0.34,
            RoofRValue=1 / 0.33,
            Name="Facade Upgrade Mid",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Regular(cls):
        return cls(
            FacadeRValue=1 / 1.66,
            RoofRValue=1 / 2.37,
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Low(cls):
        return cls(
            FacadeRValue=1 / 3.5,
            RoofRValue=1 / 4.5,
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )


class SetFacadeThermalResistance(Measure):

    _name = "Facade Upgrade"
    _description = "Upgrade roof and facade insulation by specifying R-Values for entire assemblies."

    def __init__(self, RoofRValue, FacadeRValue, **kwargs):

        super(SetFacadeThermalResistance, self).__init__(**kwargs)
        roof_property = MeasureProperty(
            Name="Roof R-Value",
            AttrName="RoofRValue",
            Description="R-value for entire roof assembly",
            Default=RoofRValue,
        )
        roof_property.add_action(
            MeasureAction(
                Name="Change Roof R-Value",
                Lookup=["Perimeter", "Constructions", "Roof", "r_value"],
            )
        )
        facade_property = MeasureProperty(
            Name="Facade R-Value",
            AttrName="FacadeRValue",
            Description="R-value for entire facade assembly",
            Default=FacadeRValue,
        )
        facade_property.add_action(
            MeasureAction(
                Name="Change Facade R-Value",
                Lookup=["Perimeter", "Constructions", "Facade", "r_value"],
            )
        )

        self.add_property(roof_property)
        self.add_property(facade_property)

    @classmethod
    def Best(cls):
        return cls(
            FacadeRValue=15,
            RoofRValue=10,
            Name="Facade Upgrade Best",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Mid(cls):
        return cls(
            FacadeRValue=10,
            RoofRValue=10,
            Name="Facade Upgrade Mid",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Regular(cls):
        return cls(
            FacadeRValue=2,
            RoofRValue=2,
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Low(cls):
        return cls(
            FacadeRValue=1,
            RoofRValue=1,
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )


class SetInfiltration(Measure):

    _name = "Set Infiltration"
    _description = "This measure sets the infiltration ACH of the perimeter zone."

    def __init__(self, Infiltration=0.6, **kwargs):
        infiltration_action = MeasureAction(
            Name="Set Infiltration ACH",
            Lookup=["Perimeter", "Ventilation", "Infiltration"],
            **kwargs,
        )
        infiltration_property = MeasureProperty(
            Name="Infiltration",
            AttrName="Infiltration",
            Description="Set Infiltration ACH",
            Default=Infiltration,
            Actions=infiltration_action,
        )

        super().__init__(Properties=infiltration_property)

    @classmethod
    def Regular(cls):
        return cls(Infiltration=0.6)

    @classmethod
    def Medium(cls):
        return cls(Infiltration=0.3)

    @classmethod
    def Tight(cls):
        return cls(Infiltration=0.1)
