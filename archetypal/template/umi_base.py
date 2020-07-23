################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import math
import re
from itertools import chain

import numpy as np

from archetypal import log
from archetypal.idfclass import IDF
from archetypal.utils import lcm


class Unique(type):
    """Metaclass that handles unique class instantiation based on the
    :attr:`Name` attribute of a class.
    """

    def __call__(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        self = cls.__new__(cls, *args, **kwargs)
        cls.__init__(self, *args, **kwargs)
        if self not in CREATED_OBJECTS or kwargs.get("allow_duplicates", "False"):
            CREATED_OBJECTS.append(self)
            return self
        else:
            return next((x for x in CREATED_OBJECTS if x == self), None)

    def __init__(cls, name, bases, attributes):
        """
        Args:
            name:
            bases:
            attributes:
        """
        super().__init__(name, bases, attributes)


def _resolve_combined_names(predecessors):
    """Creates a unique name from the list of :class:`UmiBase` objects
    (predecessors)

    Args:
        predecessors (MetaData):
    """

    # all_names = [obj.Name for obj in predecessors]
    class_ = list(set([obj.__class__.__name__ for obj in predecessors]))[0]

    return "Combined_%s_%s" % (
        class_,
        str(hash((pre.Name for pre in predecessors))).strip("-"),
    )


def _shorten_name(long_name):
    """Check if name is longer than 300 characters, and return truncated version

    Args:
        long_name (str): A long name (300 char+) to shorten.
    """
    if len(long_name) > 300:
        # shorten name if longer than 300 characters (limit set by
        # EnergyPlus)
        return long_name[:148] + (long_name[148:] and " .. ")
    else:
        return long_name


def clear_cache():
    """Clear the dict of created object instances"""
    CREATED_OBJECTS.clear()


class UmiBase(object):
    # dependencies: dict of <dependant value: independant value>
    _dependencies = {"sql": ["idf"]}
    _independant_vars = set(chain(*list(_dependencies.values())))
    _dependant_vars = set(_dependencies.keys())

    def _reset_dependant_vars(self, name):
        _reverse_dependencies = {}
        for k, v in self._dependencies.items():
            for x in v:
                _reverse_dependencies.setdefault(x, []).append(k)
        for var in _reverse_dependencies[name]:
            super().__setattr__(f"_{var}", None)

    def __setattr__(self, key, value):
        propobj = getattr(self.__class__, key, None)
        if isinstance(propobj, property):
            if propobj.fset is None:
                self.__set_on_dependencies(key.strip("_"), value)
            else:
                propobj.fset(self, value)
                self.__set_on_dependencies(key, value)
        else:
            self.__set_on_dependencies(key, value)

    def __set_on_dependencies(self, key, value):
        if key in self._dependant_vars:
            raise AttributeError("Cannot set this value.")
        if key in self._independant_vars:
            self._reset_dependant_vars(key)
            key = f"_{key}"
        super(UmiBase, self).__setattr__(key, value)

    def __init__(
        self,
        Name,
        idf=None,
        Category="Uncategorized",
        Comments="",
        DataSource="",
        **kwargs,
    ):
        """The UmiBase class handles common properties to all Template objects.

        Args:
            Name (str): Unique, the name of the object.
            idf (IDF): The idf object associated to this object.
            Category (str): Group objects by assigning the same category
                identifier. Thies can be any string.
            Comments (str): A comment displayed in the UmiTemplateLibrary.
            DataSource (str): A description of the datasource of the object.
                This helps identify from which data is the current object
                created.
            **kwargs:
        """
        super(UmiBase, self).__init__()
        self.Name = Name
        self._idf = idf
        self._sql = None
        self.Category = Category
        self.Comments = Comments
        if DataSource == "":
            try:
                self.DataSource = self.idf.name
            except:
                self.DataSource = DataSource
        else:
            self.DataSource = DataSource
        self.all_objects = CREATED_OBJECTS
        self.id = kwargs.get("$id", id(self))
        self._predecessors = MetaData()

    def __str__(self):
        """string representation of the object as id:Name"""
        return ":".join([str(self.id), str(self.Name)])

    @property
    def idf(self):
        return self._idf

    @property
    def sql(self):
        if self._sql is None:
            self._sql = self.idf.sql
        return self._sql

    @property
    def predecessors(self):
        """Of which objects is self made of. If from nothing else then self,
        return self.
        """
        if self._predecessors:
            return self._predecessors
        else:
            return MetaData([self])

    def _get_predecessors_meta(self, other):
        """get predecessor objects to self and other

        Args:
            other (UmiBase): The other object.
        """
        predecessors = self.predecessors + other.predecessors
        meta = {
            "Name": _resolve_combined_names(predecessors),
            "Comments": (
                "Object composed of a combination of these "
                "objects:\n{}".format(
                    "\n- ".join(set(obj.Name for obj in predecessors))
                )
            ),
            "Category": ", ".join(set([obj.Category for obj in predecessors])),
            "DataSource": ", ".join(set([obj.DataSource for obj in predecessors])),
        }

        return meta

    def combine(self):
        pass

    def rename(self, name):
        """renames self as well as the cached object

        Args:
            name (str): the name.
        """
        self.Name = name

    def to_json(self):
        """Convert class properties to dict"""
        return {"$id": "{}".format(self.id), "Name": "{}".format(UniqueName(self.Name))}

    @classmethod
    def get_classref(cls, ref):
        return next(
            iter([value for value in CREATED_OBJECTS if value.id == ref["$ref"]]), None
        )

    def get_ref(self, ref):
        """Gets item matching ref id

        Args:
            ref:
        """
        return next(
            iter([value for value in self.all_objects if value.id == ref["$ref"]]), None
        )

    def __hash__(self):
        return hash((self.__class__.mro()[0].__name__, self.Name))

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}

    def _float_mean(self, other, attr, weights=None):
        """Calculates the average attribute value of two floats. Can provide
        weights.

        Args:
            other (UmiBase): The other UmiBase object to calculate average value
                with.
            attr (str): The attribute of the UmiBase object.
            weights (iterable, optional): Weights of [self, other] to calculate
                weighted average.
        """
        if getattr(self, attr) is None:
            return getattr(other, attr)
        if getattr(other, attr) is None:
            return getattr(self, attr)
        # If weights is a list of zeros
        if not np.array(weights).any():
            weights = [1, 1]

        if not isinstance(self.__dict__[attr], list) and not isinstance(
            other.__dict__[attr], list
        ):
            if math.isnan(self.__dict__[attr]):
                return other.__dict__[attr]
            elif math.isnan(other.__dict__[attr]):
                return self.__dict__[attr]
            elif math.isnan(self.__dict__[attr]) and math.isnan(other.__dict__[attr]):
                raise ValueError("Both values for self and other are Not A Number.")
            else:
                return np.average(
                    [self.__dict__[attr], other.__dict__[attr]], weights=weights
                )
        elif self.__dict__[attr] is None and other.__dict__[attr] is None:
            return None
        else:
            # handle arrays by finding the least common multiple of the two arrays and
            # tiling to the full length; then, apply average
            self_attr_ = np.array(self.__dict__[attr])
            other_attr_ = np.array(other.__dict__[attr])
            l_ = lcm(len(self_attr_), len(other_attr_))
            self_attr_ = np.tile(self_attr_, int(l_ / len(self_attr_)))
            other_attr_ = np.tile(other_attr_, int(l_ / len(other_attr_)))
            return np.average([self_attr_, other_attr_], weights=weights, axis=0)

    def _str_mean(self, other, attr, append=False):
        """Returns the combined string attributes

        Args:
            other (UmiBase): The other UmiBase object to calculate combined
                string.
            attr (str): The attribute of the UmiBase object.
            append (bool): Whether or not the attributes should be combined
                together. If False, the attribute of self will is used (other is
                ignored).
        """
        if self is None:
            return other
        if other is None:
            return self
        # if self has info, but other is none, use self
        if self.__dict__[attr] is not None and other.__dict__[attr] is None:
            return self.__dict__[attr]
        # if self is none, but other is not none, use other
        elif self.__dict__[attr] is None and other.__dict__[attr] is not None:
            return other.__dict__[attr]
        # if both are not note, impose self
        elif self.__dict__[attr] and other.__dict__[attr]:
            if append:
                return self.__dict__[attr] + other.__dict__[attr]
            else:
                return self.__dict__[attr]
        # if both are None, return None
        else:
            return None

    def __iadd__(self, other):
        """Overload += to implement self.extend.

        Args:
            other:
        """
        return UmiBase.extend(self, other)

    def extend(self, other):
        """Append other to self. Modify and return self.

        Args:
            other (UmiBase):

        Returns:
            UmiBase: self
        """
        if self is None:
            return other
        if other is None:
            return self
        self.all_objects.pop(self.__hash__())
        id = self.id
        new_obj = self.combine(other)
        new_obj.__dict__.pop("id")
        new_obj.id = id
        name = new_obj.__dict__.pop("Name")
        self.__dict__.update(Name=name, **new_obj.__dict__)
        self.all_objects[self.__hash__()] = self
        return self

    def validate(self):
        """Validates UmiObjects and fills in missing values"""
        return self

    def mapping(self):
        pass


class MaterialBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of materials

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life-cycle-impact
    """

    def __init__(
        self,
        Name,
        Cost=0,
        EmbodiedCarbon=0,
        EmbodiedEnergy=0,
        SubstitutionTimestep=100,
        TransportCarbon=0,
        TransportDistance=0,
        TransportEnergy=0,
        SubstitutionRatePattern=None,
        Conductivity=2.4,
        Density=2400,
        **kwargs,
    ):
        """Initialize a MaterialBase object with parameters:

        Args:
            Name (str): Name of the Material.
            Cost (float): The purchase cost of the material by volume ($/m3).
            EmbodiedCarbon (float): Represents the GHG emissions through the
                lifetime of the product (kgCO2/kg).
            EmbodiedEnergy (float): Represents all fuel consumption ( Typically
                from non-renewable sources) which happened through the lifetime
                of a product (or building), expressed as primary energy (MJ/kg).
            SubstitutionTimestep (float): The duration in years of a period of
                replacement (e.g. There will be interventions in this material
                type every 10 years).
            TransportCarbon (float): The impacts associated with the transport
                by km of distance and kg of material (kgCO2/kg/km).
            TransportDistance (float): The average distance in km from the
                manufacturing site to the building construction site
            TransportEnergy (float): The impacts associated with the transport
                by km of distance and kg of material (MJ/kg/km).
            SubstitutionRatePattern (list-like): A ratio from 0 to 1 which
                defines the amount of the material replaced at the end of each
                period of replacement, :attr:`SubstitutionTimestep` (e.g. Every
                10 years this cladding will be completely replaced with ratio
                1). Notice that you can define different replacement ratios for
                different consecutive periods, introducing them separated by
                commas. For example, if you introduce the series “0.1 , 0.1 , 1”
                after the first 10 years a 10% will be replaced, then after 20
                years another 10%, then after 30 years a 100%, and finally the
                series would start again in year 40.
            Conductivity (float): Thermal conductivity (W/m-K).
            Density (float): A number representing the density of the material
                in kg/m3. This is essentially the mass of one cubic meter of the
                material.
            **kwargs: Keywords passed to the :class:`UmiBase` class. See
                :class:`UmiBase` for more details.
        """
        super(MaterialBase, self).__init__(Name, **kwargs)
        if SubstitutionRatePattern is None:
            SubstitutionRatePattern = [1.0]
        self.Conductivity = Conductivity
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name))

    def __eq__(self, other):
        if not isinstance(other, MaterialBase):
            return False
        else:
            return all(
                [
                    self.Cost == other.Cost,
                    self.EmbodiedCarbon == other.EmbodiedCarbon,
                    self.EmbodiedEnergy == other.EmbodiedEnergy,
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                    self.TransportCarbon == other.TransportCarbon,
                    self.TransportDistance == other.TransportDistance,
                    self.TransportEnergy == other.TransportEnergy,
                    self.SubstitutionRatePattern == other.SubstitutionRatePattern,
                    self.Conductivity == other.Conductivity,
                    self.Density == other.Density,
                ]
            )

    def validate(self):
        """Validates UmiObjects and fills in missing values"""
        return self


CREATED_OBJECTS = []


class MaterialLayer(object):
    """Class used to define one layer in a construction assembly. This class has
    two attributes:

    1. Material (:class:`OpaqueMaterial` or :class:`GlazingMaterial` or
       :class:`GasMaterial`): the material object for this layer.
    2. Thickness (float): The thickness of the material in the layer.
    """

    def __init__(self, Material, Thickness):
        """Initialize a MaterialLayer object with parameters:

        Args:
            Material (OpaqueMaterial, GlazingMaterial, GasMaterial):
            Thickness (float): The thickness of the material in the
                construction.
        """
        if Thickness < 0.003:
            log(
                "Modeling layers thinner (less) than 0.003 m is not "
                "recommended; rather, add those properties to one of the "
                'adjacent layers. Layer "%s"' % Material.Name,
                lg.WARNING,
            )
        self.Thickness = Thickness
        self.Material = Material

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        if not isinstance(other, MaterialLayer):
            return False
        else:
            return all(
                [self.Thickness == other.Thickness, self.Material == other.Material]
            )

    def __repr__(self):
        return "{} with thickness of {:,.3f} m".format(self.Material, self.Thickness)

    @property
    def r_value(self):
        """float: The Thermal Resistance of the :class:`MaterialLayer`"""
        return self.Thickness / self.Material.Conductivity  # (K⋅m2/W)

    @property
    def u_value(self):
        """float: The overall heat transfer coefficient of the
        :class:`MaterialLayer`. Expressed in W/(m2⋅K)
        """
        return 1 / self.r_value

    @property
    def heat_capacity(self):
        """float: The Material Layer's heat capacity J/m2-k"""
        return self.Material.Density * self.Material.SpecificHeat * self.Thickness

    @property
    def specific_heat(self):
        """float: The Material's specific heat J/kg-K"""
        return self.Material.SpecificHeat

    def to_dict(self):
        return collections.OrderedDict(
            Material={"$ref": str(self.Material.id)}, Thickness=self.Thickness
        )

    def mapping(self):
        return dict(Material=self.Material, Thickness=self.Thickness)


class MetaData(collections.UserList):
    """Handles data of combined objects such as Name, Comments and other."""

    @property
    def Name(self):
        return "+".join([obj.Name for obj in self])

    @property
    def comments(self):
        return "Object composed of a combination of these objects:\n{}".format(
            set(obj.Name for obj in self)
        )


def load_json_objects(datastore, idf=None):
    """
    Args:
        datastore:
    """
    from archetypal import (
        GasMaterial,
        GlazingMaterial,
        OpaqueMaterial,
        OpaqueConstruction,
        WindowConstruction,
        StructureInformation,
        DaySchedule,
        WeekSchedule,
        YearSchedule,
        DomesticHotWaterSetting,
        VentilationSetting,
        ZoneConditioning,
        ZoneConstructionSet,
        ZoneLoad,
        ZoneDefinition,
        BuildingTemplate,
    )

    if not idf:
        idf = IDF(prep_outputs=False)
    loading_json_list = []
    loading_json_list.append(
        [GasMaterial.from_dict(**store, idf=idf) for store in datastore["GasMaterials"]]
    )
    loading_json_list.append(
        [GlazingMaterial(**store, idf=idf) for store in datastore["GlazingMaterials"]]
    )
    loading_json_list.append(
        [OpaqueMaterial(**store, idf=idf) for store in datastore["OpaqueMaterials"]]
    )
    loading_json_list.append(
        [
            OpaqueConstruction.from_dict(**store, idf=idf)
            for store in datastore["OpaqueConstructions"]
        ]
    )
    loading_json_list.append(
        [
            WindowConstruction.from_dict(**store, idf=idf)
            for store in datastore["WindowConstructions"]
        ]
    )
    loading_json_list.append(
        [
            StructureInformation.from_dict(**store, idf=idf)
            for store in datastore["StructureDefinitions"]
        ]
    )
    loading_json_list.append(
        [DaySchedule.from_dict(**store, idf=idf) for store in datastore["DaySchedules"]]
    )
    loading_json_list.append(
        [
            WeekSchedule.from_dict(**store, idf=idf)
            for store in datastore["WeekSchedules"]
        ]
    )
    loading_json_list.append(
        [
            YearSchedule.from_dict(**store, idf=idf)
            for store in datastore["YearSchedules"]
        ]
    )
    loading_json_list.append(
        [
            DomesticHotWaterSetting.from_dict(**store, idf=idf)
            for store in datastore["DomesticHotWaterSettings"]
        ]
    )
    loading_json_list.append(
        [
            VentilationSetting.from_dict(**store, idf=idf)
            for store in datastore["VentilationSettings"]
        ]
    )
    loading_json_list.append(
        [
            ZoneConditioning.from_dict(**store, idf=idf)
            for store in datastore["ZoneConditionings"]
        ]
    )
    loading_json_list.append(
        [
            ZoneConstructionSet.from_dict(**store, idf=idf)
            for store in datastore["ZoneConstructionSets"]
        ]
    )
    loading_json_list.append(
        [ZoneLoad.from_dict(**store, idf=idf) for store in datastore["ZoneLoads"]]
    )
    loading_json_list.append(
        [ZoneDefinition.from_dict(**store, idf=idf) for store in datastore["Zones"]]
    )
    loading_json_list.append(
        [
            BuildingTemplate.from_dict(**store, idf=idf)
            for store in datastore["BuildingTemplates"]
        ]
    )
    return loading_json_list


class UniqueName(str):
    """Handles the attribution of user defined names for :class:`UmiBase`, and
    makes sure they are unique.
    """

    existing = {}  # a dict to store the created names

    def __new__(cls, content):
        """Pick a name. Will increment the name if already used"""
        return str.__new__(cls, cls.create_unique(content))

    @classmethod
    def create_unique(cls, name):
        """Check if name has already been used. If so, try to increment until
        not used

        Args:
            name:
        """
        if not name:
            return None
        match = re.match(r"^(.*?)(\D*)(\d+)$", name)
        if match:
            groups = list(match.groups())
            groups[-1] = int(groups[-1])
            groups[-1] += 1
            key = "".join(map(str, groups))
        else:
            key = name

        if key not in cls.existing:
            cls.existing[key] = 0
        else:
            cls.existing[key] += 1
            key = key + str(cls.existing[key])
        return key
