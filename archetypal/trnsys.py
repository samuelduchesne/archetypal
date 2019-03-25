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


def convert_idf_to_t3d(idf):
    """

    Args:
        idf (str): ejfufidfq

    Returns:

    """
    start_time = time.time()
    # Load IDF file(s)
    idfFiles = ar.load_idf(idf)
    log("IDF files loaded in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")

    print(type(idfFiles[os.path.basename(idf)]))

    # Load IDF_T3D template
    start_time = time.time()
    ori_idf_filename = "originBUISketchUp.idf"
    ori_idf_filepath = os.path.join("..", "tests", "input_data", "trnsys", ori_idf_filename)
    # Read IDF_T3D template and write lines in variable
    lines = open(ori_idf_filepath).readlines()
    log("IDF_T3D template read in {:,.2f} seconds".format(time.time() - start_time),
        lg.INFO, name="CoverterLog", filename="CoverterLog")


