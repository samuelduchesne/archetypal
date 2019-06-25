Translator IDF to BUI
=====================

The necessity of translating IDF files (EnergyPlus input files) to BUI files (TRNBuild input files) emerged from the
need of modeling building archetypes [#]_. Knowing that a lot of different models from different sources (NECB and US-DOE)
have already been developed under EnergyPlus, and it can be a tedious task to create a multizone building in a model
editor (e.g. TRNBuild), we assume the development of a file translator could be useful for simulationists.

Objectives
----------
The principal ojectives of this module was to translate the geometry of the building, the different schedules used in
the model, and the thermal gains.

1. Geometry

The building geometry is kept with all the zoning, the different surfaces (construction and windows) and the thermal
properties of the walls. The thermal properties of windows are not from the IDF, but chosen by the user. The user gives
a U-value, a SHGC value and Tvis value. Then a window is chosen in the Berkeley Lab library (library used in TRNBuild).
For more information, see the methodology_ section please.

2. Schedules

All schedules from the IDF file are translated. The translator is able to process all schedule types defined by
EnergyPlus (see the different schedules_ for more information). Only day and week schedules are written in the output
BUI file

3. Gains

Internal thermal gains such as “people”, “lights” and “equipment” are translated from the IDF file to the BUI file.

Methodology
-----------

The module is divided in 2 major operations. The first one consist in translating the IDF file from EnergyPlus, to an
IDF file proper to an input file for TRNBuild (T3D file), usually created by the TRNSYS plugin "Trnsys3D_" in SketchUp.
The second operation is the conversion of the IDF file for TRNBuild to a BUI file done with the executable trnsidf.exe
(installed by default in the TRNSYS installation folder: `C:TRNSYS18\\Building\\trnsIDF\\`)

1. IDF to T3D

The conversion from the IDF EnergyPlus file to the IDF TRNBuild file (called here T3D file) is the important part of
the module, which uses the Eppy_ python package, allowing, with object classes, to find the IDF objects, modify them if
necessary and re-transcribe them in the T3D file

2. T3D to BUI

The operation to convert the T3D file to the BUI one is just done by running the trnsidf.exe executable with a command
line.

How to convert an IDF file
--------------------------

You have to run the command line::

    archetypal convert [OPTIONS] IDF_FILE OUTPUT_FOLDER

1. `IDF_FILE` is the file path of the IDF file we want to convert. If there is space characters in the path, should be
between quotation marks.

2. `OUTPUT_FOLDER` is the folder where we want the output folders to be written. If there is space characters in the
path, should be between quotation marks.

Example::

    archetypal convert "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"

3. `OPTIONS`: There is different option that can be given to the command line

    - if `-i` is given as an option, the IDF file to convert is returned in the output folder
        Example::

            archetypal convert -i "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"

    - if `-b` is given as an option, the BUI file (converted from the IDF file) is returned in the output folder
        Example::

            archetypal convert -b "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - if `-t` is given as an option, the T3D file (converted from the IDF file) is returned in the output folder
        Example::

            archetypal convert -t "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - if `-d` is given as an option, a DCK file (TRNSYS input file) is returned in the output folder
        Example::

            archetypal convert -d "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - `window-lib PATH` is the path of the window library (from Berkeley Lab). Should be between quotation marks if there is space characters in the path
        Example::

            archetypal convert "/Users/Documents/W74-lib.dat" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - `trnsidf_exe_dir PATH` is the path of the trnsidf.exe executable. Should be between quotation marks if there is space characters in the path
        Example::

            archetypal convert "C:TRNSYS18\\Building\\trnsIDF\\trnsidf.exe" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - `template PATH` is the path of the d18 template file (usually in the same directory of the `trnsidf.exe` executable)
        Example::

            archetypal convert "C:TRNSYS18\\Building\\trnsIDF\\NewFileTemplate.d18" "/Users/Documents/NECB 2011 - Warehouse.idf" "/Users/Documents/WIP"
    - `-h` Shows the "help" message
        Example::

            archetypal convert -h

.. [#] Archetype: building model representing a type of building based on its geometry, thermal properties and its
    usage. Usually used to create urban building model by assigning different archetypes to represent at best the building
    stock we want to model.

.. _schedules: https://bigladdersoftware.com/epx/docs/8-9/input-output-reference/group-schedules.html#group-schedules

.. _Trnsys3D: https://www.trnsys.de/docs/trnsys3d/trnsys3d_uebersicht_en.htm

.. _Eppy: https://pythonhosted.org/eppy/Main_Tutorial.html




