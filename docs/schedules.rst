.. currentmodule:: archetypal

Schedules
=========

*archetypal* implements the schedules interpretation native to EnergyPlus.

Reading Schedules
-----------------

*archetypal* can read almost any schedules defined in an IDF file using the the command::

    idf = archetypal.load_idf(<idf-file-path>)
    this_schedule = Schedule(idf, sch_name='name')


