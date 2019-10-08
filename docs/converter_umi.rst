Convert IDF to UMI
==================

The IDF to UMI converter generates an Umi Template from one or more EnergyPlus models (IDF file). The conversion is
performed by simpliying a multi-zone and geometric model to a 2-zone and non-geometric template. In other words, a
complex EnergyPlus model is be converted to a generalized core- and perimeter-zone with aggregated performances.

First, load the EnergyPlus idf file using the :func:`archetypal.idfclass.load_idf` method.


.. code-block:: shell

    >>> from archetypal import load_idf
    >>> weather = "path/to/weather/file.epw"
    >>> eplus_file = "path/to/energyplus/file.idf"
    >>> idf = load_idf(eplus_file=eplus_file, weather_file=weather)


.. code-block:: shell

    >>> from archetypal import BuildingTemplate
    >>> template_obj = BuildingTemplate.from_idf(
    >>>     x.idf, sql=x.idf.sql, DataSource=x.idf.name
    >>> )


.. code-block:: shell

    >>> from archetypal import UmiTemplate
    >>> template_json = UmiTemplate(
    >>>     name="my_umi_template",
    >>>     BuildingTemplates=template_obj
    >>> ).to_json()
