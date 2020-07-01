Schedules
=========

`archetypal` can parse EnergyPlus schedules. In EnergyPlus, there are many ways to define schedules in an IDF file. The
Schedule module defines a class that handles parsing, plotting converting schedules.

Reading Schedules
-----------------

*archetypal* can read almost any schedules defined in an IDF file using a few commands. First,

.. code-block:: python

    >>> import archetypal as ar
    >>> idf = ar.IDF(<idf-file-path>)
    >>> this_schedule = Schedule(Name='name', idf=idf)


Converting Schedules
--------------------

Some tools typically rely on a group of 3 schedules; defined as a Yearly, Weekly, Daily schedule object. This is the
case for the :ref:`IDF to UMI <Converting IDF to UMI>` converter and for the :ref:`IDF to TRNSYS <Converting IDF to BUI>`
converter. The Schedule module of *archetypal* can handle this conversion.

The `year-week-day` representation for any schedule object is invoked with
the :py:meth:`~archetypal.schedule.Schedule.to_year_week_day` method:

.. code-block:: python

    >>> this_schedule.to_year_week_day()

Plotting Schedules
------------------

Schedules can be parsed as :class:`pandas.Series` objects (call the `series` property on a Schedule object) which then
exposes useful methods from the pandas package. For convenience, a wrapper for the plotting method is built-in the
Schedule class. To plot the full annual schedule (or a specific range), simply call the :meth:`archetypal.schedule.Schedule.plot`
method. For example,

.. code-block:: python

    >>> this_schedule.plot(slice=("2018/01/02", "2018/01/03"), drawstyle="steps-post")