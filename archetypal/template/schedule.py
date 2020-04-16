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
from archetypal import Schedule, log
from archetypal.template import UmiBase, Unique, UniqueName
from eppy.bunch_subclass import EpBunch


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """Class that handles Schedules as"""

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(UmiSchedule, self).__init__(*args, **kwargs)

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
    def from_values(cls, Name, values, **kwargs):
        """
        Args:
            Name:
            values:
            **kwargs:
        """
        return super(UmiSchedule, cls).from_values(Name=Name, values=values, **kwargs)

    @classmethod
    def from_yearschedule(cls, year_sched):
        """
        Args:
            year_sched:
        """
        if isinstance(year_sched, YearSchedule):
            return cls.from_values(
                Name=year_sched.Name,
                values=year_sched.all_values,
                schTypeLimitsName=year_sched.schTypeLimitsName,
            )

    def __add__(self, other):
        return self.combine(other)

    def __repr__(self):
        name = self.Name
        resample = self.series.resample("D")
        min = resample.min().mean()
        mean = resample.mean().mean()
        max = resample.max().mean()
        return (
            name
            + ": "
            + "mean daily min:{:.2f} mean:{:.2f} max:{:.2f}".format(min, mean, max)
        )

    def __str__(self):
        return repr(self)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, UmiSchedule):
            return False
        else:
            return all(
                [
                    self.strict == other.strict,
                    self.schType == other.schType,
                    self.schTypeLimitsName == other.schTypeLimitsName,
                    np.array_equal(self.all_values, other.all_values),
                ]
            )

    def combine(self, other, weights=None, quantity=None):
        """Combine two UmiSchedule objects together.

        Args:
            other (UmiSchedule): The other Schedule object to combine with.
            weights (list): Attribute of self and other containing the weight
                factor.
            quantity (list or dict): Scalar value that will be multiplied by self before
                the averaging occurs. This ensures that the resulting schedule
                returns the correct integrated value. If a dict is passed, keys are
                schedules Names and values are quantities.

        Returns:
            (UmiSchedule): the combined UmiSchedule object.
        """
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
                [self.all_values * quantity[self.Name], other.all_values * quantity[
                    other.Name]],
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

        attr = self.__dict__.copy()
        attr.update(dict(values=new_values))
        attr["Name"] = meta["Name"]
        new_obj = super().from_values(**attr)
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
                    Comments="Year Week Day schedules created from: {}".format(
                        "\n".join(lines)
                    ),
                )
            )
        newweeks = []
        for week in weeks:
            newweeks.append(
                WeekSchedule.from_epbunch(
                    week,
                    Comments="Year Week Day schedules created from: {}".format(
                        "\n".join(lines)
                    ),
                )
            )
        year = YearSchedule(
            idf=self.idf,
            Name=year.Name,
            id=self.id,
            schTypeLimitsName=self.schTypeLimitsName,
            epbunch=year,
            newweeks=newweeks,
            Comments="Year Week Day schedules created from: "
            "{}".format("\n".join(lines)),
        )
        return year

    def to_json(self):
        """UmiSchedule does not implement the to_json method because it is not
        used when generating the json file. Only Year-Week- and DaySchedule
        classes are used
        """
        pass

    def to_dict(self):
        year_sched = self.develop()
        return year_sched.to_dict()


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
    def from_json(cls, all_objects, *args, **kwargs):
        """
        Args:
            all_objects:
            *args:
            **kwargs:
        """
        ysp = cls(*args, **kwargs)
        ref = kwargs.get("Schedule", None)
        ysp.Schedule = all_objects.get_ref(ref)

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
            **kwargs
        )
        sched.values = sched.get_schedule_values(epbunch)
        return sched

    @classmethod
    def from_values(cls, Values, **kwargs):
        """Create a DaySchedule from an array of size (24,)

        Args:
            Values (array-like): A list of values of length 24.
            **kwargs: Keywords passed to the :class:`UmiSchedule` constructor.
                See :class:`UmiSchedule` for more details.
        """
        sched = cls(**kwargs)
        sched.values = Values

        return sched

    @classmethod
    def from_json(cls, Type, **kwargs):
        """Create a DaySchedule from a Umi Template json file.

        Args:
            Type (str): The schedule type limits name.
            **kwargs:
        """
        values = kwargs.pop("Values")
        sched = cls.from_values(values, schTypeLimitsName=Type, **kwargs)

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
        return np.array(self.values)

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
    def from_json(cls, **kwargs):
        """
        Args:
            **kwargs:
        """
        sch_type_limits_name = kwargs.pop("Type")
        wc = cls(schTypeLimitsName=sch_type_limits_name, **kwargs)
        days = kwargs.get("Days", None)
        wc.Days = [wc.get_ref(day) for day in days]
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
                self.all_objects[
                    hash(("DaySchedule", week_day_schedule_name, self.DataSource))
                ]
            )

        return blocks

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}


class YearSchedule(UmiSchedule):
    """Superclass of UmiSchedule that handles yearly schedules."""

    def __init__(self, *args, **kwargs):
        """Initialize a YearSchedule object with parameters:

        Args:
            *args:
            **kwargs:
        """
        super(YearSchedule, self).__init__(*args, **kwargs)
        self.epbunch = kwargs.get("epbunch", None)
        parts = kwargs.get("Parts", None)
        if parts is None:
            self.Parts = self.get_parts(self.epbunch)
        else:
            self.Parts = parts

    @property
    def all_values(self):
        index = pd.date_range(start=self.startDate, freq="1H", periods=8760)
        series = pd.Series(index=index)
        for part in self.Parts:
            start = "{}-{}-{}".format(self.year, part.FromMonth, part.FromDay)
            end = "{}-{}-{}".format(self.year, part.ToMonth, part.ToDay)
            one_week = np.array(
                [item for sublist in part.Schedule.Days for item in sublist.all_values]
            )
            all_weeks = np.resize(one_week, len(series.loc[start:end]))
            series.loc[start:end] = all_weeks
        return series.values

    @classmethod
    def from_json(cls, **kwargs):
        """
        Args:
            **kwargs:
        """
        schtypelimitsname = kwargs.pop("Type")
        ys = cls(schTypeLimitsName=schtypelimitsname, **kwargs)
        parts = kwargs.get("Parts", None)

        ys.Parts = [
            YearScheduleParts.from_json(all_objects=ys, **part) for part in parts
        ]
        ys.schType = "Schedule:Year"
        return UmiSchedule.from_yearschedule(ys)

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
                    self.all_objects[
                        hash(("WeekSchedule", week_day_schedule_name, self.DataSource))
                    ],
                )
            )
        return parts

    def to_dict(self):
        """returns umi template repr"""
        return {"$ref": str(self.id)}
