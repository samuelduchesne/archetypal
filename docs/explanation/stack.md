---
diataxis: explanation
---

# About archetypal, epinterface and idfkit

An archetype is only useful if the tools around it agree on what it is and on how it becomes
an EnergyPlus model. Three packages share that work, and archetypal 3 is the one that does the
least of it on purpose. This page explains who does what, why archetypal 3 is smaller than
archetypal 2, and why SBEM is the only archetype model it knows.

## Each package owns one layer

```text
archetypal    create · translate · apply
     ↓
epinterface   SBEM data model · composer · EnergyPlus generation
     ↓
idfkit        EnergyPlus I/O · simulation · results · weather · schedules
```

idfkit owns general EnergyPlus scripting. It reads, edits and writes models, validates them
against the schema of each EnergyPlus release, runs simulations, upgrades models between
releases, evaluates schedules and reads results. Anything that would work the same on any
EnergyPlus model belongs there.

epinterface owns SBEM, the archetype data model: zones described by their use, constructions,
loads, schedules and systems, rather than by surfaces and objects. It also owns the composer
that turns an SBEM archetype back into an EnergyPlus model, so the same archetype always
produces the same simulation, whichever tool asks for it.

archetypal owns the life of an archetype around those two: deriving it from a detailed model
or a published source, translating it to and from the formats other tools read, such as UMI
template libraries, and stating the rules by which an archetype is assigned to a real building.
When it needs EnergyPlus, it calls idfkit; when it needs an archetype, it uses epinterface's
model.

## archetypal 3 is smaller because the rest found owners

archetypal 2 had to be a general EnergyPlus toolkit, because no other package was. It wrapped
eppy to read and edit models, ran EnergyPlus and its preprocessors in threads, upgraded model
versions, parsed results into data frames, evaluated schedules, computed glazing properties
and drew figures, and it kept its own classes for every UMI component.

idfkit now does the EnergyPlus half better: it is typed for each EnergyPlus release, tracks
references between objects, and caches simulations. Keeping archetypal 2's versions would have
split users and bug reports between two toolkits, and every fix would have been made twice.
archetypal 3 therefore drops them, and the [migration guide](../how-to/migrate-from-v2.md)
maps each one to its idfkit replacement.

A smaller package is also a smaller install. A user who only wants to reduce a model or
translate a UMI library no longer installs eppy, geomeppy, plotting libraries or a data portal
client, and nothing in archetypal 3 reads environment variables or writes folders on import.

The cost is that archetypal 3 depends on epinterface changes that are not yet released. Until
the main epinterface repository releases them, archetypal depends on a maintained fork that
carries exactly those changes, each also offered upstream; that is why archetypal 3 is
installed from git for now.

## SBEM is the one archetype model

Each format that describes an archetype, such as UMI, ClimateStudio or CityGML's Energy ADE,
could have had its own classes inside archetypal; archetypal 2 had them for UMI. Two models of
the same thing drift apart, though, and every new format would have multiplied the code that
keeps them in step.

archetypal 3 keeps one model, SBEM, and treats every other format as a translator to and from
it. A reduction produces SBEM; a UMI library is read into SBEM and written from it. Every
creation method then composes with every translator, and an archetype written by archetypal
can be read and simulated by any tool built on epinterface, without archetypal installed.

A translation states what it loses. UMI cannot hold everything SBEM describes, and SBEM does not
yet hold every UMI field, so each translation writes a report of the fields it could not carry.
A round trip either gives back its input or names exactly what changed.
