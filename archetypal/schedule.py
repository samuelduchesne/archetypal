################################################################################
# Module: schedule.py
# Description: Functions for handling conversion of EnergyPlus schedule objects
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import functools
import io
import logging as lg
from calendar import calendar
from datetime import datetime, timedelta
from itertools import groupby

import numpy as np
import pandas as pd
from eppy.bunch_subclass import EpBunch
from numpy import ndarray

from archetypal import EnergySeries
from archetypal.utils import log


class Schedule(object):
    """An object designed to handle any EnergyPlus schedule object"""

    def __init__(
        self,
        Name,
        idf=None,
        start_day_of_the_week=None,
        strict=False,
        base_year=None,
        schType=None,
        Type=None,
        Values=None,
        epbunch=None,
        **kwargs,
    ):
        """
        Args:
            Name (str): The schedule name in the idf model.
            idf (IDF): The IDF model.
            start_day_of_the_week (int): 0-based day of week (Monday=0). Default is
                None which looks for the start day in the IDF model.
            strict (bool): if True, schedules that have the Field-Sets such as
                Holidays and CustomDay will raise an error if they are absent
                from the IDF file. If False, any missing qualifiers will be
                ignored.
            base_year (int): The base year of the schedule. Defaults to 2018
                since the first day of that year is a Monday.
            schType (str): The EnergyPlus schedule type. eg.: "Schedule:Year"
            Type (str): This field contains a reference to the
                Schedule Type Limits object. If found in a list of Schedule Type
                Limits (see above), then the restrictions from the referenced
                object will be used to validate the current field values.
            Values (ndarray): A 24 or 8760 list of schedule values.
            epbunch (EpBunch): An EpBunch object from which this schedule can
                be created.
            **kwargs:
        """
        try:
            kwargs["idf"] = idf
            Name = kwargs.pop("Name", Name)
            super(Schedule, self).__init__(Name, **kwargs)
        except Exception as e:
            pass  # todo: make this more robust
        self.strict = strict
        self._idf = idf
        self.Name = Name
        self.startDayOfTheWeek = self.get_sdow(start_day_of_the_week)
        self.year = get_year_for_first_weekday(self.startDayOfTheWeek)

        self.count = 0
        self.startHOY = 1
        self.endHOY = 24
        self.unit = "unknown"
        self.index_ = None
        self._values = Values
        self.schType = schType
        self.Type = Type

        try:
            self.epbunch = epbunch or self.idf.get_schedule_epbunch(self.Name)
        except KeyError:
            self.epbunch = None

        if self.Type is None:
            self.Type = self.get_schedule_type_limits_name(sch_type=self.schType)

    @property
    def idf(self):
        if self._idf is None:
            from .idfclass.idf import IDF

            self._idf = IDF()
        return self._idf

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
        return cls(Name=Name, Values=Values, Type=Type, idf=idf, **kwargs)

    @classmethod
    def constant_schedule(
        cls, hourly_value=1, Name="AlwaysOn", idf=None, Type="Fraction", **kwargs
    ):
        """Create a schedule with a constant value for the whole year. Defaults
        to a schedule with a value of 1, named 'AlwaysOn'.

        Args:
            hourly_value (float, optional): The value for the constant schedule.
                Defaults to 1.
            Name (str, optional): The name of the schedule. Defaults to Always
                On.
            idf:
            **kwargs:
        """
        if not idf:
            from archetypal import IDF

            idf = IDF(prep_outputs=False)
        # Add the schedule to the existing idf
        epbunch = idf.anidfobject(
            key="Schedule:Constant".upper(),
            Name=Name,
            Schedule_Type_Limits_Name=Type,
            Hourly_Value=hourly_value,
        )
        return cls(
            Name=Name,
            Values=np.ones(8760) * hourly_value,
            idf=idf,
            epbunch=epbunch,
            **kwargs,
        )

    @property
    def all_values(self) -> np.ndarray:
        """returns the values array"""
        if self._values is None:
            self._values = self.get_schedule_values(self.epbunch)
        return self._values

    @property
    def max(self):
        return max(self.all_values)

    @property
    def min(self):
        return min(self.all_values)

    @property
    def mean(self):
        return np.average(self.all_values)

    @property
    def series(self):
        """Returns the schedule values as an :class:`EnergySeries` object with a
        DateTimeIndex
        """
        index = pd.date_range(
            start=self.startDate, periods=len(self.all_values), freq="1H"
        )
        return EnergySeries(self.all_values, index=index, name=self.Name)

    def get_schedule_type_limits_name(self, sch_type=None):
        """Return the Schedule Type Limits name associated to this schedule

        Args:
            sch_type:
        """
        if self.epbunch is None:
            schedule_values = self.idf.get_schedule_epbunch(
                self.Name, sch_type=sch_type
            )
        else:
            schedule_values = self.epbunch
        try:
            schedule_limit_name = schedule_values.Schedule_Type_Limits_Name
        except:
            return "unknown"
        else:
            return schedule_limit_name

    def get_schedule_type_limits_data(self, name=None):
        """Returns Schedule Type Limits data from schedule name

        Args:
            name:
        """

        if name is None:
            name = self.Name

        schedule_values = self.epbunch
        try:
            schedule_limit_name = schedule_values.Schedule_Type_Limits_Name
        except:
            # this schedule is probably a 'Schedule:Week:Daily' which does
            # not have a Schedule_Type_Limits_Name field
            return "", "", "", ""
        else:
            (
                lower_limit,
                upper_limit,
                numeric_type,
                unit_type,
            ) = self.idf.get_schedule_type_limits_data_by_name(schedule_limit_name)

            self.unit = unit_type
            if self.unit == "unknown":
                self.unit = numeric_type

            return lower_limit, upper_limit, numeric_type, unit_type

    def get_schedule_type(self, name=None):
        """Return the schedule type, eg.: "Schedule:Year"

        Args:
            name:
        """
        if name is None:
            name = self.Name

        schedule_values = self.epbunch
        sch_type = schedule_values.key

        return sch_type

    @property
    def startDate(self):
        """The start date of the schedule. Satisfies `startDayOfTheWeek`"""
        year = get_year_for_first_weekday(self.startDayOfTheWeek)
        return datetime(year, 1, 1)

    def plot(self, slice=None, **kwargs):
        """Plot the schedule. Implements the .loc accessor on the series object.

        Examples:
            >>> from archetypal import IDF
            >>> idf = IDF()
            >>> s = Schedule(
            >>>         Name="NECB-A-Thermostat Setpoint-Heating",
            >>>         idf=idf)
            >>>     )
            >>> s.plot(slice=("2018/01/02", "2018/01/03"), drawstyle="steps-post")

        Args:
            slice (tuple): define a 2-tuple object the will be passed to
                :class:`pandas.IndexSlice` as a range.
            **kwargs (dict): keyword arguments passed to
                :meth:`pandas.Series.plot`.
        """
        hourlyvalues = self.all_values
        index = pd.date_range(self.startDate, periods=len(hourlyvalues), freq="1H")
        series = pd.Series(hourlyvalues, index=index, dtype=float)
        if slice is None:
            slice = pd.IndexSlice[:]
        elif len(slice) > 1:
            slice = pd.IndexSlice[slice[0] : slice[1]]
        label = kwargs.pop("label", self.Name)
        ax = series.loc[slice].plot(**kwargs, label=label)
        return ax

    def plot2d(self, **kwargs):
        """Plot the carpet plot of the schedule"""
        return EnergySeries(self.series, name=self.Name).plot2d(**kwargs)

    def get_interval_day_ep_schedule_values(self, epbunch: EpBunch) -> np.ndarray:
        """Schedule:Day:Interval

        Args:
            epbunch (EpBunch): The schedule EpBunch object.
        """

        (
            lower_limit,
            upper_limit,
            numeric_type,
            unit_type,
        ) = self.get_schedule_type_limits_data(epbunch.Name)

        number_of_day_sch = int((len(epbunch.fieldvalues) - 3) / 2)

        hourly_values = np.arange(24, dtype=float)
        start_hour = 0
        for i in range(number_of_day_sch):
            value = float(epbunch["Value_Until_Time_{}".format(i + 1)])
            until_time = [
                int(s.strip())
                for s in epbunch["Time_{}".format(i + 1)].split(":")
                if s.strip().isdigit()
            ]
            end_hour = int(until_time[0] + until_time[1] / 60)
            for hour in range(start_hour, end_hour):
                hourly_values[hour] = value

            start_hour = end_hour

        if numeric_type.strip().lower() == "discrete":
            hourly_values = hourly_values.astype(int)

        return hourly_values

    def get_hourly_day_ep_schedule_values(self, epbunch):
        """Schedule:Day:Hourly

        Args:
            epbunch (EpBunch): The schedule EpBunch object.
        """

        fieldvalues_ = np.array(epbunch.fieldvalues[3:])

        return fieldvalues_

    def get_compact_weekly_ep_schedule_values(
        self, epbunch, start_date=None, index=None
    ) -> np.ndarray:
        """schedule:week:compact

        Args:
            epbunch (EpBunch): the name of the schedule
            start_date:
            index:
        """
        if start_date is None:
            start_date = self.startDate
        if index is None:
            idx = pd.date_range(start=start_date, periods=168, freq="1H")
            slicer_ = pd.Series([False] * (len(idx)), index=idx)
        else:
            slicer_ = pd.Series([False] * (len(index)), index=index)

        weekly_schedules = pd.Series([0] * len(slicer_), index=slicer_.index)
        # update last day of schedule

        if self.count == 0:
            self.schType = epbunch.key
            self.endHOY = 168

        num_of_daily_schedules = int(len(epbunch.fieldvalues[2:]) / 2)

        for i in range(num_of_daily_schedules):
            day_type = epbunch["DayType_List_{}".format(i + 1)].lower()
            # This field can optionally contain the prefix “For”
            how = self.field_set(day_type.strip("for: "), slicer_)
            if not weekly_schedules.loc[how].empty:
                # Loop through days and replace with day:schedule values
                days = []
                for name, day in weekly_schedules.loc[how].groupby(
                    pd.Grouper(freq="D")
                ):
                    if not day.empty:
                        ref = epbunch.get_referenced_object(
                            "ScheduleDay_Name_{}".format(i + 1)
                        )
                        day.loc[:] = self.get_schedule_values(sched_epbunch=ref)
                        days.append(day)
                new = pd.concat(days)
                slicer_.update(pd.Series([True] * len(new.index), index=new.index))
                slicer_ = slicer_.apply(lambda x: x == True)
                weekly_schedules.update(new)
            else:
                return weekly_schedules.values

        return weekly_schedules.values

    def get_daily_weekly_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:week:daily

        Args:
            epbunch (EpBunch): The schedule EpBunch object.
        """
        # 7 list for 7 days of the week
        hourly_values = []
        for day in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]:
            ref = epbunch.get_referenced_object("{}_ScheduleDay_Name".format(day))
            h = self.get_schedule_values(sched_epbunch=ref)
            hourly_values.append(h)
        hourly_values = np.array(hourly_values)
        # shift days earlier by self.startDayOfTheWeek
        hourly_values = np.roll(hourly_values, -self.startDayOfTheWeek, axis=0)

        return hourly_values.ravel()

    def get_list_day_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:day:list

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        import pandas as pd

        freq = int(epbunch["Minutes_per_Item"])  # Frequency of the values
        num_values = epbunch.fieldvalues[5:]  # List of values
        method = epbunch["Interpolate_to_Timestep"]  # How to resample

        # fill a list of available values and pad with zeros (this is safer
        # but should not occur)
        all_values = np.arange(int(24 * 60 / freq))
        for i in all_values:
            try:
                all_values[i] = num_values[i]
            except:
                all_values[i] = 0
        # create a fake index to help us with the resampling
        index = pd.date_range(
            start=self.startDate, periods=(24 * 60) / freq, freq="{}T".format(freq)
        )
        series = pd.Series(all_values, index=index)

        # resample series to hourly values and apply resampler function
        series = series.resample("1H").apply(_how(method))

        return series.values

    def get_constant_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:constant

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        (
            lower_limit,
            upper_limit,
            numeric_type,
            unit_type,
        ) = self.get_schedule_type_limits_data(epbunch.Name)

        hourly_values = np.arange(8760)
        value = float(epbunch["Hourly_Value"])
        for hour in hourly_values:
            hourly_values[hour] = value

        if numeric_type.strip().lower() == "discrete":
            hourly_values = hourly_values.astype(int)

        return hourly_values

    def get_file_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:file

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        filename = epbunch["File_Name"]
        column = epbunch["Column_Number"]
        rows = epbunch["Rows_to_Skip_at_Top"]
        hours = epbunch["Number_of_Hours_of_Data"]
        sep = epbunch["Column_Separator"]
        interp = epbunch["Interpolate_to_Timestep"]

        file = self.idf.simulation_dir.files(filename)[0]

        delimeter = _separator(sep)
        skip_rows = int(rows) - 1  # We want to keep the column
        col = [int(column) - 1]  # zero-based
        epbunch = pd.read_csv(
            file, delimiter=delimeter, skiprows=skip_rows, usecols=col
        )

        return epbunch.iloc[:, 0].values

    def get_compact_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:compact

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        field_sets = ["through", "for", "interpolate", "until", "value"]
        fields = epbunch.fieldvalues[3:]

        index = pd.date_range(start=self.startDate, periods=8760, freq="H")
        zeros = np.zeros(len(index))

        slicer_ = pd.Series([False] * len(index), index=index)
        series = pd.Series(zeros, index=index)

        from_day = self.startDate
        ep_from_day = datetime(self.year, 1, 1)
        from_time = "00:00"
        how_interpolate = None
        for field in fields:
            if any([spe in field.lower() for spe in field_sets]):
                f_set, hour, minute, value = self._field_interpreter(field)

                if f_set.lower() == "through":
                    # main condition. All sub-conditions must obey a
                    # `Through` condition

                    # First, initialize the slice (all False for now)
                    through_conditions = self.invalidate_condition(series)

                    # reset from_time
                    from_time = "00:00"

                    # Prepare ep_to_day variable
                    ep_to_day = self._date_field_interpretation(value) + timedelta(
                        days=1
                    )

                    # Calculate Timedelta in days
                    days = (ep_to_day - ep_from_day).days
                    # Add timedelta to startDate
                    to_day = from_day + timedelta(days=days) + timedelta(hours=-1)

                    # slice the conditions with the range and apply True
                    through_conditions.loc[from_day:to_day] = True

                    from_day = to_day + timedelta(hours=1)
                    ep_from_day = ep_to_day
                elif f_set.lower() == "for":
                    # slice specific days
                    # reset from_time
                    from_time = "00:00"

                    for_condition = self.invalidate_condition(series)
                    fors = value.split()
                    if len(fors) > 1:
                        # if multiple `For`. eg.: For: Weekends Holidays,
                        # Combine both conditions
                        for value in fors:
                            if value.lower() == "allotherdays":
                                # Apply condition to slice
                                how = self.field_set(value, slicer_)
                                # Reset through condition
                                through_conditions = how
                                for_condition = how
                            else:
                                how = self.field_set(value, slicer_)
                                if how is not None:
                                    for_condition.loc[how] = True
                    elif value.lower() == "allotherdays":
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
                elif "interpolate" in f_set.lower():
                    # we need to upsample to series to 8760 * 60 values
                    new_idx = pd.date_range(
                        start=self.startDate, periods=525600, closed="left", freq="T"
                    )
                    series = series.resample("T").pad()
                    series = series.reindex(new_idx)
                    series.fillna(method="pad", inplace=True)
                    through_conditions = through_conditions.resample("T").pad()
                    through_conditions = through_conditions.reindex(new_idx)
                    through_conditions.fillna(method="pad", inplace=True)
                    for_condition = for_condition.resample("T").pad()
                    for_condition = for_condition.reindex(new_idx)
                    for_condition.fillna(method="pad", inplace=True)
                    how_interpolate = value.lower()
                elif f_set.lower() == "until":
                    until_condition = self.invalidate_condition(series)
                    if series.index.freq.name == "T":
                        # until_time = str(int(hour) - 1) + ':' + minute
                        until_time = timedelta(
                            hours=int(hour), minutes=int(minute)
                        ) - timedelta(minutes=1)

                    else:
                        until_time = str(int(hour) - 1) + ":" + minute
                    until_condition.loc[
                        until_condition.between_time(from_time, str(until_time)).index
                    ] = True
                    all_conditions = (
                        for_condition & through_conditions & until_condition
                    )

                    from_time = str(int(hour)) + ":" + minute
                elif f_set.lower() == "value":
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
            return series.resample("H").mean().values
        else:
            return series.values

    def _field_interpreter(self, field):
        """dealing with a Field-Set (Through, For, Interpolate, # Until, Value)
        and return the parsed string

        Args:
            field:
        """

        values_sets = [
            "weekdays",
            "weekends",
            "alldays",
            "allotherdays",
            "sunday",
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "summerdesignday",
            "winterdesignday",
            "holiday",
        ]
        keywords = None

        if "through" in field.lower():
            # deal with through
            if ":" in field.lower():
                # parse colon
                f_set, statement = field.split(":")
                hour = None
                minute = None
                value = statement.strip()
            else:
                msg = (
                    'The schedule "{sch}" contains a Field '
                    'that is not understood: "{field}"'.format(
                        sch=self.Name, field=field
                    )
                )
                raise NotImplementedError(msg)
        elif "for" in field.lower():
            keywords = [word for word in values_sets if word in field.lower()]
            if ":" in field.lower():
                # parse colon
                f_set, statement = field.split(":")
                value = statement.strip()
                hour = None
                minute = None
            elif keywords:
                # get epBunch of the sizing period
                statement = " ".join(keywords)
                f_set = [s for s in field.split() if "for" in s.lower()][0]
                value = statement.strip()
                hour = None
                minute = None
            else:
                # parse without a colon
                msg = (
                    'The schedule "{sch}" contains a Field '
                    'that is not understood: "{field}"'.format(
                        sch=self.Name, field=field
                    )
                )
                raise NotImplementedError(msg)
        elif "interpolate" in field.lower():
            msg = (
                'The schedule "{sch}" contains sub-hourly values ('
                'Field-Set="{field}"). The average over the hour is '
                "taken".format(sch=self.Name, field=field)
            )
            log(msg, lg.WARNING)
            f_set, value = field.split(":")
            hour = None
            minute = None
        elif "until" in field.lower():
            if ":" in field.lower():
                # parse colon
                try:
                    f_set, hour, minute = field.split(":")
                    hour = hour.strip()  # remove trailing spaces
                    minute = minute.strip()  # remove trailing spaces
                    value = None
                except:
                    f_set = "until"
                    hour, minute = field.split(":")
                    hour = hour[-2:].strip()
                    minute = minute.strip()
                    value = None
            else:
                msg = (
                    'The schedule "{sch}" contains a Field '
                    'that is not understood: "{field}"'.format(
                        sch=self.Name, field=field
                    )
                )
                raise NotImplementedError(msg)
        elif "value" in field.lower():
            if ":" in field.lower():
                # parse colon
                f_set, statement = field.split(":")
                value = statement.strip()
                hour = None
                minute = None
            else:
                msg = (
                    'The schedule "{sch}" contains a Field '
                    'that is not understood: "{field}"'.format(
                        sch=self.Name, field=field
                    )
                )
                raise NotImplementedError(msg)
        else:
            # deal with the data value
            f_set = field
            hour = None
            minute = None
            value = field[len(field) + 1 :].strip()

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

    def get_yearly_ep_schedule_values(self, epbunch) -> np.ndarray:
        """schedule:year

        Args:
            epbunch (EpBunch): the schedule epbunch.
        """
        # first week

        start_date = self.startDate
        idx = pd.date_range(start=start_date, periods=8760, freq="1H")
        hourly_values = pd.Series([0] * 8760, index=idx)

        # update last day of schedule
        self.endHOY = 8760

        # generate weekly schedules
        num_of_weekly_schedules = int(len(epbunch.fieldvalues[3:]) / 5)

        for i in range(num_of_weekly_schedules):
            ref = epbunch.get_referenced_object("ScheduleWeek_Name_{}".format(i + 1))

            start_month = getattr(epbunch, "Start_Month_{}".format(i + 1))
            end_month = getattr(epbunch, "End_Month_{}".format(i + 1))
            start_day = getattr(epbunch, "Start_Day_{}".format(i + 1))
            end_day = getattr(epbunch, "End_Day_{}".format(i + 1))

            start = datetime.strptime(
                "{}/{}/{}".format(self.year, start_month, start_day), "%Y/%m/%d"
            )
            end = datetime.strptime(
                "{}/{}/{}".format(self.year, end_month, end_day), "%Y/%m/%d"
            )
            days = (end - start).days + 1

            end_date = start_date + timedelta(days=days) + timedelta(hours=23)
            how = pd.IndexSlice[start_date:end_date]

            weeks = []
            for name, week in hourly_values.loc[how].groupby(pd.Grouper(freq="168H")):
                if not week.empty:
                    try:
                        week.loc[:] = self.get_schedule_values(
                            sched_epbunch=ref,
                            start_date=week.index[0],
                            index=week.index,
                        )
                    except ValueError:
                        week.loc[:] = self.get_schedule_values(
                            sched_epbunch=ref, start_date=week.index[0]
                        )[0 : len(week)]
                    finally:
                        weeks.append(week)
            new = pd.concat(weeks)
            hourly_values.update(new)
            start_date += timedelta(days=days)

        return hourly_values.values

    def get_schedule_values(
        self, sched_epbunch, start_date=None, index=None
    ) -> np.ndarray:
        """Main function that returns the schedule values

        Args:
            sched_epbunch (EpBunch): the schedule epbunch object
            start_date:
            index:
        """
        if self.count == 0:
            # This is the first time, get the schedule type and the type limits.
            if self.Type is None:
                self.Type = self.get_schedule_type_limits_name()
        self.count += 1

        sch_type = sched_epbunch.key.upper()

        if sch_type.upper() == "schedule:year".upper():
            hourly_values = self.get_yearly_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:day:interval".upper():
            hourly_values = self.get_interval_day_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:day:hourly".upper():
            hourly_values = self.get_hourly_day_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:day:list".upper():
            hourly_values = self.get_list_day_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:week:compact".upper():
            hourly_values = self.get_compact_weekly_ep_schedule_values(
                sched_epbunch, start_date, index
            )
        elif sch_type.upper() == "schedule:week:daily".upper():
            hourly_values = self.get_daily_weekly_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:constant".upper():
            hourly_values = self.get_constant_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:compact".upper():
            hourly_values = self.get_compact_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:file".upper():
            hourly_values = self.get_file_ep_schedule_values(sched_epbunch)
        else:
            log(
                "Archetypal does not currently support schedules of type "
                '"{}"'.format(sch_type),
                lg.WARNING,
            )
            hourly_values = []

        return hourly_values

    def to_year_week_day(self, Values=None):
        """convert a Schedule Class to the 'Schedule:Year',
        'Schedule:Week:Daily' and 'Schedule:Day:Hourly' representation

        Args:
            Values:

        Returns:
            3-element tuple containing

            - **yearly** (*Schedule*): The yearly schedule object
            - **weekly** (*list of Schedule*): The list of weekly schedule
              objects
            - **daily** (*list of Schedule*):The list of daily schedule objects
        """
        if Values:
            full_year = Values
        else:
            full_year = np.array(self.all_values)  # array of shape (8760,)

        # reshape to (365, 24)
        Values = full_year.reshape(-1, 24)  # shape (365, 24)

        # create unique days
        unique_days, nds = np.unique(Values, axis=0, return_inverse=True)

        ep_days = []
        dict_day = {}
        for count_day, unique_day in enumerate(unique_days):
            name = f"d_{self.Name}_{count_day:02d}"
            dict_day[name] = unique_day

            # Create idf_objects for schedule:day:hourly
            ep_day = self.idf.anidfobject(
                key="Schedule:Day:Hourly".upper(),
                **dict(
                    Name=name,
                    Schedule_Type_Limits_Name=self.Type,
                    **{"Hour_{}".format(i + 1): unique_day[i] for i in range(24)},
                ),
            )
            ep_days.append(ep_day)

        # create unique weeks from unique days
        try:
            unique_weeks, nwsi, nws, count = np.unique(
                full_year[: 364 * 24, ...].reshape(-1, 168),
                return_index=True,
                axis=0,
                return_inverse=True,
                return_counts=True,
            )
        except ValueError:
            raise ValueError(
                "Looks like the idf model needs to be rerun with 'annual=True'"
            )

        # We use the calendar module to set the week days order
        import calendar

        # initialize the calendar object
        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)

        # Appending unique weeks in dictionary with name and values of weeks as
        # keys
        # {'name_week': {'dayName':[]}}
        dict_week = {}
        for count_week, unique_week in enumerate(unique_weeks):
            week_id = f"w_{self.Name}_{count_week:02d}"
            dict_week[week_id] = {}
            for i, day in zip(list(range(0, 7)), list(c.iterweekdays())):
                day_of_week = unique_week[..., i * 24 : (i + 1) * 24]
                for key in dict_day:
                    if (day_of_week == dict_day[key]).all():
                        dict_week[week_id]["day_{}".format(day)] = key

        # Create idf_objects for schedule:week:daily

        # Create ep_weeks list and iterate over dict_week
        ep_weeks = []
        for week_id in dict_week:
            ep_week = self.idf.anidfobject(
                key="Schedule:Week:Daily".upper(),
                **dict(
                    Name=week_id,
                    **{
                        "{}_ScheduleDay_Name".format(
                            calendar.day_name[day_num]
                        ): dict_week[week_id]["day_{}".format(day_num)]
                        for day_num in c.iterweekdays()
                    },
                    Holiday_ScheduleDay_Name=dict_week[week_id]["day_6"],
                    SummerDesignDay_ScheduleDay_Name=dict_week[week_id]["day_1"],
                    WinterDesignDay_ScheduleDay_Name=dict_week[week_id]["day_1"],
                    CustomDay1_ScheduleDay_Name=dict_week[week_id]["day_2"],
                    CustomDay2_ScheduleDay_Name=dict_week[week_id]["day_5"],
                ),
            )
            ep_weeks.append(ep_week)

        blocks = {}
        from_date = datetime(self.year, 1, 1)
        bincount = [sum(1 for _ in group) for key, group in groupby(nws + 1) if key]
        week_order = {
            i: v
            for i, v in enumerate(
                np.array([key for key, group in groupby(nws + 1) if key]) - 1
            )
        }
        for i, (week_n, count) in enumerate(zip(week_order, bincount)):
            week_id = list(dict_week)[week_order[i]]
            to_date = from_date + timedelta(days=int(count * 7), hours=-1)
            blocks[i] = {}
            blocks[i]["week_id"] = week_id
            blocks[i]["from_day"] = from_date.day
            blocks[i]["end_day"] = to_date.day
            blocks[i]["from_month"] = from_date.month
            blocks[i]["end_month"] = to_date.month
            from_date = to_date + timedelta(hours=1)

            # If this is the last block, force end of year
            if i == len(bincount) - 1:
                blocks[i]["end_day"] = 31
                blocks[i]["end_month"] = 12

        new_dict = dict(Name=self.Name, Schedule_Type_Limits_Name=self.Type)
        for i in blocks:
            new_dict.update(
                {
                    "ScheduleWeek_Name_{}".format(i + 1): blocks[i]["week_id"],
                    "Start_Month_{}".format(i + 1): blocks[i]["from_month"],
                    "Start_Day_{}".format(i + 1): blocks[i]["from_day"],
                    "End_Month_{}".format(i + 1): blocks[i]["end_month"],
                    "End_Day_{}".format(i + 1): blocks[i]["end_day"],
                }
            )

        ep_year = self.idf.anidfobject(key="Schedule:Year".upper(), **new_dict)
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
        formats = ["%m/%d", "%d %B", "%B %d", "%d %b", "%b %d"]
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
                msg = (
                    "the schedule '{sch}' contains a "
                    "Field that is not understood: '{field}'".format(
                        sch=self.Name, field=field
                    )
                )
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
        time, month = field.lower().split(" in ")
        month = datetime.strptime(month, "%B").month

        # split the first part into nth and dayofweek
        nth, dayofweek = time.split(" ")
        if "last" in nth:
            nth = -1  # Use the last one
        else:
            nth = re.findall(r"\d+", nth)  # use the nth one
            nth = int(nth[0]) - 1  # python is zero-based

        weekday = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }

        # parse the dayofweek eg. monday
        dayofweek = weekday.get(dayofweek, 6)

        # create list of possible days using Calendar
        import calendar

        c = calendar.Calendar(firstweekday=self.startDayOfTheWeek)
        monthcal = c.monthdatescalendar(self.year, month)

        # iterate though the month and get the nth weekday
        date = [
            day
            for week in monthcal
            for day in week
            if day.weekday() == dayofweek and day.month == month
        ][nth]
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

        if field.lower() == "weekdays":
            # return only days of weeks
            return lambda x: x.index.dayofweek < 5
        elif field.lower() == "weekends":
            # return only weekends
            return lambda x: x.index.dayofweek >= 5
        elif field.lower() == "alldays":
            log(
                'For schedule "{}", the field-set "AllDays" may be overridden '
                'by the "AllOtherDays" field-set'.format(self.Name),
                lg.WARNING,
            )
            # return all days := equivalent to .loc[:]
            return pd.IndexSlice[:]
        elif field.lower() == "allotherdays":
            # return unused days (including special days). Uses the global
            # variable `slicer_`
            import operator

            if slicer_ is not None:
                return _conjunction(
                    *[self.special_day(field, slicer_), ~slicer_], logical=operator.or_
                )
            else:
                raise NotImplementedError
        elif field.lower() == "sunday":
            # return only sundays
            return lambda x: x.index.dayofweek == 6
        elif field.lower() == "monday":
            # return only mondays
            return lambda x: x.index.dayofweek == 0
        elif field.lower() == "tuesday":
            # return only Tuesdays
            return lambda x: x.index.dayofweek == 1
        elif field.lower() == "wednesday":
            # return only Wednesdays
            return lambda x: x.index.dayofweek == 2
        elif field.lower() == "thursday":
            # return only Thursdays
            return lambda x: x.index.dayofweek == 3
        elif field.lower() == "friday":
            # return only Fridays
            return lambda x: x.index.dayofweek == 4
        elif field.lower() == "saturday":
            # return only Saturdays
            return lambda x: x.index.dayofweek == 5
        elif field.lower() == "summerdesignday":
            # return design_day(self, field)
            return None
        elif field.lower() == "winterdesignday":
            # return design_day(self, field)
            return None
        elif field.lower() == "holiday" or field.lower() == "holidays":
            field = "holiday"
            return self.special_day(field, slicer_)
        elif not self.strict:
            # If not strict, ignore missing field-sets such as CustomDay1
            return lambda x: x < 0
        else:
            raise NotImplementedError(
                f"Archetypal does not yet support The Field_set '{field}'"
            )

    def __len__(self):
        """returns the length of all values of the schedule"""
        return len(self.all_values)

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

    def _repr_svg_(self):
        """SVG representation for iPython notebook"""
        fig, ax = self.series.plot2d(cmap="Greys", show=False, fig_width=5, dpi=72)
        f = io.BytesIO()
        fig.savefig(f, format="svg")
        return f.getvalue()

    def get_sdow(self, start_day_of_week):
        """Returns the start day of the week

        Args:
            start_day_of_week:
        """
        if start_day_of_week is None:
            try:
                return self.idf.day_of_week_for_start_day
            except:
                return 0
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
        special_day_types = ["holiday", "customday1", "customday2"]

        dds = self.idf.idfobjects["RunPeriodControl:SpecialDays".upper()]
        dd = [
            dd
            for dd in dds
            if dd.Special_Day_Type.lower() == field
            or dd.Special_Day_Type.lower() in special_day_types
        ]
        if len(dd) > 0:
            for dd in dd:
                # can have more than one special day types
                data = dd.Start_Date
                ep_start_date = self._date_field_interpretation(data)
                ep_orig = datetime(self.year, 1, 1)
                days_to_speciald = (ep_start_date - ep_orig).days
                duration = int(dd.Duration)
                from_date = self.startDate + timedelta(days=days_to_speciald)
                to_date = from_date + timedelta(days=duration) + timedelta(hours=-1)

                sp_slicer_.loc[from_date:to_date] = True
            return sp_slicer_
        elif not self.strict:
            return sp_slicer_
        else:
            msg = (
                'Could not find a "SizingPeriod:DesignDay" object '
                'needed for schedule "{}" with Day Type "{}"'.format(
                    self.Name, field.capitalize()
                )
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
        dds = self.idf.idfobjects["SizingPeriod:DesignDay".upper()]
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
                to_date = from_date + timedelta(days=duration) + timedelta(hours=-1)

                sp_slicer_.loc[from_date:to_date] = True
            return sp_slicer_
        elif not self.strict:
            return sp_slicer_
        else:
            msg = (
                'Could not find a "SizingPeriod:DesignDay" object '
                'needed for schedule "{}" with Day Type "{}"'.format(
                    self.Name, field.capitalize()
                )
            )
            raise ValueError(msg)

            data = [dd[0].Month, dd[0].Day_of_Month]
            date = "/".join([str(item).zfill(2) for item in data])
            date = self._date_field_interpretation(date)
            return lambda x: x.index == date

    def combine(self, other, weights=None, quantity=None):
        """Combine two schedule objects together.

        Args:
            other (Schedule): the other Schedule object to combine with.
            weights (list-like, optional): A list-like object of len 2. If None,
                equal weights are used.
            quantity: scalar value that will be multiplied by self before the
                averaging occurs. This ensures that the resulting schedule
                returns the correct integrated value.

        Returns:
            (Schedule): the combined Schedule object.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other

        # Check if other is the same type as self
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
            weights = [1, 1]
        new_values = np.average(
            [self.all_values, other.all_values], axis=0, weights=weights
        )

        # the new object's name
        name = "+".join([self.Name, other.Name])

        new_obj = self.__class__(name, value=new_values, idf=self.idf)

        return new_obj


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
    if sep == "Comma":
        return ","
    elif sep == "Tab":
        return "\t"
    elif sep == "Fixed":
        return None
    elif sep == "Semicolon":
        return ";"
    else:
        return ","


def _how(how):
    """Helper function to return the correct resampler

    Args:
        how:
    """
    if how.lower() == "average":
        return "mean"
    elif how.lower() == "linear":
        return "interpolate"
    elif how.lower() == "no":
        return "max"
    else:
        return "max"


def get_year_for_first_weekday(weekday=0):
    """Returns the year that starts on weekday, eg. Monday=0"""
    import calendar

    if weekday > 6:
        raise ValueError("weekday must be between 0 and 6")
    year = 2020
    not_found = True
    while not_found:
        firstday = calendar.weekday(year, 1, 1)
        if firstday == weekday and not calendar.isleap(year):
            not_found = False
        else:
            year = year - 1
    return year
