################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

import numpy as np
from deprecation import deprecated
from sigfig import round

import archetypal
from archetypal.template import MaterialBase


class GasMaterial(MaterialBase):
    """Gas Materials

    .. image:: ../images/template/materials-gas.png
    """

    def __init__(self, Name, Category="Gases", Type="Air", **kwargs):
        """
        Args:
            Name:
            Category:
            Type (str): The choices are Air, Argon, Krypton, or Xenon.
            **kwargs:
        """
        super(GasMaterial, self).__init__(Name, Category=Category, **kwargs)
        self.Type = Type

    def __hash__(self):
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
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

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):

        """
        Args:
            *args:
            **kwargs:
        """
        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
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
        mapping = self.reverse_mapping()
        mapping.update(dict(Name=f"{self.Name}, {thickness} m", Thickness=thickness))
        return idf.newidfobject(**mapping)

    def mapping(self):
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

    def reverse_mapping(self):
        """UMI to EpBunch mapping.

        Name and Thickness must be provided.
        """
        return {
            "key": "WINDOWMATERIAL:GAS",
            "Name": "",
            "Gas_Type": self.Type,
            "Thickness": "",
            "Conductivity_Coefficient_A": "",
            "Conductivity_Coefficient_B": "",
            "Conductivity_Coefficient_C": "",
            "Viscosity_Coefficient_A": "",
            "Viscosity_Coefficient_B": "",
            "Viscosity_Coefficient_C": "",
            "Specific_Heat_Coefficient_A": "",
            "Specific_Heat_Coefficient_B": "",
            "Specific_Heat_Coefficient_C": "",
            "Molecular_Weight": "",
            "Specific_Heat_Ratio": "",
        }
