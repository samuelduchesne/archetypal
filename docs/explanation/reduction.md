---
diataxis: explanation
---

# About reduction: what an archetype conserves, and why

A detailed EnergyPlus model describes a building zone by zone, sometimes with dozens of zones
and hundreds of objects. An SBEM archetype describes the same building as a few zone groups,
each with one zone definition and a share of the floor area. Something is lost on the way, and
an archetype is only useful if what is lost does not change the building's energy use.
archetypal's answer is to conserve *totals*, not to pick representative values: every
quantity that drives energy use is summed over the zones a group is made of, and the
archetype's intensities are those totals divided by the group's floor area or envelope area.
This page explains how zones are grouped, what each group conserves, why the rules take the
form they do, and what SBEM cannot hold. It describes the rules of spec 002 (FR-014 to FR-024);
[How to reduce a model](../how-to/reduce-a-model.md) shows how to run a reduction, and
[Reduction report](../reference/reduction-report.md) describes the record it keeps.

## Zones are grouped by what they are used for and where they sit

Two zones behave alike when they hold the same activity and see the same outdoor conditions.
Reduction therefore classifies each conditioned zone twice.

Its **exposure** is *perimeter* when it has an exterior wall or a window facing the outdoors,
and *core* otherwise. Roofs, exposed floors and ground contact do not decide exposure: a
top-floor core zone stays core, and its roof is carried as envelope of its group. Exposure is
read from EnergyPlus's resolved surfaces, so it does not depend on how the geometry was drawn.

Its **space use** comes, in order, from a mapping you supply, from the space types declared in
the model, or from the zone's *signature*: its gain densities, its schedules (compared by
their hourly values, not their names) and its thermostat and outdoor-air settings, rounded so
that numerical noise does not split a class. Zones with equal signatures share a space use,
labelled after the first zone's name, such as `use:G_Core`. The result never depends on the
order of zones in the file, and the report states which source decided each zone.

The default layout forms one group per space use and exposure. Coarser layouts drop one
distinction or both; because every group is a sum of zones, a coarser layout is a sum of finer
groups, and merging a reduction gives the same archetype as reducing the model again.

## Unconditioned zones become no group, but keep their envelope

A zone with no thermostat that enables heating or cooling, and no equipment delivering either,
is not conditioned. Attics and basements map to SBEM's building-level attic and basement
assumptions; any other unconditioned zone (a return plenum, a crawlspace) is excluded and listed
with its floor area. Excluding a plenum must not delete its roof and walls, which lose heat on
behalf of the floor below: an excluded zone's envelope is assigned to the conditioned zones it
shares surfaces with, in proportion to the shared area, and the report records the
assignment. Return plenums report air-system energy because return air passes through them;
that alone does not make them conditioned.

Every zone counts as many times as EnergyPlus counts it. A typical floor drawn once with a
multiplier of ten weighs ten times in every total, so a model with multipliers and the same
building drawn floor by floor reduce to the same groups and the same totals.

## Each group conserves the totals that drive energy use

Conserving a total, rather than averaging a value, is what keeps an archetype's annual energy
close to the detailed model's: energy is additive over zones, averages are not. The table
names what each group conserves.

| Quantity | Conserved over the group's zones | The archetype holds |
|---|---|---|
| Floor area | the sum of floor areas | each group's share of the conditioned area |
| Internal gains | installed people and watts, and installed total × schedule, hour by hour | densities and a schedule |
| Envelope, by class | area and heat loss coefficient (area × U) of walls, roofs, floors, ground contact | one equivalent construction per class |
| Windows, by orientation | area, area × U, area × SHGC, area × visible transmittance | one window and the window-to-wall ratio of each orientation |
| Thermal mass | heat capacity of the envelope and of internal mass | the capacity in the equivalent constructions |
| Infiltration | design airflow and its hourly profile | flow per exterior area and a schedule |
| Outdoor air | hourly outdoor airflow, heat recovery and economiser by the airflow they serve | peak flow per area and a schedule |
| Hot water | hourly volume and the energy to heat it | flow per person, a schedule and a supply temperature |
| Conditioning energy | delivered and consumed energy, by mode and fuel | effective efficiencies |
| Fan energy | fan energy and air volume moved | a specific fan power |
| Geometry | envelope and window areas by orientation per floor area, storeys | geometry characteristics |

Each total sits in the group's *ledger*, which the report keeps. Ledgers add exactly, so
merging two groups, or reaching a coarser layout later, needs only the report.

Thermostat setpoints are the exception. A setpoint has no total: the group's setpoint is the
floor-area-weighted mean of its heated (or cooled) zones' setpoints, hour by hour. That rule is
representative, not conserving, and the report says so, with the share of the group's floor
area that is not heated or not cooled.

## Representative days conserve monthly energy

SBEM holds a schedule as one week per month, seven days of 24 hourly values, with holiday and
design-day slots. A detailed model's schedule has 8760 hours, and its days differ within a
month. Reduction projects each hourly profile onto SBEM's form by taking, for each month and
weekday, the mean over that month's days of that weekday. The projection is linear, so each
month's energy is kept exactly; and projecting a sum equals summing projections, so merging
projected schedules weighted by their totals gives the schedule of the merged group.

The schedule is the conserved profile divided by its installed total, so installed total ×
schedule reproduces the profile. Peak-normalised schedules, as archetypal 2 built them,
conserve neither. Every SBEM schedule converts without loss to an EnergyPlus
`Schedule:Compact` with `archetypal.reduction.schedule_compact`.

## Equivalent constructions keep heat loss and mass

SBEM wants one layered construction per envelope slot (facade, flat roof, ground slab, ...),
while a group's zones may use several. Choosing the most common one would conserve neither heat
loss nor mass, and layers do not align from one construction to another. Reduction builds an
equivalent three-layer construction for each class instead: every source construction is split
at its most resistive layer; the inner layer holds the area-weighted heat capacity inside it,
the outer layer the capacity outside it, and the middle layer is the insulation whose
resistance reproduces the class's area × U with the surface films epinterface uses. Heat loss
and capacity are then exact, and the mass stays on the side of the insulation where it was.

Windows are conserved through their products: the group's U, solar heat gain coefficient and
visible transmittance are each the area-weighted mean, so area × U, solar gain admitted and
daylight admitted are kept by orientation.

## Efficiency reproduces the energy consumed

An archetype conditions its zones with ideal loads, and turns delivered heating and cooling
into consumed fuel with an efficiency. For that efficiency to reproduce the detailed model's
consumption, it must be measured against the same delivery: the energy the HVAC equipment
hands over, outdoor-air load included, not the zone air's sensible load. Each hour's consumed
energy is attributed to the zones in proportion to that hour's delivery in the same mode, and
the group's efficiency is total delivered over total consumed, by fuel. Pumps and heat
rejection have no end use in SBEM; their energy is folded into the distribution efficiency of
the mode they serve that hour.

A constant efficiency is exact over the year but misplaces energy in time: a heat pump or an
air-cooled chiller consumes the most in the hours with the most extreme outdoor temperature,
which is when peak demand is measured. Reduction therefore fits the energy input ratio (the
inverse of the COP) as a linear function of outdoor temperature, constrained so that the
annual consumed energy is reproduced exactly. A boiler, whose efficiency does not depend on
the weather, gets a slope of practically zero. The fit uses only sums that add over zones, so
merged groups are refitted exactly.

## Fan energy follows the air the archetype moves

Fan energy is not folded into the efficiencies. Each group carries a specific fan power, its
fans' energy divided by the air volume they moved, which is the descriptor a modeller can check
against a design value. For the archetype's fan energy to match, it must move the same air.
Ideal loads move as much air as the load needs at their supply-air temperature limit, so
reduction sets those limits from the detailed model's effective supply temperature difference
in each mode. With the same delivered energy, the archetype moves the same volume, and
specific fan power × volume gives back the detailed fan energy. Air moved when there is neither
a load nor an outdoor-air demand, such as a constant-volume fan recirculating, has no
counterpart in ideal loads.

## What SBEM cannot hold is named, never dropped

Some features of a detailed model have no place in SBEM: daylighting controls, shading,
exterior lights, infiltration that responds differently to wind in different zones, the
radiant, latent and lost parts of internal gains, fuels other than a mode's main one. Reduction keeps a table of such features and lists each one it finds in the
report's `not_represented`, with the zones it affects, its magnitude when the results give one,
and the SBEM field its effect was folded into, if any. Nothing is left out silently, so a
difference between the archetype's results and the model's can be traced to a named cause.

## What this means for an archetype's results

Because the totals are conserved, an archetype built this way reproduces the detailed model's
floor area, gains, envelope heat loss, airflows, hot water and consumed energy by construction;
its annual energy differs only through what SBEM simplifies, and the report lists each such
simplification. The remaining differences come from geometry (epinterface builds a shoebox
from the archetype's characteristics), from day types and weather responses SBEM averages,
and from the features in `not_represented`. Whether they matter for a given building is a
question for the comparison: simulate the archetype and compare its results with the model's,
as [How to check that an archetype reproduces its building](../how-to/compare-results.md)
describes.
