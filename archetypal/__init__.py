################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
import logging as lg
from pathlib import Path
from typing import Literal, List, Optional, Any

from energy_pandas.units import unit_registry

# Version of the package
from pkg_resources import get_distribution, DistributionNotFound
from pydantic import (
    BaseSettings,
    Field,
    validator,
    DirectoryPath,
)

# don't display futurewarnings

import warnings

warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=UserWarning)


class ZoneWeight(object):
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


class Settings(BaseSettings):
    class Config:
        arbitrary_types_allowed = True
        validate_assignment = True

    data_folder: Path = Field("data", env="ARCHETYPAL_DATA")
    logs_folder: Path = Field("logs", env="ARCHETYPAL_LOGS")
    imgs_folder: Path = Field("images", env="ARCHETYPAL_IMAGES")
    cache_folder: Path = Field("cache", env="ARCHETYPAL_CACHE")

    # cache server responses
    cache_responses: bool = Field(False, env="ARCHETYPAL_CACHE_RESPONSES")

    # Debug behavior
    debug = Field(False, env="ARCHETYPAL_DEBUG")

    # write log to file and/or to console
    log_file: bool = Field(False)
    log_console: bool = Field(False)
    log_notebook: bool = Field(False)
    log_level: Literal[0, 10, 20, 30, 40, 50] = Field(
        lg.INFO, env="ARCHETYPAL_LOG_LEVEL"
    )
    log_name: str = Field("archetypal", env="ARCHETYPAL_LOG_NAME")
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

    zone_weight = ZoneWeight(n=0)

    ep_version: str = Field(
        "9-2-0",
        env="ENERGYPLUS_VERSION",
        description="Latest version of EnergyPlus compatible with archetypal. looks "
        "for ENERGYPLUS_VERSION in os.environ",
    )

    energyplus_location: Optional[DirectoryPath] = Field(
        None,
        env="ENERGYPLUS_LOCATION",
        description="Root directory of the EnergyPlus install.",
    )

    unit_registry: Any = None

    @validator("unit_registry")
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
from .idfclass import IDF
from .eplus_interface.version import EnergyPlusVersion
from .umi_template import UmiTemplateLibrary
from .utils import config, clear_cache, parallel_process
from .umi_template import BuildingTemplate


try:
    __version__ = get_distribution("archetypal").version
except DistributionNotFound:
    # package is not installed
    __version__ = "0.0.0"  # should happen only if package is copied, not installed.
else:
    # warn if a newer version of archetypal is available
    from outdated import warn_if_outdated
    from .eplus_interface.version import warn_if_not_compatible
finally:
    # warn if energyplus not installed or incompatible
    from .eplus_interface.version import warn_if_not_compatible

    warn_if_not_compatible()
