"""UmiSchedules module."""

import calendar
import collections
import hashlib
from datetime import datetime

import numpy as np
import pandas as pd
from validator_collection import validators

from archetypal.schedule import Schedule, _ScheduleParser, get_year_for_first_weekday
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log


class UmiSchedule(Schedule, UmiBase):
    """Class that handles Schedules."""

    __slots__ = ("_quantity",)

    def __init__(self, Name, quantity=None, **kwargs):
        """Initialize object with parameters.

        Args:
            Name:
            quantity:
            **kwargs:
        """
        super(UmiSchedule, self).__init__(Name, **kwargs)
        self.quantity = quantity

    @property
    def quantity(self):
        """Get or set the schedule quantity."""
        return self._quantity

    @quantity.setter
    def quantity(self, value):
        self._quantity = value

    @classmethod
    def constant_schedule(cls, value=1, Name="AlwaysOn", Type="Fraction", **kwargs):
        """Create an UmiSchedule with a constant value at each timestep.

        Args:
            Type:
            value (float):
            Name:
            idf:
            **kwargs:
        """
        value = validators.float(value)
        return super(UmiSchedule, cls).constant_schedule(
            value=value, Name=Name, Type=Type, **kwargs
        )

    @classmethod
    def random(cls, Name="AlwaysOn", Type="Fraction", **kwargs):
        """Create an UmiSchedule with a randomized value (0-1) at each timestep.

        Args:
            Name (str): The name of the Schedule.
            Type (str or ScheduleTypeLimits):
            **kwargs: keywords passed to the constructor.
        """
        values = np.random.rand(
            8760,
        )
        return cls(Values=values.tolist(), Name=Name, Type=Type, **kwargs)

    @classmethod
    def from_values(cls, Name, Values, Type="Fraction", **kwargs):
        """Create an UmiSchedule from a list of values.

        Args:
            Name (str): The name of the Schedule.
            Values (list):
            Type:
            **kwargs:
        """
        return super(UmiSchedule, cls).from_values(
            Name=Name, Values=Values, Type=Type, **kwargs
        )

    def combine(self, other, weights=None, quantity=None):
        """Combine two UmiSchedule objects together.

        Args:
            other (UmiSchedule): The other Schedule object to combine with.
            weights (list, dict or string): Attribute of self and other containing the
                weight factor. If a list is passed, it must have len = 2; the first
                element is applied to self and the second element is applied to other.
                If a dict is passed, the self.Name and other.Name are the keys. If a
                str is passed, the
            quantity (list or dict or bool): Scalar value that will be multiplied by
                self before the averaging occurs. This ensures that the resulting
                schedule returns the correct integrated value. If a dict is passed,
                keys are schedules Names and values are quantities.

        Returns:
            (UmiSchedule): the combined UmiSchedule object.

        Raises:
            TypeError: if Quantity is not of type list, tuple, dict or a callable.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        if not isinstance(other, UmiSchedule):
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # check if the schedule is the same
        if self == other:
            if self.quantity and other.quantity:
                self.quantity += other.quantity
            return self
        # check if self is only zeros. Should not affect other.
        if not np.any(self.all_values):
            return other
        # check if other is only zeros. Should not affect self.
        if not np.any(other.all_values):
            return self

        if not weights:
            log(
                'using 1 as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [1, 1]
        elif isinstance(weights, str):
            # get the attribute from self and other
            weights = [getattr(self, weights), getattr(other, weights)]
        elif isinstance(weights, (list, tuple)):
            # check if length is 2.
            length = len(weights)
            if length != 2:
                raise ValueError(
                    "USing a list or tuple, the weights attribute must "
                    "have a length of 2. A length of {}".format(length)
                )
        elif isinstance(weights, dict):
            weights = [weights[self.Name], weights[other.Name]]

        if quantity is None:
            new_values = np.average(
                [self.all_values, other.all_values], axis=0, weights=weights
            )
        elif isinstance(quantity, dict):
            # Multiplying the schedule values by the quantity for both self and other
            # and then using a weighted average. Finally, new values are normalized.
            new_values = np.average(
                [
                    self.all_values * quantity[self.Name],
                    other.all_values * quantity[other.Name],
                ],
                axis=0,
                weights=weights,
            )
            new_values /= quantity[self.Name] + quantity[other.Name]
        elif callable(quantity):
            new_values = np.average(
                np.stack((self.all_values, other.all_values), axis=1),
                axis=1,
                weights=[
                    quantity(self.predecessors.data),
                    quantity(other.predecessors.data),
                ],
            )
        elif isinstance(quantity, (list, tuple)):
            # Multiplying the schedule values by the quantity for both self and other
            # and then using a weighted average. Finally, new values are normalized.
            self_quantity, other_quantity = quantity
            new_values = (
                self.all_values * self_quantity + other.all_values * other_quantity
            ) / sum(quantity)
        elif isinstance(quantity, bool):
            new_values = np.average(
                [self.all_values, other.all_values],
                axis=0,
                weights=[self.quantity * weights[0], other.quantity * weights[1]],
            )
        else:
            raise TypeError("Quantity is not of type list, tuple, dict or a callable")

        # the new object's name
        meta = self._get_predecessors_meta(other)

        # Overriding meta Name
        hasher = hashlib.md5()
        hasher.update(new_values)
        meta["Name"] = f"Combined_UmiSchedule_{hasher.hexdigest()}"
        quantity = np.nansum(
            [self.quantity or float("nan"), other.quantity or float("nan")]
        )
        new_obj = UmiSchedule.from_values(
            Values=new_values, Type="Fraction", quantity=quantity, **meta
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        new_obj.weights = sum(weights)
        return new_obj

    def develop(self):
        """Develop the UmiSchedule into a Year-Week-Day schedule structure."""
        year, weeks, days = self.to_year_week_day()
        lines = ["- {}".format(obj) for obj in self.predecessors]

        _from = "\n".join(lines)
        year.Comments = (
            f"Year Week Day schedules created from: \n{_from}" + str(id(self)),
        )
        return year

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return super(UmiSchedule, self.develop()).get_unique()

    def to_dict(self):
        """Return UmiSchedule dictionary representation.

        Hint:
            UmiSchedule does not implement the to_dict method because it is not used
            when generating the json file. Only Year-Week- and DaySchedule classes
            are used.
        """
        return self.to_ref()

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}

    def validate(self):
        """Validate object and fill in missing values."""
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
            Category=self.Category,
            Type=self.Type,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in UmiSchedule.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __add__(self, other):
        """Return new object that is the combination of self and other."""
        return UmiSchedule.combine(self, other)

    def __repr__(self):
        """Return a representation of self."""
        name = self.Name
        resample = self.series.resample("D")
        min = resample.min().mean()
        mean = resample.mean().mean()
        max = resample.max().mean()
        return (
            name
            + ": "
            + "mean daily min:{:.2f} mean:{:.2f} max:{:.2f} ".format(min, mean, max)
            + (f"quantity {self.quantity}" if self.quantity is not None else "")
        )

    def __str__(self):
        """Return the string representation of self."""
        return repr(self)

    def __hash__(self):
        """Return the hash value of self."""
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, UmiSchedule):
            return NotImplemented
        if self.all_values.size != other.all_values.size:
            return NotImplemented
        else:
            return all(
                [
                    self.strict == other.strict,
                    self.Type == other.Type,
                    self.quantity == other.quantity,
                    np.allclose(self.all_values, other.all_values, rtol=1e-02),
                ]
            )

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(
            Name=self.Name,
            quantity=self.quantity,
            Values=self.all_values.tolist(),
            strict=self.strict,
            Type=self.Type,
        )


class YearSchedulePart:
    """Helper Class for YearSchedules defined with FromDay FromMonth ToDay ToMonth."""

    __slots__ = ("_from_day", "_from_month", "_to_day", "_to_month", "_schedule")

    def __init__(
        self,
        FromDay=None,
        FromMonth=None,
        ToDay=None,
        ToMonth=None,
        Schedule=None,
        **kwargs,
    ):
        """Initialize YearSchedulePart.

        Args:
            FromDay (int): This numeric field is the starting day for the
                schedule time period.
            FromMonth (int): This numeric field is the starting month for the
                schedule time period.
            ToDay (int): This numeric field is the ending day for the schedule
                time period.
            ToMonth (int): This numeric field is the ending month for the
                schedule time period.
            Schedule (UmiSchedule): The associated UmiSchedule related to this
                object.
            kwargs (dict): Other Keyword arguments.
        """
        self.FromDay = FromDay
        self.FromMonth = FromMonth
        self.ToDay = ToDay
        self.ToMonth = ToMonth
        self.Schedule = Schedule

    @property
    def FromDay(self):
        """Get or set the start day-of-month number [int]."""
        return self._from_day

    @FromDay.setter
    def FromDay(self, value):
        self._from_day = validators.integer(value, minimum=1, maximum=31)

    @property
    def FromMonth(self):
        """Get or set the start month-number [int]."""
        return self._from_month

    @FromMonth.setter
    def FromMonth(self, value):
        self._from_month = validators.integer(value, minimum=1, maximum=12)

    @property
    def ToDay(self):
        """Get or set the end day-of-month number [int]."""
        return self._to_day

    @ToDay.setter
    def ToDay(self, value):
        self._to_day = validators.integer(value, minimum=1, maximum=31)

    @property
    def ToMonth(self):
        """Get or set the end month-number [int]."""
        return self._to_month

    @ToMonth.setter
    def ToMonth(self, value):
        self._to_month = validators.integer(value, minimum=1, maximum=12)

    @property
    def Schedule(self):
        """Get or set the WeekSchedule object."""
        return self._schedule

    @Schedule.setter
    def Schedule(self, value):
        assert isinstance(value, WeekSchedule), "schedule must be of type WeekSchedule"
        self._schedule = value

    @classmethod
    def from_dict(cls, data, schedules, **kwargs):
        """Create a YearSchedulePart object from a dictionary.

        Args:
            data (dict): The python dictionary.
            schedules (dict): A dictionary of WeekSchedules with their id as keys.
            **kwargs: keywords passed to parent constructor.

        .. code-block:: python

            data = {
                'FromDay': 1,
                'FromMonth': 1,
                'ToDay': 31,
                'ToMonth': 12,
                'Schedule': {'$ref': '140622440042800'}
            }
        """
        schedule = schedules[data.pop("Schedule")["$ref"]]
        ysp = cls(Schedule=schedule, **data, **kwargs)

        return ysp

    def to_dict(self):
        """Return YearSchedulePart dictionary representation."""
        return collections.OrderedDict(
            FromDay=self.FromDay,
            FromMonth=self.FromMonth,
            ToDay=self.ToDay,
            ToMonth=self.ToMonth,
            Schedule={"$ref": str(self.Schedule.id)},
        )

    def __str__(self):
        """Return string representation of self."""
        return str(self.to_dict())

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        return dict(
            FromDay=self.FromDay,
            FromMonth=self.FromMonth,
            ToDay=self.ToDay,
            ToMonth=self.ToMonth,
            Schedule=self.Schedule,
        )

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return self

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, YearSchedulePart):
            return NotImplemented
        else:
            return all(
                [
                    self.FromDay == other.FromDay,
                    self.FromMonth == other.FromMonth,
                    self.ToDay == other.ToDay,
                    self.ToMonth == other.ToMonth,
                    self.Schedule == other.Schedule,
                ]
            )

    def __iter__(self):
        """Iterate over attributes. Yields tuple of (keys, value)."""
        for k, v in self.mapping().items():
            yield k, v

    def __hash__(self):
        """Return the hash value of self."""
        return id(self)


class DaySchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles daily schedules."""

    __slots__ = ("_values",)

    def __init__(self, Name, Values, Category="Day", **kwargs):
        """Initialize a DaySchedule object with parameters.

        Args:
            Values (list): List of 24 values.
            Name (str): Name of the schedule.
            Category (str): category identification (default: "Day").
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
        """
        super(DaySchedule, self).__init__(
            Category=Category, Name=Name, Values=Values, **kwargs
        )

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        return np.array(self._values)

    @all_values.setter
    def all_values(self, value):
        self._values = validators.iterable(value, maximum_length=24)

    @classmethod
    def from_epbunch(cls, epbunch, strict=False, **kwargs):
        """Create a DaySchedule from an EpBunch.

        This method accepts "Schedule:Day:Hourly", "Schedule:Day:List" and
        "Schedule:Day:Interval".

        Args:
            epbunch (EpBunch): The EpBunch object to construct a DaySchedule
                from.
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """
        assert epbunch.key.lower() in (
            "schedule:day:hourly",
            "schedule:day:list",
            "schedule:day:interval",
        ), (
            f"Input error for '{epbunch.key}'. Expected on of "
            f"('Schedule:Day:Hourly', 'Schedule:Day:List' and "
            f"'Schedule:Day:Interval')"
        )
        start_day_of_the_week = epbunch.theidf.day_of_week_for_start_day
        start_date = datetime(get_year_for_first_weekday(start_day_of_the_week), 1, 1)
        sched = cls(
            Name=epbunch.Name,
            epbunch=epbunch,
            schType=epbunch.key,
            Type=cls.get_schedule_type_limits_name(epbunch),
            Values=_ScheduleParser.get_schedule_values(
                epbunch, start_date, strict=strict
            ),
            **kwargs,
        )

        return sched

    @classmethod
    def from_values(cls, Name, Values, Type="Fraction", **kwargs):
        """Create a DaySchedule from an array of size (24,).

        Args:
            Name:
            Values (array-like): A list of values of length 24.
            Type (str): Schedule Type Limit name.
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """
        return cls(Name=Name, Values=Values, Type=Type, **kwargs)

    @classmethod
    def from_dict(cls, data, **kwargs):
        """Create a DaySchedule from a dictionary.

        Args:
            data (dict): A python dictionary with the structure shown bellow.
            **kwargs: keywords passed to parents constructors.

        .. code-block:: python

            {
              "$id": "67",
              "Category": "Day",
              "Type": "Fraction",
              "Values": [...],  # 24 hourly values
              "Comments": "default",
              "DataSource": "default",
              "Name": "B_Res_D_Occ_WD"
            },
        """
        _id = data.pop("$id")
        sched = cls.from_values(id=_id, **data, **kwargs)

        return sched

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return UmiBase.get_unique(self)

    def to_dict(self):
        """Return DaySchedule dictionary representation."""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Type"] = "Fraction" if self.Type is None else self.Type.Name
        data_dict["Values"] = np.round(self.all_values, 3).tolist()
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
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
            Category=self.Category,
            Type=self.Type,
            Values=self.all_values.round(3).tolist(),
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, DaySchedule):
            return NotImplemented
        else:
            return all(
                [
                    self.Type == other.Type,
                    np.allclose(self.all_values, other.all_values, rtol=1e-02),
                ]
            )

    def __hash__(self):
        """Return the hash value of self."""
        return super(DaySchedule, self).__hash__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(self.Name, Values=self.all_values.tolist())

    def to_epbunch(self, idf):
        """Convert self to an epbunch given an idf model.

        Args:
            idf (IDF): An IDF model.

        .. code-block:: python

            SCHEDULE:DAY:HOURLY,
                ,                         !- Name
                ,                         !- Schedule Type Limits Name
                0,                        !- Hour 1
                0,                        !- Hour 2
                0,                        !- Hour 3
                0,                        !- Hour 4
                0,                        !- Hour 5
                0,                        !- Hour 6
                0,                        !- Hour 7
                0,                        !- Hour 8
                0,                        !- Hour 9
                0,                        !- Hour 10
                0,                        !- Hour 11
                0,                        !- Hour 12
                0,                        !- Hour 13
                0,                        !- Hour 14
                0,                        !- Hour 15
                0,                        !- Hour 16
                0,                        !- Hour 17
                0,                        !- Hour 18
                0,                        !- Hour 19
                0,                        !- Hour 20
                0,                        !- Hour 21
                0,                        !- Hour 22
                0,                        !- Hour 23
                0;                        !- Hour 24

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            key="Schedule:Day:Hourly".upper(),
            **dict(
                Name=self.Name,
                Schedule_Type_Limits_Name=self.Type.to_epbunch(idf).Name,
                **{"Hour_{}".format(i + 1): self.all_values[i] for i in range(24)},
            ),
        )


class WeekSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles weekly schedules."""

    __slots__ = ("_days", "_values")

    def __init__(self, Name, Days=None, Category="Week", **kwargs):
        """Initialize a WeekSchedule object with parameters.

        Args:
            Days (list of DaySchedule): list of :class:`DaySchedule`.
            **kwargs:
        """
        super(WeekSchedule, self).__init__(Name, Category=Category, **kwargs)
        self.Days = Days

    @property
    def Days(self):
        """Get or set the list of DaySchedule objects."""
        return self._days

    @Days.setter
    def Days(self, value):
        if value is not None:
            assert all(
                isinstance(x, DaySchedule) for x in value
            ), f"Input value error '{value}'. Expected list of DaySchedule."
        self._days = value

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Create a WeekSchedule from a Schedule:Week:Daily object.

        Args:
            epbunch (EpBunch): The Schedule:Week:Daily object.
            **kwargs: keywords passed to the constructor.
        """
        assert (
            epbunch.key.lower() == "schedule:week:daily"
        ), f"Expected a 'schedule:week:daily' not a '{epbunch.key.lower()}'"
        Days = WeekSchedule.get_days(epbunch, **kwargs)
        sched = cls(
            Name=epbunch.Name,
            schType=epbunch.key,
            Days=Days,
            **kwargs,
        )

        return sched

    @classmethod
    def from_dict(cls, data, day_schedules, **kwargs):
        """Create a WeekSchedule from a dictionary.

        Args:
            data (dict): The python dictionary.
            day_schedules (dict): A dictionary of python DaySchedules with their id as
                keys.
            **kwargs: keywords passed to the constructor.
        """
        refs = data.pop("Days")
        _id = data.pop("$id")
        Days = [day_schedules[ref["$ref"]] for ref in refs]
        wc = cls(Days=Days, id=_id, **data, **kwargs)
        return wc

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return UmiBase.get_unique(self)

    def to_dict(self):
        """Return WeekSchedule dictionary representation."""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Days"] = [day.to_ref() for day in self.Days]
        data_dict["Type"] = "Fraction" if self.Type is None else self.Type.Name
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
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
            Category=self.Category,
            Days=self.Days,
            Type=self.Type,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    @classmethod
    def get_days(cls, epbunch, **kwargs):
        """Get the DaySchedules referenced in the Week:Schedule:Days object.

        Args:
            list of DaySchedule: The list of DaySchedules referenced by the epbunch.
        """
        assert (
            epbunch.key.lower() == "schedule:week:daily"
        ), f"Expected a 'schedule:week:daily' not a '{epbunch.key.lower()}'"
        Days = []
        dayname = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for day in dayname:
            day_ep = epbunch.get_referenced_object("{}_ScheduleDay_Name".format(day))
            Days.append(DaySchedule.from_epbunch(day_ep, **kwargs))

        return Days

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        if self._values is None:
            self._values = np.concatenate([day.all_values for day in self.Days])
        return self._values

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, WeekSchedule):
            return NotImplemented
        else:
            return all(
                [
                    self.Type == other.Type,
                    self.Days == other.Days,
                ]
            )

    def __hash__(self):
        """Return the hash value of self."""
        return super(WeekSchedule, self).__hash__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(Name=self.Name, Days=self.Days)

    def to_epbunch(self, idf):
        """Convert self to an epbunch given an idf model.

        Args:
            idf (IDF): An IDF model.

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            key="Schedule:Week:Daily".upper(),
            **dict(
                Name=self.Name,
                **{
                    f"{calendar.day_name[i]}_ScheduleDay_Name": day.to_epbunch(idf).Name
                    for i, day in enumerate(self.Days)
                },
                Holiday_ScheduleDay_Name=self.Days[6].Name,
                SummerDesignDay_ScheduleDay_Name=self.Days[0].Name,
                WinterDesignDay_ScheduleDay_Name=self.Days[0].Name,
                CustomDay1_ScheduleDay_Name=self.Days[1].Name,
                CustomDay2_ScheduleDay_Name=self.Days[6].Name,
            ),
        )


class YearSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles yearly schedules."""

    def __init__(self, Name, Type="Fraction", Parts=None, Category="Year", **kwargs):
        """Initialize a YearSchedule object with parameters.

        Args:
            Category:
            Name:
            Type:
            Parts (list of YearSchedulePart): The YearScheduleParts.
            **kwargs:
        """
        self.epbunch = kwargs.get("epbunch", None)
        if Parts is None:
            self.Parts = self._get_parts(self.epbunch)
        else:
            self.Parts = Parts
        super(YearSchedule, self).__init__(
            Name=Name, Type=Type, schType="Schedule:Year", Category=Category, **kwargs
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, YearSchedule):
            return NotImplemented
        else:
            return all([self.Type == other.Type, self.Parts == other.Parts])

    def __hash__(self):
        """Return the hash value of self."""
        return super(YearSchedule, self).__hash__()

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        if self._values is None:
            index = pd.date_range(start=self.startDate, freq="1H", periods=8760)
            series = pd.Series(index=index)
            for part in self.Parts:
                start = "{}-{}-{}".format(self.year, part.FromMonth, part.FromDay)
                end = "{}-{}-{}".format(self.year, part.ToMonth, part.ToDay)
                # Get week values from all_values of Days
                one_week = np.array(
                    [
                        item
                        for sublist in part.Schedule.Days
                        for item in sublist.all_values
                    ]
                )

                all_weeks = np.resize(one_week, len(series.loc[start:end]))
                series.loc[start:end] = all_weeks
            self._values = series.values
        return self._values

    @classmethod
    def from_dict(cls, data, week_schedules, **kwargs):
        """Create a YearSchedule from a dictionary.

        Args:
            data (dict): The python dictionary.
            week_schedule (dict): A dictionary of python WeekSchedules with their id as
                keys.
            **kwargs: keywords passed to the constructor.
        """
        Parts = [
            YearSchedulePart.from_dict(data, week_schedules)
            for data in data.pop("Parts", None)
        ]
        _id = data.pop("$id")
        ys = cls(Parts=Parts, id=_id, **data, **kwargs)
        return ys

    def get_unique(self):
        """Return the first of all the created objects that is equivalent to self."""
        return UmiBase.get_unique(self)

    def to_dict(self):
        """Return YearSchedule dictionary representation."""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
        data_dict["Type"] = "Fraction" if self.Type is None else self.Type.Name
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf):
        """Convert self to an epbunch given an idf model.

        Notes:
            The object is added to the idf model.

        Args:
            idf (IDF): An IDF model.

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        new_dict = dict(
            Name=self.Name, Schedule_Type_Limits_Name=self.Type.to_epbunch(idf).Name
        )
        for i, part in enumerate(self.Parts):
            new_dict.update(
                {
                    "ScheduleWeek_Name_{}".format(i + 1): part.Schedule.to_epbunch(
                        idf
                    ).Name,
                    "Start_Month_{}".format(i + 1): part.FromMonth,
                    "Start_Day_{}".format(i + 1): part.FromDay,
                    "End_Month_{}".format(i + 1): part.ToMonth,
                    "End_Day_{}".format(i + 1): part.ToDay,
                }
            )

        return idf.newidfobject(key="Schedule:Year".upper(), **new_dict)

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
            Parts=self.Parts,
            Type=self.Type,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def _get_parts(self, epbunch):
        parts = []
        for i in range(int(len(epbunch.fieldvalues[3:]) / 5)):
            week_day_schedule_name = epbunch["ScheduleWeek_Name_{}".format(i + 1)]

            FromMonth = epbunch["Start_Month_{}".format(i + 1)]
            ToMonth = epbunch["End_Month_{}".format(i + 1)]
            FromDay = epbunch["Start_Day_{}".format(i + 1)]
            ToDay = epbunch["End_Day_{}".format(i + 1)]
            parts.append(
                YearSchedulePart(
                    FromDay,
                    FromMonth,
                    ToDay,
                    ToMonth,
                    next(
                        (
                            x
                            for x in self.CREATED_OBJECTS
                            if x.Name == week_day_schedule_name
                            and type(x).__name__ == "WeekSchedule"
                        )
                    ),
                )
            )
        return parts

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}
