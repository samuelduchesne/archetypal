################################################################################
# Module: __init__.py
# Description: Archetypal: Convert EnergyPlus models to UMI building templates
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
from __future__ import annotations

import logging as lg

# Version of the package
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, ClassVar, Literal, Optional

# Version of the package
from pkg_resources import DistributionNotFound, get_distribution

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic_settings import BaseSettingsModel as BaseSettings
from pydantic import Field

try:
    from pydantic import field_validator
except ImportError:
    from pydantic import validator as field_validator


class ZoneWeight:
    """Zone weights for Umi Templates"""

    weight_attr: ClassVar[dict] = {0: "area", 1: "volume"}

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

    zone_weight: ZoneWeight = ZoneWeight(n=0)

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

try:
    from energy_pandas.units import unit_registry

    settings.unit_registry = unit_registry
except ImportError:
    pass

# After settings are loaded, import other modules
from .umi_template import (  # noqa: E402
    BuildingTemplate,
    UmiTemplateLibrary,
)
from .utils import clear_cache, config, parallel_process  # noqa: E402

try:
    __version__ = version("archetypal")
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"

__all__ = [
    "settings",
    "Settings",
    "__version__",
    "BuildingTemplate",
    "UmiTemplateLibrary",
    "__version__",
    "clear_cache",
    "config",
    "dataportal",
    "parallel_process",
    "settings",
    "utils",
]
