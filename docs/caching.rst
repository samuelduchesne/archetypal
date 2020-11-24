Caching
=======

Archetypal features a caching api aimed at accelerating reproducible workflows using EnergyPlus simulations by reducing
unnecessary calls to the EnergyPlus executable or transitioning programs. Concretely, caching an IDF model means that,
for instance, if an older version model (less than 9.2) is ran, archetypal will transition a copy of that file to
version 9.2 (making a copy beforehand) and run the simulation with the matching EnergyPlus executable. The next time the
:func:`~archetypal.idfclass.idf.IDF` constructor is called, the cached
(transitioned) file will be readily available and used; This helps to save time especially with reproducible workflows
since transitioning files can take a while to complete.

As for simulation results, after :func:`archetypal.idfclass.idf.IDF.simulate` is called, the EnergyPlus outputs (.csv,
sqlite, mtd, .mdd, etc.) are cached in a folder structure than is identified according to the simulation parameters;
those parameters include the content of the IDF file itself (if the file has changed, a new simulation is required),
whether an annual or design day simulation is executed, etc. This means that if simulate is called a second time (let us
say after restarting a Jupyter Notebook kernel), the simulate will bypass the EnergyPlus executable and retrieve the
cached simulation results instead. This has two advantages, the first one being a quicker workflow and the second one
making sure that whatever `IDF.simulation_files` returns fits the parameters used with the executable. Let us use this
in a real world example. First, caching is enabled using the `config` method:

Enabling caching
----------------

Caching is enabled by passing the `use_cache=True` attribute to the :func:`archetypal.utils.config` method. The
configuration of archetypal settings are not persistent and must be called whenever a python session is started. It is
recommended to put the `config` method at the beginning of a script or in the first cells of a Jupyter Notebook
(after the import statements).

.. code-block:: python

    from archetypal import IDF, config, get_eplus_dirs, settings
    config(use_cache=True, log_console=True)

Example
-------

In a Jupyter Notebook, one would typically do the following:

.. code-block:: python

    idf = IDF(
        get_eplus_dirs(settings.as_version) / "ExampleFiles" / "BasicsFiles/AdultEducationCenter.idf",
        epw=get_eplus_dirs(settings.as_version) / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
        design_day=True,
        annual=False,
        expandobjects=True,
        prep_outputs=True,
    )

If the file would be an older version, archetypal is going to transition the file to EnergyPlus 9.2 (or any other
version specified with the as_version parameter) and execute EnergyPlus for the `design_day` only.

The command bellow yields a list of output files. These will be located
inside a cache folder specified by the settings.cache_folder variable (this folder path can be changed using the config
method).

.. code-block:: python

    >>> idf.simulate().simulation_files
    [Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\AdultEducationCenter.idf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.audit'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.bnd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.dxf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.eio'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.end'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.err'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.eso'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.expidf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.mdd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.mtd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.mtr'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.rdd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.shd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431bout.sql'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431btbl.csv'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\b07dbcb49b54298c5f64fe5ee730431btbl.htm'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\runargs.json'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\sqlite.err'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\b07dbcb49b54298c5f64fe5ee730431b\\USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw')]]

Now, if the command above is modified with `annual=True` and set `design_day=False`, then `idf.simulate().simulation_files`
should return the annual simulation results (which do not exist yet).

.. code-block:: python

    >>> idf.simulate(annual=True, design_day=False).simulation_files

Now, since the original IDF file (the version 8.9 one) has not changed, archetypal is going to look for the transitioned
file that resides in the cache folder and use that one instead of retransitioning the original file a second time. On
the other hand, since the parameters of `simulate()` have changed (annual instead of design_day), it is going to execute
EnergyPlus using the annual method and return the annual results (see that the second-level folder id has changed from
b07dbcb49b54298c5f64fe5ee730431b to 1cc202748b6c3c2431d203ce90e4d081; *these ids may be different on your computer*):

.. code-block:: python

    [Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.audit'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.bnd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.dxf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.eio'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.end'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.err'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.eso'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.expidf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.mdd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.mtd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.mtr'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.rdd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.shd'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081out.sql'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081tbl.csv'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\1cc202748b6c3c2431d203ce90e4d081tbl.htm'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\AdultEducationCenter.idf'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\runargs.json'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\sqlite.err'),
    Path('cache\\b0b749f1c11f28b3d24d1d8978d1140e\\1cc202748b6c3c2431d203ce90e4d081\\USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw')]

If we were to rerun the first code block (annual simulation) then it would return the cached results instantly from
the cache:

.. code-block:: shell

    Successfully parsed cached idf run in 0.00 seconds

Profiling this simple script shows an 8x speedup.