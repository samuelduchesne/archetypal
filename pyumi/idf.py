import glob
import logging as lg
import time

import pandas as pd
from eppy.modeleditor import IDF

from .utils import log


def object_from_idfs(idfs, ep_object, keys=None, groupby_name=True):
    """

    :param idfs: list
        List of IDF objects
    :param ep_object: string
        EnergyPlus object eg. 'WINDOWMATERIAL:GAS' as a string
    :param keys: list
        List of names for each idf file. Becomes level-0 of a multi-index.
    :param groupby_name: bool

    :return: DataFrame of all specified objects in idf files
    """
    container = []
    start_time = time.time()
    for idf in idfs:
        # Load objects from IDF files and concatenate
        this_frame = object_from_idf(idf, ep_object)
        this_frame = pd.concat(this_frame, ignore_index=True, sort=True)
        container.append(this_frame)
    if keys:
        # If keys given, construct hierarchical index using the passed keys as the outermost level
        this_frame = pd.concat(container, keys=keys, names=['Archetype', '$id'], sort=True)
        this_frame.reset_index(inplace=True)
        this_frame.drop(columns='$id', inplace=True)
    if groupby_name:
        this_frame = this_frame.groupby('Name').first()
    this_frame.reset_index(inplace=True)
    this_frame.index.rename('$id', inplace=True)
    log('Parsed {} {} objects in {:,.2f} seconds'.format(len(idfs), ep_object, time.time() - start_time))
    return this_frame


def object_from_idf(idf, ep_object):
    """

    :param idf: IDF
        IDF object
    :param ep_object:
    :return:
    """
    object_values = [get_values(frame) for frame in idf.idfobjects[ep_object]]
    return object_values


def load_idf(files, idd_filename=None, openstudio_version=None):
    """
    Returns a list of IDF objects using the eppy package.
    :param files: list
        List of file paths
    :param idd_filename: string
        IDD file name location (Energy+.idd)
    :return: list
        List of IDF objects
    """
    # Check weather to use MacOs or Windows location
    if idd_filename is None:
        from sys import platform

        if openstudio_version:
            # Specify version
            open_studio_folder = 'OpenStudio-{}'.format(openstudio_version)
        else:
            # Don't specify version
            open_studio_folder = 'OpenStudio*'  # Wildcard will find any version installed

        # Platform specific location of IDD file
        if platform == "darwin":
            # Assume MacOs file location in Applications Folder
            idd_filename = glob.glob("/Applications/{}/EnergyPlus/*.idd".format(open_studio_folder))
            if len(idd_filename) > 1:
                log('More than one versions of OpenStudio were found. First one is used')
                idd_filename = idd_filename[0]
            elif len(idd_filename) == 1:
                idd_filename = idd_filename[0]
            else:
                log('The necessary IDD file could not be found', level=lg.ERROR)
                raise ValueError('File Energy+.idd could not be found')
        elif platform == "win32":
            # Assume Windows file location in "C" Drive
            idd_filename = glob.glob("C:\{}\EnergyPlus\*.idd".format(open_studio_folder))
            if len(idd_filename) > 1:
                log('More than one versions of OpenStudio were found. First one is used')
                idd_filename = idd_filename[0]
            elif len(idd_filename) == 1:
                idd_filename = idd_filename[0]
            else:
                log('The necessary IDD file could not be found', level=lg.ERROR)
                raise ValueError('File Energy+.idd could not be found')
        print(idd_filename)
        if idd_filename:
            log('Retrieved OpenStudio IDD file at location: {}'.format(idd_filename))

    # Loading eppy
    IDF.setiddname(idd_filename)
    idfs = []
    start_time = time.time()
    for file in files:
        idf_object = IDF(file)

        # Check version of IDF file against version of IDD file
        idf_version = idf_object.idfobjects['VERSION'][0].Version_Identifier
        idd_version = '{}.{}'.format(idf_object.idd_version[0], idf_object.idd_version[1])
        building = idf_object.idfobjects['BUILDING'][0]
        if idf_version == idd_version:
            log('The version of the IDF file {} : version {}, matched the version of EnergyPlus {}, '
                'version {} used to parse it.'.format(building.Name, idf_version,
                                                     idd_filename, idd_version),
                level=lg.DEBUG)
        else:
            log('The version of the IDF file {} : version {}, does not match the version of EnergyPlus {}, '
                'version {} used to parse it.'.format(idf_object.idfobjects['BUILDING:Name'], idf_version,
                                                     idd_filename, idd_version),
                level=lg.WARNING)
        idfs.append(idf_object)

    log('Parsed {} idf file(s) in {:,.2f} seconds'.format(len(files), time.time() - start_time))
    return idfs


def get_values(frame):
    ncols = min(len(frame.fieldvalues), len(frame.fieldnames))
    return pd.DataFrame([frame.fieldvalues[0:ncols]], columns=frame.fieldnames[0:ncols])
