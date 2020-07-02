import glob
import os
import shutil
import sys

import pytest

import archetypal as ar


# Parametrization of the fixture scratch_then_cache. The following array
# tells pytest to use True than False for all tests that use this fixture.
# This is very usefull to test the behavior of methods that use cached data
# or not.
do = [True, False]


@pytest.fixture(params=do, ids=["from_scratch", "from_cache"], scope="function")
def scratch_then_cache(request):
    """# remove the tests/temp folder if it already exists so we
    start fresh with tests"""
    # request is a special parameter known to pytest. It passes whatever is in
    # params=do. Ids are there to give the test a human readable name.
    dirs = [ar.settings.data_folder, ar.settings.cache_folder, ar.settings.imgs_folder]
    if request.param:
        for dir in dirs:
            if os.path.exists(dir):
                try:
                    shutil.rmtree(dir)
                finally:
                    assert not os.path.exists(dir)


samples_ = ["regular", "umi_samples"]  # ['problematic', 'regular',


# 'umi_samples']


@pytest.fixture(params=samples_, ids=samples_, scope="session")
def idf_source(request):
    return glob.glob("tests/input_data/{}/*.idf".format(request.param))


@pytest.fixture(scope="session")
def config():
    ar.config(
        data_folder="tests/.temp/data",
        logs_folder="tests/.temp/logs",
        imgs_folder="tests/.temp/images",
        cache_folder="tests/.temp/cache",
        use_cache=True,
        log_file=True,
        log_console=True,
        umitemplate="tests/input_data/umi_samples/BostonTemplateLibrary_2.json",
    )


@pytest.fixture(scope="class")
def clean_config(config):
    """calls config fixture and clears default folders"""

    dirs = [ar.settings.data_folder, ar.settings.cache_folder, ar.settings.imgs_folder]
    for dir in dirs:
        dir.rmdir_p()
        assert not dir.exists()


# List fixtures that are located outiside of conftest.py so that they can be
# used in other tests
pytest_plugins = ["tests.test_dataportals"]

ALL = set("darwin linux win32".split())


def pytest_runtest_setup(item):
    supported_platforms = ALL.intersection(mark.name for mark in item.iter_markers())
    plat = sys.platform
    if supported_platforms and plat not in supported_platforms:
        pytest.skip("cannot run on platform %s" % (plat))


# dynamically define files to be ignored
collect_ignore = ["test_core.py"]


def get_platform():
    """Returns the MacOS release number as tuple of ints"""
    import platform

    release, versioninfo, machine = platform.mac_ver()
    release_split = release.split(".")
    return tuple(map(safe_int_cast, release_split))


def safe_int_cast(val, default=0):
    """Safely casts a value to an int"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default
