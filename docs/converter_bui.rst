Converting IDF to BUI
---------------------

.. figure:: images/converter@2x.png
   :alt: converter logo
   :width: 100%
   :align: center

The necessity of translating IDF files (EnergyPlus_ input files) to BUI files (TRNBuild_ input files) emerged from the
need of modeling building archetypes [#]_. Knowing that a lot of different models from different sources (NECB_ and US-DOE_)
have already been developed under EnergyPlus, and it can be a tedious task to create a multizone building in a model
editor (e.g. TRNBuild), we assume the development of a file translator could be useful for simulationists.

Objectives
..........

The principal objectives of this module was to translate (from IDF to BUI) the geometry of the building, the different schedules used in
the model, and the thermal gains.

1. Geometry

The building geometry is kept with all the zoning, the different surfaces (construction and windows) and the thermal
properties of the walls. The thermal properties of windows are not from the IDF, but chosen by the user. The user gives
a U-value, a SHGC value and Tvis value. Then a window is chosen in the Berkeley Lab library (library used in TRNBuild).
For more information, see the methodology_ section please.

2. Schedules

All schedules from the IDF file are translated. The translator is able to process all schedule types defined by
EnergyPlus (see the different schedule_ types for more information). Only day and week schedules are written in the output
BUI file

3. Gains

Internal thermal gains such as “people”, “lights” and “equipment” are translated from the IDF file to the BUI file.

4. Conditioning

Heating and cooling demands are translated from the IDF file to the BUI file such as power per floor area (W/m²) and a temperature setpoint.
The temperature set-point is the set-point at the peak time for heating (or cooling).

Methodology
...........

The module is divided in 2 major operations. The first one consist in translating the IDF file from EnergyPlus, to an
IDF file proper to an input file for TRNBuild (T3D file), usually created by the TRNSYS plugin "Trnsys3D_" in SketchUp.
The second operation is the conversion of the IDF file for TRNBuild to a BUI file done with the executable trnsidf.exe
(installed by default in the TRNSYS installation folder: `C:TRNSYS18\\Building\\trnsIDF\\`)

1. IDF to T3D

The conversion from the IDF EnergyPlus file to the IDF TRNBuild file (called here T3D file) is the important part of
the module, which uses the Eppy_ python package, allowing, with object classes, to find the IDF objects, modify them if
necessary and re-transcribe them in the T3D file

2. T3D to BUI

The operation to convert the T3D file to the BUI file is done by running the trnsidf.exe executable with a command
line. After this operation, the infiltration rate, internal gains and conditioning systems are written in the "REGIME"
section of each zone in the BUI file.

How to convert an IDF file
..........................

Converting an IDF file to a BUI file is done using the terminal with a command line. First, open the Command Prompt on Windows
or the Terminal on Mac. Note that if you used Anaconda to install python on your machine, you will most likely avoid some issues
by using the Anaconda Prompt instead.

Then simply run the following command:

.. code-block:: python

    archetypal convert [OPTIONS] IDF_FILE WEATHER_FILE OUTPUT_FOLDER

1. ``IDF_FILE`` is the file path of the IDF file to convert. If there are space characters in the path, it should be
enclosed in quotation marks.

2. ``WEATHER_FILE`` is the file path of the weather file to use to run the EnergyPlus simulation. If there are space characters in the path, it should be
enclosed in quotation marks.

3. ``OUTPUT_FOLDER`` is the folder where we want the output folders to be written. If there are space characters in
the path, it should enclosed in quotation marks. If output folder path is passed, it must exist.
If nothing is passed, the output folder will be the current working directory.

Here is an example. Make sure to replace the last two arguments with the idf file path and the output folder path
respectively.

.. code-block:: python

    archetypal convert "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

4. `OPTIONS`: There are different options to the `convert` command. The first 3 manage the requested output files.
Users can chose to return a combination of flags

    - if ``-i`` is added, the path to the modified IDF file is returned in the console, and the modified IDF file is
      returned in the output folder. If ``-t`` is added, the path to the T3D file (converted from the IDF file) is
      returned. If ``-d`` is added, the DCK file (TRNSYS input file) is returned in the output folder, and the path to
      this DCK file is returned in the console.

    .. code-block:: python

        archetypal convert -i -t -d "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--window_lib`` is the path of the window library (W74-lib.dat). This library must be in the same format as the
      Berkeley Lab library used by default in TRNBuild. If nothing is passed, the "W74-lib.dat" file available in the
      package "ressources" folder will be used.

    .. code-block:: python

        archetypal convert --window_lib "/Users/Documents/W74-lib.dat" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--trnsidf_exe`` is the path of the trnsidf.exe executable. Usually located in the TRNSYS18 folder under
      "Building/trnsIDF/trnsidf.exe".
      If nothing is passed, the following path will be used : "C:TRNSYS18\\Building\\trnsIDF\\trnsidf.exe".

    .. code-block:: python

        archetypal convert --trnsidf_exe "C:TRNSYS18\\Building\\trnsIDF\\trnsidf.exe" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--template`` is the path of the .d18 template file (usually in the same directory as the `trnsidf.exe` executable).
      If nothing is passed, the following path will be used : "C:TRNSYS18\\Building\\trnsIDF\\NewFileTemplate.d18".

    .. code-block:: python

        archetypal convert --template "C:TRNSYS18\\Building\\trnsIDF\\NewFileTemplate.d18" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--log_clear_names`` if added, do not print log of "clear_names" (equivalence between old and new names) in
      the console.

    .. code-block:: python

        archetypal convert --log_clear_names "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--window`` specifies the window properties <u_value (W/m²-K)> <shgc (-)> <t_vis (-)> <tolerance (-)> <fframe (-)> <uframe (kJ/m²-K-h)>.
      If nothing is passed, the following values will be used : 2.2 0.65 0.8 0.05 0.15 8.17

    .. code-block:: python

        archetypal convert --window 2.2 0.65 0.8 0.05 0.15 8.17 "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``--ordered`` sorts the idf object names

    .. code-block:: python

        archetypal convert --ordered "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - If ``--nonum`` is added, do not renumber surfaces in BUI. If ``--batchjob`` or ``-N`` is added, does BatchJob Modus when running trnsidf.exe.
      ``--geofloor`` must be followed by a float between 0 and 1, and generates GEOSURF values for distributing direct solar radiation where `geo_floor` % is directed to the floor,
      the rest to walls/windows. If ``--refarea`` is added, updates floor reference area of airnodes. If ``--volume`` is added, updates volume of airnodes.
      If ``--capacitance`` is added, updates capacitance of airnodes. All those options are used when running trnsidf.exe (converting T3D file to BUI file).

    .. code-block:: python

        archetypal convert --nonum -N --geofloor 0.6 --refarea --volume --capacitance "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw" "/Users/Documents/WIP"

    - ``-h`` Shows the "help" message

    .. code-block:: python

        archetypal convert -h

.. [#] Archetype: building model representing a type of building based on its geometry, thermal properties and its
   usage. Usually used to create urban building model by assigning different archetypes to represent at best the
   building stock we want to model.

Equivalence between idf object names when converting a file
...........................................................

.. csv-table:: Equivalences
    :file: ./_static/name_equivalence.csv
    :header-rows: 1


.. _EnergyPlus: https://energyplus.net
.. _TRNBuild: http://www.trnsys.com/features/suite-of-tools.php
.. _NECB: https://github.com/canmet-energy/necb_2011_reference_buildings/tree/master/osm_files
.. _US-DOE: https://www.energycodes.gov/development/commercial/prototype_models
.. _schedule: https://bigladdersoftware.com/epx/docs/8-9/input-output-reference/group-schedules.html#group-schedules
.. _Trnsys3D: https://www.trnsys.de/docs/trnsys3d/trnsys3d_uebersicht_en.htm
.. _Eppy: https://pythonhosted.org/eppy/Main_Tutorial.html

