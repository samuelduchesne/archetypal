"""archetypal MaterialBase."""

import numpy as np
from validator_collection import validators

from archetypal.template.umi_base import UmiBase


class MaterialBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of materials.

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life
    -cycle-impact
    """

    __slots__ = (
        "_cost",
        "_embodied_carbon",
        "_embodied_energy",
        "_substitution_timestep",
        "_transport_carbon",
        "_transport_distance",
        "_transport_energy",
        "_substitution_rate_pattern",
        "_density",
    )

    def __init__(
        self,
        Name,
        Cost=0,
        EmbodiedCarbon=0,
        EmbodiedEnergy=0,
        SubstitutionTimestep=100,
        TransportCarbon=0,
        TransportDistance=0,
        TransportEnergy=0,
        SubstitutionRatePattern=None,
        **kwargs,
    ):
        """Initialize a MaterialBase object with parameters.

        Args:
            Name (str): Name of the Material.
            Cost (float): The purchase cost of the material by volume ($/m3).
            EmbodiedCarbon (float): Represents the GHG emissions through the
                lifetime of the product (kgCO2/kg).
            EmbodiedEnergy (float): Represents all fuel consumption ( Typically
                from non-renewable sources) which happened through the lifetime
                of a product (or building), expressed as primary energy (MJ/kg).
            SubstitutionTimestep (float): The duration in years of a period of
                replacement (e.g. There will be interventions in this material
                type every 10 years).
            TransportCarbon (float): The impacts associated with the transport
                by km of distance and kg of material (kgCO2/kg/km).
            TransportDistance (float): The average distance in km from the
                manufacturing site to the building construction site
            TransportEnergy (float): The impacts associated with the transport
                by km of distance and kg of material (MJ/kg/km).
            SubstitutionRatePattern (list-like): A ratio from 0 to 1 which
                defines the amount of the material replaced at the end of each
                period of replacement, :attr:`SubstitutionTimestep` (e.g. Every
                10 years this cladding will be completely replaced with ratio
                1). Notice that you can define different replacement ratios for
                different consecutive periods, introducing them separated by
                commas. For example, if you introduce the series “0.1 , 0.1 , 1”
                after the first 10 years a 10% will be replaced, then after 20
                years another 10%, then after 30 years a 100%, and finally the
                series would start again in year 40.
            **kwargs: Keywords passed to the :class:`UmiBase` class. See
                :class:`UmiBase` for more details.
        """
        super(MaterialBase, self).__init__(Name, **kwargs)
        self.Cost = Cost
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy

    @property
    def Cost(self):
        """Get or set the cost of the material [$]."""
        return self._cost

    @Cost.setter
    def Cost(self, value):
        self._cost = validators.float(value)

    @property
    def EmbodiedCarbon(self):
        """Get or set the embodied carbon of the material [kgCO2/kg]."""
        return self._embodied_carbon

    @EmbodiedCarbon.setter
    def EmbodiedCarbon(self, value):
        self._embodied_carbon = validators.float(value)

    @property
    def EmbodiedEnergy(self):
        """Get or set the embodied energy of the material [MJ/kg]."""
        return self._embodied_energy

    @EmbodiedEnergy.setter
    def EmbodiedEnergy(self, value):
        self._embodied_energy = validators.float(value)

    @property
    def SubstitutionTimestep(self):
        """Get or set the substitution timestep of the material."""
        return self._substitution_timestep

    @SubstitutionTimestep.setter
    def SubstitutionTimestep(self, value):
        self._substitution_timestep = validators.float(value, minimum=0)

    @property
    def SubstitutionRatePattern(self):
        """Get or set the substitution rate pattern of the material."""
        return self._substitution_rate_pattern

    @SubstitutionRatePattern.setter
    def SubstitutionRatePattern(self, value):
        if value is None:
            value = [1.0]
        elif isinstance(value, np.ndarray):
            value = value.tolist()
        self._substitution_rate_pattern = validators.iterable(value, allow_empty=True)

    @property
    def TransportCarbon(self):
        """Get or set the transportation carbon of the material [kgCO2/kg/km]."""
        return self._transport_carbon

    @TransportCarbon.setter
    def TransportCarbon(self, value):
        self._transport_carbon = validators.float(value, minimum=0)

    @property
    def TransportDistance(self):
        """Get or set the transportation distance of the material [km]."""
        return self._transport_distance

    @TransportDistance.setter
    def TransportDistance(self, value):
        self._transport_distance = validators.float(value, minimum=0)

    @property
    def TransportEnergy(self):
        """Get or set the transporation energy of the material [MJ/kg/km]."""
        return self._transport_energy

    @TransportEnergy.setter
    def TransportEnergy(self, value):
        self._transport_energy = validators.float(value, minimum=0)

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

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

    def validate(self):
        """Validate object and fill in missing values."""
        return self
