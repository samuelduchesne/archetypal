import logging as lg
import os

import eppy.modeleditor

from archetypal import log


class IDF(eppy.modeleditor.IDF):
    """Wrapper over the eppy.modeleditor.IDF class

    """

    def __init__(self, *args, **kwargs):
        super(IDF, self).__init__(*args, **kwargs)
        self.schedules_dict = self.get_all_schedules()

    def add_object(self, ep_object, save=True, **kwargs):
        """Add a new object to an idf file. The function will test if the
        object exists to prevent duplicates.

        Args:
            ep_object (str): the object name to add, eg. 'OUTPUT:METER' (Must
                be in all_caps)
            **kwargs: keyword arguments to pass to other functions.

        Returns:
            eppy.modeleditor.IDF: the IDF object
        """
        # get list of objects
        objs = self.idfobjects[ep_object]  # a list
        # create new object
        new_object = self.newidfobject(ep_object, **kwargs)
        # Check if new object exists in previous list
        # If True, delete the object
        if sum([str(obj).upper() == str(new_object).upper() for obj in
                objs]) > 1:
            log('object "{}" already exists in idf file'.format(ep_object),
                lg.WARNING)
            # Remove the newly created object since the function
            # `idf.newidfobject()` automatically adds it
            self.removeidfobject(new_object)
            if not save:
                return []
        else:
            if save:
                log('object "{}" added to the idf file'.format(ep_object))
                self.save()
            else:
                # return the ep_object
                return new_object

    def get_schedule_type_limits_data_by_name(self, schedule_limit_name):
        """Returns the data for a particular 'ScheduleTypeLimits' object"""
        schedule = self.getobject('ScheduleTypeLimits'.upper(), schedule_limit_name)

        if schedule is not None:
            lower_limit = schedule['Lower_Limit_Value']
            upper_limit = schedule['Upper_Limit_Value']
            numeric_type = schedule['Numeric_Type']
            unit_type = schedule['Unit_Type']

            if schedule['Unit_Type'] == '':
                unit_type = numeric_type

            return lower_limit, upper_limit, numeric_type, unit_type
        else:
            return '', '', '', ''


    def get_schedule_data_by_name(self, sch_name, sch_type=None):
        """Returns the epbunch of a particular schedule name

        Args:
            sch_type:
        """
        if sch_type is None:
            try:
                return self.schedules_dict[sch_name]
            except:
                try:
                    schedules_dict = self.get_all_schedules()
                    return schedules_dict[sch_name]
                except KeyError:
                    raise KeyError('Unable to find schedule "{}" in idf '
                                   'file "{}"'.format(
                        sch_name, self.idfname))
        else:
            return self.getobject(sch_type, sch_name)

    def get_all_schedules(self, yearly_only=False):
        """Returns all schedule ep_objects in a dict with their name as a key

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (dict of eppy.bunch_subclass.EpBunch): the schedules with their
                name as a key
        """
        from archetypal import schedule_types
        if yearly_only:
            schedule_types = ['Schedule:Year'.upper(),
                              'Schedule:Compact'.upper(),
                              'Schedule:Constant'.upper(),
                              'Schedule:File'.upper()]
        scheds = {}
        for sched_type in schedule_types:
            for sched in self.idfobjects[sched_type]:
                try:
                    if sched.key.upper() in schedule_types:
                        scheds[sched.Name] = sched
                except:
                    pass
        return scheds

    def get_used_schedules(self, yearly_only=False):
        """Returns all used schedules

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (list): the schedules names

        """

        used_schedules = []
        from archetypal import schedule_types
        all_schedules = self.get_all_schedules(yearly_only=yearly_only)
        for object_name in self.idfobjects:
            for object in self.idfobjects[object_name]:
                if object.key.upper() not in schedule_types:
                    for fieldvalue in object.fieldvalues:
                        try:
                            if fieldvalue in all_schedules and fieldvalue not \
                                    in used_schedules:
                                used_schedules.append(fieldvalue)
                        except:
                            pass
        return used_schedules

    @property
    def day_of_week_for_start_day(self):
        """Get day of week for start day for the first found RUNPERIOD"""
        import calendar
        day = self.idfobjects["RUNPERIOD"][0]["Day_of_Week_for_Start_Day"]

        if day.lower() == "sunday":
            return calendar.SUNDAY
        elif day.lower() == "monday":
            return calendar.MONDAY
        elif day.lower() == "tuesday":
            return calendar.TUESDAY
        elif day.lower() == "wednesday":
            return calendar.WEDNESDAY
        elif day.lower() == "thursday":
            return calendar.THURSDAY
        elif day.lower() == "friday":
            return calendar.FRIDAY
        elif day.lower() == "saturday":
            return calendar.SATURDAY
        else:
            return 0

    def building_name(self, use_idfname=False):
        if use_idfname:
            return os.path.basename(self.idfname)
        else:
            bld = self.idfobjects["BUILDING"]
            if bld is not None:
                return bld[0].Name
            else:
                return os.path.basename(self.idfname)
