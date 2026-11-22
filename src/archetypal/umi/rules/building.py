"""Building rules: template ↔ archetype, window-to-wall ratio, metadata and names (R4, R11, R13).

- **Groups** (`building.groups`). A building template becomes an archetype with two zone
  groups, `core` and `perimeter`, built from the template's `Core` and `Perimeter` zone
  definitions. Their floor-area shares are unset (`None`): the building's geometry sets them
  when the archetype is applied (research R4; the fork's `ZoneGroup.FloorAreaShare`). When
  both reference one zone definition, the definition is translated once and both groups hold
  it. On writing, an archetype must already have core and perimeter groups, or a single group
  (research R12): set shares are dropped and reported, and a single group is copied to both.
- **Window-to-wall ratio** (`wwr.uniform`). The template's one ratio becomes the ratio of
  every orientation. On writing, a uniform ratio is copied; differing ratios become the
  facade-area-weighted mean (the plain mean when facade areas are unknown) and are reported as
  lost. The mean conserves window area for a given facade.
- **Template-level fields** (UP-9, research R6). The descriptive and life-cycle fields
  (`building.metadata`) and the template's `Category`, `Comments` and `DataSource`
  (`names.metadata`) map to the archetype's fields of the same names; the structure
  (`structure.component`) to the archetype's `StructureComponent`, field by field. The partition
  ratio (`building.partition_ratio`), partition wall area per floor area, becomes each group's
  `PartitionAreaPerFloorArea`, which counts both faces: twice the ratio. Writing takes the
  perimeter group's and loses a different one of another group.
- **Names** (`names.component`, data-model.md "Names of components without a one-to-one
  counterpart"). Reading names each SBEM sub-component from the UMI component that holds its
  content; writing recovers the UMI name from the parent, so names survive both round trips.
  `UniqueNames` gives the ` #2`, ` #3`, … suffixes of research R11 and R13.
- **Metadata** (`names.metadata`). `Category`, `Comments` and `DataSource` map to the receiving
  SBEM component's `Category`, `Comment` and `DataSource`. Basilisk's default category,
  `"Uncategorized"`, is SBEM's unset category.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from epinterface.sbem.archetype import ORIENTATIONS, Archetype, BuildingGeometry, ZoneGroup
from epinterface.sbem.components.envelope import ZoneEnvelopeComponent
from epinterface.sbem.components.operations import ZoneOperationsComponent
from epinterface.sbem.components.structure import StructureComponent
from epinterface.sbem.components.zones import ZoneComponent

from archetypal.umi._format import (
    AdvancedStructuralModel,
    BuildingTemplate,
    MassRatios,
    OpaqueMaterial,
    StructureInformation,
)
from archetypal.umi.correspondence import declare_rule, rule
from archetypal.umi.report import Findings, Loss, LossKind, Note, NoteKind
from archetypal.umi.rules.materials import (
    assembly_life_cycle_losses,
    assembly_life_cycle_to_sbem,
    assembly_life_cycle_to_umi,
    material_to_sbem,
    material_to_umi,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping, Sequence

    from epinterface.sbem.archetype import Orientation
    from epinterface.sbem.common import MetadataMixin
    from epinterface.sbem.components.envelope import (
        EnvelopeAssemblyComponent,
        InfiltrationComponent,
        WindowConstruction,
        WindowSettingsComponent,
    )
    from epinterface.sbem.components.materials import ConstructionMaterialComponent
    from epinterface.sbem.components.space_use import ZoneSpaceUseComponent
    from epinterface.sbem.components.systems import DHWComponent, ZoneHVACComponent
    from pydantic import JsonValue

    from archetypal.umi._format import LibraryComponent, ZoneDefinition

__all__ = [
    "CORE_GROUP",
    "DERIVED_NAMES",
    "NAMED_FROM",
    "PERIMETER_GROUP",
    "UNCATEGORIZED",
    "MetadataFields",
    "TemplateZones",
    "UniqueNames",
    "WindowToWallRatio",
    "ZoneNames",
    "apply_names",
    "archetype_from_template",
    "collision_loss",
    "derived_name",
    "groups_from_template",
    "metadata_to_sbem",
    "metadata_to_umi",
    "partition_area_to_sbem",
    "partition_ratio_to_umi",
    "structure_to_sbem",
    "structure_to_umi",
    "template_losses",
    "template_metadata_to_sbem",
    "template_metadata_to_umi",
    "template_zones",
    "umi_names",
    "window_settings_name",
    "wwr_to_sbem",
    "wwr_to_umi",
    "zone_component",
]

CORE_GROUP = "core"
"""The name (and exposure) of the group built from a template's `Core` zone definition."""

PERIMETER_GROUP = "perimeter"
"""The name (and exposure) of the group built from a template's `Perimeter` zone definition."""

UNCATEGORIZED = "Uncategorized"
"""Basilisk's default `Category`, which SBEM holds as an unset category."""

_WWR_PATH = "archetype.Geometry.WindowToWallRatio"

declare_rule("building.library")


# --- Groups and shares (building.groups) --------------------------------------------------------


@rule("building.groups", to="sbem")
def groups_from_template(
    template: BuildingTemplate, translate_zone: Callable[[ZoneDefinition], ZoneComponent]
) -> list[ZoneGroup]:
    """Build the `core` and `perimeter` groups of a template, shares unset (research R4).

    Args:
        template: The building template.
        translate_zone: Translates one UMI zone definition into an SBEM zone definition.
            It is called once when `Core` and `Perimeter` reference one zone definition.

    Returns:
        The groups `core` and `perimeter`, in that order, with `FloorAreaShare = None` and the
        matching `Exposure`.

    Raises:
        ValueError: The template has no `Core` or no `Perimeter` (validation refuses both).
    """
    if template.core is None or template.perimeter is None:
        missing = "Core" if template.core is None else "Perimeter"
        msg = f"building template {template.name!r} has no {missing} zone definition"
        raise ValueError(msg)
    core = translate_zone(template.core)
    same = template.perimeter is template.core or template.perimeter == template.core
    perimeter = core if same else translate_zone(template.perimeter)
    return [
        ZoneGroup(Name=CORE_GROUP, Zone=core, FloorAreaShare=None, Exposure="core"),
        ZoneGroup(Name=PERIMETER_GROUP, Zone=perimeter, FloorAreaShare=None, Exposure="perimeter"),
    ]


def archetype_from_template(
    template: BuildingTemplate,
    translate_zone: Callable[[ZoneDefinition], ZoneComponent],
    *,
    pointer: str,
    name: str | None = None,
) -> tuple[Archetype, list[Loss]]:
    """Build the archetype of one template: its groups, window-to-wall ratio and name.

    Args:
        template: The building template.
        translate_zone: Translates one UMI zone definition into an SBEM zone definition.
        pointer: The template's JSON pointer, for example `"/BuildingTemplates/0"`.
        name: The archetype's name; by default the template's (a renamed duplicate passes its
            new name).

    Returns:
        The archetype, with the template's metadata and structure (UP-9), and what they lost.
        The partition ratio goes to the zone definitions (`partition_area_to_sbem`).

    Raises:
        ValueError: The template has no name, `Core` or `Perimeter`.
    """
    subject = name if name is not None else template.name
    if subject is None:
        msg = f"the building template at {pointer} has no name"
        raise ValueError(msg)
    metadata, losses = template_metadata_to_sbem(template, pointer=pointer, subject=subject)
    structure = None
    if template.structure is not None:
        structure, structure_losses = structure_to_sbem(
            template.structure, pointer=f"{pointer}/Structure", subject=subject
        )
        losses.extend(structure_losses)
    archetype = Archetype.model_validate({
        "Name": subject,
        "Groups": groups_from_template(template, translate_zone),
        "Geometry": BuildingGeometry(WindowToWallRatio=wwr_to_sbem(template.default_window_to_wall_ratio)),
        "Structure": structure,
        **metadata,
    })
    return archetype, losses


class TemplateZones(NamedTuple):
    """The zone definitions a template is written from, and what writing them lost."""

    core: ZoneComponent
    """The zone definition written as the template's `Core`."""
    perimeter: ZoneComponent
    """The zone definition written as the template's `Perimeter`."""
    losses: tuple[Loss, ...]
    """Dropped shares, a copied group and building-level fields UMI cannot hold."""


@rule("building.groups", to="umi")
def template_zones(archetype: Archetype) -> TemplateZones:
    """Return the core and perimeter zone definitions of an archetype (research R4, R12).

    An archetype with other groups must first be merged to core and perimeter (002's merge or
    the approximate merge). Set shares are dropped and reported (`layout.share_dropped`); a
    single group is written for both and reported (`layout.core_copied`). Building-level SBEM
    fields other than the window-to-wall ratio have no UMI counterpart and are reported as
    lost when set.

    Args:
        archetype: An archetype with core and perimeter groups, or a single group.

    Returns:
        The two zone definitions and the losses, sorted by location.

    Raises:
        ValueError: The archetype has more than two groups, or two that are not one core and
            one perimeter group.
    """
    subject = archetype.Name
    groups = archetype.Groups
    losses: list[Loss] = []
    if len(groups) == 1:
        only = groups[0]
        core = perimeter = only.Zone
        copied_to = "Perimeter" if only.Exposure == "core" else "Core"
        losses.append(
            Loss(
                kind=LossKind.COPIED,
                subject=subject,
                location=only.Name,
                value=only.Name,
                replacement=copied_to,
                rule="layout.core_copied",
                reason=f"The archetype has one group; its zone definition was also written as {copied_to}, "
                "copied, not derived.",
            )
        )
    else:
        by_exposure = {group.Exposure: group for group in groups}
        if len(groups) != 2 or "core" not in by_exposure or "perimeter" not in by_exposure:  # noqa: PLR2004
            names = ", ".join(repr(group.Name) for group in groups)
            msg = (
                f"archetype {subject!r} has groups {names}; a UMI template needs core and perimeter groups, "
                "so merge the groups to core and perimeter first"
            )
            raise ValueError(msg)
        core = by_exposure["core"].Zone
        perimeter = by_exposure["perimeter"].Zone
        losses.extend(
            Loss(
                kind=LossKind.SHARE_DROPPED,
                subject=subject,
                location=f"{group.Name}.FloorAreaShare",
                value=group.FloorAreaShare,
                rule="layout.share_dropped",
                reason="UMI templates have no floor-area shares: the geometry sets them when the template is used.",
            )
            for group in groups
            if group.FloorAreaShare is not None
        )
    losses.extend(_group_name_losses(groups, subject))
    losses.extend(_building_level_losses(archetype))
    return TemplateZones(core, perimeter, tuple(sorted(losses, key=lambda loss: loss.location)))


def _group_name_losses(groups: Sequence[ZoneGroup], subject: str) -> list[Loss]:
    """Report each group whose name is not the UMI zone it becomes: UMI has no group names."""
    losses: list[Loss] = []
    for group in groups:
        umi_name = CORE_GROUP if group.Exposure == CORE_GROUP else PERIMETER_GROUP
        if group.Name != umi_name:
            losses.append(
                Loss(
                    kind=LossKind.RENAMED,
                    subject=subject,
                    location=f"{group.Name}.Name",
                    value=group.Name,
                    replacement=umi_name,
                    rule="building.groups",
                    reason=f"UMI zones have no group names; the group reads back as {umi_name!r}.",
                )
            )
    return losses


def _building_level_losses(archetype: Archetype) -> list[Loss]:
    """Report the archetype's building-level fields that a UMI template cannot hold."""
    losses: list[Loss] = []
    for field in ("Attic", "Basement"):
        value: Any = getattr(archetype, field)
        default = Archetype.model_fields[field].get_default(call_default_factory=True)
        if value != default:
            losses.append(
                _lost(
                    archetype.Name,
                    f"archetype.{field}",
                    value.model_dump(mode="json"),
                    "building.groups",
                    f"UMI templates have no {field.lower()} assumptions.",
                )
            )
    geometry = archetype.Geometry
    for field in BuildingGeometry.model_fields:
        value = getattr(geometry, field)
        if field != "WindowToWallRatio" and value is not None:
            losses.append(
                _lost(
                    archetype.Name,
                    f"archetype.Geometry.{field}",
                    cast("JsonValue", value),
                    "building.groups",
                    "UMI templates carry no building geometry.",
                )
            )
    return losses


# --- Window-to-wall ratio (wwr.uniform) ----------------------------------------------------------


@rule("wwr.uniform", to="sbem")
def wwr_to_sbem(ratio: float) -> dict[Orientation, float]:
    """Return the template's window-to-wall ratio as the ratio of every orientation."""
    return BuildingGeometry.uniform(ratio)


class WindowToWallRatio(NamedTuple):
    """A template's `DefaultWindowToWallRatio`, and what writing it lost or assumed."""

    value: float
    """The ratio written."""
    losses: tuple[Loss, ...]
    """The per-orientation ratios, when they differ."""
    notes: tuple[Note, ...]
    """Basilisk's default, when the archetype has no ratio."""


@rule("wwr.uniform", to="umi")
def wwr_to_umi(geometry: BuildingGeometry, *, subject: str) -> WindowToWallRatio:
    """Return the single window-to-wall ratio of an archetype's geometry.

    Args:
        geometry: The archetype's geometry.
        subject: The archetype's name, for the report.

    Returns:
        The ratio: copied when every orientation has the same; else the facade-area-weighted
        mean (the plain mean without facade areas), with the per-orientation ratios reported as
        lost; Basilisk's default 0.4, noted, when the geometry has no ratio.
    """
    ratios = geometry.WindowToWallRatio
    if ratios is None:
        default = cast("float", BuildingTemplate.model_fields["default_window_to_wall_ratio"].default)
        note = Note(
            kind=NoteKind.DEFAULTED,
            subject=subject,
            location=_WWR_PATH,
            value=default,
            rule="wwr.uniform",
            reason="The archetype has no window-to-wall ratio; Basilisk's default was written.",
        )
        return WindowToWallRatio(default, (), (note,))
    values = [ratios[orientation] for orientation in ORIENTATIONS]
    if all(value == values[0] for value in values):
        return WindowToWallRatio(values[0], (), ())
    mean = geometry.OverallWindowToWallRatio
    if mean is None:  # pragma: no cover - set whenever the ratios are
        mean = math.fsum(values) / len(values)
    weighted = "facade-area-weighted" if geometry.FacadeAreaPerFloorArea is not None else "plain"
    loss = Loss(
        kind=LossKind.LOST,
        subject=subject,
        location=_WWR_PATH,
        value=cast("JsonValue", dict(ratios)),
        replacement=mean,
        rule="wwr.uniform",
        reason=f"A UMI template has one window-to-wall ratio; the orientations differ, so their {weighted} mean "
        "was written.",
    )
    return WindowToWallRatio(mean, (loss,), ())


# --- Template-level fields (UP-9) ------------------------------------------------------------------

_TEMPLATE_METADATA: tuple[tuple[str, str], ...] = (
    ("lifespan", "Lifespan"),
    ("year_from", "YearFrom"),
    ("year_to", "YearTo"),
    ("country", "Country"),
    ("climate_zone", "ClimateZone"),
    ("authors", "Authors"),
    ("author_emails", "AuthorEmails"),
    ("version", "Version"),
)
_FIELD_OF: dict[str, str] = {key: name for name, key in _TEMPLATE_METADATA}
PARTITION_FACES = 2.0
"""Faces of a partition wall exposed to the zone: SBEM's partition area counts both."""


def _lost(
    subject: str, location: str, value: JsonValue, rule_id: str, reason: str, upstream: str | None = None
) -> Loss:
    return Loss(
        kind=LossKind.LOST,
        subject=subject,
        location=location,
        value=value,
        rule=rule_id,
        reason=reason,
        upstream=upstream,
    )


def _json(value: object) -> JsonValue:
    """Return a template field as a JSON value: tuples as lists."""
    if isinstance(value, tuple):
        return [_json(item) for item in cast("tuple[object, ...]", value)]
    return cast("JsonValue", value)


def _subject(template: BuildingTemplate, subject: str | None) -> str:
    return subject if subject is not None else (template.name or "")


@rule("building.partition_ratio", to="sbem")
def partition_area_to_sbem(
    template: BuildingTemplate, *, pointer: str, subject: str | None = None
) -> tuple[float, list[Loss]]:
    """Return SBEM's `PartitionAreaPerFloorArea` of a template's zones: twice its `PartitionRatio`.

    The ratio is partition wall area per floor area; SBEM's internal partitions count both
    faces, as EnergyPlus internal mass does. A negative ratio is lost (no partitions).

    Args:
        template: The building template.
        pointer: Its JSON pointer.
        subject: The archetype's name; by default the template's.

    Returns:
        The area per floor area and the losses.
    """
    ratio = template.partition_ratio
    if ratio < 0:
        loss = _lost(
            _subject(template, subject),
            f"{pointer}/PartitionRatio",
            ratio,
            "building.partition_ratio",
            "SBEM's partition area cannot be negative; the zones have no internal partitions.",
        )
        return 0.0, [loss]
    return PARTITION_FACES * ratio, []


@rule("building.partition_ratio", to="umi")
def partition_ratio_to_umi(areas: Mapping[str, float], *, subject: str) -> tuple[float, list[Loss]]:
    """Return a template's `PartitionRatio` from its groups' partition areas: half the perimeter group's.

    Another group's different area is lost.

    Args:
        areas: Each group's `PartitionAreaPerFloorArea`, by group name, in group order.
        subject: The archetype's name.

    Returns:
        The ratio and the losses.
    """
    if not areas:
        return 0.0, []
    chosen = PERIMETER_GROUP if PERIMETER_GROUP in areas else next(iter(areas))
    area = areas[chosen]
    losses = [
        _lost(
            subject,
            f"{group}.Envelope.Assemblies.PartitionAreaPerFloorArea",
            other,
            "building.partition_ratio",
            f"A UMI template has one partition ratio: the {chosen} group's partitions are written.",
        )
        for group, other in areas.items()
        if group != chosen and other != area
    ]
    return area / PARTITION_FACES, losses


def _material_to_sbem(
    material: OpaqueMaterial | None, pointer: str, subject: str, findings: Findings
) -> ConstructionMaterialComponent | None:
    return None if material is None else material_to_sbem(material, subject, pointer, findings)


def _material_to_umi(
    material: ConstructionMaterialComponent | None, location: str, subject: str, findings: Findings
) -> OpaqueMaterial | None:
    return None if material is None else material_to_umi(material, subject, location, findings)


_SYSTEM_SLOTS: tuple[tuple[str, str], ...] = (
    ("beams", "Beams"),
    ("columns", "Columns"),
    ("floors", "Floors"),
    ("foundations", "Foundations"),
    ("lateral_system", "LateralSystem"),
)


@rule("structure.component", to="sbem")
def structure_to_sbem(
    structure: StructureInformation, *, pointer: str, subject: str
) -> tuple[StructureComponent, list[Loss]]:
    """Read a template's structure as the archetype's `StructureComponent` (UP-9), field by field.

    Materials go through the material rules, with their losses.

    Args:
        structure: The UMI structure.
        pointer: Its JSON pointer.
        subject: The archetype's name.

    Returns:
        The structure and the losses.

    Raises:
        ValueError: A material has a roughness that is not an EnergyPlus keyword.
    """
    findings = Findings()
    ratios: list[dict[str, object]] = []
    for index, ratio in enumerate(structure.mass_ratios):
        where = f"{pointer}/MassRatios/{index}"
        if ratio.material is None:
            findings.lose(
                LossKind.LOST,
                subject,
                where,
                ratio.model_dump(mode="json", by_alias=True),
                "structure.component",
                "An SBEM mass ratio needs a material.",
            )
            continue
        ratios.append({
            "Material": material_to_sbem(ratio.material, subject, f"{where}/Material", findings),
            "NormalRatio": ratio.normal_ratio,
            "HighLoadRatio": ratio.high_load_ratio,
        })
    advanced = structure.advanced_model
    systems = advanced.construction_systems
    assembly_life_cycle_losses(structure, subject, pointer, findings)
    component = StructureComponent.model_validate({
        "Name": structure.name or "",
        **metadata_to_sbem(structure),
        **assembly_life_cycle_to_sbem(structure),
        "MassRatios": ratios,
        "UseAdvancedModel": structure.use_advanced_model,
        "AdvancedModel": {
            "ColumnWallSpacing": {
                "PrimarySpan": advanced.column_wall_spacing.primary_span,
                "SecondarySpan": advanced.column_wall_spacing.secondary_span,
            },
            "ConstructionSystems": {
                key: {
                    "Material": _material_to_sbem(
                        getattr(systems, name).material,
                        f"{pointer}/AdvancedModel/ConstructionSystems/{key}/Material",
                        subject,
                        findings,
                    ),
                    "ConstructionSystemType": getattr(systems, name).construction_system_type.value,
                }
                for name, key in _SYSTEM_SLOTS
            },
            "FoundationSoilSettings": {
                "FoundationSoilPreset": advanced.foundation_soil_settings.foundation_soil_preset.value,
                "FoundationSoilValue": advanced.foundation_soil_settings.foundation_soil_value,
            },
            "LoadingSettings": {
                "LiveLoadingPreset": advanced.loading_settings.live_loading_preset.value,
                "LiveLoadingValue": advanced.loading_settings.live_loading_value,
            },
        },
    })
    return component, findings.losses


@rule("structure.component", to="umi")
def structure_to_umi(
    structure: StructureComponent, *, location: str, subject: str
) -> tuple[StructureInformation, list[Loss]]:
    """Write the archetype's `StructureComponent` (UP-9) as a template's structure.

    Args:
        structure: The SBEM structure.
        location: Its SBEM field path (`archetype.Structure`).
        subject: The archetype's name.

    Returns:
        The UMI structure and the losses (materials, SBEM's `Version`).
    """
    findings = Findings()
    metadata = metadata_to_umi(structure, subject=subject, location=location)
    advanced = structure.AdvancedModel
    systems = advanced.ConstructionSystems
    model = AdvancedStructuralModel.model_validate({
        "ColumnWallSpacing": advanced.ColumnWallSpacing.model_dump(),
        "ConstructionSystems": {
            key: {
                "Material": _material_to_umi(
                    getattr(systems, key).Material,
                    f"{location}.AdvancedModel.ConstructionSystems.{key}.Material",
                    subject,
                    findings,
                ),
                "ConstructionSystemType": getattr(systems, key).ConstructionSystemType,
            }
            for _, key in _SYSTEM_SLOTS
        },
        "FoundationSoilSettings": advanced.FoundationSoilSettings.model_dump(),
        "LoadingSettings": advanced.LoadingSettings.model_dump(),
    })
    ratios = [
        MassRatios.model_validate({
            "Material": material_to_umi(ratio.Material, subject, f"{location}.MassRatios.{index}.Material", findings),
            "NormalRatio": ratio.NormalRatio,
            "HighLoadRatio": ratio.HighLoadRatio,
        })
        for index, ratio in enumerate(structure.MassRatios)
    ]
    information = StructureInformation.model_validate({
        "Name": structure.Name,
        **metadata.fields,
        **assembly_life_cycle_to_umi(structure),
        "MassRatios": ratios,
        "UseAdvancedModel": structure.UseAdvancedModel,
        "AdvancedModel": model,
    })
    return information, [*metadata.losses, *findings.losses]


@rule("building.metadata", to="sbem")
def template_metadata_to_sbem(
    template: BuildingTemplate, *, pointer: str, subject: str | None = None
) -> tuple[dict[str, object], list[Loss]]:
    """Return the archetype's descriptive and life-cycle fields of a template (UP-9).

    `Lifespan`, `YearFrom`, `YearTo`, `Country`, `ClimateZone`, `Authors`, `AuthorEmails` and
    `Version` are copied, and the template's `Category`, `Comments` and `DataSource` become the
    archetype's (`names.metadata`). A negative lifespan, or a `YearTo` before `YearFrom`, which
    SBEM refuses, is lost.

    Args:
        template: The building template.
        pointer: Its JSON pointer.
        subject: The archetype's name; by default the template's.

    Returns:
        The archetype's fields by name, and the losses.
    """
    subject = _subject(template, subject)
    fields: dict[str, object] = {key: _json(getattr(template, name)) for name, key in _TEMPLATE_METADATA}
    fields.update(metadata_to_sbem(template))
    losses: list[Loss] = []
    if template.lifespan < 0:
        losses.append(
            _lost(
                subject,
                f"{pointer}/Lifespan",
                template.lifespan,
                "building.metadata",
                "SBEM's lifespan cannot be negative.",
            )
        )
        del fields["Lifespan"]
    year_from, year_to = template.year_from, template.year_to
    if year_from is not None and year_to is not None and year_from > year_to:
        losses.append(
            _lost(subject, f"{pointer}/YearTo", year_to, "building.metadata", "SBEM refuses a YearTo before YearFrom.")
        )
        del fields["YearTo"]
    return fields, losses


def template_metadata_notes(archetype: Archetype) -> list[Note]:
    """Note the archetype's unset template-level fields that writing fills with Basilisk's defaults."""
    findings = Findings()
    keys = [key for _, key in _TEMPLATE_METADATA if BuildingTemplate.model_fields[_FIELD_OF[key]].default is not None]
    findings.unset(archetype, keys, archetype.Name, "archetype", "building.metadata")
    return findings.notes


@rule("building.metadata", to="umi")
def template_metadata_to_umi(archetype: Archetype) -> dict[str, object]:
    """Return a template's descriptive and life-cycle fields from the archetype (UP-9).

    Unset fields take Basilisk's defaults; the archetype's `Category`, `Comment` and
    `DataSource` become the template's (`names.metadata`).

    Args:
        archetype: The archetype.

    Returns:
        The template's fields by Basilisk key.
    """
    fields: dict[str, object] = {
        key: value for _, key in _TEMPLATE_METADATA if (value := getattr(archetype, key)) is not None
    }
    fields.update({
        "Category": archetype.Category if archetype.Category is not None else UNCATEGORIZED,
        "Comments": archetype.Comment,
        "DataSource": archetype.DataSource,
    })
    return fields


def template_losses(template: BuildingTemplate, *, pointer: str, subject: str | None = None) -> list[Loss]:
    """Report the template-level fields of research R6's table that the archetype loses.

    Since UP-9 the archetype holds every one of them, so only values SBEM refuses are lost:
    a negative partition ratio or lifespan, a `YearTo` before `YearFrom`, and the structure's
    losses.

    Args:
        template: The building template.
        pointer: The template's JSON pointer, for example `"/BuildingTemplates/0"`.
        subject: The archetype's name; by default the template's.

    Returns:
        The losses.
    """
    subject = _subject(template, subject)
    losses = [
        *partition_area_to_sbem(template, pointer=pointer, subject=subject)[1],
        *template_metadata_to_sbem(template, pointer=pointer, subject=subject)[1],
    ]
    if template.structure is not None:
        losses.extend(structure_to_sbem(template.structure, pointer=f"{pointer}/Structure", subject=subject)[1])
    return losses


# --- Names (names.component) ----------------------------------------------------------------------

NAMED_FROM: Mapping[str, str] = {
    "ZoneDefinition": "",
    "ZoneLoads": "Operations.SpaceUse",
    "ZoneConditioning": "Operations.HVAC",
    "ZoneVentilation": "Envelope.Infiltration",
    "DomesticHotWaterSettings": "Operations.DHW",
    "ZoneConstructions": "Envelope.Assemblies",
}
"""The SBEM component, relative to the zone, whose name a UMI component takes on writing."""

DERIVED_NAMES: tuple[tuple[str, str, str | None], ...] = (
    ("Operations", "ZoneDefinition", None),
    ("Envelope", "ZoneDefinition", None),
    ("Operations.SpaceUse.Occupancy", "ZoneLoads", "occupancy"),
    ("Operations.SpaceUse.Lighting", "ZoneLoads", "lighting"),
    ("Operations.SpaceUse.Equipment", "ZoneLoads", "equipment"),
    ("Operations.SpaceUse.Thermostat", "ZoneConditioning", None),
    ("Operations.HVAC.ConditioningSystems", "ZoneConditioning", None),
    ("Operations.HVAC.ConditioningSystems.Heating", "ZoneConditioning", "heating"),
    ("Operations.HVAC.ConditioningSystems.Cooling", "ZoneConditioning", "cooling"),
    ("Operations.HVAC.Ventilation", "ZoneConditioning", None),
    ("Envelope.AtticInfiltration", "ZoneVentilation", None),
    ("Envelope.BasementInfiltration", "ZoneVentilation", None),
    ("Operations.SpaceUse.WaterUse", "DomesticHotWaterSettings", None),
)
"""The other SBEM components named on reading: (path, UMI class, suffix or `None`)."""


def derived_name(parent: str, part: str) -> str:
    """Return the name of a sub-component: `"{parent} {part}"`, e.g. `"Office loads occupancy"`."""
    return f"{parent} {part}"


def window_settings_name(window_name: str) -> str:
    """Return the name of the `WindowSettings` written for a window: `"{window} settings"`."""
    return f"{window_name} settings"


def _expected(names: Mapping[str, str], umi_class: str, suffix: str | None) -> str:
    parent = names[umi_class]
    return parent if suffix is None else derived_name(parent, suffix)


def _get(zone: ZoneComponent, path: str) -> Any:
    """Return the component at a dotted path from the zone, or `None` when a step is `None`."""
    node: Any = zone
    for step in path.split(".") if path else ():
        if node is None:
            return None
        node = getattr(node, step)
    return node


@rule("names.component", to="sbem")
def apply_names(zone: ZoneComponent, names: Mapping[str, str]) -> ZoneComponent:
    """Name a zone's components after the UMI components that hold their content.

    Args:
        zone: The SBEM zone definition; it is not changed.
        names: The UMI name by UMI class (keys of `NAMED_FROM`); a class left out keeps its
            SBEM names.

    Returns:
        A copy of the zone, with each component of `NAMED_FROM` and `DERIVED_NAMES` renamed.
        A system that is off (`None`) is skipped.
    """
    named = zone.model_copy(deep=True)
    targets = [(path, umi_class, None) for umi_class, path in NAMED_FROM.items()] + list(DERIVED_NAMES)
    for path, umi_class, suffix in targets:
        component = _get(named, path)
        if umi_class in names and component is not None:
            component.Name = _expected(names, umi_class, suffix)
    return named


class ZoneNames(NamedTuple):
    """The UMI names recovered from a zone, and the SBEM names they cannot carry."""

    names: dict[str, str]
    """The UMI name by UMI class."""
    losses: tuple[Loss, ...]
    """Sub-component names that differ from the names the rules derive."""


@rule("names.component", to="umi")
def umi_names(zone: ZoneComponent, *, subject: str, group: str) -> ZoneNames:
    """Recover the UMI component names of a zone (the inverse of `apply_names`).

    Args:
        zone: The SBEM zone definition.
        subject: The archetype's name, for the report.
        group: The group's name, which prefixes each loss's location.

    Returns:
        The UMI name by UMI class, taken from the components of `NAMED_FROM`, and a loss for
        each component of `DERIVED_NAMES` whose name differs from the derived one.
    """
    names = {umi_class: cast("str", _get(zone, path).Name) for umi_class, path in NAMED_FROM.items()}
    losses: list[Loss] = []
    for path, umi_class, suffix in DERIVED_NAMES:
        component = _get(zone, path)
        expected = _expected(names, umi_class, suffix)
        if component is not None and component.Name != expected:
            losses.append(
                Loss(
                    kind=LossKind.LOST,
                    subject=subject,
                    location=f"{group}.{path}.Name",
                    value=component.Name,
                    replacement=expected,
                    rule="names.component",
                    reason=f"UMI has no component of its own here; its name is derived from the {umi_class}.",
                )
            )
    return ZoneNames(names, tuple(losses))


class UniqueNames:
    """Keep names unique within one collection (research R11, R13).

    The same name with the same content is one component. A name already used for other
    content gets the suffix ` #2`, ` #3`, … in order of first appearance, skipping any name
    already taken. Other names with the same content stay apart.
    """

    def __init__(self) -> None:
        """Start with no names used."""
        self._assigned: dict[tuple[str, Hashable], str] = {}
        self._used: set[str] = set()
        self._renamed: list[tuple[str, str]] = []

    def assign(self, name: str, content: Hashable) -> str:
        """Return the unique name of a component.

        Args:
            name: The component's name.
            content: A key of its content without the name (for example its canonical JSON).

        Returns:
            `name`, or `name` with the first free suffix ` #n` (n ≥ 2) when `name` is already
            used for other content.
        """
        key = (name, content)
        if key in self._assigned:
            return self._assigned[key]
        unique = name
        number = 2
        while unique in self._used:
            unique = f"{name} #{number}"
            number += 1
        self._assigned[key] = unique
        self._used.add(unique)
        if unique != name:
            self._renamed.append((name, unique))
        return unique

    @property
    def renamed(self) -> tuple[tuple[str, str], ...]:
        """Each renaming as (original, new), in order."""
        return tuple(self._renamed)


def collision_loss(*, subject: str, location: str, original: str, renamed: str) -> Loss:
    """Report a component renamed to keep names unique (`names.collision`).

    Args:
        subject: The template or archetype; `""` for a library-level component.
        location: Where the component is (a JSON pointer, or an SBEM field path).
        original: Its name.
        renamed: Its new name.
    """
    return Loss(
        kind=LossKind.RENAMED,
        subject=subject,
        location=location,
        value=original,
        replacement=renamed,
        rule="names.collision",
        reason="Another component of the same kind has this name and different content.",
    )


# --- Metadata (names.metadata) ------------------------------------------------------------------


@rule("names.metadata", to="sbem")
def metadata_to_sbem(component: LibraryComponent) -> dict[str, str | None]:
    """Return the SBEM metadata of a UMI component: `Category`, `Comment` and `DataSource`.

    Basilisk's default category, `"Uncategorized"`, becomes an unset category.
    """
    category = None if component.category == UNCATEGORIZED else component.category
    return {"Category": category, "Comment": component.comments, "DataSource": component.data_source}


class MetadataFields(NamedTuple):
    """A UMI component's metadata, and the SBEM metadata it cannot carry."""

    fields: dict[str, str | None]
    """`Category`, `Comments` and `DataSource`, keyed by their Basilisk keys."""
    losses: tuple[Loss, ...]
    """SBEM's `Version`, which UMI components do not have, when set."""


@rule("names.metadata", to="umi")
def metadata_to_umi(component: MetadataMixin, *, subject: str, location: str) -> MetadataFields:
    """Return the UMI metadata of an SBEM component.

    Args:
        component: The SBEM component.
        subject: The archetype's name, for the report.
        location: The component's field path, for the report.

    Returns:
        The metadata by Basilisk key (an unset category becomes `"Uncategorized"`), and a loss
        for SBEM's `Version` when it is set.
    """
    fields: dict[str, str | None] = {
        "Category": component.Category if component.Category is not None else UNCATEGORIZED,
        "Comments": component.Comment,
        "DataSource": component.DataSource,
    }
    losses: tuple[Loss, ...] = ()
    if component.Version is not None:
        losses = (
            _lost(
                subject,
                f"{location}.Version",
                component.Version,
                "names.metadata",
                "UMI components have no version.",
            ),
        )
    return MetadataFields(fields, losses)


# --- Zone definitions (building.zone_definition) -------------------------------------------------


@rule("building.zone_definition", to="sbem")
def zone_component(  # noqa: PLR0913 - one argument per part of an SBEM zone
    name: str,
    *,
    space_use: ZoneSpaceUseComponent,
    hvac: ZoneHVACComponent,
    dhw: DHWComponent,
    assemblies: EnvelopeAssemblyComponent,
    infiltration: InfiltrationComponent,
    attic_infiltration: InfiltrationComponent,
    basement_infiltration: InfiltrationComponent,
    window: WindowConstruction | None,
    window_settings: WindowSettingsComponent | None = None,
    metadata: Mapping[str, str | None] | None = None,
) -> ZoneComponent:
    """Assemble the SBEM zone definition of a UMI zone definition from its translated parts.

    The zone, its operations and its envelope take the zone definition's name; the operations
    carry its metadata (`metadata_to_sbem`).

    Args:
        name: The UMI zone definition's name.
        space_use: From its `Loads` (and the thermostat and water use).
        hvac: From its `Conditioning` and `Ventilation`.
        dhw: From its `DomesticHotWater`.
        assemblies: From its `Constructions` and internal mass.
        infiltration: From its `Ventilation`.
        attic_infiltration: The attic's infiltration.
        basement_infiltration: The basement's infiltration.
        window: The template's window, or `None`.
        window_settings: The template's window settings (UP-9), or `None`.
        metadata: SBEM metadata for the operations (`Category`, `Comment`, `DataSource`).

    Returns:
        The zone definition.
    """
    operations = ZoneOperationsComponent(Name=name, SpaceUse=space_use, HVAC=hvac, DHW=dhw, **dict(metadata or {}))
    envelope = ZoneEnvelopeComponent(
        Name=name,
        Assemblies=assemblies,
        Infiltration=infiltration,
        AtticInfiltration=attic_infiltration,
        BasementInfiltration=basement_infiltration,
        Window=window,
        WindowSettings=window_settings,
    )
    return ZoneComponent(Name=name, Operations=operations, Envelope=envelope)
