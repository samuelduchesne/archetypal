################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import uuid

import numpy as np

from archetypal import log
from archetypal.template import Unique, MaterialLayer, OpaqueMaterial, UmiBase


class ConstructionBase(UmiBase):
    """A class used to store data linked with the Life Cycle aspect of
    constructions (eg.: wall assemblies).

    For more information on the Life Cycle Analysis performed in UMI, see:
    https://umidocs.readthedocs.io/en/latest/docs/life-cycle-introduction.html#life-cycle-impact
    """

    def __init__(
        self,
        AssemblyCarbon=0,
        AssemblyCost=0,
        AssemblyEnergy=0,
        DisassemblyCarbon=0,
        DisassemblyEnergy=0,
        **kwargs
    ):
        """Initialize a ConstructionBase object with parameters:

        Args:
            AssemblyCarbon:
            AssemblyCost:
            AssemblyEnergy:
            DisassemblyCarbon:
            DisassemblyEnergy:
            **kwargs:
        """
        super(ConstructionBase, self).__init__(**kwargs)
        self.AssemblyCarbon = AssemblyCarbon
        self.AssemblyCost = AssemblyCost
        self.AssemblyEnergy = AssemblyEnergy
        self.DisassemblyCarbon = DisassemblyCarbon
        self.DisassemblyEnergy = DisassemblyEnergy


class LayeredConstruction(ConstructionBase):
    """Defines the layers of an :class:`OpaqueConstruction`. This class has one
    attribute:

    1. A list of :class:`MaterialLayer` objects.
    """

    def __init__(self, Layers, **kwargs):
        """
        Args:
            Layers (list of MaterialLayer): A list of :class:`MaterialLayer`
                objects.
            **kwargs: Keywords passed to the :class:`ConstructionBase`
                constructor.
        """
        super(LayeredConstruction, self).__init__(Layers=Layers, **kwargs)
        self.Layers = Layers


class OpaqueConstruction(LayeredConstruction, metaclass=Unique):
    """Opaque Constructions

    .. image:: ../images/template/constructions-opaque.png
    """

    def __init__(
        self,
        Layers,
        Surface_Type=None,
        Outside_Boundary_Condition=None,
        IsAdiabatic=False,
        **kwargs
    ):
        """
        Args:
            Layers (list of MaterialLayer):
            Surface_Type:
            Outside_Boundary_Condition:
            IsAdiabatic:
            **kwargs:
        """
        super(OpaqueConstruction, self).__init__(Layers, **kwargs)
        self.Surface_Type = Surface_Type
        self.Outside_Boundary_Condition = Outside_Boundary_Condition
        self.IsAdiabatic = IsAdiabatic

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other:
        """
        return self.combine(other)

    @property
    def r_value(self):
        """float: The Thermal Resistance of the :class:`OpaqueConstruction`"""
        return sum(
            [layer.Thickness / layer.Material.Conductivity for layer in self.Layers]
        )  # (K⋅m2/W)

    @property
    def u_value(self):
        """float: The overall heat transfer coefficient of the
        :class:`OpaqueConstruction`. Expressed in W/(m2⋅K)
        """
        return 1 / self.r_value

    def combine(self, other, weights=None, method="constant_ufactor"):
        """Combine two OpaqueConstruction together.

        Args:
            other (OpaqueConstruction): The other OpaqueConstruction object to
                combine with.
            weights (list-like, optional): A list-like object of len 2. If None,
                the weight is the same for both self and other.
            method (str): Equivalent wall assembly method. Only
                'constan_ufactor' is implemented for now.

        Returns:
            (OpaqueConstruction): the combined ZoneLoad object.
        """
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

        if not weights:
            log(
                'using 1 as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [1.0, 1.0]

        meta = self._get_predecessors_meta(other)
        # thicknesses & materials for self
        if method == "equivalent_volume":
            new_m, new_t = self.equivalent_volume(other)
        elif method == "constant_ufactor":
            new_m, new_t = self.constant_ufactor(other, weights)
        else:
            raise ValueError(
                'Possible choices are ["equivalent_volume","constant_ufactor"]'
            )
        # layers for the new OpaqueConstruction
        layers = [MaterialLayer(mat, t) for mat, t in zip(new_m, new_t)]
        new_obj = self.__class__(**meta, Layers=layers)
        new_name = (
            "Combined Opaque Construction {{{}}} with u_value "
            "of {:,.3f} W/m2k".format(uuid.uuid1(), new_obj.u_value)
        )
        new_obj.rename(new_name)
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
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

        def obj_func(thicknesses, materials, expected):
            calc = 1 / sum(
                [
                    thickness / mat.Conductivity
                    for thickness, mat in zip(thicknesses, materials)
                ]
            )
            return (calc - expected) ** 2

        if not weights:
            weights = [1.0, 1.0]

        # If weights is a list of zeros
        if not np.array(weights).any():
            weights = [1, 1]

        equi_u = np.average([self.u_value, other.u_value], weights=weights)

        materials = set(
            [layer.Material for layer in self.Layers]
            + [layer.Material for layer in other.Layers]
        )

        from scipy.optimize import minimize

        x0 = np.ones(len(materials))
        bnds = tuple([(0.003, None) for layer in materials])
        res = minimize(obj_func, x0, args=(materials, equi_u), bounds=bnds)

        return np.array(list(materials)), res.x

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        # resolve Material objects from ref
        layers = kwargs.pop("Layers")
        oc = cls(Layers=None, **kwargs)
        lys = [
            MaterialLayer(oc.get_ref(layer["Material"]), layer["Thickness"])
            for layer in layers
        ]
        oc.Layers = lys

        return oc

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        # from the construction or internalmass object
        """
        Args:
            epbunch (EpBunch):
            **kwargs:
        """
        name = epbunch.Name
        idf = kwargs.pop("idf", epbunch.theidf)
        # treat internalmass and surfaces differently
        if epbunch.key.lower() == "internalmass":
            layers = cls._internalmass_layer(epbunch)
            return cls(Name=name, Layers=layers, idf=idf)
        else:
            layers = cls._surface_layers(epbunch)
            return cls(Name=name, Layers=layers, idf=idf, **kwargs)

    @classmethod
    def _internalmass_layer(cls, epbunch):
        """
        Args:
            epbunch:
        """

        layers = []
        constr_obj = epbunch.theidf.getobject("CONSTRUCTION", epbunch.Construction_Name)
        field_idd = constr_obj.getfieldidd("Outside_Layer")
        validobjects = field_idd["validobjects"]  # plausible layer types
        for layer in constr_obj.fieldvalues[2:]:
            # Iterate over the constructions layers
            found = False
            for key in validobjects:
                try:
                    material = constr_obj.theidf.getobject(key, layer)
                    o = OpaqueMaterial.from_epbunch(material)
                    found = True
                except AttributeError:
                    pass
                else:
                    layers.append(
                        MaterialLayer(**dict(Material=o, Thickness=o._thickness))
                    )
            if not found:
                raise AttributeError("%s material not found in IDF" % layer)
        return layers

    @staticmethod
    def _surface_layers(c):
        """Retrieve layers for the OpaqueConstruction

        Args:
            c (EpBunch): EP-Construction object
        """
        layers = []
        field_idd = c.getfieldidd("Outside_Layer")
        validobjects = field_idd["validobjects"]  # plausible layer types
        for layer in c.fieldvalues[2:]:
            # Iterate over the constructions layers
            found = False
            for key in validobjects:
                try:
                    material = c.theidf.getobject(key, layer)
                    o = OpaqueMaterial.from_epbunch(material)
                    found = True
                except AttributeError:
                    pass
                else:
                    layers.append(
                        MaterialLayer(**dict(Material=o, Thickness=o._thickness))
                    )
            if not found:
                raise AttributeError("%s material not found in IDF" % layer)
        return layers

    def to_json(self):
        """Convert class properties to dict"""
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
        data_dict["Name"] = str(self.Name)

        return data_dict

    @classmethod
    def generic(cls, idf=None):
        # Generic Plaster Board
        """
        Args:
            idf:
        """
        om = OpaqueMaterial(
            Conductivity=0.17,
            SpecificHeat=800,
            Density=800,
            Name="generic_Material",
            idf=idf,
        )
        layers = [MaterialLayer(om, 0.0127)]  # half inch
        return cls(Name="generic plaster board half inch", Layers=layers, idf=idf)
