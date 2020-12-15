Reading and running IDF files
=============================

`archetypal` is packed up with some built-in workflows to read, edit and run EnergyPlus files.

Reading
-------

To read an IDF file, simply call :class:`~archetypal.idfclass.idf.IDF` with the path name. For example:

.. code-block:: python

    >>> from archetypal import get_eplus_dirs, IDF
    >>> eplus_dir = get_eplus_dirs("9-2-0")  # Getting EnergyPlus install path
    >>> eplus_file = eplus_dir / "ExampleFiles" / "BasicsFiles" / "AdultEducationCenter.idf"  # Model path
    >>> idf = IDF(eplus_file)  # IDF load

You can optionally pass the weather file path as well:

.. code-block:: python

    >>> weather = eplus_dir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"  # Weather file path
    >>> idf = IDF(eplus_file, epw=weather)  # IDF load

Editing
-------

Editing IDF files is based on the :ref:`eppy` package. The :class:`~archetypal.idfclass.idf.IDF` object exposes the
EnergyPlus objects that make up the IDF file. These objects can be edited and new objects can be created. See the `eppy
documentation <https://eppy.readthedocs.io/en/latest/>`_ for more information on how to edit IDF files.

.. hint:: Pre-sets

    EnergyPlus outputs can be quickly defined using the :class:`~archetypal.idfclass.Outputs` class. This class and its
    methods handle adding predefined or custom outputs to an IDF model. An :class:`~archetypal.idfclass.Outputs` is
    instantiated by default in an :class:`~archetypal.idfclass.idf.IDF` model. It accessed with the
    :attr:`~archetypal.idfclass.idf.IDF.outputs` attribute. For example, the idf object created above can be modified by
    adding a basic set of outputs:

    .. code-block:: python

        >>> idf.add_basics().apply()

    One can specify custom outputs by calling :meth:`~archetypal.idfclass.Outputs.add_custom()` with a list of dict
    of the form fieldname:value and then :meth:`~archetypal.idfclass.Outputs.apply()`. These outputs will be
    appended to the IDF model only if :meth:`~archetypal.idfclass.Outputs.apply()` is called. See
    :class:`~archetypal.idfclass.Outputs` for more details on all possible methods.


Running
-------

To run an :class:`~archetypal.idfclass.idf.IDF` model, simply call the :meth:`~archetypal.idfclass.idf.IDF.simulate()` function
on the IDF object. In both cases, users can also specify run options as well as output options.

For the same IDF object above:

.. code-block:: python

    >>> idf.simulate(weather_file=weather)


.. hint:: Caching system.

    When running EnergyPlus simulations, a caching system can be activated to reduce the number of calls to the
    EnergyPlus executable or to reduce time spent on I/O operations such as in :attr:`~archetypal.idfclass.idf.IDF.sql` and
    :func:`~archetypal.idfclass.idf.IDF.htm()` which parse the simulation results. This caching system will save
    simulation results in a folder identified by a unique identifier. This identifier is based on the content of the IDF
    file, as well as EnergyPlus simulate options. This system works by invalidating any dependant attributes when
    independent attributes change.

    The caching system is activated by calling the :meth:`archetypal.utils.config` method (or by setting
    :attr:`settings.use_cache = True`), which can also be used to set a series of package-wide options. ``config`` would
    typically be put at the top of a python script:

    .. code-block:: python

        >>> from archetypal import config
        >>> config(use_cache=True)