################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import uuid

import numpy as np
from deprecation import deprecated
from eppy.bunch_subclass import BadEPFieldError

import archetypal
from archetypal.template import MaterialLayer, OpaqueMaterial, UmiBase, UniqueName


class ConstructionBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of
    constructions (eg.: wall assemblies).

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life
    -cycle-impact
    """

    __slots__ = (
        "_assembly_carbon",
        "_assembly_cost",
        "_assembly_energy",
        "_dissassembly_carbon",
        "_dissassembly_energy",
    )

    def __init__(
        self,
        AssemblyCarbon=0,
        AssemblyCost=0,
        AssemblyEnergy=0,
        DisassemblyCarbon=0,
        DisassemblyEnergy=0,
        **kwargs,
    ):
        """Initialize a ConstructionBase object with parameters:

        Args:
            AssemblyCarbon (float): assembly carbon [kgCO2/m2].
            AssemblyCost (float): assembly carbon [kgCO2/m2].
            AssemblyEnergy (float): assembly energy [MJ/m2].
            DisassemblyCarbon (float): disassembly carbon [kgCO2/m2].
            DisassemblyEnergy (float): disassembly energy [MJ/m2].
            **kwargs: keywords passed to UmiBase.
        """
        super(ConstructionBase, self).__init__(**kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy

    @property
    def AssemblyCarbon(self):
        """Get or set the assembly carbon [kgCO2/m2]."""
        return self._assembly_carbon

    @AssemblyCarbon.setter
    def AssemblyCarbon(self, value):
        self._assembly_carbon = float(value)

    @property
    def AssemblyCost(self):
        """Get or set the assembly cost [$/m2]."""
        return self._assembly_cost

    @AssemblyCost.setter
    def AssemblyCost(self, value):
        self._assembly_cost = float(value)

    @property
    def AssemblyEnergy(self):
        """Get or set the assembly energy [MJ/m2]."""
        return self._assembly_energy

    @AssemblyEnergy.setter
    def AssemblyEnergy(self, value):
        self._assembly_energy = float(value)

    @property
    def DisassemblyCarbon(self):
        """Get or set the disassembly carbon [kgCO2/m2]."""
        return self._dissassembly_carbon

    @DisassemblyCarbon.setter
    def DisassemblyCarbon(self, value):
        self._dissassembly_carbon = float(value)

    @property
    def DisassemblyEnergy(self):
        """Get or set the disassembly energy [MJ/m2]."""
        return self._dissassembly_energy

    @DisassemblyEnergy.setter
    def DisassemblyEnergy(self, value):
        self._dissassembly_energy = float(value)

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in ConstructionBase.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


class LayeredConstruction(ConstructionBase):
    """Defines the layers of an :class:`OpaqueConstruction`.

    Attributes:
        Layers (list of MaterialLayer): List of MaterialLayer objects from
            outside to inside.
    """

    def __init__(self, Layers, **kwargs):
        """Initialize object.

        Args:
            Layers (list of MaterialLayer): A list of :class:`MaterialLayer`
                objects.
            **kwargs: Keywords passed to the :class:`ConstructionBase`
                constructor.
        """
        super(LayeredConstruction, self).__init__(Layers=Layers, **kwargs)
        self.Layers = Layers


class OpaqueConstruction(LayeredConstruction):
    """Opaque Constructions

    .. image:: ../images/template/constructions-opaque.png

    Properties:
        * r_value
        * u_value
        * r_factor
        * u_factor
        * equivalent_heat_capacity_per_unit_volume
        * specific_heat
        * heat_capacity_per_unit_wall_area
        * total_thickness
        * mass_per_unit_area
        * timeconstant_per_unit_area
        * solar_reflectance_index
    """
    __slots__ = ()

    def __init__(self, Layers, **kwargs):
        """
        Args:
            Layers (list of MaterialLayer): List of MaterialLayers making up the
                construction.
            **kwargs: Other attributes passed to parent constructors such as
                :class:`ConstructionBase`.
        """
        super(OpaqueConstruction, self).__init__(Layers, **kwargs)
        self.area = 1

    @property
    def r_value(self):
        """Get or set the thermal resistance [K⋅m2/W] (excluding air films).

        Note that, when setting the R-value, the thickness of the inferred insulation
        layer will be adjusted.
        """
        return sum([layer.r_value for layer in self.Layers])

    @r_value.setter
    def r_value(self, value):
        # First, find the insulation layer
        i = self.infer_insulation_layer()
        all_layers_except_insulation_layer = [a for a in self.Layers]
        all_layers_except_insulation_layer.pop(i)
        insulation_layer: MaterialLayer = self.Layers[i]

        if value <= sum([a.r_value for a in all_layers_except_insulation_layer]):
            raise ValueError(
                f"Cannot set assembly r-value smaller than "
                f"{sum([a.r_value for a in all_layers_except_insulation_layer])} "
                f"because it would result in an insulation of a "
                f"negative thickness. Try a higher value or changing the material "
                f"layers instead."
            )

        alpha = float(value) / self.r_value
        new_r_value = (
            ((alpha - 1) * sum([a.r_value for a in all_layers_except_insulation_layer]))
        ) + alpha * insulation_layer.r_value
        insulation_layer.r_value = new_r_value

    @property
    def u_value(self):
        """Construction heat transfer coefficient [W/m2⋅K] (excluding air films)."""
        return 1 / self.r_value

    @property
    def r_factor(self):
        """Construction R-factor [m2-K/W] (including air films).

        inside film resistance = 8 [K⋅m2/W]
        outside film resistance = 20 [K⋅m2/W]
        """
        h_in = 8.0
        h_out = 20.0
        return 1 / h_out + self.r_value + 1 / h_in

    @property
    def u_factor(self):
        """Overall heat transfer coefficient (including air films) W/(m2⋅K)."""
        return 1 / self.r_factor

    @property
    def equivalent_heat_capacity_per_unit_volume(self):
        """Construction equivalent per unit wall **volume** heat capacity [J/(kg⋅K)].

        Hint:
            "The physical quantity which represents the heat storage capability
            is the wall heat capacity, defined as HC=M·c. While the per unit
            wall area of this quantity is (HC/A)=ρ·c·δ, where δ the wall
            thickness, the per unit volume wall heat capacity, being a
            characteristic wall quantity independent from the wall thickness, is
            equal to ρ·c. This quantity for a composite wall of an overall
            thickness L, is usually defined as the equivalent per unit wall
            volume heat capacity and it is expressed as
            :math:`{{(ρ·c)}}_{eq}{{=(1/L)·∑}}_{i=1}^n{{(ρ}}_i{{·c}}_i{{·δ}}_i{)}`
            where :math:`{ρ}_i`, :math:`{c}_i` and :math:`{δ}_i` are the
            densities, the specific heat capacities and the layer thicknesses of
            the n parallel layers of the composite wall." [ref]_

        .. [ref] Tsilingiris, P. T. (2004). On the thermal time constant of
            structural walls. Applied Thermal Engineering, 24(5–6), 743–757.
            https://doi.org/10.1016/j.applthermaleng.2003.10.015
        """
        return (1 / self.total_thickness) * sum(
            [
                layer.Material.Density * layer.Material.SpecificHeat * layer.Thickness
                for layer in self.Layers
            ]
        )

    @property
    def specific_heat(self):
        """Construction specific heat weighted by wall area mass [J/(kg⋅K)]."""
        return np.average(
            [layer.specific_heat for layer in self.Layers],
            weights=[layer.Thickness * layer.Material.Density for layer in self.Layers],
        )

    @property
    def heat_capacity_per_unit_wall_area(self):
        """Construction heat capacity per unit wall area [J/(m2⋅K)].

        Hint:
            :math:`(HC/A)=ρ·c·δ`, where :math:`δ` is the wall thickness.
        """
        return sum([layer.heat_capacity for layer in self.Layers])

    @property
    def total_thickness(self):
        """Construction total thickness [m]."""
        return sum([layer.Thickness for layer in self.Layers])

    @property
    def mass_per_unit_area(self):
        """Construction mass per unit area [kg/m2]."""
        return sum([layer.Thickness * layer.Material.Density for layer in self.Layers])

    @property
    def time_constant_per_unit_area(self):
        """Construction time constant per unit area."""
        return self.mass_per_unit_area * self.specific_heat / self.u_factor

    @property
    def solar_reflectance_index(self):
        """Construction's Solar Reflectance Index of the exposed surface.

        Hint:
            calculation from K-12 AEDG, derived from ASTM E1980 assuming medium wind
            speed.

        """
        exposedMaterial = self.Layers[0]  # 0-th layer is exterior layer
        solarAbsorptance = exposedMaterial.Material.SolarAbsorptance
        thermalEmissivity = exposedMaterial.Material.ThermalEmittance

        x = (20.797 * solarAbsorptance - 0.603 * thermalEmissivity) / (
            9.5205 * thermalEmissivity + 12.0
        )
        sri = 123.97 - 141.35 * x + 9.6555 * x * x

        return sri

    def infer_insulation_layer(self):
        """Return the material layer index that corresponds to the insulation layer."""
        return self.Layers.index(max(self.Layers, key=lambda x: x.r_value))

    def combine(self, other, method="dominant_wall", allow_duplicates=False):
        """Combine two OpaqueConstruction together.

        Args:
            other (OpaqueConstruction): The other OpaqueConstruction object to
                combine with.
            method (str): Equivalent wall assembly method. Only 'dominant_wall'
                is safe to use. 'constant_ufactor' is still weird in terms of
                respecting the thermal response of the walls and may cause
                conversion issues with Conduction Transfer Functions (CTFs) in
                EnergyPlus.

        Returns:
            (OpaqueConstruction): the combined ZoneLoad object.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        weights = [self.area, other.area]

        meta = self._get_predecessors_meta(other)
        # thicknesses & materials for self
        if method == "equivalent_volume":
            new_m, new_t = self.equivalent_volume(other)
        elif method == "constant_ufactor":
            new_m, new_t = self.constant_ufactor(other, weights)
        elif method == "dominant_wall":
            # simply return the dominant wall construction
            oc = self.dominant_wall(other, weights)
            return oc
        else:
            raise ValueError(
                'Possible choices are ["equivalent_volume", "constant_ufactor", '
                '"dominant_wall"]'
            )
        # layers for the new OpaqueConstruction
        layers = [MaterialLayer(mat, t) for mat, t in zip(new_m, new_t)]
        new_obj = self.__class__(**meta, Layers=layers, idf=self.idf)
        new_name = (
            "Combined Opaque Construction {{{}}} with u_value "
            "of {:,.3f} W/m2k".format(uuid.uuid1(), new_obj.u_value)
        )
        new_obj.rename(new_name)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        new_obj.area = sum(weights)
        return new_obj

    def equivalent_volume(self, other):
        """
        Todo:
            - Implement the 'equivalent_volume' method.

        Args:
            other:
        """
        raise NotImplementedError(
            '"equivalent_volume" method is not yet '
            "fully implemented. Please choose "
            '"constant_ufactor"'
        )

        self_t = np.array([mat.Thickness for mat in self.Layers])
        self_m = [mat.Material for mat in self.Layers]
        # thicknesses & materials for other
        other_t = np.array([mat.Thickness for mat in other.Layers])
        other_m = [mat.Material for mat in other.Layers]
        # thicknesses & materials for the new OpaqueConstruction
        new_t = np.append(self_t, other_t)
        new_t = new_t / 2
        new_m = self_m + other_m
        return new_m, new_t

    def dominant_wall(self, other, weights):
        """Simply returns dominant wall properties

        Args:
            other:
            weights:
        """
        oc = [
            x
            for _, x in sorted(
                zip([2, 1], [self, other]), key=lambda pair: pair[0], reverse=True
            )
        ][0]
        return oc

    def constant_ufactor(self, other, weights=None):
        """The constant u-factor method will produce an assembly that has the
        same u-value as an equivalent wall (weighted by wall area) but with a
        mixture of all unique layer materials

        Args:
            other (OpaqueConstruction): The other Construction.
            weights (array_like, optional): An array of weights associated with
                the self and other. Each value contributes to the average
                according to its associated weight. If `weights=None` , then all
                data are assumed to have a weight equal to one.
        """
        from scipy.optimize import minimize

        def obj_func(
            thicknesses,
            materials,
            expected_u_value,
            expected_specific_heat,
            expected_total_thickness,
        ):
            """Objective function for thickness evaluation"""

            u_value = 1 / sum(
                [
                    thickness / mat.Conductivity
                    for thickness, mat in zip(thicknesses, materials)
                ]
            )

            # Specific_heat: (J/kg K)
            h_calc = [
                mat.SpecificHeat for thickness, mat in zip(thicknesses, materials)
            ]

            # (kg/m3) x (m) = (kg/m2)
            mass_per_unit_area = [
                mat.Density * thickness
                for thickness, mat in zip(thicknesses, materials)
            ]
            specific_heat = np.average(h_calc, weights=mass_per_unit_area)
            return (
                (u_value - expected_u_value) ** 2
                + (specific_heat - expected_specific_heat) ** 2
                + (sum(thicknesses) - expected_total_thickness) ** 2
            )

        # U_eq is the weighted average of the wall u_values by their respected total
        # thicknesses. Here, the U_value does not take into account the convective heat
        # transfer coefficients.
        u_equivalent = np.average(
            [self.u_value, other.u_value],
            weights=[self.total_thickness, other.total_thickness],
        )

        # Get a set of all materials sorted by Material Density (descending order)
        materials = list(
            sorted(
                set(
                    [layer.Material for layer in self.Layers]
                    + [layer.Material for layer in other.Layers]
                ),
                key=lambda x: x.Density,
                reverse=True,
            )
        )

        # Setup weights
        if not weights:
            weights = [1.0, 1.0]

        # If weights is a list of zeros. This weight is used in the
        if not np.array(weights).any():
            weights = [1, 1]

        # Calculate the desired equivalent specific heat
        equi_spec_heat = np.average(
            [self.specific_heat, other.specific_heat], weights=weights
        )
        two_wall_thickness = np.average(
            [self.total_thickness, other.total_thickness], weights=weights
        )
        x0 = np.ones(len(materials))
        bnds = tuple([(0.003, None) for layer in materials])
        res = minimize(
            obj_func,
            x0,
            args=(materials, u_equivalent, equi_spec_heat, two_wall_thickness),
            bounds=bnds,
        )

        return np.array(materials), res.x

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
        # resolve Material objects from ref
        layers = kwargs.pop("Layers", None)
        oc = cls(Layers=layers, **kwargs)
        lys = [
            MaterialLayer(
                oc.get_ref(layer["Material"]),
                layer["Thickness"],
            )
            for layer in layers
        ]
        oc.Layers = lys

        return oc

    @classmethod
    def generic_internalmass(cls, idf, **kwargs):
        """

        Args:
            idf (IDF): The IDF model
            **kwargs:

        Returns:

        """
        mat = idf.anidfobject(
            key="Material".upper(),
            Name="Wood 6inch",
            Roughness="MediumSmooth",
            Thickness=0.15,
            Conductivity=0.12,
            Density=540,
            Specific_Heat=1210,
            Thermal_Absorptance=0.7,
            Visible_Absorptance=0.7,
        )
        return OpaqueConstruction(
            Name="InternalMass",
            idf=idf,
            Layers=[
                MaterialLayer(Material=OpaqueMaterial.from_epbunch(mat), Thickness=0.15)
            ],
            Category=kwargs.pop("Category", "InternalMass"),
            **kwargs,
        )

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Construct an OpaqueMaterial object given an epbunch with keys
        "BuildingSurface:Detailed" or "InternalMass"
        Args:
            epbunch (EpBunch):
            **kwargs:
        """
        name = epbunch.Name
        idf = kwargs.pop("idf", epbunch.theidf)
        # treat internalmass and surfaces differently
        if epbunch.key.lower() == "internalmass":
            layers = cls._internalmass_layer(epbunch)
            return cls(Name=name, Layers=layers, idf=idf, **kwargs)
        else:
            layers = cls._surface_layers(epbunch)
            return cls(Name=name, Layers=layers, idf=idf, **kwargs)

    @classmethod
    def _internalmass_layer(cls, epbunch):
        """Returns layers of an internal mass object.

        Args:
            epbunch (EpBunch): The InternalMass epobject.
        """
        constr_obj = epbunch.theidf.getobject("CONSTRUCTION", epbunch.Construction_Name)
        return cls._surface_layers(constr_obj)

    @classmethod
    def _surface_layers(cls, epbunch):
        """Retrieve layers for the OpaqueConstruction

        Args:
            epbunch (EpBunch): EP-Construction object
        """
        layers = []
        for layer in epbunch.fieldnames[2:]:
            # Iterate over the constructions layers
            material = epbunch.get_referenced_object(layer)
            if material:
                o = OpaqueMaterial.from_epbunch(material)
                try:
                    thickness = material.Thickness
                except BadEPFieldError:
                    thickness = o.Conductivity * material.Thermal_Resistance
                layers.append(MaterialLayer(Material=o, Thickness=thickness))
        return layers

    def to_json(self):
        """Convert class properties to dict"""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Layers"] = [lay.to_dict() for lay in self.Layers]
        data_dict["AssemblyCarbon"] = self.AssemblyCarbon
        data_dict["AssemblyCost"] = self.AssemblyCost
        data_dict["AssemblyEnergy"] = self.AssemblyEnergy
        data_dict["DisassemblyCarbon"] = self.DisassemblyCarbon
        data_dict["DisassemblyEnergy"] = self.DisassemblyEnergy
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = str(self.DataSource)
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def mapping(self):
        self.validate()

        return dict(
            Layers=self.Layers,
            AssemblyCarbon=self.AssemblyCarbon,
            AssemblyCost=self.AssemblyCost,
            AssemblyEnergy=self.AssemblyEnergy,
            DisassemblyCarbon=self.DisassemblyCarbon,
            DisassemblyEnergy=self.DisassemblyEnergy,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    @classmethod
    def generic(cls, idf=None):
        # 90.1-2007 Nonres 4B Int Wall
        """
        Args:
            idf:
        """
        om = OpaqueMaterial.generic(idf=idf)

        layers = [MaterialLayer(om, 0.0127), MaterialLayer(om, 0.0127)]  # half inch
        return cls(
            Name="90.1-2007 Nonres 6A Int Wall",
            Layers=layers,
            DataSource="ASHRAE 90.1-2007",
            idf=idf,
            Category="Partition",
        )

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueConstruction): The other OpaqueConstruction.
        """
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        if not isinstance(other, OpaqueConstruction):
            return NotImplemented
        else:
            return all([self.Layers == other.Layers])
