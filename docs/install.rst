Installation
============


Requirements
------------

Prior to installing this package, you must have the latest version of `EnergyPlus`_ installed in it's default location.
On Windows that would be in `C:\\EnergyPlusV8-X-X` and on MacOS that would be `/Applications/EnergyPlus-8-X-X`.


Installating with Anaconda / conda
----------------------------------

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

.. figure:: images/20181211121922.png
   :alt: choosing the correct kernel in a jupyter notebook
   :width: 100%
   :align: center

   choosing the correct kernel in a jupyter notebook.
   In the *kernel* menu, select *Change Kernel*
   and select the appropriate virtual env created earlier (*archetypal* in our case).

