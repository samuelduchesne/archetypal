"""archetypal OpaqueMaterial."""

import collections

import numpy as np
from sigfig import round
from validator_collection import validators

from archetypal.template.materials.material_base import MaterialBase
from archetypal.template.umi_base import UniqueName
from archetypal.utils import log


class OpaqueMaterial(MaterialBase):
    """Use this component to create a custom opaque material.

    .. image:: ../images/template/materials-opaque.png
    """

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
        "_specific_heat",
        "_thermal_emittance",
        "_visible_absorptance",
        "_moisture_diffusion_resistance",
    )

    def __init__(
        self,
        Name,
        Conductivity,
        SpecificHeat,
        SolarAbsorptance=0.7,
        ThermalEmittance=0.9,
        VisibleAbsorptance=0.7,
        Roughness="Rough",
        Cost=0,
        Density=1,
        MoistureDiffusionResistance=50,
        EmbodiedCarbon=0.45,
        EmbodiedEnergy=0,
        TransportCarbon=0,
        TransportDistance=0,
        TransportEnergy=0,
        SubstitutionRatePattern=None,
        SubstitutionTimestep=20,
        **kwargs,
    ):
        """Initialize an opaque material.

        Args:
            Name (str): The name of the material.
            Conductivity (float): A number representing the conductivity of the
                material in W/m-K. This is essentially the heat flow in Watts
                across one meter thick of the material when the temperature
                difference on either side is 1 Kelvin. Modeling layers with
                conductivity higher than 5.0 W/(m-K) is not recommended.
            SpecificHeat (float): A number representing the specific heat
                capacity of the material in J/kg-K. This is essentially the
                number of joules needed to raise one kg of the material by 1
                degree Kelvin. Only values of specific heat of 100 or larger are
                allowed. Typical ranges are from 800 to 2000 J/(kg-K).
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
            Density (float): A number representing the density of the material
                in kg/m3. This is essentially the mass of one cubic meter of the
                material.
            MoistureDiffusionResistance (float): the factor by which the vapor
                diffusion in the material is impeded, as compared to diffusion in
                stagnant air [%].
            **kwargs: keywords passed to parent constructors.
        """
        super(OpaqueMaterial, self).__init__(
            Name,
            Conductivity=Conductivity,
            Cost=Cost,
            Density=Density,
            EmbodiedCarbon=EmbodiedCarbon,
            EmbodiedEnergy=EmbodiedEnergy,
            TransportCarbon=TransportCarbon,
            TransportDistance=TransportDistance,
            TransportEnergy=TransportEnergy,
            SubstitutionRatePattern=SubstitutionRatePattern,
            SubstitutionTimestep=SubstitutionTimestep,
            **kwargs,
        )

        self.Roughness = Roughness
        self.SolarAbsorptance = SolarAbsorptance
        self.SpecificHeat = SpecificHeat
        self.ThermalEmittance = ThermalEmittance
        self.VisibleAbsorptance = VisibleAbsorptance
        self.MoistureDiffusionResistance = MoistureDiffusionResistance

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
    def SpecificHeat(self):
        """Get or set the specific heat of the material [J/(kg-K)]."""
        return self._specific_heat

    @SpecificHeat.setter
    def SpecificHeat(self, value):
        self._specific_heat = validators.float(value, minimum=100)

    @property
    def ThermalEmittance(self):
        """Get or set the thermal emittance of the material [-]."""
        return self._thermal_emittance

    @ThermalEmittance.setter
    def ThermalEmittance(self, value):
        self._thermal_emittance = validators.float(value, minimum=0, maximum=1)

    @property
    def VisibleAbsorptance(self):
        """Get or set the visible absorptance of the material [-]."""
        return self._visible_absorptance

    @VisibleAbsorptance.setter
    def VisibleAbsorptance(self, value):
        self._visible_absorptance = validators.float(
            value, minimum=0, maximum=1, allow_empty=True
        )

    @property
    def MoistureDiffusionResistance(self):
        """Get or set the vapor resistance factor of the material [%]."""
        return self._moisture_diffusion_resistance

    @MoistureDiffusionResistance.setter
    def MoistureDiffusionResistance(self, value):
        self._moisture_diffusion_resistance = validators.float(value, minimum=0)

    @classmethod
    def generic(cls, **kwargs):
        """Return a generic material based on properties of plaster board.

        Args:
            **kwargs: keywords passed to UmiBase constructor.
        """
        return cls(
            Conductivity=0.16,
            SpecificHeat=1090,
            Density=800,
            Name="GP01 GYPSUM",
            Roughness="Smooth",
            SolarAbsorptance=0.7,
            ThermalEmittance=0.9,
            VisibleAbsorptance=0.5,
            DataSource="ASHRAE 90.1-2007",
            MoistureDiffusionResistance=8.3,
            **kwargs,
        )

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
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        if not weights:
            log(
                'using OpaqueMaterial density as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [self.Density, other.Density]

        meta = self._get_predecessors_meta(other)
        new_obj = OpaqueMaterial(
            **meta,
            Conductivity=self._float_mean(other, "Conductivity", weights),
            Roughness=self._str_mean(other, attr="Roughness", append=False),
            SolarAbsorptance=self._float_mean(other, "SolarAbsorptance", weights),
            SpecificHeat=self._float_mean(other, "SpecificHeat"),
            ThermalEmittance=self._float_mean(other, "ThermalEmittance", weights),
            VisibleAbsorptance=self._float_mean(other, "VisibleAbsorptance", weights),
            TransportCarbon=self._float_mean(other, "TransportCarbon", weights),
            TransportDistance=self._float_mean(other, "TransportDistance", weights),
            TransportEnergy=self._float_mean(other, "TransportEnergy", weights),
            SubstitutionRatePattern=self._float_mean(
                other, "SubstitutionRatePattern", weights=None
            ),
            SubstitutionTimestep=self._float_mean(
                other, "SubstitutionTimestep", weights
            ),
            Cost=self._float_mean(other, "Cost", weights),
            Density=self._float_mean(other, "Density", weights),
            EmbodiedCarbon=self._float_mean(other, "EmbodiedCarbon", weights),
            EmbodiedEnergy=self._float_mean(other, "EmbodiedEnergy", weights),
            MoistureDiffusionResistance=self._float_mean(
                other, "MoistureDiffusionResistance", weights
            ),
            idf=self.idf,
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_ref(self):
        """Return a ref pointer to self."""
        pass

    def to_dict(self):
        """Return OpaqueMaterial dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
        data_dict["Roughness"] = self.Roughness
        data_dict["SolarAbsorptance"] = round(self.SolarAbsorptance, 2)
        data_dict["SpecificHeat"] = round(self.SpecificHeat, 4)
        data_dict["ThermalEmittance"] = round(self.ThermalEmittance, 2)
        data_dict["VisibleAbsorptance"] = round(self.VisibleAbsorptance, 2)
        data_dict["Conductivity"] = round(self.Conductivity, 3)
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = round(self.Density, 4)
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create an OpaqueMaterial from a dictionary.

        Args:
            data (dict): The python dictionary.
            **kwargs: keywords passed to MaterialBase constructor.

        .. code-block:: python

            {
                "$id": "1",
                "MoistureDiffusionResistance": 50.0,
                "Roughness": "Rough",
                "SolarAbsorptance": 0.7,
                "SpecificHeat": 920.0,
                "ThermalEmittance": 0.9,
                "VisibleAbsorptance": 0.7,
                "Conductivity": 0.85,
                "Cost": 0.0,
                "Density": 2000,
                "EmbodiedCarbon": 0.45,
                "EmbodiedEnergy": 0.0,
                "SubstitutionRatePattern": [
                 1.0
                ],
                "SubstitutionTimestep": 20.0,
                "TransportCarbon": 0.0,
                "TransportDistance": 0.0,
                "TransportEnergy": 0.0,
                "Category": "Uncategorized",
                "Comments": "",
                "DataSource": null,
                "Name": "Concrete"
            }
        """
        _id = data.pop("$id")
        return cls(id=_id, **data, **kwargs)

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Create an OpaqueMaterial from an EpBunch.

        Note that "Material", "Material:NoMAss" and "Material:AirGap" objects are
        supported.

        Hint:
            (From EnergyPlus Manual): When a user enters such a “no mass”
            material into EnergyPlus, internally the properties of this layer
            are converted to approximate the properties of air (density,
            specific heat, and conductivity) with the thickness adjusted to
            maintain the user’s desired R-Value. This allowed such layers to be
            handled internally in the same way as other layers without any
            additional changes to the code. This solution was deemed accurate
            enough as air has very little thermal mass and it made the coding of
            the state space method simpler.

            For Material:AirGap, a similar strategy is used, with the
            exception that solar properties (solar and visible absorptance and
            emittance) are assumed null.

        Args:
            epbunch (EpBunch): EP-Construction object
            **kwargs:
        """
        if epbunch.key.upper() == "MATERIAL":
            return cls(
                Conductivity=epbunch.Conductivity,
                Density=epbunch.Density,
                Roughness=epbunch.Roughness,
                SolarAbsorptance=epbunch.Solar_Absorptance,
                SpecificHeat=epbunch.Specific_Heat,
                ThermalEmittance=epbunch.Thermal_Absorptance,
                VisibleAbsorptance=epbunch.Visible_Absorptance,
                Name=epbunch.Name,
                idf=epbunch.theidf,
                **kwargs,
            )
        elif epbunch.key.upper() == "MATERIAL:NOMASS":
            # Assume properties of air.
            return cls(
                Conductivity=0.02436,  # W/mK, dry air at 0 °C and 100 kPa
                Density=1.2754,  # dry air at 0 °C and 100 kPa.
                Roughness=epbunch.Roughness,
                SolarAbsorptance=epbunch.Solar_Absorptance,
                SpecificHeat=100.5,  # J/kg-K, dry air at 0 °C and 100 kPa
                ThermalEmittance=epbunch.Thermal_Absorptance,
                VisibleAbsorptance=epbunch.Visible_Absorptance,
                Name=epbunch.Name,
                idf=epbunch.theidf,
                **kwargs,
            )
        elif epbunch.key.upper() == "MATERIAL:AIRGAP":
            gas_prop = {
                "AIR": dict(
                    Conductivity=0.02436,
                    Density=1.754,
                    SpecificHeat=1000,
                    ThermalEmittance=0.001,
                ),
                "ARGON": dict(
                    Conductivity=0.016,
                    Density=1.784,
                    SpecificHeat=1000,
                    ThermalEmittance=0.001,
                ),
                "KRYPTON": dict(
                    Conductivity=0.0088,
                    Density=3.749,
                    SpecificHeat=1000,
                    ThermalEmittance=0.001,
                ),
                "XENON": dict(
                    Conductivity=0.0051,
                    Density=5.761,
                    SpecificHeat=1000,
                    ThermalEmittance=0.001,
                ),
                "SF6": dict(
                    Conductivity=0.001345,
                    Density=6.17,
                    SpecificHeat=1000,
                    ThermalEmittance=0.001,
                ),
            }
            for gasname, properties in gas_prop.items():
                if gasname.lower() in epbunch.Name.lower():
                    thickness = properties["Conductivity"] * epbunch.Thermal_Resistance
                    return cls(
                        Name=epbunch.Name,
                        Thickness=thickness,
                        **properties,
                        idf=epbunch.theidf,
                    )
                else:
                    thickness = (
                        gas_prop["AIR"]["Conductivity"] * epbunch.Thermal_Resistance
                    )
                    return cls(
                        Name=epbunch.Name,
                        Thickness=thickness,
                        **gas_prop["AIR"],
                        idf=epbunch.theidf,
                    )
        else:
            raise NotImplementedError(
                "Material '{}' of type '{}' is not yet "
                "supported. Please contact package "
                "authors".format(epbunch.Name, epbunch.key)
            )

    def validate(self):
        """Validate object and fill in missing values.

        Hint:
            Some OpaqueMaterial don't have a default value, therefore an empty string
            is parsed. This breaks the UmiTemplate Editor, therefore we set a value
            on these attributes (if necessary) in this validation step.
        """
        if getattr(self, "SolarAbsorptance") == "":
            setattr(self, "SolarAbsorptance", 0.7)
        if getattr(self, "ThermalEmittance") == "":
            setattr(self, "ThermalEmittance", 0.9)
        if getattr(self, "VisibleAbsorptance") == "":
            setattr(self, "VisibleAbsorptance", 0.7)
        return self

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        self.validate()

        return dict(
            MoistureDiffusionResistance=self.MoistureDiffusionResistance,
            Roughness=self.Roughness,
            SolarAbsorptance=self.SolarAbsorptance,
            SpecificHeat=self.SpecificHeat,
            ThermalEmittance=self.ThermalEmittance,
            VisibleAbsorptance=self.VisibleAbsorptance,
            Conductivity=self.Conductivity,
            Cost=self.Cost,
            Density=self.Density,
            EmbodiedCarbon=self.EmbodiedCarbon,
            EmbodiedEnergy=self.EmbodiedEnergy,
            SubstitutionRatePattern=self.SubstitutionRatePattern,
            SubstitutionTimestep=self.SubstitutionTimestep,
            TransportCarbon=self.TransportCarbon,
            TransportDistance=self.TransportDistance,
            TransportEnergy=self.TransportEnergy,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

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
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, OpaqueMaterial):
            return NotImplemented
        else:
            return all(
                [
                    self.Conductivity == other.Conductivity,
                    self.SpecificHeat == other.SpecificHeat,
                    self.SolarAbsorptance == other.SolarAbsorptance,
                    self.ThermalEmittance == other.ThermalEmittance,
                    self.VisibleAbsorptance == other.VisibleAbsorptance,
                    self.Roughness == other.Roughness,
                    self.Cost == other.Cost,
                    self.Density == other.Density,
                    self.MoistureDiffusionResistance
                    == self.MoistureDiffusionResistance,
                    self.EmbodiedCarbon == other.EmbodiedCarbon,
                    self.EmbodiedEnergy == other.EmbodiedEnergy,
                    self.TransportCarbon == other.TransportCarbon,
                    self.TransportDistance == other.TransportDistance,
                    self.TransportEnergy == other.TransportEnergy,
                    np.array_equal(
                        self.SubstitutionRatePattern, other.SubstitutionRatePattern
                    ),
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        new_om = self.__class__(**self.mapping())
        return new_om
