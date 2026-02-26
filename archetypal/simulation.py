"""Simulation interface using idfkit.

This module provides a simplified interface for running EnergyPlus simulations
and accessing results, built on top of idfkit's simulation capabilities.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from idfkit.simulation import simulate as idfkit_simulate

if TYPE_CHECKING:
    import idfkit

from archetypal.utils import log


class SimulationResult:
    """Container for simulation results.

    Provides access to simulation output files and result queries.
    """

    def __init__(self, result: idfkit.SimulationResult, output_dir: Path) -> None:
        """Initialize simulation result.

        Args:
            result: idfkit SimulationResult object
            output_dir: Directory containing output files
        """
        self._result = result
        self._output_dir = output_dir

    @property
    def sql_path(self) -> Path:
        """Path to the SQLite results database."""
        return self._output_dir / "eplusout.sql"

    @property
    def htm_path(self) -> Path:
        """Path to the HTML tabular results."""
        return self._output_dir / "eplustbl.htm"

    @property
    def err_path(self) -> Path:
        """Path to the error file."""
        return self._output_dir / "eplusout.err"

    @property
    def sql(self):
        """Access SQL query interface from idfkit."""
        return self._result.sql

    def get_timeseries(
        self,
        variable_name: str,
        key_value: str | None = None,
        frequency: str = "Hourly",
    ):
        """Get time series data for a variable.

        Args:
            variable_name: Name of the output variable
            key_value: Key value (e.g., zone name), or None for site-level
            frequency: Reporting frequency

        Returns:
            pandas DataFrame with timestamp index
        """
        return self._result.sql.get_timeseries(
            variable_name=variable_name,
            key_value=key_value,
            frequency=frequency,
        )


def simulate(
    doc: idfkit.Document,
    weather_file: str | Path,
    output_dir: str | Path | None = None,
    annual: bool = True,
    design_day: bool = False,
    expand_objects: bool = True,
) -> SimulationResult:
    """Run EnergyPlus simulation.

    Args:
        doc: idfkit Document object
        weather_file: Path to EPW weather file
        output_dir: Directory for output files (default: temp directory)
        annual: Run annual simulation
        design_day: Run design day simulation
        expand_objects: Run ExpandObjects preprocessor

    Returns:
        SimulationResult with access to output files and queries
    """
    weather_path = Path(weather_file)
    if not weather_path.exists():
        raise FileNotFoundError(f"Weather file not found: {weather_path}")

    if output_dir is None:
        import tempfile

        output_dir = Path(tempfile.mkdtemp(prefix="archetypal_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    log(f"Running simulation in {output_dir}")

    result = idfkit_simulate(
        doc,
        str(weather_path),
        output_directory=str(output_dir),
        annual=annual,
        design_day=design_day,
        expand_objects=expand_objects,
    )

    return SimulationResult(result, output_dir)


def simulate_batch(
    docs: list[idfkit.Document],
    weather_file: str | Path,
    output_base_dir: str | Path,
    **kwargs,
) -> list[SimulationResult]:
    """Run multiple simulations in parallel.

    Args:
        docs: List of idfkit Document objects
        weather_file: Path to EPW weather file
        output_base_dir: Base directory for output (subdirs created per model)
        **kwargs: Additional arguments passed to simulate()

    Returns:
        List of SimulationResult objects
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed

    from tqdm import tqdm

    output_base = Path(output_base_dir)
    results = []

    with ProcessPoolExecutor() as executor:
        futures = {}
        for i, doc in enumerate(docs):
            output_dir = output_base / f"sim_{i:04d}"
            future = executor.submit(
                simulate,
                doc,
                weather_file,
                output_dir=output_dir,
                **kwargs,
            )
            futures[future] = i

        for future in tqdm(as_completed(futures), total=len(futures), desc="Simulating"):
            idx = futures[future]
            try:
                result = future.result()
                results.append((idx, result))
            except Exception as e:
                log(f"Simulation {idx} failed: {e}")
                results.append((idx, None))

    # Sort by original index
    results.sort(key=lambda x: x[0])
    return [r for _, r in results]
