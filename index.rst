.. archetypal documentation master file, created by
   sphinx-quickstart on Thu Nov  8 13:38:32 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to archetypal's documentation!
======================================

archetypal is a python module that can reduce EnergyPlus reference building models from a complex format (multiple zones)
to a 2-zone model compatible with umi.


Installation
------------

If you have any trouble with the installation, try installing archetypal in a new,
clean `virtual environment`_ using conda. Note that python version 3.7 is recommended:

.. code-block:: shell

   cd <path of archetypal root folder>
   conda env create --file environment.yml
   source activate archetypal
   python setup.py


To use the new environnement inside a `jupyter notebook`_, we recommend using the steps described by `Angelo
Basile`_, but instead of creating a python venv, we use conda's virtual environment functions:

.. code-block:: shell

   source activate archetypal
   pip install ipykernel
   ipython kernel install --user --name=archetypal

Next time you `start a jupyter notebook`_, you will have the option to choose the *kernel* corresponding to your
project, *archetypal* in this case.

.. figure:: docs/images/20181211121922.png
   :alt: choosing the correct kernel in a jupyter notebook
   :width: 100%
   :align: center

   choosing the correct kernel in a jupyter notebook.
   In the *kernel* menu, select *Change Kernel*
   and select the appropriate virtual env created earlier (*archetypal* in our case).


Packages
--------

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Getting Started <docs/first.md>
   Modelign Assumptions <docs/assumptions.rst>

.. automodule:: archetypal.idf
   :members:

.. automodule:: archetypal.core
   :members:

.. automodule:: archetypal.utils
   :members:

Simple Galzing Module
=====================

.. automodule:: archetypal.simple_glazing
   :members:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _virtual environment: https://conda.io/docs/using/envs.html
.. _jupyter notebook: https://jupyter-notebook.readthedocs.io/en/stable/#
.. _Angelo Basile: https://anbasile.github.io/programming/2017/06/25/jupyter-venv/
.. _start a jupyter notebook: https://jupyter.readthedocs.io/en/latest/running.html#starting-the-notebook-server