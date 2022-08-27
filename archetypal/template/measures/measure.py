"""Energy measures modules."""
import functools
import logging

from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.building_template import BuildingTemplate
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
    """

    def __init__(self, Name, object_address, validator=None, transformer=None):
        self._name = Name # Names are not mutable
        assert callable(object_address) or isinstance(object_address, list), "Object address must be a function, list"
        self._object_address = object_address
        # TODO: make getters and setters for validator and transformer
        if callable(validator):
            self._validator = validator 
        elif validator is not None:
            raise ValueError("Provided 'validator' arg is not callable.")
        if callable(transformer): 
            self._transformer = transformer
        elif transformer is not None:
            raise ValueError("Provided 'transformer' arg is not callable.")
    
    def __repr__(self):
        return f"{self.Name}:{self._object_address}"
    
    def __str__(self):
        """string representation of the object as Name:address"""
        return self.__repr__()

    def __hash__(self):
        return hash(self.__repr__())
    
    def __eq__(self, other):
        return self._object_address == other._object_address

    @property
    def Name(self):
        return self._name
    
    @property
    def is_dynamic(self):
        return callable(self._object_address)
    
    def determine_full_address(self, building_template):
        """Determine the full mutation path for the action in a given building template

        Args:
            building_template: the building template to find the path in 
        """

        return (
            self._object_address(building_template)
            if self.is_dynamic
            else self._object_address
        )

    def determine_parameter_name(self, building_template):
        """Determine the parameter name to mutate for the action in a given building template

        Args:
            building_template: the building template to find the path in 
        """
        path = self.determine_full_address(building_template)
        return path[-1]

    def determine_object_address(self, building_template):
        """Determine the path to the object to mutate for the action in a given building template

        Args:
            building_template: the building template to find the path in 
        """

        path = self.determine_full_address(building_template)
        path = path.copy()
        path.pop()
        return path


    def lookup_original_value(self, building_template):
        """Find the current value of the target parameter in a given building template

        Args:
            building_template: the building template to find the parameter value in
        """
        return get_path(
            root=building_template,
            address=self.determine_full_address(building_template),
        )

    def lookup_original_object(self, building_template):
        """Find the object to mutate in a given building template

        Args:
            building_template: the building template to find the object in
        """
        return get_path(
            root=building_template,
            address=self.determine_object_address(building_template)
        )
    
    def compute_new_value(self, building_template, proposed_transformer_value, *args, **kwargs):
        """Return a proposed new value for the target parameter in a building template

        Args:
            building_template: the building template to validate a change in
            proposed_transformer_value: the input to the transformer which generates a new value
        """
        original_value = self.lookup_original_value(building_template)
        new_value = self._transformer(original_value, proposed_transformer_value, *args, **kwargs) if hasattr(self, "_transformer") else proposed_transformer_value
        return new_value

    def _validate(self, building_template, new_value):
        """Validate a proposed change to a building template and return the new value

        Args:
            building_template: the building template to validate a change in
            new_value: the new value for the target parameter
        """

        original_value = self.lookup_original_value(building_template)
        return self._validator(
                original_value=original_value,
                new_value=new_value,
                root=building_template,
            ) if hasattr(self, "_validator") else True

    def mutate(self, building_template, proposed_transformer_value, *args, **kwargs):
        new_value = self.compute_new_value(building_template, proposed_transformer_value, *args, **kwargs)
        validated = self._validate(building_template, new_value)
        if validated:
            address = self.determine_full_address(building_template)
            set_path(
                root=building_template,
                address=address,
                value=new_value
            )


class MeasureProperty:
    """Class for controlling multiple actions with a single property value"""

    def __init__(self, Name, AttrName, Description, Default, transformer=None, validator=None, actions=None):
        assert isinstance(Name, str)
        self._name = Name 
        assert isinstance(AttrName, str) and AttrName.isidentifier()
        self._attr_name = AttrName
        self._description = Description 
        self._default = Default
        self._transformer = transformer
        self._validator = validator

        if isinstance(actions, MeasureAction):
            actions = [actions] 
        self._actions = set()
        for action in actions or []:
            self.add_action(action)

        self._value = Default
    
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
        return self._validator

    @Validator.setter
    def Validator(self, validator):
        # TODO: Validate that the validator has the correct shape:
        # lambda root, original_value, new_value: boolean
        assert callable(validator), "The provided validator is not callable"
        self._validator = validator
        for action in self._actions:
            action._validator = validator

    @property
    def Transformer(self):
        return self._transformer

    @Transformer.setter
    def Transformer(self, transformer):
        # TODO: Validate that the transformer has the correct shape:
        # lambda original_value, proposed_transformer_value, *args, **kwargs: boolean
        assert callable(transformer), "The provided validator is not callable"
        self._transformer = transformer
        for action in self._actions:
            action._transformer = transformer


    def add_action(self, action):
        """Add an action which will be controlled by this property

        Args:
            action (MeasureAction): the action to add
        """
        assert isinstance(action, MeasureAction)
        if self.Validator and not hasattr(action, "_validator"):
            action._validator = self.Validator
        if self.Transformer and not hasattr(action, "_transformer"):
            print(f"adding a transformer to a an action {action}")
            action._transformer = self.Transformer
        self._actions.add(action)
    
    def lookup_objects_to_mutate(self, building_template):
        """Lookup all objects which will be mutated by this property

        Args:
            building_template: the template to identify all mutation targets in
        """
        objects_to_mutate = {} # store the objects to mutate and the path to find it at
        for action in self._actions:
            object_to_mutate = action.lookup_original_object(building_template)
            object_address = action.determine_object_address(building_template)
            full_path = action.determine_full_address(building_template)
            if object_to_mutate not in objects_to_mutate:
                objects_to_mutate[object_to_mutate] = []
            objects_to_mutate[object_to_mutate].append({"path": full_path, "object_address": object_address})
        return objects_to_mutate
    
    def mutate(self, building_template):
        for action in self._actions:
            action.mutate(building_template=building_template, proposed_transformer_value=self.Value)
    
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
    

class Measure(object):
    """Main class for the definition of measures.

    Args:
        Name (str): The name of the measure.
        Description (str): A description of the measure.
        Properties (list<MeasureProperty>): Initial properties that are part of the measure
    """

    # TODO: Add methods for adding measures together, extending with more properties, etc
    # TODO: abstract inheritance classes into presets objects
    __slots__ = (
        "_name",
        "_description",
        "_properties",
    )

    def __init__(self, Name="Measure", Description="Upgrade Templates", Properties=[]):
        # TODO: Get multi-class and nested inheritance working
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

    def _get_property_by_name(self, name):
        """find a MeasureProperty object by Name"""
        prop = next(
            iter(
                    (
                        x
                        for x in self._properties
                        if x.Name == name
                    )
            ),
            None,
        )
        return prop

    def _get_property_by_attr_name(self, attr_name):
        """find a MeasureProperty object by AttrName"""
        prop = next(
            iter(
                    (
                        x
                        for x in self._properties
                        if x.AttrName == attr_name
                    )
            ),
            None,
        )
        return prop

    def __setitem__(self, name, value):
        """Change a MeasureProperty's value using the property's Name"""
        prop = self._get_property_by_name(name)
        assert isinstance(prop, MeasureProperty), f"Measure:{self.Name} does not have a property named '{name}'"
        prop.Value = value

    def __getitem__(self, name):
        """Get a MeasureProperty's value using the property's Name"""
        prop = self._get_property_by_name(name)
        assert isinstance(prop, MeasureProperty), f"Measure:{self.Name} does not have a property named '{name}'"
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

    def add_property(self, prop):
        """Add a property to a measure
        
        Args:
            prop (MeasureProperty): The property to add
        """
        assert isinstance(prop, MeasureProperty)
        assert prop.Name not in [_prop.Name for _prop in self._properties], f"Measure {self} already has a property with the Name {prop.Name}"
        assert prop.AttrName not in [_prop.AttrName for _prop in self._properties], f"Measure {self} already has a property with the AttrName {prop.AttrName}"
        self._properties.add(prop)
    
    def lookup_objects_to_mutate(self, building_template):
        """Returns a dict of objects which will be mutated by this measure, 
        with objects as keys and the path data about the mutations as values.
        Useful for disentanglement before mutation

        Args:
            building_template: the building template to determine mutations in
        """
        measure_objects_to_mutate = {}
        for prop in self._properties:
            prop_objects_to_mutate = prop.lookup_objects_to_mutate(building_template)
            for object_to_mutate, addresses in prop_objects_to_mutate.items():
                if object_to_mutate not in measure_objects_to_mutate:
                    measure_objects_to_mutate[object_to_mutate] = []
                measure_objects_to_mutate[object_to_mutate].extend(addresses)
        return measure_objects_to_mutate

    def mutate(self, target, disentangle=True, *args, **kwargs):
        """Mutate a template or a whole library 
        
        Args:
            target (BuildingTemplate | UmiTemplateLibrary): The template or library to upgrade
            disentangle (boolean): If true, the tree of each upgraded object will be duplicated and replaced before mutation
        """
        if isinstance(target, BuildingTemplate):
            self.mutate_template(target, disentangle=disentangle, *args, **kwargs)
        elif isinstance(target, UmiTemplateLibrary):
            self.mutate_library(target, disentangle=disentangle, *args, **kwargs)

    def mutate_template(self, building_template, disentangle=True, *args, **kwargs):
        """Mutate a template 
        
        Args:
            target (BuildingTemplate): The template to upgrade
        """
        assert isinstance(building_template, BuildingTemplate), "'building_template' argument must be a BuildingTemplate"
        if disentangle:
            # Every object which gets mutated is given an entirely new tree to separate it 
            # from other templates which may have used the objects or even other objects 
            # within the same template which may use it
            objects_to_mutate = self.lookup_objects_to_mutate(building_template)
            for metadatas in objects_to_mutate.values():
                for metadata in metadatas:
                    object_address = metadata["object_address"]
                    for i in range(1, len(object_address)+1):
                        address = object_address[0:i]
                        original_object = get_path(root=building_template, address=address)
                        new_object = original_object.duplicate() if hasattr(original_object, "duplicate") else original_object.copy()
                        set_path(root=building_template, address=address, value=new_object)

        for prop in self._properties:
            prop.mutate(building_template, *args, **kwargs)
    
    def mutate_library(self, library, disentangle=True, *args, **kwargs):
        """Mutate a library

        Args:
            target (UmiTemplateLibrary): The library to upgrade
        """
        assert isinstance(library, UmiTemplateLibrary), "'library' argument must be an UmiTemplateLibrary"
        for bt in library.BuildingTemplates:
            self.mutate(bt, disentangle=disentangle, *args, **kwargs)
    
    # TODO: write changelog functions

class SetMechanicalVentilation(Measure):
    """Set the Mechanical Ventilation."""

    _name="Set Mechanical Ventilation", 
    _description="Change mechanical ventilation rates and schedules", 

    def __init__(self, VentilationACH=3.5, VentilationSchedule=None, **kwargs):
        """Initialize measure with parameters."""
        super(SetMechanicalVentilation, self).__init__(
            **kwargs,
        )

        # Configure Ventilation ACH Property and actions
        ventilation_ach_property = MeasureProperty(
            Name="Ventilation ACH",
            AttrName="ventilation_ach",
            Description="Set Ventilation ACH",
            Default=VentilationACH,
        )
        ventilation_ach_property.add_action(MeasureAction(
            Name="Set Perimeter Ventilation ACH",
            object_address=["Perimeter", "Ventilation", "ScheduledVentilationAch"],
        ))
        ventilation_ach_property.add_action(MeasureAction(
            Name="Set Core Ventilation ACH",
            object_address=["Core", "Ventilation", "ScheduledVentilationAch"],
        ))

        # Configure Ventilation boolean actions
        ventilation_boolean_property = MeasureProperty(
            Name="Is Ventilation",
            AttrName="is_ventilation_on",
            Description="Automatically turn on scheduled ventilation",
            Default=True,
        )
        ventilation_boolean_property.add_action(MeasureAction(
            Name="Set Perimeter Ventilation Toggle",
            object_address=["Perimeter", "Ventilation", "IsScheduledVentilationOn"],
        ))
        ventilation_boolean_property.add_action(MeasureAction(
            Name="Set Core Ventilation ACH",
            object_address=["Core", "Ventilation", "IsScheduledVentilationOn"],
        ))
        
        # Configure schedule actions
        if VentilationSchedule:
            ventilation_schedule_property = MeasureProperty(
                Name="Ventilation Schedule",
                AttrName="ventilation_schedule",
                Description="Set Ventilation Schedule",
                Default=VentilationSchedule
            )
            ventilation_schedule_property.add_action(MeasureAction(
                Name="Set Perimeter Ventilation Schedule",
                object_address=["Perimeter", "Ventilation", "ScheduledVentilationSchedule"],
            ))
            ventilation_schedule_property.add_action(MeasureAction(
                Name="Set Core Ventilation Schedule",
                object_address=["Core", "Ventilation", "ScheduledVentilationSchedule"],
            ))

        # Add properties to measure
        self.add_property(ventilation_ach_property)
        self.add_property(ventilation_boolean_property)
        if ventilation_schedule_property:
            self.add_property(ventilation_schedule_property)


class SetCOP(Measure):
    """Set the COPs."""

    _name="Set HVAC CoP", 
    _description="Set heating and cooling coefficients of performance", 

    def __init__(self, CoolingCoP=3.5, HeatingCoP=1, **kwargs):
        """Initialize measure with parameters."""
        super(SetCOP, self).__init__(
            **kwargs
        )

        # Configure Heating Property and Actions
        heating_property = MeasureProperty(
            Name="Heating CoP",
            AttrName="HeatingCoP",
            Description="Set Heating Coefficient of Performance",
            Default=HeatingCoP,
        )
        heating_property.add_action(MeasureAction(
            Name="Set Perimeter Heating CoP",
            object_address=["Perimeter", "Conditioning", "HeatingCoeffOfPerf"],
        ))
        heating_property.add_action(MeasureAction(
            Name="Set Core Core Heating CoP",
            object_address=["Core", "Conditioning", "HeatingCoeffOfPerf"],
        ))

        # Configure Cooling Property and Actions
        cooling_property = MeasureProperty(
            Name="Cooling CoP",
            AttrName="CoolingCoP",
            Description="Set Cooling Coefficient of Performance",
            Default=CoolingCoP,
        )
        cooling_property.add_action(MeasureAction(
            Name="Set Perimeter Cooling CoP",
            object_address=["Perimeter", "Conditioning", "CoolingCoeffOfPerf"],
        ))
        cooling_property.add_action(MeasureAction(
            Name="Set Core Core Cooling CoP",
            object_address=["Core", "Conditioning", "CoolingCoeffOfPerf"],
        ))

        # Add properties to measure
        self.add_property(heating_property)
        self.add_property(cooling_property)
        


class SetElectricLoadsEfficiency(Measure):
    """The EnergyStarUpgrade changes the equipment power density too."""

    _name="Electric Loads Efficiency",
    _description="Change equipment and lighting loads efficiency",

    def __init__(self, LightingPowerDensity=8.07, EquipmentPowerDensity=8.07, **kwargs):
        """Initialize measure with parameters."""
        super(SetElectricLoadsEfficiency, self).__init__(
            **kwargs
        )
        
        # Configure Equipment Properties and Actions
        equipment_property = MeasureProperty(
            Name="Equipment Power Density", 
            AttrName="EquipmentPowerDensity", 
            Description="Change Equipment Power Density", 
            Default=EquipmentPowerDensity, 
        )
        equipment_property.add_action(MeasureAction(
            Name="Change Perimeter Equipment Power Density", 
            object_address=["Perimeter", "Loads", "EquipmentPowerDensity"]
        ))
        equipment_property.add_action(MeasureAction(
            Name="Change Core Equipment Power Density", 
            object_address=["Core", "Loads", "EquipmentPowerDensity"]
        ))

        # Configure Lighting Properties and Actions
        lighting_property = MeasureProperty(
            Name="Lighting Power Density", 
            AttrName="LightingPowerDensity", 
            Description="Change Lighting Power Density", 
            Default=LightingPowerDensity,
        )
        lighting_property.add_action(MeasureAction(
            Name="Change Perimeter Lighting Power Density", 
            object_address=["Perimeter", "Loads", "LightingPowerDensity"]
        ))
        lighting_property.add_action(MeasureAction(
            Name="Change Core Lighting Power Density", 
            object_address=["Core", "Loads", "LightingPowerDensity"]
        ))

        # Add properties to measure
        self.add_property(equipment_property)
        self.add_property(lighting_property)


class SetFacadeInsulationThermalResistance(Measure):

    _name = "Facade Upgrade (Insulation Only)"
    _description = "Upgrade roof and facade insulation by specifying R-Values for the Insulation Layers."

    def __init__(self, RoofRValue=5.02, FacadeRValue=3.08, **kwargs):
        super(SetFacadeInsulationThermalResistance, self).__init__(
            **kwargs
        )

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
        facade_insulation_property.add_action(MeasureAction(
            Name="Change Facade Insualtion Layer R-Value",
            object_address=get_facade_insulation_layer_path
        ))
        self.add_property(facade_insulation_property)

        roof_insulation_property = MeasureProperty(
            Name="Roof Insulation R-Value",
            AttrName="RoofRValue",
            Description="Set roof insulation layer R-Value",
            Default=RoofRValue,
        )
        roof_insulation_property.add_action(MeasureAction(
            Name="Change Roof Insualtion Layer R-Value",
            object_address=get_roof_insulation_layer_path
        ))
        self.add_property(roof_insulation_property)

    @classmethod
    def Best(cls):
        return cls(
            FacadeRValue = 1 / 0.13, 
            RoofRValue = 1 / 0.11, 
            Name="Facade Upgrade Best",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Mid(cls):
        return cls(
            FacadeRValue = 1 / 0.34, 
            RoofRValue = 1 / 0.33, 
            Name="Facade Upgrade Mid",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Regular(cls):
        return cls(
            FacadeRValue = 1 / 1.66, 
            RoofRValue = 1 / 2.37, 
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Low(cls):
        return cls(
            FacadeRValue = 1 / 3.5, 
            RoofRValue = 1 / 4.5, 
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

class SetFacadeThermalResistance(Measure):

    _name = "Facade Upgrade"
    _description = "Upgrade roof and facade insulation by specifying R-Values for entire assemblies."

    def __init__(self, RoofRValue, FacadeRValue, **kwargs):


        super(SetFacadeThermalResistance, self).__init__(
            **kwargs
        )
        roof_property = MeasureProperty(
            Name="Roof R-Value",
            AttrName="RoofRValue",
            Description="R-value for entire roof assembly",
            Default=RoofRValue,
        )
        roof_property.add_action(MeasureAction(
            Name="Change Roof R-Value",
            object_address=["Perimeter", "Constructions", "Roof", "r_value"]
        ))
        facade_property = MeasureProperty(
            Name="Facade R-Value",
            AttrName="FacadeRValue",
            Description="R-value for entire facade assembly",
            Default=FacadeRValue,
        )
        facade_property.add_action(MeasureAction(
            Name="Change Facade R-Value",
            object_address=["Perimeter", "Constructions", "Facade", "r_value"]
        ))

        self.add_property(roof_property)
        self.add_property(facade_property)

    @classmethod
    def Best(cls):
        return cls(
            FacadeRValue = 15, 
            RoofRValue = 10, 
            Name="Facade Upgrade Best",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Mid(cls):
        return cls(
            FacadeRValue = 10, 
            RoofRValue = 10, 
            Name="Facade Upgrade Mid",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Regular(cls):
        return cls(
            FacadeRValue = 2, 
            RoofRValue = 2, 
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )

    @classmethod
    def Low(cls):
        return cls(
            FacadeRValue = 1, 
            RoofRValue = 1, 
            Name="Facade Upgrade Regular",
            Description="Set R-Value of roof and facade using values from climaplusbeta.com",
        )


class SetInfiltration(Measure):

    _name="Set Infiltration",
    _description="This measure sets the infiltration ACH of the perimeter zone.",

    def __init__(self, Infiltration=0.6, **kwargs):
        infiltration_action = MeasureAction(
            Name="Set Infiltration ACH",
            object_address=["Perimeter", "Ventilation", "Infiltration"],
            **kwargs,
        )
        infiltration_property=MeasureProperty(
            Name="Infiltration",
            AttrName="Infiltration",
            Description="Set Infiltration ACH",
            Default=Infiltration,
            actions=infiltration_action,
        )

        super().__init__(
            Properties=infiltration_property
        )

    @classmethod
    def Regular(cls):
        return cls(
            Infiltration = 0.6
        )

    @classmethod
    def Medium(cls):
        return cls(
            Infiltration = 0.3
        )

    @classmethod
    def Tight(cls):
        return cls(
            Infiltration = 0.1
        )