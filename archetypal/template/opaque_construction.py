################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

import numpy as np

from archetypal.template import Unique, MaterialLayer, \
    OpaqueMaterial, UmiBase


class ConstructionBase(UmiBase):
    """

    """

    def __init__(self, AssemblyCarbon=0, AssemblyCost=0, AssemblyEnergy=0,
                 DisassemblyCarbon=0, DisassemblyEnergy=0, **kwargs):
        """
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
    """

    """
    def __init__(self, Layers, **kwargs):
        """
        Args:
            Layers (list of MaterialLayer):
            **kwargs:
        """
        super(LayeredConstruction, self).__init__(Layers=Layers, **kwargs)
        self.Layers = Layers


class OpaqueConstruction(LayeredConstruction, metaclass=Unique):
    """Opaque Constructions

    .. image:: ../images/template/constructions-opaque.png

    """

    def __init__(self, Layers, Surface_Type=None,
                 Outside_Boundary_Condition=None,
                 IsAdiabatic=False, **kwargs):
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

    def combine(self, other, method='constant_ufactor'):
        """Combine two OpaqueConstruction together.

        Info:
            The returned OpaqueConstruction assumes the thickness of each
            constructions' materials is distributed equally.

        Args:
            other (OpaqueConstruction):
        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        # the new object's name
        name = " + ".join([self.Name, other.Name])
        # thicknesses & materials for self
        if method == 'equivalent_volume':
            new_m, new_t = self.equivalent_volume(other)
        elif method == 'constant_ufactor':
            new_m, new_t = self.constant_ufactor(other)
        else:
            raise ValueError(
                'Possible choices are ["equivalent_volume","constant_ufactor"]')
        # layers for the new OpaqueConstruction
        layers = [MaterialLayer(mat, t) for mat, t in zip(new_m, new_t)]
        new_attr = dict(Layers=layers,
                        Category=self._str_mean(other, attr='Category',
                                                append=False),
                        Comments=self._str_mean(other, attr='Comments',
                                                append=True),
                        DataSource=self._str_mean(other, attr='DataSource',
                                                  append=False)
                        )
        new_obj = self.__class__(Name=name, **new_attr)
        return new_obj

    def equivalent_volume(self, other):
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

    def constant_ufactor(self, other):
        self_t = np.array([mat.Thickness for mat in self.Layers])
        self_m = np.array([mat.Material for mat in self.Layers])
        self_k = np.array([mat.Material.Conductivity for mat in self.Layers])

        other_t = np.array([mat.Thickness for mat in other.Layers])
        other_m = np.array([mat.Material for mat in other.Layers])
        other_k = np.array([mat.Material.Conductivity for mat in other.Layers])

        factor = sum(self_t / self_k) / sum(other_t / other_k)

        new_t = np.append(self_t, other_t)
        new_t = new_t * factor
        new_m = np.append(self_m , other_m)
        return new_m, new_t

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        # resolve Material objects from ref
        layers = kwargs.pop('Layers')
        oc = cls(Layers=None, **kwargs)
        lys = [MaterialLayer(oc.get_ref(layer['Material']),
                             layer['Thickness'])
               for layer in layers]
        oc.Layers = lys

        return oc

    @classmethod
    def from_epbunch(cls, epbunch):
        # from the construction or internalmass object
        """
        Args:
            epbunch (EpBunch):
        """
        name = epbunch.Name
        # treat internalmass and surfaces differently
        if epbunch.key.lower() == 'internalmass':
            layers = cls._internalmass_layer(epbunch)
            return cls(Name=name, Layers=layers)
        else:
            layers = cls._surface_layers(epbunch)
            return cls(Name=name, Layers=layers)

    @classmethod
    def _internalmass_layer(cls, epbunch):
        """
        Args:
            epbunch:
        """
        validobjects = epbunch.getfieldidd_item('Construction_Name',
                                                'validobjects')
        found = False
        for key in validobjects:
            try:
                material = epbunch.theidf.getobject(key,
                                                    epbunch.Construction_Name)
                om = OpaqueMaterial.from_epbunch(material)
                found = True
            except AttributeError:
                pass
            else:
                layers = [MaterialLayer(**dict(Material=om,
                                               Thickness=om.Thickness))]
                return layers
        if not found:
            raise AttributeError("%s internalmass not found in IDF",
                                 epbunch.Name)

    @staticmethod
    def _surface_layers(c):
        """Retrieve layers for the OpaqueConstruction

        Args:
            c (EpBunch): EP-Construction object
        """
        layers = []
        field_idd = c.getfieldidd('Outside_Layer')
        validobjects = field_idd['validobjects']  # plausible layer types
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
                    layers.append(MaterialLayer(**dict(Material=o,
                                                       Thickness=o._thickness)))
            if not found:
                raise AttributeError("%s material not found in IDF" % layer)
        return layers

    def type_surface(self):
        """Takes a boundary and returns its corresponding umi-type"""

        # Floors
        if self.Surface_Type == 'Floor':
            if self.Outside_Boundary_Condition == 'Surface':
                self.Type = 3  # umi defined
            if self.Outside_Boundary_Condition == 'Ground':
                self.Type = 2  # umi defined
            if self.Outside_Boundary_Condition == 'Outdoors':
                self.Type = 4  # umi defined
            if self.Outside_Boundary_Condition == 'Adiabatic':
                self.Type = 5  # umi defined
                self.IsAdiabatic = True
            else:
                return ValueError(
                    'Cannot find Construction Type for "{}"'.format(self))

        # Roofs & Ceilings
        elif self.Surface_Type == 'Roof':
            self.Type = 1  # umi defined
        elif self.Surface_Type == 'Ceiling':
            self.Type = 3  # umi defined
        # Walls
        elif self.Surface_Type == 'Wall':
            if self.Outside_Boundary_Condition == 'Surface':
                self.Type = 5  # umi defined
            if self.Outside_Boundary_Condition == 'Outdoors':
                self.Type = 0  # umi defined
            if self.Outside_Boundary_Condition == 'Adiabatic':
                self.Type = 5  # umi defined
                self.IsAdiabatic = True
        else:
            raise ValueError(
                'Cannot find Construction Type for "{}"'.format(self))

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
    def generic(cls):
        # Generic Plaster Board
        om = OpaqueMaterial(Conductivity=0.17, SpecificHeat=800, Density=800,
                            Name='generic_Material')
        layers = [MaterialLayer(om, 0.0127)]  # half inch
        return cls(Name='generic plaster board half inch', Layers=layers)
