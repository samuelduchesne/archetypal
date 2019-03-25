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

                print("changed layer {} with {}".format(old_name, new_name))
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
    idfFile = ar.load_idf(idf)
    log("IDF files loaded in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")

    # Load IDF_T3D template
    start_time = time.time()
    ori_idf_filename = "originBUISketchUp.idf"
    ori_idf_filepath = os.path.join("..", "tests", "input_data", "trnsys", ori_idf_filename)
    # Read IDF_T3D template and write lines in variable
    lines = open(ori_idf_filepath).readlines()
    log("IDF_T3D template read in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")

    # Clean names of idf objects (e.g. 'MATERIAL')
    clear_name_idf_objects(idfFile[os.path.basename(idf)])
