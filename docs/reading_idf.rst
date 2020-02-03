Reading and running IDF files
=============================

`archetypal` is packed up with some built-in workflows to read, edit and run EnergyPlus files.

Reading
-------

To read an IDF file, simply call :meth:`~archetypal.idfclass.load_idf` with the path name. For example:

.. code-block:: python

    >>> from archetypal import get_eplus_dirs, load_idf
    >>> eplus_dir = get_eplus_dirs("9-2-0")  # Getting EnergyPlus install path
    >>> eplus_file = eplus_dir / "ExampleFiles" / "BasicsFiles" / "AdultEducationCenter.idf"  # Model path
    >>> idf = load_idf(eplus_file)  # IDF load

You can optionally pass the weather file path as well:

.. code-block:: python

    >>> weather = eplus_dir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"  # Weather file path
    >>> idf = load_idf(eplus_file, weather)  # IDF load

Editing
-------

Editing IDF files is based on the :ref:`eppy` package. The :class:`~archetypal.idfclass.IDF` object that the
:meth:`~archetypal.idfclass.load_idf` method returns exposes the EnergyPlus objects that make up the IDF file.

.. hint:: Pre-sets

    EnergyPlus outputs can be defined quickly using the :class:`archetypal.idfclass.OutputPrep` class. This class
    and its methods handles adding predefined or custom output EnergyPlus objects to an IDF object. For example, the
    idf object created above can be modified by adding a basic set of outputs:

    .. code-block:: python

        >>> from archetypal import OutputPrep
        >>> OutputPrep(idf=idf, save=True).add_basics()

    See :class:`~archetypal.idfclass.OutputPrep` for more details on all possible methods.


Running
-------

Running an EnerguPlus file can be done in two ways. The first way is to call the :meth:`archetypal.idfclass.run_eplus`
function with the path of the IDF file and the path of the weather file. The second method is to call the
:meth:`~archetypal.idfclass.IDF.run_eplus` method on an :class:`~archetypal.idfclass.IDF` object that has been
previously read. In both cases, users can also specify run options as well as output options. For example, instead of
creating an OutputPrep object, one can specify custom outputs in the :attr:`archetypal.idfclass.run_eplus.prep_outputs`
attribute. These outputs will be appended to the IDF file before the simulation is run.

For the same IDF object read above, the following:

.. code-block:: python

    >>> idf.run_eplus(weather_file, **other_options)

is equivalent to:

.. code-block:: python

    >>> idf_path = "path/to/idf_file"
    >>> run_eplus(idf_path, weather_file, **other_options)

.. hint:: Caching system.

    When running EnergyPlus simulations, a caching system can be activated to reduce the number of calls to the
    EnergyPlus executable. This can be helpful when `archetypal` is called many times. This caching system will save
    simulation results in a folder identified by a unique identifier. This identifier is based on the content of the IDF
    file, as well as the various :meth:`~archetypal.idfclass.run_eplus` options. If caching is activated, then
    subsequent calls to the :meth:`~archetypal.idfclass.run_eplus` method will return the cached results.

    The caching system is activated by calling the :meth:`archetypal.utils.config` method, which can also be used to
    set a series of package-wide options. ``config`` would typically be put at the top of a python script:

    .. code-block:: python

        >>> from archetypal import config
        >>> config(use_cache=True)