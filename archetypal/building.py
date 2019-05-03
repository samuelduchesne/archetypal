################################################################################
# Module: building.py
# Description: Functions related to building
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import numpy as np

from archetypal.core import EnergyProfile
import pyomo.environ
import pyomo.core as pyomo
from pyomo.opt import SolverFactory


def create_fake_profile(x=None, y1={}, y2={}, normalize=False,
                        profile_type='undefined', sorted=False,
                        ascending=False, units='J'):
    """Utility that generates a generic EnergyProfile isntance

    Args:
        x (np.ndarray): is a linspace. Default is np.linspace(0, 8759, 8760)
        y1 (dict): {'A':1, 'f':1/8760, 'phy':1, 's':0.5}
        y2 (dict): {'A':1, 'f':1/24, 'phy':1, 's':0.5}
        ascending (bool): if True, sorts in ascending order. Implies 'sorted'
            is also True
        profile_type (str): name to give the series. eg. 'heating load' or
            'cooling load'
        sorted (bool): id True, series will be sorted.

    Returns:
        EnergyProfile: the EnergyProfile
    """
    if x is None:
        x = np.linspace(0, 8759, 8760)
    A1 = y1.get('A', 1)
    f = y1.get('f', 1 / 8760)
    w = 2 * np.pi * f
    phy = y1.get('phy', 1)
    s = y1.get('s', 0.5)
    y1 = A1 * np.sin(w * x + phy) + s

    A = y2.get('A', A1)
    f = y2.get('f', 1 / 24)
    w = 2 * np.pi * f
    phy = y2.get('phy', 1)
    s = y2.get('s', 0.5)
    y2 = A * np.sin(w * x + phy) + s

    y = y1 + y2
    return EnergyProfile(y, index=x, frequency='1H', units=units,
                         profile_type=profile_type, normalize=normalize,
                         is_sorted=sorted,
                         ascending=ascending)


def discretize(profile, bins=5):
    m = pyomo.ConcreteModel()

    m.bins = pyomo.Set(initialize=range(bins))
    m.timesteps = pyomo.Set(initialize=range(8760))
    m.profile = profile.copy()
    m.duration = pyomo.Var(m.bins, within=pyomo.NonNegativeIntegers)
    m.amplitude = pyomo.Var(m.bins, within=pyomo.NonNegativeReals)

    m.total_duration = pyomo.Constraint(m.bins,
                                        doc='All duration must be ' \
                                            'smaller or '
                                            'equal to 8760',
                                        rule=total_duration_rule)

    m.obj = pyomo.Objective(sense=pyomo.minimize,
                            doc='Minimize the sum of squared errors',
                            rule=obj_rule)
    optim = SolverFactory('gurobi')

    result = optim.solve(m, tee=True, load_solutions=False)

    m.solutions.load_from(result)

    return m


def total_duration_rule(m):
    return sum(m.duration[i] for i in m.bins) == 8760


def obj_rule(m):
    return sum(m.duration * m.amplitude)