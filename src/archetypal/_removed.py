"""The v2 names, modules, commands and options that archetypal 3 does not provide.

`REMOVED` is the only source (spec 001, data-model.md, RemovedCapability): import errors,
rejected options, the migration guide's table and the removed-names reference are generated
from it.
"""

from __future__ import annotations

import inspect
import re
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from archetypal.errors import RemovedInArchetypal3Error

if TYPE_CHECKING:
    from typing import NoReturn

__all__ = [
    "MIGRATION_GUIDE_URL",
    "REMOVED",
    "FrequentTask",
    "Kind",
    "RemovedCapability",
    "Replacement",
    "anchor",
    "raise_removed",
    "row_anchor",
]

MIGRATION_GUIDE_URL = "https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/"
"""The migration guide; each row has a section whose heading is its `v2_path`."""

Kind = Literal["name", "module", "command", "option"]
"""What a v2 path is: a Python name, a module, a command or a command option."""

FrequentTask = Literal[
    "reduce-to-umi", "edit-umi-library", "open-and-simulate", "read-results", "upgrade-version", "evaluate-schedule"
]
"""The frequent v2 tasks that have a before/after example in the migration guide (FR-018)."""


@dataclass(frozen=True)
class Replacement:
    """What to use instead of a removed capability.

    Attributes:
        package: The package that provides it.
        target: The name, module or command to use.
        docs_url: The page that documents it.
    """

    package: Literal["archetypal", "idfkit", "epinterface"]
    target: str
    docs_url: str


@dataclass(frozen=True)
class RemovedCapability:
    """One v2 name, module, command or option that archetypal 3 does not provide.

    Attributes:
        kind: What the v2 path is.
        v2_path: The path as a v2 user writes it, such as `archetypal.IDF` or
            `archetypal reduce --all_zones`. Unique in `REMOVED`.
        replacement: What to use instead; `None` only when `reason` says why there is none.
        reason: Why it was removed, in one sentence. Always set.
        frequent_task: The before/after example of the migration guide it belongs to, if any.
        aliases: For an `option` row, v2's other spellings of the flag, such as `("-z",)` for
            `archetypal reduce --all_zones`; the command line rejects each of them too.
    """

    kind: Kind
    v2_path: str
    replacement: Replacement | None
    reason: str
    frequent_task: FrequentTask | None = None
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a row without a reason."""
        if not self.reason.strip():
            msg = f"{self.v2_path}: a removed capability needs a reason"
            raise ValueError(msg)


_SITE = "https://samuelduchesne.github.io/archetypal/"
_API = f"{_SITE}reference/api/"
_CLI = f"{_SITE}reference/cli/"
_IDFKIT = "https://developers.idfkit.com/api/"
_EPINTERFACE = "https://github.com/samuelduchesne/epinterface"

_Special = dict[str, tuple[Replacement | None, str, FrequentTask | None]]


def _idfkit(target: str, page: str) -> Replacement:
    return Replacement(package="idfkit", target=target, docs_url=f"{_IDFKIT}{page}")


def _v3(target: str, page: str = _API) -> Replacement:
    return Replacement(package="archetypal", target=target, docs_url=page)


def _sbem(target: str = "epinterface.sbem") -> Replacement:
    return Replacement(package="epinterface", target=target, docs_url=_EPINTERFACE)


def _module(
    module: str,
    replacement: Replacement | None,
    reason: str,
    names: tuple[str, ...] = (),
    *,
    special: _Special | None = None,
    task: FrequentTask | None = None,
    module_row: bool = True,
) -> tuple[RemovedCapability, ...]:
    """Return the row of a v2 module and of each public name it defines.

    Each name shares the module's replacement and reason unless `special` gives its own.
    """
    rows = [RemovedCapability("module", module, replacement, reason, task)] if module_row else []
    for name in names:
        name_replacement, name_reason, name_task = (special or {}).get(name, (replacement, reason, None))
        rows.append(RemovedCapability("name", f"{module}.{name}", name_replacement, name_reason, name_task))
    return tuple(rows)


def _options(
    command: str, flags: tuple[str, ...], replacement: Replacement | None, reason: str
) -> tuple[RemovedCapability, ...]:
    """Return one option row per flag; a flag written `-s/--silent` gets `-s` as its alias."""
    rows: list[RemovedCapability] = []
    for flag in flags:
        *aliases, long = flag.split("/")
        rows.append(RemovedCapability("option", f"{command} {long}", replacement, reason, aliases=tuple(aliases)))
    return tuple(rows)


# Shared replacements and reasons.
_LOAD_IDF = _idfkit("idfkit.load_idf", "io/")
_SIMULATE = _idfkit("idfkit.simulation.simulate", "simulation/runner/")
_SQL = _idfkit("idfkit.simulation.SQLResult", "simulation/sql/")
_MIGRATE = _idfkit("idfkit.migration.migrate", "migration/")
_EVALUATE = _idfkit("idfkit.schedules.evaluate", "schedules/")
_READ_UMI = _v3("archetypal.read_umi")
_REDUCE = _v3("archetypal.reduce")
_BATCH = _idfkit("idfkit.simulation.simulate_batch", "simulation/batch/")
_IDF_WHY = "idfkit reads, edits and writes EnergyPlus models, so archetypal no longer wraps eppy."
_RUN_WHY = "idfkit runs EnergyPlus and its preprocessors."
_RESULTS_WHY = "idfkit reads EnergyPlus results from the SQLite output."
_UMI_WHY = (
    "Archetypes are SBEM models from epinterface; archetypal.read_umi and archetypal.write_umi translate UMI "
    "libraries to and from them."
)
_INTERNAL = "It was an internal helper of archetypal 2, so there is no replacement."
_NO_SETTINGS = (
    "archetypal 3 has no global settings: it reads no environment variable and writes only the files you ask for, "
    "so there is no replacement."
)
_DATAPORTAL = (
    "archetypal 3.0 has no data portal and no replacement for it; TABULA returns as a reader in a later release, "
    "so stay on archetypal 2 for it until then."
)
_NO_FOLDERS = "archetypal 3 writes only the outputs you ask for, so there is no replacement for this folder."
_NO_LOG_FILE = "There is no replacement: use --log-level and redirect stderr to keep a log."
_TRANSITION_GONE = "The transition command is removed; idfkit.migration.migrate upgrades models."

REMOVED: tuple[RemovedCapability, ...] = (
    # --- The package's own names ---------------------------------------------------------------
    *_module(
        "archetypal",
        None,
        _INTERNAL,
        (
            "BuildingTemplate",
            "EnergyPlusVersion",
            "IDF",
            "Settings",
            "UmiTemplateLibrary",
            "ZoneWeight",
            "clear_cache",
            "config",
            "parallel_process",
            "settings",
        ),
        module_row=False,
        special={
            "IDF": (_LOAD_IDF, _IDF_WHY, "open-and-simulate"),
            "BuildingTemplate": (
                _REDUCE,
                "BuildingTemplate.from_idf reduced one model; archetypal.reduce reduces it to an SBEM archetype, "
                "which archetypal.write_umi writes as a building template.",
                "reduce-to-umi",
            ),
            "UmiTemplateLibrary": (_READ_UMI, _UMI_WHY, "edit-umi-library"),
            "EnergyPlusVersion": (
                _idfkit("idfkit.get_idf_version", "io/"),
                "idfkit gives a model's EnergyPlus version as a tuple and upgrades models with "
                "idfkit.migration.migrate.",
                "upgrade-version",
            ),
            "Settings": (None, _NO_SETTINGS, None),
            "settings": (None, _NO_SETTINGS, None),
            "config": (None, _NO_SETTINGS, None),
            "ZoneWeight": (
                None,
                "Reduction weights every zone by floor area as part of its method, so there is no replacement setting.",
                None,
            ),
            "clear_cache": (
                _idfkit("idfkit.simulation.SimulationCache", "simulation/cache/"),
                "archetypal 3 keeps no cache of its own; idfkit caches simulations.",
                None,
            ),
            "parallel_process": (_BATCH, "Running many simulations at once is idfkit's job.", None),
        },
    ),
    # --- archetypal 2's command-line module (archetypal 3 has its own `archetypal.cli`) ---------
    *_module(
        "archetypal.cli",
        _v3("archetypal reduce", _CLI),
        "It implemented archetypal 2's command line; use the archetypal command, whose reduce command keeps "
        "v2's main options.",
        (
            "CONTEXT_SETTINGS",
            "CliConfig",
            "cli",
            "pass_config",
            "reduce",
            "set_filepaths",
            "transition",
            "validate_energyplusversion",
            "validate_paths",
            "walkdirs",
        ),
        module_row=False,
        special={"transition": (_MIGRATE, _TRANSITION_GONE, None)},
    ),
    # --- Data portal ---------------------------------------------------------------------------
    *_module(
        "archetypal.dataportal",
        None,
        _DATAPORTAL,
        (
            "download_bld_window",
            "get_from_cache",
            "nrel_api_cbr_request",
            "nrel_bcl_api_request",
            "openei_api_request",
            "save_to_cache",
            "stat_can_geo_request",
            "stat_can_request",
            "tabula_api_request",
            "tabula_available_buildings",
            "tabula_building_details_sheet",
            "tabula_system",
            "tabula_system_request",
        ),
    ),
    # --- Running EnergyPlus --------------------------------------------------------------------
    *_module(
        "archetypal.eplus_interface",
        _SIMULATE,
        _RUN_WHY,
        (
            "BasementThread",
            "EnergyPlusExe",
            "EnergyPlusProcessError",
            "EnergyPlusProgram",
            "EnergyPlusThread",
            "EnergyPlusVersion",
            "EnergyPlusVersionError",
            "EnergyPlusWeatherError",
            "ExpandObjectsThread",
            "InvalidEnergyPlusVersion",
            "SlabThread",
            "TransitionThread",
        ),
        special={
            "EnergyPlusProcessError": (
                _idfkit("idfkit.exceptions.SimulationError", "exceptions/"),
                "idfkit raises SimulationError, quoting EnergyPlus's fatal and severe messages, from "
                "result.raise_for_status().",
                None,
            ),
            "EnergyPlusVersion": (
                _idfkit("idfkit.get_idf_version", "io/"),
                "idfkit gives a model's EnergyPlus version as a tuple.",
                None,
            ),
            "EnergyPlusVersionError": (
                _idfkit("idfkit.exceptions.EnergyPlusNotFoundError", "exceptions/"),
                "idfkit finds the installed EnergyPlus and names the versions it found when none fits.",
                None,
            ),
            "InvalidEnergyPlusVersion": (
                _idfkit("idfkit.exceptions.VersionNotFoundError", "exceptions/"),
                "idfkit raises VersionNotFoundError for a version it has no schema for.",
                None,
            ),
            "TransitionThread": (_MIGRATE, "idfkit upgrades models with EnergyPlus's transition programs.", None),
        },
    ),
    *_module(
        "archetypal.eplus_interface.basement",
        _idfkit("idfkit.simulation.run_basement_preprocessor", "simulation/runner/"),
        "idfkit runs the basement preprocessor, and simulate runs it when the model needs it.",
        ("BasementThread",),
    ),
    *_module(
        "archetypal.eplus_interface.energy_plus",
        _SIMULATE,
        _RUN_WHY,
        ("EnergyPlusExe", "EnergyPlusProgram", "EnergyPlusThread"),
    ),
    *_module(
        "archetypal.eplus_interface.exceptions",
        _idfkit("idfkit.exceptions", "exceptions/"),
        "idfkit raises its own errors for EnergyPlus runs, versions and weather files.",
        ("EnergyPlusProcessError", "EnergyPlusVersionError", "EnergyPlusWeatherError", "InvalidEnergyPlusVersion"),
    ),
    *_module(
        "archetypal.eplus_interface.expand_objects",
        _idfkit("idfkit.simulation.expand_objects", "simulation/expand/"),
        "idfkit runs ExpandObjects, and simulate runs it when the model needs it.",
        ("ExpandObjectsExe", "ExpandObjectsThread"),
    ),
    *_module(
        "archetypal.eplus_interface.slab",
        _idfkit("idfkit.simulation.run_slab_preprocessor", "simulation/runner/"),
        "idfkit runs the slab preprocessor, and simulate runs it when the model needs it.",
        ("SlabThread",),
    ),
    *_module(
        "archetypal.eplus_interface.transition",
        _MIGRATE,
        "idfkit upgrades models with EnergyPlus's transition programs.",
        ("TransitionExe", "TransitionThread"),
        task="upgrade-version",
    ),
    *_module(
        "archetypal.eplus_interface.version",
        _idfkit("idfkit.get_idf_version", "io/"),
        "idfkit gives a model's EnergyPlus version as a tuple and finds the installed EnergyPlus.",
        ("EnergyPlusVersion", "get_eplus_basedirs", "warn_if_not_compatible"),
        special={
            "get_eplus_basedirs": (
                _idfkit("idfkit.simulation.find_energyplus", "simulation/runner/"),
                "idfkit finds the installed EnergyPlus.",
                None,
            ),
            "warn_if_not_compatible": (
                None,
                "archetypal 3 checks nothing when imported, so there is no replacement; idfkit checks the "
                "EnergyPlus version when it runs a model.",
                None,
            ),
        },
    ),
    # --- Models ----------------------------------------------------------------------------------
    *_module(
        "archetypal.idfclass",
        _LOAD_IDF,
        _IDF_WHY,
        ("IDF", "Meters", "Outputs", "Variables", "__eq__", "get_default", "hash_model", "makedict", "nameexists"),
        special={
            "Meters": (_SQL, _RESULTS_WHY, None),
            "Variables": (_SQL, _RESULTS_WHY, None),
            "Outputs": (
                _idfkit("idfkit.simulation.prep_outputs", "simulation/results/"),
                "idfkit adds the output objects a run needs.",
                None,
            ),
            "__eq__": (None, _INTERNAL, None),
        },
    ),
    *_module(
        "archetypal.idfclass.end_use_balance",
        None,
        "archetypal 3 computes no end-use balance and has no replacement; reduction keeps its own energy ledgers.",
        ("EndUseBalance",),
    ),
    *_module(
        "archetypal.idfclass.extensions",
        _idfkit("idfkit.IDFObject", "objects/"),
        "idfkit's objects read and write their fields directly.",
        ("bunch2db", "get_coords", "get_default", "get_name_attribute", "makedict", "nameexists", "to_dict"),
    ),
    *_module(
        "archetypal.idfclass.idf",
        _LOAD_IDF,
        _IDF_WHY,
        (
            "IDF",
            "ModelInRelativeCoordinatesError",
            "ReportingFrequency",
            "ScheduleNotFoundError",
            "SimulationNotRunError",
            "closest_cardinal_angle",
            "find_and_launch",
        ),
        special={
            "ReportingFrequency": (_SQL, _RESULTS_WHY, None),
            "SimulationNotRunError": (
                _idfkit("idfkit.exceptions.OutputNotFoundError", "exceptions/"),
                "idfkit raises OutputNotFoundError when a result file is missing.",
                None,
            ),
            "find_and_launch": (None, _INTERNAL, None),
        },
    ),
    *_module(
        "archetypal.idfclass.load_balance",
        None,
        "archetypal 3 computes no load balance and has no replacement; reduction keeps its own energy ledgers.",
        ("LoadBalance",),
    ),
    *_module("archetypal.idfclass.meters", _SQL, _RESULTS_WHY, ("Meter", "MeterGroup", "Meters")),
    *_module(
        "archetypal.idfclass.outputs",
        _idfkit("idfkit.simulation.prep_outputs", "simulation/results/"),
        "idfkit adds the output objects a run needs.",
        ("Outputs",),
    ),
    *_module(
        "archetypal.idfclass.reports",
        _SQL,
        _RESULTS_WHY,
        (
            "get_html_report",
            "get_ideal_loads_summary",
            "get_report",
            "get_sqlite_report",
            "summary_reports_to_dataframes",
        ),
    ),
    *_module(
        "archetypal.idfclass.sql",
        _SQL,
        _RESULTS_WHY,
        ("Sql", "SqlOutput", "closing_connection"),
        special={"Sql": (_SQL, _RESULTS_WHY, "read-results")},
    ),
    *_module(
        "archetypal.idfclass.util",
        _idfkit("idfkit.get_idf_version", "io/"),
        "idfkit reads a model's version without parsing the rest.",
        ("get_idf_version", "getoldiddfile", "hash_model"),
        special={"hash_model": (None, _INTERNAL, None)},
    ),
    *_module("archetypal.idfclass.variables", _SQL, _RESULTS_WHY, ("Variable", "VariableGroup", "Variables")),
    # --- Results, schedules, glazing, plots --------------------------------------------------------
    *_module(
        "archetypal.plot",
        None,
        "archetypal 3 draws no figures, so there is no replacement; plot results with your own plotting library.",
        ("save_and_show",),
    ),
    *_module(
        "archetypal.reportdata",
        _SQL,
        _RESULTS_WHY,
        ("ReportData", "conjunction"),
        special={"ReportData": (_SQL, _RESULTS_WHY, "read-results")},
    ),
    *_module(
        "archetypal.schedule",
        _EVALUATE,
        "idfkit evaluates every EnergyPlus schedule type without running a simulation.",
        ("Schedule", "ScheduleTypeLimits", "get_year_for_first_weekday"),
        special={
            "Schedule": (
                _EVALUATE,
                "idfkit evaluates every EnergyPlus schedule type without running a simulation.",
                "evaluate-schedule",
            ),
            "ScheduleTypeLimits": (
                _idfkit("idfkit.schedules.create_schedule_type_limits", "schedules/"),
                "idfkit creates and resolves schedule type limits.",
                None,
            ),
        },
    ),
    *_module(
        "archetypal.simple_glazing",
        None,
        "SBEM describes windows by U-value, SHGC and visible transmittance, as EnergyPlus's simple glazing model "
        "does, so archetypal 3 needs no conversion and has no replacement.",
        (
            "calc_simple_glazing",
            "frac_inward",
            "lambda_eff",
            "r_i_s",
            "r_i_s_intermediate",
            "r_i_w",
            "r_l_w",
            "r_o_s",
            "r_o_s_intermediate",
            "r_o_w",
            "r_s_f",
            "r_vis_b",
            "r_vis_f",
            "t_sol",
            "t_sol_intermediate",
            "thickness",
        ),
    ),
    *_module(
        "archetypal.tabulardata",
        _SQL,
        _RESULTS_WHY,
        ("TabularData", "conjunction", "or_conjunction"),
        special={"TabularData": (_SQL, _RESULTS_WHY, "read-results")},
    ),
    # --- UMI templates -----------------------------------------------------------------------------
    *_module(
        "archetypal.template",
        _sbem(),
        _UMI_WHY,
        (
            "BuildingTemplate",
            "DaySchedule",
            "DomesticHotWaterSetting",
            "GasLayer",
            "GasMaterial",
            "GlazingMaterial",
            "MassRatio",
            "MaterialLayer",
            "OpaqueConstruction",
            "OpaqueMaterial",
            "StructureInformation",
            "UmiSchedule",
            "VentilationSetting",
            "WeekSchedule",
            "WindowConstruction",
            "WindowSetting",
            "YearSchedule",
            "YearSchedulePart",
            "ZoneConditioning",
            "ZoneConstructionSet",
            "ZoneDefinition",
            "ZoneLoad",
        ),
    ),
    *_module("archetypal.template.building_template", _sbem(), _UMI_WHY, ("BuildingTemplate",)),
    *_module(
        "archetypal.template.conditioning",
        _sbem(),
        _UMI_WHY,
        ("EconomizerTypes", "FuelType", "HeatRecoveryTypes", "IdealSystemLimit", "UmiBaseEnum", "ZoneConditioning"),
    ),
    *_module("archetypal.template.constructions", _sbem(), _UMI_WHY),
    *_module(
        "archetypal.template.constructions.base_construction",
        _sbem(),
        _UMI_WHY,
        ("ConstructionBase", "LayeredConstruction"),
    ),
    *_module("archetypal.template.constructions.internal_mass", _sbem(), _UMI_WHY, ("InternalMass",)),
    *_module("archetypal.template.constructions.opaque_construction", _sbem(), _UMI_WHY, ("OpaqueConstruction",)),
    *_module(
        "archetypal.template.constructions.window_construction",
        _sbem(),
        _UMI_WHY,
        ("ShadingType", "WindowConstruction", "WindowType"),
    ),
    *_module(
        "archetypal.template.dhw",
        _sbem(),
        _UMI_WHY,
        ("DomesticHotWaterSetting", "water_main_correlation"),
        special={"water_main_correlation": (None, _INTERNAL, None)},
    ),
    *_module("archetypal.template.load", _sbem(), _UMI_WHY, ("DimmingTypes", "ZoneLoad")),
    *_module("archetypal.template.materials", _sbem(), _UMI_WHY, ("GasMaterial", "GlazingMaterial", "OpaqueMaterial")),
    *_module("archetypal.template.materials.gas_layer", _sbem(), _UMI_WHY, ("GasLayer",)),
    *_module("archetypal.template.materials.gas_material", _sbem(), _UMI_WHY, ("GasMaterial",)),
    *_module("archetypal.template.materials.glazing_material", _sbem(), _UMI_WHY, ("GlazingMaterial",)),
    *_module("archetypal.template.materials.material_base", _sbem(), _UMI_WHY, ("MaterialBase",)),
    *_module("archetypal.template.materials.material_layer", _sbem(), _UMI_WHY, ("MaterialLayer",)),
    *_module("archetypal.template.materials.nomass_material", _sbem(), _UMI_WHY, ("NoMassMaterial",)),
    *_module("archetypal.template.materials.opaque_material", _sbem(), _UMI_WHY, ("OpaqueMaterial",)),
    *_module(
        "archetypal.template.schedule",
        _sbem(),
        _UMI_WHY,
        ("DaySchedule", "UmiSchedule", "WeekSchedule", "YearSchedule", "YearSchedulePart"),
    ),
    *_module("archetypal.template.structure", _sbem(), _UMI_WHY, ("MassRatio", "StructureInformation")),
    *_module(
        "archetypal.template.umi_base",
        _sbem(),
        _UMI_WHY,
        ("MetaData", "UmiBase", "UniqueName", "UserSet"),
        special={"UniqueName": (None, _INTERNAL, None)},
    ),
    *_module(
        "archetypal.template.ventilation",
        _sbem(),
        _UMI_WHY,
        (
            "VentilationSetting",
            "VentilationType",
            "do_infiltration",
            "do_natural_ventilation",
            "do_scheduled_ventilation",
            "get_from_tabulardata",
            "nominal_infiltration",
            "nominal_mech_ventilation",
            "nominal_nat_ventilation",
            "nominal_ventilation",
            "nominal_ventilation_aggregation",
            "resolve_temp",
        ),
        special=dict.fromkeys(
            (
                "do_infiltration",
                "do_natural_ventilation",
                "do_scheduled_ventilation",
                "get_from_tabulardata",
                "nominal_infiltration",
                "nominal_mech_ventilation",
                "nominal_nat_ventilation",
                "nominal_ventilation",
                "nominal_ventilation_aggregation",
                "resolve_temp",
            ),
            (_REDUCE, "Reduction reads ventilation and infiltration from the model and its results (spec 002).", None),
        ),
    ),
    *_module("archetypal.template.window_setting", _sbem(), _UMI_WHY, ("WindowSetting",)),
    *_module(
        "archetypal.template.zone_construction_set",
        _sbem(),
        _UMI_WHY,
        ("SurfaceDispatcher", "ZoneConstructionSet"),
        special={"SurfaceDispatcher": (None, _INTERNAL, None)},
    ),
    *_module(
        "archetypal.template.zonedefinition",
        _sbem(),
        _UMI_WHY,
        ("ZoneDefinition", "is_core", "resolve_obco"),
        special={
            "is_core": (_REDUCE, "Reduction classifies zones as core or perimeter (spec 002).", None),
            "resolve_obco": (None, _INTERNAL, None),
        },
    ),
    *_module(
        "archetypal.umi_template",
        _READ_UMI,
        _UMI_WHY,
        (
            "AllFailedError",
            "DEEP_OBJECTS",
            "DuplicateAttributeError",
            "UmiTemplateLibrary",
            "no_duplicates",
            "parent_child_traversal",
            "parent_key_child_traversal",
            "traverse",
        ),
        special={
            "AllFailedError": (
                _v3("archetypal.errors.ReductionError"),
                "Each failed model raises its own reduction error, and the command line lists every failure.",
                None,
            ),
            **dict.fromkeys(
                (
                    "DEEP_OBJECTS",
                    "DuplicateAttributeError",
                    "no_duplicates",
                    "parent_child_traversal",
                    "parent_key_child_traversal",
                    "traverse",
                ),
                (None, _INTERNAL, None),
            ),
        },
    ),
    # --- Helpers ---------------------------------------------------------------------------------
    *_module(
        "archetypal.utils",
        None,
        _INTERNAL,
        (
            "CustomJSONEncoder",
            "angle",
            "cd",
            "check_unique_name",
            "clear_cache",
            "close_logger",
            "config",
            "copy_file",
            "docstring_parameter",
            "extend_class",
            "float_round",
            "get_logger",
            "is_referenced",
            "lcm",
            "load_umi_template",
            "log",
            "parallel_process",
            "recursive_len",
            "reduce",
            "rotate",
            "safe_prod",
            "signif",
            "submit",
            "timeit",
            "top",
            "weighted_mean",
        ),
        special={
            "clear_cache": (
                _idfkit("idfkit.simulation.SimulationCache", "simulation/cache/"),
                "archetypal 3 keeps no cache of its own; idfkit caches simulations.",
                None,
            ),
            "config": (None, _NO_SETTINGS, None),
            "parallel_process": (_BATCH, "Running many simulations at once is idfkit's job.", None),
            "load_umi_template": (_READ_UMI, _UMI_WHY, None),
            **dict.fromkeys(
                ("log", "get_logger", "close_logger"),
                (
                    None,
                    "archetypal 3 logs to the standard `archetypal` logger and configures no handler, so there is "
                    "no replacement.",
                    None,
                ),
            ),
        },
    ),
    *_module(
        "archetypal.zone_graph",
        None,
        "archetypal 3 builds no zone adjacency graph, so there is no replacement.",
        ("ZoneGraph", "add_to_report", "discrete_cmap"),
    ),
    # --- Command line (contracts/cli.md, FR-013) -------------------------------------------------
    RemovedCapability(
        "command",
        "archetypal transition",
        _MIGRATE,
        "archetypal no longer upgrades models; idfkit does, with EnergyPlus's transition programs.",
        "upgrade-version",
    ),
    *_options(
        "archetypal",
        ("--data-folder", "--logs-folder", "--imgs-folder", "--cache-folder"),
        None,
        _NO_FOLDERS,
    ),
    RemovedCapability(
        "option",
        "archetypal --ep_version",
        _idfkit("idfkit.simulation.find_energyplus", "simulation/runner/"),
        "archetypal no longer runs a chosen EnergyPlus; idfkit finds the installed one.",
    ),
    RemovedCapability(
        "option",
        "archetypal --cache-responses",
        None,
        "The data portal is removed, so there is no replacement; TABULA returns as a reader in a later release.",
        aliases=("-c",),
    ),
    *_options("archetypal", ("-l/--log-file", "-s/--silent", "--log-name", "--log-filename"), None, _NO_LOG_FILE),
    RemovedCapability(
        "option",
        "archetypal reduce --version",
        _MIGRATE,
        "reduce no longer upgrades models; upgrade them with idfkit.migration.migrate before reducing.",
        aliases=("-v",),
    ),
    RemovedCapability(
        "option",
        "archetypal reduce --all_zones",
        _v3("archetypal reduce --layout", _CLI),
        "Replaced by --layout; reduction always counts every conditioned zone.",
        aliases=("-z",),
    ),
    *_options("archetypal transition", ("-p/--parallel", "-v/--version", "-y"), _MIGRATE, _TRANSITION_GONE),
)
"""Every removed v2 capability (spec 001, user stories 1 and 2; tests/data/v2_surface.json)."""


def anchor(heading: str) -> str:
    """Return the anchor the docs site gives a heading (Python-Markdown's default slug).

    Args:
        heading: The heading text, such as `archetypal.IDF`.

    Returns:
        The anchor, such as `archetypalidf`.
    """
    slug = re.sub(r"[^\w\s-]", "", heading).strip().lower()
    return re.sub(r"[-\s]+", "-", slug)


def row_anchor(v2_path: str) -> str:
    """Return the anchor of a row in the migration guide's table.

    It is `anchor(v2_path)`, except when an earlier row of `REMOVED` has the same anchor (the
    slug ignores case, so `archetypal.Settings` and `archetypal.settings` collide): the later
    rows then get `_1`, `_2`, ... in table order, as Python-Markdown numbers repeated headings.

    Args:
        v2_path: A `v2_path` of `REMOVED`.

    Returns:
        The anchor, such as `archetypalidf` or `archetypalsettings_1`.
    """
    base = anchor(v2_path)
    count = 0
    for row in REMOVED:
        if row.v2_path == v2_path:
            return base if count == 0 else f"{base}_{count}"
        if anchor(row.v2_path) == base:
            count += 1
    return base


def _message(row: RemovedCapability) -> str:
    instead = (
        row.reason if row.replacement is None else f"Use {row.replacement.target} ({row.replacement.package}) instead."
    )
    return f"was removed in archetypal 3.\n{instead}\nSee {MIGRATION_GUIDE_URL}#{row_anchor(row.v2_path)}"


def raise_removed(v2_path: str) -> NoReturn:
    """Raise the error for a removed v2 capability.

    For a `module` row, the error names the deepest removed module under it that the import in
    progress asked for: the stub of `archetypal.idfclass` raises `archetypal.idfclass.sql`'s row
    for `import archetypal.idfclass.sql`.

    Args:
        v2_path: A `v2_path` of `REMOVED`.

    Raises:
        RemovedInArchetypal3Error: Always, naming the replacement and the migration guide's section.
        LookupError: `v2_path` is not in `REMOVED`.
    """
    if v2_path == "__main__":
        # A stub run as `python -m archetypal.utils` is `__main__`; its spec keeps its name.
        spec = getattr(sys.modules.get("__main__"), "__spec__", None)
        v2_path = getattr(spec, "name", v2_path)
    rows = {row.v2_path: row for row in REMOVED}
    if v2_path not in rows:
        msg = f"{v2_path} is not a removed v2 capability"
        raise LookupError(msg)
    row = rows[v2_path]
    if row.kind == "module":
        # Python runs a parent module before its child, so the stub of `archetypal.idfclass` is
        # what runs for `import archetypal.idfclass.sql`: name the row of the module asked for.
        requested = _requested_module(v2_path)
        while requested != v2_path and (requested not in rows or rows[requested].kind != "module"):
            requested = requested.rpartition(".")[0]
        row = rows[requested]
    raise RemovedInArchetypal3Error(row.v2_path, _message(row)) from None


def _requested_module(module: str) -> str:
    """Return the deepest module under `module` that an import in progress asked for, else `module`.

    It reads the `name` of the import system's `_find_and_load` frames (CPython); without them,
    it returns `module`.
    """
    requested = module
    frame = inspect.currentframe()
    while frame is not None:
        code = frame.f_code
        if code.co_name in {"_find_and_load", "_find_and_load_unlocked"} and code.co_filename.startswith(
            "<frozen importlib"
        ):
            name = frame.f_locals.get("name")
            if isinstance(name, str) and name.startswith(f"{module}.") and len(name) > len(requested):
                requested = name
        frame = frame.f_back
    return requested
