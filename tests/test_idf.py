import os
import random
import subprocess

import archetypal as ar
import matplotlib as mpl

# use agg backend so you don't need a display on travis-ci
import pytest
from path import Path

from archetypal import EnergyPlusProcessError

mpl.use("Agg")


# given, when, then
# or
# arrange, act, assert


def test_small_home_data(config, fresh_start):
    file = "tests/input_data/regular/AdultEducationCenter.idf"
    file = ar.copy_file(file)
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    return ar.run_eplus(
        file, wf, prep_outputs=True, design_day=True, expandobjects=True, verbose="q"
    )


def test_necb(config):
    """Test all necb files with design_day = True"""
    from archetypal import parallel_process

    necb_dir = Path("tests/input_data/necb")
    files = necb_dir.glob("*.idf")
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    rundict = {
        file: dict(
            eplus_file=file,
            weather_file=wf,
            expandobjects=True,
            verbose="q",
            design_day=True,
            output_report="sql",
        )
        for file in files
    }
    result = parallel_process(rundict, ar.run_eplus, use_kwargs=True)

    assert not any(isinstance(a, Exception) for a in result.values())


def test_load_idf(config):
    """Will load an idf object"""

    files = [
        "tests/input_data/regular/5ZoneNightVent1.idf",
        "tests/input_data/regular/AdultEducationCenter.idf",
    ]

    obj = {os.path.basename(file): ar.load_idf(file) for file in files}
    assert isinstance(obj, dict)


def test_load_old(config):
    files = [
        "tests/input_data/problematic/nat_ventilation_SAMPLE0.idf",
        "tests/input_data/regular/5ZoneNightVent1.idf",
    ]

    obj = {os.path.basename(file): ar.load_idf(file) for file in files}

    assert not any(isinstance(a, Exception) for a in obj.values())


@pytest.mark.parametrize(
    "ep_version",
    [ar.ep_version, None],
    ids=["specific-ep-version", "no-specific-ep-version"],
)
def test_run_olderv(config, fresh_start, ep_version):
    """Will run eplus on a file that needs to be upgraded with one that does
    not"""
    ar.settings.use_cache = False
    files = [
        "tests/input_data/problematic/nat_ventilation_SAMPLE0.idf",
        "tests/input_data/regular/5ZoneNightVent1.idf",
    ]
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    files = ar.copy_file(files)
    rundict = {
        file: dict(
            eplus_file=file,
            weather_file=wf,
            ep_version=ep_version,
            annual=True,
            prep_outputs=True,
            expandobjects=True,
            verbose="q",
            output_report="sql",
        )
        for file in files
    }
    result = {file: ar.run_eplus(**rundict[file]) for file in files}


@pytest.mark.xfail(
    raises=(subprocess.CalledProcessError, FileNotFoundError, EnergyPlusProcessError)
)
def test_run_olderv_problematic(config, fresh_start):
    """Will run eplus on a file that needs to be upgraded and that should
    fail. Will be ignored in the test suite"""

    file = (
        "tests/input_data/problematic/RefBldgLargeOfficeNew2004_v1.4_7"
        ".2_5A_USA_IL_CHICAGO-OHARE.idf"
    )
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    file = ar.copy_file([file])
    ar.run_eplus(
        file, wf, prep_outputs=True, annual=True, expandobjects=True, verbose="q"
    )


def test_run_eplus_from_idf(config, fresh_start):
    file = "tests/input_data/regular/5ZoneNightVent1.idf"
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

    idf = ar.load_idf(file, weather_file=wf)
    sql = idf.run_eplus(output_report="sql")

    assert sql


@pytest.mark.parametrize(
    "archetype, area",
    [
        ("FullServiceRestaurant", 511),
        pytest.param(
            "Hospital",
            22422,
            marks=pytest.mark.xfail(reason="Difference cannot be explained"),
        ),
        ("LargeHotel", 11345),
        ("LargeOffice", 46320),
        ("MediumOffice", 4982),
        ("MidriseApartment", 3135),
        ("Outpatient", 3804),
        ("PrimarySchool", 6871),
        ("QuickServiceRestaurant", 232),
        ("SecondarySchool", 19592),
        ("SmallHotel", 4013),
        ("SmallOffice", 511),
        pytest.param(
            "RetailStandalone",
            2319,
            marks=pytest.mark.xfail(reason="Difference cannot be explained"),
        ),
        ("RetailStripmall", 2090),
        pytest.param(
            "Supermarket",
            4181,
            marks=pytest.mark.skip("Supermarket " "missing from " "BTAP " "database"),
        ),
        ("Warehouse", 4835),
    ],
)
def test_area(archetype, area):
    """Test the conditioned_area property against published values
    desired values taken from https://github.com/canmet-energy/btap"""
    import numpy as np
    from archetypal import load_idf

    idf_file = Path("tests/input_data/necb/").glob("*{}*.idf".format(archetype))
    idf = load_idf(next(iter(idf_file)))
    np.testing.assert_almost_equal(actual=idf.area_conditioned, desired=area, decimal=0)


def test_partition_ratio():
    from archetypal import load_idf

    idf_file = Path("tests/input_data/necb/").glob("*LargeOffice*.idf")
    idf = load_idf(next(iter(idf_file)))
    print(idf.partition_ratio)


def test_space_cooling_profile(config):
    from archetypal import load_idf

    file = "tests/input_data/regular/AdultEducationCenter.idf"
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

    idf = load_idf(file, None, weather_file=wf)

    assert not idf.space_cooling_profile().empty


def test_space_heating_profile(config):
    from archetypal import load_idf

    file = "tests/input_data/necb/NECB 2011-Warehouse-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

    idf = load_idf(file, None, weather_file=wf)

    assert not idf.space_heating_profile().empty
