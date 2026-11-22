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
- **Template-level fields** (`building.metadata`, `building.partition_ratio`,
  `structure.upstream`, `names.metadata`). SBEM has no place for them until UP-9 (research
  R6): each one that differs from Basilisk's default is reported as lost.
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
from epinterface.sbem.components.zones import ZoneComponent

from archetypal.umi._format import BuildingTemplate
from archetypal.umi.correspondence import declare_rule, rule
from archetypal.umi.report import Loss, LossKind, Note, NoteKind

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Mapping

    from epinterface.sbem.archetype import Orientation
    from epinterface.sbem.common import MetadataMixin
    from epinterface.sbem.components.envelope import (
        EnvelopeAssemblyComponent,
        GlazingConstructionSimpleComponent,
        InfiltrationComponent,
    )
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
    "partition_ratio_losses",
    "structure_losses",
    "template_losses",
    "template_metadata_losses",
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
_UP9 = "UP-9"

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
        The archetype and the template-level fields it lost (`template_losses`).

    Raises:
        ValueError: The template has no name, `Core` or `Perimeter`.
    """
    subject = name if name is not None else template.name
    if subject is None:
        msg = f"the building template at {pointer} has no name"
        raise ValueError(msg)
    archetype = Archetype(
        Name=subject,
        Groups=groups_from_template(template, translate_zone),
        Geometry=BuildingGeometry(WindowToWallRatio=wwr_to_sbem(template.default_window_to_wall_ratio)),
    )
    return archetype, template_losses(template, pointer=pointer, subject=subject)


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
    losses.extend(_building_level_losses(archetype))
    return TemplateZones(core, perimeter, tuple(sorted(losses, key=lambda loss: loss.location)))


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


# --- Template-level fields SBEM cannot hold yet (UP-9) -------------------------------------------

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
_COMPONENT_METADATA: tuple[tuple[str, str], ...] = (
    ("category", "Category"),
    ("comments", "Comments"),
    ("data_source", "DataSource"),
)


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


def _upstream_losses(
    template: BuildingTemplate, fields: tuple[tuple[str, str], ...], rule_id: str, *, pointer: str, subject: str
) -> list[Loss]:
    """Report each field that differs from Basilisk's default as lost until UP-9."""
    losses: list[Loss] = []
    for attribute, key in fields:
        value = getattr(template, attribute)
        default = BuildingTemplate.model_fields[attribute].get_default(call_default_factory=True)
        if value != default:
            losses.append(
                _lost(
                    subject,
                    f"{pointer}/{key}",
                    _json(value),
                    rule_id,
                    f"The archetype has no {key} yet; UP-9 adds archetype-level fields for UMI.",
                    _UP9,
                )
            )
    return losses


def _subject(template: BuildingTemplate, subject: str | None) -> str:
    return subject if subject is not None else (template.name or "")


@rule("building.partition_ratio", to="sbem")
def partition_ratio_losses(template: BuildingTemplate, *, pointer: str, subject: str | None = None) -> list[Loss]:
    """Report a template's `PartitionRatio` as lost unless it is Basilisk's default (UP-9)."""
    fields = (("partition_ratio", "PartitionRatio"),)
    return _upstream_losses(
        template, fields, "building.partition_ratio", pointer=pointer, subject=_subject(template, subject)
    )


@rule("structure.upstream", to="sbem")
def structure_losses(template: BuildingTemplate, *, pointer: str, subject: str | None = None) -> list[Loss]:
    """Report a template's `Structure` as lost, by name, when it has one (UP-9)."""
    if template.structure is None:
        return []
    return [
        _lost(
            _subject(template, subject),
            f"{pointer}/Structure",
            template.structure.name,
            "structure.upstream",
            "The archetype has no structure yet; UP-9 adds a structure component at building level.",
            _UP9,
        )
    ]


@rule("building.metadata", to="sbem")
def template_metadata_losses(template: BuildingTemplate, *, pointer: str, subject: str | None = None) -> list[Loss]:
    """Report the template's descriptive and life-cycle fields as lost unless at their defaults (UP-9).

    These are `Lifespan`, `YearFrom`, `YearTo`, `Country`, `ClimateZone`, `Authors`,
    `AuthorEmails` and `Version`.
    """
    return _upstream_losses(
        template, _TEMPLATE_METADATA, "building.metadata", pointer=pointer, subject=_subject(template, subject)
    )


def template_losses(template: BuildingTemplate, *, pointer: str, subject: str | None = None) -> list[Loss]:
    """Report every template-level field of research R6's table that the archetype loses.

    A field at Basilisk's default loses nothing, since writing the archetype back gives the
    same default. The others are lost with `upstream: "UP-9"`: `PartitionRatio`, `Structure`,
    the descriptive and life-cycle fields, and the template's `Category`, `Comments` and
    `DataSource`.

    Args:
        template: The building template.
        pointer: The template's JSON pointer, for example `"/BuildingTemplates/0"`.
        subject: The archetype's name; by default the template's.

    Returns:
        The losses, in R6's order.
    """
    subject = _subject(template, subject)
    return [
        *partition_ratio_losses(template, pointer=pointer, subject=subject),
        *structure_losses(template, pointer=pointer, subject=subject),
        *template_metadata_losses(template, pointer=pointer, subject=subject),
        *_upstream_losses(template, _COMPONENT_METADATA, "names.metadata", pointer=pointer, subject=subject),
    ]


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
    window: GlazingConstructionSimpleComponent | None,
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
    )
    return ZoneComponent(Name=name, Operations=operations, Envelope=envelope)
