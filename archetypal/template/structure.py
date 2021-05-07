"""archetypal StructureInformation."""

import collections

from validator_collection import validators

from archetypal.template.constructions.base_construction import ConstructionBase
from archetypal.template.materials.opaque_material import OpaqueMaterial


class MassRatio(object):
    """Handles the properties of the mass ratio for building template structure."""

    __slots__ = ("_high_load_ratio", "_material", "_normal_ratio")

    def __init__(self, HighLoadRatio=None, Material=None, NormalRatio=None, **kwargs):
        """Initialize a MassRatio object with parameters.

        Args:
            HighLoadRatio (float):
            Material (OpaqueMaterial):
            NormalRatio (float):
        """
        self.HighLoadRatio = HighLoadRatio
        self.Material = Material
        self.NormalRatio = NormalRatio

    @property
    def HighLoadRatio(self):
        """Get or set the high load ratio [kg/m2]."""
        return self._high_load_ratio

    @HighLoadRatio.setter
    def HighLoadRatio(self, value):
        self._high_load_ratio = validators.float(value, minimum=0)

    @property
    def Material(self):
        """Get or set the structure OpaqueMaterial."""
        return self._material

    @Material.setter
    def Material(self, value):
        assert isinstance(
            value, OpaqueMaterial
        ), f"Material must be of type OpaqueMaterial, not {type(value)}"
        self._material = value

    @property
    def NormalRatio(self):
        """Get or set the normal load ratio [kg/m2]."""
        return self._normal_ratio

    @NormalRatio.setter
    def NormalRatio(self, value):
        self._normal_ratio = validators.float(value, minimum=0)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.__key__())

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return (
            self.HighLoadRatio,
            self.Material,
            self.NormalRatio,
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, MassRatio):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()

    def __iter__(self):
        """Iterate over attributes. Yields tuple of (keys, value)."""
        for k, v in self.mapping().items():
            yield k, v

    def to_dict(self):
        """Return MassRatio dictionary representation."""
        return collections.OrderedDict(
            HighLoadRatio=self.HighLoadRatio,
            Material={"$ref": str(self.Material.id)},
            NormalRatio=self.NormalRatio,
        )

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        return dict(
            HighLoadRatio=self.HighLoadRatio,
            Material=self.Material,
            NormalRatio=self.NormalRatio,
        )

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return self

    @classmethod
    def generic(cls):
        """Create generic MassRatio object."""
        mat = OpaqueMaterial(
            Name="Steel General",
            Conductivity=45.3,
            SpecificHeat=500,
            SolarAbsorptance=0.4,
            ThermalEmittance=0.9,
            VisibleAbsorptance=0.4,
            Roughness="Rough",
            Cost=0,
            Density=7830,
            MoistureDiffusionResistance=50,
            EmbodiedCarbon=1.37,
            EmbodiedEnergy=20.1,
            TransportCarbon=0.067,
            TransportDistance=500,
            TransportEnergy=0.94,
            SubstitutionRatePattern=[1],
            SubstitutionTimestep=100,
            DataSource="BostonTemplateLibrary.json",
        )
        return cls(HighLoadRatio=305, Material=mat, NormalRatio=305)

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(self.HighLoadRatio, self.Material, self.NormalRatio)


class StructureInformation(ConstructionBase):
    """Building Structure settings.

    .. image:: ../images/template/constructions-structure.png
    """

    __slots__ = ("_mass_ratios",)

    def __init__(self, Name, MassRatios, **kwargs):
        """Initialize object.

        Args:
            MassRatios (list of MassRatio): MassRatio object.
            **kwargs: keywords passed to the ConstructionBase constructor.
        """
        super(StructureInformation, self).__init__(Name, **kwargs)
        self.MassRatios = MassRatios

    @property
    def MassRatios(self):
        """Get or set the list of MassRatios."""
        return self._mass_ratios

    @MassRatios.setter
    def MassRatios(self, value):
        assert isinstance(value, list), "mass_ratio must be of a list of MassRatio"
        self._mass_ratios = value

    @classmethod
    def from_dict(cls, data, materials, **kwargs):
        """Create StructureInformation from a dictionary.

        Args:
            data (dict): A python dictionary.
            materials (dict): A dictionary of python OpaqueMaterials with their id as
                keys.
            **kwargs: keywords passed to parent constructors.
        """
        mass_ratio_ref = data.pop("MassRatios")
        mass_ratios = [
            MassRatio(
                HighLoadRatio=massratio["HighLoadRatio"],
                Material=materials[massratio["Material"]["$ref"]],
                NormalRatio=massratio["NormalRatio"],
            )
            for massratio in mass_ratio_ref
        ]
        _id = data.pop("$id")
        return cls(MassRatios=mass_ratios, id=_id, **data, **kwargs)

    def to_dict(self):
        """Return StructureInformation dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MassRatios"] = [mass.to_dict() for mass in self.MassRatios]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            MassRatios=self.MassRatios,
            AssemblyCarbon=self.AssemblyCarbon,
            AssemblyCost=self.AssemblyCost,
            AssemblyEnergy=self.AssemblyEnergy,
            DisassemblyCarbon=self.DisassemblyCarbon,
            DisassemblyEnergy=self.DisassemblyEnergy,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __hash__(self):
        """Return the hash value of self."""
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, StructureInformation):
            return NotImplemented
        else:
            return all(
                [
                    self.AssemblyCarbon == other.AssemblyCarbon,
                    self.AssemblyCost == other.AssemblyCost,
                    self.AssemblyEnergy == other.AssemblyEnergy,
                    self.DisassemblyCarbon == other.DisassemblyCarbon,
                    self.DisassemblyEnergy == other.DisassemblyEnergy,
                    self.MassRatios == other.MassRatios,
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping(validate=False))
