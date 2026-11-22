---
diataxis: explanation
---

# archetypal

archetypal is where building energy archetypes are created, translated and codified for
application. It takes the detailed EnergyPlus models and published sources that describe real
buildings, turns them into archetypes, and moves those archetypes between the formats that
urban building energy tools read, such as UMI template libraries.

## archetypal sits on top of epinterface and idfkit

Two packages already own the work around an archetype, so archetypal does not repeat it:

```text
archetypal    create · translate · apply
     ↓
epinterface   SBEM data model · composer · EnergyPlus generation
     ↓
idfkit        EnergyPlus I/O · simulation · results · weather · schedules
```

- **idfkit** reads, writes and edits EnergyPlus models, runs simulations and reads their
  results, weather files and schedules.
- **epinterface** defines SBEM, the archetype data model, and generates EnergyPlus models from
  it.
- **archetypal** covers the life of an archetype around them: deriving it from a detailed model
  or a published source, translating it between SBEM and other formats, and stating the rules
  by which an archetype is assigned to a real building.

Whenever archetypal needs EnergyPlus scripting, it calls idfkit; whenever it needs an archetype,
it uses epinterface's SBEM model. The install therefore stays small, and an archetype written by
archetypal can be read by any tool built on epinterface, without archetypal.

## archetypal 3 replaces the toolkit of archetypal 2

archetypal 2 was also a general EnergyPlus toolkit: it read and edited models, ran simulations,
upgraded model versions and read results. idfkit now does that work, so archetypal 3 keeps only
the archetype half. archetypal 3 is under development and not yet released; archetypal 2 remains
installable from its last release, 2.18.11.

If your scripts use archetypal 2, its documentation stays on Read the Docs:
[archetypal 2 documentation](https://archetypal.readthedocs.io/en/v2.x/).
