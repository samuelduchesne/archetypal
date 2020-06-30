---
title: 'archetypal: A Python package for collecting, simulating, converting and analyzing
 building archetypes'
tags:
  - Python
  - Building Energy Model
  - Archetype
  - Archetype Template
  - EnergyPlus
  - TRNSYS
authors:
  - name: Samuel Letellier-Duchesne
    orcid: 0000-0001-5790-878X
    affiliation: 1
  - name: Louis Leroy
    affiliation: 1
affiliations:
 - name: Department of Mechanical Engineering, Polytechnique Montréal, Montréal, Canada
   index: 1
date: 8 October 2019
bibliography: paper.bib
---

# Summary

The field of Urban Building Energy Modeling (UBEM), which assesses the energy performance
of buildings in cities relies on advanced physical models known as building energy models
that are representative of the building stock. These building archetypes are often
developed in specific modelling platforms such as EnergyPlus or TRNSYS, two leading
simulation engines in the field of building energy modeling. EnergyPlus is an open source
simulation engine developed by the US Department of Energy. TRNSYS is a well established
and specialized simulation platform used to simulate the behavior of transient systems.
The Urban Modeling Interface (UMI), developed by the MIT Sustainable Design Lab, leverages
EnergyPlus to enable building energy modeling at the urban scale. The three tools offer
many advantages in their respective fields, but all suffer from the same flaw: creating
building archetypes for any platform is a time-consuming, tedious and error-prone process.
`archetypal` is a Python package that helps handling collections of such archetypes and to
enable the interoperability between these energy simulation platforms to accelerate the
creation of reliable urban building energy models. This package offers three major
capabilities for researchers and practitioners:

1. Run, modify and analyze collections of EnergyPlus models in a persistent environment;
2. Convert [EnergyPlus](https://energyplus.net) models to [UMI Template Files](http://web.mit.edu/sustainabledesignlab/projects/umi/index.html);
3. Edit [UMI Template Files](http://web.mit.edu/sustainabledesignlab/projects/umi/index.html) in a scripting environment.
4. Convert [EnergyPlus](https://energyplus.net) models to TRNSYS [TrnBuild](http://www.trnsys.com/features/suite-of-tools.php) Models.
 
## EnergyPlus Simulation Environment

`archetypal` leverages the Python Eppy [@Philip2004] and GeomEppy [@Bull2016] packages to
read, edit and run EnergyPlus files. It includes additional functionalities developed to
improve building energy analysis workflows. For instance, `archetypal` exposes simulation
results as time-series DataFrames and typical building energy profiles such as the space
heating, space cooling and domestic hot water profiles are accessible by default. Other
output names can be specified by the user.

Furthermore, for a drastic workflow speed gain, especially with multiple and/or larger IDF
files (which can take several minutes to transition and simulate), `archetypal` features a
caching API. This is particularly useful for reproducible workflows such as the Jupyter
Notebook programming environment. Rerunning cells (even after a kernel restart) will use
the cached IDF models and their simulation results instead of executing EnergyPlus again.
Speedups of up to 8x have been measured.

## EnergyPlus to UMI Template File Conversion

UMI users spend a lot of time and resources gathering all the necessary data and creating
archetype templates for their urban building energy models. `archetypal` offers
researchers and designers a way of creating UMI Template Files from existing EnergyPlus
models, automatically. The algorithm approximates the non-geometric parameters of a
multi-zone EnergyPlus model by dissecting and combining core zones and perimeter zones.
The procedure is an attempt to streamline and accelerate the creation of urban building
energy models [@Reinhart2016] by handling the creation of the inputs of the "Shoeboxer"
method [@Dogan2017] used by UMI.

![Archetypal converts a multizone EnergyPlus model to an UMI Template File by combining core and perimeter zones](../docs/images/model_complexity_reduction@3x.png)

## UMI Template File Scripting Language

`archetypal` also aims at providing a scripting language for the modification of UMI
Template Files. It is a Python interface for the specific data format of the [UMI Template
Editor](https://github.com/MITSustainableDesignLab/basilisk) developed in C#.

## EnergyPlus to TRNBuild Conversion

Intermodel comparison methods are important in the field of building energy modelling
because they allow model methodologies and results to be reviewed [@Judkoff1995].
Furthermore, some model engines include features that others don't already implement.
Since it can be long and error-prone to create archetype buildings by hand, converting
EnergyPlus models to TrnBuild models emerged as a way of speeding both the intermodel
comparisons and the supplemental model creation. That is to say, a large repository of
prototype building models exists in the literature with a large majority developed in the
popular EnergyPlus environment [@USDOE2012; @USDOE2018]. With `archetypal`, researchers
and building energy model specialists can create TrnBuild Models from existing EnergyPlus
models.

The latest stable release of the software can be installed via pip and full documentation
can be found at https://archetypal.readthedocs.io.

# References
