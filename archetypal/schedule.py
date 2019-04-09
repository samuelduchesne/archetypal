import logging as lg

from archetypal import log


class Schedule(object):
    """An object designed to handle any EnergyPlys schedule object"""

    def __init__(self, idf, schName, startDayOfTheWeek=0):
        self.idf = idf
        # self.hb_EPObjectsAUX = sc.sticky["honeybee_EPObjectsAUX"]()
        # self.lb_preparation = sc.sticky["ladybug_Preparation"]()
        self.schName = schName
        self.startDayOfTheWeek = startDayOfTheWeek
        self.count = 0
        self.startHOY = 1
        self.endHOY = 24
        self.unit = "unknown"

    @property
    def all_values(self):
        return self.getScheduleValues(self.schName)

    def getScheduleTypeLimitsData(self, schName):

        if schName is None:
            schName = self.schName

        schedule = self.idf.getScheduleTypeLimitsDataByName(schName)
        try:
            lowerLimit, upperLimit, numericType, unitType = schedule.obj[2:]
        except:
            lowerLimit, upperLimit, numericType = schedule.obj[2:]
            unitType = "unknown"

        self.unit = unitType
        if self.unit == "unknown":
            self.unit = numericType

        return lowerLimit, upperLimit, numericType, unitType

    def getIntervalDayEPScheduleValues(self, schName=None):
        """'Schedule:Day:Interval"""

        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())
        typeLimitName = values.Schedule_Type_Limits_Name
        lowerLimit, upperLimit, numericType, unitType = \
            self.getScheduleTypeLimitsData(typeLimitName)

        numberOfDaySch = int((len(values) - 3) / 2)

        hourlyValues = list(range(24))
        startHour = 0
        for i in range(numberOfDaySch):
            value = float(values['Value_Until_Time_{}'.format(i + 1)])
            untilTime = [int(s.strip()) for s in
                         values['Time_{}'.format(i + 1)].split(":") if
                         s.strip().isdigit()]
            endHour = int(untilTime[0] + untilTime[1] / 60)
            for hour in range(startHour, endHour):
                hourlyValues[hour] = value

            startHour = endHour

        if numericType.strip().lower() == "district":
            hourlyValues = map(int, hourlyValues)

        return hourlyValues

    def getHourlyDayEPScheduleValues(self, schName=None):
        """'Schedule:Day:Hourly'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getCompactWeeklyEPScheduleValues(self, schName=None):
        """'schedule:week:compact'"""

        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getDailyWeeklyEPScheduleValues(self, schName=None):
        """'schedule:week:daily'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getConstantEPScheduleValues(self, schName=None):
        """'schedule:constant'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getHourlyWeeklyEPScheduleValues(self, schName=None):
        """'schedule:week:hourly'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getFileEPScheduleValues(self, schName=None):
        """'schedule:file'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())
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

    def getCompcatEPScheduleValues(self, schName=None):
        """'schedule:compact'"""
        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        return []

    def getYearlyEPScheduleValues(self, schName=None):
        """'schedule:year'"""
        # place holder for 365 days
        hourlyValues = range(365)

        # update last day of schedule
        self.endHOY = 8760

        if schName is None:
            schName = self.schName

        values = self.idf.getScheduleDataByName(schName.upper())

        # generate weekly schedules
        numOfWeeklySchedules = int(len(values) / 5)

        for i in range(numOfWeeklySchedules):
            weekDayScheduleName = values['ScheduleWeek_Name_{}'.format(i + 1)]

            startDay = values['Start_Day_{}'.format(i + 1)]
            endDay = values['End_Day_{}'.format(i + 1)]

            # 7 list for 7 days of the week
            hourlyValuesForTheWeek = self.getScheduleValues(weekDayScheduleName)

            for day in range(startDay - 1, endDay):
                hourlyValues[day] = hourlyValuesForTheWeek[day % 7]

        return hourlyValues

    def getScheduleValues(self, schName=None):
        if schName is None:
            schName = self.schName
        if self.isSchedule(schName):
            scheduleValues = self.idf.getScheduleDataByName(schName.upper())

            scheduleType = scheduleValues.fieldvalues[0].upper()
            if self.count == 0:
                self.schType = scheduleType

            self.count += 1

            if scheduleType == "schedule:year".upper():
                hourlyValues = self.getYearlyEPScheduleValues(schName)
            elif scheduleType == "schedule:day:interval".upper():
                hourlyValues = self.getIntervalDayEPScheduleValues(schName)
            elif scheduleType == "schedule:day:hourly".upper():
                hourlyValues = self.getHourlyDayEPScheduleValues(schName)
            elif scheduleType == "schedule:week:compact".upper():
                hourlyValues = self.getCompactWeeklyEPScheduleValues(schName)
            elif scheduleType == "schedule:week:daily".upper():
                hourlyValues = self.getDailyWeeklyEPScheduleValues(schName)
            elif scheduleType == "schedule:week:hourly".upper():
                hourlyValues = self.getHourlyWeeklyEPScheduleValues(schName)
            elif scheduleType == "schedule:constant".upper():
                hourlyValues = self.getConstantEPScheduleValues(schName)
            elif scheduleType == "schedule:compact".upper():
                hourlyValues = self.getCompcatEPScheduleValues(schName)
            elif scheduleType == "schedule:file".upper():
                hourlyValues = self.getFileEPScheduleValues(schName)
            else:
                log('Archetypal does not support "{}" currently'.format(
                    scheduleType), lg.WARNING)

                hourlyValues = []

            return hourlyValues

    def isSchedule(self, schName):
        for obj in self.idf.idfobjects:
            for bunch in self.idf.idfobjects[obj]:
                try:
                    if bunch.Name.upper() == schName.upper():
                        obj_type = bunch.fieldvalues[0]
                        if obj_type.upper() in schedule_types:
                            return True
                        else:
                            return False
                except:
                    pass


def separator(sep):
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
