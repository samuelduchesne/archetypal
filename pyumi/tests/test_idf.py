################################################################################
# test_osmnx.py
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/gboeing/osmnx
################################################################################

import os
import shutil

import matplotlib as mpl
# use agg backend so you don't need a display on travis-ci
import pytest

mpl.use('Agg')

# remove the .temp folder if it already exists so we start fresh with tests
if os.path.exists('.temp'):
    shutil.rmtree('.temp')

import pyumi as pu

# configure OSMnx
pu.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../../data/BostonTemplateLibrary.json')


# given, when, then
# or
# arrange, act, assert


def test_small_home_data():
    file = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return pu.run_eplus(file, wf, expandobjects=True)


@pytest.mark.parametrize('processors', [0, 1, -1])
@pytest.mark.parametrize('expandobjects', [True, False])
@pytest.mark.parametrize('annual', [True, False])
def test_example_idf(processors, expandobjects, annual):
    file1 = './input_data/AdultEducationCenter.idf'
    file2 = './input_data/AdultEducationCenter.idf'
    wf = './input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
    return pu.run_eplus([file1, file2], wf, processors=processors, expandobjects=expandobjects, annual=annual)
