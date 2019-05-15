import os

import matplotlib as mpl
# use agg backend so you don't need a display on travis-ci
import pytest

import archetypal as ar
from archetypal import copy_file, CalledProcessError

mpl.use('Agg')

# configure archetypal
ar.config(log_console=True, log_file=True, use_cache=True,
          data_folder='tests/temp/data', logs_folder='tests/temp/logs',
          imgs_folder='tests/temp/imgs', cache_folder='tests/temp/cache',
          umitemplate='tests/input_data/umi_samples/BostonTemplateLibrary_2'
                      '.json')


# given, when, then
# or
# arrange, act, assert

def test_small_home_data(fresh_start):
    file = 'tests/input_data/regular/AdultEducationCenter.idf'
    file = copy_file(file)[0]
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(file, wf, expandobjects=True, verbose='q',
                        prep_outputs=True, design_day=True)


def test_necb(config):
    import glob
    files = glob.glob("tests/input_data/necb/*.idf")
    files = copy_file(files)
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          expandobjects=True, verbose='q',
                          design_day=True
                          ) for file in files}
    result = {file: ar.run_eplus(**rundict[file]) for file in files}

    assert not any(isinstance(a, Exception) for a in result.values())


def test_std(scratch_then_cache, config):
    import glob
    files = glob.glob("tests/input_data/STD/*idf")
    files = copy_file(files)
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          expandobjects=True, annual=True,
                          verbose='q', prep_outputs=True, design_day=False,
                          output_report='sql') for file in files}
    result = ar.parallel_process(rundict, ar.run_eplus, use_kwargs=True)

    assert not any(isinstance(a, Exception) for a in result.values())


def test_load_idf(config):
    """Will load an idf object"""

    files = ['tests/input_data/regular/5ZoneNightVent1.idf',
             'tests/input_data/regular/AdultEducationCenter.idf']

    obj = {os.path.basename(file): ar.load_idf(file)
           for file in files}
    assert isinstance(obj, dict)


@pytest.mark.parametrize('ep_version', ['8-9-0', None],
                         ids=['specific-ep-version', 'no-specific-ep-version'])
def test_run_olderv(fresh_start, ep_version):
    """Will run eplus on a file that needs to be upgraded with one that does
    not"""

    files = ['tests/input_data/problematic/nat_ventilation_SAMPLE0.idf',
             'tests/input_data/regular/5ZoneNightVent1.idf']
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    files = copy_file(files)
    rundict = {file: dict(eplus_file=file, weather_file=wf,
                          ep_version=ep_version, annual=True, prep_outputs=True,
                          expandobjects=True, verbose='q', output_report='sql')
               for file in files}
    result = {file: ar.run_eplus(**rundict[file]) for file in files}


@pytest.mark.xfail(raises=(CalledProcessError, FileNotFoundError))
def test_run_olderv_problematic(fresh_start):
    """Will run eplus on a file that needs to be upgraded and that should
    fail. Will be ignored in the test suite"""

    file = 'tests/input_data/problematic/RefBldgLargeOfficeNew2004_v1.4_7' \
           '.2_5A_USA_IL_CHICAGO-OHARE.idf'
    wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    file = copy_file([file])[0]
    ar.run_eplus(file, wf, ep_version='8-9-0', annual=True,
                 expandobjects=True, verbose='q', prep_outputs=True)
