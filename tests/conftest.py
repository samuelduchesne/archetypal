import glob
import os
import shutil

import pytest

import archetypal as ar
import osmnx as ox


@pytest.fixture(scope='session')
def fresh_start():
    """# remove the .temp folder if it already exists so we
    start fresh with tests"""
    settings = [ar.settings.cache_folder, ar.settings.data_folder,
                    ar.settings.imgs_folder, ar.settings.logs_folder]
    for setting in settings:
        if os.path.exists(setting):
            shutil.rmtree(setting)
            assert not os.path.exists(setting)


# Parametrization of the fixture scratch_then_cache. The following array
# tells pytest to use True than False for all tests that use this fixture.
# This is very usefull to test the behavior of methods that use cached data
# or not.
do = [True, False]


@pytest.fixture(params=do, ids=['from_scratch', 'from_cache'],
                scope='function')
def scratch_then_cache(request):
    """# remove the .temp folder if it already exists so we
    start fresh with tests"""
    # request is a spacial paramter known to pytest. ot passes whatever is in
    # params=do. Ids are there to give the test a human readable name.
    if request.param:
        if os.path.exists('.temp'):
            shutil.rmtree('.temp')
            assert not os.path.exists('.temp')


samples_ = ['regular', 'umi_samples']  # ['problematic', 'regular',


# 'umi_samples']


@pytest.fixture(params=samples_, ids=samples_, scope='session')
def idf_source(request):
    return glob.glob('./input_data/{}/*.idf'.format(request.param))


@pytest.fixture(scope='session')
def config():
    ar.config(log_console=True, log_file=True, use_cache=True,
              data_folder='.temp/data', logs_folder='.temp/logs',
              imgs_folder='.temp/imgs', cache_folder='.temp/cache',
              umitemplate='../data/BostonTemplateLibrary.json')


@pytest.fixture()
def ox_config(config):
    ox.config(log_console=ar.settings.log_console, log_file=ar.settings.log_file,
              use_cache=ar.settings.use_cache,
              data_folder=ar.settings.data_folder, logs_folder=ar.settings.logs_folder,
              imgs_folder=ar.settings.imgs_folder,
              cache_folder=ar.settings.cache_folder,
              log_name=ar.settings.log_name)


# List fixtures that are located outiside of conftest.py so that they can be
# used in other tests
pytest_plugins = [
    "tests.test_dataportals",
]
