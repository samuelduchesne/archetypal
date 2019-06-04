################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import random

from archetypal import Schedule
from archetypal.template import UmiBase, Unique


class UmiSchedule(Schedule, UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, DataSource, Name, Parts, Type
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
    def random_constant_schedule(cls, seed=1, **kwargs):
        """
        Args:
            seed:
            **kwargs:
        """
        randint = random.randint(25, 50)
        name = 'Constant_value_{}'.format(randint)
        random.seed(seed)

        sched = cls.constant_schedule(Name=name, **kwargs)
        sched = cls(Name=name, idf=sched.idf)
        return sched

    @classmethod
    def from_idf(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        sched = cls(*args, **kwargs)
        sched.develop()
        return sched

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(repr(self))

    def develop(self):
        year, weeks, days = self.to_year_week_day()

        newdays = []
        for day in days:
            newdays.append(
                DaySchedule(Name=day.Name, idf=self.idf, epbunch=day,
                            Comments='Year Week Day schedules created from: '
                                     '{}'.format(self.Name)))
        newweeks = []
        for week in weeks:
            newweeks.append(WeekSchedule(Name=week.Name, idf=self.idf,
                                         epbunch=week, newdays=newdays,
                                         Comments='Year Week Day schedules '
                                                  'created from: '
                                                  '{}'.format(self.Name)))
        year = YearSchedule(Name=year.Name, id=self.id, idf=self.idf,
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
        self.Values = kwargs.get('Values', None)

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Category"] = "Day"
        data_dict["Type"] = self.schTypeLimitsName
        data_dict["Values"] = self.Values
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
        day: DaySchedule
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
                {
                    "$ref": self.all_objects[('DaySchedule',
                                              week_day_schedule_name)].id
                }
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

        return ys

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