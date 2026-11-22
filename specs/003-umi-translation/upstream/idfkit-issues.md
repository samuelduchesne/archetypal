# Draft idfkit issue for spec 003

A draft for the maintainer to file on idfkit's issue tracker. Nothing here has been filed.

---

## UP-10 — equivalent glazing layer of a simple-glazing window

**Title:** `idfkit.thermal.equivalent_glazing_layer(u, shgc, vt)`: the single glazing layer
EnergyPlus's simple window model builds from U-factor, SHGC and VT

**Roadmap item:** UP-10 (blocking for marking archetypal spec 003 implemented; bridged
meanwhile).

### Summary

For a `WindowMaterial:SimpleGlazingSystem`, EnergyPlus does not simulate U, SHGC and VT
directly. It first converts them to one equivalent glazing layer — thickness, conductivity,
solar and visible transmittance and reflectances — and simulates that layer. The method is
in the Engineering Reference, "Window Calculation Module", section "Simple Window Model".

idfkit reads U, SHGC and VT back from a simple-glazing construction
(`calculate_u_value`, `calculate_shgc`, `calculate_visible_transmittance`), but it has no
function that gives the equivalent layer. A tool that must write a simple-glazing window
as a layered glazing material has to reimplement the EnergyPlus procedure.

### Minimal reproduction

This is an API gap, not a failure. idfkit 1.3.0rc2, Python 3.13, no EnergyPlus needed.

```python
import idfkit
from idfkit import new_document
from idfkit import thermal

doc = new_document()
doc.add(
    "WindowMaterial:SimpleGlazingSystem",
    "Simple",
    u_factor=1.8,
    solar_heat_gain_coefficient=0.4,
    visible_transmittance=0.6,
)
doc.add("Construction", "Window", outside_layer="Simple")
c = doc["Construction"]["Window"]
print("idfkit", idfkit.__version__)
print(
    "U, SHGC, VT =", thermal.calculate_u_value(c), thermal.calculate_shgc(c), thermal.calculate_visible_transmittance(c)
)
print("equivalent_glazing_layer in idfkit.thermal:", hasattr(thermal, "equivalent_glazing_layer"))
```

Output:

```text
idfkit 1.3.0rc2
U, SHGC, VT = 1.7999999999999998 0.4 0.6
equivalent_glazing_layer in idfkit.thermal: False
```

### Expected vs actual

| | Expected | Actual (1.3.0rc2) |
|---|---|---|
| Layer properties for U = 1.8, SHGC = 0.4, VT = 0.6 | thickness, conductivity, solar and visible transmittance and reflectances, as EnergyPlus computes them | no API; callers reimplement the Engineering Reference procedure |

### Proposed API

In `idfkit.thermal`, next to `calculate_shgc`:

```python
@dataclass(frozen=True, slots=True)
class EquivalentGlazingLayer:
    thickness: float  # m
    conductivity: float  # W/m-K
    solar_transmittance: float
    front_solar_reflectance: float
    back_solar_reflectance: float
    visible_transmittance: float
    front_visible_reflectance: float
    back_visible_reflectance: float
    infrared_transmittance: float
    front_infrared_emissivity: float
    back_infrared_emissivity: float


def equivalent_glazing_layer(
    u_factor: float,  # W/m2-K, with films, as in WindowMaterial:SimpleGlazingSystem
    shgc: float,
    visible_transmittance: float | None = None,  # EnergyPlus uses the solar value when absent
) -> EquivalentGlazingLayer: ...
```

Follow the Engineering Reference steps, in EnergyPlus's order:

1. Inside and outside film resistances as functions of U, and the layer's resistance as
   `1/U` minus both films.
2. Thickness and conductivity from the layer's resistance.
3. Solar transmittance from SHGC and U, with EnergyPlus's interpolation between its low-U
   and high-U correlations.
4. Solar reflectances from the inward-flowing fraction and the film coefficients.
5. Visible transmittance from VT, and visible reflectances from it.
6. The same input limits EnergyPlus applies (for example its maximum U-factor), with a
   clear `ValueError` outside them.

Useful additions, at idfkit's discretion:

- An overload taking a `WindowMaterial:SimpleGlazingSystem` object.
- A helper that adds the result to a document as a `WindowMaterial:Glazing`.

**Test.** For a few (U, SHGC, VT) triples, a window whose only layer is the returned
`WindowMaterial:Glazing` should give, in EnergyPlus's *Envelope Summary*, the same U-factor,
SHGC and VT as the same window with the `WindowMaterial:SimpleGlazingSystem`, within
EnergyPlus's reporting precision.

### Why archetypal needs it

archetypal 3 (spec 003) writes archetypes to UMI template libraries. archetypal's reduction
(spec 002) produces windows as simple glazing (U, SHGC, VT), but UMI has no simple-glazing
material: each window must be a list of glazing and gas layers. Writing one glazing layer
computed by EnergyPlus's own simple window model keeps the simulated window the same,
without inventing a multi-layer unit that no one specified. The procedure is an EnergyPlus
computation, so it belongs in idfkit, not in archetypal. Until it is released, archetypal
keeps one private bridge function implementing it, tested against EnergyPlus, and removes it
when idfkit offers this function.
