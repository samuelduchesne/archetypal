Creating an Umi template
------------------------

The following sections explain how to create an Umi template using different
modules available in `archetypal`
The documentation will present how to create each Umi template object (e.g.
`opaque materials`, `window settings`, `zone loads`, etc). Every inputs of
each object will be presented with their default parameters, and simple
examples will be shown for each object.

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

      Example of WindowConstruction objects:

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

      Example of StructureDefinition objects:

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