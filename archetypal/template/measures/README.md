# UMI Measures Module

UMI `Measures` provide a convenient way to apply technology packages to Archetypal `BuildingTemplates`.  For instance, to upgrade the HVAC system efficiency, it's as easy as the following:

```
from archetypal import UmiTemplateLibrary
from archetypal.template.measures.measure import SetCOP

lib = UmiTemplateLibrary.open("/path/to/your/lib.json")

measure = SetCOP(HeatingCoP=4, CoolingCoP=3.25)

measure.mutate(lib)

```

### Changing Property Values

You may change the values of each MeasureProperty at any time.  You may use either bracket notation and the desired `MeasureProperty`'s `Name` to change the value, or dot notation and the `MeasureProperty`'s `AttrName`.
```
# Change a MeasureProperty's value using bracket notation and the Property's Name
measure["Heating CoP"] = 3.0 

# Apply measure to the entire library
measure.mutate(lib)

# Change a measure Property's value using dot notation and the Property's AttrName
measure.HeatingCoP = 3.2 

# Only apply the measure to a single template
measure.mutate(lib.BuildingTemplates[0]) 
```

### Entanglement

By default, when you apply a measure, it will duplicate and replace the tree of any objects which are mutated so that the mutation does not ripple out to other parents of the targeted object.  

For instance, consider a measure which only upgrades the Perimeter Loads Equipment Power Density but not the Core. If a single ZoneDefinition is used for the Core and Perimeter, or separate definitions are used but they both use the same ZoneLoad object, the Perimeter ZoneDefinition and ZoneLoads objects will be duplicated and replaced to prevent propoagating the Perimeter changes to the core.  

This behavior is enabled by default, but if you wish to preserve the entanglement and allow the knock-on effects to propagate, simply set `disentangle=False` when mutating the library:

```
measure.mutate(lib, disentangle=False)
```

### Changelogs

The changes executed by a measure are returneed as a changelog by each call to mutate an `UmiTemplateLibrary` or `BuildingTemplate`.  The log is formatted as a dict, with `BuildingTemplate`s as keys, and tuples of `(address, original_value, new_value)` as values:

```
changelog = measure.mutate(lib)
```

You can also generate a changelog of pending changes without mutating the target by using the `changelog` method.  

```
changelog = measure.changelog(lib)
```

# What is a Measure

An UMI `Measure`  is defined by a collection of `MeasureProperties`, which each define a set of `MeasureActions` to mutate a `BuildingTemplate`.  `Measures` can be composed into new `Measures` which combine several other` Measures`, and each` MeasureProperty` or `MeasureAction` may have `Validators` associated with it (e.g. to only allow upgrades to be applied if certain conditions are met).  Each `MeasureProperty` or `MeasureAction` may also have a `Transformer` associated with it, which allows the new values applied by an upgrade to depend on the current state of the `BuildingTemplate` (see [Advanced Usage](#advanced-usage)).  Archetypal comes with several pre-defined measures, but the `Measure` class makes it easy to define your own.

# Defining a Measure
To define a measure, create a Measure object, at least one MeasureProperty, and at least one MeasureAction associated with that property.  Each MeasureProperty represets a control variable, and the value of the Property will be passed to each of the MeasureActions associated with it when the measure's upgrade is used to mutate the library.  Once you've defined your Actions and Properties, you will associate them and connect them to the Measure: 

```
from archetypal.template.measures.measure import Measure, MeasureProperty, MeasureAction

measure = Measure(
	Name="Set Heating Setpoint",
    Description="Change HVAC heating setpoints to reduce heating loads",
)

heating_property = MeasureProperty(
    Name="Heating Setpoint",
    AttrName="HeatingSetpoint",
    Description="Change the heating setpoint",
    Default=17,
)

heating_core_action = MeasureAction(
    Name="Change Core Heating Setpoint",
    Lookup=["Core", "Conditioning", "HeatingSetpoint"],
)

heating_perimeter_action = MeasureAction(
    Name="Change Perimeter Heating Setpoint",
    Lookup=["Perimeter", "Conditioning", "HeatingSetpoint"],
)

# Add actions to the heating_property
heating_property.add_action(heating_perimeter_action)
heating_property.add_action(heating_core_action)

# Add the heating_property to the measure
measure.add_property(heating_property)

# Apply the measure to the whole library
measure.mutate(your_library) 

```

Although the measure above only uses one property, you may use arbitrarily many properties in a Measure, potentially allowing you to define large-scale macros for upgrading a template library.

You may also create your properties and actions in the reverse order, and pass them in during object creation.  The following is equivalent to the snippet above:

```
from archetypal.template.measures.measure import Measure, MeasureProperty, MeasureAction

heating_core_action = MeasureAction(
    Name="Change Core Heating Setpoint",
    Lookup=["Core", "Conditioning", "HeatingSetpoint"],
)

heating_perimeter_action = MeasureAction(
    Name="Change Perimeter Heating Setpoint",
    Lookup=["Perimeter", "Conditioning", "HeatingSetpoint"],
)

heating_property = MeasureProperty(
    Name="Heating Setpoint",
    AttrName="HeatingSetpoint",
    Description="Change the heating setpoint",
    Default=17,
    Actions=[heating_core_action, heating_perimeter_action]
)

measure = Measure(
	Name="Set Heating Setpoint",
    Description="Change HVAC heating setpoints to reduce heating loads",
    Properties=[heating_property]
)
```

## Action Creator Syntactic Sugar
If a MeasureProperty only uses one Action, you may define it inline with the MeasureProperty as a shortcut, and the action will be internally created and associated with the property automatically:

```
infiltration_ach_property = MeasureProperty(
    Name="Infiltration",
    AttrName="Infiltration",
    Description="Change Infiltration ACH",
    Default=0.2,
    Lookup=["Perimeter", "Ventilation", "Infiltration"],
)

measure = Measure(
    Name="Upgrade Tightness",
    Description="Change the infiltration airchange frequency of the perimeter zone.",
    Properties=infiltration_ach_property # You may pass in a list or a single property
)
```

## Extending a Measure

You may also add `MeasureProperties` to `Measures` at any time after their initial creation, or similarly `MeasureActions` to` MeasureProperties`, so they are easily extensible.

```
cop_and_infiltration_measure = SetCOP()
cop_and_ventilation_measure.add_property(
    Name="Infiltration",
    AttrName="Infiltration",
    Description="Change perimeter infiltration ach",
    Default=0.2,
    Lookup=["Perimeter", "Ventilation", "Infiltration"]
)
```

# Measure Presets

Some of Archetypal's predfined Measure subclasses may come with presets defined as classmethods, for instance `SetInfiltration`:

```
measure = SetInfiltration.Best()
measure.mutate(your_library)
```

See the documentation for the predfined Measure subclasses for a list of available presets.

# Combining Measures

Existing Measure subclasses can be easily combined using class inheritance:
```
class SetCOPandInfiltration(SetCOP, SetInfiltration):
    HeatingCoP = 3.75
    CoolingCoP = 3.5
    Infiltration = 0.2

measure = SetCoPAndInfiltration()
measure.mutate(lib)
```
If you omit a `MeasureProperty` from the subclass definition, the default value from the original measure will be used.

You can also easily combine measure instances using addition, e.g.:

```
measure_c = measure_a + measure_b
```

or

```
measure_a += measure_b
```
# Subclassing Measure

You may easily define Measure your own `Measure` subclasses to preserve or share your custom measures.  Inherit `Measure`, call provide a `_name` and `_description` class arg, and then define your measure in `__init__`.  `__init__` should accept `**kwargs` and should provide default values for the properties it uses by their `AttrNames`. the See the following example:

```
class SetHVACSetpoint(Measure):
    _name = "Set HVAC Setpoints"
    _description = "Set heating and cooling setpoints for all zones

    def __init__(self, HeatingSetpoint=18, CoolingSetpoing=24, **kwargs):
        super().__init__(**kwargs)

        heating_property = MeasureProperty(
            Name="Heating Setpoint",
            AttrName="HeatingSetpoint",
            Description="Change the heating setpoint in deg. c.",
            Default=HeatingSetpoint,
            Lookup=["Perimeter", "Conditioning", "HeatingSetpoint"]
        )
        heating_property.add_action(
            Name="Change core heating setpoint in deg. c."
            Lookup=["Core", "Conditioning", "HeatingSetpoint]
        )
        self.add_property(heating_property)

        cooling_property = MeasureProperty(
            Name="Cooling Setpoint",
            AttrName="CoolingSetpoint",
            Description="Change the cooling setpoint in deg. c.",
            Default=CoolingSetpoint,
            Lookup=["Perimeter", "Conditioning", "CoolingSetpoint"]
        )
        cooling_property.add_action(
            Name="Change core cooling setpoint in deg. c."
            Lookup=["Core", "Conditioning", "CoolingSetpoint]
        )
        self.add_property(cooling_property)
```
## Defining Measure Subclass Presets

Given an existing `Measure` subclass, you may define a preset (i.e. a collections of values for each Property) with two different techniques.

### Option 1: Classmethods

Add one `classmethod` for each preset which returns an instance of the `Measure` subclass with `MeasureProperty` values set as desired, e.g.:

```
class SetHVACSetpoints(Measure):

    ...

    @classmethod
    def Extreme(cls):
        return cls(
            HeatingSetpoint=15,
            CoolingSetpoint=27
        )
```

Then, instantiate a preset by calling the `classmethod`:

```
measure = SetHVACSetpoints.Extreme()
```

### Option 2: Inheritance Presets

Create a subclass for each preset which inherits the desired measure, and set the `MeasureProperty` values using class attrs.  No need for an `__init__` method!  See here:

```
class ExtremeSetpoints(SetHVACSetpoints):
    HeatingSetpoint = 15
    CoolingSetpoint = 15

measure = ExtremeSetpoints()
```

This technique is especially convenient when combining multiple measures into a single measure (see [Combining Measures](#combining-measures) )

# Advanced Usage

TODO: Document `Validators`, `Transformers`, and dynamic `Lookup`.



