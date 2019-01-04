import os
import shutil

import pytest


@pytest.fixture(scope='session')
def cleanup():
    """# remove the .temp folder if it already exists so we start fresh with tests"""
    if os.path.exists('.temp'):
        shutil.rmtree('.temp')
        assert not os.path.exists('.temp')
