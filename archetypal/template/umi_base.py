################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import random

import numpy as np

from archetypal import log


class Unique(type):

    def __call__(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        key = (cls.mro()[0].__name__, kwargs['Name'])
        if key not in created_obj:
            self = cls.__new__(cls, *args, **kwargs)
            cls.__init__(self, *args, **kwargs)
            cls._cache[key] = self
            created_obj[key] = self
        return created_obj[key]

    def __init__(cls, name, bases, attributes):
        """
        Args:
            name:
            bases:
            attributes:
        """
        super().__init__(name, bases, attributes)
        cls._cache = {}


class UmiBase(object):
    def __init__(self,
                 Name,
                 idf=None,
                 Category='Uncategorized',
                 Comments=None,
                 DataSource=None,
                 sql=None,
                 **kwargs):
        """The UmiBase class handles common properties to all Template objects.

        Args:
            Name (str): Unique, the name of the object.
            idf (IDF): The idf object associated to this object.
            Category (str): Group objects by assigning the same category
                identifier. Thies can be any string.
            Comments (str): A comment displayed in the UmiTemplate.
            DataSource (str): A description of the datasource of the object.
                This helps identify from which data is the current object
                created.
            sql (dict of pandas.DataFrame):
            **kwargs:
        """
        super(UmiBase, self).__init__()
        self.Name = Name
        self.idf = idf
        self.sql = sql
        self.Category = Category
        self.Comments = ''
        try:
            self.Comments += Comments
        except:
            self.Comments = Comments
        if DataSource is None:
            try:
                self.DataSource = self.idf.building_name(use_idfname=True)
            except:
                self.DataSource = DataSource
        else:
            self.DataSource = DataSource
        self.all_objects = created_obj
        self.id = kwargs.get('$id', id(self))

    def __str__(self):
        """string representation of the object as id:Name"""
        return ':'.join([str(self.id), str(self.Name)])

    def to_json(self):
        """Convert class properties to dict"""
        return {"$id": "{}".format(self.id),
                "Name": "{}".format(self.Name)}

    def get_ref(self, ref):
        """Gets item matching ref id

        Args:
            ref:
        """
        return [self.all_objects[obj]
                for obj in self.all_objects
                if self.all_objects[obj].id == ref['$ref']][0]

    def get_random_schedule(self):
        """Return a random YearSchedule from cache"""
        return random.choice([self.all_objects[obj] for obj in
                              self.all_objects if 'YearSchedule' in obj])

    def __hash__(self):
        return hash(self.Name)

    def to_dict(self):
        return {'$ref': str(self.id)}

    def _float_mean(self, other, attr, weights=None):
        """Calculates the average attribute value of two floats. Can provide
        weights.

        Args:
            other (UmiBase): The other UmiBase object to calculate average value
                with.
            attr (str): The attribute of the UmiBase object.
            weights (iterable, optional): Weights of [self, other] to calculate
                weighted average.
        """
        if self.__dict__[attr] is None and other.__dict__[attr] is None:
            return None
        else:
            try:
                return np.average([self.__dict__[attr],
                                   other.__dict__[attr]], weights=weights)
            except:
                pass

    def _str_mean(self, other, attr, append=False):
        """Returns the combined string attributes

        Args:
            other (UmiBase): The other UmiBase object to calculate combined
                string.
            attr (str): The attribute of the UmiBase object.
            append (bool): Whether or not the attributes should be combined
                together. If False, the attribute of self will is used (other is
                ignored).
        """
        # if self has info, but other is none, use self
        if self.__dict__[attr] is not None and other.__dict__[attr] is None:
            return self.__dict__[attr]
        # if self is none, but other is not none, use other
        elif self.__dict__[attr] is None and other.__dict__[attr] is not None:
            return other.__dict__[attr]
        # if both are not note, impose self
        elif self.__dict__[attr] and other.__dict__[attr]:
            if append:
                return self.__dict__[attr] + other.__dict__[attr]
            else:
                return self.__dict__[attr]
        # if both are None, return None
        else:
            return None

    def __iadd__(self, other):
        """Overload += to implement self.extend.

        Args:
            other:
        """
        return self.extend(other)

    def extend(self, other):
        """Append other to self. Modify and return self.

        Args (UmiBase):

        Args:
            other:

        Returns:
            UmiBase: self
        """
        new_obj = self + other
        new_obj.__dict__.pop('id')
        name = new_obj.__dict__.pop('Name')
        self.__dict__.update(**new_obj.__dict__)
        self.all_objects.pop((self.__class__.__name__, name))
        return self

    def __radd__(self, other):
        """
        Args:
            other:
        """
        return self + other


class MaterialBase(UmiBase):
    def __init__(self, Cost=0, EmbodiedCarbon=0, EmbodiedEnergy=0,
                 SubstitutionTimestep=0, TransportCarbon=0, TransportDistance=0,
                 TransportEnergy=0, SubstitutionRatePattern=None,
                 Conductivity=2.4, Density=2400,
                 **kwargs):
        """
        Args:
            Cost (float):
            EmbodiedCarbon (float):
            EmbodiedEnergy (float):
            SubstitutionTimestep (float):
            TransportCarbon (float):
            TransportDistance (float):
            TransportEnergy (float):
            SubstitutionRatePattern (list):
            Conductivity (float):
            Density (float):
            **kwargs: Keywords passed to the base class :class:`UmiBase`
        """
        super(MaterialBase, self).__init__(**kwargs)
        if SubstitutionRatePattern is None:
            SubstitutionRatePattern = [1.0]
        self.Conductivity = Conductivity
        self.Cost = Cost
        self.Density = Density
        self.EmbodiedCarbon = EmbodiedCarbon
        self.EmbodiedEnergy = EmbodiedEnergy
        self.SubstitutionRatePattern = SubstitutionRatePattern
        self.SubstitutionTimestep = SubstitutionTimestep
        self.TransportCarbon = TransportCarbon
        self.TransportDistance = TransportDistance
        self.TransportEnergy = TransportEnergy

    def __eq__(self, other):
        if isinstance(other, MaterialBase):
            return \
                self.Name == other.Name and \
                self.Conductivity == other.Conductivity and \
                self.Cost == other.Cost and \
                self.Density == other.Density and \
                self.EmbodiedCarbon == other.EmbodiedCarbon and \
                self.EmbodiedEnergy == other.EmbodiedEnergy and \
                self.SubstitutionRatePattern == other.SubstitutionRatePattern \
                and \
                self.SubstitutionTimestep == other.SubstitutionTimestep and \
                self.TransportCarbon == other.TransportCarbon and \
                self.TransportDistance == other.TransportDistance and \
                self.TransportEnergy == other.TransportEnergy
        else:
            raise NotImplementedError

    def __hash__(self):
        return hash((self.Density,
                     self.EmbodiedCarbon,
                     self.EmbodiedEnergy,
                     ' '.join(map(str, self.SubstitutionRatePattern)),
                     self.SubstitutionTimestep,
                     self.TransportCarbon,
                     self.TransportDistance,
                     self.TransportEnergy))


created_obj = {}


class MaterialLayer(object):
    def __init__(self, Material, Thickness):
        """
        Args:
            Material (archetypal.template.opaque_material.OpaqueMaterial):
            Thickness (float): The thickness of the material in the
                construction.
        """
        if Thickness < 0.003:
            log(
                'Modeling layers thinner (less) than 0.003 m is not '
                'recommended; rather, add those properties to one of the '
                'adjacent layers. Layer "%s"' % Material.Name, lg.WARNING)
        self.Thickness = Thickness
        self.Material = Material

    def to_dict(self):
        return collections.OrderedDict(Material={'$ref': str(self.Material.id)},
                                       Thickness=self.Thickness)
