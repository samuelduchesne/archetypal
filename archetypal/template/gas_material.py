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
