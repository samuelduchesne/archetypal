.. archetypal documentation master file, created by
   sphinx-quickstart on Thu Nov  8 13:38:32 2018.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to archetypal's documentation!
======================================

archetypal is a python module that can reduce EnergyPlus reference building models from a complex definition (multiple
zones) to a 2-zone model. This complexity-decution is particularly usefull for umi, the Urban Modeling Interface
developed by the MIT Sustainable Design Lab.


Requirements
------------

Prior to installing this package, you must have the latest version of `EnergyPlus`_ installed in it's default location.
On Windows that would be in `C:\\EnergyPlusV8-X-X` and on MacOS that would be `/Applications/EnergyPlus-8-X-X`.


Installation
------------

If you have any trouble with the installation, try installing archetypal in a new,
clean `virtual environment`_ using conda. Note that python version 3 is required:

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


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Getting Started <docs/first.md>
   Modelign Assumptions <docs/assumptions.rst>
   Package Modules <docs/package_modules.rst>


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _virtual environment: https://conda.io/docs/using/envs.html
.. _jupyter notebook: https://jupyter-notebook.readthedocs.io/en/stable/#
.. _Angelo Basile: https://anbasile.github.io/programming/2017/06/25/jupyter-venv/
.. _start a jupyter notebook: https://jupyter.readthedocs.io/en/latest/running.html#starting-the-notebook-server
.. _EnergyPlus: https://energyplus.net
.. _umi: https://umidocs.readthedocs.io/en/latest/