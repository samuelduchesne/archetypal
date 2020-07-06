.. archetypal documentation master file, created by
   sphinx-quickstart on Thu Nov  8 13:38:32 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

archetypal |version|
====================

`archetypal` is a Python package designed with the objective of helping building energy modelers and researchers
maintain collections of building archetypes. `archetypal` depends on `eppy`_ for EnergyPlus models and makes use of
great packages such as `pandas`_ for data structure processing and `tsam`_ for time series aggregation.

.. _eppy: https://eppy.readthedocs.io/
.. _pandas: http://pandas.pydata.org
.. _tsam: https://github.com/FZJ-IEK3-VSA/tsam

Description
===========

As building energy modelers ourselves, we found it was sometimes difficult to use scripting language to retrieve,
modify, simulate and analyze Building Energy Models (BEM). This is why `archetypal` was created. We built two main
capabilities into the package:

1. The conversion of EnergyPlus to `TRNBuild <http://sel.me.wisc.edu/trnsys/index.html>`_ models (shout out to TRNSYS users!)
2. The conversion of EnergyPlus to `UMI <http://web.mit.edu/sustainabledesignlab/projects/umi/index.html>`_ Template Files.

`archetypal` also features a :ref:`Command Line Interface (CLI)<Command reference>` which means that users can execute
commands in the terminal instead of writing a python script. In addition, we believe reproducible research through
Jupyter Notebooks, for instance, is the way foreword. Therefore, all the modules are discoverable and can be imported
independently.

.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   Installation <install.rst>
   For MacOS/Linux users <unix_users.rst>
   Caching <caching.rst>


.. toctree::
   :maxdepth: 2
   :caption: User Guide
   :numbered:

   Converting IDF models <converting.rst>
   Reading and Running IDF files <reading_idf.rst>
   Parallel Processing <tutorials/parallel_process.rst>
   Managing Schedules <tutorials/schedules.rst>
   Creating Umi template <creating_umi_template.rst>
   Reading and Editing UMI Template Files <tutorials/edit_umitemplate.rst>
   Troubleshooting <troubleshooting.rst>

.. toctree::
   :maxdepth: 1
   :caption: Reference Guide

   commands
   package_modules


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
