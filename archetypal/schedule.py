"""archetypal Schedule module."""

import functools
import io
import logging as lg
from datetime import datetime, timedelta
from itertools import groupby

import numpy as np
import pandas as pd
from energy_pandas import EnergySeries
from eppy.bunch_subclass import BadEPFieldError
from validator_collection import checkers, validators

from archetypal.utils import log


class ScheduleTypeLimits:
    """ScheduleTypeLimits class."""

    __slots__ = ("_name", "_lower_limit", "_upper_limit", "_numeric_type", "_unit_type")

    _NUMERIC_TYPES = ("continuous", "discrete")
    _UNIT_TYPES = (
        "Dimensionless",
        "Temperature",
        "DeltaTemperature",
        "PrecipitationRate",
        "Angle",
        "ConvectionCoefficient",
        "ActivityLevel",
        "Velocity",
        "Capacity",
        "Power",
        "Availability",
        "Percent",
        "Control",
        "Mode",
    )

    def __init__(
        self,
        Name,
        LowerLimit,
        UpperLimit,
        NumericType="Continuous",
        UnitType="Dimensionless",
    ):
        """Initialize object."""
        self.Name = Name
        self.LowerLimit = LowerLimit
        self.UpperLimit = UpperLimit
        self.NumericType = NumericType
        self.UnitType = UnitType

    @property
    def Name(self):
        """Get or set the name of the ScheduleTypeLimits."""
        return self._name

    @Name.setter
    def Name(self, value):
        self._name = validators.string(value)

    @property
    def LowerLimit(self):
        """Get or set the LowerLimit."""
        return self._lower_limit

    @LowerLimit.setter
    def LowerLimit(self, value):
        self._lower_limit = validators.float(value, allow_empty=True)

    @property
    def UpperLimit(self):
        """Get or set the UpperLimit."""
        return self._upper_limit

    @UpperLimit.setter
    def UpperLimit(self, value):
        self._upper_limit = validators.float(value, allow_empty=True)

    @property
    def NumericType(self):
        """Get or set numeric type. Can be null."""
        return self._numeric_type

    @NumericType.setter
    def NumericType(self, value):
        validators.string(value, allow_empty=True)
        if value is not None:
            assert value.lower() in self._NUMERIC_TYPES, (
                f"Input error for value '{value}'. NumericType must "
                f"be one of '{self._NUMERIC_TYPES}'"
            )
        self._numeric_type = value

    @property
    def UnitType(self):
        """Get or set the unit type. Can be null."""
        return self._unit_type

    @UnitType.setter
    def UnitType(self, value):
        value = validators.string(value)
        assert value.lower() in map(str.lower, self._UNIT_TYPES), (
            f"Input error for value '{value}'. UnitType must "
            f"be one of '{self._UNIT_TYPES}'"
        )
        self._unit_type = value

    @classmethod
    def from_dict(cls, data):
        """Create a ScheduleTypeLimit from a dictionary.

        Args:
            data: ScheduleTypeLimit dictionary following the format below.

        .. code-block:: python

            {
            "Name": 'Fractional',
            "LowerLimit": 0,
            "UpperLimit": 1,
            "NumericType": None,
            "UnitType": "Dimensionless"
            }
        """
        return cls(**data)

    @classmethod
    def from_epbunch(cls, epbunch):
        """Create a ScheduleTypeLimits from an epbunch.

        Args:
            epbunch (EpBunch): The epbunch of key "SCHEDULETYPELIMITS".
        """
        assert (
            epbunch.key.upper() == "SCHEDULETYPELIMITS"
        ), f"Expected 'SCHEDULETYPELIMITS' epbunch. Got {epbunch.key}."
        name = epbunch.Name
        lower_limit = epbunch.Lower_Limit_Value
        upper_limit = epbunch.Upper_Limit_Value
        numeric_type = epbunch.Numeric_Type
        unit_type = epbunch.Unit_Type
        return cls(
            Name=name,
            LowerLimit=lower_limit if checkers.is_numeric(lower_limit) else None,
            UpperLimit=upper_limit if checkers.is_numeric(upper_limit) else None,
            NumericType=numeric_type
            if checkers.is_string(numeric_type, minimum_length=1)
            else "Continuous",
            UnitType=unit_type
            if checkers.is_string(unit_type, minimum_length=1)
            else "Dimensionless",
        )

    def to_dict(self):
        """Return ScheduleTypeLimits dictionary representation."""
        return {
            "Name": self.Name,
            "LowerLimit": self.LowerLimit,
            "UpperLimit": self.UpperLimit,
            "NumericType": self.NumericType,
            "UnitType": self.UnitType,
        }

    def to_epbunch(self, idf):
        """Convert self to an epbunch given an idf model.

        Notes:
            The object is added to the idf model.

        Args:
            idf (IDF): An IDF model.

        .. code-block:: python

            SCHEDULETYPELIMITS,
                ,                         !- Name
                ,                         !- Lower Limit Value
                ,                         !- Upper Limit Value
                ,                         !- Numeric Type
                Dimensionless;            !- Unit Type

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        return idf.newidfobject(
            key="SCHEDULETYPELIMITS",
            Name=self.Name,
            Lower_Limit_Value=self.LowerLimit,
            Upper_Limit_Value=self.UpperLimit,
            Numeric_Type=self.NumericType,
            Unit_Type=self.UnitType,
        )

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __copy__(self):
        """Get copy of self."""
        return self.__class__(
            self.Name, self.LowerLimit, self.UpperLimit, self.NumericType, self.UnitType
        )

    def __repr__(self):
        """Return the string representation of self."""
        return (
            self.Name
            + f" {self.LowerLimit} < values < {self.UpperLimit}"
            + f"Units: {self.UnitType}"
        )

    def __keys__(self):
        """Get keys of self. Useful for hashing."""
        return (
            self.Name,
            self.LowerLimit,
            self.UpperLimit,
            self.NumericType,
            self.UnitType,
        )

    def __eq__(self, other):
        """Assert self is equal to other."""
        if not isinstance(other, ScheduleTypeLimits):
            return NotImplemented
        else:
            return self.__keys__() == other.__keys__()


class _ScheduleParser:
    """Class used to parse schedules in IDF files."""

    @staticmethod
    def get_interval_day_ep_schedule_values(epbunch) -> np.ndarray:
        """Get values for Schedule:Day:Interval.

        Args:
            epbunch (EpBunch): The schedule EpBunch object.
        """
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
        _, _, numeric_type, _ = _ScheduleParser.get_schedule_type_limits_data(epbunch)
        if numeric_type.strip().lower() == "discrete":
            hourly_values = hourly_values.astype(int)

        return hourly_values

    @staticmethod
    def get_hourly_day_ep_schedule_values(epbunch):
        """Get values for Schedule:Day:Hourly.

        Args:
            epbunch (EpBunch): The schedule EpBunch object.
        """
        return np.array(epbunch.fieldvalues[3:])

    @staticmethod
    def get_compact_weekly_ep_schedule_values(
        epbunch, start_date, index=None, strict=False
    ) -> np.ndarray:
        """Get values for schedule:week:compact.

        Args:
            strict:
            epbunch (EpBunch): the name of the schedule
            start_date:
            index:
        """
        if index is None:
            idx = pd.date_range(start=start_date, periods=168, freq="1H")
            slicer_ = pd.Series([False] * (len(idx)), index=idx)
        else:
            slicer_ = pd.Series([False] * (len(index)), index=index)

        weekly_schedules = pd.Series([0] * len(slicer_), index=slicer_.index)
        # update last day of schedule

        num_of_daily_schedules = int(len(epbunch.fieldvalues[2:]) / 2)

        for i in range(num_of_daily_schedules):
            day_type = epbunch["DayType_List_{}".format(i + 1)].lower()
            # This field can optionally contain the prefix “For”
            how = _ScheduleParser._field_set(
                epbunch, day_type.strip("for: "), start_date, slicer_, strict
            )
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
                        day.loc[:] = _ScheduleParser.get_schedule_values(
                            sched_epbunch=ref, start_date=start_date, strict=strict
                        )
                        days.append(day)
                new = pd.concat(days)
                slicer_.update(pd.Series([True] * len(new.index), index=new.index))
                slicer_ = slicer_.apply(lambda x: x is True)
                weekly_schedules.update(new)
            else:
                return weekly_schedules.values

        return weekly_schedules.values

    @staticmethod
    def get_daily_weekly_ep_schedule_values(epbunch, start_date, strict) -> np.ndarray:
        """Get values for schedule:week:daily.

        Args:
            strict:
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
            h = _ScheduleParser.get_schedule_values(
                sched_epbunch=ref, start_date=start_date, strict=strict
            )
            hourly_values.append(h)
        hourly_values = np.array(hourly_values)
        # shift days earlier by self.startDayOfTheWeek
        hourly_values = np.roll(hourly_values, -start_date.weekday(), axis=0)

        return hourly_values.ravel()

    @staticmethod
    def get_list_day_ep_schedule_values(epbunch, start_date) -> np.ndarray:
        """Get values for schedule:day:list.

        Args:
            start_date:
            epbunch (EpBunch): The schedule epbunch object.
        """
        freq = int(epbunch["Minutes_per_Item"])  # Frequency of the values
        num_values = epbunch.fieldvalues[5:]  # List of values
        method = epbunch["Interpolate_to_Timestep"]  # How to resample

        # fill a list of available values and pad with zeros (this is safer
        # but should not occur)
        all_values = np.arange(int(24 * 60 / freq))
        for i in all_values:
            try:
                all_values[i] = num_values[i]
            except Exception:
                all_values[i] = 0
        # create a fake index to help us with the resampling
        index = pd.date_range(
            start=start_date, periods=(24 * 60) / freq, freq="{}T".format(freq)
        )
        series = pd.Series(all_values, index=index)

        # resample series to hourly values and apply resampler function
        series = series.resample("1H").apply(_how(method))

        return series.values

    @staticmethod
    def get_constant_ep_schedule_values(epbunch) -> np.ndarray:
        """Get values for schedule:constant.

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        hourly_values = np.arange(8760)
        value = float(epbunch["Hourly_Value"])
        for hour in hourly_values:
            hourly_values[hour] = value
        _, _, numeric_type, _ = _ScheduleParser.get_schedule_type_limits_data(epbunch)
        if numeric_type.strip().lower() == "discrete":
            hourly_values = hourly_values.astype(int)

        return hourly_values

    @staticmethod
    def get_file_ep_schedule_values(epbunch) -> np.ndarray:
        """Get values for schedule:file.

        Args:
            epbunch (EpBunch): The schedule epbunch object.
        """
        filename = epbunch["File_Name"]
        column = epbunch["Column_Number"]
        rows = epbunch["Rows_to_Skip_at_Top"]
        # hours = epbunch["Number_of_Hours_of_Data"]
        sep = epbunch["Column_Separator"]
        # interp = epbunch["Interpolate_to_Timestep"]

        file = epbunch.theidf.simulation_dir.files(filename)[0]

        delimeter = _separator(sep)
        skip_rows = int(rows) - 1  # We want to keep the column
        col = [int(column) - 1]  # zero-based
        epbunch = pd.read_csv(
            file, delimiter=delimeter, skiprows=skip_rows, usecols=col
        )

        return epbunch.iloc[:, 0].values

    @staticmethod
    def get_compact_ep_schedule_values(epbunch, start_date, strict) -> np.ndarray:
        """Get values for schedule:compact.

        Args:
            strict:
            start_date:
            epbunch (EpBunch): The schedule epbunch object.
        """
        field_sets = ["through", "for", "interpolate", "until", "value"]
        fields = epbunch.fieldvalues[3:]

        index = pd.date_range(start=start_date, periods=8760, freq="H")
        zeros = np.zeros(len(index))

        slicer_ = pd.Series([False] * len(index), index=index)
        series = pd.Series(zeros, index=index)

        from_day = start_date
        ep_from_day = datetime(start_date.year, 1, 1)
        from_time = "00:00"
        how_interpolate = None
        for field in fields:
            if any([spe in field.lower() for spe in field_sets]):
                f_set, hour, minute, value = _ScheduleParser._field_interpreter(
                    field, epbunch.Name
                )

                if f_set.lower() == "through":
                    # main condition. All sub-conditions must obey a
                    # `Through` condition

                    # First, initialize the slice (all False for now)
                    through_conditions = _ScheduleParser._invalidate_condition(series)

                    # reset from_time
                    from_time = "00:00"

                    # Prepare ep_to_day variable
                    ep_to_day = _ScheduleParser._date_field_interpretation(
                        value, start_date
                    ) + timedelta(days=1)

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

                    for_condition = _ScheduleParser._invalidate_condition(series)
                    fors = value.split()
                    if len(fors) > 1:
                        # if multiple `For`. eg.: For: Weekends Holidays,
                        # Combine all conditions
                        for value in fors:
                            if value.lower() == "allotherdays":
                                # Apply condition to slice
                                how = _ScheduleParser._field_set(
                                    epbunch, value, start_date, slicer_, strict
                                )
                                # Reset for condition
                                for_condition = how
                            else:
                                how = _ScheduleParser._field_set(
                                    epbunch, value, start_date, slicer_, strict
                                )
                                if how is not None:
                                    for_condition.loc[how] = True
                    elif value.lower() == "allotherdays":
                        # Apply condition to slice
                        how = _ScheduleParser._field_set(
                            epbunch, value, start_date, slicer_, strict
                        )
                        # Reset for condition
                        for_condition = how
                    else:
                        # Apply condition to slice
                        how = _ScheduleParser._field_set(
                            epbunch, value, start_date, slicer_, strict
                        )
                        for_condition.loc[how] = True

                    # Combine the for_condition with all_conditions
                    all_conditions = through_conditions & for_condition

                    # update in memory slice
                    # self.sliced_day_.loc[all_conditions] = True
                elif "interpolate" in f_set.lower():
                    # we need to upsample to series to 8760 * 60 values
                    new_idx = pd.date_range(
                        start=start_date, periods=525600, closed="left", freq="T"
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
                    until_condition = _ScheduleParser._invalidate_condition(series)
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

    @classmethod
    def get_yearly_ep_schedule_values(cls, epbunch, start_date, strict) -> np.ndarray:
        """Get values for schedule:year.

        Args:
            strict:
            start_date (datetime):
            epbunch (EpBunch): the schedule epbunch.
        """
        # first week
        year = start_date.year
        idx = pd.date_range(start=start_date, periods=8760, freq="1H")
        hourly_values = pd.Series([0] * 8760, index=idx)

        # generate weekly schedules
        num_of_weekly_schedules = int(len(epbunch.fieldvalues[3:]) / 5)

        for i in range(num_of_weekly_schedules):
            ref = epbunch.get_referenced_object("ScheduleWeek_Name_{}".format(i + 1))

            start_month = getattr(epbunch, "Start_Month_{}".format(i + 1))
            end_month = getattr(epbunch, "End_Month_{}".format(i + 1))
            start_day = getattr(epbunch, "Start_Day_{}".format(i + 1))
            end_day = getattr(epbunch, "End_Day_{}".format(i + 1))

            start = datetime.strptime(
                "{}/{}/{}".format(year, start_month, start_day), "%Y/%m/%d"
            )
            end = datetime.strptime(
                "{}/{}/{}".format(year, end_month, end_day), "%Y/%m/%d"
            )
            days = (end - start).days + 1

            end_date = start_date + timedelta(days=days) + timedelta(hours=23)
            how = pd.IndexSlice[start_date:end_date]

            weeks = []
            for name, week in hourly_values.loc[how].groupby(pd.Grouper(freq="168H")):
                if not week.empty:
                    try:
                        week.loc[:] = cls.get_schedule_values(
                            sched_epbunch=ref,
                            start_date=week.index[0],
                            index=week.index,
                            strict=strict,
                        )
                    except ValueError:
                        week.loc[:] = cls.get_schedule_values(
                            sched_epbunch=ref, start_date=week.index[0], strict=strict
                        )[0 : len(week)]
                    finally:
                        weeks.append(week)
            new = pd.concat(weeks)
            hourly_values.update(new)
            start_date += timedelta(days=days)

        return hourly_values.values

    @staticmethod
    def get_schedule_values(
        sched_epbunch, start_date, index=None, strict=False
    ) -> list:
        """Get schedule values for epbunch.

        Args:
            strict:
            sched_epbunch (EpBunch): the schedule epbunch object
            start_date:
            index:
        """
        cls = _ScheduleParser
        sch_type = sched_epbunch.key.upper()

        if sch_type.upper() == "schedule:year".upper():
            hourly_values = cls.get_yearly_ep_schedule_values(
                sched_epbunch, start_date, strict
            )
        elif sch_type.upper() == "schedule:day:interval".upper():
            hourly_values = cls.get_interval_day_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:day:hourly".upper():
            hourly_values = cls.get_hourly_day_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:day:list".upper():
            hourly_values = cls.get_list_day_ep_schedule_values(
                sched_epbunch, start_date
            )
        elif sch_type.upper() == "schedule:week:compact".upper():
            hourly_values = cls.get_compact_weekly_ep_schedule_values(
                sched_epbunch, start_date, index, strict
            )
        elif sch_type.upper() == "schedule:week:daily".upper():
            hourly_values = cls.get_daily_weekly_ep_schedule_values(
                sched_epbunch, start_date, strict
            )
        elif sch_type.upper() == "schedule:constant".upper():
            hourly_values = cls.get_constant_ep_schedule_values(sched_epbunch)
        elif sch_type.upper() == "schedule:compact".upper():
            hourly_values = cls.get_compact_ep_schedule_values(
                sched_epbunch, start_date, strict
            )
        elif sch_type.upper() == "schedule:file".upper():
            hourly_values = cls.get_file_ep_schedule_values(sched_epbunch)
        else:
            log(
                "Archetypal does not currently support schedules of type "
                '"{}"'.format(sch_type),
                lg.WARNING,
            )
            hourly_values = []

        return list(hourly_values)

    @staticmethod
    def _field_interpreter(field, name):
        """Deal with a Field-Set (Through, For, Interpolate, # Until, Value).

        Args:
            name:
            field:

        Returns:
            string: the parsed string
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
                    'that is not understood: "{field}"'.format(sch=name, field=field)
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
                    'that is not understood: "{field}"'.format(sch=name, field=field)
                )
                raise NotImplementedError(msg)
        elif "interpolate" in field.lower():
            msg = (
                'The schedule "{sch}" contains sub-hourly values ('
                'Field-Set="{field}"). The average over the hour is '
                "taken".format(sch=name, field=field)
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
                except Exception:
                    f_set = "until"
                    hour, minute = field.split(":")
                    hour = hour[-2:].strip()
                    minute = minute.strip()
                    value = None
            else:
                msg = (
                    'The schedule "{sch}" contains a Field '
                    'that is not understood: "{field}"'.format(sch=name, field=field)
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
                    'that is not understood: "{field}"'.format(sch=name, field=field)
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
    def _invalidate_condition(series):
        index = series.index
        periods = len(series)
        return pd.Series([False] * periods, index=index)

    @staticmethod
    def get_schedule_type_limits_data(epbunch):
        """Return schedule type limits info for epbunch."""
        try:
            schedule_limit_name = epbunch.Schedule_Type_Limits_Name
        except Exception:
            # this schedule is probably a 'Schedule:Week:Daily' which does
            # not have a Schedule_Type_Limits_Name field
            return "", "", "", ""
        else:
            (
                lower_limit,
                upper_limit,
                numeric_type,
                unit_type,
            ) = epbunch.theidf.get_schedule_type_limits_data_by_name(
                schedule_limit_name
            )

            return lower_limit, upper_limit, numeric_type, unit_type

    @staticmethod
    def _field_set(schedule_epbunch, field, start_date, slicer_=None, strict=False):
        """Return the proper slicer depending on the _field_set value.

        Available values are: Weekdays, Weekends, Holidays, Alldays,
        SummerDesignDay, WinterDesignDay, Sunday, Monday, Tuesday, Wednesday,
        Thursday, Friday, Saturday, CustomDay1, CustomDay2, AllOtherDays

        Args:
            start_date:
            strict:
            schedule_epbunch:
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
            # return all days := equivalent to .loc[:]
            return pd.IndexSlice[:]
        elif field.lower() == "allotherdays":
            # return unused days (including special days). Uses the global
            # variable `slicer_`
            import operator

            if slicer_ is not None:
                return _conjunction(
                    *[
                        _ScheduleParser.special_day(
                            schedule_epbunch, field, slicer_, strict, start_date
                        ),
                        ~slicer_,
                    ],
                    logical=operator.or_,
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
            # return _ScheduleParser.design_day(
            #     schedule_epbunch, field, slicer_, start_date, strict
            # )
            return None
        elif field.lower() == "winterdesignday":
            # return _ScheduleParser.design_day(
            #     schedule_epbunch, field, slicer_, start_date, strict
            # )
            return None
        elif field.lower() == "holiday" or field.lower() == "holidays":
            field = "holiday"
            return _ScheduleParser.special_day(
                schedule_epbunch, field, slicer_, strict, start_date
            )
        elif not strict:
            # If not strict, ignore missing field-sets such as CustomDay1
            return lambda x: x < 0
        else:
            raise NotImplementedError(
                f"Archetypal does not yet support The Field_set '{field}'"
            )

    @staticmethod
    def _date_field_interpretation(field, start_date):
        """Date Field Interpretation.

        Info:
            See EnergyPlus documentation for more details: 1.6.8.1.2 Field:
            Start Date (Table 1.4: Date Field Interpretation)

        Args:
            start_date:
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
            except Exception:
                pass
            else:
                date = datetime(start_date.year, date.month, date.day)
        if date is None:
            # if the defined formats did not work, try the fancy parse
            try:
                date = _ScheduleParser._parse_fancy_string(field, start_date)
            except Exception as e:
                msg = (
                    f"the schedule contains a "
                    f"Field that is not understood: '{field}'"
                )
                raise ValueError(msg, e)
            else:
                return date
        else:
            return date

    @staticmethod
    def _parse_fancy_string(field, start_date):
        """Parse cases such as `3rd Monday in February` or `Last Weekday In Month`.

        Args:
            start_date:
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

        c = calendar.Calendar(firstweekday=start_date.weekday())
        monthcal = c.monthdatescalendar(start_date.year, month)

        # iterate though the month and get the nth weekday
        date = [
            day
            for week in monthcal
            for day in week
            if day.weekday() == dayofweek and day.month == month
        ][nth]
        return datetime(date.year, date.month, date.day)

    @staticmethod
    def special_day(schedule_epbunch, field, slicer_, strict, start_date):
        """Try to get the RunPeriodControl:SpecialDays for the corresponding DayType.

        Args:
            start_date:
            strict:
            field:
            slicer_:
        """
        sp_slicer_ = slicer_.copy()
        sp_slicer_.loc[:] = False
        special_day_types = ["holiday", "customday1", "customday2"]

        dds = schedule_epbunch.theidf.idfobjects["RunPeriodControl:SpecialDays".upper()]
        dd = [
            dd
            for dd in dds
            if dd.Special_Day_Type.lower() == field
            or dd.Special_Day_Type.lower() in special_day_types
        ]
        if len(dd) > 0:
            for dd in dd:
                # can have more than one special day types
                field = dd.Start_Date
                special_day_start_date = _ScheduleParser._date_field_interpretation(
                    field, start_date
                )
                duration = int(dd.Duration)
                to_date = (
                    special_day_start_date
                    + timedelta(days=duration)
                    + timedelta(hours=-1)
                )

                sp_slicer_.loc[special_day_start_date:to_date] = True
            return sp_slicer_
        elif not strict:
            return sp_slicer_
        else:
            msg = (
                'Could not find a "SizingPeriod:DesignDay" object '
                'needed for schedule with Day Type "{}"'.format(field.capitalize())
            )
            raise ValueError(msg)

    @staticmethod
    def design_day(schedule_epbunch, field, slicer_, start_date, strict):
        """Try to get the SizingPeriod:DesignDay for the corresponding Day Type.

        Args:
            strict:
            start_date:
            schedule_epbunch:
            field:
            slicer_:
        """
        sp_slicer_ = slicer_.copy()
        sp_slicer_.loc[:] = False
        dds = schedule_epbunch.theidf.idfobjects["SizingPeriod:DesignDay".upper()]
        dd = [dd for dd in dds if dd.Day_Type.lower() == field]
        if len(dd) > 0:
            for dd in dd:
                # should have found only one design day matching the Day Type
                month = dd.Month
                day = dd.Day_of_Month
                data = str(month) + "/" + str(day)
                ep_start_date = _ScheduleParser._date_field_interpretation(
                    data, start_date
                )
                ep_orig = datetime(start_date.year, 1, 1)
                days_to_speciald = (ep_start_date - ep_orig).days
                duration = 1  # Duration of 1 day
                from_date = start_date + timedelta(days=days_to_speciald)
                to_date = from_date + timedelta(days=duration) + timedelta(hours=-1)

                sp_slicer_.loc[from_date:to_date] = True
            return sp_slicer_
        elif not strict:
            return sp_slicer_
        else:
            msg = (
                f"Could not find a 'SizingPeriod:DesignDay' object "
                f"needed for schedule with Day Type '{field.capitalize()}'"
            )
            raise ValueError(msg)
            data = [dd[0].Month, dd[0].Day_of_Month]
            date = "/".join([str(item).zfill(2) for item in data])
            date = _ScheduleParser._date_field_interpretation(date, start_date)
            return lambda x: x.index == date


class Schedule:
    """Class handling any EnergyPlus schedule object."""

    def __init__(
        self,
        Name,
        start_day_of_the_week=0,
        strict=False,
        Type=None,
        Values=None,
        **kwargs,
    ):
        """Initialize object.

        Args:
            Name (str): The schedule name in the idf model.
            start_day_of_the_week (int): 0-based day of week (Monday=0). Default is
                None which looks for the start day in the IDF model.
            strict (bool): if True, schedules that have the Field-Sets such as
                Holidays and CustomDay will raise an error if they are absent
                from the IDF file. If False, any missing qualifiers will be
                ignored.
            Type (str, ScheduleTypeLimits): This field contains a reference to the
                Schedule Type Limits object. If found in a list of Schedule Type
                Limits (see above), then the restrictions from the referenced
                object will be used to validate the current field values. If None,
                no validation will occur.
            Values (ndarray): A 24 or 8760 list of schedule values.
            **kwargs:
        """
        try:
            super(Schedule, self).__init__(Name, **kwargs)
        except Exception:
            pass  # todo: make this more robust
        self.Name = Name
        self.strict = strict
        self.startDayOfTheWeek = start_day_of_the_week
        self.year = get_year_for_first_weekday(self.startDayOfTheWeek)
        self.Values = Values
        self.Type = Type

    @property
    def Type(self):
        """Get or set the schedule type limits object. Can be None."""
        return self._schedule_type_limits

    @Type.setter
    def Type(self, value):
        if isinstance(value, str):
            if "fraction" in value.lower():
                value = ScheduleTypeLimits("Fraction", 0, 1)
            elif value.lower() == "temperature":
                value = ScheduleTypeLimits("Temperature", -100, 100)
            elif value.lower() == "on/off":
                value = ScheduleTypeLimits("On/Off", 0, 1, "Discrete", "availability")
            else:
                value = ScheduleTypeLimits("Fraction", 0, 1)
                log(
                    f"'{value}' is not a known ScheduleTypeLimits for "
                    f"{self.Name}. Please instantiate the object before "
                    f"passing as the 'Type' parameter.",
                    level=lg.WARNING,
                )
            assert isinstance(value, ScheduleTypeLimits), value
        self._schedule_type_limits = value

    @property
    def Values(self):
        """Get or set the list of schedule values."""
        return self._values

    @Values.setter
    def Values(self, value):
        if isinstance(value, np.ndarray):
            assert value.ndim == 1, value.ndim
            value = value.tolist()
        self._values = validators.iterable(value, allow_empty=True)

    @property
    def Name(self):
        """Get or set the name of the schedule."""
        return self._name

    @Name.setter
    def Name(self, value):
        self._name = value

    @classmethod
    def from_values(cls, Name, Values, Type="Fraction", **kwargs):
        """Create a Schedule from a list of Values.

        Args:
            Name:
            Values:
            Type:
            **kwargs:
        """
        return cls(Name=Name, Values=Values, Type="Fraction", **kwargs)

    @classmethod
    def from_epbunch(cls, epbunch, strict=False, Type=None, **kwargs):
        """Create a Schedule from an epbunch.

        Args:
            epbunch:
            strict:
            **kwargs:

        """
        if Type is None:
            try:
                type_limit_ep = epbunch.get_referenced_object(
                    "Schedule_Type_Limits_Name"
                )
                Type = ScheduleTypeLimits.from_epbunch(type_limit_ep)
            except (BadEPFieldError, AttributeError):
                pass
        name = epbunch.Name
        start_day_of_the_week = epbunch.theidf.day_of_week_for_start_day
        start_date = datetime(get_year_for_first_weekday(start_day_of_the_week), 1, 1)

        schedule = cls(
            Name=kwargs.pop("Name", name),
            epbunch=epbunch,
            start_day_of_the_week=kwargs.pop(
                "start_day_of_the_week", start_day_of_the_week
            ),
            Type=Type,
            DataSource=kwargs.pop("DataSource", epbunch.theidf.name),
            Values=np.array(
                _ScheduleParser.get_schedule_values(
                    epbunch, start_date=start_date, strict=strict
                )
            ),
            **kwargs,
        )
        return schedule

    @classmethod
    def constant_schedule(cls, value=1, Name="AlwaysOn", Type="Fraction", **kwargs):
        """Initialize a schedule with a constant value for the whole year.

        Defaults to a schedule with a value of 1, named 'AlwaysOn'.

        Args:
            value (float, optional): The value for the constant schedule.
                Defaults to 1.
            Name (str, optional): The name of the schedule. Defaults to Always
                On.
            **kwargs:
        """
        return cls.from_values(
            Name=Name,
            Values=np.ones((8760,)) * value,
            **kwargs,
        )

    @property
    def all_values(self) -> np.ndarray:
        """Return numpy array of schedule Values."""
        return np.array(self._values)

    @all_values.setter
    def all_values(self, value):
        self._values = validators.iterable(value, maximum_length=8760)

    @property
    def max(self):
        """Get the maximum value of the schedule."""
        return max(self.all_values)

    @property
    def min(self):
        """Get the minimum value of the schedule."""
        return min(self.all_values)

    @property
    def mean(self):
        """Get the mean value of the schedule."""
        return np.average(self.all_values)

    @property
    def series(self):
        """Return an :class:`EnergySeries`."""
        index = pd.date_range(
            start=self.startDate, periods=self.all_values.size, freq="1H"
        )
        return EnergySeries(self.all_values, index=index, name=self.Name)

    @staticmethod
    def get_schedule_type_limits_name(epbunch):
        """Return the Schedule Type Limits name associated to this schedule."""
        try:
            schedule_limit_name = epbunch.Schedule_Type_Limits_Name
        except Exception:
            return "unknown"
        else:
            return schedule_limit_name

    @property
    def startDate(self):
        """Get the start date of the schedule. Satisfies `startDayOfTheWeek`."""
        year = get_year_for_first_weekday(self.startDayOfTheWeek)
        return datetime(year, 1, 1)

    def plot(self, slice=None, **kwargs):
        """Plot the schedule. Implements the .loc accessor on the series object.

        Examples:
            >>> from archetypal import IDF
            >>> idf = IDF()
            >>> epbunch = idf.schedules_dict["NECB-A-Thermostat Setpoint-Heating"]
            >>> s = Schedule.from_epbunch(epbunch)
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
        """Plot the carpet plot of the schedule."""
        return EnergySeries(self.series, name=self.Name).plot2d(**kwargs)

    plot2d.__doc__ += EnergySeries.plot2d.__doc__

    def to_year_week_day(self):
        """Convert to three-tuple epbunch given an idf model.

        Returns 'Schedule:Year', 'Schedule:Week:Daily' and 'Schedule:Day:Hourly'
        representations.

        Returns:
            3-element tuple containing

            - **yearly** (*Schedule*): The yearly schedule object
            - **weekly** (*list of Schedule*): The list of weekly schedule
              objects
            - **daily** (*list of Schedule*):The list of daily schedule objects
        """
        from archetypal.template.schedule import (
            DaySchedule,
            WeekSchedule,
            YearSchedule,
            YearSchedulePart,
        )

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
            ep_day = DaySchedule(
                Name=name, Type=self.Type, Values=[unique_day[i] for i in range(24)]
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
                for key, ep_day in zip(dict_day, ep_days):
                    if (day_of_week == dict_day[key]).all():
                        dict_week[week_id]["day_{}".format(day)] = ep_day

        # Create idf_objects for schedule:week:daily

        # Create ep_weeks list and iterate over dict_week
        ep_weeks = {}
        for week_id in dict_week:
            ep_week = WeekSchedule(
                Name=week_id,
                Days=[
                    dict_week[week_id]["day_{}".format(day_num)]
                    for day_num in c.iterweekdays()
                ],
            )
            ep_weeks[week_id] = ep_week

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
            blocks[i] = YearSchedulePart(
                FromDay=from_date.day,
                FromMonth=from_date.month,
                ToDay=to_date.day,
                ToMonth=to_date.month,
                Schedule=ep_weeks[week_id],
            )
            from_date = to_date + timedelta(hours=1)

            # If this is the last block, force end of year
            if i == len(bincount) - 1:
                blocks[i].ToDay = 31
                blocks[i].ToMonth = 12

        ep_year = YearSchedule(self.Name, Type=self.Type, Parts=list(blocks.values()))

        return ep_year, list(ep_weeks.values()), ep_days

    def __len__(self):
        """Get the length of all values of the schedule."""
        return len(self.all_values)

    def __add__(self, other):
        """Add self and other."""
        if isinstance(other, Schedule):
            return self.all_values + other.all_values
        elif isinstance(other, list):
            return self.all_values + other
        else:
            raise NotImplementedError

    def __sub__(self, other):
        """Subtract self and other."""
        if isinstance(other, Schedule):
            return self.all_values - other.all_values
        elif isinstance(other, list):
            return self.all_values - other
        else:
            raise NotImplementedError

    def __mul__(self, other):
        """Multiply self with other."""
        if isinstance(other, Schedule):
            return self.all_values * other.all_values
        elif isinstance(other, list):
            return self.all_values * other
        else:
            raise NotImplementedError

    def _repr_svg_(self):
        """SVG representation for iPython notebook."""
        fig, ax = self.series.plot2d(cmap="Greys", show=False, fig_width=5, dpi=72)
        f = io.BytesIO()
        fig.savefig(f, format="svg")
        return f.getvalue()

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

        new_obj = self.__class__(name, value=new_values)

        return new_obj


def _conjunction(*conditions, logical=np.logical_and):
    return functools.reduce(logical, conditions)


def _separator(sep):
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
    if how.lower() == "average":
        return "mean"
    elif how.lower() == "linear":
        return "interpolate"
    elif how.lower() == "no":
        return "max"
    else:
        return "max"


def get_year_for_first_weekday(weekday=0):
    """Get the year that starts on 'weekday', eg. Monday=0."""
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
