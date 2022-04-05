[![Build Status](https://github.com/samuelduchesne/archetypal/actions/workflows/python-package.yml/badge.svg?branch=main)](https://github.com/samuelduchesne/archetypal/actions/workflows/python-package.yml)
[![Coverage Status](https://coveralls.io/repos/github/samuelduchesne/archetypal/badge.svg)](https://coveralls.io/github/samuelduchesne/archetypal)
[![Documentation Status](https://readthedocs.org/projects/archetypal/badge/?version=latest)](https://archetypal.readthedocs.io/en/latest/?badge=latest)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.01833/status.svg)](https://doi.org/10.21105/joss.01833)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

# Archetypal

**python for building simulation archetypes**

Retrieve, construct, simulate, convert and analyze building simulation
templates

## Overview

**Archetypal** is a Python package that helps handle building
archetypes.

## Changes since v2.0.0

The conversion of [EnergyPlus](https://energyplus.net) IDF models to
Trnsys
[TrnBuild](http://www.trnsys.com/features/suite-of-tools.php.html)
Models (compatible with the multizone building model) is now part of a
distinct package known as the
[trnslator](https://github.com/louisleroy5/trnslator).

## Features

Here is a short overview of features that are part of archetypal:

1. Building Complexity Reduction: A utility to transform a multizone
   EnergyPlus model to a two-zone normalized model. Such models are
   called `building archetypes` and are the foundation of the
   [UMI Energy Module](https://umidocs.readthedocs.io/en/latest/docs/model-setup-template.html).
   This tool will allow any EnergyPlus model to be imported into
   [UMI](http://web.mit.edu/sustainabledesignlab/projects/umi/index.html)
   and drastically speedup the UBEM process.

## Installation

Recommended to use a conda environement running python 3.8. Pip install should work on all platforms (linux, macOS and Windows).
First,
```cmd
conda create -n venv python=3.8
``` 
`-n venv` is the name of your environement; it can be anything.
Then,
```cmd
pip install -U archetypal
```

## Local Development

1. Clone this repo locally

```console
git clone https://github.com/samuelduchesne/archetypal.git
```

2. Install dependencies:

```console
cd archetypal
conda env create
```

This will create a new environment named `archetypal`. Don't forget to activate the environment.

3. Run Tests:

```console
python -m pytest tests/
```

4. Generate Documentation:

```console
make html
```

