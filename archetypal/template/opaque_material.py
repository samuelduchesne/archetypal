################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

import numpy as np
from sigfig import round

from archetypal import log
from archetypal.template import UmiBase, UniqueName


class OpaqueMaterial(UmiBase):
    """Use this component to create a custom opaque material.

    .. image:: ../images/template/materials-opaque.png
    """

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
        """A custom opaque material.

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
            Cost: # todo: define parameter
            Density (float): A number representing the density of the material
                in kg/m3. This is essentially the mass of one cubic meter of the
                material.
            MoistureDiffusionResistance: # todo: defined parameter
            EmbodiedCarbon: # todo: define parameter
            EmbodiedEnergy: # todo: define parameter
            TransportCarbon: # todo: define parameter
            TransportDistance: # todo: define parameter
            TransportEnergy: # todo: define parameter
            SubstitutionRatePattern: # todo: define parameter
            SubstitutionTimestep: # todo: define parameter
            **kwargs:
        """
        super(OpaqueMaterial, self).__init__(Name, **kwargs)

        if SubstitutionRatePattern is None:
            SubstitutionRatePattern = [0.5, 1]
        self.Conductivity = Conductivity
        self.Roughness = Roughness
        self.SolarAbsorptance = SolarAbsorptance
        self.SpecificHeat = SpecificHeat
        self.ThermalEmittance = ThermalEmittance
        self.VisibleAbsorptance = VisibleAbsorptance
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.MoistureDiffusionResistance = MoistureDiffusionResistance

    @property
    def ThermalEmittance(self):
        return float(self._thermal_emittance)

    @ThermalEmittance.setter
    def ThermalEmittance(self, value):
        try:
            value = float(value)
        except ValueError:
            value = 0.9  # Use default
        finally:
            if 9.9999e-6 < value <= 1:
                self._thermal_emittance = value
            else:
                raise ValueError(
                    f"Out of range value Numeric Field (ThermalEmittance), "
                    f"value={value}, "
                    "range={>9.9999E-6 and <=1}, "
                    f"in MATERIAL={self.Name}"
                )

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueMaterial):
        """
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
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

    @classmethod
    def generic(cls, idf=None):
        """generic plaster board"""
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
            idf=idf,
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

    def to_json(self):
        """Convert class properties to dict"""
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
    def from_epbunch(cls, epbunch, **kwargs):
        """Create an OpaqueMaterial from an IDF "Material", "Material:NoMAss",
        or "Material:AirGap" element.

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
            # do MATERIAL
            Name = epbunch.Name
            Conductivity = epbunch.Conductivity
            Density = epbunch.Density
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            SpecificHeat = epbunch.Specific_Heat
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            Thickness = epbunch.Thickness
            return cls(
                Conductivity=Conductivity,
                Density=Density,
                Roughness=Roughness,
                SolarAbsorptance=SolarAbsorptance,
                SpecificHeat=SpecificHeat,
                ThermalEmittance=ThermalEmittance,
                VisibleAbsorptance=VisibleAbsorptance,
                Thickness=Thickness,
                Name=Name,
                idf=epbunch.theidf,
                **kwargs,
            )
        elif epbunch.key.upper() == "MATERIAL:NOMASS":
            # do MATERIAL:NOMASS. Assume properties of air.
            Name = epbunch.Name
            Conductivity = 0.02436  # W/mK, dry air at 0 °C and 100 kPa.
            Density = 1.2754  # dry air at 0 °C and 100 kPa.
            SpecificHeat = 100.5  # J/kg-K, dry air at 0 °C and 100 kPa.
            Thickness = Conductivity * epbunch.Thermal_Resistance
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            return cls(
                Conductivity=Conductivity,
                Density=Density,
                Roughness=Roughness,
                SolarAbsorptance=SolarAbsorptance,
                SpecificHeat=SpecificHeat,
                ThermalEmittance=ThermalEmittance,
                VisibleAbsorptance=VisibleAbsorptance,
                Thickness=Thickness,
                Name=Name,
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
        """Validate object and fill in missing values."""

        # Some OpaqueMaterial don't have a default value, therefore an empty string is
        # parsed. This breaks the UmiTemplate Editor, therefore we set a value on these
        # attributes (if necessary) in this validation step.

        if getattr(self, "SolarAbsorptance") == "":
            setattr(self, "SolarAbsorptance", 0.7)
        if getattr(self, "ThermalEmittance") == "":
            setattr(self, "ThermalEmittance", 0.9)
        if getattr(self, "VisibleAbsorptance") == "":
            setattr(self, "VisibleAbsorptance", 0.7)
        return self

    def mapping(self):
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

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in OpaqueMaterial.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )
