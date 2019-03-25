from archetypal import convert_idf_to_t3d
import re
import math


# Function to find the line number of a specific string in a txt file
def checkStr(pathFile, string):
    datafile = open(pathFile, "r")
    value = []
    count = 0
    for line in datafile:
        count = count + 1
        match = re.search(string, line)
        if match:
            return count
            break

# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier

def test_trnbuild_from_idf(scratch_then_cache, config):

    # Path to IDF file to convert
    convert_idf_to_t3d("./input_data/trnsys/NECB 2011 - Medium Office.idf")


