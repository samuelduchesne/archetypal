import logging as lg

# locations to save data, logs, images, and cache
data_folder = 'data'
logs_folder = 'logs'
imgs_folder = 'images'
cache_folder = 'cache'

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
