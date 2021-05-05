"""GasMaterial module."""

import collections

import numpy as np
from sigfig import round
from validator_collection import validators

from .material_base import MaterialBase


class GasMaterial(MaterialBase):
    """Gas Materials.

    .. image:: ../images/template/materials-gas.png
    """

    __slots__ = ("_type", "_conductivity", "_density")

    _GASTYPES = ("air", "argon", "krypton", "xenon", "sf6")

    def __init__(
        self, Name, Conductivity=None, Density=None, Category="Gases", **kwargs
    ):
        """Initialize object with parameters.

        Args:
            Name (str): The name of the GasMaterial.
            Conductivity (float): Thermal conductivity (W/m-K).
            Density (float): A number representing the density of the material
                in kg/m3. This is essentially the mass of one cubic meter of the
                material.
            Category (str): Category is set as "Gases" for GasMaterial.
            **kwargs: keywords passed to the MaterialBase constructor.
        """
        super(GasMaterial, self).__init__(Name, Category=Category, **kwargs)
        self.Type = Name.upper()
        self.Conductivity = Conductivity
        self.Density = Density

    @property
    def Type(self):
        """Get or set the gas type.

        Choices are ("Air", "Argon", "Krypton", "Xenon").
        """
        return self._type

    @Type.setter
    def Type(self, value):
        assert value.lower() in self._GASTYPES, (
            f"Invalid value '{value}' for material gas type. Gas type must be one "
            f"of the following:\n{self._GASTYPES}"
        )
        self._type = value

    @property
    def Conductivity(self):
        """Get or set the conductivity of the gas at 0C [W/m-K]."""
        return self._conductivity

    @Conductivity.setter
    def Conductivity(self, value):
        if value is not None:
            self._conductivity = validators.float(value, minimum=0)
        else:
            self._conductivity = self.conductivity_at_temperature(273.15)

    @property
    def Density(self):
        """Get or set the density of the gas."""
        return self._density

    @Density.setter
    def Density(self, value):
        """Density of the gas at 0C and sea-level pressure [J/kg-K]."""
        if value is not None:
            self._density = validators.float(value, minimum=0)
        else:
            self._density = self.density_at_temperature(273.15)

    @property
    def molecular_weight(self):
        """Get the molecular weight [kg/mol]."""
        import CoolProp.CoolProp as CP

        return CP.PropsSI("molemass", self.Type)

    @property
    def specific_heat(self):
        """Get the material layer's specific heat at 0C [J/kg-K]."""
        return self.specific_heat_at_temperature(273.15)

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create a GasMaterial from a dictionary.

        Args:
            data (dict): A python dictionary.
            **kwargs: keywords passed the MaterialBase constructor.
        """
        _id = data.pop("$id")
        return cls(id=_id, **data, **kwargs)

    def to_dict(self):
        """Return GasMaterial dictionary representation."""
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
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf, thickness):
        """Convert self to an epbunch given an idf model and a thickness.

        Args:
            idf (IDF): An IDF model.
            thickness (float): the thickness of the material.

        .. code-block:: python

            WindowMaterial:Gas,
                AIR_0.006_B_Dbl_Air_Cl,    !- Name
                AIR,                      !- Gas Type
                0.006;                    !- Thickness

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            "WINDOWMATERIAL:GAS",
            Name=self.Name,
            Gas_Type=self.Type,
            Thickness=thickness,
        )

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
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

    def density_at_temperature(self, t_kelvin, pressure=101325):
        """Get the density of the gas [kg/m3] at a given temperature and pressure.

        This method uses CoolProp to get the density.

        Args:
            t_kelvin (float): The average temperature of the gas cavity in Kelvin.
            pressure (float): The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        import CoolProp.CoolProp as CP

        return CP.PropsSI("Dmass", "T", t_kelvin, "P", pressure, self.Type)

    def specific_heat_at_temperature(self, t_kelvin, pressure=101325):
        """Get the specific heat of the gas [J/(kg-K)] at a given Kelvin temperature.

        This method uses CoolProp to get the density.

        Args:
            t_kelvin (float): The average temperature of the gas cavity in Kelvin.
            pressure (float): The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        import CoolProp.CoolProp as CP

        return CP.PropsSI("Cpmass", "T", t_kelvin, "P", pressure, self.Type)

    def viscosity_at_temperature(self, t_kelvin, pressure=101325):
        """Get the viscosity of the gas [kg/m-s] at a given Kelvin temperature.

        This method uses CoolProp to get the density.

        Args:
            t_kelvin (float): The average temperature of the gas cavity in Kelvin.
            pressure (float): The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        import CoolProp.CoolProp as CP

        try:
            return CP.PropsSI("viscosity", "T", t_kelvin, "P", pressure, self.Type)
        except ValueError:
            # ValueError: Viscosity model is not available for Krypton, Xenon
            return {"krypton": 2.3219e-5, "xenon": 2.1216e-5}[self.Type.lower()]

    def conductivity_at_temperature(self, t_kelvin, pressure=101325):
        """Get the conductivity of the gas [W/(m-K)] at a given Kelvin temperature.

        This method uses CoolProp to get the density. Note that the thermal
        conductivity model is not available for Krypton, Xenon gases. Values from the
        literature are used instead.

        Args:
            t_kelvin (float): The average temperature of the gas cavity in Kelvin.
            pressure (float): The average pressure of the gas cavity in Pa.
                Default is 101325 Pa for standard pressure at sea level.
        """
        import CoolProp.CoolProp as CP

        try:
            return CP.PropsSI("conductivity", "T", t_kelvin, "P", pressure, self.Type)
        except ValueError:
            # ValueError: Thermal conductivity model is not available for Krypton, Xenon
            return {"krypton": 0.00943, "xenon": 5.65e-3}[self.Type.lower()]

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
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

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping(validate=False))
