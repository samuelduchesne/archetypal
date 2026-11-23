"""Window rules (spec 003, research R8): layered windows, the two bridges, placement and settings.

UMI windows are layers of glazing and gas; SBEM windows are simple glazing (U-factor, SHGC and
visible transmittance) or, since UP-9, layers of glazing and gas.

- `window.layers`: a UMI window construction becomes UP-9's
  `GlazingConstructionLayeredComponent`, layer by layer, and back, exactly. Two bridges handle
  what one side cannot hold, each listing the window as approximate:
  - `simple_from_layers` (reading), when the layers cannot be a layered window (more than 4
    panes, panes and gases not alternating): the UMI layers become an in-memory idfkit
    `Construction`, and `idfkit.thermal` gives U, SHGC and VT. Each layer is lost, and the
    three values are approximate: idfkit's simplified method is not EnergyPlus's window model.
  - `equivalent_layer` (writing), for a simple-glazing window: it becomes the one glazing layer
    EnergyPlus's simple window model builds from it (`archetypal.umi._bridges` until UP-10). The
    layer reproduces the window at normal incidence; EnergyPlus applies its simple-glazing
    angular curves only to `WindowMaterial:SimpleGlazingSystem`, so off-normal solar gains
    differ.
- `window.placement`: UMI has one window per building template, SBEM one per zone group.
  Reading gives every group the template's window; writing uses the perimeter group's window
  and lists a different window of another group as lost.
- `window.settings`: operable area and shading map to UP-9's `WindowSettingsComponent`, which
  every group gets; writing uses the perimeter group's. The interior-window, zone-mixing and
  airflow-network fields have no SBEM field (UP-9 does not add them): reading reports those
  that differ from Basilisk's defaults, which writing gives.

The layer and placement rules return their losses; the settings rules, which convert schedules,
take a `RuleContext` and a schedule converter (`_common`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from epinterface.sbem.components.envelope import (
    MAX_GLAZING_LAYERS,
    GasLayerComponent,
    GasMaterialComponent,
    GlazingConstructionLayeredComponent,
    GlazingConstructionSimpleComponent,
    GlazingLayerComponent,
    GlazingMaterialComponent,
    WindowSettingsComponent,
)
from idfkit import new_document
from idfkit.exceptions import IdfKitError
from idfkit.thermal import calculate_shgc, calculate_u_value, calculate_visible_transmittance
from pydantic import ValidationError

from archetypal.umi._bridges import MAX_U_FACTOR, equivalent_glazing_layer
from archetypal.umi._format import (
    GasMaterial,
    GlazingMaterial,
    MaterialLayer,
    ShadingType,
    WindowConstruction,
    WindowSettings,
)
from archetypal.umi.correspondence import rule
from archetypal.umi.report import Findings, Loss, LossKind
from archetypal.umi.rules._common import (
    identity_to_sbem,
    identity_to_umi,
    optional_schedule_to_sbem,
    optional_schedule_to_umi,
    report_upstream,
    upstream_defaults,
)
from archetypal.umi.rules.building import window_settings_name
from archetypal.umi.rules.materials import (
    ASSEMBLY_LIFE_CYCLE,
    assembly_life_cycle_to_sbem,
    assembly_life_cycle_to_umi,
    life_cycle_to_sbem,
    life_cycle_to_umi,
    lose_version,
    non_negative,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from idfkit.document import Construction

    from archetypal.umi.rules._common import RuleContext, ScheduleToSbem, ScheduleToUmi

__all__ = [
    "LAYER_U_MAX",
    "PERIMETER",
    "SbemWindow",
    "equivalent_layer",
    "layers_to_sbem",
    "layers_to_umi",
    "place_window",
    "settings_to_sbem",
    "settings_to_umi",
    "simple_from_layers",
    "template_settings",
    "template_window",
]

SbemWindow = GlazingConstructionSimpleComponent | GlazingConstructionLayeredComponent
"""An SBEM window construction: simple glazing or, since UP-9, glazing and gas layers."""

PERIMETER = "perimeter"
"""The zone group whose window a building template gets on writing."""

LAYER_U_MAX = 5.83
"""The largest U-factor (W/m2-K) EnergyPlus 24.2 computes for a single glazing layer.

With its standard film coefficients, no `WindowMaterial:Glazing` gives more; a simple glazing
above it is written as a layer at about this U (`verification/umi/simple_glazing.py`).
"""

WindowType = Literal["Single", "Double", "Triple"]
_TYPES: dict[int, WindowType] = {1: "Single", 2: "Double"}
_TRIPLE_PANES = 3
GasType = Literal["Air", "Argon", "Krypton", "Xenon"]
_GASES: dict[str, GasType] = {"AIR": "Air", "ARGON": "Argon", "KRYPTON": "Krypton", "XENON": "Xenon"}
_MAX_LAYERS = 10  # of an EnergyPlus Construction
_SIMPLIFIED = (
    "computed from the layers by idfkit.thermal's simplified method (normal incidence, NFRC films), "
    "not by EnergyPlus's window model"
)
_LAYERS = "window.layers"
_SETTINGS = "window.settings"
_UNCATEGORIZED = "Uncategorized"
_PER_MASS = "kg"


def _gas_type(material: GasMaterial) -> GasType:
    """Return EnergyPlus's gas type of a UMI gas, from its `Type` or else its name.

    Some libraries write `Type` as `"Gas"` and name the gas (`"ARGON"`).
    """
    for candidate in (material.type, material.name or ""):
        gas = _GASES.get(candidate.strip().upper())
        if gas is not None:
            return gas
    msg = (
        f"gas material {material.name!r} (Type {material.type!r}) has no EnergyPlus gas type; "
        f"expected one of {sorted(_GASES)}"
    )
    raise ValueError(msg)


def _idfkit_construction(construction: WindowConstruction) -> Construction:
    """Build the layers as an in-memory idfkit `Construction`, outside layer first."""
    doc = new_document()
    names: list[str] = []
    for index, layer in enumerate(construction.layers):
        material = layer.material
        name = f"Layer {index + 1}"
        if isinstance(material, GlazingMaterial):
            # idfkit.thermal ignores the dirt correction factor; EnergyPlus multiplies the solar
            # and visible transmittances by it, so it is applied here and set to 1.
            dirt = material.dirt_factor
            doc.window_material_glazings.add(
                name,
                optical_data_type="SpectralAverage",
                thickness=layer.thickness,
                solar_transmittance_at_normal_incidence=material.solar_transmittance * dirt,
                front_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_front,
                back_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_back,
                visible_transmittance_at_normal_incidence=material.visible_transmittance * dirt,
                front_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_front,
                back_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_back,
                infrared_transmittance_at_normal_incidence=material.ir_transmittance,
                front_side_infrared_hemispherical_emissivity=material.ir_emissivity_front,
                back_side_infrared_hemispherical_emissivity=material.ir_emissivity_back,
                conductivity=material.conductivity,
                dirt_correction_factor_for_solar_and_visible_transmittance=1.0,
            )
        elif isinstance(material, GasMaterial):
            doc.window_material_gases.add(name, gas_type=_gas_type(material), thickness=layer.thickness)
        else:
            msg = f"window construction {construction.name!r}: layer {index} has no material"
            raise ValueError(msg)  # noqa: TRY004 - a malformed library, not a wrong argument type
        names.append(name)
    if len(names) > _MAX_LAYERS:
        msg = f"window construction {construction.name!r} has {len(names)} layers; EnergyPlus allows {_MAX_LAYERS}"
        raise ValueError(msg)
    slots: list[str | None] = [*names, *[None] * (_MAX_LAYERS - len(names))]
    return doc.constructions.add(
        "Window",
        outside_layer=names[0],
        layer_2=slots[1],
        layer_3=slots[2],
        layer_4=slots[3],
        layer_5=slots[4],
        layer_6=slots[5],
        layer_7=slots[6],
        layer_8=slots[7],
        layer_9=slots[8],
        layer_10=slots[9],
    )


def _glazings(construction: WindowConstruction) -> int:
    count = sum(isinstance(layer.material, GlazingMaterial) for layer in construction.layers)
    if count == 0:
        msg = f"window construction {construction.name!r} has no glazing layer"
        raise ValueError(msg)
    return count


def simple_from_layers(
    construction: WindowConstruction, *, subject: str, location: str, reason: str | None = None
) -> tuple[GlazingConstructionSimpleComponent, list[Loss]]:
    """Reduce a UMI window construction to SBEM simple glazing (the reading bridge of `window.layers`).

    Args:
        construction: The UMI window construction.
        subject: The building template being read, for the losses.
        location: The construction's JSON pointer in the UMI file.
        reason: Why the layers cannot be a layered window, for the losses.

    Returns:
        The simple-glazing window and its losses: each layer (lost) and the U, SHGC and VT that
        replace them (approximate).

    Raises:
        ValueError: The construction has no glazing layer, a layer has no material, or a gas
            has no EnergyPlus gas type (such as SF6).
    """
    glazings = _glazings(construction)
    try:
        idf = _idfkit_construction(construction)
        u_value = calculate_u_value(idf)
        shgc = calculate_shgc(idf)
        visible = calculate_visible_transmittance(idf)
    except IdfKitError as error:
        # idfkit refuses a layer EnergyPlus would refuse; the reader reports a ValueError.
        msg = f"window construction {construction.name!r}: {error}"
        raise ValueError(msg) from error
    if shgc is None or visible is None:  # pragma: no cover - every layer is glazing or gas
        msg = f"idfkit.thermal cannot compute SHGC and VT of window construction {construction.name!r}"
        raise ValueError(msg)
    window = GlazingConstructionSimpleComponent(
        Name=construction.name or "Window",
        UValue=u_value,
        SHGF=shgc,
        TVis=visible,
        Type=_TYPES.get(glazings, "Triple"),
        Category=construction.category,
        Comment=construction.comments,
        DataSource=construction.data_source,
    )
    losses = [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{location}/Layers/{index}",
            value=layer.model_dump(mode="json", by_alias=True),
            rule=_LAYERS,
            reason=f"{reason or 'The layers cannot be a layered SBEM window'}: the window is simple glazing, "
            "and the layer itself is not kept.",
        )
        for index, layer in enumerate(construction.layers)
    ]
    losses.append(
        Loss(
            kind=LossKind.APPROXIMATE,
            subject=subject,
            location=f"{location}/Layers",
            value=[layer.material.name if layer.material else None for layer in construction.layers],
            replacement={"UValue": u_value, "SHGF": shgc, "TVis": visible},
            rule=_LAYERS,
            reason=f"U, SHGC and VT are {_SIMPLIFIED}; each pane's dirt factor is applied to its transmittances.",
        )
    )
    # Simple glazing has no assembly life-cycle fields: they are lost, not dropped silently.
    losses += [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{location}/{key}",
            value=value,
            rule="construction.environmental",
            reason="SBEM's simple-glazing window has no assembly life-cycle fields.",
        )
        for key, name in ASSEMBLY_LIFE_CYCLE.items()
        if (value := getattr(construction, name))
    ]
    return window, losses


def _window_life_cycle_losses(window: SbemWindow, *, subject: str, location: str) -> list[Loss]:
    """The SBEM window's own life-cycle fields, which a UMI window construction cannot hold."""
    return [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{location}.{key}",
            value=value,
            rule="construction.environmental",
            reason="A UMI window construction has no cost, rate unit, life or embodied carbon of its own.",
        )
        for key in ("Cost", "RateUnit", "Life", "EmbodiedCarbon")
        if (value := getattr(window, key, None)) is not None
    ]


_SIMPLE_U_MIN = 0.01
"""The lowest U, W/m2-K, written for a simple-glazing window (EnergyPlus refuses 0)."""
_SIMPLE_FRACTION_MIN = 0.001
"""The margin kept from 0 and 1 for SHGC and VT (EnergyPlus refuses both ends)."""


def equivalent_layer(
    window: GlazingConstructionSimpleComponent, *, subject: str, location: str
) -> tuple[WindowConstruction, list[Loss]]:
    """Write an SBEM simple-glazing window as the one glazing layer EnergyPlus simulates for it.

    The writing bridge of `window.layers`.

    The layer comes from EnergyPlus's simple window model (`archetypal.umi._bridges` until
    UP-10). The construction and the window share the name; the glazing material is named
    `"{name} glazing"`.

    Args:
        window: The SBEM window.
        subject: The archetype being written, for the losses.
        location: The window's SBEM path, such as `"perimeter.Envelope.Window"`.

    Returns:
        The UMI window construction and its loss: the window, written in another form
        (approximate).
    """
    # EnergyPlus's simple window model takes U in (0, 7] and SHGC and VT strictly between 0 and
    # 1; SBEM allows any U >= 0 and the closed [0, 1]. Values outside are moved inside.
    u_value = min(max(window.UValue, _SIMPLE_U_MIN), MAX_U_FACTOR)
    shgc = min(max(window.SHGF, _SIMPLE_FRACTION_MIN), 1.0 - _SIMPLE_FRACTION_MIN)
    visible = min(max(window.TVis, _SIMPLE_FRACTION_MIN), 1.0 - _SIMPLE_FRACTION_MIN)
    layer = equivalent_glazing_layer(u_value, shgc, visible)
    glass = GlazingMaterial(
        Name=f"{window.Name} glazing",
        Category=window.Category or "Uncategorized",
        Comments=window.Comment,
        DataSource=window.DataSource,
        Conductivity=layer.conductivity,
        DirtFactor=1.0,
        IREmissivityBack=layer.back_infrared_emissivity,
        IREmissivityFront=layer.front_infrared_emissivity,
        IRTransmittance=layer.infrared_transmittance,
        SolarReflectanceBack=layer.back_solar_reflectance,
        SolarReflectanceFront=layer.front_solar_reflectance,
        SolarTransmittance=layer.solar_transmittance,
        VisibleReflectanceBack=layer.back_visible_reflectance,
        VisibleReflectanceFront=layer.front_visible_reflectance,
        VisibleTransmittance=layer.visible_transmittance,
    )
    construction = WindowConstruction(
        Name=window.Name,
        Category=window.Category or "Uncategorized",
        Comments=window.Comment,
        DataSource=window.DataSource,
        Layers=(MaterialLayer[GlazingMaterial | GasMaterial](Material=glass, Thickness=layer.thickness),),
    )
    reason = (
        "UMI has no simple glazing: the window is written as the single glazing layer EnergyPlus's "
        "simple window model derives from U, SHGC and VT."
    )
    if (u_value, shgc, visible) != (window.UValue, window.SHGF, window.TVis):
        reason += (
            f" EnergyPlus's simple window model takes U in (0, {MAX_U_FACTOR}] and SHGC and VT strictly between "
            f"0 and 1, so U, SHGC and VT {window.UValue:g}, {window.SHGF:g}, {window.TVis:g} were written as "
            f"{u_value:g}, {shgc:g}, {visible:g}."
        )
    if window.UValue > LAYER_U_MAX:
        reason += f" EnergyPlus computes at most {LAYER_U_MAX} W/m2-K for a glazing layer, so U is not reproduced."
    loss = Loss(
        kind=LossKind.APPROXIMATE,
        subject=subject,
        location=location,
        value={"UValue": window.UValue, "SHGF": window.SHGF, "TVis": window.TVis, "Type": window.Type},
        replacement={"Layers": [{"Material": glass.name, "Thickness": layer.thickness}]},
        rule=_LAYERS,
        reason=reason,
    )
    version = Findings()
    lose_version(window, location, subject, version)
    return construction, [loss, *_window_life_cycle_losses(window, subject=subject, location=location), *version.losses]


# --- Layered windows (window.layers, UP-9) ---------------------------------------------------------


def _category(value: str) -> str | None:
    return None if value == _UNCATEGORIZED else value


def _cost_per_kg(cost: float, density: float, pointer: str, subject: str, findings: Findings) -> float | None:
    """A UMI cost per m³ as a cost per kg, or `None` (lost) when the density is 0."""
    if cost == 0.0:
        return None
    if density <= 0.0:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{pointer}/Cost",
            cost,
            "material.cost_per_m3",
            "SBEM holds the cost of a window material per kg, and a material of density 0 has none per kg.",
        )
        return None
    return cost / density


def _glass_to_sbem(
    material: GlazingMaterial, pointer: str, subject: str, findings: Findings
) -> GlazingMaterialComponent:
    return GlazingMaterialComponent.model_validate({
        "Name": material.name or "",
        "Category": _category(material.category),
        "Comment": material.comments,
        "DataSource": material.data_source,
        "Conductivity": material.conductivity,
        "Density": material.density,
        "SolarTransmittance": material.solar_transmittance,
        "SolarReflectanceFront": material.solar_reflectance_front,
        "SolarReflectanceBack": material.solar_reflectance_back,
        "VisibleTransmittance": material.visible_transmittance,
        "VisibleReflectanceFront": material.visible_reflectance_front,
        "VisibleReflectanceBack": material.visible_reflectance_back,
        "IRTransmittance": material.ir_transmittance,
        "IREmissivityFront": material.ir_emissivity_front,
        "IREmissivityBack": material.ir_emissivity_back,
        "DirtFactor": material.dirt_factor,
        "RateUnit": _PER_MASS,
        "Cost": non_negative(
            _cost_per_kg(material.cost, material.density, pointer, subject, findings),
            "Cost",
            pointer,
            subject,
            findings,
            "material.cost_per_m3",
        ),
        "EmbodiedCarbon": non_negative(
            material.embodied_carbon, "EmbodiedCarbon", pointer, subject, findings, "material.carbon_per_m3"
        ),
        **life_cycle_to_sbem(material, subject, pointer, findings, per_volume=False),
    })


def _gas_to_sbem(material: GasMaterial, pointer: str, subject: str, findings: Findings) -> GasMaterialComponent:
    for key, value in (("Conductivity", material.conductivity), ("Density", material.density)):
        if value != 0.0:
            findings.lose(
                LossKind.LOST,
                subject,
                f"{pointer}/{key}",
                value,
                "material.properties",
                f"SBEM gases have no {key.lower()}: EnergyPlus knows each gas's properties.",
            )
    if material.cost != 0.0:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{pointer}/Cost",
            material.cost,
            "material.cost_per_m3",
            "SBEM gases have no density, so a cost per m3 cannot be given per kg.",
        )
    return GasMaterialComponent.model_validate({
        "Name": material.name or "",
        "Comment": material.comments,
        "DataSource": material.data_source,
        "GasType": _gas_type(material),
        "RateUnit": _PER_MASS,
        "EmbodiedCarbon": non_negative(
            material.embodied_carbon, "EmbodiedCarbon", pointer, subject, findings, "material.carbon_per_m3"
        ),
        **life_cycle_to_sbem(material, subject, pointer, findings, per_volume=False),
    })


def _layered(
    construction: WindowConstruction, *, subject: str, location: str, findings: Findings
) -> GlazingConstructionLayeredComponent:
    """Build the layered window; raises `ValueError` when the fork cannot hold the layers."""
    panes = sum(isinstance(layer.material, GlazingMaterial) for layer in construction.layers)
    if panes > MAX_GLAZING_LAYERS:
        msg = f"it has {panes} panes, more than the {MAX_GLAZING_LAYERS} a layered SBEM window holds"
        raise ValueError(msg)
    layers: list[GlazingLayerComponent | GasLayerComponent] = []
    for index, layer in enumerate(construction.layers):
        material = layer.material
        pointer = f"{location}/Layers/{index}/Material"
        if isinstance(material, GlazingMaterial):
            layers.append(
                GlazingLayerComponent(
                    Thickness=layer.thickness, GlazingMaterial=_glass_to_sbem(material, pointer, subject, findings)
                )
            )
        elif isinstance(material, GasMaterial):
            layers.append(
                GasLayerComponent(
                    Thickness=layer.thickness, GasMaterial=_gas_to_sbem(material, pointer, subject, findings)
                )
            )
        else:
            msg = f"layer {index} has no material"
            raise ValueError(msg)  # noqa: TRY004 - a malformed library, not a wrong argument type
    for key, value in (
        ("AssemblyCarbon", construction.assembly_carbon),
        ("AssemblyCost", construction.assembly_cost),
        ("AssemblyEnergy", construction.assembly_energy),
        ("DisassemblyCarbon", construction.disassembly_carbon),
        ("DisassemblyEnergy", construction.disassembly_energy),
    ):
        if value < 0:
            findings.lose(
                LossKind.LOST,
                subject,
                f"{location}/{key}",
                value,
                "construction.environmental",
                f"SBEM's {key} cannot be negative.",
            )
    return GlazingConstructionLayeredComponent.model_validate({
        "Name": construction.name or "Window",
        "Category": _category(construction.category),
        "Comment": construction.comments,
        "DataSource": construction.data_source,
        "Layers": layers,
        # Above three panes there is no SBEM type: `None` names the window by its number of panes.
        "Type": _TYPES.get(panes, "Triple" if panes == _TRIPLE_PANES else None),
        **assembly_life_cycle_to_sbem(construction),
    })


@rule("window.layers", to="sbem")
def layers_to_sbem(construction: WindowConstruction, *, subject: str, location: str) -> tuple[SbemWindow, list[Loss]]:
    """Read a UMI window construction as UP-9's layered window, exactly.

    When the fork cannot hold the layers (more than 4 panes, panes and gases not alternating, a
    property outside its range), the window is reduced to simple glazing (`simple_from_layers`).

    Args:
        construction: The UMI window construction.
        subject: The building template being read, for the losses.
        location: The construction's JSON pointer in the UMI file.

    Returns:
        The SBEM window and its losses.

    Raises:
        ValueError: The construction has no glazing layer, a layer has no material, or a gas
            has no EnergyPlus gas type (such as SF6).
    """
    _glazings(construction)
    findings = Findings()
    try:
        window = _layered(construction, subject=subject, location=location, findings=findings)
    except (ValueError, ValidationError) as error:
        reason = str(error).splitlines()[0] if not isinstance(error, ValidationError) else _first_error(error)
        return simple_from_layers(construction, subject=subject, location=location, reason=reason)
    return window, findings.losses


def _first_error(error: ValidationError) -> str:
    first = error.errors()[0]
    where = ".".join(str(step) for step in first["loc"])
    return f"{where}: {first['msg']}" if where else str(first["msg"])


def _glass_to_umi(
    material: GlazingMaterialComponent, location: str, subject: str, findings: Findings
) -> GlazingMaterial:
    lose_version(material, location, subject, findings)
    # An unset RateUnit is per m3, as for opaque materials (`material.cost_per_m3`).
    density = material.Density or 0.0
    per_volume = material.RateUnit in (None, "m3")
    cost = 0.0
    if material.Cost:
        if per_volume:
            cost = material.Cost
        elif material.RateUnit == _PER_MASS and density > 0:
            cost = material.Cost * density
        else:
            findings.lose(
                LossKind.LOST,
                subject,
                f"{location}.Cost",
                material.Cost,
                "material.cost_per_m3",
                f"UMI holds cost per m3; a cost per {material.RateUnit} needs a density or thickness "
                "the material lacks.",
                replacement=0.0,
            )
    carbon = material.EmbodiedCarbon or 0.0
    if carbon and material.RateUnit != _PER_MASS:
        if per_volume and density > 0:
            carbon /= density
        else:
            findings.lose(
                LossKind.LOST,
                subject,
                f"{location}.EmbodiedCarbon",
                carbon,
                "material.carbon_per_m3",
                f"UMI holds carbon per kg; a carbon per {material.RateUnit or 'm3'} needs a density or thickness "
                "the material lacks.",
                replacement=0.0,
            )
            carbon = 0.0
    return GlazingMaterial.model_validate({
        "Name": material.Name,
        "Category": material.Category or _UNCATEGORIZED,
        "Comments": material.Comment,
        "DataSource": material.DataSource,
        "Conductivity": material.Conductivity,
        "Density": density,
        "SolarTransmittance": material.SolarTransmittance,
        "SolarReflectanceFront": material.SolarReflectanceFront,
        "SolarReflectanceBack": material.SolarReflectanceBack,
        "VisibleTransmittance": material.VisibleTransmittance,
        "VisibleReflectanceFront": material.VisibleReflectanceFront,
        "VisibleReflectanceBack": material.VisibleReflectanceBack,
        "IRTransmittance": material.IRTransmittance,
        "IREmissivityFront": material.IREmissivityFront,
        "IREmissivityBack": material.IREmissivityBack,
        "DirtFactor": material.DirtFactor,
        "Cost": cost,
        "EmbodiedCarbon": carbon,
        **life_cycle_to_umi(material, material.RateUnit, density, subject, location, findings),
    })


def _gas_to_umi(material: GasMaterialComponent, location: str, subject: str, findings: Findings) -> GasMaterial:
    lose_version(material, location, subject, findings)
    if material.Cost is not None:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{location}.Cost",
            material.Cost,
            "material.cost_per_m3",
            "UMI holds cost per m3, and an SBEM gas has no density to convert it.",
            replacement=0.0,
        )
    if material.Category is not None:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{location}.Category",
            material.Category,
            _LAYERS,
            'Basilisk fixes the category of gas materials to "Gases".',
            replacement="Gases",
        )
    # An SBEM gas has no density (UMI writes 0), so only a carbon per kg converts.
    carbon = material.EmbodiedCarbon or 0.0
    if carbon and material.RateUnit != _PER_MASS:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{location}.EmbodiedCarbon",
            carbon,
            "material.carbon_per_m3",
            f"UMI holds carbon per kg; a carbon per {material.RateUnit or 'm3'} needs a density or thickness "
            "an SBEM gas lacks.",
            replacement=0.0,
        )
        carbon = 0.0
    return GasMaterial.model_validate({
        "Name": material.Name,
        "Comments": material.Comment,
        "DataSource": material.DataSource,
        "Type": material.GasType.upper(),
        "EmbodiedCarbon": carbon,
        **life_cycle_to_umi(material, material.RateUnit, None, subject, location, findings),
    })


@rule("window.layers", to="umi")
def layers_to_umi(window: SbemWindow, *, subject: str, location: str) -> tuple[WindowConstruction, list[Loss]]:
    """Write an SBEM window as a UMI window construction.

    A layered window (UP-9) is written layer by layer, exactly; a simple-glazing window as its
    equivalent layer (`equivalent_layer`, approximate).

    Args:
        window: The SBEM window.
        subject: The archetype being written, for the losses.
        location: The window's SBEM path, such as `"perimeter.Envelope.Window"`.

    Returns:
        The UMI window construction and its losses.
    """
    if isinstance(window, GlazingConstructionSimpleComponent):
        return equivalent_layer(window, subject=subject, location=location)
    findings = Findings()
    layers: list[MaterialLayer[GlazingMaterial | GasMaterial]] = []
    for index, layer in enumerate(window.Layers):
        where = f"{location}.Layers.{index}"
        material: GlazingMaterial | GasMaterial = (
            _glass_to_umi(layer.GlazingMaterial, f"{where}.GlazingMaterial", subject, findings)
            if isinstance(layer, GlazingLayerComponent)
            else _gas_to_umi(layer.GasMaterial, f"{where}.GasMaterial", subject, findings)
        )
        layers.append(MaterialLayer[GlazingMaterial | GasMaterial](Material=material, Thickness=layer.Thickness))
    if window.Version is not None:
        findings.lose(
            LossKind.LOST,
            subject,
            f"{location}.Version",
            window.Version,
            "names.metadata",
            "UMI components have no version.",
        )
    construction = WindowConstruction.model_validate({
        "Name": window.Name,
        "Category": window.Category or _UNCATEGORIZED,
        "Comments": window.Comment,
        "DataSource": window.DataSource,
        "Layers": layers,
        **assembly_life_cycle_to_umi(window),
    })
    return construction, [*findings.losses, *_window_life_cycle_losses(window, subject=subject, location=location)]


@rule("window.placement", to="sbem")
def place_window(window: SbemWindow | None, groups: Sequence[str]) -> dict[str, SbemWindow | None]:
    """Give every zone group the building template's window.

    Args:
        window: The template's window, or `None` when it has none.
        groups: The zone group names.

    Returns:
        Each group's window, by group name.
    """
    return dict.fromkeys(groups, window)


@rule("window.placement", to="umi")
def template_window(
    windows: Mapping[str, SbemWindow | None], *, subject: str, chosen: str | None = None
) -> tuple[SbemWindow | None, list[Loss]]:
    """Choose the building template's window from the zone groups' windows.

    The `chosen` group's window is used: the perimeter-exposed group's, which the writer passes
    (by default the group named `perimeter`, else the first group). Another group's window that
    differs from it is lost; a group without a window loses nothing.

    Args:
        windows: Each group's window, by group name, in group order.
        subject: The archetype being written, for the losses.
        chosen: The name of the group whose window is used.

    Returns:
        The template's window and the losses.
    """
    if not windows:
        return None, []
    chosen_group = _chosen_group(windows, chosen)
    if windows[chosen_group] is None:
        # The chosen group has no window: use the first group's that has one rather than
        # writing a default window the archetype never had.
        chosen_group = next((group for group, other in windows.items() if other is not None), chosen_group)
    window = windows[chosen_group]
    losses = [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{group}.Envelope.Window",
            value=other.model_dump(mode="json", exclude_none=True),
            replacement=None if window is None else window.Name,
            rule="window.placement",
            reason=f"UMI has one window per building template: the {chosen_group} group's window is used.",
        )
        for group, other in windows.items()
        if group != chosen_group and other is not None and other != window
    ]
    return window, losses


def _chosen_group(groups: Mapping[str, object], chosen: str | None) -> str:
    """The group whose window (settings) the template takes: `chosen`, else `perimeter`, else the first."""
    if chosen is not None and chosen in groups:
        return chosen
    return PERIMETER if PERIMETER in groups else next(iter(groups))


# --- Window settings (window.settings, UP-9) -------------------------------------------------------


@rule("window.settings", to="sbem")
def settings_to_sbem(
    settings: WindowSettings, *, schedule: ScheduleToSbem, context: RuleContext
) -> WindowSettingsComponent:
    """Read UMI window settings as UP-9's `WindowSettingsComponent`.

    Operable area and shading are copied; an always-on shading availability schedule is SBEM's
    `None`. A transmittance of 1 (SBEM needs less) and a schedule without Fraction limits are
    lost, SBEM's defaults kept. The interior-window, zone-mixing and airflow-network fields,
    which UP-9 does not add, are lost unless at Basilisk's defaults.

    Args:
        settings: The UMI window settings.
        schedule: The schedule converter.
        context: Their reading context (`/BuildingTemplates/<i>/Windows`).
    """
    report_upstream(settings, _SETTINGS, context)
    fields: dict[str, object] = {
        **identity_to_sbem(settings),
        "OperableArea": settings.operable_area,
        "IsShadingSystemOn": settings.is_shading_system_on,
        "ShadingSystemType": settings.shading_system_type.name,
        "ShadingSystemSetpoint": settings.shading_system_setpoint,
        "ShadingSystemAvailabilitySchedule": optional_schedule_to_sbem(
            settings.shading_system_availability_schedule,
            "ShadingSystemAvailabilitySchedule",
            "Window",
            schedule=schedule,
            context=context,
            rule_id=_SETTINGS,
        ),
    }
    checks = (
        ("OperableArea", settings.operable_area, 0.0 <= settings.operable_area <= 1.0, "in [0, 1]"),
        (
            "ShadingSystemSetpoint",
            settings.shading_system_setpoint,
            settings.shading_system_setpoint >= 0,
            "at least 0",
        ),
    )
    for key, value, valid, expected in checks:
        if not valid:
            fields.pop(key)
            context.lose(key, value, rule=_SETTINGS, reason=f"SBEM's {key} must be {expected}; its default is kept")
    transmittance = settings.shading_system_transmittance
    if 0.0 <= transmittance < 1.0:
        fields["ShadingSystemTransmittance"] = transmittance
    else:
        context.lose(
            "ShadingSystemTransmittance",
            transmittance,
            rule=_SETTINGS,
            reason="SBEM's shade transmittance must be in [0, 1); its default is kept",
        )
    return WindowSettingsComponent.model_validate(fields)


@rule("window.settings", to="umi")
def settings_to_umi(
    settings: WindowSettingsComponent | None,
    construction: WindowConstruction,
    *,
    schedule: ScheduleToUmi,
    context: RuleContext,
) -> WindowSettings:
    """Write UMI window settings from a group's `WindowSettingsComponent` (UP-9) and the window.

    `None` (fully operable, unshaded) is written as an operable area of 1 without shading,
    named after the window. The fields UP-9 does not add take Basilisk's defaults (noted), with
    always-on schedules.

    Args:
        settings: The group's window settings, or `None`.
        construction: The UMI window construction written.
        schedule: The schedule converter.
        context: The writing context at the settings (`<group>.Envelope.WindowSettings`).
    """
    always_on = optional_schedule_to_umi(
        None, "AfnWindowAvailability", schedule=schedule, context=context, rule_id=_SETTINGS
    )
    fields: dict[str, object] = {
        **upstream_defaults(WindowSettings, _SETTINGS, context),
        "Construction": construction,
        "AfnWindowAvailability": always_on,
        "ZoneMixingAvailabilitySchedule": always_on,
    }
    if settings is None:
        context.note(
            "",
            None,
            rule=_SETTINGS,
            reason="The group has no window settings: fully operable windows without shading are written",
        )
        fields.update({
            "Name": window_settings_name(construction.name or ""),
            "OperableArea": 1.0,
            "IsShadingSystemOn": False,
            "ShadingSystemAvailabilitySchedule": always_on,
        })
        return WindowSettings.model_validate(fields)
    fields.update({
        **identity_to_umi(settings, context),
        "OperableArea": settings.OperableArea,
        "IsShadingSystemOn": settings.IsShadingSystemOn,
        "ShadingSystemType": ShadingType[settings.ShadingSystemType],
        "ShadingSystemSetpoint": settings.ShadingSystemSetpoint,
        "ShadingSystemTransmittance": settings.ShadingSystemTransmittance,
        "ShadingSystemAvailabilitySchedule": optional_schedule_to_umi(
            settings.ShadingSystemAvailabilitySchedule,
            "ShadingSystemAvailabilitySchedule",
            schedule=schedule,
            context=context,
            rule_id=_SETTINGS,
        ),
    })
    return WindowSettings.model_validate(fields)


def template_settings(
    settings: Mapping[str, WindowSettingsComponent | None], *, subject: str, chosen: str | None = None
) -> tuple[str, WindowSettingsComponent | None, list[Loss]]:
    """Choose the building template's window settings from the zone groups' (UP-9).

    As for the window: the `chosen` group's (by default the group named `perimeter`, else the
    first group); another group's settings that differ are lost, `None` (fully operable,
    unshaded) included. The writer leaves out a group with neither window nor settings: it
    simulates no window, so gaining the template's settings changes nothing (noted instead).

    Args:
        settings: Each group's window settings, by group name, in group order.
        subject: The archetype being written, for the losses.
        chosen: The name of the group whose settings are used.

    Returns:
        The chosen group's name, its settings and the losses; with no groups, `chosen` (or
        `perimeter`), no settings and no losses.
    """
    if not settings:
        return chosen if chosen is not None else PERIMETER, None, []
    chosen_group = _chosen_group(settings, chosen)
    chosen_settings = settings[chosen_group]
    losses = [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{group}.Envelope.WindowSettings",
            value=None if other is None else other.model_dump(mode="json", exclude_none=True),
            replacement=None if chosen_settings is None else chosen_settings.Name,
            rule=_SETTINGS,
            reason=f"UMI has one window settings per building template: the {chosen_group} group's are used.",
        )
        for group, other in settings.items()
        if group != chosen_group and other != chosen_settings
    ]
    return chosen_group, chosen_settings, losses
