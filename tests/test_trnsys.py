import math
import os

from archetypal import convert_idf_to_t3d, parallel_process


# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


def test_trnbuild_from_idf(scratch_then_cache, config):
    # Path to IDF file to convert
    convert_idf_to_t3d("./input_data/trnsys/NECB 2011 - Small Office.idf")


def test_trnbuild_from_idf_parallel(scratch_then_cache, config):
    # List files here
    files = ["./input_data/trnsys/NECB 2011 - Small Office.idf"]

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): {'idf': file,
                                        'output_folder': None} for
               file in files}

    parallel_process(in_dict, convert_idf_to_t3d, 8, use_kwargs=True)
