"""Temporary bridges over idfkit gaps for UMI translation, each removed when its upstream item is released.

Removal conditions:

- `equivalent_glazing_layer` (**UP-10**): delete when idfkit releases UP-10 (T072), and call
  idfkit's function from `archetypal.umi.rules.windows` instead. The test
  `tests/unit/umi/test_rules_windows.py::test_remove_bridge_once_idfkit_releases_up10` fails on
  that day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = ["EquivalentGlazingLayer", "equivalent_glazing_layer"]

MAX_U_FACTOR = 7.0
"""The largest U-factor (W/m2-K) `WindowMaterial:SimpleGlazingSystem` accepts."""

# U-factor bounds (W/m2-K) of EnergyPlus's interpolation between its correlations.
_U_LOW = 3.4
_U_HIGH = 4.5
# SHGC bounds of the piecewise solar transmittance correlations.
_SHGC_BREAK_HIGH_U = 0.7206
_SHGC_BREAK_LOW_U = 0.15
# EnergyPlus's thermal infrared properties of the equivalent layer.
_IR_EMISSIVITY = 0.84


@dataclass(frozen=True, slots=True)
class EquivalentGlazingLayer:
    """The single glazing layer EnergyPlus simulates for a simple-glazing window.

    The fields follow the proposed `idfkit.thermal.EquivalentGlazingLayer` of UP-10.

    Attributes:
        thickness: Layer thickness (m).
        conductivity: Layer conductivity (W/m-K).
        solar_transmittance: Solar transmittance at normal incidence.
        front_solar_reflectance: Front solar reflectance at normal incidence.
        back_solar_reflectance: Back solar reflectance at normal incidence.
        visible_transmittance: Visible transmittance at normal incidence.
        front_visible_reflectance: Front visible reflectance at normal incidence.
        back_visible_reflectance: Back visible reflectance at normal incidence.
        infrared_transmittance: Thermal infrared transmittance.
        front_infrared_emissivity: Front thermal infrared hemispherical emissivity.
        back_infrared_emissivity: Back thermal infrared hemispherical emissivity.
    """

    thickness: float
    conductivity: float
    solar_transmittance: float
    front_solar_reflectance: float
    back_solar_reflectance: float
    visible_transmittance: float
    front_visible_reflectance: float
    back_visible_reflectance: float
    infrared_transmittance: float = 0.0
    front_infrared_emissivity: float = _IR_EMISSIVITY
    back_infrared_emissivity: float = _IR_EMISSIVITY


def _interpolate(u_factor: float, low_u_value: float, high_u_value: float) -> float:
    """Return EnergyPlus's solar transmittance for `u_factor` between its two correlations.

    `low_u_value` holds below 3.4 W/m2-K, `high_u_value` above 4.5 W/m2-K, and the value is
    linear in U between them.
    """
    if u_factor > _U_HIGH:
        return high_u_value
    if u_factor < _U_LOW:
        return low_u_value
    return (u_factor - _U_LOW) / (_U_HIGH - _U_LOW) * (high_u_value - low_u_value) + low_u_value


def _film(u_factor: float, low_u_value: float, high_u_value: float) -> float:
    """Return EnergyPlus's summer film resistance for `u_factor` between its two correlations.

    Between 3.4 and 4.5 W/m2-K, EnergyPlus 24.2 computes `f * (low - high) + low`, with
    `f = (U - 3.4) / 1.1`: not a linear interpolation, so the value leaves the interval
    between the two correlations and jumps at 4.5 W/m2-K. The bridge reproduces EnergyPlus,
    since the point is to write the layer EnergyPlus simulates.
    """
    if u_factor > _U_HIGH:
        return high_u_value
    if u_factor < _U_LOW:
        return low_u_value
    return (u_factor - _U_LOW) / (_U_HIGH - _U_LOW) * (low_u_value - high_u_value) + low_u_value


def _check(name: str, value: float, *, upper: float, upper_inclusive: bool) -> None:
    within = 0.0 < value <= upper if upper_inclusive else 0.0 < value < upper
    if not (math.isfinite(value) and within):
        bound = "<=" if upper_inclusive else "<"
        msg = f"{name} must be > 0 and {bound} {upper}, as WindowMaterial:SimpleGlazingSystem requires; got {value!r}"
        raise ValueError(msg)


def equivalent_glazing_layer(
    u_factor: float, shgc: float, visible_transmittance: float | None = None
) -> EquivalentGlazingLayer:
    """Return the glazing layer EnergyPlus's simple window model builds from U, SHGC and VT.

    The steps are those of the EnergyPlus Engineering Reference, "Window Calculation Module",
    section "Simple Window Model", as EnergyPlus 24.2 implements them
    (`MaterialGlass::SetupSimpleWindowGlazingSystem`), in its order:

    1. inside and outside film resistances as functions of U, and the layer's resistance as
       `1/U` minus both;
    2. thickness and conductivity from the layer's resistance;
    3. solar transmittance from SHGC and U, interpolating between the low-U and high-U
       correlations for 3.4 <= U <= 4.5 W/m2-K;
    4. solar reflectance (front and back) from the inward-flowing fraction of absorbed solar,
       with EnergyPlus's summer film resistances (see `_film` for its 3.4-4.5 W/m2-K range);
    5. visible transmittance from VT and visible reflectances from it, each reflectance capped
       at `0.999 - VT`; without VT the solar values are used, as EnergyPlus does.

    The result matches the layer EnergyPlus writes to its `.eio` file for the same
    `WindowMaterial:SimpleGlazingSystem` (checked by `verification/umi/simple_glazing.py`).

    Removal condition: delete when idfkit releases UP-10 (T072).

    Args:
        u_factor: U-factor with films (W/m2-K), as in `WindowMaterial:SimpleGlazingSystem`.
        shgc: Solar heat gain coefficient at normal incidence.
        visible_transmittance: Visible transmittance at normal incidence, or `None`.

    Returns:
        The equivalent layer.

    Raises:
        ValueError: An input is outside the range EnergyPlus accepts (U in (0, 7], SHGC and VT
            in (0, 1)).
    """
    _check("u_factor", u_factor, upper=MAX_U_FACTOR, upper_inclusive=True)
    _check("shgc", shgc, upper=1.0, upper_inclusive=False)
    if visible_transmittance is not None:
        _check("visible_transmittance", visible_transmittance, upper=1.0, upper_inclusive=False)

    # Step 1: film resistances and the layer's own resistance.
    if u_factor < 5.85:  # noqa: PLR2004 - EnergyPlus's breakpoint
        r_inside = 1.0 / (0.359073 * math.log(u_factor) + 6.949915)
    else:
        r_inside = 1.0 / (1.788041 * u_factor - 2.886625)
    r_outside = 1.0 / (0.025342 * u_factor + 29.163853)
    r_layer = max(1.0 / u_factor - r_inside - r_outside, 0.001)

    # Step 2: thickness and conductivity.
    thickness = 0.002 if 1.0 / r_layer > 7.0 else 0.05914 - 0.00714 / r_layer  # noqa: PLR2004
    conductivity = thickness / r_layer

    # Step 3: solar transmittance.
    t_high_u = 0.939998 * shgc**2 + 0.20332 * shgc if shgc < _SHGC_BREAK_HIGH_U else 1.30415 * shgc - 0.30515
    t_low_u = 0.41040 * shgc if shgc <= _SHGC_BREAK_LOW_U else 0.085775 * shgc**2 + 0.963954 * shgc - 0.084958
    solar_transmittance = max(_interpolate(u_factor, t_low_u, t_high_u), 0.0)

    # Step 4: solar reflectance from the inward-flowing fraction.
    delta = shgc - solar_transmittance
    r_inside_solar = _film(
        u_factor,
        1.0 / (199.8208128 * delta**3 - 90.639733 * delta**2 + 19.737055 * delta + 6.766575),
        1.0 / (29.436546 * delta**3 - 21.943415 * delta**2 + 9.945872 * delta + 7.426151),
    )
    r_outside_solar = _film(
        u_factor,
        1.0 / (5.763355 * delta + 20.541528),
        1.0 / (2.225824 * delta + 20.577080),
    )
    inflow_fraction = (r_outside_solar + 0.5 * r_layer) / (r_outside_solar + r_layer + r_inside_solar)
    solar_absorptance = delta / inflow_fraction
    solar_reflectance = 1.0 - solar_transmittance - solar_absorptance

    # Step 5: visible properties.
    if visible_transmittance is None:
        visible = solar_transmittance
        front_visible = back_visible = solar_reflectance
    else:
        visible = visible_transmittance
        back_visible = -0.7409 * visible**3 + 1.6531 * visible**2 - 1.2299 * visible + 0.4545
        front_visible = -0.0622 * visible**3 + 0.4277 * visible**2 - 0.4169 * visible + 0.2399
        # EnergyPlus caps each reflectance so that transmittance plus reflectance stays below 1.
        if visible + back_visible >= 1.0:
            back_visible = 0.999 - visible
        if visible + front_visible >= 1.0:
            front_visible = 0.999 - visible

    return EquivalentGlazingLayer(
        thickness=thickness,
        conductivity=conductivity,
        solar_transmittance=solar_transmittance,
        front_solar_reflectance=solar_reflectance,
        back_solar_reflectance=solar_reflectance,
        visible_transmittance=visible,
        front_visible_reflectance=front_visible,
        back_visible_reflectance=back_visible,
    )
