Convert IDF to UMI
==================

The IDF to UMI converter generates an Umi Template from one or more EnergyPlus models (IDF file). The conversion is
performed by simpliying a multi-zone and geometric model to a 2-zone and non-geometric template. In other words, a
complex EnergyPlus model is be converted to a generalized core- and perimeter-zone with aggregated performances.

First, load the EnergyPlus idf file using the :func:`archetypal.idfclass.load_idf` method.


.. code-block:: python

    >>> from archetypal import get_eplus_dirs, load_idf
    >>> eplus_dir = get_eplus_dirs("9-2-0")
    >>> eplus_file = eplus_dir / "ExampleFiles" / "BasicsFiles" / "AdultEducationCenter.idf"
    >>> weather = eplus_dir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
    >>> idf = load_idf(eplus_file=eplus_file, weather_file=weather)


.. code-block:: python

    >>> from archetypal import BuildingTemplate
    >>> template_obj = BuildingTemplate.from_idf(
    >>>     idf, sql=idf.sql, DataSource=idf.name
    >>> )


.. code-block:: python

    >>> from archetypal import UmiTemplate
    >>> template_json = UmiTemplate(
    >>>     name="my_umi_template",
    >>>     BuildingTemplates=[template_obj]
    >>> ).to_json()
