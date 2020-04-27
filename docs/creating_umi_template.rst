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

Blablablbalba


.. _OpaqueMaterial: https://archetypal.readthedocs.io/en/develop/reference/archetypal.template.OpaqueMaterial.html




