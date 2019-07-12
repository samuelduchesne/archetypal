################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import UmiBase, Unique


class OpaqueMaterial(UmiBase, metaclass=Unique):
    """Use this component to create a custom opaque material.

    .. image:: ../images/template/materials-opaque.png

    """

    def __init__(self, Conductivity, SpecificHeat, SolarAbsorptance=0.7,
                 ThermalEmittance=0.9, VisibleAbsorptance=0.7,
                 Roughness='Rough', Cost=0, Density=1,
                 MoistureDiffusionResistance=50, EmbodiedCarbon=0.45,
                 EmbodiedEnergy=0, TransportCarbon=0, TransportDistance=0,
                 TransportEnergy=0, SubstitutionRatePattern=[0.5, 1],
                 SubstitutionTimestep=20, **kwargs):
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
                the abstorptance of solar radiation by the material. The default
                is set to 0.7, which is common for most non-metallic materials.
            ThermalEmittance (float): An number between 0 and 1 that represents
                the thermal abstorptance of the material. The default is set to
                0.9, which is common for most non-metallic materials. For long
                wavelength radiant exchange, thermal emissivity and thermal
                emittance are equal to thermal absorptance.
            VisibleAbsorptance (float): An number between 0 and 1 that
                represents the abstorptance of visible light by the material.
                The default is set to 0.7, which is common for most non-metallic
                materials.
            Roughness (str): A text value that indicated the roughness of your
                material. This can be either "VeryRough", "Rough",
                "MediumRough", "MediumSmooth", "Smooth", and "VerySmooth". The
                default is set to "Rough".
            Cost: # todo: defined parameter
            Density: A number representing the density of the material in kg/m3.
                This is essentially the mass of one cubic meter of the material.
            MoistureDiffusionResistance: # todo: defined parameter
            EmbodiedCarbon: # todo: defined parameter
            EmbodiedEnergy: # todo: defined parameter
            TransportCarbon: # todo: defined parameter
            TransportDistance: # todo: defined parameter
            TransportEnergy: # todo: defined parameter
            SubstitutionRatePattern: # todo: defined parameter
            SubstitutionTimestep: # todo: defined parameter
            **kwargs:
        """
        super(OpaqueMaterial, self).__init__(**kwargs)

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

        self._thickness = kwargs.get('Thickness', None)

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueMaterial):
        """
        return self.combine(other)

    def combine(self, other):
        """Append other to self. Return self + other as a new object.

        Args:
            other (OpaqueMaterial): The other OpaqueMaterial object

        Returns:
            OpaqueMaterial: A new combined object made of self + other.
        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self
        name = " + ".join([self.Name, other.Name])
        new_attr = dict(Category=self._str_mean(other, attr='Category',
                                                append=False),
                        Comments=self._str_mean(other, attr='Comments',
                                                append=True),
                        DataSource=self._str_mean(other, attr='DataSource',
                                                  append=False),
                        Conductivity=self._float_mean(other, 'Conductivity'),
                        Roughness=self._str_mean(other, attr='Roughness',
                                                 append=False),
                        SolarAbsorptance=self._float_mean(other,
                                                          'SolarAbsorptance'),
                        SpecificHeat=self._float_mean(other, 'SpecificHeat'),
                        ThermalEmittance=self._float_mean(other,
                                                          'ThermalEmittance'),
                        VisibleAbsorptance=self._float_mean(other,
                                                            'VisibleAbsorptance'),
                        TransportCarbon=self._float_mean(other,
                                                         'TransportCarbon'),
                        TransportDistance=self._float_mean(other,
                                                           'TransportDistance'),
                        TransportEnergy=self._float_mean(other,
                                                         'TransportEnergy'),
                        SubstitutionRatePattern=self._float_mean(other,
                                                                 'SubstitutionRatePattern'),
                        SubstitutionTimestep=self._float_mean(other,
                                                              'SubstitutionTimestep'),
                        Cost=self._float_mean(other, 'Cost'),
                        Density=self._float_mean(other, 'Density'),
                        EmbodiedCarbon=self._float_mean(other,
                                                        'EmbodiedCarbon'),
                        EmbodiedEnergy=self._float_mean(other,
                                                        'EmbodiedEnergy'),
                        MoistureDiffusionResistance=self._float_mean(other,
                                                                     'MoistureDiffusionResistance'))
        new_obj = self.__class__(Name=name, **new_attr)
        return new_obj

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict[
            "MoistureDiffusionResistance"] = self.MoistureDiffusionResistance
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
    def from_idf(cls, idf, *args, **kwargs):
        """
        Args:
            idf:
            *args:
            **kwargs:
        """
        all_ = []
        all_.extend(idf.idfobjects['Material'.upper()])
        all_.extend(idf.idfobjects['Material:NoMass'.upper()])

        return [cls.from_epbunch(om, **kwargs) for om in all_]

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """
        Args:
            epbunch (EpBunch): EP-Construction object
            *args:
            **kwargs:
        """
        if epbunch.key.upper() == 'MATERIAL':
            # do MATERIAL
            Name = epbunch.Name
            Conductivity = epbunch.Conductivity
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            SpecificHeat = epbunch.Specific_Heat
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            Thickness = epbunch.Thickness
            return cls(Conductivity=Conductivity,
                       Roughness=Roughness,
                       SolarAbsorptance=SolarAbsorptance,
                       SpecificHeat=SpecificHeat,
                       ThermalEmittance=ThermalEmittance,
                       VisibleAbsorptance=VisibleAbsorptance,
                       Thickness=Thickness,
                       Name=Name,
                       **kwargs)
        elif epbunch.key.upper() == 'MATERIAL:NOMASS':
            # do MATERIAL:NOMASS
            Name = epbunch.Name
            Thickness = 0.0127  # half inch thickness
            Conductivity = Thickness / epbunch.Thermal_Resistance
            Roughness = epbunch.Roughness
            SolarAbsorptance = epbunch.Solar_Absorptance
            ThermalEmittance = epbunch.Thermal_Absorptance
            VisibleAbsorptance = epbunch.Visible_Absorptance
            Density = 1  # 1 kg/m3, smallest value umi allows
            SpecificHeat = 100  # 100 J/kg-K, smallest value umi allows
            return cls(Conductivity=Conductivity,
                       Roughness=Roughness,
                       SolarAbsorptance=SolarAbsorptance,
                       SpecificHeat=SpecificHeat,
                       ThermalEmittance=ThermalEmittance,
                       VisibleAbsorptance=VisibleAbsorptance,
                       Thickness=Thickness,
                       Density=Density,
                       Name=Name,
                       **kwargs)
        elif epbunch.key.upper() == 'MATERIAL:AIRGAP':
            Name = epbunch.Name
            Thickness = 0.0127  # half inch thickness
            Conductivity = Thickness / epbunch.Thermal_Resistance
            Roughness = "Smooth"
            Density = 1  # 1 kg/m3, smallest value umi allows
            SpecificHeat = 100  # 100 J/kg-K, smallest value umi allows
            return cls(Conductivity=Conductivity,
                       Roughness=Roughness,
                       SpecificHeat=SpecificHeat,
                       Thickness=Thickness,
                       Density=Density,
                       Name=Name,
                       **kwargs)
        else:
            raise NotImplementedError("Material '{}' of type '{}' is not yet "
                                      "supported. Please contact package "
                                      "authors".format(epbunch.Name,
                                                       epbunch.key))