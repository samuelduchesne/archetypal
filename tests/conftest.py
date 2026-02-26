import os
import sys
from pathlib import Path

import pytest

# Parametrization of the fixture scratch_then_cache. The following array
# tells pytest to use True than False for all tests that use this fixture.
# This is very usefull to test the behavior of methods that use cached data
# or not.
from archetypal import settings, utils

data_dir = Path(__file__).parent / "input_data"


@pytest.fixture(params=[True, False], ids=["from_scratch", "from_cache"], scope="function")
def scratch_then_cache(request):
    """# remove the tests/temp folder if it already exists so we
    start fresh with tests"""
    # request is a special parameter known to pytest. It passes whatever is in
    # params=do. Ids are there to give the test a human-readable name.
    if request.param:
        dirs = [
            settings.data_folder,
            settings.cache_folder,
            settings.imgs_folder,
        ]
        for d in dirs:
            d.rmtree_p()


@pytest.fixture(scope="session")
def config():
    utils.config(
        data_folder=os.getenv("ARCHETYPAL_DATA") or "tests/.temp/data",
        logs_folder=os.getenv("ARCHETYPAL_LOGS") or "tests/.temp/logs",
        imgs_folder=os.getenv("ARCHETYPAL_IMAGES") or "tests/.temp/images",
        cache_folder=os.getenv("ARCHETYPAL_CACHE") or "tests/.temp/cache",
        cache_responses=True,
        log_file=False,
        log_console=True,
        debug=True,
    )


@pytest.fixture(scope="class")
def clean_config(config):
    """calls config fixture and clears default folders"""

    dirs = [settings.data_folder, settings.cache_folder, settings.imgs_folder, settings.logs_folder]
    for d in dirs:
        d.rmtree_p()


# List fixtures that are located outside of conftest.py so that they can be
# used in other tests
pytest_plugins = []

ALL = set("darwin linux win32".split())


def pytest_runtest_setup(item):
    supported_platforms = ALL.intersection(mark.name for mark in item.iter_markers())
    plat = sys.platform
    if supported_platforms and plat not in supported_platforms:
        pytest.skip(f"cannot run on platform {plat}")


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


def pytest_addoption(parser):
    parser.addoption("--runslow", action="store_true", default=False, help="run slow tests")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
