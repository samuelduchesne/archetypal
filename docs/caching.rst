Caching
=======

Archetypal features a caching api aimed at accelerating reproducible workflows using EnergyPlus simulations by reducing
unnecessary calls to the EnergyPlus executable or transitioning programs. Concretely, caching an IDF model means that,
for instance, if an older version model (less than 9.2) is ran, archetypal will transition a copy of that file to
version 9.2 (making a copy beforehand) and run the simulation with the matching EnergyPlus executable. The next time the
:func:`archetypal.idfclass.run_eplus` or the :func:`archetypal.idfclass.load_idf` method is called, the cached
(transitioned) file will be readily available and used; This helps to save time especially with reproducible workflows
since transitioning files can take a while to complete.

As for simulation results, after :func:`archetypal.idfclass run_eplus` is called, the EnergyPlus outputs (.csv, sqlite,
mtd, .mdd, etc.) are cached in a folder structure than is identified according to the simulation parameters; those
parameters include the content of the IDF file itself (if the file has changed, a new simulation is required), whether
an annual or design day simulation is executed, etc. This means that if run_eplus is called a second time (let us say
after restarting a Jupyter Notebook kernel), the run_eplus will bypass the EnergyPlus executable and retrieve the cached
simulation results instead. This has two advantages, the first one being a quicker workflow and the second one making
sure that whatever `run_eplus` returns fits the parameters used with the executable. Let us use this in a real world
example. First, caching is enabled using the `config` method:

Enabling caching
----------------

Caching is enabled by passing the `use_cache=True` attribute to the :func:`archetypal.utils.config` method. The
configuration of archetypal settings are not persistent and must be called whenever a python session is started. It is
recommended to put the `config` method at the beginning of a script or in the first cells of a Jupyter Notebook
(after the import statements).

.. code-block:: python

    import archetypal as ar
    ar.config(use_cache=True, log_console=True)

Example
-------

In a Jupyter Notebook, one would typically do the following:

.. code-block:: python

    _, idf, results = ar.run_eplus(
        eplus_file=ar.utils.get_eplus_dirs("8-9-0") / "ExampleFiles" / "BasicsFiles/AdultEducationCenter.idf",
        weather_file=ar.utils.get_eplus_dirs("8-9-0") / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
        design_day=True,
        return_files=True,
        annual=False,
        return_idf=True,
        expandobjects=True,
        prep_outputs=True,
    )

Since the file is a version 8.0 IDF file, archetypal is going to transition the file to EnergyPlus 9.2 (or any other
version specified with the ep_version parameter) and execute EnergyPlus for the `design_day` only.

The command above yields a list of output files thanks to the `return_files=True` parameter. These will be located
inside a cache folder specified by the settings.cache_folder variable (this folder path can be changed using the config
method).

.. code-block:: python

    [None, <archetypal.idfclass.IDF at 0x10fb9f4a8>,
    [Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4tbl.csv'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.end'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/AdultEducationCenter.idf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.dxf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.eso'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.mtd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.bnd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.sql'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.mdd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4tbl.htm'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.shd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.expidf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.err'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/eplus_run_AdultEducationCenter.idf_2020_02_27.log'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.mtr'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/sqlite.err'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.audit'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.eio'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/d04795a50b4ff172da72fec54c6991e4/d04795a50b4ff172da72fec54c6991e4out.rdd')]]

Now, if the command above is modified with `annual=True` and set `design_day=False`, then run_eplus should return the
annual simulation results (which do not exist yet).

.. code-block:: python

    _, idf, results = ar.run_eplus(
        eplus_file=ar.utils.get_eplus_dirs("8-9-0") / "ExampleFiles" / "BasicsFiles/AdultEducationCenter.idf",
        weather_file=ar.utils.get_eplus_dirs("8-9-0") / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
        design_day=False,
        return_files=True,
        annual=True,
        return_idf=True,
        expandobjects=True,
        prep_outputs=True,
    )

Now, since the original IDF file (the version 8.9 one) has not changed, archetypal is going to look for the transitioned
file that resides in the cache folder and use that one instead of retransitioning the original file a second time. On
the other hand, since the parameters of run_eplus have changed (annual instead of design_day), it is going to execute
EnergyPlus using the annual method and return the annual results (see that the second-level folder id has changed from
d04795a50b4ff172da72fec54c6991e4 to 9efc05f6e6cde990685b8ef61e326d94; *these ids may be different on your computer*):

.. code-block:: python

    [None, <archetypal.idfclass.IDF at 0x1a2c7e0128>,
    [Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/AdultEducationCenter.idf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.mdd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.shd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94tbl.htm'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.audit'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.mtr'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.err'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.rdd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.expidf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.eio'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.dxf'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.end'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94tbl.csv'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.eso'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.bnd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.mtd'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/sqlite.err'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/9efc05f6e6cde990685b8ef61e326d94out.sql'),
    Path('cache/e8f4fb7e50ecaaf2cf2c9d4e4d159605/9efc05f6e6cde990685b8ef61e326d94/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw')]]

If we were to rerun the first code block (annual simulation) then it would return the cached results instantly from
the cache:

.. code-block:: shell

    Successfully parsed cached idf run in 0.00 seconds

Profiling this simple script shows an 8x speedup.