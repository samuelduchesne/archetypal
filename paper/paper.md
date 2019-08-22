---
title: 'archetypal: A Python package for retrieving, constructing, simulating, converting and analysing building
 simulation templates'
tags:
  - Python
  - Building Energy Model
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
date: 21 August 2019
bibliography: paper.bib
---

# Summary

`archetypal` is a Python package that helps handle building archetypes. It offers the
possibility of converting [EnergyPlus](https://energyplus.net) IDF models to Trnsys
[TrnBuild](http://www.trnsys.com/features/suite-of-tools.php) Models (compatible with the
multizone building model).

## EnergyPlus to TRNBuild

## EnergyPlus to UMI Template
It aims to provide a solution to the problem of
scale and lack of data presented in the previous chapter. The algorithm approximates the
non-geometric parameters of a multi-zone BEM by dissecting and combining core-zones and
perimeter -zones. The procedure is an attempt to streamline the creation of UBEM models
based on the Shoeboxer method [@Dogan:2017] by accelerating the creation of building
archetype templates. As we will discuss, this approach introduces a robust method to
convert detailed multi-zone models to archetype templates, striped of geometric
properties. The templates then allow the creation of large numbers of contextually-award
buildings which abstract their thermo-physical properties from the archetype template,
ultimately recreating geometric models.

# Mathematics

Single dollars ($) are required for inline mathematics e.g. $f(x) = e^{\pi/x}$

Double dollars make self-standing equations:

$$\Theta(x) = \left\{\begin{array}{l}
0\textrm{ if } x < 0\cr
1\textrm{ else}
\end{array}\right.$$


# Citations

Citations to entries in paper.bib should be in
[rMarkdown](http://rmarkdown.rstudio.com/authoring_bibliographies_and_citations.html)
format.

For a quick reference, the following citation commands can be used:
- `@author:2001`  ->  "Author et al. (2001)"
- `[@author:2001]` -> "(Author et al., 2001)"
- `[@author1:2001; @author2:2001]` -> "(Author1 et al., 2001; Author2 et al., 2002)"

# Figures

Figures can be included like this: ![Example figure.](../docs/images/20181211121922.png)

# Acknowledgements

We acknowledge the financial support of the Institut de l'Énergie Trottier.

# References