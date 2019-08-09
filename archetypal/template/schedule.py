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
from archetypal.template import UmiBase, Unique
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
        return hash((self.__class__.__name__, self.Name))

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

    def combine(self, other, weights=None):
        """Combine two UmiSchedule objects together.

        Args:
            other (UmiSchedule):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

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
        if not weights:
            log(
                'using 1 as weighting factor in "{}" '
                "combine.".format(self.__class__.__name__)
            )
            weights = [1.0, 1.0]
        new_values = np.average(
            [self.all_values, other.all_values], axis=0, weights=weights
        )

        # the new object's name
        meta = self._get_predecessors_meta(other)

        attr = self.__dict__.copy()
        attr.update(dict(value=new_values))
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
    def __init__(
        self, FromDay=None, FromMonth=None, ToDay=None, ToMonth=None, Schedule=None
    ):
        """
        Args:
            FromDay:
            FromMonth:
            ToDay:
            ToMonth:
            Schedule:
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
    """A DaySchedule is a superclass of UmiSchedule and handles the conversion
    to and from the json UmiTemplate.
    """

    def __init__(self, **kwargs):
        """Initialize a DaySchedule object with parameters: :param **kwargs:
        keywords passed to the :class:`UmiSchedule`:param constructor. See
        :class:`UmiSchedule` for more info.:

        Args:
            **kwargs: Keywords passed to the :class:`UmiSchedule`
                constructor. See :class:`UmiSchedule` for more details.
        """
        super(DaySchedule, self).__init__(**kwargs)

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        """Create a DaySchedule from a :class:`EpBunch` object

        Args:
            epbunch (EpBunch): The EpBunch object to construct a DaySchedule
                from.
            **kwargs: Keywords passed to the :class:`UmiSchedule`
                constructor. See :class:`UmiSchedule` for more details.
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
            **kwargs: Keywords passed to the :class:`UmiSchedule`
             constructor. See :class:`UmiSchedule` for more details.
        """
        sched = cls(**kwargs)
        sched.values = Values

        return sched

    @classmethod
    def from_json(cls, Type, **kwargs):
        values = kwargs.pop("Values")
        sched = cls.from_values(values, schTypeLimitsName=Type, **kwargs)

        return sched

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Values"] = self.all_values.round(3).tolist()
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @property
    def all_values(self):
        return np.array(self.values)

    def to_dict(self):
        return {"$ref": str(self.id)}


class WeekSchedule(UmiSchedule):
    """
    $id, Category, Comments, DataSource, Days, Name, Type
    """

    def __init__(self, days=None, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(WeekSchedule, self).__init__(**kwargs)
        self.Days = days

    @classmethod
    def from_epbunch(cls, epbunch, **kwargs):
        sched = cls(
            idf=epbunch.theidf, Name=epbunch.Name, schType=epbunch.key, **kwargs
        )
        sched.Days = sched.get_days(epbunch)

        return sched

    @classmethod
    def from_json(cls, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        sch_type_limits_name = kwargs.pop("Type")
        wc = cls(schTypeLimitsName=sch_type_limits_name, **kwargs)
        days = kwargs.get("Days", None)
        wc.Days = [wc.get_ref(day) for day in days]
        return wc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        data_dict["Days"] = [day.to_dict() for day in self.Days]
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def get_days(self, epbunch):
        """
        Args:
            epbunch (EpBunch):
        """
        blocks = []
        dayname = [
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        ]
        for day in dayname:
            week_day_schedule_name = epbunch["{}_ScheduleDay_Name".format(day)]
            blocks.append(self.all_objects[hash(("DaySchedule", week_day_schedule_name))])

        return blocks

    def to_dict(self):
        return {"$ref": str(self.id)}


class YearSchedule(UmiSchedule):
    """
    $id, Category, Comments, DataSource, Name, Parts, Type
    """

    def __init__(self, *args, **kwargs):
        """
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
        index = pd.DatetimeIndex(start=self.startDate, freq="1H", periods=8760)
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
            *args:
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
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

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
                    self.all_objects[hash(("WeekSchedule", week_day_schedule_name))],
                )
            )
        return parts

    def to_dict(self):
        return {"$ref": str(self.id)}
