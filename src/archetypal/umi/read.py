"""Reading a UMI template library into SBEM archetypes (spec 003, US2, research R4, R11, R14).

`read_umi` runs the reading pipeline of data-model.md:

1. **Dialect** (`archetypal.umi.dialects`): the file is recognised from its shape and brought
   to Core JSON; refused files raise `UmiFormatError`.
2. **Names** (research R11): within one collection (glazing and gas materials together), a
   component whose name another component with different content already has is renamed with
   ` #2`, ` #3`, … in file order; so is a building template whose name an earlier template has.
   Each renaming is reported (`names.collision`).
3. **References** (`archetypal.umi._refs.resolve`): broken references raise `UmiFormatError`.
4. **Validation** (`archetypal.umi.validate`): completeness and range problems raise one
   `UmiValidationError` listing them all, unless `skip_invalid_templates` skips the templates
   they affect (`validation.skipped`).
5. **Translation**: each template becomes one archetype with `core` and `perimeter` groups and
   unset shares, through the registered UMI → SBEM rules. The rules without a function of
   their own (`material.environmental`, `construction.environmental`,
   `construction.adiabatic`, `window.settings`, `schedule.metadata`) are reported here from
   `CORRESPONDENCE`: each upstream field that differs from Basilisk's default is lost.
6. **Report**: components no template uses (`library.unused`), the fields that took
   Basilisk's default and the unknown keys (notes), the Archsim keys without a Core
   counterpart (losses), and the source (file name, SHA-256, dialect, versions).

`read_umi` never writes a file; `UmiImport.write` does.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeVar, cast

from epinterface.sbem.components.space_use import ZoneSpaceUseComponent
from epinterface.sbem.components.systems import ZoneHVACComponent

from archetypal.errors import InputError, Problem, UmiValidationError
from archetypal.io import ARCHETYPE_SUFFIX, dumps
from archetypal.umi import dialects
from archetypal.umi._format import (
    ConstructionBase,
    LibraryComponent,
    MaterialBase,
    OpaqueConstruction,
    UmiLibrary,
    YearSchedule,
)
from archetypal.umi._refs import resolve
from archetypal.umi.correspondence import MappingStatus, mappings_for
from archetypal.umi.report import Findings, Loss, LossKind, Note, NoteKind, SourceInfo, TranslationReport
from archetypal.umi.rules._common import RuleContext, json_value
from archetypal.umi.rules.building import (
    UniqueNames,
    apply_names,
    archetype_from_template,
    collision_loss,
    metadata_to_sbem,
    zone_component,
)
from archetypal.umi.rules.conditioning import conditioning_to_sbem
from archetypal.umi.rules.hotwater import dhw_to_sbem
from archetypal.umi.rules.loads import daylighting_to_sbem, internal_mass_to_sbem, loads_to_sbem
from archetypal.umi.rules.materials import assemblies_to_sbem, construction_to_sbem
from archetypal.umi.rules.schedules import year_to_sbem
from archetypal.umi.rules.ventilation import zone_ventilation_to_sbem
from archetypal.umi.rules.windows import simple_from_layers
from archetypal.umi.validate import LibraryIndex, template_problems

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Hashable, Iterable

    from epinterface.sbem.archetype import Archetype
    from epinterface.sbem.components.envelope import GlazingConstructionSimpleComponent
    from epinterface.sbem.components.schedules import YearComponent, YearScheduleCategory
    from epinterface.sbem.components.zones import ZoneComponent
    from pydantic import JsonValue

    from archetypal.umi._format import FormatModel, WindowSettings, ZoneDefinition
    from archetypal.umi.rules._common import ScheduleToSbem

__all__ = ["LOSS_SUFFIX", "UmiImport", "read_umi"]

LOSS_SUFFIX: Final = ".loss.json"
"""The suffix of the loss report written beside the archetypes: `<library stem>.loss.json`."""

_T = TypeVar("_T")
_Finding = Loss | Note

_DIRECTION: Final = "umi_to_sbem"
_TRANSLATION: Final = "translation"
_BASILISK_DEFAULT: Final = "format.basilisk_default"
_UNKNOWN_KEY: Final = "format.unknown_key"

# Collections whose components share one namespace of names (research R11).
_NAME_GROUPS: Final = {"GasMaterials": "WindowMaterials", "GlazingMaterials": "WindowMaterials"}
# The rule an Archsim key without a Core counterpart is reported under, by collection.
_ARCHSIM_RULES: Final = {
    "GasMaterials": "material.properties",
    "GlazingMaterials": "material.properties",
    "OpaqueMaterials": "material.properties",
    "OpaqueConstructions": "construction.layers",
    "WindowConstructions": "construction.layers",
}


@dataclass(frozen=True)
class UmiImport:
    """The archetypes read from a UMI library, and the report of the translation.

    Attributes:
        archetypes: One archetype per building template, in template order.
        report: What the translation lost and assumed.
    """

    archetypes: tuple[Archetype, ...]
    report: TranslationReport

    def write(self, directory: str | os.PathLike[str], *, overwrite: bool = False) -> tuple[Path, ...]:
        """Write `<archetype>.sbem.json` per archetype and `<library stem>.loss.json`.

        No file is written when one of them exists and `overwrite` is false.

        Args:
            directory: The directory, created if needed.
            overwrite: Replace existing files.

        Returns:
            The paths written: the archetypes in order, then the loss report.

        Raises:
            InputError: A file exists and `overwrite` is false, or two archetypes would
                share a file name.
        """
        folder = Path(directory)
        stem = Path(self.report.source.path).stem if self.report.source.path else "library"
        files = [(folder / f"{_file_stem(a.Name)}{ARCHETYPE_SUFFIX}", dumps(a)) for a in self.archetypes]
        files.append((folder / f"{stem}{LOSS_SUFFIX}", self.report.to_json()))
        seen: set[Path] = set()
        for path, _ in files:
            if path in seen:
                raise InputError(path, "two archetypes would be written to this file; rename one of them")
            seen.add(path)
            if not overwrite and path.exists():
                raise InputError(path, "already exists; pass overwrite=True to replace it")
        folder.mkdir(parents=True, exist_ok=True)
        for path, text in files:
            path.write_bytes(text.encode("utf-8"))
        return tuple(path for path, _ in files)


def _file_stem(name: str) -> str:
    """Return a file name stem for an archetype name: path separators become `_`."""
    stem = name.replace("/", "_").replace("\\", "_").strip()
    return stem if stem not in {"", ".", ".."} else "archetype"


# --- Names (research R11) ----------------------------------------------------------------------


def _definitions(document: dict[str, object]) -> list[tuple[str, str, dict[str, object]]]:
    """Each component defined in the file, as (name group, JSON pointer, object), in file order."""
    found: list[tuple[str, str, dict[str, object]]] = []
    for key, value in document.items():
        if key not in dialects.COLLECTIONS or not isinstance(value, list):
            continue
        for index, item in enumerate(cast("list[object]", value)):
            if not isinstance(item, dict) or "$ref" in item:
                continue
            obj = cast("dict[str, object]", item)
            found.append((_NAME_GROUPS.get(key, key), f"/{key}/{index}", obj))
            windows = obj.get("Windows")
            if key == "BuildingTemplates" and isinstance(windows, dict) and "$ref" not in windows:
                found.append(("WindowSettings", f"/{key}/{index}/Windows", cast("dict[str, object]", windows)))
    return found


def _content(obj: dict[str, object]) -> str:
    return json.dumps({key: value for key, value in obj.items() if key not in {"$id", "Name"}}, sort_keys=True)


def _rename_collisions(document: dict[str, object]) -> tuple[dict[str, object], list[Loss]]:
    """Rename components that share a name with different content, and repeated template names.

    Args:
        document: The library in Core JSON; it is not changed.

    Returns:
        A copy with the new names, and one `names.collision` loss per renaming.
    """
    renamed = copy.deepcopy(document)
    namers: dict[str, UniqueNames] = {}
    losses: list[Loss] = []
    for group, pointer, obj in _definitions(renamed):
        name = obj.get("Name")
        if not isinstance(name, str):
            continue
        # Every template gives an archetype, so a repeated template name is always renamed.
        content: Hashable = pointer if group == "BuildingTemplates" else _content(obj)
        unique = namers.setdefault(group, UniqueNames()).assign(name, content)
        if unique != name:
            obj["Name"] = unique
            subject = unique if group == "BuildingTemplates" else ""
            losses.append(collision_loss(subject=subject, location=pointer, original=name, renamed=unique))
    return renamed, losses


# --- Upstream fields reported from the table ----------------------------------------------------


def _report_table_upstream(component: FormatModel, rule_id: str, context: RuleContext) -> None:
    """Report each upstream field of `rule_id` that differs from Basilisk's default, as lost.

    Unlike `report_upstream`, rows declared on a base class (`MaterialBase`,
    `ConstructionBase`) apply to every class derived from it.
    """
    model = type(component)
    classes = {klass.__name__ for klass in model.__mro__}
    aliases = {info.alias or name: name for name, info in model.model_fields.items()}
    for row in mappings_for(rule_id):
        if row.status is not MappingStatus.UPSTREAM or row.umi_class not in classes or row.umi_key not in aliases:
            continue
        name = aliases[row.umi_key]
        value: object = getattr(component, name)
        if value == model.model_fields[name].get_default(call_default_factory=True):
            continue
        context.lose(
            row.umi_key,
            json_value(value),
            rule=rule_id,
            reason=f"SBEM has no field for {row.umi_key} yet",
            upstream=row.upstream,
        )


# --- Translation ------------------------------------------------------------------------------------


class _Reader:
    """Translates the templates of one library, translating each shared component once."""

    def __init__(self, index: LibraryIndex) -> None:
        self.index = index
        self._cache: dict[tuple[object, ...], tuple[object, tuple[_Finding, ...]]] = {}

    def _at(self, item: FormatModel, context: RuleContext) -> RuleContext:
        """A context at a component's pointer, sharing `context`'s findings."""
        return RuleContext(context.subject, self.index.pointer(item), _DIRECTION, context.findings)

    def _cached(self, key: tuple[object, ...], context: RuleContext, build: Callable[[RuleContext], _T]) -> _T:
        """Build once per key; later uses copy the findings to their own subject."""
        hit = self._cache.get(key)
        if hit is None:
            local = RuleContext(context.subject, context.at, _DIRECTION)
            hit = (build(local), tuple(local.findings))
            self._cache[key] = hit
        result, found = hit
        context.findings.extend(
            finding if finding.subject == context.subject else finding.model_copy(update={"subject": context.subject})
            for finding in found
        )
        return cast("_T", result)

    @staticmethod
    def _collect(context: RuleContext, findings: Findings) -> None:
        context.findings.extend(findings.losses)
        context.findings.extend(findings.notes)

    # --- Schedules --------------------------------------------------------------------------------

    def schedules(self, context: RuleContext) -> ScheduleToSbem:
        """The schedule converter of research R7, reporting into `context`."""

        def convert(year: YearSchedule, role: YearScheduleCategory, field: str) -> YearComponent:
            del field  # findings are located at the schedule itself
            return self._cached(("schedule", id(year), role), context, lambda local: self._year(year, role, local))

        return convert

    def _year(self, year: YearSchedule, role: YearScheduleCategory, context: RuleContext) -> YearComponent:
        pointer = self.index.pointer(year)
        findings = Findings()
        component = year_to_sbem(year, role, context.subject, pointer, findings)
        self._collect(context, findings)
        here = self._at(year, context)
        _report_table_upstream(year, "schedule.metadata", here)
        for key, value in (("Comments", year.comments), ("DataSource", year.data_source)):
            if value is not None:
                here.lose(
                    key,
                    value,
                    rule="schedule.metadata",
                    reason="SBEM schedules have no metadata yet",
                    upstream="UP-9",
                )
        return component

    # --- Constructions --------------------------------------------------------------------------

    def _construction_upstream(self, construction: OpaqueConstruction, context: RuleContext) -> None:
        _report_table_upstream(construction, "construction.environmental", self._at(construction, context))
        for layer in construction.layers:
            if layer.material is not None:
                material: MaterialBase = layer.material
                _report_table_upstream(material, "material.environmental", self._at(material, context))

    def window(self, settings: WindowSettings, context: RuleContext) -> GlazingConstructionSimpleComponent:
        """The template's simple-glazing window, from its window settings' construction."""
        construction = settings.construction
        if construction is None:  # pragma: no cover - validation refuses it
            msg = f"{self.index.pointer(settings)}: the window settings have no construction"
            raise ValueError(msg)

        def build(local: RuleContext) -> GlazingConstructionSimpleComponent:
            window, losses = simple_from_layers(
                construction, subject=local.subject, location=self.index.pointer(construction)
            )
            local.findings.extend(losses)
            _report_table_upstream(construction, "construction.environmental", self._at(construction, local))
            return window

        return self._cached(("window", id(construction)), context, build)

    # --- Zones ------------------------------------------------------------------------------------------

    def zone(
        self, zone: ZoneDefinition, window: GlazingConstructionSimpleComponent, window_key: int, context: RuleContext
    ) -> ZoneComponent:
        """The SBEM zone definition of a UMI zone definition, with the template's window."""
        return self._cached(("zone", id(zone), window_key), context, lambda local: self._zone(zone, window, local))

    def _zone(self, zone: ZoneDefinition, window: GlazingConstructionSimpleComponent, context: RuleContext) -> ZoneComponent:
        loads, conditioning, ventilation = zone.loads, zone.conditioning, zone.ventilation
        dhw, constructions, mass = zone.domestic_hot_water, zone.constructions, zone.internal_mass_construction
        if None in (loads, conditioning, ventilation, dhw, constructions, mass):  # pragma: no cover - validated
            msg = f"{self.index.pointer(zone)}: the zone definition misses a reference"
            raise ValueError(msg)
        assert loads is not None and conditioning is not None and ventilation is not None  # noqa: S101 - narrowed
        assert dhw is not None and constructions is not None and mass is not None  # noqa: S101 - narrowed
        subject = context.subject
        loads_at, conditioning_at = self._at(loads, context), self._at(conditioning, context)
        ventilation_at, dhw_at = self._at(ventilation, context), self._at(dhw, context)
        zone_at = self._at(zone, context)

        gains = loads_to_sbem(loads, schedule=self.schedules(loads_at), context=loads_at)
        systems = conditioning_to_sbem(
            conditioning,
            ventilation,
            schedule=self.schedules(conditioning_at),
            context=conditioning_at,
            ventilation_context=ventilation_at,
        )
        infiltration = zone_ventilation_to_sbem(ventilation, context=ventilation_at)
        hot_water = dhw_to_sbem(dhw, loads, schedule=self.schedules(dhw_at), context=dhw_at)

        space_use = ZoneSpaceUseComponent.model_validate({
            **metadata_to_sbem(loads),
            "Name": loads.name or "",
            "Occupancy": gains.occupancy,
            "Lighting": gains.lighting,
            "Equipment": gains.equipment,
            "Thermostat": systems.thermostat,
            "WaterUse": hot_water.water_use,
        })
        hvac = ZoneHVACComponent.model_validate({
            **metadata_to_sbem(conditioning),
            "Name": conditioning.name or "",
            "ConditioningSystems": systems.systems,
            "Ventilation": systems.ventilation,
        })

        findings = Findings()
        mass_assembly = construction_to_sbem(mass, "InternalMass", subject, self.index.pointer(mass), findings)
        assembly, ratio = internal_mass_to_sbem(
            mass_assembly, zone.internal_mass_exposed_per_floor_area, context=zone_at
        )
        assemblies = assemblies_to_sbem(
            constructions,
            subject,
            self.index.pointer(constructions),
            findings,
            internal_mass=assembly,
            internal_mass_exposed=ratio,
        )
        self._collect(context, findings)
        _report_table_upstream(constructions, "construction.adiabatic", self._at(constructions, context))
        for slot in (constructions.facade, constructions.ground, constructions.partition, constructions.roof):
            if slot is not None:
                self._construction_upstream(slot, context)
        if constructions.slab is not None:
            self._construction_upstream(constructions.slab, context)
        self._construction_upstream(mass, context)
        daylighting_to_sbem(zone, context=zone_at)

        component = zone_component(
            zone.name or "",
            space_use=space_use,
            hvac=hvac,
            dhw=hot_water.dhw,
            assemblies=assemblies,
            infiltration=infiltration.infiltration,
            attic_infiltration=infiltration.attic,
            basement_infiltration=infiltration.basement,
            window=window,
            metadata=metadata_to_sbem(zone),
        )
        parts: dict[str, LibraryComponent] = {
            "ZoneDefinition": zone,
            "ZoneLoads": loads,
            "ZoneConditioning": conditioning,
            "ZoneVentilation": ventilation,
            "DomesticHotWaterSettings": dhw,
            "ZoneConstructions": constructions,
        }
        names = {umi_class: part.name for umi_class, part in parts.items() if part.name is not None}
        return apply_names(component, names)

    # --- Templates --------------------------------------------------------------------------------------

    def template(self, number: int) -> tuple[Archetype, list[_Finding]]:
        """Translate template number `number` into an archetype, with its findings."""
        template = self.index.library.building_templates[number]
        pointer = self.index.pointer(template)
        name = template.name
        if name is None:
            msg = f"{pointer}: the building template has no name"
            raise ValueError(msg)
        context = RuleContext(name, pointer, _DIRECTION)
        settings = template.windows
        if settings is None:  # pragma: no cover - validation refuses it
            msg = f"{pointer}: the building template has no window settings"
            raise ValueError(msg)
        window = self.window(settings, context)
        window_key = id(settings.construction)
        _report_table_upstream(settings, "window.settings", self._at(settings, context))
        archetype, losses = archetype_from_template(
            template,
            lambda zone: self.zone(zone, window, window_key, context),
            pointer=pointer,
            name=name,
        )
        context.findings.extend(losses)
        return archetype, list(context.findings)


# --- The report -------------------------------------------------------------------------------------


def _unused(index: LibraryIndex) -> list[Loss]:
    """A loss for each component of the collections that no template uses."""
    used = {id(item) for number in range(len(index.library.building_templates)) for item, _ in index.reachable(number)}
    reason = (
        "No building template uses this component, so it was not translated."
        if index.library.building_templates
        else "The library has no building template, so no component is used; it was not translated."
    )
    return [
        Loss(
            kind=LossKind.UNUSED,
            subject="",
            location=pointer,
            value=item.name if isinstance(item, LibraryComponent) else None,
            rule="library.unused",
            reason=reason,
        )
        for item, pointer in index.components()
        if id(item) not in used
    ]


def _library_findings(raw: dialects.RawLibrary, defaulted: Iterable[str], unknown: Iterable[tuple[str, object]]) -> list[_Finding]:
    """The library-level notes (defaults, unknown keys) and the Archsim keys lost."""
    found: list[_Finding] = [
        Note(
            kind=NoteKind.DEFAULTED,
            subject="",
            location=pointer,
            value=None,
            rule=_BASILISK_DEFAULT,
            reason="The key is absent from the file; Basilisk's default was used.",
        )
        for pointer in defaulted
    ]
    found.extend(
        Note(
            kind=NoteKind.UNKNOWN_KEY,
            subject="",
            location=pointer,
            value=cast("JsonValue", value),
            rule=_UNKNOWN_KEY,
            reason="Basilisk's Core format has no such key; it was ignored.",
        )
        for pointer, value in unknown
    )
    found.extend(
        Loss(
            kind=LossKind.LOST,
            subject="",
            location=pointer,
            value=cast("JsonValue", value),
            rule=_ARCHSIM_RULES.get(pointer.split("/")[1], "building.library"),
            reason="This Archsim-era key has no counterpart in Basilisk's Core format.",
        )
        for pointer, value in raw.lost
    )
    return found


def _unique(findings: Iterable[_Finding]) -> list[_Finding]:
    seen: set[tuple[str, str]] = set()
    kept: list[_Finding] = []
    for finding in findings:
        key = (type(finding).__name__, finding.model_dump_json())
        if key not in seen:
            seen.add(key)
            kept.append(finding)
    return kept


def _skipped(name: str, pointer: str, problems: list[Problem]) -> Loss:
    return Loss(
        kind=LossKind.SKIPPED_TEMPLATE,
        subject=name,
        location=pointer,
        value=[str(problem) for problem in problems],
        rule="validation.skipped",
        reason="The template is invalid and skip_invalid_templates is set, so it was not read.",
    )


# --- Public interface -------------------------------------------------------------------------------


def read_umi(
    path: str | os.PathLike[str],
    *,
    strict: bool = False,
    skip_invalid_templates: bool = False,
) -> UmiImport:
    """Read a UMI template library into SBEM archetypes, one per building template.

    Each archetype has the groups `core` and `perimeter`, built from the template's `Core`
    and `Perimeter` zone definitions, with unset floor-area shares: the building's geometry
    sets them when the archetype is applied, as in UMI (research R4). The report lists every
    value SBEM cannot hold. Nothing is written; call `UmiImport.write` for that.

    Example:
        ```python
        from archetypal import read_umi

        result = read_umi("BostonTemplateLibrary.json")
        for archetype in result.archetypes:
            print(archetype.Name)
        print(result.report.summary)
        result.write("archetypes/")
        ```

    Args:
        path: The library file (UMI's JSON).
        strict: Raise `LossyTranslationError` when anything is lost, after the whole library
            has been translated.
        skip_invalid_templates: Skip the templates with completeness or range problems,
            reporting each as `skipped_template`, instead of raising.

    Returns:
        The archetypes, in template order, and the report.

    Raises:
        UmiFormatError: The file is refused (dialect, malformed JSON) or a reference is broken.
        UmiValidationError: A template has completeness or range problems (each listed with its
            JSON pointer and template), unless `skip_invalid_templates` is set.
        LossyTranslationError: `strict` is set and the report lists losses.
    """
    raw = dialects.load(path)
    document, renamed = _rename_collisions(raw.document)
    resolution = resolve(document, path)
    library: UmiLibrary = resolution.library
    index = LibraryIndex(library, document)
    problems = [template_problems(index, number) for number in range(len(library.building_templates))]
    if any(problems) and not skip_invalid_templates:
        raise UmiValidationError(path, [problem for found in problems for problem in found])

    reader = _Reader(index)
    archetypes: list[Archetype] = []
    findings: list[_Finding] = list(renamed)
    failed: list[Problem] = []
    for number, template in enumerate(library.building_templates):
        pointer = index.pointer(template)
        name = template.name or pointer
        if problems[number]:
            findings.append(_skipped(name, pointer, problems[number]))
            continue
        try:
            archetype, found = reader.template(number)
        except ValueError as error:
            problem = Problem(pointer, name, _TRANSLATION, str(error))
            if not skip_invalid_templates:
                failed.append(problem)
            else:
                findings.append(_skipped(name, pointer, [problem]))
            continue
        archetypes.append(archetype)
        findings.extend(found)
    if failed:
        raise UmiValidationError(path, failed)

    findings.extend(_unused(index))
    findings.extend(_library_findings(raw, resolution.defaulted, resolution.unknown_keys))
    kept = _unique(findings)
    report = TranslationReport(
        direction=_DIRECTION,
        source=SourceInfo.current(path, sha256=raw.sha256, dialect=raw.dialect),
        subjects=[archetype.Name for archetype in archetypes],
        losses=[finding for finding in kept if isinstance(finding, Loss)],
        notes=[finding for finding in kept if isinstance(finding, Note)],
    )
    if strict:
        report.raise_for_losses(path)
    return UmiImport(archetypes=tuple(archetypes), report=report)
