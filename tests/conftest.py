import glob
import os
import shutil

import pytest


@pytest.fixture(scope='session')
def fresh_start():
    """# remove the .temp folder if it already exists so we
    start fresh with tests"""
    if os.path.exists('.temp'):
        shutil.rmtree('.temp')
        assert not os.path.exists('.temp')


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


@pytest.fixture(params=['problematic', 'regular', 'umi_samples'],
                ids=['problematic', 'regular', 'umi_samples'], scope='session')
def idf_source(request):
    return glob.glob('./input_data/{}/*.idf'.format(request.param))
