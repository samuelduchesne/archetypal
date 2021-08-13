################################################################################
# Module: settings.py
# Description: Various settings used across the package
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import logging as lg
import os

from path import Path

# locations to save data, logs, images, and cache
import archetypal

data_folder = Path("data")
logs_folder = Path("logs")
imgs_folder = Path("images")
cache_folder = Path("cache")
umitemplate = Path("data/BostonTemplateLibrary.json")

# cache server responses
use_cache = False

# Debug behavior
debug = False

# write log to file and/or to console
log_file = False
log_console = False
log_notebook = False
log_level = lg.INFO
log_name = "archetypal"
log_filename = "archetypal"

# usual idfobjects
useful_idf_objects = [
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

available_sqlite_tables = dict(
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
    NominalGasEquipment={"PrimaryKey": ["NominalGasEquipmentIndex"], "ParseDates": []},
    NominalHotWaterEquipment={
        "PrimaryKey": ["NominalHotWaterEquipmentIndex"],
        "ParseDates": [],
    },
    NominalInfiltration={"PrimaryKey": ["NominalInfiltrationIndex"], "ParseDates": []},
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
    NominalVentilation={"PrimaryKey": ["NominalVentilationIndex"], "ParseDates": []},
    ReportData={"PrimaryKey": ["ReportDataIndex"], "ParseDates": []},
    ReportDataDictionary={
        "PrimaryKey": ["ReportDataDictionaryIndex"],
        "ParseDates": [],
    },
    ReportExtendedData={"PrimaryKey": ["ReportExtendedDataIndex"], "ParseDates": []},
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

# common_umi_objects
common_umi_objects = []

# default crs for when creating plots and querying databases
default_crs = {"init": "epsg:4326"}

# unique schedule number as list
unique_schedules = []

resource_package = archetypal.__name__  # Could be any module/package name

# Units

from energy_pandas.units import unit_registry

unit_registry.define("m3 = 1 * meter ** 3 = m³")
unit_registry.define(
    "degree_Celsius = kelvin; offset: 273.15 = °C = C = celsius = degC = degreeC"
)
unit_registry.define(
    "degree_Fahrenheit = 5 / 9 * kelvin; offset: 233.15 + 200 / 9 = "
    "°F = F = fahrenheit = degF = degreeF"
)
unit_registry.define("ach = dimensionless")  # Air Changes per Hour
unit_registry.define("acr = 1 / hour")  # Air change rate


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


zone_weight = ZoneWeight(n=0)

# Latest version of EnergyPlus compatible with archetypal looks for ENERGYPLUS_VERSION in os.environ
ep_version = (
    os.getenv("ENERGYPLUS_VERSION").replace("-", ".")
    if os.getenv("ENERGYPLUS_VERSION")
    else "9-2-0"  # default if not found
)
