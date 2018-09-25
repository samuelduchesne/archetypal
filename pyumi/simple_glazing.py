# coding=utf-8
import math

import numpy as np


def simple_glazing(shgc, u_factor, visible_transmisstance):
    """
    Calculates the physical properties of an equivalent single pane of glass from the solar_heat_gain_coefficient,
    the U_factor and the Visible Transmittance.
    :param visible_transmisstance: Visible Transmittance
    :param shgc: Solar Heat Gain Coefficient
    :param u_factor: U-factor
    :param t_vis: Layer’s Visible Transmittance at normal incidence

    :return dict:
    """

    if isinstance(shgc, str):
        shgc = float(shgc)
    if isinstance(u_factor, str):
        u_factor = float(u_factor)
    if isinstance(visible_transmisstance, str):
        visible_transmisstance = float(visible_transmisstance)

    dict = {}

    # Step 1. Determine glass-to-glass Resistance.

    # glass-to-glass resistance (R_l_w) is calculated using:
    R_l_w = r_l_w(u_factor)

    # Step 2. Determine Layer Thickness

    # The thickness of the equivalent layer in units of meters is calculated using:
    Thickness = thickness(R_l_w)

    # Step 3. Determine Layer Thermal Conductivity

    # The effective thermal conductivity, `lambda_eff`, of the equivalent layer is calculated using:
    Lambda_eff = lambda_eff(Thickness, R_l_w)

    # Step 4. Determine Layer Solar Transmittance

    # The layer’s solar transmittance at normal incidence, `T_sol`, is calculated using correlations that are a
    # function of SHGC and U-Factor.

    T_sol = t_sol(shgc, u_factor)

    # Step 5. Determine Layer Solar Reflectance

    R_i_s = r_i_s(shgc, T_sol, u_factor)
    R_o_s = r_o_s(shgc, T_sol, u_factor)
    R_s_f = r_s_f(T_sol, shgc, R_o_s, R_l_w, R_i_s)
    R_s_b = R_s_f  # Both are taken equal

    # The thermal absorptance, or emittance, is taken as 0.84 for both the front and back and the longwave
    # transmittance is 0.0



    # Step 6. Determine Layer Visible Properties

    T_vis = visible_transmisstance

    R_vis_b = r_vis_b(T_vis)
    R_vis_f = r_vis_f(T_vis)

    # Last Step. Saving results to dict

    dict['Conductivity'] = Lambda_eff
    dict['Thickness'] = Thickness
    dict['SolarTransmittance'] = T_sol
    dict['SolarReflectanceFront'] = R_s_f
    dict['SolarReflectanceBack'] = R_s_b
    dict['IRTransmittance'] = 0.0
    dict['VisibleTransmittance'] = T_vis
    dict['VisibleReflectanceFront'] = R_vis_f
    dict['VisibleReflectanceBack'] = R_vis_b
    dict['IREmissivityFront'] = 0.84
    dict['IREmissivityBack'] = 0.84
    dict['DirtFactor'] = 1.0  # Clean glass

    dict['Cost'] = 0
    dict['Density'] = 2500
    dict['EmbodiedCarbon'] = 0
    dict['EmbodiedCarbonStdDev'] = 0
    dict['EmbodiedEnergy'] = 0
    dict['EmbodiedEnergyStdDev'] = 0
    dict['Life'] = 1
    dict['SubstitutionRatePattern'] = np.NaN # ! Might have to change to an empty array
    dict['SubstitutionTimestep'] = 0
    dict['TransportCarbon'] = 0
    dict['TransportDistance'] = 0
    dict['TransportEnergy'] = 0
    dict['Type'] = 'Uncoated'  # TODO Further investigation necessary

    dict['Comment'] = 'Properties calculated from Simple Glazing System'

    return dict


def r_i_w(U_factor):
    if U_factor < 5.85:
        return 1 / (0.359073 * math.log(U_factor) + 6.949915)
    return 1 / (1.788041 * U_factor - 2.886625)


def r_o_w(U_factor):
    return 1 / (0.025342 * U_factor + 29.162853)


def r_l_w(U_factor):
    if U_factor > 7.0:
        print(
            "The model cannot support glazing systems with a U higher than 7.0 because the thermal resistance of "
            "the film coefficients alone can provide this level of performance and none of the various resistances"
            "can be negative.")
        pass
    return (1 / U_factor) - r_i_w(U_factor) - r_o_w(U_factor)


# Step 2. Determine Layer Thickness

def thickness(r_l_w):
    """
    The thickness of the equivalent layer in units of meters
    :param r_l_w:
    :return:
    """
    if 1 / r_l_w > 7.0:
        return 0.002
    return 0.05914 - 0.00714 / r_l_w


def lambda_eff(thickness, r_l_w):
    """
    The effective thermal conductivity of the equivalent layer in W/m-K
    :param thickness: in meters
    :param r_l_w:
    :return:
    """
    return thickness / r_l_w


# Step 4. Determine Layer Solar Transmittance

def t_sol_intermediate(shgc, U_factor):
    if U_factor >= 4.5 and shgc < 0.7206:
        return 0.939998 * shgc ** 2 + 0.20332 * shgc
    if U_factor >= 4.5 and shgc >= 0.7206:
        return 1.30415 * shgc - 0.30515
    if U_factor <= 3.4 and shgc <= 0.15:
        return 0.41040 * shgc
    if U_factor <= 3.4 and shgc > 0.15:
        return 0.085775 * shgc ** 2 + 0.963954 * shgc - 0.084958
    pass


def t_sol(shgc, U_factor):
    """
    The Solat Transmittance at normal incidence t_sol, is calculated using correlations
    that are a function of SHGC and U-Factor. for U-values between 3.4 and 4.5, the value for T_sol is interpolated
    using results of the equations for both ranges.
    :param shgc:
    :param U_factor:
    :return:
    """
    if U_factor >= 3.4 and U_factor <= 4.5:
        return np.interp(U_factor, [3.4, 4.5], [t_sol_intermediate(shgc, 3.4), t_sol_intermediate(shgc, 4.5)])
    return t_sol_intermediate(shgc, U_factor)


# Step 5. Determine Layer Solar Reflectance

def r_i_s_intermediate(shgc, t_sol, U_factor):
    if U_factor >= 4.5:
        return 1 / (29.436546 * (shgc - t_sol) ** 3 - 21.943415 * (shgc - t_sol) ** 2 + 9.945872 * (
                shgc - t_sol) + 7.426151)
    if U_factor <= 3.4:
        return 1 / (199.8208128 * (shgc - t_sol) ** 3 - 90.639733 * (shgc - t_sol) ** 2 + 19.737055 * (
                shgc - t_sol) + 6.766575)
    pass


def r_i_s(shgc, t_sol, U_factor):
    if U_factor >= 3.4 and U_factor <= 4.5:
        return np.interp(U_factor, [3.4, 4.5],
                         [r_i_s_intermediate(shgc, t_sol, 3.4), r_i_s_intermediate(shgc, t_sol, 4.5)])
    return r_i_s_intermediate(shgc, t_sol, U_factor)


def r_o_s_intermediate(shgc, t_sol, U_factor):
    if U_factor >= 4.5:
        return 1 / (2.225824 * (shgc - t_sol) + 20.57708)
    if U_factor <= 3.4:
        return 1 / (5.763355 * (shgc - t_sol) + 20.541528)
    pass


def r_o_s(shgc, t_sol, U_factor):
    if U_factor >= 3.4 and U_factor <= 4.5:
        return np.interp(U_factor, [3.4, 4.5],
                         [r_o_s_intermediate(shgc, t_sol, 3.4), r_o_s_intermediate(shgc, t_sol, 4.5)])
    return r_o_s_intermediate(shgc, t_sol, U_factor)


def frac_inward(r_o_s, r_l_w, r_i_s):
    return (r_o_s + 0.5 * r_l_w) / (r_o_s + r_l_w + r_i_s)


def r_s_f(t_sol, shgc, r_o_s, r_l_w, r_i_s):
    """
    The the solar reflectances of the front face
    :param t_sol:
    :param shgc:
    :param r_o_s:
    :param r_l_w:
    :param r_i_s:
    :return:
    """
    return 1 - t_sol - (shgc - t_sol) / frac_inward(r_o_s, r_l_w, r_i_s)


# Step 6. Determine Layer Visible Properties

def r_vis_b(t_vis):
    """
    The visible light reflectance for the back surface
    :param t_vis:
    :return:
    """
    return -0.7409 * t_vis ** 3 + 1.6531 * t_vis ** 2 - 1.2299 * t_vis + 0.4547


def r_vis_f(t_vis):
    """
    The visible light reflectance for the front surface
    :param t_vis:
    :return:
    """
    return -0.0622 * t_vis ** 3 + 0.4277 * t_vis ** 2 - 0.4169 * t_vis + 0.2399
