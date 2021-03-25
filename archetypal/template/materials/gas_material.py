"""GasMaterial module."""

import collections

import numpy as np
from sigfig import round

from .material_base import MaterialBase


class GasMaterial(MaterialBase):
    """Gas Materials.

    .. image:: ../images/template/materials-gas.png
    """

    __slots__ = ("_type",)

    GASTYPES = ("air", "argon", "krypton", "xenon", "sf6")

    def __init__(self, Name, Type="Air", Category="Gases", **kwargs):
        """Initialize object with parameters.

        Args:
            Name (str): The name of the GasMaterial.
            Category (str): Category is set as "Gases" for GasMaterial.
            Type (str): The gas type of the GasMaterial. Choices are ("Air", "Argon",
                "Krypton", "Xenon")
            **kwargs: keywords passed to the MaterialBase constructor.
        """
        super(GasMaterial, self).__init__(Name, Category=Category, **kwargs)
        self.Type = Type

    @property
    def Type(self):
        """Get or set the gas type.

        Choices are ("Air", "Argon", "Krypton", "Xenon").
        """
        return self._type

    @Type.setter
    def Type(self, value):
        assert value.lower() in self.GASTYPES, (
            f"Invalid value '{value}' for material gas type. Gas type must be one "
            f"of the following:\n{self.GASTYPES}"
        )
        self._type = value

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create a GasMaterial from a dictionary.

        Args:
            data (dict): A python dictionary.
            **kwargs: keywords passed the MaterialBase constructor.
        """
        _id = data.pop("$id")
        return cls(id=_id, **data, **kwargs)

    def to_dict(self):
        """Return GasMaterial dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Type"] = self.Type
        data_dict["Conductivity"] = round(self.Conductivity, sigfigs=2)
        data_dict["Cost"] = self.Cost
        data_dict["Density"] = self.Density
        data_dict["EmbodiedCarbon"] = self.EmbodiedCarbon
        data_dict["EmbodiedEnergy"] = self.EmbodiedEnergy
        data_dict["SubstitutionRatePattern"] = self.SubstitutionRatePattern
        data_dict["SubstitutionTimestep"] = self.SubstitutionTimestep
        data_dict["TransportCarbon"] = self.TransportCarbon
        data_dict["TransportDistance"] = self.TransportDistance
        data_dict["TransportEnergy"] = self.TransportEnergy
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf, thickness):
        """Convert self to an epbunch given an idf model and a thickness.

        Args:
            idf (IDF): An IDF model.
            thickness (float): the thickness of the material.

        .. code-block:: python

            WindowMaterial:Gas,
                AIR_0.006_B_Dbl_Air_Cl,    !- Name
                AIR,                      !- Gas Type
                0.006;                    !- Thickness

        """
        return idf.newidfobject(
            "WINDOWMATERIAL:GAS",
            Name=self.Name,
            Gas_Type=self.Type,
            Thickness=thickness,
        )

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        self.validate()

        return dict(
            Category=self.Category,
            Type=self.Type,
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
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, GasMaterial):
            return NotImplemented
        else:
            return all(
                [
                    self.Category == other.Category,
                    self.Type == other.Type,
                    self.Conductivity == other.Conductivity,
                    self.Cost == other.Cost,
                    self.Density == other.Density,
                    self.EmbodiedCarbon == other.EmbodiedCarbon,
                    self.EmbodiedEnergy == other.EmbodiedEnergy,
                    np.array_equal(
                        self.SubstitutionRatePattern, other.SubstitutionRatePattern
                    ),
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                    self.TransportCarbon == other.TransportCarbon,
                    self.TransportDistance == other.TransportDistance,
                    self.TransportEnergy == other.TransportEnergy,
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping())
