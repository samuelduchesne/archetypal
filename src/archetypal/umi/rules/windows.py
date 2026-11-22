"""Window rules (spec 003, research R8): simple glazing from layers, the equivalent layer, placement.

UMI windows are layers of glazing and gas; SBEM windows (until UP-9's layered windows) are simple
glazing: U-factor, SHGC and visible transmittance.

- `window.simple_from_layers` (reading): the UMI layers become an in-memory idfkit
  `Construction`, and `idfkit.thermal` gives U, SHGC and VT. Each layer is lost (UP-9), and the
  three values are approximate: idfkit's simplified method is not EnergyPlus's window model.
- `window.equivalent_layer` (writing): a simple-glazing window becomes the one glazing layer
  EnergyPlus's simple window model builds from it (`archetypal.umi._bridges` until UP-10), so
  EnergyPlus simulates the same window. The window is listed as approximate: it is written in
  another form.
- `window.placement`: UMI has one window per building template, SBEM one per zone group.
  Reading gives every group the template's window; writing uses the perimeter group's window
  and lists a different window of another group as lost.
- `window.settings`: the other `WindowSettings` fields, lost until UP-9 (no function).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from epinterface.sbem.components.envelope import GlazingConstructionSimpleComponent
from idfkit import new_document
from idfkit.thermal import calculate_shgc, calculate_u_value, calculate_visible_transmittance

from archetypal.umi._bridges import equivalent_glazing_layer
from archetypal.umi._format import GasMaterial, GlazingMaterial, MaterialLayer, WindowConstruction
from archetypal.umi.correspondence import declare_rule, rule
from archetypal.umi.report import Loss, LossKind

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from idfkit.document import Construction

__all__ = [
    "LAYER_U_MAX",
    "PERIMETER",
    "equivalent_layer",
    "place_window",
    "simple_from_layers",
    "template_window",
]

PERIMETER = "perimeter"
"""The zone group whose window a building template gets on writing."""

LAYER_U_MAX = 5.83
"""The largest U-factor (W/m2-K) EnergyPlus 24.2 computes for a single glazing layer.

With its standard film coefficients, no `WindowMaterial:Glazing` gives more; a simple glazing
above it is written as a layer at about this U (`verification/umi/simple_glazing.py`).
"""

WindowType = Literal["Single", "Double", "Triple"]
_TYPES: dict[int, WindowType] = {1: "Single", 2: "Double"}
GasType = Literal["Air", "Argon", "Krypton", "Xenon"]
_GASES: dict[str, GasType] = {"AIR": "Air", "ARGON": "Argon", "KRYPTON": "Krypton", "XENON": "Xenon"}
_MAX_LAYERS = 10  # of an EnergyPlus Construction
_SIMPLIFIED = (
    "computed from the layers by idfkit.thermal's simplified method (normal incidence, NFRC films), "
    "not by EnergyPlus's window model"
)

declare_rule("window.settings")


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
            doc.window_material_glazings.add(
                name,
                optical_data_type="SpectralAverage",
                thickness=layer.thickness,
                solar_transmittance_at_normal_incidence=material.solar_transmittance,
                front_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_front,
                back_side_solar_reflectance_at_normal_incidence=material.solar_reflectance_back,
                visible_transmittance_at_normal_incidence=material.visible_transmittance,
                front_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_front,
                back_side_visible_reflectance_at_normal_incidence=material.visible_reflectance_back,
                infrared_transmittance_at_normal_incidence=material.ir_transmittance,
                front_side_infrared_hemispherical_emissivity=material.ir_emissivity_front,
                back_side_infrared_hemispherical_emissivity=material.ir_emissivity_back,
                conductivity=material.conductivity,
                dirt_correction_factor_for_solar_and_visible_transmittance=material.dirt_factor,
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


@rule("window.simple_from_layers", to="sbem")
def simple_from_layers(
    construction: WindowConstruction, *, subject: str, location: str
) -> tuple[GlazingConstructionSimpleComponent, list[Loss]]:
    """Reduce a UMI window construction to SBEM simple glazing.

    Args:
        construction: The UMI window construction.
        subject: The building template being read, for the losses.
        location: The construction's JSON pointer in the UMI file.

    Returns:
        The simple-glazing window and its losses: each layer (lost until UP-9) and the U, SHGC
        and VT that replace them (approximate).

    Raises:
        ValueError: The construction has no glazing layer, a layer has no material, or a gas
            has no EnergyPlus gas type (such as SF6).
    """
    glazings = _glazings(construction)
    idf = _idfkit_construction(construction)
    u_value = calculate_u_value(idf)
    shgc = calculate_shgc(idf)
    visible = calculate_visible_transmittance(idf)
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
            rule="window.simple_from_layers",
            reason="SBEM windows are simple glazing: the layer itself is not kept.",
            upstream="UP-9",
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
            rule="window.simple_from_layers",
            reason=f"U, SHGC and VT are {_SIMPLIFIED}.",
            upstream="UP-9",
        )
    )
    return window, losses


@rule("window.equivalent_layer", to="umi")
def equivalent_layer(
    window: GlazingConstructionSimpleComponent, *, subject: str, location: str
) -> tuple[WindowConstruction, list[Loss]]:
    """Write an SBEM simple-glazing window as the one glazing layer EnergyPlus simulates for it.

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
    layer = equivalent_glazing_layer(window.UValue, window.SHGF, window.TVis)
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
    if window.UValue > LAYER_U_MAX:
        reason += f" EnergyPlus computes at most {LAYER_U_MAX} W/m2-K for a glazing layer, so U is not reproduced."
    loss = Loss(
        kind=LossKind.APPROXIMATE,
        subject=subject,
        location=location,
        value={"UValue": window.UValue, "SHGF": window.SHGF, "TVis": window.TVis, "Type": window.Type},
        replacement={"Layers": [{"Material": glass.name, "Thickness": layer.thickness}]},
        rule="window.equivalent_layer",
        reason=reason,
    )
    return construction, [loss]


@rule("window.placement", to="sbem")
def place_window(
    window: GlazingConstructionSimpleComponent | None, groups: Sequence[str]
) -> dict[str, GlazingConstructionSimpleComponent | None]:
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
    windows: Mapping[str, GlazingConstructionSimpleComponent | None], *, subject: str
) -> tuple[GlazingConstructionSimpleComponent | None, list[Loss]]:
    """Choose the building template's window from the zone groups' windows.

    The perimeter group's window is used (the first group's when there is no perimeter group).
    Another group's window that differs from it is lost; a group without a window loses
    nothing.

    Args:
        windows: Each group's window, by group name, in group order.
        subject: The archetype being written, for the losses.

    Returns:
        The template's window and the losses.
    """
    if not windows:
        return None, []
    chosen_group = PERIMETER if PERIMETER in windows else next(iter(windows))
    chosen = windows[chosen_group]
    losses = [
        Loss(
            kind=LossKind.LOST,
            subject=subject,
            location=f"{group}.Envelope.Window",
            value=window.model_dump(mode="json", exclude_none=True),
            replacement=None if chosen is None else chosen.Name,
            rule="window.placement",
            reason=f"UMI has one window per building template: the {chosen_group} group's window is used.",
        )
        for group, window in windows.items()
        if group != chosen_group and window is not None and window != chosen
    ]
    return chosen, losses
