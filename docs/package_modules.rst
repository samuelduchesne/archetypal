Modules
=======

IDF Class
---------

.. currentmodule:: archetypal.idfclass

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    IDF
    Outputs
    Meters
    Variables

UMI Template Library
--------------------

.. currentmodule:: archetypal.umi_template

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    UmiTemplateLibrary

.. _templates_label:

Template Classes
----------------

.. currentmodule:: archetypal.template

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    BuildingTemplate
    ZoneConditioning
    DomesticHotWaterSetting
    GasMaterial
    GlazingMaterial
    ZoneLoad
    OpaqueConstruction
    OpaqueMaterial
    UmiSchedule
    StructureInformation
    VentilationSetting
    WindowConstruction
    WindowSetting
    ZoneDefinition
    ZoneConstructionSet

Template Helper Classes
-----------------------

Classes that support the :ref:`templates_label` classes above.

.. currentmodule:: archetypal.template

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    umi_base.UmiBase
    materials.material_base.MaterialBase
    materials.material_layer.MaterialLayer
    constructions.base_construction.ConstructionBase
    constructions.base_construction.LayeredConstruction
    structure.MassRatio
    schedule.YearSchedulePart
    schedule.DaySchedule
    schedule.WeekSchedule
    schedule.YearSchedule
    constructions.window_construction.WindowType
    constructions.window_construction.ShadingType

Graph Module
------------

.. currentmodule:: archetypal.zone_graph

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    ZoneGraph


Schedule Module
---------------

.. currentmodule:: archetypal.schedule

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    Schedule


Data Portal
-----------

.. currentmodule:: archetypal.dataportal

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    tabula_available_buildings
    tabula_building_details_sheet
    tabula_system
    tabula_system_request
    openei_api_request
    nrel_api_cbr_request
    nrel_bcl_api_request
    stat_can_request
    stat_can_geo_request
    download_bld_window


EnergyDataFrame
---------------

.. note::

    EnergyDataFrame is now part of its own package `energy-pandas <https://github.com/samuelduchesne/energy-pandas>`_.


EnergySeries
------------

.. note::

    EnergySeries is now part of its own package `energy-pandas <https://github.com/samuelduchesne/energy-pandas>`_.


Report Data
-----------

.. currentmodule:: archetypal.reportdata

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    ReportData.__init__
    ReportData.from_sql_dict
    ReportData.from_sqlite
    ReportData.filter_report_data


Tabular Data
------------

.. currentmodule:: archetypal.tabulardata

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    TabularData.from_sql
    TabularData.filter_tabular_data


Utils
-----

.. currentmodule:: archetypal.utils

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    config
    log
    weighted_mean
    top
    copy_file
    load_umi_template
    check_unique_name
    angle
    float_round
    timeit
    lcm
    recursive_len
    rotate
    parallel_process