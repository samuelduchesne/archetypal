Running multiple files
======================

Running multiple IDF files is easily achieved by using the :meth:`~archetypal.utils.parallel_process` method.

.. hint::

    The :meth:`~archetypal.utils.parallel_process` method works with any method. You can use it to parallelize
    other functions in your script.

To create a parallel run, first import the usual package methods and configure `archetypal` to use caching and to
show logs in the console.

.. code-block:: python

    >>> from path import Path
    >>> from archetypal import IDF, config, settings, parallel_process
    >>> import pandas as pd
    >>> config(use_cache=True, log_console=True)

Then, use

.. code-block:: python

    >>> from archetypal import IDF, config, settings
    >>> from archetypal import parallel_process
    >>> import pandas as pd
    >>> config(use_cache=True, log_console=True)

Then, use `glob` to make a list of NECB idf files in the input_data directory (relative to this package). The weather
file path is also created:

.. code-block:: python

    >>> necb_basedir = Path("tests/input_data/necb")
    >>> files = necb_basedir.glob("*.idf")
    >>> epw = Path("data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw")

For good measure, load the files in a DataFrame, which we will use to create the rundict in the next step.

.. code-block:: python

    >>> idfs = pd.DataFrame({"file": files, "name": [file.basename() for file in files]})

The rundict, is the list of tasks we wish to do in parallel. This dictionary is passed to :meth:`~archetypal.idfclass
.parallel_process`. Here, we want to execute :meth:`~archetypal.idfclass.run_eplus` with the following parameters:

.. code-block:: python

    >>> rundict = {
    >>>     k: dict(
    >>>         idfname=str(file),
    >>>         prep_outputs=True,
    >>>         weather_file=str(epw),
    >>>         expandobjects=True,
    >>>         verbose=True,
    >>>         design_day=True,
    >>>         simulate=True,
    >>>     )
    >>>     for k, file in idfs.file.to_dict().items()
    >>> }

Finally, execute :meth:`~archetypal.utils.parallel_process`. The resulting sql_file paths, which we defined as the
type of output_report attribute for :meth:`~archetypal.idfclass.run_eplus` is returned as a dictionary with the same
keys as the index of the DataFrame.

.. code-block:: python

    >>> sql_files =  parallel_process(rundict, run_eplus, use_kwargs=True, processors=-1)
    >>> sql_files
    {0: Path('cache/06e92da0247c71762d64aed4bcf3cdb2/output_data/06e92da0247c71762d64aed4bcf3cdb2out.sql'),
     1: Path('cache/aee8caf562b3519942ef88f533800dd0/output_data/aee8caf562b3519942ef88f533800dd0out.sql'),
     2: Path('cache/9d14a6aa6fda03a77ed5c5c48d28a73b/output_data/9d14a6aa6fda03a77ed5c5c48d28a73bout.sql'),
     3: Path('cache/5ddfa8827d2a577aabb02d60195bf53a/output_data/5ddfa8827d2a577aabb02d60195bf53aout.sql'),
     4: Path('cache/225c3428099e2abcc4051750db12731b/output_data/225c3428099e2abcc4051750db12731bout.sql'),
     5: Path('cache/0991d42c5af387833b68adffc0d7b523/output_data/0991d42c5af387833b68adffc0d7b523out.sql'),
     6: Path('cache/e10a4bf8bae93b0b0d2ad2638c807b61/output_data/e10a4bf8bae93b0b0d2ad2638c807b61out.sql'),
     7: Path('cache/86439047af9e8ff4650d6bab460d5e70/output_data/86439047af9e8ff4650d6bab460d5e70out.sql'),
     8: Path('cache/68da0886afa316f75bc63d7e576d0228/output_data/68da0886afa316f75bc63d7e576d0228out.sql'),
     9: Path('cache/68a8be47fe4573a61d388a0101798958/output_data/68a8be47fe4573a61d388a0101798958out.sql'),
     10: Path('cache/f6f8abae5272bf607a9f53d18c10a50d/output_data/f6f8abae5272bf607a9f53d18c10a50dout.sql'),
     11: Path('cache/4cf8589df098bb0c3f2b9f8589ec6ed6/output_data/4cf8589df098bb0c3f2b9f8589ec6ed6out.sql'),
     12: Path('cache/5dd643faf859ed1aed5adffcecd0d47c/output_data/5dd643faf859ed1aed5adffcecd0d47cout.sql'),
     13: Path('cache/e7cf6ae2be8917a409c9a1acad3bc349/output_data/e7cf6ae2be8917a409c9a1acad3bc349out.sql'),
     14: Path('cache/3f122e04f7d8d19195cb8818a0be390f/output_data/3f122e04f7d8d19195cb8818a0be390fout.sql'),
     15: Path('cache/d263b5b5d3bc56f2fb3795c61ac89cfe/output_data/d263b5b5d3bc56f2fb3795c61ac89cfeout.sql')}