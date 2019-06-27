Schedules
=========

*archetypal* can parse schedules native to EnergyPlus Models. In EnergyPlus, there are many ways to define schedules
but sometimes, it is necessary to have a single schedule representation. This is the case for the EnergyPlus to BUI
converter and for the upcoming UMI converter. In both cases, the schedules are defined as a Yearly, Weekly, Daily
schedule object. The Schedule module of *archetypal* handles this conversion.

Reading Schedules
-----------------

*archetypal* can read almost any schedules defined in an IDF file using a few commands. First,

.. code-block:: python

    import archetypal as ar
    idf = ar.load_idf(<idf-file-path>)
    this_schedule = Schedule(sch_name='name', idf=idf)

On can create the year-week-day representation for any schedule object by invoking the
:py:meth:`archetypal.Schedule.to_year_week_day` method:

.. code-block:: python

    this_schedule.to_year_week_day()