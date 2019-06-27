################################################################################
# Module: schedule.py
# Description: Functions for handling conversion of EnergyPlus schedule objects
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import functools
import io
import logging as lg
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import archetypal
from archetypal import IDF
from archetypal import log


class Schedule(object):
    """An object designed to handle any EnergyPlys schedule object"""

    def __init__(self, sch_name, idf=None, start_day_of_the_week=0,
                 strict=False, base_year=2018, schType=None, **kwargs):
        """
        Args:
            sch_name (str): The schedule name in the idf file
            idf (IDF): IDF object
            start_day_of_the_week (int): 0-based day of week (Monday=0)
            strict (bool): if True, schedules that have the Field-Sets such as
                Holidays and CustomDay will raise an error if they are absent
                from the IDF file. If False, any missing qualifiers will be
                ignored.
            base_year (int): The base year of the schedule. Defaults to 2018
                since the first day of that year is a Monday.
            schType (str): The EneryPlus schedule object from which this
            **kwargs:
        """
        super(Schedule, self).__init__(**kwargs)
        self.strict = strict
        self.idf = idf
        self.schName = sch_name
        self.startDayOfTheWeek = self.get_sdow(start_day_of_the_week)
        self.year = base_year
        self.startDate = self.start_date()
        self.count = 0
        self.startHOY = 1
        self.endHOY = 24
        self.unit = "unknown"

        self.index_ = None
        self.values = None
        self.schType = schType
        _type = kwargs.get('Type', None)
        if _type is None:
            self.schTypeLimitsName = self.get_schedule_type_limits_name(
                sch_type=self.schType)
        else:
            self.schTypeLimitsName = _type

    @classmethod
    def constant_schedule(cls, hourly_value=1, Name='AlwaysOn', **kwargs):
        """Create a schedule with a constant value for the whole year. Defaults
        to a schedule with a value of 1, named 'AlwaysOn'.

        Args:
            hourly_value (float, optional): The value for the constant schedule.
                Defaults to 1.
            Name (str, optional): The name of the schedule. Defaults to Always
                On.
            **kwargs:
        """
        idftxt = "VERSION, 8.9;"  # Not an emplty string. has just the
        # version number
        # we can make a file handle of a string
        fhandle = io.StringIO(idftxt)
        # initialize the IDF object with the file handle
        idf_scratch = archetypal.IDF(fhandle)

        idf_scratch.add_object(ep_object='Schedule:Constant'.upper(),
                               **dict(Name=Name,
                                      Schedule_Type_Limits_Name='',
                                      Hourly_Value=hourly_value),
                               save=False)

        sched = Schedule(sch_name=Name, idf=idf_scratch, **kwargs)
        return sched

    @property
    def all_values(self):
        """returns the values array"""
        if self.values is None:
            self.values = self.get_schedule_values(sch_name=self.schName,
                                                   sch_type=self.schType)
            return self.values
        else:
            return self.values

    @property
    def max(self):
        return max(self.all_values)

    @property
    def min(self):
        return min(self.all_values)

    @property
    def mean(self):
        return np.mean(self.all_values)

    @property
    def series(self):
        """Returns the schedule values as a pd.Series object with a
        DateTimeIndex
        """
        index = pd.date_range(start=self.startDate, periods=len(
            self.all_values), freq='1H')
        return pd.Series(self.all_values, index=index)

    def get_schedule_type_limits_name(self, sch_name=None, sch_type=None):
        """Return the Schedule Type Limits name associated to a schedule name

        Args:
            sch_name:
            sch_type:
        """
        if sch_name is None:
            sch_name = self.schName
        if sch_type is None:
            schedule_values = self.idf.get_schedule_data_by_name(sch_name,
                                                                 sch_type=sch_type)
        try:
            schedule_limit_name = schedule_values.Schedule_Type_Limits_Name
        except:
            return 'unknown'
        else:
            return schedule_limit_name

    def get_schedule_type_limits_data(self, sch_name=None):
        """Returns Schedule Type Limits data from schedule name

        Args:
            sch_name:
        """

        if sch_name is None:
            sch_name = self.schName

        schedule_values = self.idf.get_schedule_data_by_name(sch_name)
        try:
            schedule_limit_name = schedule_values.Schedule_Type_Limits_Name
        except:
            # this schedule is probably a 'Schedule:Week:Daily' which does
            # not have a Schedule_Type_Limits_Name field
            return '', '', '', ''
        else:
            lower_limit, upper_limit, numeric_type, unit_type = \
                self.idf.get_schedule_type_limits_data_by_name(
                    schedule_limit_name)

            self.unit = unit_type
            if self.unit == "unknown":
                self.unit = numeric_type

            return lower_limit, upper_limit, numeric_type, unit_type

    def get_schedule_type(self, sch_name=None):
        """Return the schedule type

        Args:
            sch_name:
        """
        if sch_name is None:
            sch_name = self.schName

        schedule_values = self.idf.get_schedule_data_by_name(sch_name)
        sch_type = schedule_values.fieldvalues[0]

        return sch_type

    def start_date(self):
        """The start date of the schedule. Satisfies `startDayOfTheWeek`"""
        import calendar
        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)
        start_date = c.monthdatescalendar(self.year, 1)[0][0]
        return datetime(start_date.year, start_date.month, start_date.day)

    def plot(self, slice=None, **kwargs):
        """Plot the schedule :param slice: Implements the .loc method on the
        schedule Series object.

        Args:
            slice:
            **kwargs:
        """
        hourlyvalues = self.all_values
        index = pd.date_range(self.startDate, periods=len(
            hourlyvalues),
                              freq='1H')
        series = pd.Series(hourlyvalues, index=index, dtype=float)
        if slice is None:
            slice = pd.IndexSlice[:]
        elif len(slice) > 1:
            slice = pd.IndexSlice[slice[0]:slice[1]]
        ax = series.loc[slice].plot(**kwargs, label=self.schName)
        return ax

    def get_interval_day_ep_schedule_values(self, sch_name=None):
        """Schedule:Day:Interval

        Args:
            sch_name (str): the name of the schedule
        """

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('Schedule:Day:Interval'.upper(), sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(sch_name)

        number_of_day_sch = int((len(values.fieldvalues) - 3) / 2)

        hourly_values = np.arange(24)
        start_hour = 0
        for i in range(number_of_day_sch):
            value = float(values['Value_Until_Time_{}'.format(i + 1)])
            until_time = [int(s.strip()) for s in
                          values['Time_{}'.format(i + 1)].split(":") if
                          s.strip().isdigit()]
            end_hour = int(until_time[0] + until_time[1] / 60)
            for hour in range(start_hour, end_hour):
                hourly_values[hour] = value

            start_hour = end_hour

        if numeric_type.strip().lower() == "discrete":
            hourly_values = hourly_values.astype(int)

        return hourly_values

    def get_hourly_day_ep_schedule_values(self, sch_name=None):
        """Schedule:Day:Hourly

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('Schedule:Day:Hourly'.upper(), sch_name)

        fieldvalues_ = np.array(values.fieldvalues[3:])

        return fieldvalues_

    def get_compact_weekly_ep_schedule_values(self, sch_name=None,
                                              start_date=None, index=None):
        """schedule:week:compact

        Args:
            sch_name (str): the name of the schedule
            start_date:
            index:
        """
        if start_date is None:
            start_date = self.startDate
        if index is None:
            idx = pd.date_range(start=start_date, periods=168, freq='1H')
            slicer_ = pd.Series([False] * (len(idx)), index=idx)
        else:
            slicer_ = pd.Series([False] * (len(index)), index=index)

        if sch_name is None:
            sch_name = self.schName
        values = self.idf.getobject('schedule:week:compact'.upper(), sch_name)

        weekly_schedules = pd.Series([0] * len(slicer_), index=slicer_.index)
        # update last day of schedule

        if self.count == 0:
            self.schType = values.key
            self.endHOY = 168

        num_of_daily_schedules = int(len(values.fieldvalues[2:]) / 2)

        for i in range(num_of_daily_schedules):
            day_type = values['DayType_List_{}'.format(i + 1)].lower()
            how = self.field_set(day_type, slicer_)
            if not weekly_schedules.loc[how].empty:
                # Loop through days and replace with day:schedule values
                days = []
                for name, day in weekly_schedules.loc[how].groupby(pd.Grouper(
                        freq='D')):
                    if not day.empty:
                        ref = values.get_referenced_object(
                            "ScheduleDay_Name_{}".format(i + 1))
                        day.loc[:] = self.get_schedule_values(
                            sch_name=ref.Name, sch_type=ref.key)
                        days.append(day)
                new = pd.concat(days)
                slicer_.update(
                    pd.Series([True] * len(new.index), index=new.index))
                slicer_ = slicer_.apply(lambda x: x == True)
                weekly_schedules.update(new)
            else:
                return weekly_schedules.values

        return weekly_schedules.values

    def get_daily_weekly_ep_schedule_values(self, sch_name=None):
        """schedule:week:daily

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:week:daily'.upper(), sch_name)

        # 7 list for 7 days of the week
        hourly_values = []
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                    'Friday', 'Saturday', 'Sunday']:
            ref = values.get_referenced_object(
                '{}_ScheduleDay_Name'.format(day))
            h = self.get_schedule_values(sch_name=ref.Name, sch_type=ref.key)
            hourly_values.append(h)
        hourly_values = np.array(hourly_values)
        # shift days earlier by self.startDayOfTheWeek
        hourly_values = np.roll(hourly_values, -self.startDayOfTheWeek, axis=0)

        return hourly_values.ravel()

    def get_list_day_ep_schedule_values(self, sch_name=None):
        """schedule:day:list

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:day:list'.upper(), sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(sch_name)

        import pandas as pd
        freq = int(values['Minutes_per_Item'])  # Frequency of the values
        num_values = values.fieldvalues[5:]  # List of values
        method = values['Interpolate_to_Timestep']  # How to resample

        # fill a list of available values and pad with zeros (this is safer
        # but should not occur)
        all_values = np.arange(int(24 * 60 / freq))
        for i in all_values:
            try:
                all_values[i] = num_values[i]
            except:
                all_values[i] = 0
        # create a fake index to help us with the resampling
        index = pd.date_range(start=self.startDate,
                              periods=(24 * 60) / freq,
                              freq='{}T'.format(freq))
        series = pd.Series(all_values, index=index)

        # resample series to hourly values and apply resampler function
        series = series.resample('1H').apply(_how(method))

        return series.values

    def get_constant_ep_schedule_values(self, sch_name=None):
        """schedule:constant

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:constant'.upper(), sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(sch_name)

        hourly_values = np.arange(8760)
        value = float(values['Hourly_Value'])
        for hour in hourly_values:
            hourly_values[hour] = value

        if numeric_type.strip().lower() == 'discrete':
            hourly_values = hourly_values.astype(int)

        return hourly_values

    def get_file_ep_schedule_values(self, sch_name=None):
        """schedule:file

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:file'.upper(), sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(sch_name)

        filename = values['File_Name']
        column = values['Column_Number']
        rows = values['Rows_to_Skip_at_Top']
        hours = values['Number_of_Hours_of_Data']
        sep = values['Column_Separator']
        interp = values['Interpolate_to_Timestep']

        import pandas as pd
        import os
        idfdir = os.path.dirname(self.idf.idfname)
        file = os.path.join(idfdir, filename)
        delimeter = _separator(sep)
        skip_rows = int(rows) - 1  # We want to keep the column
        col = [int(column) - 1]  # zero-based
        values = pd.read_csv(file, delimiter=delimeter, skiprows=skip_rows,
                             usecols=col)

        return values.iloc[:, 0].values

    def get_compact_ep_schedule_values(self, sch_name=None):
        """schedule:compact

        Args:
            sch_name (str): the name of the schedule
        """

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:compact'.upper(), sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(sch_name)

        field_sets = ['through', 'for', 'interpolate', 'until', 'value']
        fields = values.fieldvalues[3:]

        index = pd.date_range(start=self.startDate, periods=8760, freq='H')
        zeros = np.zeros(len(index))

        slicer_ = pd.Series([False] * len(index), index=index)
        series = pd.Series(zeros, index=index)

        from_day = self.startDate
        ep_from_day = datetime(self.year, 1, 1)
        from_time = '00:00'
        how_interpolate = None
        for field in fields:
            if any([spe in field.lower() for spe in field_sets]):
                f_set, hour, minute, value = self._field_interpreter(field)

                if f_set.lower() == 'through':
                    # main condition. All sub-conditions must obey a
                    # `Through` condition

                    # First, initialize the slice (all False for now)
                    through_conditions = self.invalidate_condition(series)

                    # reset from_time
                    from_time = '00:00'

                    # Prepare ep_to_day variable
                    ep_to_day = self._date_field_interpretation(value) + \
                                timedelta(days=1)

                    # Calculate Timedelta in days
                    days = (ep_to_day - ep_from_day).days
                    # Add timedelta to start_date
                    to_day = from_day + timedelta(days=days) + timedelta(
                        hours=-1)

                    # slice the conditions with the range and apply True
                    through_conditions.loc[from_day:to_day] = True

                    from_day = to_day + timedelta(hours=1)
                    ep_from_day = ep_to_day
                elif f_set.lower() == 'for':
                    # slice specific days
                    # reset from_time
                    from_time = '00:00'

                    for_condition = self.invalidate_condition(series)
                    values = value.split()
                    if len(values) > 1:
                        # if multiple `For`. eg.: For: Weekends Holidays,
                        # Combine both conditions
                        for value in values:
                            if value.lower() == 'allotherdays':
                                # Apply condition to slice
                                how = self.field_set(value, slicer_)
                                # Reset through condition
                                through_conditions = how
                                for_condition = how
                            else:
                                how = self.field_set(value, slicer_)
                                if not how is None:
                                    for_condition.loc[how] = True
                    elif value.lower() == 'allotherdays':
                        # Apply condition to slice
                        how = self.field_set(value, slicer_)
                        # Reset through condition
                        through_conditions = how
                        for_condition = how
                    else:
                        # Apply condition to slice
                        how = self.field_set(value, slicer_)
                        for_condition.loc[how] = True

                    # Combine the for_condition with all_conditions
                    all_conditions = through_conditions & for_condition

                    # update in memory slice
                    # self.sliced_day_.loc[all_conditions] = True
                elif 'interpolate' in f_set.lower():
                    # we need to upsample to series to 8760 * 60 values
                    new_idx = pd.date_range(start=self.startDate,
                                            periods=525600, closed='left',
                                            freq='T')
                    series = series.resample('T').pad()
                    series = series.reindex(new_idx)
                    series.fillna(method='pad', inplace=True)
                    through_conditions = through_conditions.resample('T').pad()
                    through_conditions = through_conditions.reindex(new_idx)
                    through_conditions.fillna(method='pad', inplace=True)
                    for_condition = for_condition.resample('T').pad()
                    for_condition = for_condition.reindex(new_idx)
                    for_condition.fillna(method='pad', inplace=True)
                    how_interpolate = value.lower()
                elif f_set.lower() == 'until':
                    until_condition = self.invalidate_condition(series)
                    if series.index.freq.name == 'T':
                        # until_time = str(int(hour) - 1) + ':' + minute
                        until_time = timedelta(hours=int(hour),
                                               minutes=int(minute)) - timedelta(
                            minutes=1)

                    else:
                        until_time = str(int(hour) - 1) + ':' + minute
                    until_condition.loc[until_condition.between_time(from_time,
                                                                     str(
                                                                         until_time)).index] = True
                    all_conditions = for_condition & through_conditions & \
                                     until_condition

                    from_time = str(int(hour)) + ':' + minute
                elif f_set.lower() == 'value':
                    # If the therm `Value: ` field is used, we will catch it
                    # here.
                    # update in memory slice
                    slicer_.loc[all_conditions] = True
                    series[all_conditions] = value
                else:
                    # Do something here before looping to the next Field
                    pass
            else:
                # If the term `Value: ` is not used; the variable is simply
                # passed in the Field
                value = float(field)
                series[all_conditions] = value

                # update in memory slice
                slicer_.loc[all_conditions] = True
        if how_interpolate:
            return series.resample('H').mean().values
        else:
            return series.values

    def _field_interpreter(self, field):
        """dealing with a Field-Set (Through, For, Interpolate, # Until, Value)
        and return the parsed string

        Args:
            field:
        """

        values_sets = ['weekdays', 'weekends', 'alldays', 'allotherdays',
                       'sunday', 'monday', 'tuesday', 'wednesday',
                       'thursday', 'friday', 'saturday', 'summerdesignday',
                       'winterdesignday', 'holiday']
        keywords = None

        if 'through' in field.lower():
            # deal with through
            if ':' in field.lower():
                # parse colon
                f_set, statement = field.split(':')
                hour = None
                minute = None
                value = statement.strip()
            else:
                msg = 'The schedule "{sch}" contains a Field ' \
                      'that is not understood: "{field}"'.format(
                    sch=self.schName, field=field)
                raise NotImplementedError(msg)
        elif 'for' in field.lower():
            keywords = [word for word in values_sets if word in field.lower()]
            if ':' in field.lower():
                # parse colon
                f_set, statement = field.split(':')
                value = statement.strip()
                hour = None
                minute = None
            elif keywords:
                # get epBunch of the sizing period
                statement = " ".join(keywords)
                f_set = [s for s in field.split() if "for" in
                         s.lower()][0]
                value = statement.strip()
                hour = None
                minute = None
            else:
                # parse without a colon
                msg = 'The schedule "{sch}" contains a Field ' \
                      'that is not understood: "{field}"'.format(
                    sch=self.schName, field=field)
                raise NotImplementedError(msg)
        elif 'interpolate' in field.lower():
            msg = 'The schedule "{sch}" contains sub-hourly values (' \
                  'Field-Set="{field}"). The average over the hour is ' \
                  'taken'.format(sch=self.schName, field=field)
            log(msg, lg.WARNING)
            f_set, value = field.split(':')
            hour = None
            minute = None
        elif 'until' in field.lower():
            if ':' in field.lower():
                # parse colon
                try:
                    f_set, hour, minute = field.split(':')
                    hour = hour.strip()  # remove trailing spaces
                    minute = minute.strip()  # remove trailing spaces
                    value = None
                except:
                    f_set = 'until'
                    hour, minute = field.split(':')
                    hour = hour[-2:].strip()
                    minute = minute.strip()
                    value = None
            else:
                msg = 'The schedule "{sch}" contains a Field ' \
                      'that is not understood: "{field}"'.format(
                    sch=self.schName, field=field)
                raise NotImplementedError(msg)
        elif 'value' in field.lower():
            if ':' in field.lower():
                # parse colon
                f_set, statement = field.split(':')
                value = statement.strip()
                hour = None
                minute = None
            else:
                msg = 'The schedule "{sch}" contains a Field ' \
                      'that is not understood: "{field}"'.format(
                    sch=self.schName, field=field)
                raise NotImplementedError(msg)
        else:
            # deal with the data value
            f_set = field
            hour = None
            minute = None
            value = field[len(field) + 1:].strip()

        return f_set, hour, minute, value

    @staticmethod
    def invalidate_condition(series):
        """
        Args:
            series:
        """
        index = series.index
        periods = len(series)
        return pd.Series([False] * periods, index=index)

    def get_yearly_ep_schedule_values(self, sch_name=None):
        """schedule:year

        Args:
            sch_name (str): the name of the schedule
        """
        # first week

        start_date = self.startDate
        idx = pd.date_range(start=start_date, periods=8760, freq='1H')
        hourly_values = pd.Series([0] * 8760, index=idx)

        # update last day of schedule
        self.endHOY = 8760

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.getobject('schedule:year'.upper(), sch_name)

        # generate weekly schedules
        num_of_weekly_schedules = int(len(values.fieldvalues[3:]) / 5)

        for i in range(num_of_weekly_schedules):
            ref = values.get_referenced_object(
                'ScheduleWeek_Name_{}'.format(i + 1))

            start_month = values['Start_Month_{}'.format(i + 1)]
            end_month = values['End_Month_{}'.format(i + 1)]
            start_day = values['Start_Day_{}'.format(i + 1)]
            end_day = values['End_Day_{}'.format(i + 1)]

            start = datetime.strptime(
                '{}/{}/{}'.format(self.year, start_month, start_day),
                '%Y/%m/%d')
            end = datetime.strptime(
                '{}/{}/{}'.format(self.year, end_month, end_day),
                '%Y/%m/%d')
            days = (end - start).days + 1

            end_date = start_date + timedelta(days=days) + timedelta(hours=23)
            how = pd.IndexSlice[start_date:end_date]

            weeks = []
            for name, week in hourly_values.loc[how].groupby(
                    pd.Grouper(freq='168H')):
                if not week.empty:
                    try:
                        week.loc[:] = self.get_schedule_values(
                            sch_name=ref.Name, start_date=week.index[0],
                            index=week.index, sch_type=ref.key)
                    except ValueError:
                        week.loc[:] = self.get_schedule_values(
                            ref.Name, week.index[0])[0:len(week)]
                    finally:
                        weeks.append(week)
            new = pd.concat(weeks)
            hourly_values.update(new)
            start_date += timedelta(days=days)

        return hourly_values.values

    def get_schedule_values(self, sch_name=None, start_date=None, index=None,
                            sch_type=None):
        """Main function that returns the schedule values

        Args:
            sch_name (str): the name of the schedule
            start_date:
            index:
            sch_type:
        """

        if sch_name is None:
            sch_name = self.schName

        if sch_type is None:
            schedule_values = self.idf.get_schedule_data_by_name(sch_name)
            self.schType = schedule_values.key.upper()
            sch_type = self.schType
        if self.count == 0:
            # This is the first time, get the schedule type and the type limits.
            self.schTypeLimitsName = self.get_schedule_type_limits_name()
        self.count += 1

        if sch_type.upper() == "schedule:year".upper():
            hourly_values = self.get_yearly_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:day:interval".upper():
            hourly_values = self.get_interval_day_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:day:hourly".upper():
            hourly_values = self.get_hourly_day_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:day:list".upper():
            hourly_values = self.get_list_day_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:week:compact".upper():
            hourly_values = self.get_compact_weekly_ep_schedule_values(
                sch_name, start_date, index)
        elif sch_type.upper() == "schedule:week:daily".upper():
            hourly_values = self.get_daily_weekly_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:constant".upper():
            hourly_values = self.get_constant_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:compact".upper():
            hourly_values = self.get_compact_ep_schedule_values(
                sch_name)
        elif sch_type.upper() == "schedule:file".upper():
            hourly_values = self.get_file_ep_schedule_values(
                sch_name)
        else:
            log('Archetypal does not support "{}" currently'.format(
                self.schType), lg.WARNING)

            hourly_values = []

        return hourly_values

    def is_schedule(self, sch_name):
        """Returns True if idfobject is one of 'schedule_types'

        Args:
            sch_name (str): the name of the schedule
        """
        if sch_name.upper() in self.idf.schedules_dict:
            return True
        else:
            return False

    def to_year_week_day(self):
        """convert a Schedule Class to the 'Schedule:Year',
        'Schedule:Week:Daily' and 'Schedule:Day:Hourly' representation

        Returns:
            3-element tuple containing

            - **yearly** (*Schedule*): The yearly schedule object
            - **weekly** (*list of Schedule*): The list of weekly schedule
              objects
            - **daily** (*list of Schedule*):The list of daily schedule objects
        """

        full_year = np.array(self.all_values)  # array of shape (8760,)
        values = full_year.reshape(-1, 24)  # shape (365, 24)

        # create unique days
        unique_days, nds = np.unique(values, axis=0, return_inverse=True)

        ep_days = []
        dict_day = {}
        count_day = 0
        for unique_day in unique_days:
            name = 'd_' + self.schName + '_' + '%03d' % count_day
            name, count_day = archetypal.check_unique_name('d', count_day,
                                                           name,
                                                           archetypal.settings.unique_schedules,
                                                           suffix=True)
            dict_day[name] = unique_day

            archetypal.settings.unique_schedules.append(name)

            # Create idf_objects for schedule:day:hourly
            ep_day = self.idf.add_object(
                ep_object='Schedule:Day:Hourly'.upper(),
                save=False,
                **dict(Name=name,
                       Schedule_Type_Limits_Name=self.schType,
                       **{'Hour_{}'.format(i + 1): unique_day[i]
                          for i in range(24)})
            )
            ep_days.append(ep_day)

        # create unique weeks from unique days
        unique_weeks, nwsi, nws, count = np.unique(
            full_year[:364 * 24, ...].reshape(-1, 168), return_index=True,
            axis=0, return_inverse=True, return_counts=True)

        # Appending unique weeks in dictionary with name and values of weeks as
        # keys
        # {'name_week': {'dayName':[]}}
        dict_week = {}
        count_week = 0
        for unique_week in unique_weeks:
            week_id = 'w_' + self.schName + '_' + '%03d' % count_week
            week_id, count_week = archetypal.check_unique_name('w',
                                                               count_week,
                                                               week_id,
                                                               archetypal.settings.unique_schedules,
                                                               suffix=True)
            archetypal.settings.unique_schedules.append(week_id)

            dict_week[week_id] = {}
            for i in list(range(0, 7)):
                day_of_week = unique_week[..., i * 24:(i + 1) * 24]
                for key in dict_day:
                    if (day_of_week == dict_day[key]).all():
                        dict_week[week_id]['day_{}'.format(i)] = key

        # Create idf_objects for schedule:week:daily
        list_day_of_week = ['Sunday', 'Monday', 'Tuesday',
                            'Wednesday', 'Thursday', 'Friday', 'Saturday']
        ordered_day_n = np.array([6, 0, 1, 2, 3, 4, 5])
        ordered_day_n = np.roll(ordered_day_n, self.startDayOfTheWeek)
        ep_weeks = []
        for week_id in dict_week:
            ep_week = self.idf.add_object(
                ep_object='Schedule:Week:Daily'.upper(),
                save=False,
                **dict(Name=week_id,
                       **{'{}_ScheduleDay_Name'.format(
                           weekday): dict_week[week_id][
                           'day_{}'.format(i)] for
                          i, weekday in
                          zip(ordered_day_n, list_day_of_week)
                          },
                       Holiday_ScheduleDay_Name=
                       dict_week[week_id]['day_6'],
                       SummerDesignDay_ScheduleDay_Name=
                       dict_week[week_id]['day_1'],
                       WinterDesignDay_ScheduleDay_Name=
                       dict_week[week_id]['day_1'],
                       CustomDay1_ScheduleDay_Name=
                       dict_week[week_id]['day_2'],
                       CustomDay2_ScheduleDay_Name=
                       dict_week[week_id]['day_5'])
            )
            ep_weeks.append(ep_week)

        import itertools
        blocks = {}
        from_date = datetime(self.year, 1, 1)
        bincount = [sum(1 for _ in group)
                    for key, group in itertools.groupby(nws + 1) if key]
        week_order = {i: v for i, v in enumerate(np.array(
            [key for key, group in itertools.groupby(nws + 1) if key]) - 1)}
        for i, (week_n, count) in enumerate(
                zip(week_order, bincount)):
            week_id = list(dict_week)[week_order[i]]
            to_date = from_date + timedelta(days=int(count * 7), hours=-1)
            blocks[i] = {}
            blocks[i]['week_id'] = week_id
            blocks[i]['from_day'] = from_date.day
            blocks[i]['end_day'] = to_date.day
            blocks[i]['from_month'] = from_date.month
            blocks[i]['end_month'] = to_date.month
            from_date = to_date + timedelta(hours=1)

            # If this is the last block, force end of year
            if i == len(bincount) - 1:
                blocks[i]['end_day'] = 31
                blocks[i]['end_month'] = 12

        new_dict = dict(Name=self.schName + '_',
                        Schedule_Type_Limits_Name=self.schTypeLimitsName)
        for i in blocks:
            new_dict.update({"ScheduleWeek_Name_{}".format(i + 1):
                                 blocks[i]['week_id'],
                             "Start_Month_{}".format(i + 1):
                                 blocks[i]['from_month'],
                             "Start_Day_{}".format(i + 1):
                                 blocks[i]['from_day'],
                             "End_Month_{}".format(i + 1):
                                 blocks[i]['end_month'],
                             "End_Day_{}".format(i + 1):
                                 blocks[i]['end_day']})

        ep_year = self.idf.add_object(ep_object='Schedule:Year'.upper(),
                                      save=False, **new_dict)
        return ep_year, ep_weeks, ep_days

    def _date_field_interpretation(self, field):
        """Date Field Interpretation

        Info:
            See EnergyPlus documentation for more details: 1.6.8.1.2 Field:
            Start Date (Table 1.4: Date Field Interpretation)

        Args:
            field (str): The EnergyPlus Field Contents

        Returns:
            (datetime): The datetime object
        """
        # < number > Weekday in Month
        formats = ['%m/%d', '%d %B', '%B %d', '%d %b', '%b %d']
        date = None
        for format_str in formats:
            # Tru to parse using each defined formats
            try:
                date = datetime.strptime(field, format_str)
            except:
                pass
            else:
                date = datetime(self.year, date.month, date.day)
        if date is None:
            # if the defined formats did not work, try the fancy parse
            try:
                date = self._parse_fancy_string(field)
            except:
                msg = "the schedule '{sch}' contains a " \
                      "Field that is not understood: '{field}'".format(
                    sch=self.schName,
                    field=field)
                raise ValueError(msg)
            else:
                return date
        else:
            return date

    def _parse_fancy_string(self, field):
        """Will try to parse cases such as `3rd Monday in February` or `Last
        Weekday In Month`

        Args:
            field (str): The EnergyPlus Field Contents

        Returns:
            (datetime): The datetime object
        """
        import re

        # split the string at the term ' in '
        time, month = field.lower().split(' in ')
        month = datetime.strptime(month, '%B').month

        # split the first part into nth and dayofweek
        nth, dayofweek = time.split(' ')
        if 'last' in nth:
            nth = -1  # Use the last one
        else:
            nth = re.findall(r'\d+', nth)  # use the nth one
            nth = int(nth[0]) - 1  # python is zero-based

        weekday = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                   'friday': 4, 'saturday': 5, 'sunday': 6}

        # parse the dayofweek eg. monday
        dayofweek = weekday.get(dayofweek, 6)

        # create list of possible days using Calendar
        import calendar
        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)
        monthcal = c.monthdatescalendar(self.year, month)

        # iterate though the month and get the nth weekday
        date = [day for week in monthcal for day in week if \
                day.weekday() == dayofweek and \
                day.month == month][nth]
        return datetime(date.year, date.month, date.day)

    def field_set(self, field, slicer_=None):
        """helper function to return the proper slicer depending on the
        field_set value.

        Available values are: Weekdays, Weekends, Holidays, Alldays,
        SummerDesignDay, WinterDesignDay, Sunday, Monday, Tuesday, Wednesday,
        Thursday, Friday, Saturday, CustomDay1, CustomDay2, AllOtherDays

        Args:
            field (str): The EnergyPlus field set value.
            slicer_:

        Returns:
            (indexer-like): Returns the appropriate indexer for the series.
        """

        if field.lower() == 'weekdays':
            # return only days of weeks
            return lambda x: x.index.dayofweek < 5
        elif field.lower() == 'weekends':
            # return only weekends
            return lambda x: x.index.dayofweek >= 5
        elif field.lower() == 'alldays':
            log('For schedule "{}", the field-set "AllDays" may be overridden '
                'by the "AllOtherDays" field-set'.format(
                self.schName), lg.WARNING)
            # return all days := equivalenet to .loc[:]
            return pd.IndexSlice[:]
        elif field.lower() == 'allotherdays':
            # return unused days (including special days). Uses the global
            # variable `slicer_`
            import operator
            if slicer_ is not None:
                return _conjunction(*[self.special_day(field, slicer_),
                                      ~slicer_], logical=operator.or_)
            else:
                raise NotImplementedError
        elif field.lower() == 'sunday':
            # return only sundays
            return lambda x: x.index.dayofweek == 6
        elif field.lower() == 'monday':
            # return only mondays
            return lambda x: x.index.dayofweek == 0
        elif field.lower() == 'tuesday':
            # return only Tuesdays
            return lambda x: x.index.dayofweek == 1
        elif field.lower() == 'wednesday':
            # return only Wednesdays
            return lambda x: x.index.dayofweek == 2
        elif field.lower() == 'thursday':
            # return only Thursdays
            return lambda x: x.index.dayofweek == 3
        elif field.lower() == 'friday':
            # return only Fridays
            return lambda x: x.index.dayofweek == 4
        elif field.lower() == 'saturday':
            # return only Saturdays
            return lambda x: x.index.dayofweek == 5
        elif field.lower() == 'summerdesignday':
            # return design_day(self, field)
            return None
        elif field.lower() == 'winterdesignday':
            # return design_day(self, field)
            return None
        elif field.lower() == 'holiday' or field.lower() == 'holidays':
            field = 'holiday'
            return self.special_day(field, slicer_)
        elif not self.strict:
            # If not strict, ignore missing field-sets such as CustomDay1
            return pd.IndexSlice[:]
        else:
            raise NotImplementedError(
                'Archetypal does not yet support The '
                'Field_set "{}"'.format(field))

    def __len__(self):
        """returns the length of all values of the schedule"""
        return len(self.all_values)

    def __eq__(self, other):
        """Overrides the default implementation

        Args:
            other:
        """
        if isinstance(other, Schedule):
            return self.all_values == other.all_values
        else:
            raise NotImplementedError

    def __ne__(self, other):
        return ~(self.__eq__(other))

    def __add__(self, other):
        if isinstance(other, Schedule):
            return self.all_values + other.all_values
        elif isinstance(other, list):
            return self.all_values + other
        else:
            raise NotImplementedError

    def __sub__(self, other):
        if isinstance(other, Schedule):
            return self.all_values - other.all_values
        elif isinstance(other, list):
            return self.all_values - other
        else:
            raise NotImplementedError

    def __mul__(self, other):
        if isinstance(other, Schedule):
            return self.all_values * other.all_values
        elif isinstance(other, list):
            return self.all_values * other
        else:
            raise NotImplementedError

    def get_sdow(self, start_day_of_week):
        """Returns the start day of the week

        Args:
            start_day_of_week:
        """
        if start_day_of_week is None:
            return self.idf.day_of_week_for_start_day
        else:
            return start_day_of_week

    def special_day(self, field, slicer_):
        """try to get the RunPeriodControl:SpecialDays for the corresponding Day
        Type

        Args:
            field:
            slicer_:
        """
        sp_slicer_ = slicer_.copy()
        sp_slicer_.loc[:] = False
        special_day_types = ['holiday', 'customday1', 'customday2']

        dds = self.idf.idfobjects['RunPeriodControl:SpecialDays'.upper()]
        dd = [dd for dd in dds if dd.Special_Day_Type.lower() == field
              or dd.Special_Day_Type.lower() in special_day_types]
        if len(dd) > 0:
            slice = []
            for dd in dd:
                # can have more than one special day types
                data = dd.Start_Date
                ep_start_date = self._date_field_interpretation(data)
                ep_orig = datetime(self.year, 1, 1)
                days_to_speciald = (ep_start_date - ep_orig).days
                duration = int(dd.Duration)
                from_date = self.startDate + timedelta(days=days_to_speciald)
                to_date = from_date + timedelta(days=duration) + timedelta(
                    hours=-1)

                sp_slicer_.loc[from_date:to_date] = True
            return sp_slicer_
        elif not self.strict:
            return sp_slicer_
        else:
            msg = 'Could not find a "SizingPeriod:DesignDay" object ' \
                  'needed for schedule "{}" with Day Type "{}"'.format(
                self.schName, field.capitalize()
            )
            raise ValueError(msg)

    def design_day(self, field, slicer_):
        # try to get the SizingPeriod:DesignDay for the corresponding Day Type
        """
        Args:
            field:
            slicer_:
        """
        sp_slicer_ = slicer_.copy()
        sp_slicer_.loc[:] = False
        dds = self.idf.idfobjects['SizingPeriod:DesignDay'.upper()]
        dd = [dd for dd in dds if dd.Day_Type.lower() == field]
        if len(dd) > 0:
            for dd in dd:
                # should have found only one design day matching the Day Type
                month = dd.Month
                day = dd.Day_of_Month
                data = str(month) + "/" + str(day)
                ep_start_date = self._date_field_interpretation(data)
                ep_orig = datetime(self.year, 1, 1)
                days_to_speciald = (ep_start_date - ep_orig).days
                duration = 1  # Duration of 1 day
                from_date = self.startDate + timedelta(days=days_to_speciald)
                to_date = from_date + timedelta(days=duration) + timedelta(
                    hours=-1)

                sp_slicer_.loc[from_date:to_date] = True
            return sp_slicer_
        elif not self.strict:
            return sp_slicer_
        else:
            msg = 'Could not find a "SizingPeriod:DesignDay" object ' \
                  'needed for schedule "{}" with Day Type "{}"'.format(
                self.schName, field.capitalize()
            )
            raise ValueError(msg)

            data = [dd[0].Month, dd[0].Day_of_Month]
            date = '/'.join([str(item).zfill(2) for item in data])
            date = self._date_field_interpretation(date)
            return lambda x: x.index == date


def _conjunction(*conditions, logical=np.logical_and):
    """Applies a logical function on n conditions

    Args:
        *conditions:
        logical:
    """
    return functools.reduce(logical, conditions)


def _separator(sep):
    """helper function to return the correct delimiter

    Args:
        sep:
    """
    if sep == 'Comma':
        return ','
    elif sep == 'Tab':
        return '\t'
    elif sep == 'Fixed':
        return None
    elif sep == 'Semicolon':
        return ';'
    else:
        return ','


def _how(how):
    """Helper function to return the correct resampler

    Args:
        how:
    """
    if how.lower() == 'average':
        return 'mean'
    elif how.lower() == 'linear':
        return 'interpolate'
    elif how.lower() == 'no':
        return 'max'
    else:
        return 'max'
