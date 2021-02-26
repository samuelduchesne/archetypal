################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import itertools
import logging as lg
import math
import re
from itertools import chain

import numpy as np
from sigfig import round

from archetypal import IDF, log
from archetypal.utils import lcm


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


class UmiBase(object):
    # dependencies: dict of <dependant value: independant value>
    _dependencies = {"sql": ["idf"]}
    _independant_vars = set(chain(*list(_dependencies.values())))
    _dependant_vars = set(_dependencies.keys())
    CREATED_OBJECTS = []
    _ids = itertools.count(0)  # unique id for each class instance

    def _reset_dependant_vars(self, name):
        _reverse_dependencies = {}
        for k, v in self._dependencies.items():
            for x in v:
                _reverse_dependencies.setdefault(x, []).append(k)
        for var in _reverse_dependencies[name]:
            super().__setattr__(f"_{var}", None)

    def __setattr__(self, key, value):
        propobj = getattr(UmiBase, key, None)
        if isinstance(propobj, property):
            if propobj.fset is None:
                raise AttributeError("Cannot set attribute")
                # self.__set_on_dependencies(key.strip("_"), value)
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
        DataSource=None,
        allow_duplicates=False,
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
            allow_duplicates (bool): If True, this object can be equal to another one
                if it has a different name.
            **kwargs:
        """
        self._datasource = None
        self._predecessors = None
        self._idf = None
        self._sql = None
        self._id = None

        self.Name = Name
        self.idf = idf
        self.Category = Category
        self.Comments = Comments
        self.DataSource = DataSource
        self.id = kwargs.get("$id", None)
        self._allow_duplicates = allow_duplicates
        self.unit_number = next(self._ids)

        UmiBase.CREATED_OBJECTS.append(self)

    def __repr__(self):
        return ":".join([str(self.id), str(self.Name)])

    def __str__(self):
        """string representation of the object as id:Name"""
        return self.__repr__()

    def __iter__(self):
        for attr, value in self.mapping().items():
            yield attr, value

    @property
    def id(self):
        if self._id is None:
            self._id = id(self)
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def DataSource(self):
        return self._datasource

    @DataSource.setter
    def DataSource(self, value):
        self._datasource = value

    @property
    def idf(self):
        if self._idf is None:
            self._idf = IDF()
        return self._idf

    @idf.setter
    def idf(self, value):
        self._idf = value

    @property
    def sql(self):
        if self._sql is None:
            self._sql = self.idf.sql()
        return self._sql

    @property
    def predecessors(self):
        """Of which objects is self made of. If from nothing else then self,
        return self.
        """
        if self._predecessors is None:
            self._predecessors = MetaData([self])
        return self._predecessors

    def _get_predecessors_meta(self, other):
        """get predecessor objects to self and other

        Args:
            other (UmiBase): The other object.
        """
        predecessors = self.predecessors + other.predecessors
        meta = self.combine_meta(predecessors)

        return meta

    def combine_meta(self, predecessors):
        return {
            "Name": _resolve_combined_names(predecessors),
            "Comments": (
                "Object composed of a combination of these "
                "objects:\n{}".format(
                    "\n- ".join(set(obj.Name for obj in predecessors))
                )
            ),
            "Category": ", ".join(
                set(
                    itertools.chain(*[obj.Category.split(", ") for obj in predecessors])
                )
            ),
            "DataSource": ", ".join(
                set(
                    itertools.chain(
                        *[
                            obj.DataSource.split(", ")
                            for obj in predecessors
                            if obj.DataSource is not None
                        ]
                    )
                )
            ),
        }

    def combine(self, other, allow_duplicates=False):
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
            iter(
                [value for value in UmiBase.CREATED_OBJECTS if value.id == ref["$ref"]]
            ),
            None,
        )

    def get_ref(self, ref):
        pass

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

        if not isinstance(getattr(self, attr), list) and not isinstance(
            getattr(other, attr), list
        ):
            if math.isnan(getattr(self, attr)):
                return getattr(other, attr)
            elif math.isnan(getattr(other, attr)):
                return getattr(self, attr)
            elif math.isnan(getattr(self, attr)) and math.isnan(getattr(other, attr)):
                raise ValueError("Both values for self and other are Not A Number.")
            else:
                return float(
                    np.average(
                        [getattr(self, attr), getattr(other, attr)], weights=weights
                    )
                )
        elif getattr(self, attr) is None and getattr(other, attr) is None:
            return None
        else:
            # handle arrays by finding the least common multiple of the two arrays and
            # tiling to the full length; then, apply average
            self_attr_ = np.array(getattr(self, attr))
            other_attr_ = np.array(getattr(other, attr))
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
        if getattr(self, attr) is not None and getattr(other, attr) is None:
            return getattr(self, attr)
        # if self is none, but other is not none, use other
        elif getattr(self, attr) is None and getattr(other, attr) is not None:
            return getattr(other, attr)
        # if both are not note, impose self
        elif getattr(self, attr) and getattr(other, attr):
            if append:
                return getattr(self, attr) + getattr(other, attr)
            else:
                return getattr(self, attr)
        # if both are None, return None
        else:
            return None

    def __iadd__(self, other):
        """Overload += to implement self.extend.

        Args:
            other:
        """
        return UmiBase.extend(self, other, allow_duplicates=True)

    def extend(self, other, allow_duplicates):
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
        self.CREATED_OBJECTS.remove(self)
        id = self.id
        new_obj = self.combine(other, allow_duplicates=allow_duplicates)
        new_obj.id = id
        self.__dict__.update(**new_obj.__dict__)
        self.CREATED_OBJECTS.append(self)
        return self

    def validate(self):
        """Validate UmiObjects and fills in missing values."""
        return self

    def mapping(self):
        return {}

    def get_unique(self):
        """Return first object matching equality in the list of instantiated objects."""
        if self._allow_duplicates:
            # We want to return the first similar object (equality) that has this name.
            obj = next(
                iter(
                    sorted(
                        (
                            x
                            for x in UmiBase.CREATED_OBJECTS
                            if x == self
                            and x.Name == self.Name
                            and type(x) == type(self)
                        ),
                        key=lambda x: x.unit_number,
                    )
                ),
                self,
            )
        else:
            # We want to return the first similar object (equality) regardless of the
            # name.
            obj = next(
                iter(
                    sorted(
                        (
                            x
                            for x in UmiBase.CREATED_OBJECTS
                            if x == self and type(x) == type(self)
                        ),
                        key=lambda x: x.unit_number,
                    )
                ),
                self,
            )

        return obj


class MaterialBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of materials

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life
    -cycle-impact
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
        Conductivity=0,
        Density=0,
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
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        if not isinstance(other, MaterialBase):
            return NotImplemented
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
                    np.array_equal(
                        self.SubstitutionRatePattern, other.SubstitutionRatePattern
                    ),
                    self.Conductivity == other.Conductivity,
                    self.Density == other.Density,
                ]
            )

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in MaterialBase.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


class MaterialLayer(object):
    """Class used to define one layer in a construction assembly. This class has
    two attributes:

    1. Material (:class:`OpaqueMaterial` or :class:`GlazingMaterial` or
       :class:`GasMaterial`): the material object for this layer.
    2. Thickness (float): The thickness of the material in the layer.
    """

    def __init__(self, Material, Thickness, **kwargs):
        """Initialize a MaterialLayer object with parameters:

        Args:
            Material (OpaqueMaterial, GlazingMaterial, GasMaterial):
            Thickness (float): The thickness of the material in the
                construction.
        """
        self.Material = Material
        self.Thickness = Thickness

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        if not isinstance(other, MaterialLayer):
            return NotImplemented
        else:
            return all(
                [self.Thickness == other.Thickness, self.Material == other.Material]
            )

    def __repr__(self):
        return "{} with thickness of {:,.3f} m".format(self.Material, self.Thickness)

    def __iter__(self):
        for k, v in self.mapping().items():
            yield k, v

    @property
    def Thickness(self):
        return self._thickness

    @Thickness.setter
    def Thickness(self, value):
        self._thickness = value
        if value < 0.003:
            log(
                "Modeling layer thinner (less) than 0.003 m (not recommended) for "
                f"MaterialLayer '{self}'",
                lg.WARNING,
            )

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
            Material={"$ref": str(self.Material.id)},
            Thickness=round(self.Thickness, decimals=3),
        )

    def mapping(self):
        return dict(Material=self.Material, Thickness=self.Thickness)

    def get_unique(self):
        return self


from collections.abc import Hashable, MutableSet


class UserSet(Hashable, MutableSet):
    __hash__ = MutableSet._hash

    def __init__(self, iterable=()):
        self.data = set(iterable)

    def __contains__(self, value):
        return value in self.data

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return repr(self.data)

    def __add__(self, other):
        self.data.update(other.data)
        return self

    def update(self, other):
        self.data.update(other.data)
        return self

    def add(self, item):
        self.data.add(item)

    def discard(self, item):
        self.data.discard(item)


class MetaData(UserSet):
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
    from archetypal.template import (
        BuildingTemplate,
        DaySchedule,
        DomesticHotWaterSetting,
        GasMaterial,
        GlazingMaterial,
        OpaqueConstruction,
        OpaqueMaterial,
        StructureInformation,
        VentilationSetting,
        WeekSchedule,
        WindowConstruction,
        WindowSetting,
        YearSchedule,
        ZoneConditioning,
        ZoneConstructionSet,
        ZoneDefinition,
        ZoneLoad,
    )

    if not idf:
        idf = IDF(prep_outputs=False)
    t = dict(
        # with datastore, create each objects
        GasMaterials=[
            GasMaterial.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["GasMaterials"]
        ],
        GlazingMaterials=[
            GlazingMaterial(**store, idf=idf, allow_duplicates=True)
            for store in datastore["GlazingMaterials"]
        ],
        OpaqueMaterials=[
            OpaqueMaterial(**store, idf=idf, allow_duplicates=True)
            for store in datastore["OpaqueMaterials"]
        ],
        OpaqueConstructions=[
            OpaqueConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["OpaqueConstructions"]
        ],
        WindowConstructions=[
            WindowConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["WindowConstructions"]
        ],
        StructureDefinitions=[
            StructureInformation.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["StructureDefinitions"]
        ],
        DaySchedules=[
            DaySchedule.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["DaySchedules"]
        ],
        WeekSchedules=[
            WeekSchedule.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["WeekSchedules"]
        ],
        YearSchedules=[
            YearSchedule.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["YearSchedules"]
        ],
        DomesticHotWaterSettings=[
            DomesticHotWaterSetting.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["DomesticHotWaterSettings"]
        ],
        VentilationSettings=[
            VentilationSetting.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["VentilationSettings"]
        ],
        ZoneConditionings=[
            ZoneConditioning.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneConditionings"]
        ],
        ZoneConstructionSets=[
            ZoneConstructionSet.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneConstructionSets"]
        ],
        ZoneLoads=[
            ZoneLoad.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneLoads"]
        ],
        Zones=[
            ZoneDefinition.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["Zones"]
        ],
        WindowSettings=[
            WindowSetting.from_ref(
                store["$ref"], datastore["BuildingTemplates"], idf=idf
            )
            if "$ref" in store
            else WindowSetting.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["WindowSettings"]
        ],
        BuildingTemplates=[
            BuildingTemplate.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["BuildingTemplates"]
        ],
    )
    return t


class UniqueName(str):
    """Handles the attribution of user defined names for :class:`UmiBase`, and
    makes sure they are unique.
    """

    existing = set()

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
        if name not in cls.existing:
            cls.existing.add(name)
            return name
        else:
            match = re.match(r"^(.*?)(\D*)(\d+)$", name)
            if match:
                groups = list(match.groups())
                pad = len(groups[-1])
                groups[-1] = int(groups[-1])
                groups[-1] += 1
                groups[-1] = str(groups[-1]).zfill(pad)
                name = "".join(map(str, groups))
                return cls.create_unique(name)
            else:
                return cls.create_unique(name + "_1")
