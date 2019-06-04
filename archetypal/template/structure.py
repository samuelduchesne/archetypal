import collections

from archetypal.template import UmiBase, Unique


class MassRatio(object):
    def __init__(self, HighLoadRatio=None, Material=None, NormalRatio=None):
        """
        Args:
            HighLoadRatio:
            Material:
            NormalRatio:
        """
        self.HighLoadRatio = HighLoadRatio
        self.Material = Material
        self.NormalRatio = NormalRatio

    def to_dict(self):
        """dict representation of object"""
        return collections.OrderedDict(HighLoadRatio=self.HighLoadRatio,
                                       Material={'$ref': str(
                                           self.Material.id)},
                                       NormalRatio=self.NormalRatio)


class StructureDefinition(UmiBase, metaclass=Unique):
    """
    $id, AssemblyCarbon, AssemblyCost, AssemblyEnergy, Category, Comments,
    DataSource, DisassemblyCarbon, DisassemblyEnergy, MassRatios, Name,
    """

    def __init__(self, *args, AssemblyCarbon=0, AssemblyCost=0,
                 AssemblyEnergy=0, DisassemblyCarbon=0, DisassemblyEnergy=0,
                 MassRatios=None, **kwargs):
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

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        sd = cls(*args, **kwargs)
        massratios = kwargs.get('MassRatios', None)
        sd.MassRatios = [MassRatio(HighLoadRatio=massratio['HighLoadRatio'],
                                   Material=sd.get_ref(massratio['Material']),
                                   NormalRatio=massratio['NormalRatio'])
                         for massratio in massratios]
        return sd

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["MassRatios"] = [mass.to_dict() for mass
                                   in self.MassRatios]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict