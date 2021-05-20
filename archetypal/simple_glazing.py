################################################################################
# Module: simple_glazing.py
# Description: Python implementation of the EnergyPlus Simple Window Model
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import logging as lg
import math
import warnings

import numpy as np

from archetypal.utils import log


def calc_simple_glazing(shgc, u_factor, visible_transmittance=None):
    """Calculates the physical properties of an equivalent single pane of glass
    from the Solar Heat Gain Coefficient, the U-value and the Visible
    Transmittance.

    Args:
        shgc (double): The window's Solar Heat Gain Coefficient
        u_factor (double): The window's U-value
        visible_transmittance (double, optional): The window's visible
            transmittance. If none, the visible transmittance defaults to the
            solar transmittance t_sol.

    Returns:
        dict: A dictionary of properties for the simple glazing system.

    Hint:
        This is an implementation of the `Simple Window Model
        <https://bigladdersoftware.com/epx/docs/8-9/engineering-reference
        /window-calculation-module.html#simple-window-model>`_.

    """

    if isinstance(shgc, str):
        shgc = float(shgc)
    if isinstance(u_factor, str):
        u_factor = float(u_factor)
    if isinstance(visible_transmittance, str):
        try:
            visible_transmittance = float(visible_transmittance)
        except ValueError:
            visible_transmittance = None

    # Limits
    if u_factor > 7:
        raise ValueError(
            "The model cannot support glazing systems with a U higher than "
            "7.0 because  the thermal resistance of the film coefficients "
            "alone can provide this level of performance and  none of the "
            "various resistances can be negative."
        )

    dict = {}

    # Step 1. Determine glass-to-glass Resistance.

    # glass-to-glass resistance (R_l_w) is calculated using:
    R_l_w = r_l_w(u_factor)

    # Step 2. Determine Layer Thickness

    # The thickness of the equivalent layer in units of meters is calculated
    # using:
    Thickness = thickness(R_l_w)

    # Step 3. Determine Layer Thermal Conductivity

    # The effective thermal conductivity, `lambda_eff`, of the equivalent
    # layer is calculated using:
    Lambda_eff = lambda_eff(Thickness, R_l_w)

    # Step 4. Determine Layer Solar Transmittance

    # The layer’s solar transmittance at normal incidence, `T_sol`,
    # is calculated using correlations that are a function of SHGC and U-Factor.

    T_sol = t_sol(shgc, u_factor)

    # Step 5. Determine Layer Solar Reflectance

    R_i_s = r_i_s(shgc, T_sol, u_factor)
    R_o_s = r_o_s(shgc, T_sol, u_factor)
    R_s_f = r_s_f(T_sol, shgc, R_o_s, R_l_w, R_i_s)
    R_s_b = R_s_f  # Both are taken equal

    # The thermal absorptance, or emittance, is taken as 0.84 for both the
    # front and back and the longwave transmittance is 0.0

    # Step 6. Determine Layer Visible Properties
    # The user has the option of entering a value for visible transmittance
    # as one of the simple performance indices.
    # If the user does not enter a value, then the visible properties are the
    # same as the solar properties.
    if visible_transmittance:
        T_vis = visible_transmittance
    else:
        T_vis = T_sol

    R_vis_b = r_vis_b(T_vis)
    R_vis_f = r_vis_f(T_vis)

    # sanity checks
    if T_vis + R_vis_f >= 1.0:
        warnings.warn("T_vis + R_vis_f > 1", UserWarning)
        T_vis -= (T_vis + R_vis_f - 1) * 1.1
    if T_vis + R_vis_b >= 1.0:
        warnings.warn("T_vis + R_vis_b > 1", UserWarning)
        T_vis -= (T_vis + R_vis_b - 1) * 1.1

    # Last Step. Saving results to dict
    dict["SolarHeatGainCoefficient"] = shgc
    dict["UFactor"] = u_factor
    dict["Conductivity"] = Lambda_eff
    dict["Thickness"] = Thickness
    dict["SolarTransmittance"] = T_sol
    dict["SolarReflectanceFront"] = R_s_f
    dict["SolarReflectanceBack"] = R_s_b
    dict["IRTransmittance"] = 0.0
    dict["VisibleTransmittance"] = T_vis
    dict["VisibleReflectanceFront"] = R_vis_f
    dict["VisibleReflectanceBack"] = R_vis_b
    dict["IREmissivityFront"] = 0.84
    dict["IREmissivityBack"] = 0.84
    dict["DirtFactor"] = 1.0  # Clean glass

    dict["Cost"] = 0
    dict["Density"] = 2500
    dict["EmbodiedCarbon"] = 0
    dict["EmbodiedCarbonStdDev"] = 0
    dict["EmbodiedEnergy"] = 0
    dict["EmbodiedEnergyStdDev"] = 0
    dict["Life"] = 1
    dict["SubstitutionRatePattern"] = [1.0]
    dict["SubstitutionTimestep"] = 0
    dict["TransportCarbon"] = 0
    dict["TransportDistance"] = 0
    dict["TransportEnergy"] = 0
    dict["Type"] = "Uncoated"  # TODO Further investigation necessary

    dict["Comments"] = (
        "Properties calculated from Simple Glazing System with "
        "SHGC={:.3f}, UFactor={:.3f} and Tvis={:.3f}".format(shgc, u_factor, T_vis)
    )

    return dict


# region Step 1. Determine glass-to-glass Resistance
def r_i_w(u_factor):
    """The resistance of the interior film coefficient under standard winter
    conditions in units of m\ :sup:`2`\ K/W

    Args:
        u_factor: The U-value of the window including interior and exterior
        surface heat transfer coefficients

    Returns:
        The resistance of the interior film coefficient under standard winter
        conditions

    """
    if u_factor < 5.85:
        return 1 / (0.359073 * math.log(u_factor) + 6.949915)
    return 1 / (1.788041 * u_factor - 2.886625)


def r_o_w(u_factor):
    """The resistance of the exterior film coefficient under standard winter
    conditions in units of m\ :sup:`2`\ K/W

    Args:
        u_factor: The U-value of the window including interior and exterior
        surface heat transfer coefficients

    Returns:
        The resistance of the exterior film coefficient under standard winter
        conditions in units of

    """
    return 1 / (0.025342 * u_factor + 29.162853)


def r_l_w(u_factor):
    """The resisance of the bare window under winter conditions (without the
    film coefficients) in units of
    m\ :sup:`2`\ K/W.

    Args:
        u_factor: The U-value of the window including including interior and
        exterior surface heat transfer
        coefficients.

    Returns:
        The resisance of the bare window under winter conditions (without the
        film coefficients) in units of
        m\ :sup:`2`\ K/W.

    Warnings:
        The model cannot support glazing systems with a U-value higher than
        7.0 because the thermal resistance of
        the film coefficients alone can provide this level of performance and
        none of the various resistances
        can be negative.

    """
    if u_factor > 7.0:
        log(
            "The model cannot support glazing systems with a U-value higher "
            "than 7.0 because the thermal resistance "
            "of the film coefficients alone can provide this level of "
            "performance and none of the various resistances"
            "can be negative.",
            lg.WARNING,
        )
        pass
    return (1 / u_factor) - r_i_w(u_factor) - r_o_w(u_factor)


# endregion


# region Step 2. Determine Layer Thickness
def thickness(r_l_w):
    """The thickness of the equivalent layer in units of meters.

    Args:
        r_l_w (double): The resistance of the bare window under winter
            conditions (without the film coefficients) in units of m\ :sup:`2`\ K`/W.

    Returns:
        double: The thickness of the equivalent layer in units of meters

    """
    if 1 / r_l_w > 7.0:
        return 0.002
    return 0.05914 - 0.00714 / r_l_w


def lambda_eff(thickness, r_l_w):
    """The effective thermal conductivity of the equivalent layer in W/m-K.

    Args:
        thickness: The thickness of the equivalent layer in units of meters.
        r_l_w: The resisance of the bare window under winter conditions (
        without the film coefficients) in
            units of m\ :sup:`2`\ K/W.

    Returns:
        The effective thermal conductivity, λ\ :sub:`eff`, of the equivalent
        layer.

    """
    return thickness / r_l_w


# endregion

# region Step 4. Determine Layer Solar Transmittance
def t_sol_intermediate(shgc, u_factor):
    if u_factor >= 4.5 and shgc < 0.7206:
        return 0.939998 * shgc ** 2 + 0.20332 * shgc
    if u_factor >= 4.5 and shgc >= 0.7206:
        return 1.30415 * shgc - 0.30515
    if u_factor <= 3.4 and shgc <= 0.15:
        return 0.41040 * shgc
    if u_factor <= 3.4 and shgc > 0.15:
        return 0.085775 * shgc ** 2 + 0.963954 * shgc - 0.084958
    pass


def t_sol(shgc, u_factor):
    """The Solat Transmittance at normal incidence t_sol, is calculated using
    correlations
    that are a function of SHGC and U-Factor.

    Warnings:
        for U-values between 3.4 and 4.5, the value for T_sol is interpolated
        using results of the equations for both ranges.

    Args:
        shgc: The window's Solar Heat Gain Coefficient
        u_factor: The window's U-value

    Returns:
        The Solat Transmittance at normal incidence

    """
    if 3.4 <= u_factor <= 4.5:
        return np.interp(
            u_factor,
            [3.4, 4.5],
            [t_sol_intermediate(shgc, 3.4), t_sol_intermediate(shgc, 4.5)],
        )
    return t_sol_intermediate(shgc, u_factor)


# endregion

# region Step 5. Determine Layer Solar Reflectance
def r_i_s_intermediate(shgc, t_sol, u_factor):
    if u_factor >= 4.5:
        return 1 / (
            29.436546 * (shgc - t_sol) ** 3
            - 21.943415 * (shgc - t_sol) ** 2
            + 9.945872 * (shgc - t_sol)
            + 7.426151
        )
    if u_factor <= 3.4:
        return 1 / (
            199.8208128 * (shgc - t_sol) ** 3
            - 90.639733 * (shgc - t_sol) ** 2
            + 19.737055 * (shgc - t_sol)
            + 6.766575
        )


def r_i_s(shgc, t_sol, u_factor):
    """Resistance of the inside coefficient under summer conditions

    Args:
        shgc: The Solar Heat Gain Coefficient
        t_sol: The Solat Transmittance at normal incidence
        u_factor: The window's U-value

    Returns:
        The Resistance of the inside coefficient under summer conditions

    """
    if 3.4 <= u_factor <= 4.5:
        return np.interp(
            u_factor,
            [3.4, 4.5],
            [
                r_i_s_intermediate(shgc, t_sol, 3.4),
                r_i_s_intermediate(shgc, t_sol, 4.5),
            ],
        )
    return r_i_s_intermediate(shgc, t_sol, u_factor)


def r_o_s_intermediate(shgc, t_sol, u_factor):
    if u_factor >= 4.5:
        return 1 / (2.225824 * (shgc - t_sol) + 20.57708)
    if u_factor <= 3.4:
        return 1 / (5.763355 * (shgc - t_sol) + 20.541528)


def r_o_s(shgc, t_sol, u_factor):
    """Resistance of the outside coefficient under summer conditions

    Args:
        shgc: The window's Solar Heat Gain Coefficient
        t_sol: The Solat Transmittance at normal incidence
        u_factor: The window's U-value

    Returns:
        The resistance of the outside coefficient under summer conditions

    """
    if 3.4 <= u_factor <= 4.5:
        return np.interp(
            u_factor,
            [3.4, 4.5],
            [
                r_o_s_intermediate(shgc, t_sol, 3.4),
                r_o_s_intermediate(shgc, t_sol, 4.5),
            ],
        )
    return r_o_s_intermediate(shgc, t_sol, u_factor)


def frac_inward(r_o_s, r_l_w, r_i_s):
    """The inward flowing fraction

    Args:
        r_o_s: Resistance of the inside coefficient under summer conditions
        r_l_w: The resisance of the bare window under winter conditions (
        without the film coefficients) in
            units of m\ :sup:`2`\ K/W
        r_i_s: Resistance of the inside coefficient under summer conditions

    Returns:
        The inward flowing fraction

    """
    return (r_o_s + 0.5 * r_l_w) / (r_o_s + r_l_w + r_i_s)


def r_s_f(t_sol, shgc, r_o_s, r_l_w, r_i_s):
    """The solar reflectance of the front face

    Notes: The solar reflectance of the back face is the same as the solar
    reflectance of the front face.

    Args:
        t_sol (double): The Solat Transmittance at normal incidence.
        shgc (double): The window's Solar Heat Gain Coefficient
        r_o_s (double): Resistance of the outside coefficient under summer
            conditions.
        r_l_w (double): The resisance of the bare window under winter
            conditions (without the film coefficients) in units of m\ :sup:`2`\ K/W.
        r_i_s (double): Resistance of the inside coefficient under summer
        conditions.

    Returns:
        double: Solar reflectance of the front face

    """
    return 1 - t_sol - (shgc - t_sol) / frac_inward(r_o_s, r_l_w, r_i_s)


# endregion


# region Step 6. Determine Layer Visible Properties
def r_vis_b(t_vis):
    """The visible light reflectance for the back surface.

    Args:
        t_vis: The visible transmittance

    Returns:
        double: The visible light reflectance for the back surface
    """
    return -0.7409 * t_vis ** 3 + 1.6531 * t_vis ** 2 - 1.2299 * t_vis + 0.4547


def r_vis_f(t_vis):
    """The visible light reflectance for the front surface

    Args:
        t_vis (double): The visible transmittance

    Returns:
        double: The visible light reflectance for the front surface

    """
    return -0.0622 * t_vis ** 3 + 0.4277 * t_vis ** 2 - 0.4169 * t_vis + 0.2399


# endregion
