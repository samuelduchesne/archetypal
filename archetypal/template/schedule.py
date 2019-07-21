################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

import numpy as np
import pandas as pd

from archetypal import Schedule
from archetypal.template import UmiBase, Unique


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """Schedules



    """

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        kwargs['sch_name'] = kwargs.get('Name', None)
        super(UmiSchedule, self).__init__(*args, **kwargs)

        self.Type = self.schTypeLimitsName

    @classmethod
    def constant_schedule(cls, hourly_value=1, Name='AlwaysOn',
                          idf=None, **kwargs):
        return super(UmiSchedule, cls).constant_schedule(
            hourly_value=hourly_value,
            Name=Name,
            idf=idf, **kwargs)

    @classmethod
    def from_values(cls, sch_name, values, **kwargs):
        return super(UmiSchedule, cls).from_values(sch_name=sch_name,
                                                   values=values,
                                                   Name=sch_name,
                                                   **kwargs)

    @classmethod
    def from_yearschedule(cls, year_sched):
        if isinstance(year_sched, YearSchedule):
            return cls.from_values(sch_name=year_sched.Name,
                                   values=year_sched.all_values,
                                   Type=year_sched.Type)

    def __add__(self, other):
        return self.combine(other)

    def __repr__(self):
        name = self.schName
        resample = self.series.resample('D')
        min = resample.min().mean()
        mean = resample.mean().mean()
        max = resample.max().mean()
        return name + ': ' + \
               "mean daily min:{:.2f} mean:{:.2f} max:{:.2f}".format(min, mean,
                                                                     max)

    def __str__(self):
        return repr(self)

    def __hash__(self):
        return hash(repr(self))

    def combine(self, other, weights=None):
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # check if the schedule is the same

        if all(self.all_values == other.all_values):
            return self
        if not weights:
            weights = [1, 1]
        new_values = np.average([self.all_values, other.all_values],
                                axis=0, weights=weights)

        # the new object's name
        name = '+'.join([self.schName, other.schName])

        attr = self.__dict__
        attr.update(dict(value=new_values))
        attr.pop('Name', None)
        new_obj = super().from_values(sch_name=name, Name=name, **attr)

        return new_obj

    def develop(self):
        year, weeks, days = self.to_year_week_day()

        newdays = []
        for day in days:
            newdays.append(
                DaySchedule(Name=day.Name, idf=self.idf, epbunch=day,
                            Type=self.Type,
                            Comments='Year Week Day schedules created from: '
                                     '{}'.format(self.Name)))
        newweeks = []
        for week in weeks:
            newweeks.append(WeekSchedule(Name=week.Name, idf=self.idf,
                                         Type=self.Type,
                                         epbunch=week, newdays=newdays,
                                         Comments='Year Week Day schedules '
                                                  'created from: '
                                                  '{}'.format(self.Name)))
        year = YearSchedule(Name=year.Name, id=self.id, idf=self.idf,
                            Type=self.Type,
                            epbunch=year,
                            newweeks=newweeks,
                            Comments='Year Week Day schedules created from: '
                                     '{}'.format(self.Name))
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


class YearScheduleParts():
    def __init__(self, FromDay=None, FromMonth=None, ToDay=None, ToMonth=None,
                 Schedule=None):
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
        ref = kwargs.get('Schedule', None)
        ysp.Schedule = all_objects.get_ref(ref)

        return ysp

    def to_dict(self):
        return collections.OrderedDict(FromDay=self.FromDay,
                                       FromMonth=self.FromMonth,
                                       ToDay=self.ToDay,
                                       ToMonth=self.ToMonth,
                                       Schedule={'$ref': str(self.Schedule.id)})

    def __str__(self):
        return str(self.to_dict())


class DaySchedule(UmiSchedule):
    """
    $id, Category, Comments, DataSource, Name, Type, Values
    """

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(DaySchedule, self).__init__(*args, **kwargs)

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Values"] = self.all_values.tolist()
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_dict(self):
        return {'$ref': str(self.id)}


class WeekSchedule(UmiSchedule):
    """
    $id, Category, Comments, DataSource, Days, Name, Type
    """

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(WeekSchedule, self).__init__(*args, **kwargs)

        days = kwargs.get('Days', None)
        if days is None:
            self.Days = self.get_days(kwargs['epbunch'])
        else:
            self.Days = days
        _type = kwargs.get('Type', None)
        if type is None:
            self.schLimitType = self.get_schedule_type_limits_name()
        else:
            self.schLimitType = _type

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        wc = cls(*args, **kwargs)
        days = kwargs.get('Days', None)
        wc.Days = [wc.get_ref(day) for day in days]
        return wc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Week"
        data_dict["Days"] = [day.to_dict() for day in self.Days]
        data_dict["Type"] = self.schLimitType
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
        dayname = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
                   'Thursday', 'Friday', 'Saturday']
        for day in dayname:
            week_day_schedule_name = epbunch[
                "{}_ScheduleDay_Name".format(day)]
            blocks.append(
                self.all_objects[('DaySchedule',
                                  week_day_schedule_name)]
            )

        return blocks

    def to_dict(self):
        return {'$ref': str(self.id)}


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
        self.Comments = kwargs.get('Comments', '')
        self.epbunch = kwargs.get('epbunch', None)
        type = kwargs.get('Type', None)
        if type is None:
            self.Type = self.schTypeLimitsName
        else:
            self.Type = type
        parts = kwargs.get('Parts', None)
        if parts is None:
            self.Parts = self.get_parts(self.epbunch)
        else:
            self.Parts = parts
        type = kwargs.get('Type', None)
        if type is None:
            self.schLimitType = self.get_schedule_type_limits_name()
        else:
            self.schLimitType = type

    @property
    def all_values(self):
        index = pd.DatetimeIndex(start=self.startDate, freq='1H', periods=8760)
        series = pd.Series(index=index)
        for part in self.Parts:
            start = "{}-{}-{}".format(self.year, part.FromMonth, part.FromDay)
            end = "{}-{}-{}".format(self.year, part.ToMonth, part.ToDay)
            one_week = np.array(
                [item for sublist in part.Schedule.Days for item in
                 sublist.Values])
            all_weeks = np.resize(one_week, len(series.loc[start:end]))
            series.loc[start:end] = all_weeks
        return series.values

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        ys = cls(*args, **kwargs)
        parts = kwargs.get('Parts', None)

        ys.Parts = [YearScheduleParts.from_json(all_objects=ys, **part) for
                    part in parts]
        ys.schType = 'Schedule:Year'
        return UmiSchedule.from_yearschedule(ys)

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Year"
        data_dict["Parts"] = [part.to_dict() for part in self.Parts]
        data_dict["Type"] = self.schLimitType
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
            week_day_schedule_name = epbunch[
                'ScheduleWeek_Name_{}'.format(i + 1)]

            FromMonth = epbunch['Start_Month_{}'.format(i + 1)]
            ToMonth = epbunch['End_Month_{}'.format(i + 1)]
            FromDay = epbunch['Start_Day_{}'.format(i + 1)]
            ToDay = epbunch['End_Day_{}'.format(i + 1)]
            parts.append(YearScheduleParts(FromDay, FromMonth, ToDay,
                                           ToMonth, self.all_objects[
                                               ('WeekSchedule',
                                                week_day_schedule_name)]))
        return parts

    def to_dict(self):
        return {'$ref': str(self.id)}
