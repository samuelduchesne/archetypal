import matplotlib as mpl
# use agg backend so you don't need a display on travis-ci
import pytest

import archetypal as pu

mpl.use('Agg')

# configure archetypal
pu.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../data/BostonTemplateLibrary.json')


# given, when, then
# or
# arrange, act, assert

def test_small_home_data():
    file = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return pu.run_eplus(file, wf, expandobjects=True, annual=True)


@pytest.mark.parametrize('processors', [0, 1, -1])
@pytest.mark.parametrize('annual', [True, False])
@pytest.mark.parametrize('expandobjects', [True, False])
def test_example_idf(processors, expandobjects, annual):
    """Will run all combinations of parameters defined above"""

    file1 = './input_data/AdultEducationCenter.idf'
    file2 = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return pu.run_eplus([file1, file2], wf, processors=processors,
                        annual=annual, expandobjects=expandobjects)


@pytest.mark.parametrize('as_dict', [True, False])
@pytest.mark.parametrize('processors', [-1, 0, 1])
def test_load_idf_asdict(as_dict, processors):
    """Will load an idf object"""

    file1 = './input_data/AdultEducationCenter.idf'
    file2 = './input_data/AdultEducationCenter.idf'
    obj = pu.load_idf([file1, file2], as_dict=as_dict, processors=processors)
    if as_dict:
        assert isinstance(obj, dict)
    else:
        assert isinstance(obj, list)
