################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import MaterialBase, Unique


class GasMaterial(MaterialBase, metaclass=Unique):
    """Gas Materials

    .. image:: ../images/template/materials-gas.png

    """

    def __init__(self, *args, Category="Gases", Type="Gas", **kwargs):
        """
        Args:
            *args:
            Category:
            Type:
            **kwargs:
        """
        super(GasMaterial, self).__init__(*args, Category=Category, **kwargs)
        self.Type = Type

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name))

    def __eq__(self, other):
        if not isinstance(other, GasMaterial):
            return False
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
                    self.SubstitutionRatePattern == other.SubstitutionRatePattern,
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                    self.TransportCarbon == other.TransportCarbon,
                    self.TransportDistance == other.TransportDistance,
                    self.TransportEnergy == other.TransportEnergy,
                ]
            )

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        gm = cls(*args, **kwargs)
        gas_type = kwargs.get("Name", None)
        gm.Type = gas_type

        return gm

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Type"] = self.Type
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
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict
