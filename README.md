[![Build Status](https://travis-ci.com/samuelduchesne/archetypal.svg?branch=develop)](https://travis-ci.com/samuelduchesne/archetypal)
[![Coverage Status](https://coveralls.io/repos/github/samuelduchesne/archetypal/badge.svg)](https://coveralls.io/github/samuelduchesne/archetypal)
[![Documentation Status](https://readthedocs.org/projects/archetypal/badge/?version=latest)](https://archetypal.readthedocs.io/en/latest/?badge=latest)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Archetypal

**python for building simulation archetypes**

Retrieve, construct, simulate, convert and analyze building simulation templates

## Overview

**Archetypal** is a Python package that helps handle building archetypes. The first public feature released in this
version is the  conversion of [EnergyPlus](https://energyplus.net) IDF models to Trnsys [TrnBuild](http://www.trnsys.com/features/suite-of-tools.php.html) Models (compatible with the multizone building model). For a list of features
currently in development see the [In development](#in-development) section.

## In development

Many features are still in development and will become public as the development process continues. Here is a short
overview of features that we are excited to release soon:

1. Building Complexity Reduction: A utility to transform a multizone EnergyPlus model to a two-zone normalized model.
Such models are called `building archetypes` and are the foundation of the
[UMI Energy Module](https://umidocs.readthedocs.io/en/latest/docs/model-setup-template.html). This tool will allow
any EnergyPlus model to be imported into [UMI](http://web.mit.edu/sustainabledesignlab/projects/umi/index.html) and drastically speedup the UBEM process.
2. Database archetype creation: From open-source building model data sources such as the TABULA database, construct a
building template and use in UMI. Variabilty in the parameters could be achieved to effectively pick out templates
that follow a statistical distribution or a known distribution for some parameters in your area.

## Authors

This work is developed by a small team of building energy simulation enthusiasts

- Samuel Letellier-Duchesne, PhD Candidate at Polytechnique Montréal (Corresponding Author)
- Louis Leroy, Master Student at Polytechnique Montréal
