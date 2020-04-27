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

.. _OpaqueMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.OpaqueMaterial.html
.. _GlazingMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.GlazingMaterial.html
.. _GasMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.GasMaterial.html
.. _OpaqueConstruction: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.OpaqueConstruction.html
.. _WindowConstruction: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.WindowConstruction.html
.. _StructureDefinition: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.StructureDefinition.html
.. _MassRatio: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.MassRatio.html

