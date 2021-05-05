"""archetypal GasLayer."""
import collections
import logging as lg
import math

from sigfig import round

from archetypal.utils import log


class GasLayer(object):
    """Class used to define one gas layer in a window construction assembly.

    This class has two attributes:

    1. Material (:class:`GasMaterial`): the material object for this layer.
    2. Thickness (float): The thickness of the material in the layer.
    """

    __slots__ = ("_material", "_thickness")

    def __init__(self, Material, Thickness, **kwargs):
        """Initialize a MaterialLayer object with parameters.

        Args:
            Material (GasMaterial):
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
        from archetypal.template.materials import GasMaterial

        assert isinstance(value, GasMaterial), (
            f"Input value error for '{value}'. Value must be of type (GasMaterial), "
            f"not {type(value)}."
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
        self.Material.Conductivity = 1 / float(value)

    @property
    def r_value(self):
        """Get or set the the R-value of the material layer [m2-K/W].

        Note that, when setting the R-value, the thickness of the material will
        be adjusted and the conductivity will remain fixed.
        """
        return self.Thickness / self.Material.Conductivity

    @r_value.setter
    def r_value(self, value):
        self.Thickness = float(value) * self.Material.Conductivity

    @property
    def heat_capacity(self):
        """Get the material layer's heat capacity [J/(m2-k)]."""
        return (
            self.Material.Density
            * self.Material.specific_heat_at_temperature(273.15)
            * self.Thickness
        )

    @property
    def specific_heat(self):
        """Get the material layer's specific heat at 0C [J/kg-K]."""
        return self.Material.specific_heat

    def u_value(
        self,
        delta_t=15,
        emissivity_1=0.84,
        emissivity_2=0.84,
        height=1.0,
        t_kelvin=273.15,
        pressure=101325,
    ):
        """Get the U-value of a vertical gas cavity given temp diff and emissivity.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. This
                influences how strong the convection is within the gas gap. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            emissivity_1: The emissivity of the surface on one side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            emissivity_2: The emissivity of the surface on the other side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        return self.convective_conductance(
            delta_t, height, t_kelvin, pressure
        ) + self.radiative_conductance(emissivity_1, emissivity_2, t_kelvin)

    def u_value_at_angle(
        self,
        delta_t=15,
        emissivity_1=0.84,
        emissivity_2=0.84,
        height=1.0,
        angle=90,
        t_kelvin=273.15,
        pressure=101325,
    ):
        """Get the U-value of a vertical gas cavity given temp diff and emissivity.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. This
                influences how strong the convection is within the gas gap. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            emissivity_1: The emissivity of the surface on one side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            emissivity_2: The emissivity of the surface on the other side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            angle: An angle in degrees between 0 and 180.
                0 = A horizontal cavity with downward heat flow through the layer.
                90 = A vertical cavity
                180 = A horizontal cavity with upward heat flow through the layer.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        return self.convective_conductance_at_angle(
            delta_t, height, angle, t_kelvin, pressure
        ) + self.radiative_conductance(emissivity_1, emissivity_2, t_kelvin)

    def convective_conductance(
        self, delta_t=15, height=1.0, t_kelvin=273.15, pressure=101325
    ):
        """Get convective conductance of the cavity in a vertical position.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        return self.nusselt(delta_t, height, t_kelvin, pressure) * (
            self.Material.conductivity_at_temperature(t_kelvin) / self.Thickness
        )

    def convective_conductance_at_angle(
        self, delta_t=15, height=1.0, angle=90, t_kelvin=273.15, pressure=101325
    ):
        """Get convective conductance of the cavity in an angle.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            angle: An angle in degrees between 0 and 180.
                * 0 = A horizontal cavity with downward heat flow through the layer.
                * 90 = A vertical cavity
                * 180 = A horizontal cavity with upward heat flow through the layer.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        return self.nusselt_at_angle(delta_t, height, angle, t_kelvin, pressure) * (
            self.Material.conductivity_at_temperature(t_kelvin) / self.Thickness
        )

    def radiative_conductance(
        self, emissivity_1=0.84, emissivity_2=0.84, t_kelvin=273.15
    ):
        """Get the radiative conductance of the cavity given emissivities on both sides.

        Args:
            emissivity_1: The emissivity of the surface on one side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            emissivity_2: The emissivity of the surface on the other side of the cavity.
                Default is 0.84, which is typical of clear, uncoated glass.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
        """
        return (
            (4 * 5.6697e-8)
            * (((1 / emissivity_1) + (1 / emissivity_2) - 1) ** -1)
            * (t_kelvin ** 3)
        )

    def nusselt_at_angle(
        self, delta_t=15, height=1.0, angle=90, t_kelvin=273.15, pressure=101325
    ):
        """Get Nusselt number for a cavity at a given angle, temp diff and height.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            angle: An angle in degrees between 0 and 180.
                * 0 = A horizontal cavity with downward heat flow through the layer.
                * 90 = A vertical cavity
                * 180 = A horizontal cavity with upward heat flow through the layer.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """

        def dot_x(x):
            return (x + abs(x)) / 2

        rayleigh = self.rayleigh(delta_t, t_kelvin, pressure)
        if angle < 60:
            cos_a = math.cos(math.radians(angle))
            sin_a_18 = math.sin(1.8 * math.radians(angle))
            term_1 = dot_x(1 - (1708 / (rayleigh * cos_a)))
            term_2 = 1 - ((1708 * (sin_a_18 ** 1.6)) / (rayleigh * cos_a))
            term_3 = dot_x(((rayleigh * cos_a) / 5830) ** (1 / 3) - 1)
            return 1 + (1.44 * term_1 * term_2) + term_3
        elif angle < 90:
            g = 0.5 / ((1 + ((rayleigh / 3160) ** 20.6)) ** 0.1)
            n_u1 = (1 + (((0.0936 * (rayleigh ** 0.314)) / (1 + g)) ** 7)) ** (1 / 7)
            n_u2 = (0.104 + (0.175 / (self.Thickness / height))) * (rayleigh ** 0.283)
            n_u_60 = max(n_u1, n_u2)
            n_u_90 = self.nusselt(delta_t, height, t_kelvin, pressure)
            return (n_u_60 + n_u_90) / 2
        elif angle == 90:
            return self.nusselt(delta_t, height, t_kelvin, pressure)
        else:
            n_u_90 = self.nusselt(delta_t, height, t_kelvin, pressure)
            return 1 + ((n_u_90 - 1) * math.sin(math.radians(angle)))

    def nusselt(self, delta_t=15, height=1.0, t_kelvin=273.15, pressure=101325):
        """Get Nusselt number for a vertical cavity given the temp diff. and height.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            height: An optional height for the cavity in meters. Default is 1.0,
                which is consistent with NFRC standards.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        rayleigh = self.rayleigh(delta_t, t_kelvin, pressure)
        if rayleigh > 50000:
            n_u_l_1 = 0.0673838 * (rayleigh ** (1 / 3))
        elif rayleigh > 10000:
            n_u_l_1 = 0.028154 * (rayleigh ** 0.4134)
        else:
            n_u_l_1 = 1 + 1.7596678e-10 * (rayleigh ** 2.2984755)
        n_u_l_2 = 0.242 * ((rayleigh * (self.Thickness / height)) ** 0.272)
        return max(n_u_l_1, n_u_l_2)

    def rayleigh(self, delta_t=15, t_kelvin=273.15, pressure=101325):
        """Get Rayleigh number given the temperature difference across the cavity.

        Args:
            delta_t: The temperature difference across the gas cavity [C]. Default is
                15C, which is consistent with the NFRC standard for double glazed units.
            t_kelvin: The average temperature of the gas cavity in Kelvin.
                Default: 273.15 K (0C).
            pressure: The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        _numerator = (
            (self.Material.density_at_temperature(t_kelvin, pressure) ** 2)
            * (self.Thickness ** 3)
            * 9.81
            * self.Material.specific_heat_at_temperature(t_kelvin)
            * delta_t
        )
        _denominator = (
            t_kelvin
            * self.Material.viscosity_at_temperature(t_kelvin)
            * self.Material.conductivity_at_temperature(t_kelvin)
        )
        return _numerator / _denominator

    def to_dict(self):
        """Return MaterialLayer dictionary representation."""
        return collections.OrderedDict(
            Material={"$ref": str(self.Material.id)},
            Thickness=round(self.Thickness, decimals=3),
        )

    def to_epbunch(self, idf):
        """Convert self to an epbunch given an IDF model.

        Notes:
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
        if not isinstance(other, GasLayer):
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
