Installation
============


Requirements
------------

Prior to installing this package, you must have the 8.9.0 version of `EnergyPlus`_ installed in it's default location.
On Windows that would be in `C:\\EnergyPlusV8-9-0` and on MacOS that would be `/Applications/EnergyPlus-8-9-0`.

Installation with ``pip``
-------------------------

If you have Python 3 already installed on your machine and don't bother to create a virtual environement (which is
highly recommended), then simply install using the following command in the terminal:

.. code-block:: shell

    pip install archetypal


Installation within a Virtual Environment
-----------------------------------------

It is highly recommended to use/install *archetypal* on a fresh python virtual environment. If you have any trouble
with the installation above, try installing archetypal in a new, clean `virtual environment`_ using venv or conda. Note
that this pacakge was tested with python 3.6:

.. code-block:: shell

    python3 -m venv archetypal
    source archetypal/bin/activate

Activating the virtual environment will change your shell’s prompt to show what virtual environment you’re using, and
modify the environment so that running python will get you that particular version and installation of Python. For
example:

.. code-block:: shell

    $ source archetypal/bin/activate
    (archetypal) $ python
    Python 3.5.1 (default, May  6 2016, 10:59:36)
    ...
    >>> import sys
    >>> sys.path
    ['', '/usr/local/lib/python35.zip', ...,
    '~/envs/archetypal/lib/python3.5/site-packages']
    >>>

Then you can install archetypal in this freshly created environment:

.. code-block:: shell

    pip install archetypal

To use the new environment inside a `jupyter notebook`_, we recommend using the steps described by `Angelo
Basile`_:

.. code-block:: shell

   source archetypal/bin/activate
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
   and select the appropriate virtual env created earlier (*archetypal* in this case).


Installation with Anaconda / conda
----------------------------------

.. warning::

    This install method  is not yet available. Revert to the method detailed above.


Installing with conda is similar:

.. code-block:: shell

   conda update -n base conda
   conda create -n archetypal python=3 archetypal
   source activate archetypal


.. _start a jupyter notebook: https://jupyter.readthedocs.io/en/latest/running.html#starting-the-notebook-server
.. _jupyter notebook: https://jupyter-notebook.readthedocs.io/en/stable/#
.. _Angelo Basile: https://anbasile.github.io/programming/2017/06/25/jupyter-venv/
.. _virtual environment: https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#managing-environments
.. _EnergyPlus: https://energyplus.net
.. _umi: https://umidocs.readthedocs.io/en/latest/