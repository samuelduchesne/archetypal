from archetypal import convert_idf_to_t3d
import math
import os

# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier

def test_trnbuild_from_idf(scratch_then_cache, config):

    # Path to IDF file to convert
    convert_idf_to_t3d("./input_data/trnsys/test_multizone_EP.idf")