.. archetypal documentation master file, created by
   sphinx-quickstart on Thu Nov  8 13:38:32 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to archetypal's documentation!
======================================

archetypal is a python module that can reduce EnergyPlus reference building models from a complex definition (multiple
zones) to a 2-zone model. This complexity-decution is particularly usefull for umi, the Urban Modeling Interface
developed by the MIT Sustainable Design Lab.

.. toctree::
   :maxdepth: 1
   :caption: Getting Started

   Installation <install.rst>
   For MacOS/Linux users <unix_users.rst>


.. toctree::
   :maxdepth: 2
   :caption: User Guide

   Getting Started <first.rst>
   Convert IDF to UMI <converter_umi.rst>
   Convert IDF to BUI <converter_idf.rst>
   Tutorials <tutorials.rst>

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
