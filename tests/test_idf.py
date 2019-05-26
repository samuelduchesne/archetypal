import os
import random

import matplotlib as mpl
import pytest
from path import Path

import archetypal as ar
from archetypal import EnergyPlusProcessError, parallel_process

# use agg backend so you don't need a display on travis-ci
mpl.use('Agg')


# given, when, then
# or
# arrange, act, assert

@pytest.mark.parametrize('report', ['sql', 'htm'],
                         ids=['sql', 'html'])
def test_small_home_data(config, report):
    file = 'tests/input_data/regular/AdultEducationCenter.idf'
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(file, wf, expandobjects=True, verbose='v',
                        prep_outputs=True, design_day=True,
                        output_report=report)


def test_necb(config):
    """Test one of the necb files"""
    import glob
    file = random.choice(glob.glob("tests/input_data/necb/*.idf"))
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          expandobjects=True, verbose='v',
                          design_day=True, output_report='sql',
                          ) for file in [file]}
    result = {file: ar.run_eplus(**rundict[file]) for file in [file]}

    assert not any(isinstance(a, Exception) for a in result.values())


def test_necb_parallel(config):
    """Test one of the necb files"""
    files = Path("tests/input_data/necb").glob("*.idf")
    wf = Path('tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw')
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          expandobjects=True, verbose='v',
                          design_day=True, output_report='sql',
                          ) for file in files}
    result = parallel_process(rundict, ar.run_eplus, use_kwargs=True)

    assert not any(isinstance(a, Exception) for a in result.values())


def test_load_idf(config):
    """Will load an idf object"""

    files = ['tests/input_data/regular/5ZoneNightVent1.idf',
             'tests/input_data/regular/AdultEducationCenter.idf']

    obj = {os.path.basename(file): ar.load_idf(file)
           for file in files}
    assert isinstance(obj, dict)


def test_load_old(config):
    files = ['tests/input_data/problematic/nat_ventilation_SAMPLE0.idf',
             'tests/input_data/regular/5ZoneNightVent1.idf']

    obj = {os.path.basename(file): ar.load_idf(file)
           for file in files}

    assert not any(isinstance(a, Exception) for a in obj.values())


@pytest.mark.parametrize('ep_version', [ar.ep_version, None],
                         ids=['specific-ep-version', 'no-specific-ep-version'])
def test_run_olderv(config, ep_version):
    """Will run eplus on a file that needs to be upgraded with one that does
    not"""

    files = ['tests/input_data/problematic/nat_ventilation_SAMPLE0.idf',
             'tests/input_data/regular/5ZoneNightVent1.idf']
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          ep_version=ep_version, annual=True, prep_outputs=True,
                          expandobjects=True, verbose='q', output_report='sql')
               for file in files}
    result = {file: ar.run_eplus(**rundict[file]) for file in files}

    assert not any(isinstance(a, Exception) for a in result.values())


@pytest.mark.xfail(raises=(EnergyPlusProcessError))
def test_run_olderv_problematic(config):
    """Will run eplus on a file that needs to be upgraded and that should
    fail. Will be ignored in the test suite"""

    file = 'tests/input_data/problematic/RefBldgLargeOfficeNew2004_v1.4_7' \
           '.2_5A_USA_IL_CHICAGO-OHARE.idf'
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    ar.run_eplus(file, wf, annual=True,
                 expandobjects=True, verbose='v', prep_outputs=True)
