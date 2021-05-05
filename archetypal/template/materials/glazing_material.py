"""archetypal GlazingMaterial."""

import collections

from sigfig import round
from validator_collection import validators

from archetypal.idfclass.extensions import EpBunch
from archetypal.template.materials.material_base import MaterialBase
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log


class GlazingMaterial(MaterialBase):
    """Glazing Materials class.

    .. image:: ../images/template/materials-glazing.png

    """

    __slots__ = (
        "_ir_emissivity_back",
        "_ir_emissivity_front",
        "_ir_transmittance",
        "_visible_reflectance_back",
        "_visible_reflectance_front",
        "_visible_transmittance",
        "_solar_reflectance_back",
        "_solar_reflectance_front",
        "_solar_transmittance",
        "_dirt_factor",
        "_conductivity",
    )

    def __init__(
        self,
        Name,
        Density=2500,
        Conductivity=0.9,
        SolarTransmittance=0,
        SolarReflectanceFront=0,
        SolarReflectanceBack=0,
        VisibleTransmittance=0,
        VisibleReflectanceFront=0,
        VisibleReflectanceBack=0,
        IRTransmittance=0,
        IREmissivityFront=0,
        IREmissivityBack=0,
        DirtFactor=1.0,
        Cost=0.0,
        **kwargs,
    ):
        """Initialize a GlazingMaterial object.

        Args:
            Name (str): The name of the GlazingMaterial.
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
            **kwargs: keywords passed to the :class:`MaterialBase`
                constructor. For more info, see :class:`MaterialBase`.
        """
        super(GlazingMaterial, self).__init__(Name, Cost=Cost, **kwargs)

        self._solar_reflectance_front = 0
        self._solar_reflectance_back = None
        self._visible_reflectance_front = 0
        self._visible_reflectance_back = None

        self.Conductivity = Conductivity
        self.Density = Density
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

    @property
    def Conductivity(self):
        """Get or set the conductivity of the material [W/m-K]."""
        return self._conductivity

    @Conductivity.setter
    def Conductivity(self, value):
        self._conductivity = validators.float(value, minimum=0)

    @property
    def Density(self):
        """Get or set the density of the material [J/kg-K]."""
        return self._density

    @Density.setter
    def Density(self, value):
        self._density = validators.float(value, minimum=0)

    @property
    def DirtFactor(self):
        """Get or set the dirt correction factor [-]."""
        return self._dirt_factor

    @DirtFactor.setter
    def DirtFactor(self, value):
        if value == "":
            value = 1
        self._dirt_factor = validators.float(value, minimum=0, maximum=1)

    @property
    def IREmissivityBack(self):
        """Get or set the infrared emissivity of the back side [-]."""
        return float(self._ir_emissivity_back)

    @IREmissivityBack.setter
    def IREmissivityBack(self, value):
        self._ir_emissivity_back = validators.float(value, False, 0.0, 1.0)

    @property
    def IREmissivityFront(self):
        """Get or set the infrared emissivity of the front side [-]."""
        return self._ir_emissivity_front

    @IREmissivityFront.setter
    def IREmissivityFront(self, value):
        self._ir_emissivity_front = validators.float(value, False, 0.0, 1.0)

    @property
    def IRTransmittance(self):
        """Get or set the infrared transmittance [-]."""
        return self._ir_transmittance

    @IRTransmittance.setter
    def IRTransmittance(self, value):
        self._ir_transmittance = validators.float(value, False, 0.0, 1.0)

    @property
    def VisibleReflectanceBack(self):
        """Get or set the visible reflectance of the back side [-]."""
        return self._visible_reflectance_back

    @VisibleReflectanceBack.setter
    def VisibleReflectanceBack(self, value):
        self._visible_reflectance_back = validators.float(value, False, 0.0, 1.0)

    @property
    def VisibleReflectanceFront(self):
        """Get or set the visible reflectance of the front side [-]."""
        return self._visible_reflectance_front

    @VisibleReflectanceFront.setter
    def VisibleReflectanceFront(self, value):
        self._visible_reflectance_front = validators.float(value, False, 0.0, 1.0)

    @property
    def VisibleTransmittance(self):
        """Get or set the visible transmittance [-]."""
        return self._visible_transmittance

    @VisibleTransmittance.setter
    def VisibleTransmittance(self, value):
        assert value + self._visible_reflectance_front <= 1, (
            f"Sum of window transmittance and reflectance '"
            f"{self._visible_reflectance_front}' is greater than 1."
        )
        if self._visible_reflectance_back is not None:
            assert value + self._visible_reflectance_back <= 1, (
                f"Sum of window transmittance and reflectance '"
                f"{self._visible_reflectance_back}' is greater than 1."
            )
        self._visible_transmittance = validators.float(value, False, 0.0, 1.0)

    @property
    def SolarReflectanceBack(self):
        """Get or set the solar reflectance of the back side [-]."""
        return self._solar_reflectance_back

    @SolarReflectanceBack.setter
    def SolarReflectanceBack(self, value):
        self._solar_reflectance_back = validators.float(value, False, 0.0, 1.0)

    @property
    def SolarReflectanceFront(self):
        """Get or set the solar reflectance of the front side [-]."""
        return self._solar_reflectance_front

    @SolarReflectanceFront.setter
    def SolarReflectanceFront(self, value):
        self._solar_reflectance_front = validators.float(value, False, 0.0, 1.0)

    @property
    def SolarTransmittance(self):
        """Get or set the solar transmittance [-]."""
        return self._solar_transmittance

    @SolarTransmittance.setter
    def SolarTransmittance(self, value):
        self._solar_transmittance = validators.float(value, False, 0.0, 1.0)

    def combine(self, other, weights=None, allow_duplicates=False):
        """Combine two GlazingMaterial objects together.

        Args:
            other (GlazingMaterial): The other GlazingMaterial object to
                combine with.
        Returns:
            (GlazingMaterial): the combined GlazingMaterial object.
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

        meta = self._get_predecessors_meta(other)

        if not weights:
            log(
                'using GlazingMaterial density as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [self.Density, other.Density]
        # iterate over attributes and apply either float_mean or str_mean.
        new_attr = {}
        for attr, value in self.mapping().items():
            if attr not in ["Comments", "DataSource"]:
                if isinstance(value, (int, float)) or isinstance(other, (int, float)):
                    new_attr[attr] = UmiBase.float_mean(
                        self, other, attr=attr, weights=weights
                    )
                elif isinstance(value, str) or isinstance(other, str):
                    new_attr[attr] = UmiBase._str_mean(
                        self, other, attr=attr, append=False
                    )
                elif isinstance(value, list) or isinstance(other, list):
                    new_attr[attr] = getattr(self, attr) + getattr(other, attr)
                elif isinstance(value, collections.UserList) or isinstance(
                    other, collections.UserList
                ):
                    pass
                else:
                    raise NotImplementedError
        [new_attr.pop(key, None) for key in meta.keys()]  # meta handles these
        # keywords.
        # create a new object from combined attributes
        new_obj = self.__class__(**meta, **new_attr)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_dict(self):
        """Return GlazingMaterial dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DirtFactor"] = self.DirtFactor
        data_dict["IREmissivityBack"] = round(self.IREmissivityBack, 2)
        data_dict["IREmissivityFront"] = round(self.IREmissivityFront, 2)
        data_dict["IRTransmittance"] = round(self.IRTransmittance, 2)
        data_dict["SolarReflectanceBack"] = round(self.SolarReflectanceBack, 2)
        data_dict["SolarReflectanceFront"] = round(self.SolarReflectanceFront, 2)
        data_dict["SolarTransmittance"] = round(self.SolarTransmittance, 2)
        data_dict["VisibleReflectanceBack"] = round(self.VisibleReflectanceBack, 2)
        data_dict["VisibleReflectanceFront"] = round(self.VisibleReflectanceFront, 2)
        data_dict["VisibleTransmittance"] = round(self.VisibleTransmittance, 2)
        data_dict["Conductivity"] = round(self.Conductivity, 2)
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
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf, thickness) -> EpBunch:
        """Convert self to an EpBunch given an idf model and a thickness.

        Args:
            idf (IDF): An IDF model.
            thickness (float): the thickness of the material.

        .. code-block:: python

            WindowMaterial:Glazing,
                B_Glass_Clear_3_0.003_B_Dbl_Air_Cl,    !- Name
                SpectralAverage,          !- Optical Data Type
                SpectralAverage,          !- Window Glass Spectral Data Set Name
                0.003,                    !- Thickness
                0.83,                     !- Solar Transmittance at Normal Incidence
                0.07,                     !- Front Side Solar Reflectance at Normal Incidence
                0.07,                     !- Back Side Solar Reflectance at Normal Incidence
                0.89,                     !- Visible Transmittance at Normal Incidence
                0.08,                     !- Front Side Visible Reflectance at Normal Incidence
                0.08,                     !- Back Side Visible Reflectance at Normal Incidence
                0,                        !- Infrared Transmittance at Normal Incidence
                0.84,                     !- Front Side Infrared Hemispherical Emissivity
                0.84,                     !- Back Side Infrared Hemispherical Emissivity
                0.9,                      !- Conductivity
                1;                        !- Dirt Correction Factor for Solar and Visible Transmittance

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            "WINDOWMATERIAL:GLAZING",
            Name=self.Name,
            Optical_Data_Type="SpectralAverage",
            Window_Glass_Spectral_Data_Set_Name="SpectralAverage",
            Thickness=thickness,
            Solar_Transmittance_at_Normal_Incidence=self.SolarTransmittance,
            Front_Side_Solar_Reflectance_at_Normal_Incidence=self.SolarReflectanceFront,
            Back_Side_Solar_Reflectance_at_Normal_Incidence=self.SolarReflectanceBack,
            Visible_Transmittance_at_Normal_Incidence=self.VisibleTransmittance,
            Front_Side_Visible_Reflectance_at_Normal_Incidence=self.VisibleReflectanceFront,
            Back_Side_Visible_Reflectance_at_Normal_Incidence=self.VisibleReflectanceBack,
            Infrared_Transmittance_at_Normal_Incidence=self.IRTransmittance,
            Front_Side_Infrared_Hemispherical_Emissivity=self.IREmissivityFront,
            Back_Side_Infrared_Hemispherical_Emissivity=self.IREmissivityBack,
            Conductivity=self.Conductivity,
            Dirt_Correction_Factor_for_Solar_and_Visible_Transmittance=self.DirtFactor,
        )

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            DirtFactor=self.DirtFactor,
            IREmissivityBack=self.IREmissivityBack,
            IREmissivityFront=self.IREmissivityFront,
            IRTransmittance=self.IRTransmittance,
            SolarReflectanceBack=self.SolarReflectanceBack,
            SolarReflectanceFront=self.SolarReflectanceFront,
            SolarTransmittance=self.SolarTransmittance,
            VisibleReflectanceBack=self.VisibleReflectanceBack,
            VisibleReflectanceFront=self.VisibleReflectanceFront,
            VisibleTransmittance=self.VisibleTransmittance,
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

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create a GlazingMaterial from a dictionary.

        Args:
            data: The python dictionary following the format below.

        .. code-block:: python

            {'$id': '1',
             'DirtFactor': 1.0,
             'IREmissivityBack': 0.0,
             'IREmissivityFront': 0.0,
             'IRTransmittance': 0.0,
             'SolarReflectanceBack': 0.0,
             'SolarReflectanceFront': 0.0,
             'SolarTransmittance': 0.0,
             'VisibleReflectanceBack': 0.0,
             'VisibleReflectanceFront': 0.0,
             'VisibleTransmittance': 0.0,
             'Conductivity': 0.0,
             'Cost': 0.0,
             'Density': 2500,
             'EmbodiedCarbon': 0.0,
             'EmbodiedEnergy': 0.0,
             'SubstitutionRatePattern': [1.0],
             'SubstitutionTimestep': 100.0,
             'TransportCarbon': 0.0,
             'TransportDistance': 0.0,
             'TransportEnergy': 0.0,
             'Category': 'Uncategorized',
             'Comments': '',
             'DataSource': None,
             'Name': 'A'}
        """
        _id = data.pop("$id")
        return cls(id=_id, **data, **kwargs)

    def __add__(self, other):
        """Overload + to implement self.combine."""
        return self.combine(other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, GlazingMaterial):
            return NotImplemented
        else:
            return all(
                [
                    self.Density == other.Density,
                    self.Conductivity == other.Conductivity,
                    self.SolarTransmittance == other.SolarTransmittance,
                    self.SolarReflectanceFront == other.SolarReflectanceFront,
                    self.SolarReflectanceBack == other.SolarReflectanceBack,
                    self.VisibleTransmittance == other.VisibleTransmittance,
                    self.VisibleReflectanceFront == other.VisibleReflectanceFront,
                    self.VisibleReflectanceBack == other.VisibleReflectanceBack,
                    self.IRTransmittance == other.IRTransmittance,
                    self.IREmissivityFront == other.IREmissivityFront,
                    self.IREmissivityBack == other.IREmissivityBack,
                    self.DirtFactor == other.DirtFactor,
                    self.Cost == other.Cost,
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping())
