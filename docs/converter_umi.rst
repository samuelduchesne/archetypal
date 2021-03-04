Converting IDF to UMI
---------------------

The IDF to UMI converter generates an Umi Template from one or more EnergyPlus models (IDF files). The conversion is
performed by simplifying a multi-zone and geometric model to a 2-zone and non-geometric template. In other words, a
complex EnergyPlus model is be converted to a generalized core- and perimeter-zone with aggregated performances.

Conversion can be achieved either with the command line or within a python console (interactive shell). The command
line is useful for getting started quickly but does not offer any intermediate like the interactive shell does. If
you would rather use archetypal inside a python script, then the archetypal module is fully accessible and documented.

Using the Command Line
......................

.. hint::

    In this tutorial, we will be using an IDF model from the ExampleFiles folder located inside the EnergyPlus folder.

Terminal and Command Prompt may not be the most convenient tool to use, which is quite understandable, since users may
be more familiar with graphical interfaces. `archetypal` does not feature a graphical interface as it is meant to be
used in a scripting environment.

The first step would be to change the current directory to the one where the idf file is located. When `archetypal` is
executed, temporary folders may be created to enable the conversion process. It is recommended to change the current
directory of the terminal window to any working directory of your choice.

.. code-block:: shell

    cd "/path/to/directory"

An idf file can be converted to an umi template using the `reduce` command. For example, the following code will convert
the model `AdultEducationCenter.idf` to a json file named *myumitemplate.json*. Both absolute and relative paths can be
used.

.. code-block:: shell

    archetypal reduce "/Applications/EnergyPlus-9-2-0/ExampleFiles/BasicsFiles/AdultEducationCenter.idf" "./converted/myumitemplate.json"

Using the Python Console
........................

`archetypal` methods are accessible by importing the package.

1. Load the file

First, load the EnergyPlus idf file using the :class:`archetypal.idfclass.idf.IDF` class. In the following example,
the AdultEducationCenter.idf model is used.

.. code-block:: python

    >>> from archetypal import get_eplus_dirs, IDF
    >>> eplus_dir = get_eplus_dirs("9-2-0")  # Getting EnergyPlus install path
    >>> eplus_file = eplus_dir / "ExampleFiles" / "BasicsFiles" / "AdultEducationCenter.idf"  # Model path
    >>> weather = eplus_dir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"  # Weather file path
    >>> idf = IDF(idfname=eplus_file, epw=weather)  # IDF load

2. Create a BuildingTemplate Object

.. code-block:: python

    >>> from archetypal import BuildingTemplate
    >>> template_obj = BuildingTemplate.from_idf(
    >>>     idf, DataSource=idf.name
    >>> )

3. Create an UmiTemplateLibrary Object and Save

.. code-block:: python

    >>> from archetypal import UmiTemplateLibrary
    >>> template_json = UmiTemplateLibrary(
    >>>     name="my_umi_template",
    >>>     BuildingTemplates=[template_obj]
    >>> ).to_json()
