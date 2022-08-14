"""archetypal UmiBase module."""

import itertools
import math
import networkx as nx
from collections.abc import Hashable, MutableSet

import numpy as np
from validator_collection import validators

from archetypal.utils import lcm


def _resolve_combined_names(predecessors):
    """Creates a unique name from the list of :class:`UmiBase` objects
    (predecessors)

    Args:
        predecessors (MetaData):
    """

    # all_names = [obj.Name for obj in predecessors]
    class_ = list(set([obj.__class__.__name__ for obj in predecessors]))[0]

    return "Combined_%s_%s" % (
        class_,
        str(hash((pre.Name for pre in predecessors))).strip("-"),
    )


def _shorten_name(long_name):
    """Check if name is longer than 300 characters, and return truncated version

    Args:
        long_name (str): A long name (300 char+) to shorten.
    """
    if len(long_name) > 300:
        # shorten name if longer than 300 characters (limit set by
        # EnergyPlus)
        return long_name[:148] + (long_name[148:] and " .. ")
    else:
        return long_name


class UmiBase(object):
    """Base class for template objects."""

    _GRAPH = nx.MultiDiGraph()
    __slots__ = (
        "_id",
        "_datasource",
        "_predecessors",
        "_name",
        "_category",
        "_comments",
        "_allow_duplicates",
        "_unit_number",
        "_parents",
    )
    _ids = itertools.count(0)  # unique id for each class instance

    def __init__(
        self,
        Name,
        Category="Uncategorized",
        Comments="",
        DataSource=None,
        allow_duplicates=False,
        **kwargs,
    ):
        """The UmiBase class handles common properties to all Template objects.

        Args:
            Name (str): Unique, the name of the object.
            Category (str): Group objects by assigning the same category
                identifier. Thies can be any string.
            Comments (str): A comment displayed in the UmiTemplateLibrary.
            DataSource (str): A description of the datasource of the object.
                This helps identify from which data is the current object
                created.
            allow_duplicates (bool): If True, this object can be equal to another one
                if it has a different name.
            **kwargs:
        """

        self.Name = Name
        self.Category = Category
        self.Comments = Comments
        self.DataSource = DataSource

        self.id = kwargs.get("id", None)
        self.allow_duplicates = allow_duplicates
        self.unit_number = next(self._ids)
        self.predecessors = None
        self._parents = nx.MultiDiGraph()

    @property
    def Name(self):
        """Get or set the name of the object."""
        return self._name

    @Name.setter
    def Name(self, value):
        self._name = validators.string(value, coerce_value=True)

    @property
    def id(self):
        """Get or set the id."""
        return self._id

    @id.setter
    def id(self, value):
        if value is None:
            value = id(self)
        self._id = validators.string(value, coerce_value=True)

    @property
    def DataSource(self):
        """Get or set the datasource of the object."""
        return self._datasource

    @DataSource.setter
    def DataSource(self, value):
        self._datasource = validators.string(value, coerce_value=True, allow_empty=True)

    @property
    def Category(self):
        """Get or set the Category attribute."""
        return self._category

    @Category.setter
    def Category(self, value):
        value = validators.string(value, coerce_value=True, allow_empty=True)
        if value is None:
            value = ""
        self._category = value

    @property
    def Comments(self):
        """Get or set the object comments."""
        return self._comments

    @Comments.setter
    def Comments(self, value):
        value = validators.string(value, coerce_value=True, allow_empty=True)
        if value is None:
            value = ""
        self._comments = value

    @property
    def allow_duplicates(self):
        """Get or set the use of duplicates [bool]."""
        return self._allow_duplicates

    @allow_duplicates.setter
    def allow_duplicates(self, value):
        assert isinstance(value, bool), value
        self._allow_duplicates = value

    @property
    def unit_number(self):
        return self._unit_number

    @unit_number.setter
    def unit_number(self, value):
        self._unit_number = validators.integer(value)

    @property
    def predecessors(self):
        """Get or set the predecessors of self.

        Of which objects is self made of. If from nothing else then self,
        return self.
        """
        if self._predecessors is None:
            self._predecessors = MetaData([self])
        return self._predecessors

    @predecessors.setter
    def predecessors(self, value):
        self._predecessors = value

    @property
    def children(self):
        return ()

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def _get_predecessors_meta(self, other):
        """get predecessor objects to self and other

        Args:
            other (UmiBase): The other object.
        """
        predecessors = self.predecessors + other.predecessors
        meta = self.combine_meta(predecessors)

        return meta

    def combine_meta(self, predecessors):
        return {
            "Name": _resolve_combined_names(predecessors),
            "Comments": (
                "Object composed of a combination of these "
                "objects:\n{}".format(
                    "\n- ".join(set(obj.Name for obj in predecessors))
                )
            ),
            "Category": ", ".join(
                set(
                    itertools.chain(*[obj.Category.split(", ") for obj in predecessors])
                )
            ),
            "DataSource": ", ".join(
                set(
                    itertools.chain(
                        *[
                            obj.DataSource.split(", ")
                            for obj in predecessors
                            if obj.DataSource is not None
                        ]
                    )
                )
            ),
        }

    def combine(self, other, allow_duplicates=False):
        pass

    def rename(self, name):
        """renames self as well as the cached object

        Args:
            name (str): the name.
        """
        self.Name = name

    def to_dict(self):
        """Return UmiBase dictionary representation."""
        return {"$id": "{}".format(self.id), "Name": "{}".format(self.Name)}

    def get_ref(self, ref):
        pass

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __repr__(self):
        """Return a representation of self."""
        return ":".join([str(self.id), str(self.Name)])

    def __str__(self):
        """string representation of the object as id:Name"""
        return self.__repr__()

    def __iter__(self):
        """Iterate over attributes. Yields tuple of (keys, value)."""
        for attr, value in self.mapping().items():
            yield attr, value

    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(**self.mapping(validate=False))

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}

    def float_mean(self, other, attr, weights=None):
        """Calculates the average attribute value of two floats. Can provide
        weights.

        Args:
            other (UmiBase): The other UmiBase object to calculate average value
                with.
            attr (str): The attribute of the UmiBase object.
            weights (iterable, optional): Weights of [self, other] to calculate
                weighted average.
        """
        if getattr(self, attr) is None:
            return getattr(other, attr)
        if getattr(other, attr) is None:
            return getattr(self, attr)
        # If weights is a list of zeros
        if not np.array(weights).any():
            weights = [1, 1]

        if not isinstance(getattr(self, attr), list) and not isinstance(
            getattr(other, attr), list
        ):
            if math.isnan(getattr(self, attr)):
                return getattr(other, attr)
            elif math.isnan(getattr(other, attr)):
                return getattr(self, attr)
            elif math.isnan(getattr(self, attr)) and math.isnan(getattr(other, attr)):
                raise ValueError("Both values for self and other are Not A Number.")
            else:
                return float(
                    np.average(
                        [getattr(self, attr), getattr(other, attr)], weights=weights
                    )
                )
        elif getattr(self, attr) is None and getattr(other, attr) is None:
            return None
        else:
            # handle arrays by finding the least common multiple of the two arrays and
            # tiling to the full length; then, apply average
            self_attr_ = np.array(getattr(self, attr))
            other_attr_ = np.array(getattr(other, attr))
            l_ = lcm(len(self_attr_), len(other_attr_))
            self_attr_ = np.tile(self_attr_, int(l_ / len(self_attr_)))
            other_attr_ = np.tile(other_attr_, int(l_ / len(other_attr_)))
            return np.average([self_attr_, other_attr_], weights=weights, axis=0)

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
        if self is None:
            return other
        if other is None:
            return self
        # if self has info, but other is none, use self
        if getattr(self, attr) is not None and getattr(other, attr) is None:
            return getattr(self, attr)
        # if self is none, but other is not none, use other
        elif getattr(self, attr) is None and getattr(other, attr) is not None:
            return getattr(other, attr)
        # if both are not note, impose self
        elif getattr(self, attr) and getattr(other, attr):
            if append:
                return getattr(self, attr) + getattr(other, attr)
            else:
                return getattr(self, attr)
        # if both are None, return None
        else:
            return None

    def __iadd__(self, other):
        """Overload += to implement self.extend.

        Args:
            other:
        """
        return UmiBase.extend(self, other, allow_duplicates=True)

    def extend(self, other, allow_duplicates):
        """Append other to self. Modify and return self.

        Args:
            other (UmiBase):

        Returns:
            UmiBase: self
        """
        if self is None:
            return other
        if other is None:
            return self
        self._CREATED_OBJECTS.remove(self)
        id = self.id
        new_obj = self.combine(other, allow_duplicates=allow_duplicates)
        new_obj.id = id
        for key in self.mapping(validate=False):
            setattr(self, key, getattr(new_obj, key))
        return self

    def validate(self):
        """Validate UmiObjects and fills in missing values."""
        return self

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            # id=self.id,
            Name=self.Name,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
        )

    def get_unique(self):
        """Return first object matching equality in the list of instantiated objects."""
        if self.allow_duplicates:
            # We want to return the first similar object (equality) that has this name.
            obj = next(
                iter(
                    sorted(
                        (
                            x
                            for x in self._CREATED_OBJECTS
                            if x == self
                            and x.Name == self.Name
                        ),
                        key=lambda x: x.unit_number,
                    )
                ),
                self,
            )
        else:
            # We want to return the first similar object (equality) regardless of the
            # name.
            obj = next(
                iter(
                    sorted(
                        (
                            x
                            for x in self._CREATED_OBJECTS
                            if x == self
                        ),
                        key=lambda x: x.unit_number,
                    )
                ),
                self,
            )

        return obj

    @property
    def Parents(self): 
        """ Get the parents of an UmiBase Object"""
        parents = set()
        for component in self._parents:
            """Don't add self to parents!"""
            if component != self and component.id != self.id:
                parents.add(component)
        return parents

    @property
    def ParentTemplates(self):
        """Get the parent templates of an UmiBase object"""
        # TODO: This should use networkx UmiBase._GRAPH.has_path, 
        # but it requires importing BuildingTemplate._CREATED_OBJECTS
        templates = set()
        for parent in self.Parents:
             # Recursive call terminates at Parent Template level, or if self.Parents is empty
            templates = templates.union(parent.ParentTemplates)
        return templates
    
    def replace_me_with(self, other):
        # Copy the edge metadata since the edge dict will change while iterating
        edges = [(parent, _self, key, data) for parent, _self, key, data in self._parents.edges(data=True, keys=True)]

        # Iterate over the edges and replace each key
        for (parent, _, key, data) in edges:
            # fire the attr setter
            if data["meta"] is not None:
                meta = data["meta"]
                attr = meta["attr"]
                index = meta["index"]
                umibase_list = getattr(parent, attr) # get the base list
                umibase_list[index] = other # fire the setter
            else:
                parent[key] = other



    def link(self, parent, key, meta=None):
        """Link this object as child to a parent
        Args:
            parent (UmiBase): the parent to link
            key (str): the property which this child was used for in the parent and which should be unlinked, or <attr>_<index> if a list element
            meta (dict or NoneType): if self is an UmiBaseList element, stores meta stores {"attr": <attr>, "index": <index>}
        """
        self._parents.add_edge(parent, self, key, meta=meta)
        UmiBase._GRAPH.add_edge(parent, self, key, meta=meta)
    
    def unlink(self, parent, key):
        """Unlink this object as a child from a parent
        Args:
            parent (UmiBase): the parent to unlink
            key (str): the property which the child was used for in the parent and which should be unlinked.
        """
        if self._parents.has_node(parent):
            # Fails silently if edge does not exist
            self._parents.remove_edges_from([(parent, self, key)])
            UmiBase._GRAPH.remove_edges_from([(parent, self, key)])

            if len(self._parents[parent]) == 0:
                self._parents.remove_node(parent)
            

    def relink(self, child, key):
        """ Parents call this to link to a new child and unlink the old child for an attr
        Args:
            child (UmiBase): The new child
            key (str): The cache value to store in th link, which should match a Property getter
        """
        current_child = getattr(self, key, None)
        if current_child:
            getattr(self, key).unlink(self, key)
        if child is not None:
            child.link(self, key)
    
    @classmethod
    def clear_graph(cls):
        UmiBase._GRAPH = nx.MultiDiGraph()



class UserSet(Hashable, MutableSet):
    """UserSet class."""

    __hash__ = MutableSet._hash

    def __init__(self, iterable=()):
        """Initialize object."""
        self.data = set(iterable)

    def __contains__(self, value):
        """Assert value is in self.data."""
        return value in self.data

    def __iter__(self):
        """Iterate over self.data."""
        return iter(self.data)

    def __len__(self):
        """return len of self."""
        return len(self.data)

    def __repr__(self):
        """Return a representation of self."""
        return repr(self.data)

    def __add__(self, other):
        """Add other to self."""
        self.data.update(other.data)
        return self

    def update(self, other):
        """Update self with other."""
        self.data.update(other.data)
        return self

    def add(self, item):
        """Add an item."""
        self.data.add(item)

    def discard(self, item):
        """Remove a class if it is currently present."""
        self.data.discard(item)


class MetaData(UserSet):
    """Handles data of combined objects such as Name, Comments and other."""

    @property
    def Name(self):
        """Get object name."""
        return "+".join([obj.Name for obj in self])

    @property
    def comments(self):
        """Get object comments."""
        return "Object composed of a combination of these objects:\n{}".format(
            set(obj.Name for obj in self)
        )


class UniqueName(str):
    """Attribute unique user-defined names for :class:`UmiBase`."""

    existing = {}

    def __new__(cls, content):
        """Pick a name. Will increment the name if already used."""
        return str.__new__(cls, cls.create_unique(content))

    @classmethod
    def create_unique(cls, name):
        """Check if name has already been used.

        If so, try to increment until not used.

        Args:
            name:
        """
        if not name:
            return None
        if name not in cls.existing:
            cls.existing[name] = 0
            return name
        else:
            current_count = cls.existing[name]
            new_count = current_count + 1
            new_name = f"{name}_{str(new_count)}"
            cls.existing[name] = new_count
            return new_name

def umibase_property(type_of_property):
    """Create a new property decorator which will automatically
       configure the property to handle type-checking and parent-graph relinking
       Needs to be abstracted into a single class rather than a class generator

    Args: 
        type_of_property (class inherits UmiBase): which class of UmiBase object the property will store
    """
    class UmiBaseProperty(property):
        def __init__(self, getter_func, *args, **kwargs):
            super().__init__(getter_func, *args, **kwargs)
            self.type_of_property = type_of_property
            self.attr_name = getter_func.__name__
        
        def __get__(self, obj, owner):
            try:
                return super().__get__(obj, owner)
            except AttributeError:
                return None

        def __set__(self, obj, value):
            self.type_check(value)
            self.relink(obj, value)
            super().__set__(obj, value)
        
        def type_check(self, value):
            if value is not None:
                assert isinstance(value, self.type_of_property), (
                    f"Input value error. {self.attr_name} must be of "
                    f"type {self.type_of_property}, not {type(value)}."
                )
        
        def relink(self, obj, value):
            obj.relink(value, self.attr_name)

    return UmiBaseProperty

    # def _setter(self, fset):
    #     obj = super().setter(fset)
    #     obj.type_of_property = self.type_of_property 
    #     return obj

    # def setter(self, type_of_property):
    #     self.type_of_property = type_of_property
    #     return self._setter

class UmiBaseHelper:
    """Base for Helper classes so that the UmiBase object can be 
       found and operated on via the helper, e.g. for YearScheduleParts
    """
    __slots__ = (
        "_umi_base_property"
    )
    def __init__(self, umi_base_property):
        assert isinstance(umi_base_property, str), "'umi_base_property' must be a string"
        self._umi_base_property = umi_base_property

    def __getattr__(self, attr):
        umi_base = getattr(self, self._umi_base_property)
        return getattr(umi_base, attr)

class UmiBaseList:
    """This class is a hook for lists so that UmiBase fields which store lists 
       can link and unlink list elements from a parent attr
    """

    def __init__(self, parent, attr, objects=[]):
        assert isinstance(objects, list), "UmiBaseList must be initialized with a list"
        assert isinstance(parent, UmiBase), "UmiBaseList's parent must be initialized with an UmiBase object"
        assert isinstance(attr, str), "UmiBaseList's attr must be a str"
        assert attr in dir(parent), f"UmiBaseLest's attr '{attr}' is not a valid attr of parent {parent}"
        self._attr = attr
        self._parent = parent
        self.link_list(objects)

    def __getitem__(self, index):
        return self._objects[index]

    def format_graph_key(self, index):
        return f"{self._attr}_{index}"
    
    def format_edge_meta(self, index):
        return {"attr": self._attr, "index": index}

    def __setitem__(self, index, value):
        should_insert_into_helper_obj = isinstance(self[index], UmiBaseHelper) and isinstance(value, UmiBase)
        if self[index]:
            self[index].unlink(self._parent, self.format_graph_key(index))
            if should_insert_into_helper_obj:
                setattr(self[index], self[index]._umi_base_property, value)
        if not should_insert_into_helper_obj or not self[index]:
            self._objects[index] = value
        value.link(self._parent, self.format_graph_key(index), meta=self.format_edge_meta(index))
    
    def __eq__(self, other):
        """Check if two UmiBaseLists are equal by iterating through the arrays"""
        # TODO: make sure this has no other knock on effects
        # By allowing two lists which are not the same obj in memory to be equal
        if not isinstance(other, UmiBaseList):
            return NotImplemented
        else:
            if len(self) > len(other):
                return False
            else:
                return all([a == b for a, b in zip(self, other)])

    def unlink_list(self):
        for index, obj in enumerate(self._objects):
            obj.unlink(self._parent, self.format_graph_key(index))
        self._objects = []

    def link_list(self, objects):
        self._objects = [None for obj in objects]
        for i, obj in enumerate(objects):
            self[i] = obj # fire the setter

    def relink_list(self, objects):
        if len(self._objects) > 0:
            self.unlink_list()

        new_list = objects._objects if isinstance(objects, UmiBaseList) else objects
        self.link_list(new_list)

    def __len__(self):
        return len(self._objects)

    def __getattr__(self, attr):
        """ Provid access to underlying list methods"""
        return getattr(self._objects, attr)

    # TODO: implement aliases for underlying list methods which mutate the list to handle 
    # relinking
