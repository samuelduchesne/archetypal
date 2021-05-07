"""archetypal MaterialLayer."""

import collections
import logging as lg

from sigfig import round
from validator_collection import validators

from archetypal.utils import log


class MaterialLayer(object):
    """Class used to define one layer in a construction assembly.

    This class has two attributes:

    1. Material (:class:`OpaqueMaterial` or :class:`GlazingMaterial` or
       :class:`GasMaterial`): the material object for this layer.
    2. Thickness (float): The thickness of the material in the layer.
    """

    __slots__ = ("_material", "_thickness")

    def __init__(self, Material, Thickness, **kwargs):
        """Initialize a MaterialLayer object with parameters.

        Args:
            Material (OpaqueMaterial, GlazingMaterial, GasMaterial):
            Thickness (float): The thickness of the material in the
                construction.
        """
        self.Material = Material
        self.Thickness = Thickness

    @property
    def Material(self):
        """Get or set the material of self."""
        return self._material

    @Material.setter
    def Material(self, value):
        from archetypal.template.materials import GlazingMaterial, OpaqueMaterial

        assert isinstance(value, (OpaqueMaterial, GlazingMaterial)), (
            f"Input value error for '{value}'. Value must be "
            f"of type (OpaqueMaterial, GlazingMaterial), not {type(value)}"
        )
        self._material = value

    @property
    def Thickness(self):
        """Get or set the material thickness [m]."""
        return self._thickness

    @Thickness.setter
    def Thickness(self, value):
        self._thickness = value
        if value < 0.003:
            log(
                "Modeling layer thinner (less) than 0.003 m (not recommended) for "
                f"MaterialLayer '{self}'",
                lg.WARNING,
            )

    @property
    def resistivity(self):
        """Get or set the resistivity of the material layer [m-K/W]."""
        return 1 / self.Material.Conductivity

    @resistivity.setter
    def resistivity(self, value):
        self.Material.Conductivity = 1 / validators.float(value, minimum=0)

    @property
    def r_value(self):
        """Get or set the the R-value of the material layer [m2-K/W].

        Note that, when setting the R-value, the thickness of the material will
        be adjusted and the conductivity will remain fixed.
        """
        return self.Thickness / self.Material.Conductivity

    @r_value.setter
    def r_value(self, value):
        self.Thickness = validators.float(value, minimum=0) * self.Material.Conductivity

    @property
    def u_value(self):
        """Get or set the heat transfer coefficient [W/(m2⋅K)]."""
        return 1 / self.r_value

    @u_value.setter
    def u_value(self, value):
        self.r_value = 1 / validators.float(value, minimum=0)

    @property
    def heat_capacity(self):
        """Get the material layer's heat capacity [J/(m2-k)]."""
        return self.Material.Density * self.Material.SpecificHeat * self.Thickness

    @property
    def specific_heat(self):
        """Get the material layer's specific heat [J/kg-K]."""
        return self.Material.SpecificHeat

    def to_dict(self):
        """Return MaterialLayer dictionary representation."""
        return collections.OrderedDict(
            Material={"$ref": str(self.Material.id)},
            Thickness=round(self.Thickness, decimals=3),
        )

    def to_epbunch(self, idf):
        """Convert self to an EpBunch given an IDF model.

        Notes:
            The object is added to the idf model.
            The thickness is passed to the epbunch.

        Args:
            idf (IDF): An IDF model.

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return self.Material.to_epbunch(idf, self.Thickness)

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        return dict(Material=self.Material, Thickness=self.Thickness)

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return self

    def __hash__(self):
        """Return the hash value of self."""
        return id(self)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, MaterialLayer):
            return NotImplemented
        else:
            return all(
                [self.Thickness == other.Thickness, self.Material == other.Material]
            )

    def __repr__(self):
        """Return a representation of self."""
        return "{} with thickness of {:,.3f} m".format(self.Material, self.Thickness)

    def __iter__(self):
        """Iterate over attributes. Yields tuple of (keys, value)."""
        for k, v in self.mapping().items():
            yield k, v

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(self.Material, self.Thickness)
