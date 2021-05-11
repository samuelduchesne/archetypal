"""IdfClass utilities."""

import hashlib
import os
from collections import OrderedDict
from io import StringIO

import eppy
from eppy.EPlusInterfaceFunctions import parse_idd

from archetypal.utils import log


def hash_model(idfname, **kwargs):
    """Hash a file or IDF model.

    Return it as a string. Will also hash the :func:`eppy.runner.run_functions.run()`
    arguments so that correct results are returned when different run arguments are
    used.

    Todo:
        Hashing should include the external files used an idf file. For example,
        if a model uses a csv file as an input and that file changes, the
        hashing will currently not pickup that change. This could result in
        loading old results without the user knowing.

    Args:
        idfname (str or IDF): path of the idf file or the IDF model itself.
        kwargs: kwargs to serialize in addition to the file content.

    Returns:
        str: The digest value as a string of hexadecimal digits
    """
    from .idf import IDF

    if kwargs:
        # Before we hash the kwargs, remove the ones that don't have an impact on
        # simulation results and so should not change the cache dirname.
        no_impact = ["keep_data", "keep_data_err", "return_idf", "return_files"]
        for argument in no_impact:
            _ = kwargs.pop(argument, None)

        # sorting keys for serialization of dictionary
        kwargs = OrderedDict(sorted(kwargs.items()))

    # create hasher
    hasher = hashlib.md5()
    if isinstance(idfname, StringIO):
        idfname.seek(0)
        buf = idfname.read().encode("utf-8")
    elif isinstance(idfname, IDF):
        buf = idfname.idfstr().encode("utf-8")
        if idfname.name:
            hasher.update(idfname.name.encode("utf-8"))
            # hash idfname.basename in case file content is identical with another
            # file with a different name
    else:
        with open(idfname, "rb") as afile:
            buf = afile.read()
    hasher.update(buf)

    # Hashing the kwargs as well
    for k, v in kwargs.items():
        if isinstance(v, (str, bool)):
            hasher.update(v.__str__().encode("utf-8"))
        elif isinstance(v, list):
            # include files are Paths
            for item in v:
                with open(item, "rb") as f:
                    buf = f.read()
                    hasher.update(buf)
    return hasher.hexdigest()


def get_idf_version(file, doted=True):
    """Get idf version quickly by reading first few lines of idf file containing
    the 'VERSION' identifier

    Args:
        file (str or StringIO): Absolute or relative Path to the idf file
        doted (bool, optional): Wheter or not to return the version number

    Returns:
        str: the version id
    """
    if isinstance(file, StringIO):
        file.seek(0)
        txt = file.read()
    else:
        with open(os.path.abspath(file), "r", encoding="latin-1") as fhandle:
            txt = fhandle.read()
    try:
        ntxt = parse_idd.nocomment(txt, "!")
        blocks = ntxt.split(";")
        blocks = [block.strip() for block in blocks]
        bblocks = [block.split(",") for block in blocks]
        bblocks1 = [[item.strip() for item in block] for block in bblocks]
        ver_blocks = [block for block in bblocks1 if block[0].upper() == "VERSION"]
        ver_block = ver_blocks[0]
        if doted:
            versionid = ver_block[1]
        else:
            versionid = ver_block[1].replace(".", "-") + "-0"
    except Exception as e:
        log('Version id for file "{}" cannot be found'.format(file))
        log("{}".format(e))
        raise
    else:
        return versionid


def getoldiddfile(versionid):
    """find the IDD file of the E+ installation E+ version 7 and earlier have
    the idd in /EnergyPlus-7-2-0/bin/Energy+.idd

    Args:
        versionid:
    """
    vlist = versionid.split(".")
    if len(vlist) == 1:
        vlist = vlist + ["0", "0"]
    elif len(vlist) == 2:
        vlist = vlist + ["0"]
    ver_str = "-".join(vlist)
    eplus_exe, _ = eppy.runner.run_functions.install_paths(ver_str)
    eplusfolder = os.path.dirname(eplus_exe)
    iddfile = "{}/bin/Energy+.idd".format(eplusfolder)
    return iddfile
