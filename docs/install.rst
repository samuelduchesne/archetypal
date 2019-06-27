Installation
============


Requirements
------------

Prior to installing this package, you must have the latest version of `EnergyPlus`_ installed in it's default location.
On Windows that would be in `C:\\EnergyPlusV8-X-X` and on MacOS that would be `/Applications/EnergyPlus-8-X-X`.


Installation with Anaconda / conda
----------------------------------

It is highly recommended to use/install archetypal on a fresh python virtual environment. If you have any trouble
with the installation, try installing archetypal in a new, clean `virtual environment`_ using conda. Note that this
pacakge was tested with python 3.6:

.. code-block:: shell

   conda update -n base conda
   conda config --prepend channels conda-forge
   conda create -n archetypal python=3.6
   conda env update -n archetypal -f environment.yml --prune
   conda install --file requirements-dev.txt
   source activate archetypal


To use the new environment inside a `jupyter notebook`_, we recommend using the steps described by `Angelo
Basile`_, but instead of creating a python venv, we use conda's virtual environment functions:

.. code-block:: shell

   source activate archetypal
   pip install ipykernel
   ipython kernel install --user --name=archetypal

Next time you `start a jupyter notebook`_, you will have the option to choose the *kernel* corresponding to your
project, *archetypal* in this case.

.. figure:: images/20181211121922.png
   :alt: choosing the correct kernel in a jupyter notebook
   :width: 100%
   :align: center

   choosing the correct kernel in a jupyter notebook.
   In the *kernel* menu, select *Change Kernel*
   and select the appropriate virtual env created earlier (*archetypal* in our case).

.. _start a jupyter notebook: https://jupyter.readthedocs.io/en/latest/running.html#starting-the-notebook-server
.. _jupyter notebook: https://jupyter-notebook.readthedocs.io/en/stable/#
.. _Angelo Basile: https://anbasile.github.io/programming/2017/06/25/jupyter-venv/
.. _virtual environment: https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#managing-environments
.. _EnergyPlus: https://energyplus.net
.. _umi: https://umidocs.readthedocs.io/en/latest/