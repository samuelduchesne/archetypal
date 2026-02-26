"""UmiSchedules module."""

import calendar
import collections
import hashlib
import logging as lg
from datetime import datetime, timedelta
from itertools import groupby
from typing import ClassVar

import numpy as np
import pandas as pd
from validator_collection import checkers, validators

from archetypal.template.umi_base import UmiBase
from archetypal.utils import log


def get_year_for_first_weekday(weekday: int = 0) -> int:
    """Get a non-leap year that starts on the given weekday (Monday=0).

    Args:
        weekday (int): 0-based day of week (Monday=0).

    Returns:
        int: The year number whose January 1st falls on *weekday*.
    """
    if weekday > 6:
        raise ValueError("weekday must be between 0 and 6")
    year = 2020
    while True:
        if calendar.weekday(year, 1, 1) == weekday and not calendar.isleap(year):
            return year
        year -= 1


class ScheduleTypeLimits:
    """Lightweight schedule type limits descriptor."""

    __slots__ = ("_name", "_lower_limit", "_upper_limit", "_numeric_type", "_unit_type")

    def __init__(
        self,
        Name,
        LowerLimit=None,
        UpperLimit=None,
        NumericType="Continuous",
        UnitType="Dimensionless",
    ):
        self.Name = Name
        self.LowerLimit = LowerLimit
        self.UpperLimit = UpperLimit
        self.NumericType = NumericType
        self.UnitType = UnitType

    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, value):
        self._name = validators.string(value)

    @property
    def LowerLimit(self):
        return self._lower_limit

    @LowerLimit.setter
    def LowerLimit(self, value):
        self._lower_limit = validators.float(value, allow_empty=True)

    @property
    def UpperLimit(self):
        return self._upper_limit

    @UpperLimit.setter
    def UpperLimit(self, value):
        self._upper_limit = validators.float(value, allow_empty=True)

    @property
    def NumericType(self):
        return self._numeric_type

    @NumericType.setter
    def NumericType(self, value):
        self._numeric_type = value

    @property
    def UnitType(self):
        return self._unit_type

    @UnitType.setter
    def UnitType(self, value):
        self._unit_type = value

    def __eq__(self, other):
        if not isinstance(other, ScheduleTypeLimits):
            return NotImplemented
        return self.Name == other.Name

    def __hash__(self):
        return hash(self.Name)

    def __repr__(self):
        return f"ScheduleTypeLimits({self.Name!r})"

    @classmethod
    def from_dict(cls, data):
        """Create from a dictionary."""
        return cls(**data)

    def to_dict(self):
        """Return dictionary representation."""
        return {
            "Name": self.Name,
            "LowerLimit": self.LowerLimit,
            "UpperLimit": self.UpperLimit,
            "NumericType": self.NumericType,
            "UnitType": self.UnitType,
        }

    @classmethod
    def from_idf_object(cls, obj):
        """Create a ScheduleTypeLimits from an idfkit object.

        Args:
            obj: An idfkit object of type ``ScheduleTypeLimits``.
        """
        name = obj.name
        lower_limit = getattr(obj, "lower_limit_value", None)
        upper_limit = getattr(obj, "upper_limit_value", None)
        numeric_type = getattr(obj, "numeric_type", "Continuous")
        unit_type = getattr(obj, "unit_type", "Dimensionless")
        return cls(
            Name=name,
            LowerLimit=lower_limit if checkers.is_numeric(lower_limit) else None,
            UpperLimit=upper_limit if checkers.is_numeric(upper_limit) else None,
            NumericType=numeric_type if checkers.is_string(numeric_type, minimum_length=1) else "Continuous",
            UnitType=unit_type if checkers.is_string(unit_type, minimum_length=1) else "Dimensionless",
        )


# ---------------------------------------------------------------------------
# Helper utilities for parsing idfkit day-schedule objects
# ---------------------------------------------------------------------------


def _parse_day_list(obj):
    """Parse a Schedule:Day:List idfkit object into 24 hourly values.

    The object has variable-length fields: pairs of (minutes, value).
    We interpolate into 24 hourly bins (value at the start of each hour).
    """
    values = [0.0] * 24
    current_minute = 0
    idx = 1
    while True:
        minutes_attr = f"minutes_until_time_{idx}"
        value_attr = f"value_until_time_{idx}"
        minutes = getattr(obj, minutes_attr, None)
        val = getattr(obj, value_attr, None)
        if minutes is None or val is None:
            break
        end_minute = int(minutes)
        start_hour = current_minute // 60
        end_hour = min((end_minute - 1) // 60, 23)
        for h in range(start_hour, end_hour + 1):
            values[h] = float(val)
        current_minute = end_minute
        idx += 1
    return values


def _parse_day_interval(obj):
    """Parse a Schedule:Day:Interval idfkit object into 24 hourly values.

    Fields come in pairs: ``time_N`` (HH:MM format) and ``value_until_time_N``.
    """
    values = [0.0] * 24
    prev_hour = 0
    idx = 1
    while True:
        time_attr = f"time_{idx}"
        value_attr = f"value_until_time_{idx}"
        time_str = getattr(obj, time_attr, None)
        val = getattr(obj, value_attr, None)
        if time_str is None or val is None:
            break
        # time_str is typically "HH:MM"
        parts = str(time_str).split(":")
        hour = int(parts[0])
        if hour == 24:
            hour = 24  # means end of day
        for h in range(prev_hour, min(hour, 24)):
            values[h] = float(val)
        prev_hour = hour
        idx += 1
    return values


def _find_day_schedule(doc, name):
    """Look up a day schedule object by name in the idfkit Document.

    Searches across the three day-schedule types.

    Args:
        doc: An idfkit Document.
        name: The name of the day schedule to find.

    Returns:
        The idfkit object for the day schedule.

    Raises:
        KeyError: If the day schedule is not found in any of the expected types.
    """
    for type_name in ("Schedule:Day:Hourly", "Schedule:Day:List", "Schedule:Day:Interval"):
        try:
            return doc[type_name][name]
        except (KeyError, TypeError):
            continue
    raise KeyError(f"Day schedule '{name}' not found in document")


class UmiSchedule(UmiBase):
    """Class that handles Schedules."""

    _CREATED_OBJECTS: ClassVar[list["UmiSchedule"]] = []

    __slots__ = (
        "_quantity",
        "_schedule_type_limits",
        "_values",
        "_strict",
        "_start_day_of_the_week",
    )

    def __init__(
        self,
        Name,
        quantity=None,
        strict=False,
        start_day_of_the_week=0,
        Type=None,
        Values=None,
        **kwargs,
    ):
        """Initialize object with parameters.

        Args:
            Name (str): The name of the schedule.
            quantity: Optional quantity associated with the schedule.
            strict (bool): If True, raise on missing qualifiers.
            start_day_of_the_week (int): 0-based weekday (Monday=0).
            Type (str or ScheduleTypeLimits): Schedule type limits.
            Values (list or ndarray): Schedule values.
            **kwargs: Keywords passed to :class:`UmiBase`.
        """
        super().__init__(Name, **kwargs)
        self.strict = strict
        self.startDayOfTheWeek = start_day_of_the_week
        self.Values = Values
        self.Type = Type
        self.quantity = quantity

        # Only at the end append self to _CREATED_OBJECTS
        self._CREATED_OBJECTS.append(self)

    # ------------------------------------------------------------------
    # Properties inlined from the former Schedule base class
    # ------------------------------------------------------------------

    @property
    def Type(self):
        """Get or set the schedule type limits object. Can be None."""
        return self._schedule_type_limits

    @Type.setter
    def Type(self, value):
        if isinstance(value, str):
            if "fraction" in value.lower():
                value = ScheduleTypeLimits("Fraction", 0, 1)
            elif value.lower() == "temperature":
                value = ScheduleTypeLimits("Temperature", -100, 100)
            elif value.lower() == "on/off":
                value = ScheduleTypeLimits("On/Off", 0, 1, "Discrete", "Availability")
            else:
                value = ScheduleTypeLimits("Fraction", 0, 1)
                log(
                    f"'{value}' is not a known ScheduleTypeLimits for "
                    f"{self.Name}. Defaulting to 'Fraction'.",
                    level=lg.WARNING,
                )
        self._schedule_type_limits = value

    @property
    def Values(self):
        """Get or set the list of schedule values."""
        return self._values

    @Values.setter
    def Values(self, value):
        if isinstance(value, np.ndarray):
            assert value.ndim == 1, value.ndim
            value = value.tolist()
        self._values = validators.iterable(value, allow_empty=True)

    @property
    def strict(self):
        """Get or set the strict flag."""
        return self._strict

    @strict.setter
    def strict(self, value):
        self._strict = bool(value)

    @property
    def startDayOfTheWeek(self):
        """Get or set the start day of the week (Monday=0)."""
        return self._start_day_of_the_week

    @startDayOfTheWeek.setter
    def startDayOfTheWeek(self, value):
        self._start_day_of_the_week = int(value) if value is not None else 0

    @property
    def year(self):
        """Get the year satisfying startDayOfTheWeek."""
        return get_year_for_first_weekday(self.startDayOfTheWeek)

    @property
    def startDate(self):
        """Get the start date of the schedule."""
        return datetime(self.year, 1, 1)

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        return np.array(self._values)

    @all_values.setter
    def all_values(self, value):
        self._values = validators.iterable(value, maximum_length=8760)

    @property
    def max(self):
        """Get the maximum value of the schedule."""
        return max(self.all_values)

    @property
    def min(self):
        """Get the minimum value of the schedule."""
        return min(self.all_values)

    @property
    def mean(self):
        """Get the mean value of the schedule."""
        return np.average(self.all_values)

    @property
    def series(self):
        """Return a pandas Series with a DatetimeIndex."""
        index = pd.date_range(
            start=self.startDate, periods=self.all_values.size, freq="1h"
        )
        return pd.Series(self.all_values, index=index, name=self.Name)

    @staticmethod
    def get_schedule_type_limits_name(obj):
        """Return the Schedule Type Limits name associated to a schedule object.

        Works with idfkit objects (uses snake_case attribute access).
        """
        try:
            return obj.schedule_type_limits_name
        except (AttributeError, KeyError):
            return "unknown"

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
            Type (str): Schedule type limits name.
            value (float): The constant value.
            Name (str): The name of the schedule.
            **kwargs: Keywords passed to the constructor.
        """
        value = validators.float(value)
        return cls.from_values(
            Name=Name,
            Values=(np.ones((8760,)) * value).tolist(),
            Type=Type,
            **kwargs,
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
            Values (list): A list of schedule values.
            Type (str): Schedule type limits name.
            **kwargs: Keywords passed to the constructor.
        """
        return cls(Name=Name, Values=Values, Type=Type, **kwargs)

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
            msg = f"Cannot combine {self.__class__.__name__} with {other.__class__.__name__}"
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
            log(f'using 1 as weighting factor in "{self.__class__.__name__}" ' "combine.")
            weights = [1, 1]
        elif isinstance(weights, str):
            # get the attribute from self and other
            weights = [getattr(self, weights), getattr(other, weights)]
        elif isinstance(weights, (list, tuple)):
            # check if length is 2.
            length = len(weights)
            if length != 2:
                raise ValueError(
                    "USing a list or tuple, the weights attribute must " f"have a length of 2. A length of {length}"
                )
        elif isinstance(weights, dict):
            weights = [weights[self.Name], weights[other.Name]]

        if quantity is None:
            new_values = np.average([self.all_values, other.all_values], axis=0, weights=weights)
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
            new_values = (self.all_values * self_quantity + other.all_values * other_quantity) / sum(quantity)
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
        quantity = np.nansum([self.quantity or float("nan"), other.quantity or float("nan")])
        new_obj = UmiSchedule.from_values(Values=new_values, Type="Fraction", quantity=quantity, **meta)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        new_obj.weights = sum(weights)
        return new_obj

    def to_year_week_day(self):
        """Convert 8760 hourly values to Year-Week-Day schedule structure.

        Returns:
            3-element tuple containing:
                - **yearly** (*YearSchedule*): The yearly schedule object.
                - **weekly** (*list of WeekSchedule*): The weekly schedule objects.
                - **daily** (*list of DaySchedule*): The daily schedule objects.
        """
        full_year = np.array(self.all_values)  # shape (8760,)

        # reshape to (365, 24)
        Values = full_year.reshape(-1, 24)

        # create unique days
        unique_days, nds = np.unique(Values, axis=0, return_inverse=True)

        ep_days = []
        dict_day = {}
        for count_day, unique_day in enumerate(unique_days):
            name = f"d_{self.Name}_{count_day:02d}"
            dict_day[name] = unique_day
            ep_day = DaySchedule(
                Name=name, Type=self.Type, Values=[unique_day[i] for i in range(24)]
            )
            ep_days.append(ep_day)

        # create unique weeks from unique days
        try:
            unique_weeks, nwsi, nws, count = np.unique(
                full_year[: 364 * 24, ...].reshape(-1, 168),
                return_index=True,
                axis=0,
                return_inverse=True,
                return_counts=True,
            )
        except ValueError as e:
            raise ValueError(
                "Looks like the idf model needs to be rerun with 'annual=True'"
            ) from e

        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)

        dict_week = {}
        for count_week, unique_week in enumerate(unique_weeks):
            week_id = f"w_{self.Name}_{count_week:02d}"
            dict_week[week_id] = {}
            for i, day in zip(list(range(0, 7)), list(c.iterweekdays())):
                day_of_week = unique_week[..., i * 24 : (i + 1) * 24]
                for key, ep_day in zip(dict_day, ep_days):
                    if (day_of_week == dict_day[key]).all():
                        dict_week[week_id][f"day_{day}"] = ep_day

        ep_weeks = {}
        for week_id in dict_week:
            ep_week = WeekSchedule(
                Name=week_id,
                Days=[dict_week[week_id][f"day_{day_num}"] for day_num in c.iterweekdays()],
            )
            ep_weeks[week_id] = ep_week

        blocks = {}
        from_date = datetime(self.year, 1, 1)
        bincount = [
            sum(1 for _ in group) for key, group in groupby(nws + 1) if key
        ]
        week_order = dict(
            enumerate(
                np.array([key for key, group in groupby(nws + 1) if key]) - 1
            )
        )
        for i, (_, count) in enumerate(zip(week_order, bincount)):
            week_id = list(dict_week)[week_order[i]]
            to_date = from_date + timedelta(days=int(count * 7), hours=-1)
            blocks[i] = YearSchedulePart(
                FromDay=from_date.day,
                FromMonth=from_date.month,
                ToDay=to_date.day,
                ToMonth=to_date.month,
                Schedule=ep_weeks[week_id],
            )
            from_date = to_date + timedelta(hours=1)

            # If this is the last block, force end of year
            if i == len(bincount) - 1:
                blocks[i].ToDay = 31
                blocks[i].ToMonth = 12

        ep_year = YearSchedule(
            self.Name, Type=self.Type, Parts=list(blocks.values())
        )

        return ep_year, list(ep_weeks.values()), ep_days

    def develop(self):
        """Develop the UmiSchedule into a Year-Week-Day schedule structure."""
        year, weeks, days = self.to_year_week_day()
        lines = [f"- {obj}" for obj in self.predecessors]

        _from = "\n".join(lines)
        year.Comments = (f"Year Week Day schedules created from: \n{_from}" + str(id(self)),)
        year.quantity = self.quantity
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

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "Category": self.Category,
            "Type": self.Type,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter([value for value in UmiSchedule.CREATED_OBJECTS if value.id == ref["$ref"]]),
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
        low = resample.min().mean()
        mean = resample.mean().mean()
        high = resample.max().mean()
        return (
            name
            + ": "
            + f"mean daily min:{low:.2f} mean:{mean:.2f} max:{high:.2f} "
            + (f"quantity {self.quantity}" if self.quantity is not None else "")
        )

    def __str__(self):
        """Return the string representation of self."""
        return repr(self)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

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
        return repr(self)

    def __repr__(self):
        return "".join([f"{k}={v}" for k, v in self.to_dict().items()])

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        return {
            "FromDay": self.FromDay,
            "FromMonth": self.FromMonth,
            "ToDay": self.ToDay,
            "ToMonth": self.ToMonth,
            "Schedule": self.Schedule,
        }

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
        yield from self.mapping().items()

    def __hash__(self):
        """Return the hash value of self."""
        return id(self)


class DaySchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles daily schedules."""

    __slots__ = ()

    def __init__(self, Name, Values, Category="Day", **kwargs):
        """Initialize a DaySchedule object with parameters.

        Args:
            Values (list): List of 24 values.
            Name (str): Name of the schedule.
            Category (str): category identification (default: "Day").
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
        """
        super().__init__(Category=Category, Name=Name, Values=Values, **kwargs)

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        return np.array(self._values)

    @all_values.setter
    def all_values(self, value):
        self._values = validators.iterable(value, maximum_length=24)

    @classmethod
    def from_idf_object(cls, obj, doc=None, strict=False, **kwargs):
        """Create a DaySchedule from an idfkit IdfObject.

        This method accepts ``Schedule:Day:Hourly``, ``Schedule:Day:List`` and
        ``Schedule:Day:Interval`` objects.

        Args:
            obj: The idfkit schedule object.
            doc: The idfkit Document (for looking up related objects).
            strict (bool): Unused, kept for API compatibility.
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
        """
        obj_type = obj.type_name.lower()
        assert obj_type in (
            "schedule:day:hourly",
            "schedule:day:list",
            "schedule:day:interval",
        ), (
            f"Input error for '{obj.type_name}'. Expected one of "
            f"('Schedule:Day:Hourly', 'Schedule:Day:List', "
            f"'Schedule:Day:Interval')"
        )

        if obj_type == "schedule:day:hourly":
            values = [getattr(obj, f"hour_{i}") for i in range(1, 25)]
        elif obj_type == "schedule:day:list":
            values = _parse_day_list(obj)
        elif obj_type == "schedule:day:interval":
            values = _parse_day_interval(obj)

        type_name = cls.get_schedule_type_limits_name(obj)
        return cls(
            Name=obj.name,
            Type=type_name,
            Values=values,
            **kwargs,
        )

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

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "Category": self.Category,
            "Type": self.Type,
            "Values": self.all_values.round(3).tolist(),
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

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
        return super().__hash__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(self.Name, Values=self.all_values.tolist())



class WeekSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles weekly schedules."""

    __slots__ = ("_days",)

    def __init__(self, Name, Days=None, Category="Week", **kwargs):
        """Initialize a WeekSchedule object with parameters.

        Args:
            Days (list of DaySchedule): list of :class:`DaySchedule`.
            **kwargs:
        """
        super().__init__(Name, Category=Category, **kwargs)
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
    def from_idf_object(cls, obj, doc=None, **kwargs):
        """Create a WeekSchedule from a Schedule:Week:Daily idfkit object.

        Args:
            obj: The idfkit Schedule:Week:Daily object.
            doc: The idfkit Document for resolving referenced day schedules.
            **kwargs: keywords passed to the constructor.
        """
        assert (
            obj.type_name.lower() == "schedule:week:daily"
        ), f"Expected a 'schedule:week:daily' not a '{obj.type_name.lower()}'"
        Days = WeekSchedule.get_days(obj, doc=doc, **kwargs)
        sched = cls(
            Name=obj.name,
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

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "Category": self.Category,
            "Days": self.Days,
            "Type": self.Type,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    @classmethod
    def get_days(cls, obj, doc=None, **kwargs):
        """Get the DaySchedules referenced in a Schedule:Week:Daily object.

        Args:
            obj: The idfkit Schedule:Week:Daily object.
            doc: The idfkit Document for resolving referenced day schedules.
            **kwargs: Keywords forwarded to :meth:`DaySchedule.from_idf_object`.

        Returns:
            list of DaySchedule: The list of DaySchedules referenced by *obj*.
        """
        assert (
            obj.type_name.lower() == "schedule:week:daily"
        ), f"Expected a 'schedule:week:daily' not a '{obj.type_name.lower()}'"
        Days = []
        dayname = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        for day in dayname:
            day_sched_name = getattr(obj, f"{day}_schedule_day_name")
            day_obj = _find_day_schedule(doc, day_sched_name)
            Days.append(DaySchedule.from_idf_object(day_obj, doc=doc, **kwargs))

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
        return super().__hash__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(Name=self.Name, Days=self.Days)

    @property
    def children(self):
        return self.Days


class YearSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles yearly schedules."""

    def __init__(self, Name, Type="Fraction", Parts=None, Category="Year", idf_obj=None, doc=None, **kwargs):
        """Initialize a YearSchedule object with parameters.

        Args:
            Category (str): Category identification.
            Name (str): Name of the schedule.
            Type (str or ScheduleTypeLimits): Schedule type limits.
            Parts (list of YearSchedulePart): The YearScheduleParts.
            idf_obj: Optional idfkit object for ``Schedule:Year``.
            doc: Optional idfkit Document for resolving references.
            **kwargs: Keywords passed to :class:`UmiSchedule`.
        """
        self._idf_obj = idf_obj
        self._doc = doc
        if Parts is None and idf_obj is not None:
            self.Parts = self._get_parts(idf_obj)
        elif Parts is not None:
            self.Parts = Parts
        else:
            self.Parts = []
        super().__init__(Name=Name, Type=Type, Category=Category, **kwargs)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, YearSchedule):
            return NotImplemented
        else:
            return all([self.Type == other.Type, self.Parts == other.Parts])

    def __hash__(self):
        """Return the hash value of self."""
        return super().__hash__()

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        if self._values is None:
            index = pd.date_range(start=self.startDate, freq="1h", periods=8760)
            series = pd.Series(index=index, dtype="float")
            for part in self.Parts:
                start = f"{self.year}-{part.FromMonth}-{part.FromDay}"
                end = f"{self.year}-{part.ToMonth}-{part.ToDay}"
                # Get week values from all_values of Days
                one_week = np.array([item for sublist in part.Schedule.Days for item in sublist.all_values])

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
        Parts: list[YearSchedulePart] = [
            YearSchedulePart.from_dict(data, week_schedules) for data in data.pop("Parts", None)
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

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "Category": self.Category,
            "Parts": self.Parts,
            "Type": self.Type,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    def _get_parts(self, idf_obj):
        """Build YearScheduleParts from an idfkit Schedule:Year object.

        The Schedule:Year object has repeating groups of five fields:
        ``schedule_week_name_N``, ``start_month_N``, ``start_day_N``,
        ``end_month_N``, ``end_day_N``.  We iterate until the fields are
        missing or empty.

        Args:
            idf_obj: An idfkit object of type ``Schedule:Year``.

        Returns:
            list of YearSchedulePart
        """
        parts = []
        idx = 1
        while True:
            week_name = getattr(idf_obj, f"schedule_week_name_{idx}", None)
            if week_name is None or week_name == "":
                break
            from_month = getattr(idf_obj, f"start_month_{idx}", None)
            from_day = getattr(idf_obj, f"start_day_{idx}", None)
            to_month = getattr(idf_obj, f"end_month_{idx}", None)
            to_day = getattr(idf_obj, f"end_day_{idx}", None)
            if from_month is None:
                break

            # Resolve the week schedule -- first look in already-created objects,
            # then fall back to building from the doc if available.
            week_sched = next(
                (
                    x
                    for x in self._CREATED_OBJECTS
                    if x.Name == week_name and type(x).__name__ == "WeekSchedule"
                ),
                None,
            )
            if week_sched is None and self._doc is not None:
                week_obj = self._doc["Schedule:Week:Daily"][week_name]
                week_sched = WeekSchedule.from_idf_object(week_obj, doc=self._doc)

            parts.append(
                YearSchedulePart(
                    int(from_day),
                    int(from_month),
                    int(to_day),
                    int(to_month),
                    week_sched,
                )
            )
            idx += 1
        return parts

    def to_ref(self):
        """Return a ref pointer to self."""
        return {"$ref": str(self.id)}

    @property
    def children(self):
        return tuple(p.Schedule for p in self.Parts)
