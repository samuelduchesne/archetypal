import glob
import os
import shutil
import sys

import pytest

import archetypal as ar


@pytest.fixture(scope='session')
def fresh_start():
    """# remove the tests/temp folder if it already exists so we
    start fresh with tests. Needs to be called after `config`"""
    settings = [ar.settings.cache_folder, ar.settings.data_folder,
                ar.settings.imgs_folder]
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
    """# remove the tests/temp folder if it already exists so we
    start fresh with tests"""
    # request is a special parameter known to pytest. It passes whatever is in
    # params=do. Ids are there to give the test a human readable name.
    dirs = [ar.settings.data_folder, ar.settings.cache_folder,
            ar.settings.imgs_folder]
    if request.param:
        for dir in dirs:
            if os.path.exists(dir):
                try:
                    shutil.rmtree(dir)
                finally:
                    assert not os.path.exists(dir)


samples_ = ['regular', 'umi_samples']  # ['problematic', 'regular',


# 'umi_samples']


@pytest.fixture(params=samples_, ids=samples_, scope='session')
def idf_source(request):
    return glob.glob('tests/input_data/{}/*.idf'.format(request.param))


@pytest.fixture(scope='session')
def config():
    ar.config(log_console=True, log_file=True, use_cache=True,
              data_folder='tests/.temp/data', logs_folder='tests/.temp/logs',
              imgs_folder='tests/.temp/imgs', cache_folder='tests/.temp/cache',
              umitemplate='tests/input_data/umi_samples'
                          '/BostonTemplateLibrary_2.json')


# List fixtures that are located outiside of conftest.py so that they can be
# used in other tests
pytest_plugins = [
    "tests.test_dataportals",
]

ALL = set("darwin linux win32".split())


def pytest_runtest_setup(item):
    supported_platforms = ALL.intersection(
        mark.name for mark in item.iter_markers())
    plat = sys.platform
    if supported_platforms and plat not in supported_platforms:
        pytest.skip("cannot run on platform %s" % (plat))
