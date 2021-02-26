################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import hashlib

import numpy as np
import pandas as pd
from deprecation import deprecated
from eppy.bunch_subclass import EpBunch

import archetypal
from archetypal import Schedule, log
from archetypal.template import UmiBase, UniqueName


class UmiSchedule(Schedule, UmiBase):
    """Class that handles Schedules as"""

    def __init__(self, *args, quantity=None, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(UmiSchedule, self).__init__(**kwargs)
        self.quantity = quantity

    @classmethod
    def constant_schedule(
        cls, hourly_value=1, Name="AlwaysOn", Type="Fraction", idf=None, **kwargs
    ):
        """
        Args:
            hourly_value:
            Name:
            idf:
            **kwargs:
        """
        return super(UmiSchedule, cls).constant_schedule(
            hourly_value=hourly_value, Name=Name, Type=Type, idf=idf, **kwargs
        )

    @classmethod
    def from_values(cls, Name, Values, idf, Type="Fraction", **kwargs):
        """
        Args:
            Name:
            Values:
            idf:
            Type:
            **kwargs:
        """
        return super(UmiSchedule, cls).from_values(
            Name=Name, Values=Values, Type=Type, idf=idf, **kwargs
        )

    @classmethod
    def from_yearschedule(cls, year_sched, idf=None):
        """
        Args:
            year_sched:
            idf:
        """
        if isinstance(year_sched, YearSchedule):
            return cls.from_values(
                Name=year_sched.Name,
                Values=year_sched.all_values,
                Type=year_sched.Type,
                idf=idf,
            )

    def __add__(self, other):
        return UmiSchedule.combine(self, other)

    def __repr__(self):
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
        return repr(self)

    def __hash__(self):
        return hash((self.__class__.__name__, getattr(self, "Name", None)))

    def __eq__(self, other):
        if not isinstance(other, UmiSchedule):
            return NotImplemented
        else:
            return all(
                [
                    # self.Name == other.Name,
                    self.strict == other.strict,
                    self.schType == other.schType,
                    self.Type == other.Type,
                    self.quantity == other.quantity,
                    np.allclose(self.all_values, other.all_values, rtol=1e-02)
                    if self.all_values.size == other.all_values.size
                    else False,
                ]
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
            l = len(weights)
            if l != 2:
                raise ValueError(
                    "USing a list or tuple, the weights attribute must "
                    "have a length of 2. A length of {}".format(l)
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
            self_quantity, other_quantity = self.quantity, other.quantity
            new_values = (
                self.all_values * self_quantity + other.all_values * other_quantity
            ) / (self_quantity + other_quantity)
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
            Values=new_values, Type="Fraction", quantity=quantity, idf=self.idf, **meta
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        new_obj.weights = sum(weights)
        return new_obj

    def develop(self):
        year, weeks, days = self.to_year_week_day()
        lines = ["- {}".format(obj) for obj in self.predecessors]

        newdays = []
        for day in days:
            newdays.append(
                DaySchedule.from_epbunch(
                    day,
                    Comments="Year Week Day schedules created from: \n{}".format(
                        "\n".join(lines)
                    ),
                    allow_duplicates=getattr(self, "_not_unique", False),
                    Category=self.Name,
                )
            )
        Parts = []
        weeks = {schd.Name: schd for schd in weeks}

        def chunks(lst, n):
            """Yield successive n-sized chunks from lst."""
            for i in range(0, len(lst), n):
                yield lst[i : i + n]

        for fields in chunks(year.fieldvalues[3:], 5):
            weekname, from_month, from_day, to_month, to_day = fields
            Parts.append(
                YearSchedulePart(
                    FromMonth=from_month,
                    ToMonth=to_month,
                    FromDay=from_day,
                    ToDay=to_day,
                    Schedule=WeekSchedule.from_epbunch(
                        weeks[weekname],
                        Comments="Year Week Day schedules created from:\n{}".format(
                            "\n".join(lines)
                        ),
                        Category=self.Name,
                        allow_duplicates=getattr(self, "_not_unique", False),
                    ),
                )
            )
        _from = "\n".join(lines)
        return YearSchedule(
            Name=self.Name,
            Parts=Parts,
            Type="Fraction",
            epbunch=year,
            Category=self.Name,
            Comments=f"Year Week Day schedules created from: \n{_from}" + str(id(self)),
            idf=self.idf,
            allow_duplicates=getattr(self, "_not_unique", False),
        )

    def get_unique(self):
        return super(UmiSchedule, self.develop()).get_unique()

    def to_json(self):
        """UmiSchedule does not implement the to_json method because it is not
        used when generating the json file. Only Year-Week- and DaySchedule
        classes are used
        """

        return self.to_dict()

    def to_dict(self):
        return {"$ref": str(self.id)}

    def validate(self):
        """Validate object and fill in missing values."""
        return self

    def mapping(self):
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


class YearSchedulePart:
    """Helper Class for YearSchedules that are defined using FromDay FromMonth
    ToDay ToMonth attributes.
    """

    def __init__(
        self,
        FromDay=None,
        FromMonth=None,
        ToDay=None,
        ToMonth=None,
        Schedule=None,
        **kwargs,
    ):
        """
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

    def __eq__(self, other):
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
        for k, v in self.mapping().items():
            yield k, v

    def __hash__(self):
        return id(self)

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
            all_objects:
            *args:
            **kwargs:
        """
        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, Schedule, **kwargs):
        """
        Args:
            all_objects:
            *args:
            **kwargs:
        """
        ref = UmiBase.get_classref(Schedule)
        ysp = cls(Schedule=ref, **kwargs)

        return ysp

    def to_dict(self):
        return collections.OrderedDict(
            FromDay=self.FromDay,
            FromMonth=self.FromMonth,
            ToDay=self.ToDay,
            ToMonth=self.ToMonth,
            Schedule={"$ref": str(self.Schedule.id)},
        )

    def __str__(self):
        return str(self.to_dict())

    def mapping(self):
        return dict(
            FromDay=self.FromDay,
            FromMonth=self.FromMonth,
            ToDay=self.ToDay,
            ToMonth=self.ToMonth,
            Schedule=self.Schedule,
        )

    def get_unique(self):
        return self


class DaySchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles daily schedules."""

    def __init__(self, Category="Day", **kwargs):
        """Initialize a DaySchedule object with parameters:

        Args:
            Category:
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
        """
        super(DaySchedule, self).__init__(Category=Category, **kwargs)

    def __eq__(self, other):
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
        return super(DaySchedule, self).__hash__()

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Create a DaySchedule from a :class:`~eppy.bunch_subclass.EpBunch`
        object

        Args:
            epbunch (EpBunch): The EpBunch object to construct a DaySchedule
                from.
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """

        sched = cls(
            idf=epbunch.theidf,
            Name=epbunch.Name,
            epbunch=epbunch,
            schType=epbunch.key,
            **kwargs,
        )

        return sched

    @classmethod
    def from_values(cls, Name, Values, idf, Type="Fraction", **kwargs):
        """Create a DaySchedule from an array of size (24,)

        Args:
            Name:
            Values (array-like): A list of values of length 24.
            idf (IDF): The idf model.
            Type:
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """
        return cls(Name=Name, Values=np.array(Values), Type=Type, idf=idf, **kwargs)

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, Type, **kwargs):

        """
        Args:
            Type:
            **kwargs:
        """
        return cls.from_dict(Type, **kwargs)

    @classmethod
    def from_dict(cls, Name, Values, Type, **kwargs):
        """Create a DaySchedule from a Umi Template json file.

        Args:
            Type (str): The schedule type limits name.
            **kwargs:
        """
        sched = cls.from_values(Name=Name, Values=Values, Type=Type, **kwargs)

        return sched

    def get_unique(self):
        return UmiBase.get_unique(self)

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Type"] = self.Type
        data_dict["Values"] = self.all_values.round(3).tolist()
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def mapping(self):
        return dict(
            Category=self.Category,
            Type=self.Type,
            Values=self.all_values.round(3).tolist(),
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    @property
    def all_values(self) -> np.ndarray:
        if self._values is None:
            self._values = self.get_schedule_values(self.epbunch)
        if isinstance(self._values, list):
            self._values = np.array(self._values)
        return self._values

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}


class WeekSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles weekly schedules."""

    def __init__(self, Days=None, Category="Week", **kwargs):
        """Initialize a WeekSchedule object with parameters:

        Args:
            Days (list of DaySchedule): list of :class:`DaySchedule`.
            **kwargs:
        """
        super(WeekSchedule, self).__init__(Category=Category, **kwargs)
        self.Days = Days

    def __eq__(self, other):
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
        return super(WeekSchedule, self).__hash__()

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """
        Args:
            epbunch:
            **kwargs:
        """
        Days = WeekSchedule.get_days(epbunch)
        sched = cls(
            idf=epbunch.theidf,
            Name=epbunch.Name,
            schType=epbunch.key,
            Days=Days,
            **kwargs,
        )

        return sched

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, **kwargs):

        """
        Args:
            **kwargs:
        """
        return cls.from_dict(**kwargs)

    @classmethod
    def from_dict(cls, Type, **kwargs):
        """
        Args:
            **kwargs:
        """
        refs = kwargs.pop("Days")
        Days = [UmiBase.get_classref(ref) for ref in refs]
        wc = cls(Type=Type, Days=Days, **kwargs)
        return wc

    def get_unique(self):
        return UmiBase.get_unique(self)

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Days"] = [day.to_dict() for day in self.Days]
        data_dict["Type"] = self.Type
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def mapping(self):
        return dict(
            Category=self.Category,
            Days=self.Days,
            Type=self.Type,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    @classmethod
    def get_days(cls, epbunch):
        """
        Args:
            epbunch (EpBunch):
        """
        blocks = []
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
            week_day_schedule_name = epbunch["{}_ScheduleDay_Name".format(day)]
            blocks.append(
                next(
                    (
                        x
                        for x in UmiBase.CREATED_OBJECTS
                        if x.Name == week_day_schedule_name
                        and type(x).__name__ == "DaySchedule"
                    ),
                    None,
                )
            )

        return blocks

    @property
    def all_values(self) -> np.ndarray:
        if self._values is None:
            self._values = np.concatenate([day.all_values for day in self.Days])
        return self._values

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}


class YearSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles yearly schedules."""

    def __init__(self, Name, Type="Fraction", Parts=None, Category="Year", **kwargs):
        """Initialize a YearSchedule object with parameters:

        Args:
            Category:
            Name:
            Type:
            Parts (list of YearSchedulePart): The YearScheduleParts.
            **kwargs:
        """
        self.epbunch = kwargs.get("epbunch", None)
        if Parts is None:
            self.Parts = self.get_parts(self.epbunch)
        else:
            self.Parts = Parts
        super(YearSchedule, self).__init__(
            Name=Name, Type=Type, schType="Schedule:Year", Category=Category, **kwargs
        )

    def __eq__(self, other):
        if not isinstance(other, YearSchedule):
            return NotImplemented
        else:
            return all([self.Type == other.Type, self.Parts == other.Parts])

    def __hash__(self):
        return super(YearSchedule, self).__hash__()

    @classmethod
    def from_parts(cls, *args, Parts, **kwargs):
        """
        Args:
            *args:
            Parts (list of YearSchedulePart):
            **kwargs:
        """
        ysp = cls(*args, Parts=Parts, **kwargs)
        ysp._values = ysp.all_values

        return ysp

    @property
    def all_values(self) -> np.ndarray:
        if self._values is None:
            index = pd.date_range(start=self.startDate, freq="1H", periods=8760)
            series = pd.Series(index=index)
            for part in self.Parts:
                start = "{}-{}-{}".format(self.year, part.FromMonth, part.FromDay)
                end = "{}-{}-{}".format(self.year, part.ToMonth, part.ToDay)
                try:  # Get week values from all_values of Days that are DaySchedule object
                    one_week = np.array(
                        [
                            item
                            for sublist in part.Schedule.Days
                            for item in sublist.all_values
                        ]
                    )
                except:  # Days are not DaySchedule object
                    try:  # Days is a list of 7 dicts (7 days in a week)
                        # Dicts are the id of Days ({"$ref": id})
                        day_values = [self.get_ref(day) for day in part.Schedule.Days]
                        values = []
                        for i in range(0, 7):  # There is 7 days a week
                            values = values + day_values[i].all_values.tolist()
                        one_week = np.array(values)
                    except:
                        msg = (
                            'Days are not a DaySchedule or dictionaries in the form "{'
                            '$ref: id}" '
                        )
                        raise NotImplementedError(msg)

                all_weeks = np.resize(one_week, len(series.loc[start:end]))
                series.loc[start:end] = all_weeks
            self._values = series.values
        return self._values

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, **kwargs):

        """
        Args:
            **kwargs:
        """
        return cls.from_dict(**kwargs)

    @classmethod
    def from_dict(cls, Type, **kwargs):
        """
        Args:
            **kwargs:
        """
        Parts = [
            YearSchedulePart.from_dict(**part) for part in kwargs.pop("Parts", None)
        ]
        ys = cls(Type=Type, Parts=Parts, **kwargs)
        ys.schType = "Schedule:Year"
        return ys

    def get_unique(self):
        return UmiBase.get_unique(self)

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = self.Category
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
        data_dict["Type"] = self.Type
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def mapping(self):
        self.validate()

        return dict(
            Category=self.Category,
            Parts=self.Parts,
            Type=self.Type,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def get_parts(self, epbunch):
        """
        Args:
            epbunch (EpBunch):
        """
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

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}
