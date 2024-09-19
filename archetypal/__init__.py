################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import logging as lg
from pathlib import Path
from typing import Any, List, Literal, Optional

from energy_pandas.units import unit_registry

# Version of the package
from pkg_resources import DistributionNotFound, get_distribution

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic_settings import BaseSettingsModel as BaseSettings
from pydantic import DirectoryPath, Field

try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator


class ZoneWeight:
    """Zone weights for Umi Templates"""

    weight_attr = {0: "area", 1: "volume"}

    def __init__(self, n=0):
        self._weight_attr = self.weight_attr[n]

    def __str__(self):
        return self.get_weight_attr()

    def get_weight_attr(self):
        return self._weight_attr

    def set_weigth_attr(self, weight):
        if weight not in self.weight_attr.values():
            i = len(self.weight_attr) + 1
            self.weight_attr[i] = weight
        self._weight_attr = weight


class Settings(BaseSettings, arbitrary_types_allowed=True, validate_assignment=True):
    data_folder: Path = Field("data", validation_alias="ARCHETYPAL_DATA")
    logs_folder: Path = Field("logs", validation_alias="ARCHETYPAL_LOGS")
    imgs_folder: Path = Field("images", validation_alias="ARCHETYPAL_IMAGES")
    cache_folder: Path = Field("cache", validation_alias="ARCHETYPAL_CACHE")

    # cache server responses
    cache_responses: bool = Field(False, validation_alias="ARCHETYPAL_CACHE_RESPONSES")

    # Debug behavior
    debug: bool = Field(False, validation_alias="ARCHETYPAL_DEBUG")

    # write log to file and/or to console
    log_file: bool = Field(False, validation_alias="ARCHETYPAL_LOG_FILE")
    log_console: bool = Field(False, validation_alias="ARCHETYPAL_LOG_CONSOLE")
    log_notebook: bool = Field(False, validation_alias="ARCHETYPAL_LOG_NOTEBOOK")
    log_level: Literal[0, 10, 20, 30, 40, 50] = Field(lg.INFO, validation_alias="ARCHETYPAL_LOG_LEVEL")
    log_name: str = Field("archetypal", validation_alias="ARCHETYPAL_LOG_NAME")
    log_filename: str = Field("archetypal")

    # usual idfobjects
    useful_idf_objects: List[str] = [
        "WINDOWMATERIAL:GAS",
        "WINDOWMATERIAL:GLAZING",
        "WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM",
        "MATERIAL",
        "MATERIAL:NOMASS",
        "CONSTRUCTION",
        "BUILDINGSURFACE:DETAILED",
        "FENESTRATIONSURFACE:DETAILED",
        "SCHEDULE:DAY:INTERVAL",
        "SCHEDULE:WEEK:DAILY",
        "SCHEDULE:YEAR",
    ]

    # List of Available SQLite Tables
    # Ref: https://bigladdersoftware.com/epx/docs/8-3/output-details-and-examples
    # /eplusout.sql.html#schedules-table

    available_sqlite_tables: dict = dict(
        ComponentSizes={"PrimaryKey": ["ComponentSizesIndex"], "ParseDates": []},
        ConstructionLayers={"PrimaryKey": ["ConstructionIndex"], "ParseDates": []},
        Constructions={"PrimaryKey": ["ConstructionIndex"], "ParseDates": []},
        Materials={"PrimaryKey": ["MaterialIndex"], "ParseDates": []},
        NominalBaseboardHeaters={
            "PrimaryKey": ["NominalBaseboardHeaterIndex"],
            "ParseDates": [],
        },
        NominalElectricEquipment={
            "PrimaryKey": ["NominalElectricEquipmentIndex"],
            "ParseDates": [],
        },
        NominalGasEquipment={
            "PrimaryKey": ["NominalGasEquipmentIndex"],
            "ParseDates": [],
        },
        NominalHotWaterEquipment={
            "PrimaryKey": ["NominalHotWaterEquipmentIndex"],
            "ParseDates": [],
        },
        NominalInfiltration={
            "PrimaryKey": ["NominalInfiltrationIndex"],
            "ParseDates": [],
        },
        NominalLighting={"PrimaryKey": ["NominalLightingIndex"], "ParseDates": []},
        NominalOtherEquipment={
            "PrimaryKey": ["NominalOtherEquipmentIndex"],
            "ParseDates": [],
        },
        NominalPeople={"PrimaryKey": ["NominalPeopleIndex"], "ParseDates": []},
        NominalSteamEquipment={
            "PrimaryKey": ["NominalSteamEquipmentIndex"],
            "ParseDates": [],
        },
        NominalVentilation={
            "PrimaryKey": ["NominalVentilationIndex"],
            "ParseDates": [],
        },
        ReportData={"PrimaryKey": ["ReportDataIndex"], "ParseDates": []},
        ReportDataDictionary={
            "PrimaryKey": ["ReportDataDictionaryIndex"],
            "ParseDates": [],
        },
        ReportExtendedData={
            "PrimaryKey": ["ReportExtendedDataIndex"],
            "ParseDates": [],
        },
        RoomAirModels={"PrimaryKey": ["ZoneIndex"], "ParseDates": []},
        Schedules={"PrimaryKey": ["ScheduleIndex"], "ParseDates": []},
        Surfaces={"PrimaryKey": ["SurfaceIndex"], "ParseDates": []},
        SystemSizes={
            "PrimaryKey": ["SystemSizesIndex"],
            "ParseDates": {"PeakHrMin": "%m/%d %H:%M:%S"},
        },
        Time={"PrimaryKey": ["TimeIndex"], "ParseDates": []},
        ZoneGroups={"PrimaryKey": ["ZoneGroupIndex"], "ParseDates": []},
        Zones={"PrimaryKey": ["ZoneIndex"], "ParseDates": []},
        ZoneLists={"PrimaryKey": ["ZoneListIndex"], "ParseDates": []},
        ZoneSizes={"PrimaryKey": ["ZoneSizesIndex"], "ParseDates": []},
        ZoneInfoZoneLists={"PrimaryKey": ["ZoneListIndex"], "ParseDates": []},
        Simulations={
            "PrimaryKey": ["SimulationIndex"],
            "ParseDates": {"TimeStamp": {"format": "YMD=%Y.%m.%d %H:%M"}},
        },
        EnvironmentPeriods={"PrimaryKey": ["EnvironmentPeriodIndex"], "ParseDates": []},
        TabularData={"PrimaryKey": ["TabularDataIndex"], "ParseDates": []},
        Strings={"PrimaryKey": ["StringIndex"], "ParseDates": []},
        StringTypes={"PrimaryKey": ["StringTypeIndex"], "ParseDates": []},
        TabularDataWithStrings={"PrimaryKey": ["TabularDataIndex"], "ParseDates": []},
        Errors={"PrimaryKey": ["ErrorIndex"], "ParseDates": []},
    )

    zone_weight: ZoneWeight = ZoneWeight(n=0)

    ep_version: str = Field(
        "9-2-0",
        validation_alias="ENERGYPLUS_VERSION",
        description="Latest version of EnergyPlus compatible with archetypal. looks "
        "for ENERGYPLUS_VERSION in os.environ",
    )

    energyplus_location: Optional[DirectoryPath] = Field(
        None,
        validation_alias="ENERGYPLUS_LOCATION",
        description="Root directory of the EnergyPlus install.",
    )

    unit_registry: Any = None

    @field_validator("unit_registry")
    @classmethod
    def initialize_units(cls, v):
        if v is not None:
            additional_units = (
                "Dimensionless = dimensionless = Fraction = fraction",
                "@alias degC = Temperature = temperature",
            )
            for unit in additional_units:
                v.define(unit)
        return v


settings = Settings()
settings.unit_registry = unit_registry

# After settings are loaded, import other modules
from .eplus_interface.version import EnergyPlusVersion  # noqa: E402
from .idfclass import IDF  # noqa: E402
from .umi_template import (
    BuildingTemplate,  # noqa: E402
    UmiTemplateLibrary,  # noqa: E402
)
from .utils import clear_cache, config, parallel_process  # noqa: E402

try:
    __version__ = get_distribution("archetypal").version
except DistributionNotFound:
    # package is not installed
    __version__ = "0.0.0"  # should happen only if package is copied, not installed.
else:
    # warn if a newer version of archetypal is available
    from .eplus_interface.version import warn_if_not_compatible
finally:
    # warn if energyplus not installed or incompatible
    from .eplus_interface.version import warn_if_not_compatible

    warn_if_not_compatible()

from .idfclass import IDF  # noqa: E402

__all__ = ["settings", "Settings", "__version__", "utils", "dataportal", "IDF"]
