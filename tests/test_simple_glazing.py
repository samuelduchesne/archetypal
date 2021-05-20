import pytest

from archetypal.simple_glazing import calc_simple_glazing


def test_glazing():
    """Simulates a Double Clear Air Glazing System (Window.exe v.7.5)"""
    res = calc_simple_glazing(0.704, 2.703, 0.786)
    print(res["Thickness"])


def test_absurd():
    """Simulates a Double Clear Air Glazing System (Window.exe v.7.5). Will
    raise an error when checking Visible Transmittance at Normal Incidence +
    Back Side Visible Reflectance at Normal Incidence not <= 1.0"""
    with pytest.warns(UserWarning):
        calc_simple_glazing(0.704, 2.703, 0.9)


@pytest.mark.parametrize(
    "another",
    [
        calc_simple_glazing(0.5, 2.2, 0.21),
        calc_simple_glazing(0.6, 2.2),
        calc_simple_glazing(0.8, 2.2, 0.35),
        calc_simple_glazing(1.2, 0.1, 10),
    ],
)
def test_glazing_unequal(another):
    t1 = calc_simple_glazing(0.6, 2.2, 0.21)
    assert t1 != another


def test_simple_glazing_system_equal():
    dict = calc_simple_glazing(0.6, 2.2, 0.21)
    assert dict["Conductivity"] == 0.11992503503877955


def test_simple_glazing_value_error():
    # Should raise an error since u-value is higher than 7
    with pytest.raises(ValueError):
        calc_simple_glazing(1.2, 8, 10)
