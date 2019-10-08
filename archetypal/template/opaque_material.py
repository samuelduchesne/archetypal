################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal import log
from archetypal.template import UmiBase, Unique


class OpaqueMaterial(UmiBase, metaclass=Unique):
    """Use this component to create a custom opaque material.

    .. image:: ../images/template/materials-opaque.png
    """

    def __init__(
        self,
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
        **kwargs
    ):
        """A custom opaque material.

        Args:
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
                the thermal abstorptance of the material. The default is set to
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
        super(OpaqueMaterial, self).__init__(**kwargs)

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

        self._thickness = kwargs.get("Thickness", None)

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueMaterial):
        """
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name))

    def __eq__(self, other):
        if not isinstance(other, OpaqueMaterial):
            return False
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
                    self.SubstitutionRatePattern == other.SubstitutionRatePattern,
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                ]
            )

    @classmethod
    def generic(cls):
        """generic plaster board"""
        return cls(
            Conductivity=1.39,
            SpecificHeat=1085,
            Density=2000,
            Name="generic_plaster_board",
        )

    def combine(self, other, weights=None):
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
            )
        )
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
        data_dict["Roughness"] = self.Roughness
        data_dict["SolarAbsorptance"] = self.SolarAbsorptance
        data_dict["SpecificHeat"] = self.SpecificHeat
        data_dict["ThermalEmittance"] = self.ThermalEmittance
        data_dict["VisibleAbsorptance"] = self.VisibleAbsorptance
        data_dict["Conductivity"] = self.Conductivity
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = self.Density
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
        data_dict["Name"] = self.Name

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
                **kwargs
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
                **kwargs
            )
        elif epbunch.key.upper() == "MATERIAL:AIRGAP":

            Name = epbunch.Name
            Conductivity = 0.02436  # W/mK, dry air at 0 °C and 100 kPa.
            Density = 1.2754  # dry air at 0 °C and 100 kPa.
            SpecificHeat = 100.5  # J/kg-K, dry air at 0 °C and 100 kPa.
            Thickness = Conductivity * epbunch.Thermal_Resistance
            Roughness = "Smooth"
            return cls(
                Conductivity=Conductivity,
                Roughness=Roughness,
                SpecificHeat=SpecificHeat,
                Thickness=Thickness,
                Density=Density,
                Name=Name,
                SolarAbsorptance=0,
                ThermalEmittance=0,
                VisibleAbsorptance=0,
                idf=epbunch.theidf,
                **kwargs
            )
        else:
            raise NotImplementedError(
                "Material '{}' of type '{}' is not yet "
                "supported. Please contact package "
                "authors".format(epbunch.Name, epbunch.key)
            )
