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

    UmiBase
    MaterialBase
    MaterialLayer
    ConstructionBase
    LayeredConstruction
    MassRatio
    YearSchedulePart
    DaySchedule
    WeekSchedule
    YearSchedule
    WindowType
    ShadingType

Graph Module
------------

.. currentmodule:: archetypal.template

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

.. currentmodule:: archetypal.energypandas

.. autosummary::
    :template: autosummary-noinherit.rst
    :nosignatures:
    :toctree: reference/

    EnergyDataFrame
    EnergySeries.to_units
    EnergySeries.normalize
    EnergyDataFrame.discretize_tsam


EnergySeries
------------

.. currentmodule:: archetypal.energypandas

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    EnergySeries
    EnergySeries.from_reportdata
    EnergySeries.to_units
    EnergySeries.normalize
    EnergySeries.ldc_source
    EnergySeries.source_side
    EnergySeries.discretize_tsam
    EnergySeries.plot3d
    EnergySeries.plot2d
    EnergySeries.p_max
    EnergySeries.p_max
    EnergySeries.monthly
    EnergySeries.capacity_factor
    EnergySeries.bin_edges
    EnergySeries.time_at_min
    EnergySeries.bin_scaling_factors
    EnergySeries.duration_scaling_factor
    EnergySeries.ldc
    EnergySeries.nseries
    save_and_show
    plot_energyseries
    plot_energyseries_map


Report Data
-----------

.. currentmodule:: archetypal.reportdata

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

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

IDF to BUI module
-----------------

.. currentmodule:: archetypal.trnsys

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    convert_idf_to_trnbuild
    get_idf_objects
    clear_name_idf_objects
    zone_origin
    closest_coords
    parse_window_lib
    choose_window
    trnbuild_idf





Utils
-----

.. currentmodule:: archetypal.utils

.. autosummary::
    :template: autosummary.rst
    :nosignatures:
    :toctree: reference/

    config
    log
    load_umi_template_objects
    umi_template_object_to_dataframe
    get_list_of_common_umi_objects
    newrange
    date_transform
    weighted_mean
    top
    copy_file
    piecewise
    rmse
    checkStr
    write_lines
    load_umi_template
    check_unique_name
    angle
    float_round
    timeit
    lcm
    recursive_len
    rotate
    parallel_process