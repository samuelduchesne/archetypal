---
diataxis: explanation
---

# About UMI translation: what each direction loses, and why

UMI and SBEM describe the same kind of object, a building archetype, but they do not cut it the
same way. A UMI building template holds exactly two zone definitions and one window; an SBEM
archetype holds any number of zone groups, each with its own window, schedules by calendar
month and a floor-area share. Translating one into the other therefore cannot always be exact,
and a translation that changed a value silently would make every result built on it
suspect. archetypal's rule is that nothing is lost without being said: every value the target
cannot hold appears in the translation report, as a loss or, when nothing is lost, as a note.
This page explains where the two models differ and what each direction does about it.
[How to write archetypes to UMI](../how-to/write-archetypes-to-umi.md) and
[How to read a UMI library](../how-to/read-a-umi-library.md) show the translation in use;
[UMI correspondence](../reference/umi-correspondence.md) lists every field.

## A UMI template has two zones, so finer layouts are merged first

UMI's template has a `Core` and a `Perimeter` zone definition, applied to the core and perimeter
of whatever building geometry the template is used with. An SBEM archetype may group zones more
finely, by space use and exposure. Writing such an archetype first merges its groups to core and
perimeter.

For a reduction from spec 002 the merge is exact: the reduction report keeps the summed
quantities of every finer group, so merging gives what reducing the model directly to
core/perimeter gives. A bare archetype has no such record, so its groups are weighted by floor
area. Densities, setpoints and schedules merge exactly; the envelope, the window and the
efficiencies need areas and energies the archetype does not hold, and they are reported as
approximate wherever the groups differ. An archetype with a single group is written as both
zones, and the report says the zone was copied rather than derived.

Reading goes the other way without loss: each template becomes an archetype with a `core` and a
`perimeter` group. UMI has no group names, so an archetype whose groups carry other names gets
them back as `core` and `perimeter`, and writing reports the renaming.

## Floor-area shares belong to the geometry, not the template

An SBEM group may say what share of the floor area it covers. A UMI template cannot: the
building's geometry decides how much of the floor is core and how much perimeter when the
template is used. Writing drops each share and reports it (`share_dropped`). Reading leaves the
shares unset, which is not a loss, since UMI never held them.

## One window per template

UMI has one window construction and one set of window settings per template; SBEM has one per
group. Reading gives every group the template's window. Writing uses the perimeter group's
window, and reports the window of any other group that differs from it. A core without a window
gains the template's window when the library is read back; it has no facade, so this changes
nothing it simulates, and the report notes it.

The window itself survives when it is layered. UMI windows are layers of glazing and gas, and
since UP-9 SBEM can hold the same layers, so a layered window maps exactly both ways. An SBEM
window given as simple glazing (U-factor, SHGC, visible transmittance), which is what a
reduction produces, is written as the single glazing layer EnergyPlus's own simple-glazing model
builds from those three numbers. EnergyPlus then simulates the same window, but the layer is an
equivalent, not the original description, so the report lists it as approximate.

## UMI holds constant setpoints

A UMI zone has one heating setpoint and one cooling setpoint. An SBEM thermostat has setpoint
schedules, which may set back at night or on weekends. Writing keeps the occupied setpoint (the
heating schedule's maximum and the cooling schedule's minimum) and reports the setback hours it
loses, with their number over the reference year and their mean difference. The written
template therefore conditions more than the archetype did; the report says by how much.

## Hot water is per floor area in UMI, per person in SBEM

UMI gives the hot-water flow per floor area and hour, modulated by a schedule; SBEM gives it per
person and day. The conversion uses the people density and the schedule's annual sum so that the
annual volume of hot water per square metre is the same on both sides. A zone with hot water and
no people cannot be expressed per person: reading refuses it as a range problem, and writing
reports it.

## Schedules are compared by month, on a Monday-aligned year

An SBEM year schedule has one week per calendar month. A UMI year schedule has parts, each a
date range with its week, and the ranges need not follow months. Both sides are evaluated on the
same reference year: non-leap, starting on a Monday, so that a week's Monday is always a Monday
of the calendar.

A month covered by a single UMI part takes that part's week, exactly. A month that a part
boundary splits is evaluated hour by hour and projected to one representative week, each weekday
the mean of that weekday's days in the month. The projection conserves the month's sum over the
reference year, which is what drives annual energy use, but not the hour-by-hour profile, so the
month is reported as approximate. Writing turns equal consecutive months into one part. SBEM's
holiday and design-day slots have no UMI counterpart: UMI uses Sunday's day on holidays and
Monday's on design days, so writing reports only the slots that differ from those days.

## What still waits for an upstream release

The SBEM fork that archetypal uses added the fields that once had no place in SBEM: layered
glazing, window settings, partitions, natural and scheduled ventilation, the mechanical
ventilation schedule, ideal-loads limits, availability schedules, daylighting, adiabatic
surfaces, and the life-cycle and descriptive fields (UP-9), and the numeric heat-recovery
effectiveness (UP-2). A library read from UMI therefore writes back with almost no losses. One
group remains: the airflow-network, zone-mixing and interior-window settings of UMI's window
settings (`Afn*`, `ZoneMixing*`, `IsVirtualPartition`, `Type`) and the ventilation's `Afn`
switch, which UP-9 does not add. Reading reports each one that differs from Basilisk's default,
with `"upstream": "UP-9"`.

SBEM in turn holds fields that UMI has no place for, such as building geometry, attic and
basement assumptions, a temperature-dependent COP, supply-air temperature limits and fan power.
Writing reports each one that is set; reading the library back gives SBEM's defaults.

## The audit makes "nothing lost silently" a test

A promise to report every loss is only as good as its check. archetypal's tests read every
library of the UMI test set, write it back, compare the result field by field with `diff_umi`,
and do the same in the other direction with `diff_archetypes`. Every difference must appear in a
loss of the matching report, by template and location, and every loss must match a difference
or a value with no counterpart. A difference no report explains fails the test with its
location. Strict mode builds on the same reports: it fails a translation if and only if the
report lists a loss, and then writes nothing.
