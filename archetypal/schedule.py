import functools
import logging as lg
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from archetypal import log


class Schedule(object):
    """An object designed to handle any EnergyPlys schedule object"""

    def __init__(self, idf, sch_name, start_day_of_the_week=None,
                 base_year=2018):
        """

        Args:
            idf (IDF): IDF object
            sch_name (str): The schedule name in the idf file
            start_day_of_the_week (int): 0-based day of week (Monday=0)
            base_year (int): The base year of the schedule. Defaults to 2018
                since the first day of that year is a Monday.
        """
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

    @property
    def all_values(self):
        """returns the values array"""
        if self.values is None:
            self.values = self.get_schedule_values(self.schName)
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
        DateTimeIndex"""
        index = pd.date_range(start=self.startDate, periods=len(
            self.all_values), freq='1H')
        return pd.Series(self.all_values, index=index)

    def get_schedule_type_limits_data(self, sch_name):
        """Returns Schedule Type Limits data"""

        if sch_name is None:
            sch_name = self.schName

        schedule = self.idf.get_schedule_type_limits_data_by_name(sch_name)
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.schedule_type_limits(schedule)

        self.unit = unit_type
        if self.unit == "unknown":
            self.unit = numeric_type

        return lower_limit, upper_limit, numeric_type, unit_type

    @staticmethod
    def schedule_type_limits(schedule):
        """Returns ScheduleTypeValues of the epbunch"""
        if schedule is not None:
            lower_limit = schedule['Lower_Limit_Value']
            upper_limit = schedule['Upper_Limit_Value']
            numeric_type = schedule['Numeric_Type']
            unit_type = schedule['Unit_Type']

            return lower_limit, upper_limit, numeric_type, unit_type
        else:
            return '', '', '', ''

    def start_date(self):
        """The start date of the schedule. Satisfies `startDayOfTheWeek`"""
        import calendar
        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)
        start_date = c.monthdatescalendar(self.year, 1)[0][0]
        return datetime(start_date.year, start_date.month, start_date.day)

    def plot(self, slice=None, **kwargs):
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
        """'Schedule:Day:Interval"""

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)
        type_limit_name = values.Schedule_Type_Limits_Name
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(type_limit_name)

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
        """'Schedule:Day:Hourly'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

        fieldvalues_ = values.fieldvalues[3:]

        return np.array(fieldvalues_)

    def get_compact_weekly_ep_schedule_values(self, sch_name=None):
        """'schedule:week:compact'"""
        idx = pd.date_range(start=self.startDate, periods=168, freq='1H')
        slicer_ = pd.Series([False] * (len(idx)), index=idx)

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

        weekly_schedules = slicer_.apply(lambda x: 0)
        # update last day of schedule
        self.endHOY = 168

        num_of_daily_schedules = int(len(values.fieldvalues[2:]) / 2)

        for i in range(num_of_daily_schedules):
            day_type = values['DayType_List_{}'.format(i + 1)].lower()
            how = self.field_set(day_type, slicer_)

            # Loop through days and replace with day:schedule values
            days = []
            for name, day in weekly_schedules.loc[how].groupby(pd.Grouper(
                    freq='D')):
                if not day.empty:
                    day.loc[:] = self.get_schedule_values(
                        values["ScheduleDay_Name_{}".format(i + 1)])
                    days.append(day)
            new = pd.concat(days)
            slicer_.update(pd.Series([True] * len(new.index), index=new.index))
            slicer_ = slicer_.apply(lambda x: x == True)
            weekly_schedules.update(new)

        return weekly_schedules.values

    def get_daily_weekly_ep_schedule_values(self, sch_name=None):
        """'schedule:week:daily'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

        # 7 list for 7 days of the week
        hourly_values = []
        sundaySch = self.get_schedule_values(
            values['Sunday_ScheduleDay_Name'])
        mondaySch = self.get_schedule_values(
            values['Monday_ScheduleDay_Name'])
        tuesdaySch = self.get_schedule_values(
            values['Tuesday_ScheduleDay_Name'])
        wednesdaySch = self.get_schedule_values(
            values['Wednesday_ScheduleDay_Name'])
        thursdaySch = self.get_schedule_values(
            values['Thursday_ScheduleDay_Name'])
        fridaySch = self.get_schedule_values(
            values['Friday_ScheduleDay_Name'])
        saturdaySch = self.get_schedule_values(
            values['Saturday_ScheduleDay_Name'])

        # Not sure what to do with these...
        holidaySch = self.get_schedule_values(
            values['Holiday_ScheduleDay_Name'])
        summerDesignDay = self.get_schedule_values(
            values['SummerDesignDay_ScheduleDay_Name'])
        winterDesignDay = self.get_schedule_values(
            values['WinterDesignDay_ScheduleDay_Name'])
        customDay1Sch = self.get_schedule_values(
            values['CustomDay1_ScheduleDay_Name'])
        customDay2Sch = self.get_schedule_values(
            values['CustomDay2_ScheduleDay_Name'])

        hourly_values = np.array([mondaySch, tuesdaySch,
                                  wednesdaySch, thursdaySch, fridaySch,
                                  saturdaySch, sundaySch])

        # shift days earlier by self.startDayOfTheWeek
        hourly_values = np.roll(hourly_values, -self.startDayOfTheWeek, axis=0)

        return hourly_values.ravel()

    def get_list_day_ep_schedule_values(self, sch_name=None):
        """'schedule:day:list'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

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
        series = series.resample('1H').apply(how(method))

        return series.values

    def get_constant_ep_schedule_values(self, sch_name=None):
        """'schedule:constant'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

        type_limit_name = values.Schedule_Type_Limits_Name
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(type_limit_name)
        hourly_values = np.arange(8760)
        value = float(values['Hourly_Value'])
        for hour in hourly_values:
            hourly_values[hour] = value

        if numeric_type.strip().lower() == 'discrete':
            hourly_values = hourly_values.astype(int)

        return hourly_values

    def get_file_ep_schedule_values(self, sch_name=None):
        """'schedule:file'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)
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
        delimeter = separator(sep)
        skip_rows = int(rows) - 1  # We want to keep the column
        col = [int(column)]
        values = pd.read_csv(file, delimiter=delimeter, skiprows=skip_rows,
                             usecols=col)

        return values.iloc[:, 0].values

    def get_compact_ep_schedule_values(self, sch_name=None):
        """'schedule:compact'"""

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)
        field_sets = ['through', 'for', 'interpolate', 'until', 'value']
        fields = values.fieldvalues[3:]

        index = pd.date_range(start=self.startDate, periods=8760, freq='1H')
        zeros = np.zeros(8760)

        slicer_ = pd.Series([False] * 8760, index=index)
        series = pd.Series(zeros, index=index)

        from_day = self.startDate
        ep_from_day = datetime(self.year, 1, 1)
        from_time = '00:00'
        for field in fields:
            if any([spe in field.lower() for spe in field_sets]):
                # we are dealing with a Field-Set (Through, For, Interpolate,
                # Until, Value)
                try:
                    # the colon (:) after these elements (Through, For,
                    # Until) is optional. We can catch this behaviour with a
                    # try, except statement
                    f_set, value = field.split(':')
                    value = value.strip()  # remove trailing spaces
                except:
                    # The field does not have a colon or has more than one
                    # but a maximum of two!
                    try:
                        # The field has more than one colon
                        f_set, hour, minute = field.split(':')
                        hour = hour.strip()  # remove trailing spaces
                        minute = minute.strip()
                    except:
                        # The field does not have a colon. Simply capitalize
                        # and use value
                        try:
                            f_set = field.capitalize()
                            value = field[len(field) + 1:].strip()
                        except:
                            msg = 'The schedule "{sch}" contains a Field ' \
                                  'that is not understood: "{field}"'.format(
                                sch=self.schName,
                                field=field)
                            raise ValueError(msg)

                if f_set.lower() == 'through':
                    # main condition. All sub-conditions must obey a
                    # `Through` condition

                    # First, initialize the slice (all False for now)
                    # Todo: replace lambda with something quicker
                    through_conditions = series.apply(lambda x: False)

                    # reset from_time
                    from_time = '00:00'

                    # Prepare ep_to_day variable
                    ep_to_day = self.date_field_interpretation(value)

                    # Calculate Timedelta in days
                    days = (ep_to_day - ep_from_day).days
                    # Add timedelta to start_date
                    to_day = from_day + timedelta(days=days) \
                             + timedelta(hours=23)

                    # slice the conditions with the range and apply True
                    through_conditions.loc[from_day:to_day] = True

                    from_day = to_day + timedelta(hours=-23)
                    ep_from_day = ep_to_day
                elif f_set.lower() == 'for':
                    # slice specific days
                    # reset from_time
                    from_time = '00:00'

                    # Todo: replace lambda with something quicker
                    for_condition = series.apply(lambda x: False)
                    values = value.split()
                    if len(values) > 1:
                        # if multiple `For`. eg.: For: Weekends Holidays,
                        # Combine both conditions
                        for value in values:
                            if value.lower() == 'allotherdays':
                                # Apply condition to slice
                                how = self.field_set(value, slicer_)
                                # Reset though condition
                                through_conditions = how
                                for_condition = how
                            else:
                                how = self.field_set(value, slicer_)
                                for_condition.loc[how] = True
                    elif value.lower() == 'allotherdays':
                        # Apply condition to slice
                        how = self.field_set(value, slicer_)
                        # Reset though condition
                        through_conditions = how
                        for_condition = how
                    else:
                        # Apply condition to slice
                        how = self.field_set(value)
                        for_condition.loc[how] = True

                    # Combine the for_condition with all_conditions
                    all_conditions = through_conditions & for_condition

                    # update in memory slice
                    # self.sliced_day_.loc[all_conditions] = True
                elif f_set.lower() == 'interpolate':
                    raise NotImplementedError('Archetypal does not support '
                                              '"interpolate" statements yet')
                elif f_set.lower() == 'until':
                    # Todo: replace lambda with something quicker
                    until_condition = series.apply(lambda x: False)
                    until_time = str(int(hour) - 1) + ':' + minute
                    until_condition.loc[until_condition.between_time(from_time,
                                                                     until_time).index] = True
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

        return series.values

    def get_yearly_ep_schedule_values(self, sch_name=None):
        """'schedule:year'"""
        # first week

        start_date = self.startDate
        idx = pd.date_range(start=start_date, periods=8760, freq='1H')
        hourly_values = pd.Series([0] * 8760, index=idx)

        # update last day of schedule
        self.endHOY = 8760

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name)

        # generate weekly schedules
        num_of_weekly_schedules = int(len(values.fieldvalues[3:]) / 5)

        for i in range(num_of_weekly_schedules):
            week_day_schedule_name = values[
                'ScheduleWeek_Name_{}'.format(i + 1)]

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
                            week_day_schedule_name)
                    except ValueError:
                        week.loc[:] = self.get_schedule_values(
                            week_day_schedule_name)[0:len(week)]
                    finally:
                        weeks.append(week)
            new = pd.concat(weeks)
            hourly_values.update(new)
            start_date += timedelta(days=days)

        return hourly_values.values

    def get_schedule_values(self, sch_name=None):
        """Main function that returns the schedule values"""

        if sch_name is None:
            sch_name = self.schName

        schedule_values = self.idf.get_schedule_data_by_name(sch_name)

        schedule_type = schedule_values.fieldvalues[0].upper()
        if self.count == 0:
            self.schType = schedule_type

        self.count += 1

        if schedule_type == "schedule:year".upper():
            hourly_values = self.get_yearly_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:day:interval".upper():
            hourly_values = self.get_interval_day_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:day:hourly".upper():
            hourly_values = self.get_hourly_day_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:day:list".upper():
            hourly_values = self.get_list_day_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:week:compact".upper():
            hourly_values = self.get_compact_weekly_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:week:daily".upper():
            hourly_values = self.get_daily_weekly_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:constant".upper():
            hourly_values = self.get_constant_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:compact".upper():
            hourly_values = self.get_compact_ep_schedule_values(
                sch_name)
        elif schedule_type == "schedule:file".upper():
            hourly_values = self.get_file_ep_schedule_values(
                sch_name)
        else:
            log('Archetypal does not support "{}" currently'.format(
                schedule_type), lg.WARNING)

            hourly_values = []

        return hourly_values

    def is_schedule(self, sch_name):
        """Returns True if idfobject is one of 'schedule_types'"""
        if sch_name.upper() in self.idf.schedules_dict:
            return True
        else:
            return False

    def to_year_week_day(self):
        """

        Returns: epbunch
            'Schedule:Year', 'Schedule:Week:Daily', 'Schedule:Day:Hourly'
        """

        full_year = np.array(self.all_values)  # array of shape (8760,)
        values = full_year.reshape(-1, 24)  # shape (365, 24)

        # create unique days
        unique_days, nds = np.unique(values, axis=0, return_inverse=True)

        ep_days = []
        dict_day = {}
        for unique_day in unique_days:
            name = 'day_' + str(uuid.uuid4().hex)
            dict_day[name] = unique_day

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
        for unique_week in unique_weeks:
            week_id = 'week_' + str(uuid.uuid4().hex)
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
        bincount = np.bincount(nws)
        week_order = {i: v for i, v in enumerate(np.array(
            [key for key, group in itertools.groupby(nws + 1) if key]) - 1)}
        for i, (week_n, count) in enumerate(
                zip(week_order, [bincount[week_order[i]] for i in week_order])):
            week_id = list(dict_week)[week_order[i]]
            to_date = from_date + timedelta(days=int(count * 7))
            blocks[week_id] = {}
            blocks[week_id]['from_day'] = from_date.day
            blocks[week_id]['end_day'] = to_date.day
            blocks[week_id]['from_month'] = from_date.month
            blocks[week_id]['end_month'] = to_date.month
            from_date = to_date + timedelta(days=1)

            # If this is the last block, force end of year
            if i == len(bincount) - 1:
                blocks[week_id]['end_day'] = 31
                blocks[week_id]['end_month'] = 12

        new_dict = dict(Name=self.schName + '_',
                        Schedule_Type_Limits_Name=self.schType)
        for count, week_id in enumerate(blocks):
            count += 1
            new_dict.update({"ScheduleWeek_Name_{}".format(count): week_id,
                             "Start_Month_{}".format(count):
                                 blocks[week_id]['from_month'],
                             "Start_Day_{}".format(count):
                                 blocks[week_id]['from_day'],
                             "End_Month_{}".format(count):
                                 blocks[week_id]['end_month'],
                             "End_Day_{}".format(count):
                                 blocks[week_id]['end_day']})

        ep_year = self.idf.add_object(ep_object='Schedule:Year'.upper(),
                                      save=False, **new_dict)
        return ep_year, ep_weeks, ep_days

    def date_field_interpretation(self, field):
        """Date Field Interpretation

        Args:
            field (str): The EnergyPlus Field Contents

        Returns:
            (datetime): The datetime object

        Info:
            See EnergyPlus documentation for more details:
            1.6.8.1.2 Field: Start Date
                (Table 1.4: Date Field Interpretation)
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
                date = self.parse_fancy_string(field)
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

    def parse_fancy_string(self, field):
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

        # parse the dayofweek eg. monday
        dayofweek = datetime.strptime(dayofweek.capitalize(),
                                      '%A').weekday()

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
        field_set

        Weekdays, Weekends, Holidays, Alldays, SummerDesignDay,
        WinterDesignDay,
         Sunday, Monday, Tuesday, Wednesday, Thursday, Friday, Saturday,
         CustomDay1, CustomDay2, AllOtherDays

        Args:
            slicer_:
            field: """

        if field.lower() == 'weekdays':
            # return only days of weeks
            return lambda x: x.index.dayofweek < 5
        elif field.lower() == 'weekends':
            # return only weekends
            return lambda x: x.index.dayofweek >= 5
        elif field.lower() == 'alldays':
            # return all days := equivalenet to .loc[:]
            return pd.IndexSlice[:]
        elif field.lower() == 'allotherdays':
            # return unused days. Uses the global variable `sliced_day`
            if slicer_ is not None:
                return ~slicer_
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
            return pd.IndexSlice[:]
        elif field.lower() == 'winterdesignday':
            # return design_day(self, field)
            return pd.IndexSlice[:]
        elif field.lower() == 'holiday' or field.lower() == 'holidays':
            field = 'holiday'
            return special_day(self, field, slicer_)
        else:
            raise NotImplementedError(
                'Archetypal does not yet support The '
                'Field_set "{}"'.format(field))

    def __len__(self):
        """returns the length of all values of the schedule"""
        return len(self.all_values)

    def __eq__(self, other):
        """Overrides the default implementation"""
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
        """Returns the start day of the week"""
        if start_day_of_week is None:
            return self.idf.day_of_week_for_start_day
        else:
            return start_day_of_week


def design_day(schedule, field):
    # try to get the SizingPeriod:DesignDay for the corresponding Day Type
    dds = schedule.idf.idfobjects['SizingPeriod:DesignDay'.upper()]
    dd = [dd for dd in dds if dd.Day_Type.lower() == field]
    if len(dd) > 0:
        # should have found only one design day matching the Day Type

        data = [dd[0].Month, dd[0].Day_of_Month]
        date = '/'.join([str(item).zfill(2) for item in data])
        date = schedule.date_field_interpretation(date)
        return lambda x: x.index == date
    else:
        msg = 'Could not find a "SizingPeriod:DesignDay" object ' \
              'needed for schedule "{}" with Day Type "{}"'.format(
            schedule.schName, field.capitalize()
        )
        raise ValueError(msg)


def special_day(schedule, field, slicer_):
    # try to get the RunPeriodControl:SpecialDays for the corresponding Day
    # Type
    dds = schedule.idf.idfobjects['RunPeriodControl:SpecialDays'.upper()]
    dd = [dd for dd in dds if dd.Special_Day_Type.lower() == field]
    if len(dd) > 0:
        slice = []
        for dd in dd:
            # can have more than one special day types
            data = dd.Start_Date
            duration = dd.Duration
            from_date = schedule.date_field_interpretation(data)
            to_date = from_date + timedelta(days=duration)
            slice.append(slicer_.loc[from_date:to_date])
        import operator
        return conjunction(*slice, logical=operator.and_).index
    else:
        msg = 'Could not find a "SizingPeriod:DesignDay" object ' \
              'needed for schedule "{}" with Day Type "{}"'.format(
            schedule.schName, field.capitalize()
        )
        raise ValueError(msg)


def conjunction(*conditions, logical=np.logical_and):
    """Applies a logical function on n conditions"""
    return functools.reduce(logical, conditions)


def separator(sep):
    """helper function to return the correct delimiter"""
    if sep == 'Comma':
        return ','
    elif sep == 'Tab':
        return '\t'
    elif sep == 'Fixed':
        return None
    elif sep == 'Semicolon':
        return ';'
    else:
        return None


def how(how):
    """Helper function to return the correct resampler"""
    if how.lower() == 'average':
        return 'mean'
    elif how.lower() == 'linear':
        return 'interpolate'
    elif how.lower() == 'no':
        return 'max'
    else:
        return 'max'
