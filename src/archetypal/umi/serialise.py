"""The text of a UMI library as archetypal writes it (spec 003, research R13, contracts/umi-file.md).

`serialise` turns building templates into Basilisk Core JSON:

1. **Collections.** Every component a template reaches is put in its collection
   (`library_of`); the 17 collections are written in Basilisk's order (`COLLECTIONS`), all
   present. Within each collection components are sorted by name; templates keep their order.
2. **References.** `archetypal.umi._refs.dump_library` numbers components `"1"`, `"2"`, … in
   document order, defines each with `$id` first at its first occurrence and refers back to it
   with `{"$ref": id}` afterwards. Templates have no `$id`, so window settings are defined
   inline in the first template that uses them and the `WindowSettings` collection holds only
   references.
3. **Values.** Enums are integers, integer fields JSON integers, floats Python's shortest
   round-trip `repr`, never rounded. Every field of the Basilisk class is written.
4. **Bytes.** UTF-8 without BOM, two-space indentation, Unix line ends, a final newline. Equal inputs give
   equal text (FR-012).

Names must already be unique per collection (glazing and gas materials together): the writer
renames clashes before serialising (`archetypal.umi.write`), and `library_of` refuses any that
remain.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Final, cast

from archetypal.umi._format import (
    BuildingTemplate,
    DaySchedule,
    DomesticHotWaterSettings,
    FormatModel,
    GasMaterial,
    GlazingMaterial,
    LibraryComponent,
    OpaqueConstruction,
    OpaqueMaterial,
    StructureInformation,
    UmiLibrary,
    WeekSchedule,
    WindowConstruction,
    WindowSettings,
    YearSchedule,
    ZoneConditioning,
    ZoneConstructions,
    ZoneDefinition,
    ZoneLoads,
    ZoneVentilation,
)
from archetypal.umi._refs import dump_library

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = ["COLLECTIONS", "NAME_GROUPS", "library_of", "serialise"]

COLLECTIONS: Final[tuple[str, ...]] = tuple(alias for _, alias in UmiLibrary.basilisk_keys())
"""The 17 collections of a library, in the order Basilisk writes them."""

_FIELD_OF: Final[dict[type[LibraryComponent], str]] = {
    GasMaterial: "gas_materials",
    GlazingMaterial: "glazing_materials",
    OpaqueMaterial: "opaque_materials",
    OpaqueConstruction: "opaque_constructions",
    WindowConstruction: "window_constructions",
    StructureInformation: "structure_definitions",
    DaySchedule: "day_schedules",
    WeekSchedule: "week_schedules",
    YearSchedule: "year_schedules",
    DomesticHotWaterSettings: "domestic_hot_water_settings",
    ZoneVentilation: "ventilation_settings",
    ZoneConditioning: "zone_conditionings",
    ZoneConstructions: "zone_construction_sets",
    ZoneLoads: "zone_loads",
    ZoneDefinition: "zones",
    WindowSettings: "window_settings",
}

NAME_GROUPS: Final[dict[type[LibraryComponent], str]] = {
    **_FIELD_OF,
    GasMaterial: "window_materials",
    GlazingMaterial: "window_materials",
    BuildingTemplate: "building_templates",
}
"""The namespace of names of each component class: glazing and gas materials share one."""


def _children(model: FormatModel) -> Iterable[FormatModel]:
    """The format models a model holds directly, in field order."""
    for name in type(model).model_fields:
        value: object = getattr(model, name)
        if isinstance(value, FormatModel):
            yield value
        elif isinstance(value, tuple):
            yield from (item for item in cast("tuple[object, ...]", value) if isinstance(item, FormatModel))


def library_of(templates: Sequence[BuildingTemplate]) -> UmiLibrary:
    """Collect the components the templates reach into a library, sorted by name.

    Args:
        templates: The building templates, in the order they are written.

    Returns:
        The library: each reachable component once in its collection, sorted by name; the
        templates in the order given.

    Raises:
        ValueError: A component has no name, or two different components of one name group
            (or two templates) share a name.
    """
    found: dict[str, dict[FormatModel, None]] = {field: {} for field in _FIELD_OF.values()}
    names: dict[tuple[str, str], FormatModel] = {}

    def check_name(component: LibraryComponent) -> None:
        group = NAME_GROUPS[type(component)]
        if component.name is None:
            msg = f"a {type(component).__name__} has no name"
            raise ValueError(msg)
        other = names.setdefault((group, component.name), component)
        if other != component:
            msg = f"two different {type(component).__name__} components are named {component.name!r}"
            raise ValueError(msg)

    seen: set[int] = set()

    def visit(model: FormatModel) -> None:
        if id(model) in seen:
            return
        seen.add(id(model))
        if type(model) in _FIELD_OF:
            component = cast("LibraryComponent", model)
            check_name(component)
            found[_FIELD_OF[type(component)]][model] = None
        for child in _children(model):
            visit(child)

    for template in templates:
        check_name(template)
        visit(template)
    collections = {
        field: tuple(sorted(items, key=lambda item: cast("LibraryComponent", item).name or ""))
        for field, items in found.items()
    }
    return UmiLibrary.model_validate({**collections, "building_templates": tuple(templates)})


def _check_finite(value: object, where: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        msg = f"{where}: every number of a UMI library must be finite, not {value!r}"
        raise ValueError(msg)
    if isinstance(value, dict):
        for key, item in cast("dict[str, object]", value).items():
            _check_finite(item, f"{where}/{key}")
    elif isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            _check_finite(item, f"{where}/{index}")


def serialise(templates: Sequence[BuildingTemplate]) -> str:
    """Return the text of the library holding `templates` (contracts/umi-file.md).

    Args:
        templates: The building templates, in the order they are written; component names
            already unique per name group.

    Returns:
        The library as Basilisk Core JSON: UTF-8 text with two-space indentation, Unix line
        ends and a final newline.

    Raises:
        ValueError: A name clashes (`library_of`) or a number is not finite.
    """
    document = dump_library(library_of(templates))
    _check_finite(document, "")
    return json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
