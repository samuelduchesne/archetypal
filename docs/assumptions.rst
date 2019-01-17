Modeling Assumptions
====================

Online model-reduction implies that a multi-zone model propertly defined in a 3D environement is reduced in such a
way that is becomes non-geometric. Materials, Constructions, Schedules, Systems and so forth are contained,
simplified and removed to retain only essential non-geometric characteristics.

The underlying hypothesis it that a reduced model can be defined by two abstract zones, a core and a peripheral zone,
and then applied to any geometric volumes, characterising a building model.

Weighted-average and top-rank approaches
________________________________________

Given a detailed building energy model, with a multi-zone definition, the model-reduction occurs by combining all
core-zones and all-peripheral zones into one core-zone definition and one peripheral-zone definition. The conditioned
area of each zone is used as a weight function when determining the different thermo-physical properties of the
model that can be area-based (sunch as equipment-power density, lighting density, etc.). For other properties, it
has been decided to follow a top-ranked approach, such that the property is chosen based on the area-ranked ordered
occurance of the property. For example, with all peripheral zones, if the lighting schedule A is applied in two zones
of 50m2 each, and the lighting schedule B is applied in one zone of 80m2, the schedule A will be retained and the
shcedule B discarded because the sum of areas assigned to schedule A (100m2) is higher than areas assigned to
schedule B.

It could be possible to combine the schedules to ensure coherence in the model but this has the negative effect of
the changing the essence of the original schedule used.