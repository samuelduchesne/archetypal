"""archetypal UmiBase module."""

import itertools
import math
import re
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

    __slots__ = (
        "_id",
        "_datasource",
        "_predecessors",
        "_name",
        "_category",
        "_comments",
        "_allow_duplicates",
        "_unit_number",
    )
    CREATED_OBJECTS = []
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

        UmiBase.CREATED_OBJECTS.append(self)

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

    @classmethod
    def get_classref(cls, ref):
        return next(
            iter(
                [value for value in UmiBase.CREATED_OBJECTS if value.id == ref["$ref"]]
            ),
            None,
        )

    def get_ref(self, ref):
        pass

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.mro()[0].__name__, self.Name))

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
        self.CREATED_OBJECTS.remove(self)
        id = self.id
        new_obj = self.combine(other, allow_duplicates=allow_duplicates)
        new_obj.id = id
        for key in self.mapping(validate=False):
            setattr(self, key, getattr(new_obj, key))
        return self

    def validate(self):
        """Validate UmiObjects and fills in missing values."""
        return self

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return dict(
            id=self.id,
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
                            for x in UmiBase.CREATED_OBJECTS
                            if x == self
                            and x.Name == self.Name
                            and type(x) == type(self)
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
                            for x in UmiBase.CREATED_OBJECTS
                            if x == self and type(x) == type(self)
                        ),
                        key=lambda x: x.unit_number,
                    )
                ),
                self,
            )

        return obj


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

    existing = set()

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
            cls.existing.add(name)
            return name
        else:
            match = re.match(r"^(.*?)(\D*)(\d+)$", name)
            if match:
                groups = list(match.groups())
                pad = len(groups[-1])
                groups[-1] = int(groups[-1])
                groups[-1] += 1
                groups[-1] = str(groups[-1]).zfill(pad)
                name = "".join(map(str, groups))
                return cls.create_unique(name)
            else:
                return cls.create_unique(name + "_1")
