################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

# Version of the package
__version__ = "1.3.1"

# warn if a newer version of archetypal is available
from outdated import warn_if_outdated
from .utils import warn_if_not_compatible

warn_if_outdated("archetypal", __version__)
warn_if_not_compatible()

from .utils import *
from .simple_glazing import *
from .energyseries import EnergySeries
from .energydataframe import EnergyDataFrame
from .reportdata import ReportData
from .tabulardata import TabularData
from .idfclass import *
from .schedule import Schedule
from .dataportal import *
from .plot import *
from .trnsys import *
from .template import *
from .umi_template import *
from .cli import *
