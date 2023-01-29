Reading and running IDF files
=============================

`archetypal` is packed up with some built-in workflows to read, edit and run EnergyPlus files.

Reading
-------

To read an IDF file, simply call :class:`~archetypal.idfclass.idf.IDF` with the path name. For example:

.. code-block:: python

    >>> from archetypal import IDF
    >>> idf = IDF("in.idf)  # in.idf must in the current directory.

You can also load on of the example files by name.

.. code-block:: python

    >>> from archetypal import IDF
    >>> idf = IDF.from_example_files("AdultEducationCenter.idf")

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

        >>> idf.outputs.add_basics().apply()

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

    >>> idf.simulate(epw=weather)


.. hint:: Caching system.

    When running EnergyPlus simulations, a caching system is activated to reduce the number of calls to the
    EnergyPlus executable or to reduce time spent on I/O operations such as in :attr:`~archetypal.idfclass.idf.IDF.sql` and
    :func:`~archetypal.idfclass.idf.IDF.htm()` which parse the simulation results. This caching system will save
    simulation results in a folder identified by a unique identifier. This identifier is based on the content of the IDF
    file, as well as EnergyPlus simulate options. This system works by invalidating any dependant attributes when
    independent attributes change.