"""archetypal MaterialBase."""
from enum import Enum
from typing import Sequence, Optional

import numpy as np
from pydantic import BaseModel, Field
from validator_collection import validators

from archetypal.template.umi_base import UmiBase


class MaterialBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of materials.

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life
    -cycle-impact
    """

    Cost: float = Field(
        0, description="The purchase cost of the material by " "volume ($/m3)"
    )
    EmbodiedCarbon: float = Field(
        0,
        description="Represents the GHG emissions through the lifetime of the product (kgCO2/kg)",
    )
    EmbodiedEnergy: float = Field(
        0,
        description="Represents all fuel consumption (Typically from non-renewable "
        "sources) which happened through the lifetime of a product (or building), "
        "expressed as primary energy (MJ/kg).",
    )
    SubstitutionRatePattern: Optional[Sequence[float]] = Field(
        None,
        description=(
            "A ratio from 0 to 1 which\n"
            "defines the amount of the material replaced at the end of each\n"
            "period of replacement, :attr:`SubstitutionTimestep` (e.g. Every\n"
            "10 years this cladding will be completely replaced with ratio\n"
            "1). Notice that you can define different replacement ratios for\n"
            "different consecutive periods, introducing them separated by\n"
            "commas. For example, if you introduce the series “0.1 , 0.1 , "
            "1”\n"
            "after the first 10 years a 10% will be replaced, then after 20\n"
            "years another 10%, then after 30 years a 100%, and finally the\n"
            "series would start again in year 40."
        ),
    )
    SubstitutionTimestep: float = Field(
        100,
        description="The duration in years of a period of replacement (e.g. There "
        "will be interventions in this material type every 10 years).",
        ge=0,
    )
    TransportCarbon: float = Field(
        0,
        description="The impacts associated with the "
        "transport by km of distance and kg of material (kgCO2/kg/km)",
        ge=0,
    )
    TransportDistance: float = Field(
        0,
        description="The average distance in km from "
        "the manufacturing site to the building construction site",
        ge=0,
    )
    TransportEnergy: float = Field(
        0,
        description="The impacts associated with the "
        "transport by km of distance and kg of material (MJ/kg/km).",
        ge=0,
    )

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, MaterialBase):
            return NotImplemented
        else:
            return all(
                [
                    self.Cost == other.Cost,
                    self.EmbodiedCarbon == other.EmbodiedCarbon,
                    self.EmbodiedEnergy == other.EmbodiedEnergy,
                    self.SubstitutionTimestep == other.SubstitutionTimestep,
                    self.TransportCarbon == other.TransportCarbon,
                    self.TransportDistance == other.TransportDistance,
                    self.TransportEnergy == other.TransportEnergy,
                    np.array_equal(
                        self.SubstitutionRatePattern, other.SubstitutionRatePattern
                    ),
                    self.Density == other.Density,
                ]
            )


class ROUGHNESS(str, Enum):
    """A text value that indicated the roughness of your material."""

    VeryRough = "VeryRough"
    Rough = "Rough"
    MediumRough = "MediumRough"
    MediumSmooth = "MediumSmooth"
    Smooth = "Smooth"
    VerySmooth = "VerySmooth"