import matplotlib as mpl
# use agg backend so you don't need a display on travis-ci
import pytest

import archetypal as ar
from archetypal import copy_file, CalledProcessError

mpl.use('Agg')

# configure archetypal
ar.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../data/BostonTemplateLibrary.json')


# given, when, then
# or
# arrange, act, assert

def test_small_home_data(fresh_start):
    file = './input_data/regular/AdultEducationCenter.idf'
    file = copy_file(file)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(file, wf, expandobjects=True, verbose='q',
                        prep_outputs=True, design_day=True)


def test_necb(scratch_then_cache):
    import glob
    files = glob.glob("/Users/samuelduchesne/Dropbox/Polytechnique/Doc"
                      "/software/archetypal-dev/data/necb"
                      "/NECB_2011_Montreal_idf/*idf")
    files = copy_file(files)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(files, wf, expandobjects=True, verbose='q',
                        design_day=True)


def test_std(scratch_then_cache):
    import glob
    files = glob.glob("./input_data/STD/*idf")
    files = copy_file(files)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(files, wf, expandobjects=True, annual=False,
                        verbose='q', prep_outputs=True, design_day=True,
                        output_report='sql')


@pytest.mark.parametrize('as_dict', [True, False])
@pytest.mark.parametrize('processors', [1, -1])
def test_load_idf_asdict(as_dict, processors, fresh_start):
    """Will load an idf object"""

    file1 = './input_data/regular/5ZoneNightVent1.idf'
    file2 = './input_data/regular/AdultEducationCenter.idf'
    obj = ar.load_idf([file1, file2], as_dict=as_dict, processors=processors)
    if as_dict:
        assert isinstance(obj, dict)
    else:
        assert isinstance(obj, list)


@pytest.mark.parametrize('ep_version', ['8.9', None],
                         ids=['specific-ep-version', 'no-specific-ep-version'])
def test_run_olderv(fresh_start, ep_version):
    """Will run eplus on a file that needs to be upgraded with one that does
    not"""

    files = ['./input_data/problematic/nat_ventilation_SAMPLE0.idf',
             './input_data/regular/5ZoneNightVent1.idf']
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    files = copy_file(files)
    ar.run_eplus(files, wf, ep_version=ep_version, annual=True,
                 expandobjects=True, verbose='q', )


@pytest.mark.xfail(raises=CalledProcessError)
def test_run_olderv_problematic(fresh_start):
    """Will run eplus on a file that needs to be upgraded and that should
    fail. Will be ignored in the test suite"""

    file = './input_data/problematic/RefBldgLargeOfficeNew2004_v1.4_7' \
           '.2_5A_USA_IL_CHICAGO-OHARE.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    file = copy_file([file])[0]
    ar.run_eplus(file, wf, ep_version='8.9', annual=True,
                 expandobjects=True, verbose='q', prep_outputs=True)
