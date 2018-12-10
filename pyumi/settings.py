import logging as lg

# locations to save data, logs, images, and cache

data_folder = 'data'
logs_folder = 'logs'
imgs_folder = 'images'
cache_folder = 'cache'
umitemplate = 'data/BostonTemplateLibrary.json'

# cache server responses
use_cache = False

# write log to file and/or to console
log_file = False
log_console = False
log_notebook = False
log_level = lg.INFO
log_name = 'pyumi'
log_filename = 'pyumi'

# usual idfobjects
useful_idf_objects = ['WINDOWMATERIAL:GAS', 'WINDOWMATERIAL:GLAZING', 'WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM',
                      'MATERIAL', 'MATERIAL:NOMASS', 'CONSTRUCTION', 'BUILDINGSURFACE:DETAILED',
                      'FENESTRATIONSURFACE:DETAILED', 'SCHEDULE:DAY:INTERVAL', 'SCHEDULE:WEEK:DAILY', 'SCHEDULE:YEAR']

# List of Available SQLite Tables
# Ref: https://bigladdersoftware.com/epx/docs/8-3/output-details-and-examples/eplusout.sql.html#schedules-table

available_sqlite_tables = {'ComponentSizes': {'PrimaryKey': ['ComponentSizesIndex'], 'ParseDates': []},
                           'ConstructionLayers': {'PrimaryKey': ['ConstructionIndex'], 'ParseDates': []},
                           'Constructions': {'PrimaryKey': ['ConstructionIndex'], 'ParseDates': []},
                           'Materials': {'PrimaryKey': ['MaterialIndex'], 'ParseDates': []},
                           'NominalBaseboardHeaters': {'PrimaryKey': ['NominalBaseboardHeaterIndex'], 'ParseDates': []},
                           'NominalElectricEquipment': {'PrimaryKey': ['NominalElectricEquipmentIndex'],
                                                        'ParseDates': []},
                           'NominalGasEquipment': {'PrimaryKey': ['NominalGasEquipmentIndex'], 'ParseDates': []},
                           'NominalHotWaterEquipment': {'PrimaryKey': ['NominalHotWaterEquipmentIndex'],
                                                        'ParseDates': []},
                           'NominalInfiltration': {'PrimaryKey': ['NominalInfiltrationIndex'], 'ParseDates': []},
                           'NominalLighting': {'PrimaryKey': ['NominalLightingIndex'], 'ParseDates': []},
                           'NominalOtherEquipment': {'PrimaryKey': ['NominalOtherEquipmentIndex'], 'ParseDates': []},
                           'NominalPeople': {'PrimaryKey': ['NominalPeopleIndex'], 'ParseDates': []},
                           'NominalSteamEquipment': {'PrimaryKey': ['NominalSteamEquipmentIndex'], 'ParseDates': []},
                           'NominalVentilation': {'PrimaryKey': ['NominalVentilationIndex'], 'ParseDates': []},
                           'ReportData': {'PrimaryKey': ['ReportDataIndex'], 'ParseDates': []},
                           'ReportDataDictionary': {'PrimaryKey': ['ReportDataDictionaryIndex'], 'ParseDates': []},
                           'ReportExtendedData': {'PrimaryKey': ['ReportExtendedDataIndex'], 'ParseDates': []},
                           'RoomAirModels': {'PrimaryKey': ['ZoneIndex'], 'ParseDates': []},
                           'Schedules': {'PrimaryKey': ['ScheduleIndex'], 'ParseDates': []},
                           'Surfaces': {'PrimaryKey': ['SurfaceIndex'], 'ParseDates': []},
                           'SystemSizes': {'PrimaryKey': ['SystemSizesIndex'],
                                           'ParseDates': {'PeakHrMin': '%m/%d %H:%M:%S'}},
                           'Time': {'PrimaryKey': ['TimeIndex'], 'ParseDates': []},
                           'ZoneGroups': {'PrimaryKey': ['ZoneGroupIndex'], 'ParseDates': []},
                           'Zones': {'PrimaryKey': ['ZoneIndex'], 'ParseDates': []},
                           'ZoneLists': {'PrimaryKey': ['ZoneListIndex'], 'ParseDates': []},
                           'ZoneSizes': {'PrimaryKey': ['ZoneSizesIndex'], 'ParseDates': []},
                           'ZoneInfoZoneLists': {'PrimaryKey': ['ZoneListIndex'], 'ParseDates': []},
                           'Simulations': {'PrimaryKey': ['SimulationIndex'],
                                           'ParseDates': {'TimeStamp': {'format': 'YMD=%Y.%m.%d %H:%M'}}},
                           'EnvironmentPeriods': {'PrimaryKey': ['EnvironmentPeriodIndex'], 'ParseDates': []},
                           'TabularData': {'PrimaryKey': ['TabularDataIndex'], 'ParseDates': []},
                           'Strings': {'PrimaryKey': ['StringIndex'], 'ParseDates': []},
                           'StringTypes': {'PrimaryKey': ['StringTypeIndex'], 'ParseDates': []},
                           'TabularDataWithStrings': {'PrimaryKey': ['TabularDataIndex'], 'ParseDates': []},
                           'Errors': {'PrimaryKey': ['ErrorIndex'], 'ParseDates': []}}

# common_umi_objects
common_umi_objects = []
