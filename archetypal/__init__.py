################################################################################
# Module: __init__.py
# Description: Archetypal: Retrieve, construct and analyse building archetypes
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

# Version of the package
from pkg_resources import get_distribution, DistributionNotFound

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

# don't display futurewarnings

import warnings

warnings.simplefilter(action="ignore", category=FutureWarning)
warnings.simplefilter(action="ignore", category=UserWarning)

from .idfclass import IDF
from .umi_template import UmiTemplateLibrary
