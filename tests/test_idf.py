import matplotlib as mpl
# use agg backend so you don't need a display on travis-ci
import pytest

import archetypal as ar
from archetypal import copy_file

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


def test_necb(config, fresh_start):
    import glob
    files = glob.glob("/Users/samuelduchesne/Dropbox/Polytechnique/Doc"
                      "/software/archetypal-dev/data/necb"
                      "/NECB_2011_Montreal_idf/*idf")
    files = copy_file(files)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(files, wf, expandobjects=True, verbose='q',
                        design_day=True)


def test_std(config, fresh_start):
    import glob
    files = glob.glob("./input_data/STD/*idf")
    files = copy_file(files)
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return ar.run_eplus(files, wf, expandobjects=True, annual=True,
                        verbose='q', prep_outputs=True, design_day=True)


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


def test_run_olderv(fresh_start):
    """Will run eplus on a file that needs to be upgraded"""

    file = './input_data/problematic/nat_ventilation_SAMPLE0.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    ar.run_eplus(file, wf, ep_version='8.9', annual=True,
                 expandobjects=True, verbose='q', )


def test_run(scratch_then_cache):
    f1 = './input_data/umi_samples/nat_ventilation_SAMPLE0.idf'
    f2 = './input_data/umi_samples' \
         '/no_shed_ventilation_and_no_mech_ventilation_SAMPLE0.idf'
    f3 = './input_data/umi_samples/no_shed_ventilation_SAMPLE0.idf'
    f4 = './input_data/umi_samples/shed_ventilation_SAMPLE0.idf'

    files = copy_file([f1, f2, f3, f4])
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    sql = ar.run_eplus(files, wf, verbose='q',
                       expandobjects=True, annual=True, processors=-1)
    np = ar.nominal_people(sql)
    # zc = ar.zone_conditioning(sql)
    # print(zc)
