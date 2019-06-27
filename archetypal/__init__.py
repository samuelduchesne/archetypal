################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

# Version of the package
__version__ = '1.2.1'
# Latest version of EnergyPlus compatible with archetypal
ep_version = '8-9-0'

# warn if a newer version of archetypal is available
from outdated import warn_if_outdated
warn_if_outdated('archetypal', __version__)

from .utils import *
from .simple_glazing import *
from .idfclass import *
from .schedule import Schedule
from .dataportal import *
from .plot import *
from .trnsys import *
from .cli import *