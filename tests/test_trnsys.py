import math
import os

from archetypal import convert_idf_to_t3d, parallel_process, parse_window_lib, \
    choose_window, trnbuild_idf


# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


def test_trnbuild_from_idf(config):
    # Path to IDF file to convert

    window_file = 'W74-lib.dat'
    window_filepath = os.path.join("tests", "input_data", "trnsys", window_file)

    convert_idf_to_t3d("tests/input_data/trnsys/NECB 2011 - Small Office.idf",
                       window_filepath)


def test_trnbuild_from_idf_parallel(config):
    # List files here
    file_upper_path = 'tests/input_data/trnsys/'
    files = ["NECB 2011 - Warehouse.idf"]

    window_file = 'W74-lib.dat'
    window_filepath = os.path.join("tests", "input_data", "trnsys", window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): {'idf_file': file_upper_path + file,
                                        'window_lib': window_filepath,
                                        'output_folder': None} for
               file in files}

    parallel_process(in_dict, convert_idf_to_t3d, 8, use_kwargs=True)


def test_trnbuild_parse_window_lib(config):
    file = 'W74-lib.dat'
    window_filepath = os.path.join("tests", "input_data", "trnsys", file)
    df, bunches = parse_window_lib(window_filepath)

    assert len(df) == len(bunches)


def test_trnbuild_choose_window(config):
    file = 'W74-lib.dat'
    window_filepath = os.path.join("tests", "input_data", "trnsys", file)
    window = choose_window(2.2, 0.64, 0.8, 0.05,
                           window_filepath)

def test_trnbuild_idf():
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template, nonum=True)
    print(res)