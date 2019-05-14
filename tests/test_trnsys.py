import math
import os

import pytest

from archetypal import convert_idf_to_trnbuild, parallel_process, \
    parse_window_lib, \
    choose_window, trnbuild_idf


# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


def test_trnbuild_from_idf(config):
    # Path to IDF file to convert

    window_file = 'W74-lib.dat'
    window_filepath = os.path.join("tests", "input_data", "trnsys", window_file)

    convert_idf_to_trnbuild(
        "tests/input_data/trnsys/NECB 2011 - Small Office.idf", window_filepath)


@pytest.mark.win32
def test_trnbuild_from_idf_parallel(config):
    # All IDF files
    idf_list = ["NECB 2011 - Warehouse.idf"]
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf"]

    window_file = 'W74-lib.dat'
    window_filepath = os.path.join(file_upper_path, window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): {'idf_file':
                                            os.path.join(file_upper_path, file),
                                        'window_lib': window_filepath} for
               file in files}

    parallel_process(in_dict, convert_idf_to_trnbuild, 4, use_kwargs=True)


@pytest.mark.darwin
@pytest.mark.linux
def test_trnbuild_from_idf_parallel_darwin_or_linux(config):
    # All IDF files
    idf_list = ["NECB 2011 - Warehouse.idf"]
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf"]

    window_file = 'W74-lib.dat'
    window_filepath = os.path.join(file_upper_path, window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): dict(
        idf_file=os.path.join(file_upper_path, file),
        window_lib=window_filepath,
        template="tests/input_data/trnsys/NewFileTemplate.d18",
        trnidf_exe_dir='docker/trnsidf/trnsidf.exe') for
               file in files}

    parallel_process(in_dict, convert_idf_to_trnbuild, 4, use_kwargs=True)


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


@pytest.mark.win32
def test_trnbuild_idf_win32(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template, nonum=True)
    print(res)


@pytest.mark.darwin
@pytest.mark.linux
def test_trnbuild_idf_darwin_or_linux(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template,
                       trnidf_exe_dir='docker/trnsidf/trnsidf.exe',
                       nonum=False, refarea=False, volume=False,
                       capacitance=True, dck=True)
    # todo: trnidf_exe_dir should point to install path instead of docker path
    print(res)
