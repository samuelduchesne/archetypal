"""
IDF Model class - Main user-facing interface for EnergyPlus models.

This class replaces the eppy-based IDF class with a new implementation
based on the archetypal parser. It maintains backward compatibility
for most common operations.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import logging
import os
import shutil
import time
import uuid
import warnings
from collections.abc import Iterable
from io import StringIO
from pathlib import Path
from typing import Any, ClassVar, Iterator, Literal, TYPE_CHECKING

import numpy as np

from eppy_plus import (
    IDFDocument,
    IDFObject,
    IDFCollection,
    parse_idf,
    get_idf_version as _get_idf_version,
    parse_epjson,
    write_idf,
    write_epjson,
    get_schema,
    EpJSONSchema,
    validate_document,
    ValidationResult,
    EppyPlusError,
    VersionNotFoundError,
    DuplicateObjectError,
)

if TYPE_CHECKING:
    from archetypal.eplus_interface.version import EnergyPlusVersion

# Type alias for reporting frequency
ReportingFrequency = Literal["Annual", "Monthly", "Daily", "Hourly", "Timestep"]


class IDF:
    """
    Main class for working with EnergyPlus IDF and epJSON files.

    This is the primary interface for:
    - Loading and parsing IDF/epJSON files
    - Accessing and modifying model objects
    - Running EnergyPlus simulations
    - Saving models in IDF or epJSON format

    Example:
        >>> idf = IDF("model.idf", epw="weather.epw")
        >>> print(len(idf.zones))
        >>> idf.simulate()
        >>> idf.save()

    Attributes:
        idfname: Path to the IDF file
        epw: Path to the weather file
        version: EnergyPlus version tuple
    """

    # Class-level cache for schemas
    _schema_cache: ClassVar[dict[tuple, EpJSONSchema]] = {}

    def __init__(
        self,
        idfname: str | Path | StringIO | None = None,
        epw: str | Path | None = None,
        as_version: str | "EnergyPlusVersion" | None = None,
        annual: bool = False,
        design_day: bool = False,
        expandobjects: bool = False,
        convert: bool = False,
        verbose: bool = False,
        readvars: bool = True,
        prep_outputs: bool = True,
        include: list | None = None,
        output_suffix: str = "L",
        epmacro: bool = False,
        keep_data: bool = True,
        keep_data_err: bool = False,
        name: str | None = None,
        output_directory: str | Path | None = None,
        encoding: str | None = "latin-1",
        reporting_frequency: ReportingFrequency = "Monthly",
        **kwargs,
    ):
        """
        Initialize an IDF object.

        Args:
            idfname: Path to IDF/epJSON file, or StringIO for in-memory model
            epw: Path to weather file
            as_version: Target EnergyPlus version (triggers transition if higher)
            annual: Force annual simulation
            design_day: Force design-day only simulation
            expandobjects: Run ExpandObjects preprocessor
            convert: Convert between IDF and epJSON
            verbose: Enable verbose output
            readvars: Run ReadVarsESO after simulation
            prep_outputs: Add default outputs
            include: Additional files to include
            output_suffix: Output file naming style (L, C, or D)
            epmacro: Run EPMacro preprocessor
            keep_data: Keep simulation output files
            keep_data_err: Keep error files
            name: Model name (defaults to filename)
            output_directory: Directory for simulation outputs
            encoding: File encoding (default: latin-1)
            reporting_frequency: Output reporting frequency
        """
        # Store configuration
        self._encoding = encoding or "latin-1"
        self._epw = Path(epw) if epw else None
        self._as_version = as_version
        self._annual = annual
        self._design_day = design_day
        self._expandobjects = expandobjects
        self._convert = convert
        self._verbose = verbose
        self._readvars = readvars
        self._prep_outputs = prep_outputs
        self._include = include or []
        self._output_suffix = output_suffix
        self._epmacro = epmacro
        self._keep_data = keep_data
        self._keep_data_err = keep_data_err
        self._output_directory = Path(output_directory) if output_directory else None
        self._reporting_frequency = reporting_frequency

        # Internal state
        self._document: IDFDocument | None = None
        self._idfname: Path | StringIO | None = None
        self._name = name
        self._outputs = None
        self._meters = None
        self._variables = None
        self._sql = None
        self._htm = None
        self._sim_id = None
        self._sim_timestamp = None
        self._original_cache = None

        # Load the model
        if idfname is not None:
            self._load(idfname)
        else:
            # Create empty in-memory model
            self._create_empty(as_version)

        # Set up outputs if requested
        if self._prep_outputs:
            self._setup_outputs()

    def _load(self, idfname: str | Path | StringIO) -> None:
        """Load model from file or StringIO."""
        if isinstance(idfname, StringIO):
            self._idfname = idfname
            self._load_from_string(idfname.getvalue())
        else:
            self._idfname = Path(idfname)
            if not self._idfname.exists():
                raise FileNotFoundError(f"IDF file not found: {self._idfname}")
            self._load_from_file(self._idfname)

        if self._name is None and isinstance(self._idfname, Path):
            self._name = self._idfname.stem

    def _load_from_file(self, filepath: Path) -> None:
        """Load model from file."""
        suffix = filepath.suffix.lower()

        if suffix == ".epjson":
            self._document = parse_epjson(filepath)
        else:
            self._document = parse_idf(filepath, encoding=self._encoding)

        # Cache schema
        if self._document.version not in self._schema_cache:
            try:
                self._schema_cache[self._document.version] = get_schema(
                    self._document.version
                )
            except Exception:
                pass  # Schema not available

    def _load_from_string(self, content: str) -> None:
        """Load model from string content."""
        import tempfile

        # Write to temp file and parse
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".idf", delete=False, encoding=self._encoding
        ) as f:
            f.write(content)
            temp_path = Path(f.name)

        try:
            self._document = parse_idf(temp_path, encoding=self._encoding)
        finally:
            temp_path.unlink()

    def _create_empty(self, version: str | "EnergyPlusVersion" | None = None) -> None:
        """Create empty in-memory model."""
        if version is None:
            from archetypal.utils import settings
            version = settings.ep_version

        # Parse version
        if hasattr(version, "as_tuple"):
            version_tuple = version.as_tuple()
        elif isinstance(version, str):
            parts = version.replace("-", ".").split(".")
            version_tuple = tuple(int(p) for p in parts[:3])
        else:
            version_tuple = version

        # Ensure 3 components
        if len(version_tuple) == 2:
            version_tuple = (*version_tuple, 0)

        self._document = IDFDocument(version=version_tuple)
        self._idfname = StringIO()

    def _setup_outputs(self) -> None:
        """Set up default outputs."""
        from archetypal.idfclass.outputs import Outputs

        self._outputs = Outputs(
            idf=self,
            include_html=True,
            include_sqlite=True,
            reporting_frequency=self._reporting_frequency,
        )
        self._outputs.add_basics()
        self._outputs.add_profile_gas_elect_outputs()
        self._outputs.add_umi_template_outputs()
        self._outputs.apply()

    # -------------------------------------------------------------------------
    # Core Properties
    # -------------------------------------------------------------------------

    @property
    def idfname(self) -> Path | StringIO:
        """Path to the IDF file."""
        return self._idfname

    @idfname.setter
    def idfname(self, value: str | Path | StringIO | None):
        if value is None:
            self._idfname = StringIO()
        elif isinstance(value, StringIO):
            self._idfname = value
        else:
            self._idfname = Path(value)

    @property
    def name(self) -> str | None:
        """Model name."""
        return self._name

    @name.setter
    def name(self, value: str):
        self._name = value

    @property
    def version(self) -> tuple[int, int, int]:
        """EnergyPlus version tuple."""
        return self._document.version

    @property
    def file_version(self) -> "EnergyPlusVersion":
        """EnergyPlus version as EnergyPlusVersion object."""
        from archetypal.eplus_interface.version import EnergyPlusVersion
        return EnergyPlusVersion(self._document.version)

    @property
    def epw(self) -> Path | None:
        """Weather file path."""
        return self._epw

    @epw.setter
    def epw(self, value: str | Path | None):
        self._epw = Path(value) if value else None

    @property
    def encoding(self) -> str:
        """File encoding."""
        return self._encoding

    @encoding.setter
    def encoding(self, value: str):
        self._encoding = value

    # -------------------------------------------------------------------------
    # Object Access (eppy compatibility)
    # -------------------------------------------------------------------------

    @property
    def idfobjects(self) -> dict[str, IDFCollection]:
        """
        Dict-like access to all object collections.

        Example:
            >>> zones = idf.idfobjects["Zone"]
            >>> for zone in zones:
            ...     print(zone.Name)
        """
        return self._document.idfobjects

    def getobject(self, obj_type: str, name: str) -> IDFObject | None:
        """
        Get a specific object by type and name.

        Args:
            obj_type: Object type (e.g., "Zone")
            name: Object name

        Returns:
            IDFObject or None if not found
        """
        return self._document.getobject(obj_type, name)

    def newidfobject(self, obj_type: str, **kwargs) -> IDFObject:
        """
        Create a new IDF object.

        Args:
            obj_type: Object type (e.g., "Zone")
            **kwargs: Field values (Name is extracted if provided)

        Returns:
            The created IDFObject
        """
        return self._document.newidfobject(obj_type, **kwargs)

    def addidfobject(self, obj: IDFObject) -> IDFObject:
        """Add an existing IDFObject to the model."""
        return self._document.addidfobject(obj)

    def addidfobjects(self, objects: list[IDFObject]) -> list[IDFObject]:
        """Add multiple objects to the model."""
        return self._document.addidfobjects(objects)

    def removeidfobject(self, obj: IDFObject) -> None:
        """Remove an object from the model."""
        self._document.removeidfobject(obj)

    def removeidfobjects(self, objects: list[IDFObject]) -> None:
        """Remove multiple objects from the model."""
        self._document.removeidfobjects(objects)

    def copyidfobject(self, obj: IDFObject, new_name: str | None = None) -> IDFObject:
        """Create a copy of an object with optional new name."""
        return self._document.copyidfobject(obj, new_name)

    def rename(self, obj_type: str, old_name: str, new_name: str) -> None:
        """Rename an object and update all references."""
        self._document.rename(obj_type, old_name, new_name)

    # -------------------------------------------------------------------------
    # Convenience Accessors
    # -------------------------------------------------------------------------

    @property
    def zones(self) -> IDFCollection:
        """Collection of Zone objects."""
        return self._document["Zone"]

    @property
    def materials(self) -> IDFCollection:
        """Collection of Material objects."""
        return self._document["Material"]

    @property
    def constructions(self) -> IDFCollection:
        """Collection of Construction objects."""
        return self._document["Construction"]

    @property
    def schedules_dict(self) -> dict[str, IDFObject]:
        """Dict mapping schedule names (uppercase) to schedule objects."""
        return self._document.schedules_dict

    def getsurfaces(self, surface_type: str | None = None) -> list[IDFObject]:
        """Get building surfaces, optionally filtered by type."""
        return self._document.getsurfaces(surface_type)

    def getiddgroupdict(self) -> dict[str, list[str]]:
        """Get dict of object groups."""
        return self._document.getiddgroupdict()

    # -------------------------------------------------------------------------
    # References
    # -------------------------------------------------------------------------

    def get_referencing(self, name: str) -> set[IDFObject]:
        """Get all objects that reference a given name."""
        return self._document.get_referencing(name)

    def get_used_schedules(self) -> set[str]:
        """Get names of schedules actually used in the model."""
        return self._document.get_used_schedules()

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    def validate(self, **kwargs) -> ValidationResult:
        """
        Validate the model against schema.

        Returns:
            ValidationResult with errors and warnings
        """
        return validate_document(self._document, **kwargs)

    def is_valid(self) -> bool:
        """Check if model is valid."""
        return self.validate().is_valid

    # -------------------------------------------------------------------------
    # Saving
    # -------------------------------------------------------------------------

    def save(
        self,
        lineendings: str = "default",
        encoding: str | None = None,
    ) -> "IDF":
        """
        Save the model to the original file.

        Args:
            lineendings: Line ending style ('default', 'windows', 'unix')
            encoding: File encoding (default: latin-1)

        Returns:
            Self
        """
        if isinstance(self._idfname, StringIO):
            raise ValueError("Cannot save in-memory model. Use saveas() instead.")

        encoding = encoding or self._encoding
        write_idf(self._document, self._idfname, encoding=encoding)
        return self

    def saveas(
        self,
        filename: str | Path | StringIO,
        lineendings: str = "default",
        encoding: str | None = None,
        inplace: bool = False,
    ) -> "IDF":
        """
        Save the model to a new file.

        Args:
            filename: Output path or StringIO
            lineendings: Line ending style
            encoding: File encoding
            inplace: If True, update self to point to new file

        Returns:
            New IDF object (or self if inplace=True)
        """
        encoding = encoding or self._encoding

        if isinstance(filename, StringIO):
            content = write_idf(self._document, None, encoding=encoding)
            filename.write(content)
            new_path = filename
        else:
            new_path = Path(filename)
            suffix = new_path.suffix.lower()

            if suffix == ".epjson":
                write_epjson(self._document, new_path)
            else:
                write_idf(self._document, new_path, encoding=encoding)

        if inplace:
            self._idfname = new_path
            if isinstance(new_path, Path):
                self._name = new_path.stem
            return self
        else:
            # Create new IDF object
            return IDF(
                new_path,
                epw=self._epw,
                as_version=self._as_version,
                annual=self._annual,
                design_day=self._design_day,
                encoding=encoding,
            )

    def savecopy(
        self,
        filename: str | Path,
        lineendings: str = "default",
        encoding: str | None = None,
    ) -> Path:
        """
        Save a copy of the model.

        Args:
            filename: Output path
            lineendings: Line ending style
            encoding: File encoding

        Returns:
            Path to saved file
        """
        encoding = encoding or self._encoding
        filepath = Path(filename)

        suffix = filepath.suffix.lower()
        if suffix == ".epjson":
            write_epjson(self._document, filepath)
        else:
            write_idf(self._document, filepath, encoding=encoding)

        return filepath

    def copy(self) -> "IDF":
        """
        Create an in-memory copy of the model.

        Returns:
            New IDF object
        """
        new_doc = self._document.copy()
        new_idf = IDF.__new__(IDF)
        new_idf._document = new_doc
        new_idf._idfname = StringIO()
        new_idf._name = self._name
        new_idf._epw = self._epw
        new_idf._as_version = self._as_version
        new_idf._annual = self._annual
        new_idf._design_day = self._design_day
        new_idf._expandobjects = self._expandobjects
        new_idf._convert = self._convert
        new_idf._verbose = self._verbose
        new_idf._readvars = self._readvars
        new_idf._prep_outputs = self._prep_outputs
        new_idf._include = self._include
        new_idf._output_suffix = self._output_suffix
        new_idf._epmacro = self._epmacro
        new_idf._keep_data = self._keep_data
        new_idf._keep_data_err = self._keep_data_err
        new_idf._output_directory = self._output_directory
        new_idf._reporting_frequency = self._reporting_frequency
        new_idf._encoding = self._encoding
        new_idf._outputs = None
        new_idf._meters = None
        new_idf._variables = None
        new_idf._sql = None
        new_idf._htm = None
        new_idf._sim_id = None
        new_idf._sim_timestamp = None
        new_idf._original_cache = None
        return new_idf

    # -------------------------------------------------------------------------
    # String Conversion
    # -------------------------------------------------------------------------

    def idfstr(self) -> str:
        """Get the IDF file content as a string."""
        return write_idf(self._document, None, encoding=self._encoding)

    def to_epjson(self) -> dict:
        """Convert to epJSON dict."""
        from .writers import EpJSONWriter
        return EpJSONWriter(self._document).to_dict()

    # -------------------------------------------------------------------------
    # Iteration
    # -------------------------------------------------------------------------

    @property
    def all_objects(self) -> Iterator[IDFObject]:
        """Iterate over all objects in the model."""
        return self._document.all_objects

    def __len__(self) -> int:
        """Return total number of objects."""
        return len(self._document)

    def __contains__(self, obj_type: str) -> bool:
        """Check if model has objects of a type."""
        return obj_type in self._document

    def __iter__(self) -> Iterator[str]:
        """Iterate over object type names."""
        return iter(self._document)

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __str__(self) -> str:
        return self._name or "Unnamed IDF"

    def __repr__(self) -> str:
        version_str = f"{self.version[0]}.{self.version[1]}.{self.version[2]}"
        filepath = self._idfname if isinstance(self._idfname, Path) else "<in-memory>"
        return f"IDF('{self._name}', version={version_str}, path={filepath}, objects={len(self)})"

    def __copy__(self):
        return self.copy()

    # -------------------------------------------------------------------------
    # Simulation (delegates to eplus_interface)
    # -------------------------------------------------------------------------

    @property
    def simulation_dir(self) -> Path:
        """Directory containing simulation results."""
        from archetypal.utils import settings

        if self._output_directory:
            base = self._output_directory
        else:
            base = Path(settings.cache_folder)

        return base / self._get_sim_id()

    @property
    def simulation_files(self) -> list[Path]:
        """List of simulation output files."""
        if self.simulation_dir.exists():
            return list(self.simulation_dir.glob("*"))
        return []

    def _get_sim_id(self) -> str:
        """Generate unique simulation ID based on model hash."""
        if self._sim_id is None:
            from archetypal.idfclass.util import hash_model
            self._sim_id = hash_model(self)
        return self._sim_id

    def simulate(self, force: bool = False, **kwargs) -> "IDF":
        """
        Run EnergyPlus simulation.

        Args:
            force: Force simulation even if results exist
            **kwargs: Override simulation parameters

        Returns:
            Self
        """
        # Import here to avoid circular imports
        from archetypal.eplus_interface.energy_plus import EnergyPlusThread
        from archetypal.eplus_interface.expand_objects import ExpandObjectsThread
        from archetypal.eplus_interface.basement import BasementThread
        from archetypal.eplus_interface.slab import SlabThread
        from archetypal.eplus_interface.exceptions import (
            EnergyPlusProcessError,
            EnergyPlusWeatherError,
        )
        from archetypal.utils import log

        # Update parameters from kwargs
        for key, value in kwargs.items():
            if hasattr(self, f"_{key}"):
                setattr(self, f"_{key}", value)

        # Check if results already exist
        if self.simulation_dir.exists() and not force:
            return self

        # Ensure weather file is set
        if not self._epw:
            raise EnergyPlusWeatherError(
                f"No weather file specified. Set epw parameter."
            )

        # Create output directory
        output_dir = self._output_directory or Path.cwd() / "simulation_output"
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run preprocessors and simulation
        # (This is a simplified version - full implementation would match original)

        # Run ExpandObjects
        tmp = output_dir / f"expandobjects_{uuid.uuid1().hex[:8]}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            thread = ExpandObjectsThread(self, tmp)
            thread.start()
            thread.join()
            if thread.exception:
                raise thread.exception
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # Run EnergyPlus
        tmp = output_dir / f"eplus_{uuid.uuid1().hex[:8]}"
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            thread = EnergyPlusThread(self, tmp)
            thread.start()
            thread.join()
            if thread.exception:
                raise thread.exception
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        return self

    # -------------------------------------------------------------------------
    # Class Methods
    # -------------------------------------------------------------------------

    @classmethod
    def from_example_files(
        cls,
        example_name: str,
        epw: str | None = None,
        **kwargs,
    ) -> "IDF":
        """
        Load an IDF from EnergyPlus ExampleFiles.

        Args:
            example_name: Name of example file (without .idf extension)
            epw: Weather file name or path
            **kwargs: Additional IDF parameters

        Returns:
            IDF object
        """
        from archetypal.eplus_interface.version import EnergyPlusVersion

        version = EnergyPlusVersion(kwargs.get("as_version", EnergyPlusVersion.current()))
        example_dir = version.current_install_dir / "ExampleFiles"

        # Find the example file
        matches = list(example_dir.rglob(f"{example_name}.idf"))
        if not matches:
            available = sorted([f.stem for f in example_dir.glob("*.idf")])
            raise ValueError(f"Example '{example_name}' not found. Available: {available[:10]}...")

        idf_path = matches[0]

        # Find weather file if specified
        if epw:
            epw_path = Path(epw)
            if not epw_path.exists():
                weather_dir = version.current_install_dir / "WeatherData"
                matches = list(weather_dir.rglob(f"{epw_path.stem}.epw"))
                if matches:
                    epw = matches[0]

        return cls(idf_path, epw=epw, **kwargs)

    @classmethod
    def from_epjson(cls, filepath: str | Path, **kwargs) -> "IDF":
        """Load an IDF from epJSON file."""
        return cls(filepath, **kwargs)
