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


@pytest.mark.win32
def test_trnbuild_from_idf(config):
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf", "NECB 2011 - Small Office.idf"]

    window_file = 'W74-lib.dat'
    template_dir = os.path.join('archetypal', 'templates')
    window_filepath = os.path.join(template_dir, window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    kwargs_dict = {'u_value': 2.5, 'shgc': 0.6, 't_vis': 0.78,
                   'tolerance': 0.05}

    convert_idf_to_trnbuild(idf_file=os.path.join(file_upper_path, files[0]),
                            window_lib=window_filepath, **kwargs_dict)


@pytest.mark.win32
def test_trnbuild_from_idf_parallel(config):
    # All IDF files
    idf_list = ["NECB 2011 - Warehouse.idf"]
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf", "NECB 2011 - Small Office.idf"]

    # window_file = 'W74-lib.dat'
    # window_filepath = os.path.join(file_upper_path, window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): dict(
        idf_file=os.path.join(file_upper_path, file)) for file in files}

    result = parallel_process(in_dict, convert_idf_to_trnbuild, 4,
                              use_kwargs=True)

    assert not any(isinstance(a, Exception) for a in result.values())


@pytest.mark.darwin
@pytest.mark.linux
def test_trnbuild_from_idf_parallel_darwin_or_linux(config):
    # All IDF files
    idf_list = ["NECB 2011 - Warehouse.idf"]
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf", "NECB 2011 - Small Office.idf"]

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): dict(
        idf_file=os.path.join(file_upper_path, file),
        template="tests/input_data/trnsys/NewFileTemplate.d18",
        trnidf_exe_dir='docker/trnsidf/trnsidf.exe') for
        file in files}

    result = parallel_process(in_dict, convert_idf_to_trnbuild, 4,
                              use_kwargs=True)

    assert not any(isinstance(a, Exception) for a in result.values())


@pytest.mark.win32
def test_trnbuild_idf_win32(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template, nonum=True)

    assert res


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

    assert res
