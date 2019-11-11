Register new IDF class functions
================================

A simple API allows users to define new functions to append to the :class:`archetypal.idfclass.IDF` class. The
methodology is inspired by how :mod:`pandas` deals with class extensions to add additional “namespaces” to pandas
objects. Here, "namespaces" are added to the :class:`archetypal.idfclass.IDF <IDF>` class, which in turn is an
extension of the :class:`eppy.modeleditor.IDF` object.

The following example shows how to register new functions to the IDF class in order to extend capabilities of
archetypal. For instance, let us assume we are building a calibration module. This module defines one property and one
function to the IDF class:

.. literalinclude:: ../examples/api_extension.py

Now users can access your methods using the `calibrate` namespace:

.. code-block::

    >>> idf = ar.load_idf("tests/input_data/regular/5ZoneNightVent1.idf")
    >>> idf.calibrate.a_property
    >>> idf.calibrate.a_function()