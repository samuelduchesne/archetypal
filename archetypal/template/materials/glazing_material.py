"""archetypal GlazingMaterial."""

import collections

from pydantic import Field, validator, PositiveFloat
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
    _CREATED_OBJECTS = []

    Density: PositiveFloat = Field(
        ...,
        description="A number representing the density of the material in kg/m3. This "
        "is essentially the mass of one cubic meter of the material.",
    )
    Conductivity: PositiveFloat = Field(..., description="Thermal conductivity (W/m-K)")
    DirtFactor: float = Field(
        ...,
        description="This is a factor that corrects for the presence of dirt on the "
        "glass. Using a material with dirt correction factor < 1.0 in the "
        "construction for an interior window will result in an error message.",
        ge=0,
        le=1,
    )
    IREmissivityBack: float = Field(
        ..., description="Back-side long-wave emissivity", ge=0, le=1
    )
    IREmissivityFront: float = Field(
        ..., description="Front-side long-wave emissivity.", ge=0, le=1
    )
    IRTransmittance: float = Field(
        ..., description="Long-wave transmittance at normal incidence.", ge=0, le=1
    )
    VisibleReflectanceBack: float = Field(
        ...,
        description="Back-side reflectance at normal incidence averaged over the "
        "solar spectrum and weighted by the response of the human eye.",
        ge=0,
        le=1,
    )
    VisibleReflectanceFront: float = Field(
        ...,
        description="Front-side reflectance at normal incidence averaged over the "
        "solar spectrum and weighted by the response of the human eye.",
        ge=0,
        le=1,
    )
    VisibleTransmittance: float = Field(
        ...,
        description="Transmittance at normal incidence averaged over the solar "
        "spectrum and weighted by the response of the human eye.",
    )
    SolarReflectanceBack: float = Field(
        ...,
        description="Back-side reflectance at normal incidence averaged over the "
        "solar spectrum.",
        ge=0,
        le=0,
    )
    SolarReflectanceFront: float = Field(
        ...,
        description="Front-side reflectance at normal incidence averaged over the "
        "solar spectrum.",
        ge=0,
        le=0,
    )
    SolarTransmittance: float = Field(
        ...,
        description="Transmittance at normal incidence averaged over the solar "
        "spectrum.",
        ge=0,
        le=1,
    )

    @validator("VisibleTransmittance")
    def visible_transmittance_check(cls, v, values, **kwargs):
        assert v + values["VisibleReflectanceFront"] <= 1, (
            f"Sum of window transmittance and reflectance '"
            f"{values['VisibleReflectanceFront']}' is greater than 1."
        )
        if values["VisibleReflectanceBack"] is not None:
            assert v + values["VisibleReflectanceBack"] <= 1, (
                f"Sum of window transmittance and reflectance '"
                f"{values['VisibleReflectanceBack']}' is greater than 1."
            )
        return v

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

    def mapping(self, validate=False):
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
        return hash(self.id)

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
