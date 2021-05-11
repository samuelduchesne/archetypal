"""archetypal OpaqueConstruction."""

import collections
import uuid

import numpy as np
from eppy.bunch_subclass import BadEPFieldError
from validator_collection import validators

from archetypal.template.constructions.base_construction import LayeredConstruction
from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.materials.opaque_material import OpaqueMaterial


class OpaqueConstruction(LayeredConstruction):
    """Opaque Constructions.

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

    __slots__ = ("area",)

    def __init__(self, Name, Layers, **kwargs):
        """Initialize an OpaqueConstruction.

        Args:
            Layers (list of archetypal.MaterialLayer): List of MaterialLayers making
                up the construction.
            **kwargs: Other attributes passed to parent constructors such as
                :class:`ConstructionBase`.
        """
        super(OpaqueConstruction, self).__init__(Name, Layers, **kwargs)
        self.area = 1

    @property
    def r_value(self):
        """Get or set the thermal resistance [K⋅m2/W] (excluding air films).

        Note that, when setting the R-value, the thickness of the inferred
        insulation layer will be adjusted.
        """
        return super(OpaqueConstruction, self).r_value

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
    def equivalent_heat_capacity_per_unit_volume(self):
        """Get the equivalent per unit wall volume heat capacity [J/(kg⋅K)].

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
        """Get the construction specific heat weighted by wall area mass [J/(kg⋅K)]."""
        return np.average(
            [layer.specific_heat for layer in self.Layers],
            weights=[layer.Thickness * layer.Material.Density for layer in self.Layers],
        )

    @property
    def heat_capacity_per_unit_wall_area(self):
        """Get the construction heat capacity per unit wall area [J/(m2⋅K)].

        Hint:
            :math:`(HC/A)=ρ·c·δ`, where :math:`δ` is the wall thickness.
        """
        return sum([layer.heat_capacity for layer in self.Layers])

    @property
    def total_thickness(self):
        """Get the construction total thickness [m]."""
        return sum([layer.Thickness for layer in self.Layers])

    @property
    def mass_per_unit_area(self):
        """Get the construction mass per unit area [kg/m2]."""
        return sum([layer.Thickness * layer.Material.Density for layer in self.Layers])

    @property
    def time_constant_per_unit_area(self):
        """Get the construction time constant per unit area [seconds/m2]."""
        return self.mass_per_unit_area * self.specific_heat / self.u_factor

    @property
    def solar_reflectance_index(self):
        """Get the Solar Reflectance Index of the exposed surface.

        Hint:
            calculation from K-12 AEDG, derived from ASTM E1980 assuming medium wind
            speed.

        """
        exposed_material = self.Layers[0]  # 0-th layer is exterior layer
        solar_absorptance = exposed_material.Material.SolarAbsorptance
        thermal_emissivity = exposed_material.Material.ThermalEmittance

        x = (20.797 * solar_absorptance - 0.603 * thermal_emissivity) / (
            9.5205 * thermal_emissivity + 12.0
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
        if method == "constant_ufactor":
            new_m, new_t = self._constant_ufactor(other, weights)
        elif method == "dominant_wall":
            # simply return the dominant wall construction
            oc = self.dominant_wall(other, weights)
            return oc
        else:
            raise ValueError(
                'Possible choices are ["constant_ufactor", "dominant_wall"]'
            )
        # layers for the new OpaqueConstruction
        layers = [MaterialLayer(mat, t) for mat, t in zip(new_m, new_t)]
        new_obj = self.__class__(**meta, Layers=layers)
        new_name = (
            "Combined Opaque Construction {{{}}} with u_value "
            "of {:,.3f} W/m2k".format(uuid.uuid1(), new_obj.u_value)
        )
        new_obj.rename(new_name)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        new_obj.area = sum(weights)
        return new_obj

    def dominant_wall(self, other, weights):
        """Return dominant wall construction between self and other.

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

    def _constant_ufactor(self, other, weights=None):
        """Return materials and thicknesses for constant u-value.

        The constant u-factor method will produce an assembly that has the
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
            """Objective function for thickness evaluation."""
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
    def from_dict(cls, data, materials, **kwargs):
        """Create an OpaqueConstruction from a dictionary.

        Args:
            data (dict): The python dictionary.
            materials (dict): A dictionary of materials with their id as keys.

        .. code-block:: python

            materials = {}  # dict of materials.
            data = {
                 "$id": "140300770659680",
                 "Layers": [
                  {
                   "Material": {
                    "$ref": "140300653743792"
                   },
                   "Thickness": 0.013
                  },
                  {
                   "Material": {
                    "$ref": "140300653743792"
                   },
                   "Thickness": 0.013
                  }
                 ],
                 "AssemblyCarbon": 0.0,
                 "AssemblyCost": 0.0,
                 "AssemblyEnergy": 0.0,
                 "DisassemblyCarbon": 0.0,
                 "DisassemblyEnergy": 0.0,
                 "Category": "Partition",
                 "Comments": "",
                 "DataSource": "ASHRAE 90.1-2007",
                 "Name": "90.1-2007 Nonres 6A Int Wall"
            }

        """
        # resolve Material objects from ref
        layers = [
            MaterialLayer(
                Material=materials[layer["Material"]["$ref"]],
                Thickness=layer["Thickness"],
            )
            for layer in data.pop("Layers")
        ]
        _id = data.pop("$id")
        oc = cls(Layers=layers, id=_id, **data, **kwargs)

        return oc

    @classmethod
    def generic_internalmass(cls, **kwargs):
        """Create a generic internal mass object.

        Args:
            **kwargs: keywords passed to the class constructor.
        """
        mat = OpaqueMaterial(
            Name="Wood 6inch",
            Roughness="MediumSmooth",
            Thickness=0.15,
            Conductivity=0.12,
            Density=540,
            SpecificHeat=1210,
            ThermalAbsorptance=0.7,
            VisibleAbsorptance=0.7,
        )
        return OpaqueConstruction(
            Name="InternalMass",
            Layers=[MaterialLayer(Material=mat, Thickness=0.15)],
            Category="InternalMass",
            **kwargs,
        )

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Create an OpaqueConstruction object from an epbunch.

        Possible keys are "BuildingSurface:Detailed" or "InternalMass"

        Args:
            epbunch (EpBunch): The epbunch object.
            **kwargs: keywords passed to the LayeredConstruction constructor.
        """
        assert epbunch.key.lower() in ("internalmass", "construction"), (
            f"Expected ('Internalmass', 'Construction')." f"Got '{epbunch.key}'."
        )
        name = epbunch.Name

        # treat internalmass and regular surfaces differently
        if epbunch.key.lower() == "internalmass":
            layers = cls._internalmass_layer(epbunch)
            return cls(Name=name, Layers=layers, **kwargs)
        elif epbunch.key.lower() == "construction":
            layers = cls._surface_layers(epbunch)
            return cls(Name=name, Layers=layers, **kwargs)

    @classmethod
    def _internalmass_layer(cls, epbunch):
        """Return layers of an internal mass object.

        Args:
            epbunch (EpBunch): The InternalMass epobject.
        """
        constr_obj = epbunch.theidf.getobject("CONSTRUCTION", epbunch.Construction_Name)
        return cls._surface_layers(constr_obj)

    @classmethod
    def _surface_layers(cls, epbunch):
        """Retrieve layers for the OpaqueConstruction.

        Args:
            epbunch (EpBunch): EP-Construction object
        """
        layers = []
        for layer in epbunch.fieldnames[2:]:
            # Iterate over the construction's layers
            material = epbunch.get_referenced_object(layer)
            if material:
                o = OpaqueMaterial.from_epbunch(material, allow_duplicates=True)
                try:
                    thickness = material.Thickness
                except BadEPFieldError:
                    thickness = o.Conductivity * material.Thermal_Resistance
                layers.append(MaterialLayer(Material=o, Thickness=thickness))
        return layers

    def to_dict(self):
        """Return OpaqueConstruction dictionary representation."""
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
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = str(self.DataSource)
        data_dict["Name"] = self.Name

        return data_dict

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
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
    def generic(cls, **kwargs):
        """Return OpaqueConstruction based on 90.1-2007 Nonres 4B Int Wall."""
        om = OpaqueMaterial.generic()

        layers = [MaterialLayer(om, 0.0127), MaterialLayer(om, 0.0127)]  # half inch
        return cls(
            Name="90.1-2007 Nonres 6A Int Wall",
            Layers=layers,
            DataSource="ASHRAE 90.1-2007",
            Category="Partition",
            **kwargs,
        )

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other (OpaqueConstruction): The other OpaqueConstruction.
        """
        return self.combine(other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, OpaqueConstruction):
            return NotImplemented
        else:
            return all([self.Layers == other.Layers])

    def __copy__(self):
        """Create a copy of self."""
        new_con = self.__class__(Name=self.Name, Layers=[a for a in self.Layers])
        return new_con

    def to_epbunch(self, idf):
        """Get a Construction EpBunch given an idf model.

        Notes:
            Will create layered materials as well.

        Args:
            idf (IDF): An idf model to add the EpBunch in.

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            key="CONSTRUCTION",
            Name=self.Name,
            Outside_Layer=self.Layers[0].to_epbunch(idf).Name,
            **{
                f"Layer_{i+2}": layer.to_epbunch(idf).Name
                for i, layer in enumerate(self.Layers[1:])
            },
        )
