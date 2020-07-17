################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import uuid

import numpy as np
import pandas as pd
from deprecation import deprecated
from eppy.bunch_subclass import EpBunch

import archetypal
from archetypal import Schedule, log
from archetypal.template import UmiBase, Unique, UniqueName, CREATED_OBJECTS


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """Class that handles Schedules as"""

    def __init__(self, *args, quantity=None, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(UmiSchedule, self).__init__(*args, **kwargs)
        self.quantity = quantity

    @classmethod
    def constant_schedule(cls, hourly_value=1, Name="AlwaysOn", idf=None, **kwargs):
        """
        Args:
            hourly_value:
            Name:
            idf:
            **kwargs:
        """
        return super(UmiSchedule, cls).constant_schedule(
            hourly_value=hourly_value, Name=Name, idf=idf, **kwargs
        )

    @classmethod
    def from_values(cls, Name, values, idf, schTypeLimitsName="Fraction", **kwargs):
        """
        Args:
            Name:
            values:
            idf:
            schTypeLimitsName:
            **kwargs:
        """
        return super(UmiSchedule, cls).from_values(
            Name=Name,
            values=values,
            schTypeLimitsName=schTypeLimitsName,
            idf=idf,
            **kwargs,
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
                values=year_sched.all_values,
                schTypeLimitsName=year_sched.schTypeLimitsName,
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
        return hash((self.__class__.__name__, self.Name))

    def __eq__(self, other):
        if not isinstance(other, UmiSchedule):
            return False
        else:
            return all(
                [
                    self.Name == other.Name,
                    self.strict == other.strict,
                    self.schType == other.schType,
                    self.schTypeLimitsName == other.schTypeLimitsName,
                    self.quantity == other.quantity,
                    np.array_equal(self.all_values, other.all_values),
                ]
            )

    def combine(self, other, weights=None, quantity=None):
        """Combine two UmiSchedule objects together.

        Args:
            other (UmiSchedule): The other Schedule object to combine with.
            weights (list): Attribute of self and other containing the weight
                factor.
            quantity (list, dict or callable): Scalar value that will be multiplied by
                self before the averaging occurs. This ensures that the
                resulting schedule returns the correct integrated value. If a
                dict is passed, keys are schedules Names and values are
                quantities.

        Returns:
            (UmiSchedule): the combined UmiSchedule object.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        if not isinstance(other, self.__class__):
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # check if the schedule is the same
        if all(self.all_values == other.all_values):
            return self

        # check if self is only zeros. Should not affect other.
        if all(self.all_values == 0):
            return other
        # check if other is only zeros. Should not affect self.
        if all(other.all_values == 0):
            return self

        if not weights:
            log(
                'using 1 as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [1, 1]
        elif isinstance(weights, str):
            weights = [getattr(self, weights), getattr(other, weights)]

        if quantity is None:
            new_values = np.average(
                [self.all_values, other.all_values], axis=0, weights=weights
            )
        elif isinstance(quantity, dict):
            new_values = np.average(
                [
                    self.all_values * quantity[self.Name],
                    other.all_values * quantity[other.Name],
                ],
                axis=0,
                weights=weights,
            )
            new_values /= new_values.max()
        elif callable(quantity):
            new_values = np.average(
                [
                    self.all_values * quantity(self.predecessors.data),
                    other.all_values * quantity(other.predecessors.data),
                ],
                axis=0,
                weights=weights,
            )
            new_values /= new_values.max()
        else:
            new_values = np.average(
                [self.all_values * quantity[0], other.all_values * quantity[1]],
                axis=0,
                weights=weights,
            )
            new_values /= new_values.max()

        # the new object's name
        meta = self._get_predecessors_meta(other)

        new_obj = UmiSchedule.from_values(
            values=new_values, schTypeLimitsName="Fraction", idf=self.idf, **meta
        )
        new_name = (
            "Combined Schedule {{{}}} with mean daily min:{:.2f} "
            "mean:{:.2f} max:{:.2f}".format(
                uuid.uuid1(), new_obj.min, new_obj.mean, new_obj.max
            )
        )
        new_obj.rename(new_name)
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
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
                )
            )
        Parts = []
        for i, week in zip(range(int(len(year.fieldvalues[3:]) / 5)), weeks):

            Parts.append(
                YearScheduleParts(
                    FromMonth=year["Start_Month_{}".format(i + 1)],
                    ToMonth=year["End_Month_{}".format(i + 1)],
                    FromDay=year["Start_Day_{}".format(i + 1)],
                    ToDay=year["End_Day_{}".format(i + 1)],
                    Schedule=WeekSchedule.from_epbunch(
                        week,
                        Comments="Year Week Day schedules created from:\n{}".format(
                            "\n".join(lines)
                        ),
                    ),
                )
            )

        _from = "\n".join(lines)
        self.Comments = f"Year Week Day schedules created from: \n{_from}"
        self.__class__ = YearSchedule
        self.epbunch = year
        self.Parts = Parts
        return self

    def to_json(self):
        """UmiSchedule does not implement the to_json method because it is not
        used when generating the json file. Only Year-Week- and DaySchedule
        classes are used
        """

        return self.to_dict()

    def to_dict(self):
        self.validate()  # Validate object before trying to get json format
        self.develop()  # Develop into Year-, Week- and DaySchedules
        return {"$ref": str(self.id)}

    def validate(self):
        """Validates UmiObjects and fills in missing values"""
        return self


class YearScheduleParts:
    """Helper Class for YearSchedules that are defined using FromDay FromMonth
    ToDay ToMonth attributes.
    """

    def __init__(
        self, FromDay=None, FromMonth=None, ToDay=None, ToMonth=None, Schedule=None
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
        """
        self.FromDay = FromDay
        self.FromMonth = FromMonth
        self.ToDay = ToDay
        self.ToMonth = ToMonth
        self.Schedule = Schedule

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
    def from_dict(cls, *args, **kwargs):
        """
        Args:
            all_objects:
            *args:
            **kwargs:
        """
        ysp = cls(*args, **kwargs)
        ref = kwargs.get("Schedule", None)
        ysp.Schedule = UmiBase.get_classref(ref)

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


class DaySchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles daily schedules."""

    def __init__(self, **kwargs):
        """Initialize a DaySchedule object with parameters:

        Args:
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
        """
        super(DaySchedule, self).__init__(**kwargs)

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
        sched._values = sched.get_schedule_values(epbunch)
        return sched

    @classmethod
    def from_values(cls, Name, Values, idf, schTypeLimitsName="Fraction", **kwargs):
        """Create a DaySchedule from an array of size (24,)

        Args:
            Name:
            Values (array-like): A list of values of length 24.
            idf (IDF): The idf model.
            schTypeLimitsName:
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """
        return cls(
            Name=Name,
            values=Values,
            schTypeLimitsName=schTypeLimitsName,
            idf=idf,
            **kwargs,
        )

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

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Values"] = self.all_values.round(3).tolist()
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @property
    def all_values(self):
        return np.array(self._values)

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}


class WeekSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles weekly schedules."""

    def __init__(self, days=None, **kwargs):
        """Initialize a WeekSchedule object with parameters:

        Args:
            days (list of DaySchedule): list of :class:`DaySchedule`.
            **kwargs:
        """
        super(WeekSchedule, self).__init__(**kwargs)
        self.Days = days

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """
        Args:
            epbunch:
            **kwargs:
        """
        sched = cls(
            idf=epbunch.theidf, Name=epbunch.Name, schType=epbunch.key, **kwargs
        )
        sched.Days = sched.get_days(epbunch)

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
    def from_dict(cls, **kwargs):
        """
        Args:
            **kwargs:
        """
        sch_type_limits_name = kwargs.pop("Type")
        Days = [UmiBase.get_classref(ref) for ref in kwargs.pop("Days")]
        wc = cls(schTypeLimitsName=sch_type_limits_name, days=Days, **kwargs)
        return wc

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        data_dict["Days"] = [day.to_dict() for day in self.Days]
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def get_days(self, epbunch):
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
                        for x in self.all_objects
                        if x.Name == week_day_schedule_name
                        and type(x).__name__ == "DaySchedule"
                    ),
                    None,
                )
            )

        return blocks

    @property
    def all_values(self):
        return np.concatenate([day.all_values for day in self.Days])


    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}


class YearSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles yearly schedules."""

    def __init__(self, Name, schTypeLimitsName="Fraction", Parts=None, **kwargs):
        """Initialize a YearSchedule object with parameters:

        Args:
            Name:
            schTypeLimitsName:
            Parts (list of YearScheduleParts): The YearScheduleParts.
            **kwargs:
        """
        super(YearSchedule, self).__init__(
            Name=Name, schTypeLimitsName=schTypeLimitsName, **kwargs
        )
        self.epbunch = kwargs.get("epbunch", None)
        if Parts is None:
            self.Parts = self.get_parts(self.epbunch)
        else:
            self.Parts = Parts

    @classmethod
    def from_parts(cls, *args, Parts, **kwargs):
        """
        Args:
            *args:
            Parts (list of YearScheduleParts):
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
    def from_dict(cls, **kwargs):
        """
        Args:
            **kwargs:
        """
        schtypelimitsname = kwargs.pop("Type")
        Parts = [
            YearScheduleParts.from_dict(**part) for part in kwargs.pop("Parts", None)
        ]
        ys = cls(schTypeLimitsName=schtypelimitsname, Parts=Parts, **kwargs)
        ys.schType = "Schedule:Year"
        idf = kwargs.get("idf", None)
        return UmiSchedule.from_yearschedule(ys, idf=idf)

    def to_json(self):
        """Returns a dict-like representation of the schedule.

        Returns:
            dict: The dict-like representation of the schedule
        """
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

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
                YearScheduleParts(
                    FromDay,
                    FromMonth,
                    ToDay,
                    ToMonth,
                    next(
                        (
                            x
                            for x in self.all_objects
                            if x.Name == week_day_schedule_name
                            and type(x).__name__ == "WeekSchedule"
                        ),
                    ),
                )
            )
        return parts

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}
