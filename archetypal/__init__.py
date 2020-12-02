################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

# Version of the package
__version__ = "1.3.4"

# warn if a newer version of archetypal is available
from outdated import warn_if_outdated

from .eplus_interface.version import warn_if_not_compatible

warn_if_outdated("archetypal", __version__)
warn_if_not_compatible()

from .utils import *
from .simple_glazing import *
from .energypandas import EnergySeries, EnergyDataFrame
from .reportdata import ReportData
from .schedule import Schedule
from .plot import *
from .eplus_interface import *
from .idfclass.idf import IDF
from .dataportal import *
from .trnsys import *
from .umi_template import UmiTemplateLibrary
from .utils import *
from .cli import reduce, transition, convert
