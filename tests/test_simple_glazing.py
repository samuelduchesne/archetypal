import os
import shutil

import matplotlib as mpl
import pytest
import numpy as np

import archetypal as pu
from archetypal.simple_glazing import calc_simple_glazing


@pytest.mark.parametrize('t_vis', [0.1, None, 0.9])
@pytest.mark.parametrize('u_value', np.linspace(0.1, 7, 10))
@pytest.mark.parametrize('shgc', np.linspace(0.1, 1, 10))
def test_glazing(shgc, u_value, t_vis):
    calc_simple_glazing(shgc, u_value, t_vis)


@pytest.mark.parametrize('another', [
    calc_simple_glazing(0.5, 2.2, 0.21),
    calc_simple_glazing(0.6, 2.2),
    calc_simple_glazing(0.8, 2.2, 0.35),
    calc_simple_glazing(1.2, 0.1, 10),
])
def test_glazing_unequal(another):
    t1 = calc_simple_glazing(0.6, 2.2, 0.21)
    assert t1 != another


def test_simple_glazing_system_equal():
    dict = calc_simple_glazing(0.6, 2.2, 0.21)
    assert dict['Conductivity'] == 0.11992503503877955


def test_simple_glazing_value_error():
    # Should raise an error since u-value is higher than 7
    with pytest.raises(ValueError):
        calc_simple_glazing(1.2, 8, 10)
