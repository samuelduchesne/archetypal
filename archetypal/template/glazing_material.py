################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import MaterialBase, Unique


class GlazingMaterial(MaterialBase, metaclass=Unique):
    """Glazing Materials

    .. image:: ../images/template/materials-glazing.png

    """

    def __init__(self, Density=2500, Conductivity=None, SolarTransmittance=None,
                 SolarReflectanceFront=None, SolarReflectanceBack=None,
                 VisibleTransmittance=None, VisibleReflectanceFront=None,
                 VisibleReflectanceBack=None, IRTransmittance=None,
                 IREmissivityFront=None, IREmissivityBack=None, DirtFactor=1.0,
                 Type=None, EmbodiedEnergy=0, EmbodiedEnergyStdDev=0,
                 EmbodiedCarbon=0, EmbodiedCarbonStdDev=0, Cost=0.0, Life=1,
                 SubstitutionRatePattern=[0.2], SubstitutionTimestep=50,
                 TransportCarbon=None, TransportDistance=None,
                 TransportEnergy=0, **kwargs):
        """
        Args:
            Density (float): A number representing the density of the material
                in kg/m3. This is essentially the mass of one cubic meter of the
                material.
            Conductivity (float): Thermal conductivity (W/m-K).
            SolarTransmittance (float): Transmittance at normal incidence
                averaged over the solar spectrum.
            SolarReflectanceFront (float): Front-side reflectance at normal
                incidence averaged over the solar spectrum.
            SolarReflectanceBack (float): Back-side reflectance at normal
                incidence averaged over the solar spectrum.
            VisibleTransmittance (float): Transmittance at normal incidence
                averaged over the solar spectrum and weighted by the response of
                the human eye.
            VisibleReflectanceFront (float): Front-side reflectance at normal
                incidence averaged over the solar spectrum and weighted by the
                response of the human eye.
            VisibleReflectanceBack (float): Back-side reflectance at normal
                incidence averaged over the solar spectrum and weighted by the
                response of the human eye.
            IRTransmittance (float): Long-wave transmittance at normal
                incidence.
            IREmissivityFront (float): Front-side long-wave emissivity.
            IREmissivityBack (float): Back-side long-wave emissivity.
            DirtFactor (float): This is a factor that corrects for the presence
                of dirt on the glass. Using a material with dirt correction
                factor < 1.0 in the construction for an interior window will
                result in an error message.
            Type: # todo: defined parameter
            EmbodiedEnergy: # todo: defined parameter
            EmbodiedEnergyStdDev: # todo: defined parameter
            EmbodiedCarbon: # todo: defined parameter
            EmbodiedCarbonStdDev: # todo: defined parameter
            Cost: # todo: defined parameter
            Life: # todo: defined parameter
            SubstitutionRatePattern: # todo: defined parameter
            SubstitutionTimestep: # todo: defined parameter
            TransportCarbon: # todo: defined parameter
            TransportDistance: # todo: defined parameter
            TransportEnergy: # todo: defined parameter
            **kwargs:
        """
        super(GlazingMaterial, self).__init__(**kwargs)
        self.TransportEnergy = TransportEnergy
        self.TransportDistance = TransportDistance
        self.TransportCarbon = TransportCarbon
        self.SubstitutionTimestep = SubstitutionTimestep
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.Life = Life
        self.Cost = Cost
        self.EmbodiedCarbonStdDev = EmbodiedCarbonStdDev
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergyStdDev = EmbodiedEnergyStdDev
        self.EmbodiedEnergy = EmbodiedEnergy
        self.Type = Type
        self.DirtFactor = DirtFactor
        self.IREmissivityBack = IREmissivityBack
        self.IREmissivityFront = IREmissivityFront
        self.IRTransmittance = IRTransmittance
        self.VisibleReflectanceBack = VisibleReflectanceBack
        self.VisibleReflectanceFront = VisibleReflectanceFront
        self.VisibleTransmittance = VisibleTransmittance
        self.SolarReflectanceBack = SolarReflectanceBack
        self.SolarReflectanceFront = SolarReflectanceFront
        self.SolarTransmittance = SolarTransmittance
        self.Density = Density
        self.Conductivity = Conductivity

    def __add__(self, other):
        """Overload + to implement self.combine."""
        return self.combine(other)

    def combine(self, other):
        """
        Args:
            other (GlazingMaterial):
        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        name = " + ".join([self.__dict__.pop('Name'), other.Name])
        comments = self._str_mean(other, attr='Comments', append=True)
        idf = self.__dict__.get('idf')
        sql = self.__dict__.get('sql')
        # iterate over attributes and apply either float_mean or str_mean.
        new_attr = {}
        for attr in self.__dict__:
            if attr not in ['Comments', 'idf', 'sql']:
                if isinstance(self.__dict__[attr], float):
                    new_attr[attr] = self._float_mean(other, attr=attr)
                elif isinstance(self.__dict__[attr], str):
                    new_attr[attr] = self._str_mean(other, attr=attr,
                                                    append=False)
        # create a new object from combined attributes
        new_obj = self.__class__(Name=name, idf=idf, sql=sql,
                                 Comments=comments, **new_attr)
        return new_obj

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DirtFactor"] = self.DirtFactor
        data_dict["IREmissivityBack"] = self.IREmissivityBack
        data_dict["IREmissivityFront"] = self.IREmissivityFront
        data_dict["IRTransmittance"] = self.IRTransmittance
        data_dict["SolarReflectanceBack"] = self.SolarReflectanceBack
        data_dict["SolarReflectanceFront"] = self.SolarReflectanceFront
        data_dict["SolarTransmittance"] = self.SolarTransmittance
        data_dict["VisibleReflectanceBack"] = self.VisibleReflectanceBack
        data_dict["VisibleReflectanceFront"] = self.VisibleReflectanceFront
        data_dict["VisibleTransmittance"] = self.VisibleTransmittance
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
