[![Build Status](https://travis-ci.com/samuelduchesne/archetypal.svg?branch=develop)](https://travis-ci.com/samuelduchesne/archetypal)
[![Coverage Status](https://coveralls.io/repos/github/samuelduchesne/archetypal/badge.svg)](https://coveralls.io/github/samuelduchesne/archetypal)

# Archetypal

**python for building simulation archetypes** 

Retrieve, construct, simulate, and analyse building templates

## Overview

**Archetypal** is a Python package that helps handle building archetypes. The first public feature released in this 
    version is the  conversion of [EnergyPlus](https://energyplus.net) IDF models to Trnsys [TrnBuild](http://www.trnsys.com/features/suite-of-tools.php) Models 
    (compatible with the multizone building model). For a list of features currently in development see the [In 
    development](#in-development) section.

## In development

Many features are still in developement and will become public as the 
development process continues.

- Building Complexity Reduction: A utility to transform a multizone EnergyPlus model to a two-zone normalized model. 
Such models are called `building templates` and are the foundation of the
[UMI Energy Module](https://umidocs.readthedocs.io/en/latest/docs/model-setup-template.html).
- Archetype creation: From open-source building model data sources such as the TABULA database, construct a building 
template and use in UMI.

## Authors

This work is developed by a small team of building energy simulation enthousiasts

- Samuel Letellier-Duchesne, PhD Candidate at Polytechnique Montréal (Corresponding Author)
- Louis Leroy, Master Student at Polytechnique Montréal