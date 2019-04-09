import logging as lg

from archetypal import log


class Schedule(object):
    """An object designed to handle any EnergyPlys schedule object"""

    def __init__(self, idf, sch_name, start_day_of_the_week=0):
        self.idf = idf
        # self.hb_EPObjectsAUX = sc.sticky["honeybee_EPObjectsAUX"]()
        # self.lb_preparation = sc.sticky["ladybug_Preparation"]()
        self.schName = sch_name
        self.startDayOfTheWeek = start_day_of_the_week
        self.count = 0
        self.startHOY = 1
        self.endHOY = 24
        self.unit = "unknown"

    @property
    def all_values(self):
        return self.get_schedule_values(self.schName)

    def get_schedule_type_limits_data(self, sch_name):
        """Returns Scehdule Type Limits data"""

        if sch_name is None:
            sch_name = self.schName

        schedule = self.idf.get_schedule_type_limits_data_by_name(sch_name)
        try:
            lower_limit, upper_limit, numeric_type, unit_type = schedule.obj[2:]
        except:
            lower_limit, upper_limit, numeric_type = schedule.obj[2:]
            unit_type = "unknown"

        self.unit = unit_type
        if self.unit == "unknown":
            self.unit = numeric_type

        return lower_limit, upper_limit, numeric_type, unit_type

    def get_interval_day_ep_schedule_values(self, sch_name=None):
        """'Schedule:Day:Interval"""

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())
        type_limit_name = values.Schedule_Type_Limits_Name
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(type_limit_name)

        number_of_day_sch = int((len(values) - 3) / 2)

        hourly_values = list(range(24))
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
            hourly_values = list(map(int, hourly_values))

        return hourly_values

    def get_hourly_day_ep_schedule_values(self, sch_name=None):
        """'Schedule:Day:Hourly'"""
        # Todo: get_hourly_day_ep_schedule_values
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        return []

    def get_compact_weekly_ep_schedule_values(self, sch_name=None):
        """'schedule:week:compact'"""
        # Todo: get_compact_weekly_ep_schedule_values

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        return []

    def get_daily_weekly_ep_schedule_values(self, sch_name=None):
        """'schedule:week:daily'"""
        # Todo: get_daily_weekly_ep_schedule_values
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        return []

    def get_constant_ep_schedule_values(self, sch_name=None):
        """'schedule:constant'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        type_limit_name = values.Schedule_Type_Limits_Name
        lower_limit, upper_limit, numeric_type, unit_type = \
            self.get_schedule_type_limits_data(type_limit_name)
        hourly_values = list(range(8760))
        value = float(values['Hourly_Value'])
        for hour in hourly_values:
            hourly_values[hour] = value

        if numeric_type.strip().lower() == 'discrete':
            hourly_values = list(map(int, hourly_values))

        return hourly_values

    def get_hourly_weekly_ep_schedule_values(self, sch_name=None):
        """'schedule:week:hourly'"""
        # Todo: get_hourly_weekly_ep_schedule_values
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        return []

    def get_file_ep_schedule_values(self, sch_name=None):
        """'schedule:file'"""
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())
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
        skip_rows = int(rows)-1 # We want to keep the column
        col = [int(column)]
        values = pd.read_csv(file, delimiter=delimeter, skiprows=skip_rows,
                             usecols=col)

        return values.iloc[:, 0].to_list()

    def get_compcat_ep_schedule_values(self, sch_name=None):
        """'schedule:compact'"""
        # Todo: get_compcat_ep_schedule_values
        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        return []

    def get_yearly_ep_schedule_values(self, sch_name=None):
        """'schedule:year'"""
        # place holder for 365 days
        hourly_values = range(365)

        # update last day of schedule
        self.endHOY = 8760

        if sch_name is None:
            sch_name = self.schName

        values = self.idf.get_schedule_data_by_name(sch_name.upper())

        # generate weekly schedules
        num_of_weekly_schedules = int(len(values) / 5)

        for i in range(num_of_weekly_schedules):
            week_day_schedule_name = values[
                'ScheduleWeek_Name_{}'.format(i + 1)]

            start_day = values['Start_Day_{}'.format(i + 1)]
            end_day = values['End_Day_{}'.format(i + 1)]

            # 7 list for 7 days of the week
            hourly_values_for_the_week = self.get_schedule_values(
                week_day_schedule_name)

            for day in range(start_day - 1, end_day):
                hourly_values[day] = hourly_values_for_the_week[day % 7]

        return hourly_values

    def get_schedule_values(self, sch_name=None):
        """Main function that returns the schedule values"""
        if sch_name is None:
            sch_name = self.schName
        if self.is_schedule(sch_name):
            schedule_values = self.idf.get_schedule_data_by_name(sch_name.upper())

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
            elif schedule_type == "schedule:week:compact".upper():
                hourly_values = self.get_compact_weekly_ep_schedule_values(
                    sch_name)
            elif schedule_type == "schedule:week:daily".upper():
                hourly_values = self.get_daily_weekly_ep_schedule_values(
                    sch_name)
            elif schedule_type == "schedule:week:hourly".upper():
                hourly_values = self.get_hourly_weekly_ep_schedule_values(
                    sch_name)
            elif schedule_type == "schedule:constant".upper():
                hourly_values = self.get_constant_ep_schedule_values(
                    sch_name)
            elif schedule_type == "schedule:compact".upper():
                hourly_values = self.get_compcat_ep_schedule_values(
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
        for obj in self.idf.idfobjects:
            for bunch in self.idf.idfobjects[obj]:
                try:
                    if bunch.Name.upper() == sch_name.upper():
                        obj_type = bunch.fieldvalues[0]
                        if obj_type.upper() in schedule_types:
                            return True
                        else:
                            return False
                except:
                    pass


def separator(sep):
    """helper function to return the correct delimiter"""
    if sep == 'Comma':
        return ','
    if sep == 'Tab':
        return '\t'
    if sep == 'Fixed':
        return None
    if sep == 'Semicolon':
        return ';'


schedule_types = ['Schedule:Day:Hourly'.upper(),
                  'Schedule:Day:Interval'.upper(), 'Schedule:Day:List'.upper(),
                  'Schedule:Week:Daily'.upper(), 'Schedule:Year'.upper(),
                  'Schedule:Week:Compact'.upper(), 'Schedule:Compact'.upper(),
                  'Schedule:Constant'.upper(), 'Schedule:File'.upper()]
