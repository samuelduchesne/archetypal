import math
import os

import pytest

from archetypal import convert_idf_to_trnbuild, parallel_process, \
    trnbuild_idf, copy_file


# Function round to hundreds
def round_up(n, decimals=0):
    multiplier = 10 ** decimals
    return math.ceil(n * multiplier) / multiplier


@pytest.mark.xfail("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
                   reason="Skipping this test on Travis CI.")
def test_trnbuild_from_idf(config):
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["RefBldgOutPatientPost1980_v1.3_5"
             ".0_4A_USA_MD_BALTIMORE.idf",
             "ASHRAE90.1_OfficeLarge_STD2004_Rochester.idf",
             "NECB 2011 - Warehouse.idf"]
    idf_file = os.path.join(file_upper_path, files[1])
    idf_file = copy_file(idf_file)

    window_file = 'W74-lib.dat'
    template_dir = os.path.join('archetypal', 'ressources')
    window_filepath = os.path.join(template_dir, window_file)

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    kwargs_dict = {'u_value': 2.5, 'shgc': 0.6, 't_vis': 0.78,
                   'tolerance': 0.05, 'ordered': True}

    convert_idf_to_trnbuild(idf_file=idf_file[0], window_lib=window_filepath,
                            template="tests/input_data/trnsys/NewFileTemplate.d18",
                            trnsidf_exe='docker/trnsidf/trnsidf.exe',
                            **kwargs_dict)


@pytest.mark.win32
@pytest.mark.xfail("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
                   reason="Skipping this test on Travis CI.")
def test_trnbuild_from_idf_parallel(config):
    # All IDF files
    idf_list = ["NECB 2011 - Full Service Restaurant.idf",
                "NECB 2011 - HighRise Apartment.idf",
                "NECB 2011 - Hospital.idf",
                "NECB 2011 - Large Hotel.idf",
                "NECB 2011 - Medium Office.idf",
                "NECB 2011 - MidRise Apartment.idf",
                "NECB 2011 - Outpatient.idf",
                "NECB 2011 - Primary School.idf",
                "NECB 2011 - Quick Service Restaurant.idf",
                "NECB 2011 - Retail Standalone.idf",
                "NECB 2011 - Retail Stripmall.idf",
                "NECB 2011 - Secondary School.idf",
                "NECB 2011 - Small Hotel.idf",
                "NECB 2011 - Small Office.idf",
                "NECB 2011 - Warehouse.idf",
                "ASHRAE90.1_ApartmentHighRise_STD2004_Rochester.idf",
                "ASHRAE90.1_ApartmentMidRise_STD2004_Rochester.idf",
                "ASHRAE90.1_Hospital_STD2004_Rochester.idf",
                "ASHRAE90.1_HotelLarge_STD2004_Rochester.idf",
                "ASHRAE90.1_HotelSmall_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeLarge_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeMedium_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeSmall_STD2004_Rochester.idf",
                "ASHRAE90.1_OutPatientHealthCare_STD2004_Rochester.idf",
                "ASHRAE90.1_RestaurantFastFood_STD2004_Rochester.idf",
                "ASHRAE90.1_RestaurantSitDown_STD2004_Rochester.idf",
                "ASHRAE90.1_RetailStandalone_STD2004_Rochester.idf",
                "ASHRAE90.1_RetailStripmall_STD2004_Rochester.idf",
                "ASHRAE90.1_SchoolPrimary_STD2004_Rochester.idf",
                "ASHRAE90.1_SchoolSecondary_STD2004_Rochester.idf",
                "ASHRAE90.1_Warehouse_STD2004_Rochester.idf"]
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
@pytest.mark.xfail("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
                   reason="Skipping this test on Travis CI.")
def test_trnbuild_from_idf_parallel_darwin_or_linux(config):
    # All IDF files
    idf_list = ["NECB 2011 - Full Service Restaurant.idf",
                "NECB 2011 - HighRise Apartment.idf",
                "NECB 2011 - Hospital.idf",
                "NECB 2011 - Large Hotel.idf",
                "NECB 2011 - Medium Office.idf",
                "NECB 2011 - MidRise Apartment.idf",
                "NECB 2011 - Outpatient.idf",
                "NECB 2011 - Primary School.idf",
                "NECB 2011 - Quick Service Restaurant.idf",
                "NECB 2011 - Retail Standalone.idf",
                "NECB 2011 - Retail Stripmall.idf",
                "NECB 2011 - Secondary School.idf",
                "NECB 2011 - Small Hotel.idf",
                "NECB 2011 - Small Office.idf",
                "NECB 2011 - Warehouse.idf",
                "ASHRAE90.1_ApartmentHighRise_STD2004_Rochester.idf",
                "ASHRAE90.1_ApartmentMidRise_STD2004_Rochester.idf",
                "ASHRAE90.1_Hospital_STD2004_Rochester.idf",
                "ASHRAE90.1_HotelLarge_STD2004_Rochester.idf",
                "ASHRAE90.1_HotelSmall_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeLarge_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeMedium_STD2004_Rochester.idf",
                "ASHRAE90.1_OfficeSmall_STD2004_Rochester.idf",
                "ASHRAE90.1_OutPatientHealthCare_STD2004_Rochester.idf",
                "ASHRAE90.1_RestaurantFastFood_STD2004_Rochester.idf",
                "ASHRAE90.1_RestaurantSitDown_STD2004_Rochester.idf",
                "ASHRAE90.1_RetailStandalone_STD2004_Rochester.idf",
                "ASHRAE90.1_RetailStripmall_STD2004_Rochester.idf",
                "ASHRAE90.1_SchoolPrimary_STD2004_Rochester.idf",
                "ASHRAE90.1_SchoolSecondary_STD2004_Rochester.idf",
                "ASHRAE90.1_Warehouse_STD2004_Rochester.idf"]
    # List files here
    file_upper_path = os.path.join('tests', 'input_data', 'trnsys')
    files = ["NECB 2011 - Warehouse.idf", "NECB 2011 - Small Office.idf"]

    # prepare args (key=value). Key is a unique id for the runs (here the
    # file basename is used). Value is a dict of the function arguments
    in_dict = {os.path.basename(file): dict(
        idf_file=os.path.join(file_upper_path, file),
        template="tests/input_data/trnsys/NewFileTemplate.d18",
        trnsidf_exe='docker/trnsidf/trnsidf.exe') for file in files}

    result = parallel_process(in_dict, convert_idf_to_trnbuild, 4,
                              use_kwargs=True)
    [print(a) for a in result.values() if isinstance(a, Exception)]
    assert not any(isinstance(a, Exception) for a in result.values())


@pytest.mark.win32
@pytest.mark.xfail("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
                   reason="Skipping this test on Travis CI.")
def test_trnbuild_idf_win32(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    res = trnbuild_idf(idf_file, template=template, nonum=True)

    assert res


@pytest.mark.darwin
@pytest.mark.linux
@pytest.mark.xfail("TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
                   reason="Skipping this test on Travis CI.")
def test_trnbuild_idf_darwin_or_linux(config):
    idf_file = "tests/input_data/trnsys/Building.idf"
    template = "tests/input_data/trnsys/NewFileTemplate.d18"
    trnsidf_exe = "docker/trnsidf/trnsidf.exe"
    res = trnbuild_idf(idf_file, template=template, dck=True, nonum=False,
                       refarea=False, volume=False, capacitance=True,
                       trnsidf_exe=trnsidf_exe)

    assert res
