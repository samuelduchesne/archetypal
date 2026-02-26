"""archetypal NoMassMaterial."""

from __future__ import annotations

import collections
from typing import TYPE_CHECKING, ClassVar

from sigfig import round
from validator_collection import validators

from archetypal.template import GasMaterial
from archetypal.template.materials.material_base import MaterialBase
from archetypal.utils import log

if TYPE_CHECKING:
    from idfkit import IdfObject


class NoMassMaterial(MaterialBase):
    """Use this component to create a custom no mass material."""

    _CREATED_OBJECTS: ClassVar[list["NoMassMaterial"]] = []

    _ROUGHNESS_TYPES = (
        "VeryRough",
        "Rough",
        "MediumRough",
        "MediumSmooth",
        "Smooth",
        "VerySmooth",
    )

    __slots__ = (
        "_roughness",
        "_solar_absorptance",
        "_thermal_emittance",
        "_visible_absorptance",
        "_moisture_diffusion_resistance",
        "_r_value",
    )

    def __init__(
        self,
        Name,
        RValue,
        SolarAbsorptance=0.7,
        ThermalEmittance=0.9,
        VisibleAbsorptance=0.7,
        Roughness="Rough",
        MoistureDiffusionResistance=50,
        **kwargs,
    ):
        """Initialize an opaque material.

        Args:
            Name (str): The name of the material.
            RValue (float): Number for the R-value of the material [m2-K/W].
            SolarAbsorptance (float): An number between 0 and 1 that represents
                the absorptance of solar radiation by the material. The default
                is set to 0.7, which is common for most non-metallic materials.
            ThermalEmittance (float): An number between 0 and 1 that represents
                the thermal absorptance of the material. The default is set to
                0.9, which is common for most non-metallic materials. For long
                wavelength radiant exchange, thermal emissivity and thermal
                emittance are equal to thermal absorptance.
            VisibleAbsorptance (float): An number between 0 and 1 that
                represents the absorptance of visible light by the material.
                The default is set to 0.7, which is common for most non-metallic
                materials.
            Roughness (str): A text value that indicated the roughness of your
                material. This can be either "VeryRough", "Rough",
                "MediumRough", "MediumSmooth", "Smooth", and "VerySmooth". The
                default is set to "Rough".
            MoistureDiffusionResistance (float): the factor by which the vapor
                diffusion in the material is impeded, as compared to diffusion in
                stagnant air [%].
            **kwargs: keywords passed to parent constructors.
        """
        super().__init__(Name, **kwargs)
        self.r_value = RValue
        self.Roughness = Roughness
        self.SolarAbsorptance = SolarAbsorptance
        self.ThermalEmittance = ThermalEmittance
        self.VisibleAbsorptance = VisibleAbsorptance
        self.MoistureDiffusionResistance = MoistureDiffusionResistance

        # Only at the end append self to _CREATED_OBJECTS
        self._CREATED_OBJECTS.append(self)

    @property
    def r_value(self):
        """Get or set the thermal resistance [m2-K/W]."""
        return self._r_value

    @r_value.setter
    def r_value(self, value):
        self._r_value = validators.float(value, minimum=0)

    @property
    def Roughness(self):
        """Get or set the roughness of the material.

        Hint:
            choices are: "VeryRough", "Rough", "MediumRough", "MediumSmooth", "Smooth",
            "VerySmooth".
        """
        return self._roughness

    @Roughness.setter
    def Roughness(self, value):
        assert value in self._ROUGHNESS_TYPES, (
            f"Invalid value '{value}' for material roughness. Roughness must be one "
            f"of the following:\n{self._ROUGHNESS_TYPES}"
        )
        self._roughness = value

    @property
    def SolarAbsorptance(self):
        """Get or set the solar absorptance of the material [-]."""
        return self._solar_absorptance

    @SolarAbsorptance.setter
    def SolarAbsorptance(self, value):
        self._solar_absorptance = validators.float(value, minimum=0, maximum=1)

    @property
    def ThermalEmittance(self):
        """Get or set the thermal emittance of the material [-]."""
        return self._thermal_emittance

    @ThermalEmittance.setter
    def ThermalEmittance(self, value):
        if value == "" or value is None:
            value = 0.9
        self._thermal_emittance = validators.float(value, minimum=0, maximum=1, allow_empty=True)

    @property
    def VisibleAbsorptance(self):
        """Get or set the visible absorptance of the material [-]."""
        return self._visible_absorptance

    @VisibleAbsorptance.setter
    def VisibleAbsorptance(self, value):
        if value == "" or value is None or value is None:
            value = 0.7
        self._visible_absorptance = validators.float(value, minimum=0, maximum=1, allow_empty=True)

    @property
    def MoistureDiffusionResistance(self):
        """Get or set the vapor resistance factor of the material [%]."""
        return self._moisture_diffusion_resistance

    @MoistureDiffusionResistance.setter
    def MoistureDiffusionResistance(self, value):
        self._moisture_diffusion_resistance = validators.float(value, minimum=0)

    def combine(self, other, weights=None, allow_duplicates=False):
        """Combine two OpaqueMaterial objects.

        Args:
            weights (list-like, optional): A list-like object of len 2. If None,
                the density of the OpaqueMaterial of each objects is used as
                a weighting factor.
            other (OpaqueMaterial): The other OpaqueMaterial object the
                combine with.

        Returns:
            OpaqueMaterial: A new combined object made of self + other.
        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = f"Cannot combine {self.__class__.__name__} with {other.__class__.__name__}"
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        if not weights:
            log(f'using OpaqueMaterial density as weighting factor in "{self.__class__.__name__}" ' "combine.")
            weights = [self.Density, other.Density]

        meta = self._get_predecessors_meta(other)
        new_obj = NoMassMaterial(
            **meta,
            Roughness=self._str_mean(other, attr="Roughness", append=False),
            SolarAbsorptance=self.float_mean(other, "SolarAbsorptance", weights),
            r_value=self.float_mean(other, "r_value", weights),
            ThermalEmittance=self.float_mean(other, "ThermalEmittance", weights),
            VisibleAbsorptance=self.float_mean(other, "VisibleAbsorptance", weights),
            TransportCarbon=self.float_mean(other, "TransportCarbon", weights),
            TransportDistance=self.float_mean(other, "TransportDistance", weights),
            TransportEnergy=self.float_mean(other, "TransportEnergy", weights),
            SubstitutionRatePattern=self.float_mean(other, "SubstitutionRatePattern", weights=None),
            SubstitutionTimestep=self.float_mean(other, "SubstitutionTimestep", weights),
            Cost=self.float_mean(other, "Cost", weights),
            EmbodiedCarbon=self.float_mean(other, "EmbodiedCarbon", weights),
            EmbodiedEnergy=self.float_mean(other, "EmbodiedEnergy", weights),
            MoistureDiffusionResistance=self.float_mean(other, "MoistureDiffusionResistance", weights),
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_dict(self):
        """Return OpaqueMaterial dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
        data_dict["Roughness"] = self.Roughness
        data_dict["SolarAbsorptance"] = round(self.SolarAbsorptance, 2)
        data_dict["ThermalEmittance"] = round(self.ThermalEmittance, 2)
        data_dict["VisibleAbsorptance"] = round(self.VisibleAbsorptance, 2)
        data_dict["RValue"] = round(self.r_value, 3)
        data_dict["Cost"] = self.Cost
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create an NoMassMaterial from a dictionary.

        Args:
            data (dict): The python dictionary.
            **kwargs: keywords passed to MaterialBase constructor.

        .. code-block:: python

            {
                "$id": "140532076832464",
                "Name": "R13LAYER",
                "MoistureDiffusionResistance": 50.0,
                "Roughness": "Rough",
                "SolarAbsorptance": 0.75,
                "ThermalEmittance": 0.9,
                "VisibleAbsorptance": 0.75,
                "RValue": 2.29,
                "Cost": 0.0,
                "EmbodiedCarbon": 0.0,
                "EmbodiedEnergy": 0.0,
                "SubstitutionRatePattern": [1.0],
                "SubstitutionTimestep": 100.0,
                "TransportCarbon": 0.0,
                "TransportDistance": 0.0,
                "TransportEnergy": 0.0,
                "Category": "Uncategorized",
                "Comments": "",
                "DataSource": None,
            }
        """
        _id = data.pop("$id")
        return cls(id=_id, **data, **kwargs)

    @classmethod
    def from_idf_object(cls, obj: IdfObject, **kwargs):
        """Create a NoMassMaterial from an idfkit object.

        Note that "Material", "Material:NoMass" and "Material:AirGap" objects are
        supported.

        Hint:
            (From EnergyPlus Manual): When a user enters such a "no mass"
            material into EnergyPlus, internally the properties of this layer
            are converted to approximate the properties of air (density,
            specific heat, and conductivity) with the thickness adjusted to
            maintain the user's desired R-Value. This allowed such layers to be
            handled internally in the same way as other layers without any
            additional changes to the code. This solution was deemed accurate
            enough as air has very little thermal mass and it made the coding of
            the state space method simpler.

            For Material:AirGap, a similar strategy is used, with the
            exception that solar properties (solar and visible absorptance and
            emittance) are assumed null.

        Args:
            obj: idfkit Material, Material:NoMass, or Material:AirGap object
            **kwargs: Additional keyword arguments passed to constructor
        """
        obj_type = obj.type_name.upper()

        if obj_type == "MATERIAL":
            return cls(
                Conductivity=obj.conductivity,
                Density=obj.density,
                Roughness=obj.roughness,
                SolarAbsorptance=obj.solar_absorptance,
                SpecificHeat=obj.specific_heat,
                ThermalEmittance=obj.thermal_absorptance,
                VisibleAbsorptance=obj.visible_absorptance,
                Name=obj.name,
                **kwargs,
            )
        elif obj_type == "MATERIAL:NOMASS":
            # Assume properties of air.
            return cls(
                Conductivity=0.02436,  # W/mK, dry air at 0 °C and 100 kPa
                Density=1.2754,  # dry air at 0 °C and 100 kPa.
                Roughness=obj.roughness,
                SolarAbsorptance=obj.solar_absorptance,
                SpecificHeat=100.5,  # J/kg-K, dry air at 0 °C and 100 kPa
                ThermalEmittance=obj.thermal_absorptance,
                VisibleAbsorptance=obj.visible_absorptance,
                Name=obj.name,
                **kwargs,
            )
        elif obj_type == "MATERIAL:AIRGAP":
            gas_prop = {
                mat.Name.upper(): mat.mapping() for mat in [GasMaterial(gas_name) for gas_name in GasMaterial._GASTYPES]
            }
            for gasname, properties in gas_prop.items():
                if gasname.lower() in obj.name.lower():
                    thickness = properties["Conductivity"] * obj.thermal_resistance
                    return cls(
                        Name=obj.name,
                        Thickness=thickness,
                        **properties,
                    )
                else:
                    thickness = gas_prop["AIR"]["Conductivity"] * obj.thermal_resistance
                    return cls(
                        Name=obj.name,
                        Thickness=thickness,
                        **gas_prop["AIR"],
                    )
        else:
            raise NotImplementedError(
                f"Material '{obj.name}' of type '{obj.type_name}' is not yet "
                "supported. Please contact package authors"
            )

    def validate(self):
        """Validate object and fill in missing values.

        Hint:
            Some OpaqueMaterial don't have a default value, therefore an empty string
            is parsed. This breaks the UmiTemplate Editor, therefore we set a value
            on these attributes (if necessary) in this validation step.
        """
        if self.SolarAbsorptance == "":
            self.SolarAbsorptance = 0.7
        if self.ThermalEmittance == "":
            self.ThermalEmittance = 0.9
        if self.VisibleAbsorptance == "":
            self.VisibleAbsorptance = 0.7
        return self

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "RValue": self.r_value,
            "MoistureDiffusionResistance": self.MoistureDiffusionResistance,
            "Roughness": self.Roughness,
            "SolarAbsorptance": self.SolarAbsorptance,
            "ThermalEmittance": self.ThermalEmittance,
            "VisibleAbsorptance": self.VisibleAbsorptance,
            "Cost": self.Cost,
            "EmbodiedCarbon": self.EmbodiedCarbon,
            "EmbodiedEnergy": self.EmbodiedEnergy,
            "SubstitutionRatePattern": self.SubstitutionRatePattern,
            "SubstitutionTimestep": self.SubstitutionTimestep,
            "TransportCarbon": self.TransportCarbon,
            "TransportDistance": self.TransportDistance,
            "TransportEnergy": self.TransportEnergy,
            "Category": self.Category,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueMaterial):
        """
        return self.combine(other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, NoMassMaterial):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return (
            self.r_value,
            self.SolarAbsorptance,
            self.ThermalEmittance,
            self.VisibleAbsorptance,
            self.Roughness,
            self.Cost,
            self.MoistureDiffusionResistance,
            self.EmbodiedCarbon,
            self.EmbodiedEnergy,
            self.TransportCarbon,
            self.TransportDistance,
            self.TransportEnergy,
            self.SubstitutionRatePattern,
            self.SubstitutionTimestep,
        )

    def __copy__(self):
        """Create a copy of self."""
        new_om = self.__class__(**self.mapping())
        return new_om
