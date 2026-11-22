"""Reduce a detailed EnergyPlus model to an SBEM archetype (spec 002).

Reduction reads a model and its simulation results through idfkit, groups the zones into a
layout and gives one SBEM archetype per group, with a ledger of every simplification made.
"""

from archetypal.reduction.schedules import schedule_compact

__all__ = ["schedule_compact"]
