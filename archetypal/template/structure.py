################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from deprecation import deprecated

import archetypal
from archetypal.template import UmiBase, Unique, OpaqueMaterial, UniqueName


class MassRatio(object):
    """Handles the properties of the"""

    def __init__(self, HighLoadRatio=None, Material=None, NormalRatio=None):
        """Initialize a MassRatio object with parameters

        Args:
            HighLoadRatio (float):
            Material (OpaqueMaterial):
            NormalRatio (float):
        """
        self.HighLoadRatio = HighLoadRatio
        self.Material = Material
        self.NormalRatio = NormalRatio

    def __hash__(self):
        return hash(id(self))

    def __eq__(self, other):
        if not isinstance(other, MassRatio):
            return False
        else:
            return all(
                [
                    self.HighLoadRatio == other.HighLoadRatio,
                    self.Material == other.Material,
                    self.NormalRatio == other.NormalRatio,
                ]
            )

    def to_dict(self):
        """dict representation of object"""
        return collections.OrderedDict(
            HighLoadRatio=self.HighLoadRatio,
            Material={"$ref": str(self.Material.id)},
            NormalRatio=self.NormalRatio,
        )

    @classmethod
    def generic(cls):
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


class StructureDefinition(UmiBase, metaclass=Unique):
    """Building Structure settings.

    .. image:: ../images/template/constructions-structure.png
    """

    def __init__(
        self,
        *args,
        AssemblyCarbon=0,
        AssemblyCost=0,
        AssemblyEnergy=0,
        DisassemblyCarbon=0,
        DisassemblyEnergy=0,
        MassRatios=None,
        **kwargs
    ):
        """
        Args:
            *args:
            AssemblyCarbon:
            AssemblyCost:
            AssemblyEnergy:
            DisassemblyCarbon:
            DisassemblyEnergy:
            MassRatios:
            **kwargs:
        """
        super(StructureDefinition, self).__init__(*args, **kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy
        self.MassRatios = MassRatios

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, StructureDefinition):
            return False
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

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):

        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        sd = cls(*args, **kwargs)
        massratios = kwargs.get("MassRatios", None)
        sd.MassRatios = [
            MassRatio(
                HighLoadRatio=massratio["HighLoadRatio"],
                Material=sd.get_ref(massratio["Material"]),
                NormalRatio=massratio["NormalRatio"],
            )
            for massratio in massratios
        ]
        return sd

    def to_json(self):
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
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def validate(self):
        """Validates UmiObjects and fills in missing values"""
        return self
