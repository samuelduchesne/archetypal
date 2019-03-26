import logging as lg
import os
import re
import time
import shutil
import math
import uuid
from eppy import modeleditor
from eppy.modeleditor import IDF
from collections import OrderedDict

import archetypal as ar
from archetypal import log


def clear_name_idf_objects(idfFile):
    objs = ['MATERIAL', 'MATERIAL:NOMASS', 'MATERIAL:AIRGAP', 'CONSTRUCTION',
            'FENESTRATIONSURFACE:DETAILED', 'BUILDINGSURFACE:DETAILED', 'ZONE',
            'BUILDING', 'SITE:LOCATION']
    uniqueList = []

    # For all categorie that we want to change Names
    for obj in objs:
        epObjects = idfFile.idfobjects[obj]

        # For all objects in Category
        for epObject in epObjects:
            # Do not take fenestration, to be treated later
            fenestration = [s for s in ['fenestration', 'shgc', 'window'] if
                            s in epObject.Name.lower()]
            if not fenestration:
                old_name = epObject.Name
                # clean old name by removing spaces, "-", period, "{", "}", doubleunderscore
                new_name = old_name.replace(" ", "_").replace("-", "_").replace(
                    ".", "_").replace("{", "").replace("}", "").replace("__",
                                                                        "_")
                if len(new_name) > 13:
                    # Trnbuild doen not like names longer than 13 characters
                    # Replace with unique ID
                    new_name = uuid.uuid4().hex[:13]

                    # Make sure uuid does not already exist
                    while new_name in uniqueList:
                        new_name = uuid.uuid4().hex[:13]

                    uniqueList.append(new_name)

                #print("changed layer {} with {}".format(old_name, new_name))
                modeleditor.rename(idfFile, obj, old_name, new_name)

            else:
                continue


def convert_idf_to_t3d(idf):
    """

    Args:
        idf (str): ejfufidfq

    Returns:

    """
    start_time = time.time()
    # Load IDF file(s)
    idf_file = ar.load_idf(idf)
    idf_file = idf_file[os.path.basename(idf)]
    log("IDF files loaded in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")

    # Load IDF_T3D template
    ori_idf_filename = "originBUISketchUp.idf"
    ori_idf_filepath = os.path.join("..", "tests", "input_data", "trnsys", ori_idf_filename)
    # Read IDF_T3D template and write lines in variable
    lines = open(ori_idf_filepath).readlines()

    # Create temp file path to write lines during process
    tempfile_name = os.path.basename(idf)
    tempfile_path = os.path.join("..", ".temp", "TEMP_" + tempfile_name)

    # Clean names of idf objects (e.g. 'MATERIAL')
    start_time = time.time()
    clear_name_idf_objects(idf_file)
    log("Cleaned IDF object names in {:,.2f} seconds".format(
        time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")


    # Get objects from IDF file
    materials = idf_file.idfobjects['MATERIAL']
    materialNoMass = idf_file.idfobjects['MATERIAL:NOMASS']
    materialAirGap = idf_file.idfobjects['MATERIAL:AIRGAP']
    versions = idf_file.idfobjects['VERSION']
    buildings = idf_file.idfobjects['BUILDING']
    locations = idf_file.idfobjects['SITE:LOCATION']
    globGeomRules = idf_file.idfobjects['GLOBALGEOMETRYRULES']
    constructions = idf_file.idfobjects['CONSTRUCTION']
    fenestrationSurfs = idf_file.idfobjects['FENESTRATIONSURFACE:DETAILED']
    buildingSurfs = idf_file.idfobjects['BUILDINGSURFACE:DETAILED']
    zones = idf_file.idfobjects['ZONE']

    # Write data from IDF file to T3D file
    start_time = time.time()

    # Write VERSION from IDF to lines (T3D)
    # Get line number where to write
    versionNum = ar.checkStr(ori_idf_filepath,
                          'all objects in class: version')
    # Writing
    for i in range(0, len(versions)):
        lines.insert(versionNum,
                     ",".join(str(item) for item in versions.list2[i]) + ';')
    # Delete temp file if exists
    if os.path.exists(tempfile_path):
        os.remove(tempfile_path)
    # Save lines in temp file
    temp_idf_file = open(tempfile_path, "w+")
    for line in lines:
        temp_idf_file.write("%s" % line)
    temp_idf_file.close()
    # Read temp file to update lines
    lines = open(tempfile_path).readlines()

    # Write BUILDING from IDF to lines (T3D)
    # Get line number where to write
    buildingNum = ar.checkStr(tempfile_path,
                             'all objects in class: building')
    # Writing
    for building in buildings:
        lines.insert(buildingNum, building)
    # Delete temp file if exists
    if os.path.exists(tempfile_path):
        os.remove(tempfile_path)
    # Save lines in temp file
    temp_idf_file = open(tempfile_path, "w+")
    for line in lines:
        temp_idf_file.write("%s" % line)
    temp_idf_file.close()
    # Read temp file to update lines
    lines = open(tempfile_path).readlines()

    a=1

    log("Write data from IDF to T3D in {:,.2f} seconds".format(
        time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")




