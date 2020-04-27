Creating an Umi template
------------------------

The following sections explain how to create an Umi template using different
modules available in `archetypal`
The documentation will present how to create each Umi template object (e.g.
`opaque materials`, `window settings`, `zone loads`, etc). Every inputs of
each object will be presented with their default parameters, and simple
examples will show how to create Umi template objects with at least the
required inputs for each object.

1. Defining materials

  Creating Umi template objects to define materials (used as `Layers`
  in constructions).

    - Opaque materials

      Here are all the parameters and their default values for an
      OpaqueMaterial object (see OpaqueMaterial_ doc for more information)

      .. code-block:: python

        def __init__(
            Conductivity,
            SpecificHeat,
            SolarAbsorptance=0.7,
            ThermalEmittance=0.9,
            VisibleAbsorptance=0.7,
            Roughness="Rough",
            Cost=0,
            Density=1,
            MoistureDiffusionResistance=50,
            EmbodiedCarbon=0.45,
            EmbodiedEnergy=0,
            TransportCarbon=0,
            TransportDistance=0,
            TransportEnergy=0,
            SubstitutionRatePattern=None,
            SubstitutionTimestep=20,
            **kwargs)

      Example of OpaqueMaterial objects:

        .. code-block:: python

          concrete = ar.OpaqueMaterial(Conductivity=0.5, SpecificHeat=800, Density=1500)
          insulation = ar.OpaqueMaterial(Conductivity=0.04, SpecificHeat=1000, Density=30)
          brick = ar.OpaqueMaterial(Conductivity=1, SpecificHeat=900, Density=1900)
          plywood = ar.OpaqueMaterial(Conductivity=0.13, SpecificHeat=800, Density=540)
          # List of OpaqueMaterial objects (needed for Umi template creation)
          OpaqueMaterials = [concrete, insulation, brick, plywood]

    - Glazing materials

      Here are all the parameters and their default values for a
      GlazingMaterial object (see GlazingMaterial_ doc for more information)

      .. code-block:: python

        def __init__(
            Density=2500,
            Conductivity=0,
            SolarTransmittance=0,
            SolarReflectanceFront=0,
            SolarReflectanceBack=0,
            VisibleTransmittance=0,
            VisibleReflectanceFront=0,
            VisibleReflectanceBack=0,
            IRTransmittance=0,
            IREmissivityFront=0,
            IREmissivityBack=0,
            DirtFactor=1.0,
            Type=None,
            Cost=0.0,
            Life=1,
            **kwargs)

      Example of GlazingMaterial object:

        .. code-block:: python

          glass = ar.GlazingMaterial(
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.7,
            SolarReflectanceFront=0.5,
            SolarReflectanceBack=0.5,
            VisibleTransmittance=0.7,
            VisibleReflectanceFront=0.5,
            VisibleReflectanceBack=0.5,
            IRTransmittance=0.7,
            IREmissivityFront=0.5,
            IREmissivityBack=0.5)
          # List of GlazingMaterial objects (needed for Umi template creation)
          GlazingMaterials = [glass]

    - Gas materials

      Here are all the parameters and their default values for a
      GasMaterial object (see GasMaterial_ doc for more information)

      .. code-block:: python

        def __init__(
            Cost=0,
            EmbodiedCarbon=0,
            EmbodiedEnergy=0,
            SubstitutionTimestep=100,
            TransportCarbon=0,
            TransportDistance=0,
            TransportEnergy=0,
            SubstitutionRatePattern=None,
            Conductivity=2.4,
            Density=2400,
            **kwargs)

      Example of GasMaterial object:

        .. code-block:: python

          air = ar.GasMaterial(Conductivity=0.02, Density=1.24)
          # List of GasMaterial objects (needed for Umi template creation)
          GasMaterials = [air]

2. Defining constructions

  Creating Umi template objects to define constructions (e.g. `OpaqueConstruction`).

    - Opaque constructions

      Here are all the parameters and their default values for an
      OpaqueConstruction object (see OpaqueConstruction_ doc for more information)

      .. code-block:: python

        def __init__(
            Layers,
            Surface_Type=None,
            Outside_Boundary_Condition=None,
            IsAdiabatic=False,
            **kwargs)

      Example of OpaqueConstruction objects:

        .. code-block:: python

          # OpaqueConstruction using OpaqueMaterial objects
          wall_int = ar.OpaqueConstruction(
            Layers=[plywood],
            Surface_Type="Partition",
            Outside_Boundary_Condition="Zone",
            IsAdiabatic=True)

          wall_ext = ar.OpaqueConstruction(
            Layers=[concrete, insulation, brick],
            Surface_Type="Facade",
            Outside_Boundary_Condition="Outdoors")

          floor = ar.OpaqueConstruction(
            Layers=[concrete, plywood],
            Surface_Type="Ground",
            Outside_Boundary_Condition="Zone")

          roof = ar.OpaqueConstruction(
            Layers=[plywood, insulation, brick],
            Surface_Type="Roof",
            Outside_Boundary_Condition="Outdoors")
          # List of OpaqueConstruction objects (needed for Umi template creation)
          OpaqueConstructions = [wall_int, wall_ext, floor, roof]

    - Window constructions

      Here are all the parameters and their default values for an
      WindowConstruction object (see WindowConstruction_ doc for more information)

      .. code-block:: python

        def __init__(
            Layers,
            Category="Double",
            AssemblyCarbon=0,
            AssemblyCost=0,
            AssemblyEnergy=0,
            DisassemblyCarbon=0,
            DisassemblyEnergy=0,
            **kwargs)

      Example of WindowConstruction object:

        .. code-block:: python

          # WindowConstruction using GlazingMaterial and GasMaterial objects
          window = ar.WindowConstruction(Layers=[glass, air, glass])
          # List of WindowConstruction objects (needed for Umi template creation)
          WindowConstructions = [window]

    - Structure definition

      Here are all the parameters and their default values for an
      StructureDefinition object (see StructureDefinition_ doc for more information)

      .. code-block:: python

        def __init__(
            *args,
            AssemblyCarbon=0,
            AssemblyCost=0,
            AssemblyEnergy=0,
            DisassemblyCarbon=0,
            DisassemblyEnergy=0,
            MassRatios=None,
            **kwargs)

      We observe that StructureDefinition uses MassRatio objects. Here are the
      parameters of MassRatio object (see MassRatio_ doc for more information)

      .. code-block:: python

        def __init__(HighLoadRatio=None, Material=None, NormalRatio=None)

      Example of StructureDefinition object:

        .. code-block:: python

          # StructureDefinition using OpaqueMaterial objects
          mass_ratio = ar.MassRatio(Material=plywood, NormalRatio="NormalRatio")
          struct_definition = ar.StructureDefinition(MassRatios=[mass_ratio])
          # List of StructureDefinition objects (needed for Umi template creation)
          StructureDefinitions = [struct_definition]

3. Defining schedules

  Creating Umi template objects to define schedules (e.g. `DaySchedule`).

    - Day schedules

      Here are all the parameters and their default values for an
      DaySchedule object (see DaySchedule_ doc for more information)

      .. code-block:: python

        def __init__(
            Name=None,
            idf=None,
            start_day_of_the_week=0,
            strict=False,
            base_year=2018,
            schType=None,
            schTypeLimitsName=None,
            values=None,
            **kwargs)

      Example of DaySchedule objects:

        .. code-block:: python

          # Always on
          sch_d_on = ar.DaySchedule.from_values(
            [1] * 24, Category="Day", schTypeLimitsName="Fractional", Name="AlwaysOn")
          # Always off
          sch_d_off = ar.DaySchedule.from_values(
            [0] * 24, Category="Day", schTypeLimitsName="Fractional", Name="AlwaysOff")
          # DHW
          sch_d_dhw = ar.DaySchedule.from_values(
            [0.3] * 24, Category="Day", schTypeLimitsName="Fractional", Name="DHW")
          # Internal gains
          sch_d_gains = ar.DaySchedule.from_values(
            [0] * 6 + [0.5, 0.6, 0.7, 0.8, 0.9, 1] + [0.7] * 6 + [0.4] * 6,
            Category="Day",
            schTypeLimitsName="Fractional",
            Name="Gains",)
          # List of DaySchedule objects (needed for Umi template creation)
          DaySchedules = [sch_d_on, sch_d_dhw, sch_d_gains, sch_d_off]

    - Week schedules

      Here are all the parameters and their default values for an
      WeekSchedule object (see WeekSchedule_ doc for more information)

      .. code-block:: python

        def __init__(
            Name=None,
            idf=None,
            start_day_of_the_week=0,
            strict=False,
            base_year=2018,
            schType=None,
            schTypeLimitsName=None,
            values=None,
            **kwargs)

      Example of WeekSchedule objects:

        .. code-block:: python

          # WeekSchedules using DaySchedule objects
          # Variable `days` needs a list of 7 dict,
          # representing the 7 days of the week
          sch_w_on = ar.WeekSchedule(
            days=[
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_on.id},],
            Category="Week",
            schTypeLimitsName="Fractional",
            Name="AlwaysOn")
          # Always off
          sch_w_off = ar.WeekSchedule(
            days=[
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_off.id},],
            Category="Week",
            schTypeLimitsName="Fractional",
            Name="AlwaysOff")
          # DHW
          sch_w_dhw = ar.WeekSchedule(
            days=[
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},
                {"$ref": sch_d_dhw.id},],
            Category="Week",
            schTypeLimitsName="Fractional",
            Name="DHW")
          # Internal gains
          sch_w_gains = ar.WeekSchedule(
            days=[
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},
                {"$ref": sch_d_gains.id},],
            Category="Week",
            schTypeLimitsName="Fractional",
            Name="Gains")
          # List of WeekSchedule objects (needed for Umi template creation)
          WeekSchedules = [sch_w_on, sch_w_off, sch_w_dhw, sch_w_gains]

      WeekSchedule object can also be created from a dictionary.
      For example, we create a WeekSchedule `AlwaysOn` from a dictionary and
      using DaySchedule `AlwaysOn` objects:

        .. code-block:: python

          # Dict of a WeekSchedule (like it would be written in json file)
          dict_w_on = {
            "Category": "Week",
            "Days": [
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
            ],
            "Type": "Fraction",
            "Name": "OnOff_2"}
          # Creates WeekSchedule from dict (from json)
          sch_w_on = ar.WeekSchedule.from_json(**dict_w_on)

    - Year schedules

      Here are all the parameters and their default values for an
      YearSchedule object (see YearSchedule_ doc for more information)

      .. code-block:: python

        def __init__(
            Name=None,
            idf=None,
            start_day_of_the_week=0,
            strict=False,
            base_year=2018,
            schType=None,
            schTypeLimitsName=None,
            values=None,
            **kwargs)

      YearSchedule are created from dictionaries.
      For example, we create YearSchedules from dictionaries and
      using WeekSchedule objects:

        .. code-block:: python

          # YearSchedules using DaySchedule objects
          # Always on
          dict_on = {
            "Category": "Year",
            "Parts": [
                {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {"$ref": sch_w_on.id}
                }],
            "Type": "Fraction",
            "Name": "AlwaysOn"}
          sch_y_on = ar.YearSchedule.from_json(**dict_on)
          # Always off
          dict_off = {
            "Category": "Year",
            "Parts": [
                {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {"$ref": sch_w_off.id}}],
            "Type": "Fraction",
            "Name": "AlwaysOff"}
          sch_y_off = ar.YearSchedule.from_json(**dict_off)
          # Year ON/OFF
          dict_on_off = {
            "Category": "Year",
            "Parts": [
                {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 5,
                "Schedule": {"$ref": sch_w_on.id}
                },
                {
                "FromDay": 1,
                "FromMonth": 6,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {"$ref": sch_w_off.id}
                }
                ],
            "Type": "Fraction",
            "Name": "ON_OFF"}
          sch_y_on_off = ar.YearSchedule.from_json(**dict_on_off)
          # DHW
          dict_dhw = {
            "Category": "Year",
            "Parts": [
                {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {"$ref": sch_w_dhw.id}}],
            "Type": "Fraction",
            "Name": "DHW"}
          sch_y_dhw = ar.YearSchedule.from_json(**dict_dhw)
          # Internal gains
          dict_gains = {
            "Category": "Year",
            "Parts": [
                {
                "FromDay": 1,
                "FromMonth": 1,
                "ToDay": 31,
                "ToMonth": 12,
                "Schedule": {"$ref": sch_w_gains.id}}],
            "Type": "Fraction",
            "Name": "Gains"}
          sch_y_gains = ar.YearSchedule.from_json(**dict_gains)
          # List of YearSchedule objects (needed for Umi template creation)
          YearSchedules = [sch_y_on, sch_y_off, sch_y_on_off, sch_y_dhw, sch_y_gains]

4. Defining window settings

  Creating Umi template objects to define window settings

  Here are all the parameters and their default values for an
  WindowSetting object (see WindowSetting_ doc for more information)

  .. code-block:: python

    def __init__(
        Construction=None,
        OperableArea=0.8,
        AfnWindowAvailability=None,
        AfnDischargeC=0.65,
        AfnTempSetpoint=20,
        IsVirtualPartition=False,
        IsShadingSystemOn=False,
        ShadingSystemAvailabilitySchedule=None,
        ShadingSystemSetpoint=180,
        ShadingSystemTransmittance=0.5,
        ShadingSystemType=0,
        Type=WindowType.External,
        IsZoneMixingOn=False,
        ZoneMixingAvailabilitySchedule=None,
        ZoneMixingDeltaTemperature=2,
        ZoneMixingFlowRate=0.001,
        **kwargs)

  Example of WindowSetting object:

  .. code-block:: python

    # WindowSetting using WindowConstruction and YearSchedule objects
    window_setting = ar.WindowSetting(
        Construction=window,
        AfnWindowAvailability=sch_y_off,
        ShadingSystemAvailabilitySchedule=sch_y_off,
        ZoneMixingAvailabilitySchedule=sch_y_off)
    # List of WindowSetting objects (needed for Umi template creation)
    WindowSettings = [window_setting]

5. Defining DHW settings

  Creating Umi template objects to define DHW settings

  Here are all the parameters and their default values for an
  DomesticHotWaterSetting object (see DomesticHotWaterSetting_ doc for more information)

  .. code-block:: python

    def __init__(
        IsOn=True,
        WaterSchedule=None,
        FlowRatePerFloorArea=0.03,
        WaterSupplyTemperature=65,
        WaterTemperatureInlet=10,
        **kwargs)

  Example of DomesticHotWaterSetting object:

  .. code-block:: python

    # DomesticHotWaterSetting using YearSchedule objects
    dhw_setting = ar.DomesticHotWaterSetting(
        IsOn=True,
        WaterSchedule=sch_y_dhw,
        FlowRatePerFloorArea=0.03,
        WaterSupplyTemperature=65,
        WaterTemperatureInlet=10,)
    # List of DomesticHotWaterSetting objects (needed for Umi template creation)
    DomesticHotWaterSettings = [dhw_setting]

6. Defining ventilation settings

  Creating Umi template objects to define ventilation settings

  Here are all the parameters and their default values for an
  VentilationSetting object (see VentilationSetting_ doc for more information)

  .. code-block:: python

    def __init__(
        NatVentSchedule=None,
        ScheduledVentilationSchedule=None,
        Afn=False,
        Infiltration=0.1,
        IsBuoyancyOn=True,
        IsInfiltrationOn=True,
        IsNatVentOn=False,
        IsScheduledVentilationOn=False,
        IsWindOn=False,
        NatVentMaxOutdoorAirTemp=30,
        NatVentMaxRelHumidity=90,
        NatVentMinOutdoorAirTemp=0,
        NatVentZoneTempSetpoint=18,
        ScheduledVentilationAch=0.6,
        ScheduledVentilationSetpoint=18,
        **kwargs)

  Example of VentilationSetting object:

  .. code-block:: python

    # VentilationSetting using YearSchedule objects
    vent_setting = ar.VentilationSetting(
        NatVentSchedule=sch_y_off, ScheduledVentilationSchedule=sch_y_off)
    # List of VentilationSetting objects (needed for Umi template creation)
    VentilationSettings = [vent_setting]

7. Defining zone conditioning settings

  Creating Umi template objects to define zone conditioning settings

  Here are all the parameters and their default values for an
  ZoneConditioning object (see ZoneConditioning_ doc for more information)

  .. code-block:: python

    def __init__(
        CoolingCoeffOfPerf=1,
        CoolingLimitType="NoLimit",
        CoolingSetpoint=26,
        CoolingSchedule=None,
        EconomizerType="NoEconomizer",
        HeatRecoveryEfficiencyLatent=0.65,
        HeatRecoveryEfficiencySensible=0.7,
        HeatRecoveryType="None",
        HeatingCoeffOfPerf=1,
        HeatingLimitType="NoLimit",
        HeatingSetpoint=20,
        HeatingSchedule=None,
        IsCoolingOn=True,
        IsHeatingOn=True,
        IsMechVentOn=True,
        MaxCoolFlow=100,
        MaxCoolingCapacity=100,
        MaxHeatFlow=100,
        MaxHeatingCapacity=100,
        MinFreshAirPerArea=0,
        MinFreshAirPerPerson=0.00944,
        MechVentSchedule=None,
        **kwargs)

  Example of ZoneConditioning object:

  .. code-block:: python

    # ZoneConditioning using YearSchedule objects
    zone_conditioning = ar.ZoneConditioning(
        CoolingSchedule=sch_y_on, HeatingSchedule=sch_y_on, MechVentSchedule=sch_y_off)
    # List of ZoneConditioning objects (needed for Umi template creation)
    ZoneConditionings = [zone_conditioning]

8. Defining zone construction sets

  Creating Umi template objects to define zone construction sets

  Here are all the parameters and their default values for an
  ZoneConstructionSet object (see ZoneConstructionSet_ doc for more information)

  .. code-block:: python

    def __init__(
        *args,
        Zone_Names=None,
        Slab=None,
        IsSlabAdiabatic=False,
        Roof=None,
        IsRoofAdiabatic=False,
        Partition=None,
        IsPartitionAdiabatic=False,
        Ground=None,
        IsGroundAdiabatic=False,
        Facade=None,
        IsFacadeAdiabatic=False,
        **kwargs)

  Example of ZoneConstructionSet objects:

  .. code-block:: python

    # ZoneConstructionSet using OpaqueConstruction objects
    # Perimeter zone
    zone_constr_set_perim = ar.ZoneConstructionSet(
        Slab=floor,
        Roof=roof,
        Partition=wall_int,
        Ground=floor,
        Facade=wall_ext)
    # Core zone
    zone_constr_set_core = ar.ZoneConstructionSet(
        Slab=floor,
        Roof=roof,
        Partition=wall_int,
        IsPartitionAdiabatic=True,
        Ground=floor,
        Facade=wall_ext)
    # List of ZoneConstructionSet objects (needed for Umi template creation)
    ZoneConstructionSets = [zone_constr_set_perim, zone_constr_set_core]

9. Defining zone loads

  Creating Umi template objects to define zone loads

  Here are all the parameters and their default values for an
  ZoneLoad object (see ZoneLoad_ doc for more information)

  .. code-block:: python

    def __init__(
        DimmingType="Continuous",
        EquipmentAvailabilitySchedule=None,
        EquipmentPowerDensity=12,
        IlluminanceTarget=500,
        LightingPowerDensity=12,
        LightsAvailabilitySchedule=None,
        OccupancySchedule=None,
        IsEquipmentOn=True,
        IsLightingOn=True,
        IsPeopleOn=True,
        PeopleDensity=0.2,
        **kwargs)

  Example of ZoneLoad object:

  .. code-block:: python

    # ZoneLoad using YearSchedule objects
    zone_load = ar.ZoneLoad(
        EquipmentAvailabilitySchedule=sch_y_gains,
        LightsAvailabilitySchedule=sch_y_gains,
        OccupancySchedule=sch_y_gains)
    # List of ZoneLoad objects (needed for Umi template creation)
    ZoneLoads = [zone_load]

10. Defining zones

  Creating Umi template objects to define zones

  Here are all the parameters and their default values for an
  Zone object (see Zone_ doc for more information)

  .. code-block:: python

    def __init__(
        Conditioning=None,
        Constructions=None,
        DomesticHotWater=None,
        Loads=None,
        Ventilation=None,
        Windows=None,
        InternalMassConstruction=None,
        InternalMassExposedPerFloorArea=1.05,
        DaylightMeshResolution=1,
        DaylightWorkplaneHeight=0.8,
        **kwargs)

  Example of Zone objects:

  .. code-block:: python

    # Zones using ZoneConditioning, ZoneConstructionSet, DomesticWaterSetting,
    # ZoneLoad, VentilationSetting, WindowSetting and OpaqueConstruction objects
    # Perimeter zone
    perim = ar.Zone(
        Conditioning=zone_conditioning,
        Constructions=zone_constr_set_perim,
        DomesticHotWater=dhw_setting,
        Loads=zone_load,
        Ventilation=vent_setting,
        Windows=window_setting,
        InternalMassConstruction=wall_int)
    # Core zone
    core = ar.Zone(
        Conditioning=zone_conditioning,
        Constructions=zone_constr_set_core,
        DomesticHotWater=dhw_setting,
        Loads=zone_load,
        Ventilation=vent_setting,
        Windows=window_setting,
        InternalMassConstruction=wall_int)
    # List of Zone objects (needed for Umi template creation)
    Zones = [perim, core]

11. Defining building template

  Creating Umi template objects to define building template

  Here are all the parameters and their default values for an
  BuildingTemplate object (see BuildingTemplate_ doc for more information)

  .. code-block:: python

    def __init__(
        Core=None,
        Perimeter=None,
        Structure=None,
        Windows=None,
        Lifespan=60,
        PartitionRatio=0.35,
        DefaultWindowToWallRatio=0.4,
        **kwargs)

  Example of BuildingTemplate object:

  .. code-block:: python

    # BuildingTemplate using Zone, StructureDefinition and WindowSetting objects
    building_template = ar.BuildingTemplate(
        Core=core, Perimeter=perim, Structure=struct_definition, Windows=window_setting)
    # List of BuildingTemplate objects (needed for Umi template creation)
    BuildingTemplates = [building_template]
.. _OpaqueMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.OpaqueMaterial.html
.. _GlazingMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.GlazingMaterial.html
.. _GasMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.GasMaterial.html
.. _OpaqueConstruction: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.OpaqueConstruction.html
.. _WindowConstruction: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.WindowConstruction.html
.. _StructureDefinition: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.StructureDefinition.html
.. _MassRatio: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.MassRatio.html
.. _DaySchedule: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.DaySchedule.html
.. _WeekSchedule: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.WeekSchedule.html
.. _YearSchedule: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.YearSchedule.html
.. _WindowSetting: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.WindowSetting.html
.. _DomesticHotWaterSetting: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.DomesticHotWaterSetting.html
.. _VentilationSetting: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.VentilationSetting.html
.. _ZoneConditioning: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.ZoneConditioning.html
.. _ZoneConstructionSet: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.ZoneConstructionSet.html
.. _ZoneLoad: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.ZoneLoad.html
.. _Zone: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.Zone.html
.. _BuildingTemplate: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.BuildingTemplate.html